from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.bulk.service import bulk_row_summary, profile_and_validate
from cabqp.modules.document_intelligence.antimalware import scan_upload
from cabqp.modules.document_intelligence.file_validation import validate_upload
from cabqp.modules.document_intelligence.limits import DocumentLimitError
from cabqp.modules.document_intelligence.router import route_input
from cabqp.modules.document_intelligence.storage import ObjectStorage
from cabqp.shared.db import get_db
from cabqp.shared.models import BulkIngestJob, BulkIngestRow, RowError
from cabqp.shared.settings import get_settings

router=APIRouter(prefix="/bulk",tags=["bulk"])

class MappingConfirm(BaseModel):
    mapping: dict[str,str|None] = Field(default_factory=dict)


def _auth(job: BulkIngestJob,p: Principal):
    # Bulk source files can contain many personal records. REVIEWER does not get
    # blanket access merely by role; only the owner or ADMIN may inspect/import it.
    if job.created_by != p.username and "ADMIN" not in p.roles:
        raise HTTPException(403,"Bulk job not accessible")


def _row_views(db: Session, job: BulkIngestJob, limit: int = 200) -> list[dict]:
    rows=list(db.scalars(
        select(BulkIngestRow)
        .where(BulkIngestRow.job_id==job.id)
        .order_by(BulkIngestRow.row_index)
        .limit(limit)
    ))
    return [bulk_row_summary(row,job.mapping_json or {}) for row in rows]

@router.post("",status_code=202)
def create_bulk(file: UploadFile=File(...),db:Session=Depends(get_db),p:Principal=Depends(require_perms(perms.CASE_BULK))):
    content=file.file.read(); s=get_settings()
    if not content: raise HTTPException(422,"Empty upload")
    if len(content)>s.max_upload_mb*1024*1024: raise HTTPException(413,"File too large")
    name,mime=validate_upload(file.filename,content,file.content_type); scan_upload(content)
    try:
        decision=route_input(name,content)
    except DocumentLimitError as exc:
        raise HTTPException(422,exc.code) from exc
    ext=Path(name).suffix.lower()
    structured_document=ext in {".pdf", ".docx"}
    if decision.kind.value != "TABULAR_LIST" and not structured_document:
        raise HTTPException(422,f"Bulk endpoint requires a tabular list, got {decision.kind.value}")
    digest=sha256(content).hexdigest()
    existing=db.scalar(select(BulkIngestJob).where(BulkIngestJob.file_sha256==digest))
    if existing:
        if existing.created_by == p.username or "ADMIN" in p.roles:
            return {"job_id":existing.id,"status":existing.status,"duplicate_file":True}
        raise HTTPException(409,"This exact file was already ingested")
    job=BulkIngestJob(file_name=name,file_sha256=digest,status="UPLOADED",created_by=p.username)
    db.add(job); db.flush()
    try:
        # Profile first so a PDF/DOCX without a real record table does not leave an
        # orphaned object in storage. Scan PDFs may invoke PP-StructureV3 here.
        profile_and_validate(db,job,content)
    except (ValueError,DocumentLimitError) as exc:
        db.rollback()
        detail = exc.code if isinstance(exc,DocumentLimitError) else str(exc)
        raise HTTPException(422,detail) from exc
    key=f"bulk/{job.id}/{digest}_{name}"; job.storage_uri=ObjectStorage().put(key,content,mime)
    audit(
        db, actor=p.username, role=next(iter(p.roles), None), action="BULK_CREATE",
        entity_type="BULK_JOB", entity_id=job.id,
        metadata={"file_name":name,"file_sha256":digest,"rows":job.total_rows,"status":job.status},
    )
    db.commit()
    return {"job_id":job.id,"status":job.status,"profile":job.profile_json,"validation":job.validation_report,"mapping":job.mapping_json,"rows":_row_views(db,job)}

@router.post("/{job_id}/confirm",status_code=202)
def confirm_bulk(job_id:str,body:MappingConfirm,db:Session=Depends(get_db),p:Principal=Depends(require_perms(perms.CASE_BULK))):
    job=db.scalar(select(BulkIngestJob).where(BulkIngestJob.id==job_id).with_for_update())
    if not job: raise HTTPException(404,"Bulk job not found")
    _auth(job,p)
    if job.status in {"QUEUED","PROCESSING","COMPLETED","COMPLETED_WITH_ERRORS"}:
        return {"job_id":job.id,"status":job.status,"idempotent_replay":True}
    if job.status=="FAILED":
        raise HTTPException(409,"Failed bulk jobs must be re-uploaded after correcting the source file")
    if body.mapping:
        key=job.storage_uri.split(f"s3://{get_settings().minio_bucket}/",1)[-1]
        content=ObjectStorage().get(key)
        try:
            profile_and_validate(db,job,content,user_mapping=body.mapping)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
    if job.status not in {"PROFILED","AWAITING_MAPPING"}: raise HTTPException(409,f"Cannot queue job in status {job.status}")
    if job.status=="AWAITING_MAPPING": raise HTTPException(409,"Header mapping is incomplete; subject_name must be mapped")
    job.status="QUEUED"
    audit(
        db, actor=p.username, role=next(iter(p.roles), None), action="BULK_CONFIRM",
        entity_type="BULK_JOB", entity_id=job.id,
        metadata={"mapping_version":job.mapping_version,"mapping":job.mapping_json,"rows":job.total_rows},
    )
    db.commit()
    queue_status="PENDING"
    try:
        from cabqp.workers.local_queue import enqueue
        from cabqp.workers.tasks import process_bulk_job
        enqueue(process_bulk_job, job.id)
        queue_status="DISPATCH_REQUESTED"
    except Exception:
        # Job remains QUEUED; periodic reconcile will dispatch it after broker recovery.
        queue_status="PENDING_RETRY"
    return {"job_id":job.id,"status":"QUEUED","queue_status":queue_status}

@router.get("/{job_id}")
def get_bulk(job_id:str,db:Session=Depends(get_db),p:Principal=Depends(require_perms(perms.CASE_BULK))):
    job=db.get(BulkIngestJob,job_id)
    if not job: raise HTTPException(404,"Bulk job not found")
    _auth(job,p)
    errors=list(db.scalars(select(RowError).where(RowError.job_id==job.id).order_by(RowError.row_index)))
    return {"job":{"id":job.id,"status":job.status,"total_rows":job.total_rows,"processed":job.processed,"succeeded":job.succeeded,"failed":job.failed,"skipped":job.skipped,"mapping":job.mapping_json,"validation":job.validation_report},"rows":_row_views(db,job),"errors":[{"row_index":e.row_index,"column":e.column,"code":e.code,"severity":e.severity,"message_vi":e.message_vi} for e in errors]}
