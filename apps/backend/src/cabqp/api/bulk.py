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
from cabqp.modules.document_intelligence.storage import ObjectStorage, key_from_uri
from cabqp.shared.db import get_db
from cabqp.shared.models import BulkIngestJob, BulkIngestRow, Case, RowError, VerificationResult
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
    views=[bulk_row_summary(row,job.mapping_json or {}) for row in rows]

    # Each imported row becomes its own Case, decided independently. The summary
    # above describes what was *read* out of the spreadsheet; the client also has
    # to show what the pipeline *concluded*, or a finished job renders as a list
    # of names with no verdict. The field names mirror `GET /cases/{id}/subjects`
    # exactly so one list component can render either source.
    case_ids=[view["case_id"] for view in views if view.get("case_id")]
    if not case_ids:
        return views
    cases={c.id: c for c in db.scalars(select(Case).where(Case.id.in_(case_ids)))}
    results={
        r.case_id: r
        for r in db.scalars(select(VerificationResult).where(VerificationResult.case_id.in_(case_ids)))
    }
    for view in views:
        case=cases.get(view.get("case_id"))
        if case is None:
            continue
        result=results.get(case.id)
        view["workflow_status"]=case.workflow_status
        view["organization_type"]=result.organization_type if result else "UNKNOWN"
        view["resolution_status"]=result.resolution_status if result else None
        view["current_unit"]=(result.evidence or {}).get("canonical_name") if result else None
    return views

def _limit_detail(exc: Exception) -> str|dict:
    """Describe a rejected upload well enough for the operator to act on it.

    A bare error code is enough for a log line but not for a person: the row cap
    in particular has to say how many rows the file holds and how many are
    allowed, and it has to say it in Vietnamese, because the client shows this
    text verbatim. Other codes keep their existing bare-code shape so nothing
    that already matches on them breaks.
    """
    if not isinstance(exc,DocumentLimitError):
        return str(exc)
    if exc.code=="BULK_ROW_LIMIT_EXCEEDED":
        rows=exc.details.get("rows"); limit=exc.details.get("limit")
        return {
            "code": exc.code,
            "rows": rows,
            "limit": limit,
            "message": (
                f"Danh sách có {rows} dòng, vượt quá giới hạn {limit} dòng cho một lần nhập. "
                f"Hãy tách tệp thành nhiều phần, mỗi phần tối đa {limit} dòng."
            ),
        }
    return exc.code


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
        raise HTTPException(422,_limit_detail(exc)) from exc
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
        if not job.storage_uri:
            raise HTTPException(409,"Bulk source file is no longer available; re-upload it")
        content=ObjectStorage().get(key_from_uri(job.storage_uri))
        try:
            profile_and_validate(db,job,content,user_mapping=body.mapping)
        except ValueError as exc:
            # DocumentLimitError is a ValueError, so the row cap reaches here too
            # when a confirm re-profiles the source file.
            raise HTTPException(422,_limit_detail(exc)) from exc
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
