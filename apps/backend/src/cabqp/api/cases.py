from __future__ import annotations

import logging
from datetime import date
from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, current_principal, require_perms
from cabqp.modules.cases.service import process_case
from cabqp.modules.document_intelligence.antimalware import scan_upload
from cabqp.modules.document_intelligence.file_validation import validate_upload
from cabqp.modules.document_intelligence.limits import DocumentLimitError
from cabqp.modules.document_intelligence.router import route_input
from cabqp.modules.document_intelligence.storage import ObjectStorage
from cabqp.modules.document_intelligence.subject_split import detect_subject_blocks
from cabqp.shared.db import get_db
from cabqp.shared.models import (
    Case,
    Document,
    EligibilityAssessment,
    ExtractedRecord,
    OutboxEvent,
    PolicyRule,
    ReviewCase,
    VerificationResult,
)
from cabqp.shared.schemas import CaseCreate
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["cases"])


def _sees_every_case(p: Principal) -> bool:
    """CASE_VIEW_ALL lifts the own-cases-only default; admin holds it implicitly."""
    return p.is_admin or perms.CASE_VIEW_ALL in p.permissions


def _reviewer_case_scope_query(p: Principal):
    """Cases reachable through this account's review queue, as a subquery."""
    q = select(ReviewCase.case_id)
    if p.is_admin or "*" in p.coverage_groups:
        return q
    if not p.coverage_groups:
        return q if _sees_every_case(p) else q.where(False)
    return q.where(
        ReviewCase.coverage_group.in_(sorted(p.coverage_groups)),
        (ReviewCase.assigned_to.is_(None)) | (ReviewCase.assigned_to == p.username),
    )


def _authorize(db: Session, case: Case, p: Principal):
    if case.created_by == p.username or _sees_every_case(p):
        return
    if perms.REVIEW_QUEUE in p.permissions or perms.REVIEW_DECIDE in p.permissions:
        allowed = db.scalar(
            _reviewer_case_scope_query(p).where(ReviewCase.case_id == case.id).limit(1)
        )
        if allowed:
            return
    raise HTTPException(403, "Case not accessible")


def _existing_idempotent_case(db: Session, actor: str, key: str | None) -> Case | None:
    if not key:
        return None
    return db.scalar(select(Case).where(Case.created_by == actor, Case.idempotency_key == key))


def _salary_status(db: Session, assessments: list[EligibilityAssessment]) -> str:
    """Derive salary status only from rules that explicitly own that output field.

    Policy names are presentation data and must never be parsed to infer semantics.
    A rule participates in this projection only when its versioned rule_expression
    declares ``outcome_field = "salary_status"``. This keeps salary derivation
    deterministic and prevents unrelated welfare/insurance rules from being reused.
    """
    if not assessments:
        return "Không đủ dữ liệu"
    policy_ids = [a.policy_id for a in assessments]
    rules = {
        row.id: row
        for row in db.scalars(select(PolicyRule).where(PolicyRule.id.in_(policy_ids)))
    }
    salary_assessments = [
        a
        for a in assessments
        if isinstance((rules.get(a.policy_id).rule_expression if rules.get(a.policy_id) else None), dict)
        and (rules[a.policy_id].rule_expression or {}).get("outcome_field") == "salary_status"
    ]
    if not salary_assessments:
        return "Không đủ dữ liệu"
    if any(a.status == "INSUFFICIENT_DATA" for a in salary_assessments):
        return "Không đủ dữ liệu"
    if any(a.status == "ELIGIBLE" for a in salary_assessments):
        return "Có"
    if all(a.status in {"NOT_ELIGIBLE", "NOT_APPLICABLE"} for a in salary_assessments):
        return "Không"
    return "Không đủ dữ liệu"


#: Fields an operator can correct on an OCR result before re-running it.
CORRECTABLE_FIELDS = ("subject_name", "subject_code", "position", "unit_name")


def _resolve_correction_source(db: Session, body: CaseCreate, p: Principal) -> tuple[Case | None, dict]:
    """Load the Case being corrected and work out what the operator changed.

    The diff is computed here from the original's stored extraction rather than
    taken from the request: the client knows what it displayed, but only the
    server knows what the pipeline actually produced, and that is what the
    evidence has to compare against.
    """
    if not body.corrected_from_case_id:
        return None, {}

    source = db.get(Case, body.corrected_from_case_id)
    if source is None:
        raise HTTPException(404, "Không tìm thấy hồ sơ gốc để hiệu đính")
    # Correcting a Case is a read of it, so it takes the same access check.
    _authorize(db, source, p)

    original = db.scalar(
        select(ExtractedRecord).where(ExtractedRecord.case_id == source.id)
    )
    before = {
        "subject_name": original.subject_name if original else None,
        "subject_code": original.subject_code if original else None,
        "position": original.position if original else None,
        "unit_name": original.current_unit_raw if original else None,
    }
    submitted = {field: getattr(body, field, None) for field in CORRECTABLE_FIELDS}

    changed = {
        field: {"from": before.get(field), "to": submitted.get(field)}
        for field in CORRECTABLE_FIELDS
        if (submitted.get(field) or None) != (before.get(field) or None)
    }
    return source, {
        "source_case_id": source.id,
        "corrected_fields": sorted(changed),
        "changes": changed,
        "corrected_by": p.username,
    }


@router.post("/text")
def create_text_case(
    body: CaseCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.CASE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=160),
):
    existing = _existing_idempotent_case(db, p.username, idempotency_key)
    if existing:
        result = db.scalar(select(VerificationResult).where(VerificationResult.case_id == existing.id))
        return {
            "case_id": existing.id,
            "workflow_status": existing.workflow_status,
            "result_id": result.id if result else None,
            "idempotent_replay": True,
        }

    source_case, correction = _resolve_correction_source(db, body, p)

    try:
        blocks = detect_subject_blocks(body.text, "PLAIN_TEXT")
        payload = body.model_dump(mode="json")
        if correction:
            # Carried into the Case payload so process_case stamps it onto the
            # result's evidence alongside the registry/policy versions.
            payload["_operator_correction"] = correction
        c = Case(
            created_by=p.username,
            input_type="TEXT",
            raw_text=blocks[0].text if blocks else body.text,
            input_payload=payload,
            idempotency_key=idempotency_key,
        )
        db.add(c)
        db.flush()
        cases=[c]
        results=[]
        for block in blocks or []:
            if block.index == 0:
                current=c
            else:
                current=Case(
                    created_by=p.username,
                    input_type="TEXT",
                    raw_text=block.text,
                    input_payload=body.model_dump(mode="json"),
                    idempotency_key=f"{c.id}:{block.index}",
                )
                db.add(current); db.flush(); cases.append(current)
            structured=dict(payload)
            if len(blocks) > 1:
                structured["_split_source"]={
                    "source_case_id":c.id,
                    "block_index":block.index,
                    "block_count":len(blocks),
                }
            results.append(process_case(db,current,structured))
            if correction and block.index == 0:
                action = "CASE_CORRECTED"
            elif block.index == 0:
                action = "CASE_CREATE"
            else:
                action = "SPLIT_CASE_CREATE"
            audit(
                db,
                actor=p.username,
                role=next(iter(p.roles), None),
                action=action,
                entity_type="CASE",
                entity_id=current.id,
                metadata={
                    "source_case_id":c.id,
                    "block_index":block.index,
                    "block_count":len(blocks),
                    **({"operator_correction": correction} if correction and block.index == 0 else {}),
                },
            )
        if not blocks:
            results.append(process_case(db,c,dict(payload)))
        db.commit()
    except IntegrityError:
        # Concurrent request with the same Idempotency-Key won the race; treat as a replay.
        db.rollback()
        existing = _existing_idempotent_case(db, p.username, idempotency_key)
        if not existing:
            raise
        result = db.scalar(select(VerificationResult).where(VerificationResult.case_id == existing.id))
        return {
            "case_id": existing.id,
            "workflow_status": existing.workflow_status,
            "result_id": result.id if result else None,
            "idempotent_replay": True,
        }
    except Exception:
        db.rollback()
        logger.exception("text_case_processing_failed", extra={"event": {"actor": p.username}})
        raise
    result=results[0]
    return {
        "case_id":c.id,
        "case_ids":[item.id for item in cases],
        "subject_count":len(cases),
        "workflow_status":c.workflow_status,
        "result_id":result.id,
        "corrected_from_case_id":source_case.id if source_case else None,
        "corrected_fields":correction.get("corrected_fields") if correction else None,
    }


@router.post("/file", status_code=202)
def create_file_case(
    file: UploadFile = File(...),
    as_of_date: date | None = Form(default=None),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.CASE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=160),
):
    existing = _existing_idempotent_case(db, p.username, idempotency_key)
    if existing:
        d = db.scalar(
            select(Document).where(Document.case_id == existing.id).order_by(Document.id).limit(1)
        )
        return {
            "case_id": existing.id,
            "document_id": d.id if d else None,
            "workflow_status": existing.workflow_status,
            "idempotent_replay": True,
        }

    content = file.file.read()
    s = get_settings()
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")
    if not content:
        raise HTTPException(422, "Empty upload")

    # Fail early before any persistence: extension, magic bytes and antimalware are independent gates.
    safe_name, detected_mime = validate_upload(file.filename, content, file.content_type)
    scan_upload(content)
    try:
        decision = route_input(safe_name, content)
    except DocumentLimitError as exc:
        raise HTTPException(422, exc.code) from exc
    is_record_list = decision.kind.value == "TABULAR_LIST"
    if not is_record_list:
        ext=Path(safe_name).suffix.lower()
        # Cheap structured-table probe for native DOCX/digital PDF. Scanned PDF tables
        # remain asynchronous and are caught by the document worker after PP-Structure.
        try:
            from cabqp.modules.bulk.service import extract_unruled_text_table, tables_have_record_list
            if ext == ".docx":
                from io import BytesIO

                from docx import Document as DocxDocument

                from cabqp.modules.document_intelligence.table import extract_docx_tables
                is_record_list=tables_have_record_list(extract_docx_tables(DocxDocument(BytesIO(content))))
            elif ext == ".pdf" and decision.kind.value != "PDF_SCAN":
                import fitz

                from cabqp.modules.document_intelligence.table import extract_pdf_tables
                pdf_tables=extract_pdf_tables(content)
                is_record_list=tables_have_record_list(pdf_tables)
                if not is_record_list:
                    doc=fitz.open(stream=content,filetype="pdf")
                    pdf_text="\n".join(page.get_text("text") or "" for page in doc)
                    doc.close()
                    text_table=extract_unruled_text_table(pdf_text)
                    is_record_list=bool(text_table) and tables_have_record_list([text_table])
        except Exception:
            # Routing must stay fail-safe: inability to prove a record list here means
            # normal async parsing will decide later; never fabricate a bulk decision.
            is_record_list=False
    if is_record_list:
        raise HTTPException(422, {"code": "TABULAR_LIST_REQUIRES_BULK", "message": "Detected a multi-row tabular list; use bulk ingestion so each row becomes an independent Case"})
    checksum = sha256(content).hexdigest()

    try:
        c = Case(
            created_by=p.username,
            input_type="FILE",
            workflow_status="RECEIVED",
            idempotency_key=idempotency_key,
            input_payload={
                "original_name": safe_name,
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
            },
        )
        db.add(c)
        db.flush()
    except IntegrityError:
        # Concurrent request with the same Idempotency-Key won the race; treat as a replay.
        db.rollback()
        existing = _existing_idempotent_case(db, p.username, idempotency_key)
        if not existing:
            raise
        d = db.scalar(
            select(Document).where(Document.case_id == existing.id).order_by(Document.id).limit(1)
        )
        return {
            "case_id": existing.id,
            "document_id": d.id if d else None,
            "workflow_status": existing.workflow_status,
            "idempotent_replay": True,
        }
    key = f"{c.id}/{checksum}_{safe_name}"

    try:
        uri = ObjectStorage().put(key, content, detected_mime)
        d = Document(
            case_id=c.id,
            file_name=safe_name,
            mime_type=detected_mime,
            size_bytes=len(content),
            storage_uri=uri,
            checksum=checksum,
        )
        db.add(d)
        db.flush()
        outbox = OutboxEvent(
            event_type="DOCUMENT_PROCESS_REQUESTED",
            aggregate_type="DOCUMENT",
            aggregate_id=d.id,
            payload={"case_id": c.id, "document_id": d.id, "storage_key": key},
        )
        db.add(outbox)
        db.flush()
        audit(
            db,
            actor=p.username,
            role=next(iter(p.roles), None),
            action="CASE_UPLOAD",
            entity_type="CASE",
            entity_id=c.id,
            metadata={"document_id": d.id, "checksum": checksum, "file_name": safe_name},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("case_upload_persist_failed", extra={"event": {"actor": p.username}})
        raise

    queue_status = "PENDING"
    try:
        from cabqp.workers.local_queue import enqueue
        from cabqp.workers.tasks import dispatch_outbox_event

        enqueue(dispatch_outbox_event, outbox.id)
        queue_status = "DISPATCH_REQUESTED"
    except Exception as exc:
        # Durable outbox preserves the request. Celery Beat will retry after the broker recovers.
        logger.exception(
            "outbox_immediate_dispatch_failed",
            extra={
                "event": {
                    "case_id": c.id,
                    "document_id": d.id,
                    "outbox_id": outbox.id,
                    "error_type": type(exc).__name__,
                }
            },
        )

    return {
        "case_id": c.id,
        "document_id": d.id,
        "workflow_status": c.workflow_status,
        "queue_status": queue_status,
    }


@router.get("")
def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = Depends(current_principal),
):
    q = select(Case)
    if not _sees_every_case(p):
        if perms.REVIEW_QUEUE in p.permissions or perms.REVIEW_DECIDE in p.permissions:
            reviewer_case_ids = _reviewer_case_scope_query(p)
            q = q.where(
                (Case.created_by == p.username) | Case.id.in_(reviewer_case_ids)
            )
        else:
            q = q.where(Case.created_by == p.username)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(
        db.scalars(
            q.order_by(Case.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    case_ids = [item.id for item in items]
    extracted_by_case = {
        row.case_id: row
        for row in db.scalars(
            select(ExtractedRecord).where(ExtractedRecord.case_id.in_(case_ids))
        )
    } if case_ids else {}
    result_by_case = {
        row.case_id: row
        for row in db.scalars(
            select(VerificationResult).where(VerificationResult.case_id.in_(case_ids))
        )
    } if case_ids else {}
    return {
        "items": [
            {
                "id": x.id,
                "workflow_status": x.workflow_status,
                "input_type": x.input_type,
                "created_by": x.created_by,
                "created_at": x.created_at,
                "subject_name": extracted_by_case[x.id].subject_name if x.id in extracted_by_case else None,
                "birth_year": (
                    (extracted_by_case[x.id].extracted_fields or {})
                    .get("structured", {})
                    .get("business_fields", {})
                    .get("birth_year")
                ) if x.id in extracted_by_case else None,
                "position": extracted_by_case[x.id].position if x.id in extracted_by_case else None,
                "current_unit": (result_by_case[x.id].evidence or {}).get("canonical_name") if x.id in result_by_case else None,
                "subject_code": extracted_by_case[x.id].subject_code if x.id in extracted_by_case else None,
                "organization_type": result_by_case[x.id].organization_type if x.id in result_by_case else "UNKNOWN",
                "resolution_status": result_by_case[x.id].resolution_status if x.id in result_by_case else None,
            }
            for x in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{case_id}")
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_principal),
):
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    _authorize(db, c, p)
    r = db.scalar(select(VerificationResult).where(VerificationResult.case_id == case_id))
    extracted = db.scalar(select(ExtractedRecord).where(ExtractedRecord.case_id == case_id))
    documents = list(db.scalars(select(Document).where(Document.case_id == case_id).order_by(Document.id)))
    assessments = []
    if r:
        assessments = list(
            db.scalars(
                select(EligibilityAssessment).where(EligibilityAssessment.result_id == r.id)
            )
        )
    person = (r.evidence or {}).get("person_resolution") if r else None
    if not r or r.resolution_status != "MATCHED" or r.organization_type == "UNKNOWN":
        in_scope = None
    elif r.organization_type in ("BCA", "BQP"):
        in_scope = True
    elif r.organization_type == "OTHER":
        in_scope = False
    else:
        in_scope = None
    subject = {
        "name": ((person or {}).get("full_name") if person else None)
        or (extracted.subject_name if extracted else None),
        "code": extracted.subject_code if extracted else None,
        "position": extracted.position if extracted else None,
    }
    synthetic_welfare_facts = None
    if person and person.get("source_kind") == "SYNTHETIC_DEMO":
        synthetic_welfare_facts = person.get("synthetic_welfare_facts")
    return {
        "subject": subject,
        "current_unit": (r.evidence or {}).get("canonical_name") if r else None,
        "organization_type": r.organization_type if r else "UNKNOWN",
        "subject_group": r.subject_group if r else None,
        "in_scope": in_scope,
        "salary_status": _salary_status(db, assessments),
        "synthetic_welfare_facts": synthetic_welfare_facts,
        "resolution_status": r.resolution_status if r else None,
        "workflow_status": c.workflow_status,
        "verification_status": "Đã xác định" if c.workflow_status == "COMPLETED" else "Cần xác minh",
        "evidence": r.evidence if r else None,
        "person": person,
        "case": {
            "id": c.id,
            "workflow_status": c.workflow_status,
            "input_type": c.input_type,
            "created_by": c.created_by,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        },
        "documents": [
            {
                "id": d.id,
                "file_name": d.file_name,
                "mime_type": d.mime_type,
                "size_bytes": d.size_bytes,
                "checksum": d.checksum,
                "parse_status": d.parse_status,
                "parse_confidence": d.parse_confidence,
            }
            for d in documents
        ],
        "extracted": None
        if not extracted
        else {
            "document_id": extracted.document_id,
            "subject_name": extracted.subject_name,
            "subject_code": extracted.subject_code,
            "position": extracted.position,
            "current_unit_raw": extracted.current_unit_raw,
            "unit_code": (extracted.extracted_fields or {}).get("unit_code"),
            "former_units": extracted.former_units,
            "extraction_confidence": extracted.extraction_confidence,
            "relation_confidence": extracted.relation_confidence,
            "extracted_fields": extracted.extracted_fields or {},
        },
        "result": None
        if not r
        else {
            "id": r.id,
            "unit_id": r.unit_id,
            "organization_type": r.organization_type,
            "resolution_status": r.resolution_status,
            "subject_group": r.subject_group,
            "match_method": r.match_method,
            "score": r.resolution_score,
            "margin": r.candidate_margin,
            "decision_confidence": r.decision_confidence,
            "top_candidates": r.top_candidates,
            "evidence": r.evidence,
            "source_kind": r.source_kind,
            "registry_version": r.registry_version,
            "taxonomy_version": r.taxonomy_version,
            "parser_version": r.parser_version,
            "model_version": r.model_version,
            "threshold_version": r.threshold_version,
        },
        "eligibility": [
            {
                "policy_id": a.policy_id,
                "status": a.status,
                "reason": a.reason,
                "policy_version": a.policy_version,
                "source_kind": a.source_kind,
                "evidence": a.evidence,
            }
            for a in assessments
        ],
    }


def _split_group_key(result: VerificationResult | None) -> tuple[str | None, dict]:
    """Identify the multi-subject group a Case belongs to, if any.

    Both fan-out paths stamp ``evidence.split_source`` and key every sibling's
    ``idempotency_key`` as ``f"{group}:{block_index}"`` — the document id when the
    split happened in the document worker, the originating Case id when it happened
    on the synchronous text path. Block #0 on the text path keeps the caller's own
    Idempotency-Key, so it is recovered from ``source_case_id`` rather than the key.
    """
    split = ((result.evidence or {}).get("split_source") or {}) if result else {}
    if not isinstance(split, dict):
        return None, {}
    return (split.get("document_id") or split.get("source_case_id")), split


@router.get("/{case_id}/subjects")
def list_case_subjects(
    case_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_principal),
):
    """List every Case produced from the same multi-subject document.

    A single-subject Case answers with exactly itself (``subject_count == 1``), so
    the client can call this unconditionally and render a list only when the count
    is greater than one. Each sibling is an independent Case with its own result;
    this endpoint only enumerates them and never merges or re-decides anything.
    """
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    _authorize(db, c, p)

    r = db.scalar(select(VerificationResult).where(VerificationResult.case_id == case_id))
    group_id, split = _split_group_key(r)

    members: list[Case] = [c]
    if group_id:
        prefix = f"{group_id}:"
        for sibling in db.scalars(
            select(Case).where(
                Case.created_by == c.created_by,
                Case.idempotency_key.like(f"{prefix}%"),
            )
        ):
            # LIKE treats "_" as a wildcard and Case/Document ids contain one, so
            # the prefix is re-checked exactly rather than trusted from SQL.
            if (sibling.idempotency_key or "").startswith(prefix):
                members.append(sibling)
        source_id = split.get("source_case_id")
        if source_id:
            source = db.get(Case, source_id)
            if source is not None:
                members.append(source)

    unique: dict[str, Case] = {}
    for m in members:
        if m.id in unique:
            continue
        if m.id != c.id:
            # A sibling outside this caller's scope is omitted, not leaked.
            try:
                _authorize(db, m, p)
            except HTTPException:
                continue
        unique[m.id] = m

    member_ids = list(unique)
    extracted_by_case = {
        row.case_id: row
        for row in db.scalars(select(ExtractedRecord).where(ExtractedRecord.case_id.in_(member_ids)))
    }
    result_by_case = {
        row.case_id: row
        for row in db.scalars(select(VerificationResult).where(VerificationResult.case_id.in_(member_ids)))
    }

    def _block_index(case: Case) -> int:
        res = result_by_case.get(case.id)
        _, own_split = _split_group_key(res)
        idx = own_split.get("block_index")
        if isinstance(idx, int):
            return idx
        key = case.idempotency_key or ""
        if group_id and key.startswith(f"{group_id}:"):
            suffix = key.split(":")[-1]
            if suffix.isdigit():
                return int(suffix)
        return 0

    items = []
    for case in unique.values():
        ex = extracted_by_case.get(case.id)
        res = result_by_case.get(case.id)
        items.append(
            {
                "case_id": case.id,
                "block_index": _block_index(case),
                "subject_name": ex.subject_name if ex else None,
                "subject_code": ex.subject_code if ex else None,
                "position": ex.position if ex else None,
                "current_unit": (res.evidence or {}).get("canonical_name") if res else None,
                "current_unit_raw": ex.current_unit_raw if ex else None,
                "organization_type": res.organization_type if res else "UNKNOWN",
                "resolution_status": res.resolution_status if res else None,
                "subject_group": res.subject_group if res else None,
                "workflow_status": case.workflow_status,
                "created_at": case.created_at,
            }
        )
    items.sort(key=lambda row: (row["block_index"], row["case_id"]))

    return {
        "group_id": group_id,
        "document_id": split.get("document_id"),
        "block_count": split.get("block_count") or len(items),
        "subject_count": len(items),
        "items": items,
    }
