from __future__ import annotations

import logging
from datetime import timedelta

from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import func, select

from cabqp.modules.audit.service import audit
from cabqp.modules.cases.service import process_case
from cabqp.modules.document_intelligence.limits import DocumentLimitError
from cabqp.modules.document_intelligence.parsers import parse_document
from cabqp.modules.document_intelligence.storage import ObjectStorage
from cabqp.modules.document_intelligence.subject_split import detect_subject_blocks
from cabqp.shared.db import SessionLocal
from cabqp.shared.metrics import CASE_TRANSITIONS, DOCUMENT_PARSE, OUTBOX_EVENTS
from cabqp.shared.models import (
    BulkIngestJob,
    BulkIngestRow,
    Case,
    Document,
    OutboxEvent,
    ReviewCase,
    uid,
    utcnow,
)
from cabqp.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _ensure_review_case(db, case: Case, *, reason: str, payload: dict, result_id: str | None = None) -> ReviewCase:
    review = db.scalar(
        select(ReviewCase)
        .where(ReviewCase.case_id == case.id, ReviewCase.status == "OPEN")
        .limit(1)
    )
    if review is None:
        review = ReviewCase(
            case_id=case.id,
            result_id=result_id,
            reason=reason,
            payload=payload,
            coverage_group="UNASSIGNED",
        )
        db.add(review)
    else:
        review.result_id = result_id or review.result_id
        review.reason = reason
        review.payload = payload
        review.version_no += 1
    return review


def _mark_failed(case_id: str, document_id: str, exc: Exception) -> None:
    fail_db = SessionLocal()
    try:
        case = fail_db.get(Case, case_id)
        document = fail_db.get(Document, document_id)
        if case:
            case.workflow_status = "FAILED"
            CASE_TRANSITIONS.labels(status="FAILED").inc()
            audit(
                fail_db,
                actor="system:document-worker",
                role="SYSTEM",
                action="DOCUMENT_PROCESSING_FAILED",
                entity_type="CASE",
                entity_id=case_id,
                metadata={"document_id": document_id, "error_type": type(exc).__name__},
            )
        if document:
            document.parse_status = "FAILED"
        fail_db.commit()
    except Exception:
        fail_db.rollback()
        logger.exception(
            "failed_to_persist_terminal_document_failure",
            extra={"event": {"case_id": case_id, "document_id": document_id}},
        )
    finally:
        fail_db.close()


def _dead_letter(case_id: str, document_id: str, key: str, exc: Exception) -> None:
    try:
        # No worker consumes document_dlq by default. The message remains for operator inspection/replay.
        celery_app.send_task(
            "cabqp.document.dead_letter",
            args=[case_id, document_id, key, type(exc).__name__],
            queue="document_dlq",
        )
    except Exception:
        logger.exception(
            "dead_letter_publish_failed",
            extra={"event": {"case_id": case_id, "document_id": document_id}},
        )


def _dispatch_event(db, event: OutboxEvent) -> bool:
    """Deliver one outbox row, and mark it SENT only once delivery is durable.

    Under Celery, publishing to the broker *is* the durable handoff, so the row is
    marked SENT as soon as ``apply_async`` returns. The inline profile has no broker:
    handing the task to an in-process thread pool is not durable at all, and marking
    the row SENT at that point silently lost the work whenever the process died
    between ``submit()`` and the task running — the Case then sat at RECEIVED forever
    with nothing left to re-pick it. So the inline branch runs the task here and marks
    the row afterwards; a crash in between leaves it PENDING, which is exactly what
    the sweeper re-dispatches.
    """
    if event.status == "SENT":
        return True
    event.attempts += 1
    try:
        if event.event_type == "DOCUMENT_PROCESS_REQUESTED":
            payload = event.payload or {}
            from cabqp.workers.local_queue import enqueue, inline_enabled, run_task_now

            args = (payload["case_id"], payload["document_id"], payload["storage_key"])
            if inline_enabled():
                # Commit the attempt first so this session stops holding the outbox row
                # while the document is parsed: process_document opens its own session
                # and must not wait on a lock held for the length of an OCR run.
                db.commit()
                try:
                    run_task_now(process_document, *args)
                except Exception:
                    # The task exhausted its own retry budget and already ran its
                    # terminal branch (Case FAILED + dead letter). Delivery did happen,
                    # so the row is still SENT; re-queueing here would loop the sweeper
                    # forever on a document that has permanently failed.
                    logger.exception(
                        "inline_document_task_terminal_failure",
                        extra={"event": {"outbox_id": event.id, "case_id": payload.get("case_id")}},
                    )
            else:
                enqueue(process_document, *args)
        else:
            raise ValueError(f"Unsupported outbox event type: {event.event_type}")
        event.status = "SENT"
        OUTBOX_EVENTS.labels(status="SENT", event_type=event.event_type).inc()
        event.sent_at = utcnow()
        event.last_error = None
        return True
    except Exception as exc:
        event.status = "PENDING"
        OUTBOX_EVENTS.labels(status="RETRY", event_type=event.event_type).inc()
        event.available_at = utcnow() + timedelta(seconds=min(300, 2 ** min(event.attempts, 8)))
        event.last_error = type(exc).__name__
        logger.exception(
            "outbox_dispatch_failed",
            extra={"event": {"outbox_id": event.id, "attempts": event.attempts, "error_type": type(exc).__name__}},
        )
        return False


@celery_app.task(name="cabqp.workers.tasks.dispatch_outbox_event", bind=True, max_retries=5, default_retry_delay=10)
def dispatch_outbox_event(self, outbox_id: str):
    db = SessionLocal()
    try:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.id == outbox_id).with_for_update())
        if not event:
            return {"status": "missing"}
        ok = _dispatch_event(db, event)
        db.commit()
        if not ok:
            raise RuntimeError("outbox dispatch failed")
        return {"status": "sent"}
    except Exception as exc:
        db.rollback()
        try:
            # self.retry carries `exc` itself; chaining would duplicate it.
            raise self.retry(exc=exc) from None
        except MaxRetriesExceededError:
            fail_db = SessionLocal()
            try:
                event = fail_db.get(OutboxEvent, outbox_id)
                if event:
                    event.status = "FAILED"
                    event.last_error = type(exc).__name__
                    fail_db.commit()
            finally:
                fail_db.close()
            raise
    finally:
        db.close()


@celery_app.task(name="cabqp.workers.tasks.dispatch_pending_outbox")
def dispatch_pending_outbox(limit: int = 100):
    db = SessionLocal()
    sent = 0
    try:
        query = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "PENDING",
                OutboxEvent.available_at <= utcnow(),
            )
            .order_by(OutboxEvent.created_at)
            .limit(max(1, min(limit, 500)))
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        events = list(db.scalars(query))
        for event in events:
            if _dispatch_event(db, event):
                sent += 1
        db.commit()
        return {"checked": len(events), "sent": sent}
    except Exception:
        db.rollback()
        logger.exception("outbox_sweep_failed")
        raise
    finally:
        db.close()


@celery_app.task(name="cabqp.workers.tasks.process_document", bind=True, max_retries=3, default_retry_delay=10)
def process_document(self, case_id: str, document_id: str, key: str):
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        document = db.get(Document, document_id)
        if not case or not document:
            logger.warning(
                "document_task_target_missing",
                extra={"event": {"case_id": case_id, "document_id": document_id}},
            )
            return {"status": "missing"}

        if document.parse_status == "PARSED" and case.workflow_status in {"COMPLETED", "NEED_REVIEW"}:
            return {"status": "idempotent_replay"}

        case.workflow_status = "PROCESSING"
        db.flush()
        content = ObjectStorage().get(key)
        try:
            parsed = parse_document(document.file_name, content)
        except SoftTimeLimitExceeded:
            # A time budget violation is a permanent per-document safety outcome, not a
            # transient OCR error. Retrying it three times only multiplies CPU cost.
            document.parse_confidence = 0.0
            document.parse_status = "FAILED"
            case.workflow_status = "NEED_REVIEW"
            payload = {"document_id": document.id, "limit_code": "DOCUMENT_TIME_BUDGET_EXCEEDED"}
            _ensure_review_case(db, case, reason="DOCUMENT_TIME_BUDGET_EXCEEDED", payload=payload)
            audit(
                db, actor="system:document-worker", role="SYSTEM", action="DOCUMENT_RESOURCE_LIMIT",
                entity_type="CASE", entity_id=case.id, metadata=payload,
            )
            db.commit()
            return {"status": "review", "reason": "DOCUMENT_TIME_BUDGET_EXCEEDED"}
        except DocumentLimitError as exc:
            document.parse_confidence = 0.0
            document.parse_status = "FAILED"
            case.workflow_status = "NEED_REVIEW"
            payload = {"document_id": document.id, "limit_code": exc.code, "details": exc.details}
            _ensure_review_case(db, case, reason=exc.code, payload=payload)
            audit(
                db, actor="system:document-worker", role="SYSTEM", action="DOCUMENT_RESOURCE_LIMIT",
                entity_type="CASE", entity_id=case.id, metadata=payload,
            )
            db.commit()
            return {"status": "review", "reason": exc.code}
        text, conf, method = parsed.text, parsed.confidence, parsed.method
        document.parse_confidence = conf
        document.parse_status = "PARSED" if text.strip() else "FAILED"
        DOCUMENT_PARSE.labels(status=document.parse_status, method=method).inc()

        from cabqp.modules.bulk.service import tables_have_record_list
        table_record_list=bool(parsed.tables) and tables_have_record_list(parsed.tables)
        if parsed.input_kind == "TABULAR_LIST" or table_record_list:
            case.workflow_status = "NEED_REVIEW"
            payload={
                "document_id":document.id,
                "routing":parsed.evidence.get("routing"),
                "table_record_list":table_record_list,
                "table_count":len(parsed.tables or []),
                "scan_table_pages":parsed.evidence.get("scan_table_pages") or [],
            }
            _ensure_review_case(db, case, reason="BULK_ENDPOINT_REQUIRED", payload=payload)
            audit(
                db, actor="system:document-worker", role="SYSTEM", action="BULK_LIST_WRONG_ENDPOINT",
                entity_type="CASE", entity_id=case.id, metadata=payload,
            )
            db.commit()
            return {"status":"review","reason":"BULK_ENDPOINT_REQUIRED"}

        if not text.strip():
            case.workflow_status = "NEED_REVIEW"
            _ensure_review_case(
                db, case, reason="DOCUMENT_PARSE_EMPTY",
                payload={"document_id":document.id,"method":method,"confidence":conf,"quality":parsed.quality},
            )
            audit(
                db,
                actor="system:document-worker",
                role="SYSTEM",
                action="DOCUMENT_PARSE_EMPTY",
                entity_type="CASE",
                entity_id=case.id,
                metadata={"document_id": document.id, "method": method, "confidence": conf, "quality": parsed.quality},
            )
            db.commit()
            return {"status": "review", "reason": "OCR_EMPTY"}

        base_payload = dict(case.input_payload or {})
        base_payload["_parse_method"] = method
        base_payload["_parse_confidence"] = conf
        base_payload["_parse_quality"] = parsed.quality
        base_payload["_parse_evidence"] = parsed.evidence
        if parsed.ocr_lines:
            base_payload["_ocr_lines"] = [x.to_dict() for x in parsed.ocr_lines]
        if parsed.tables:
            base_payload["_parsed_tables"] = parsed.tables

        blocks = detect_subject_blocks(text, method)

        if len(blocks) <= 1 or blocks[0].ambiguous:
            # Single subject (unchanged path), or an OCR/hybrid document that looks
            # like it has multiple subjects but isn't safe to auto-split (v1 scope) —
            # either way this stays exactly one Case. An ambiguous block still carries
            # its reason into _batch_warnings so process_case abstains to NEED_REVIEW
            # instead of silently guessing.
            case.raw_text = blocks[0].text if blocks else text
            structured = dict(base_payload)
            if blocks and blocks[0].ambiguous:
                structured["_batch_warnings"] = [
                    {"code": blocks[0].ambiguous_reason, "column": None, "message_vi": ""}
                ]
            process_case(db, case, structured)
        else:
            # Multiple subjects detected in one free-text document: fan out into one
            # independent Case per person, mirroring how bulk/batch ingestion creates
            # one Case per spreadsheet row (see process_bulk_row). The Case created
            # synchronously at upload time becomes block #0; siblings are created here,
            # each keyed by a stable idempotency key so retries never duplicate Cases.
            for block in blocks:
                idem = f"{document.id}:{block.index}"
                if block.index == 0:
                    case_for_block = case
                    # Block #0 keeps the caller's own Idempotency-Key. Overwriting it
                    # with the group key made a client retry carrying the original key
                    # miss the existing Case and upload a duplicate. Siblings are still
                    # keyed by the group so the fan-out itself stays idempotent, and
                    # `_split_source.source_case_id` below is how block #0 is recovered
                    # as a group member — the same mechanism the text path already uses.
                    document_for_block = document
                else:
                    case_for_block = db.scalar(
                        select(Case).where(Case.created_by == case.created_by, Case.idempotency_key == idem)
                    )
                    if case_for_block is None:
                        case_for_block = Case(
                            created_by=case.created_by,
                            input_type=case.input_type,
                            idempotency_key=idem,
                        )
                        db.add(case_for_block)
                        db.flush()
                        audit(
                            db, actor="system:document-worker", role="SYSTEM", action="SPLIT_CASE_CREATE",
                            entity_type="CASE", entity_id=case_for_block.id,
                            metadata={"document_id": document.id, "block_index": block.index, "block_count": len(blocks)},
                        )
                    document_for_block = db.scalar(
                        select(Document).where(Document.case_id == case_for_block.id).limit(1)
                    )
                    if document_for_block is None:
                        document_for_block = Document(
                            id=uid("doc"),
                            case_id=case_for_block.id,
                            file_name=f"{document.file_name} ({block.index + 1}/{len(blocks)})",
                            mime_type=document.mime_type,
                            size_bytes=document.size_bytes,
                            storage_uri=document.storage_uri,
                            checksum=document.checksum,
                            parse_status="PARSED",
                            parse_confidence=conf,
                        )
                        db.add(document_for_block)
                        db.flush()

                case_for_block.raw_text = block.text
                structured = dict(base_payload)
                structured["_split_source"] = {
                    "document_id": document.id,
                    "source_case_id": case.id,
                    "block_index": block.index,
                    "block_count": len(blocks),
                }
                if block.ambiguous:
                    structured["_batch_warnings"] = [
                        {"code": block.ambiguous_reason, "column": None, "message_vi": ""}
                    ]
                process_case(db, case_for_block, structured)
                document_for_block.parse_status = "PARSED"
                document_for_block.parse_confidence = conf

        audit(
            db,
            actor="system:document-worker",
            role="SYSTEM",
            action="DOCUMENT_PROCESSED",
            entity_type="CASE",
            entity_id=case.id,
            metadata={"document_id": document.id, "method": method, "confidence": conf, "quality": parsed.quality},
        )
        db.commit()
        return {"status": "ok", "method": method, "confidence": conf, "subject_count": len(blocks)}
    except Exception as exc:
        db.rollback()
        attempt = int(getattr(self.request, "retries", 0))
        max_retries = int(self.max_retries or 0)
        logger.exception(
            "document_processing_attempt_failed",
            extra={
                "event": {
                    "case_id": case_id,
                    "document_id": document_id,
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "error_type": type(exc).__name__,
                }
            },
        )
        if attempt >= max_retries:
            _mark_failed(case_id, document_id, exc)
            _dead_letter(case_id, document_id, key, exc)
            raise
        # self.retry carries `exc` itself; chaining would duplicate it.
        raise self.retry(exc=exc) from None
    finally:
        db.close()


@celery_app.task(name="cabqp.workers.tasks.process_bulk_row", bind=True, max_retries=3, default_retry_delay=10)
def process_bulk_row_task(self, job_id: str, row_id: str):
    from cabqp.modules.bulk.service import process_bulk_row, refresh_job_counts
    db=SessionLocal()
    try:
        job=db.get(BulkIngestJob,job_id)
        row=db.scalar(select(BulkIngestRow).where(BulkIngestRow.id==row_id).with_for_update())
        if not job or not row: return {"status":"missing"}
        process_bulk_row(db,row,job); refresh_job_counts(db,job); db.commit()
        return {"status":row.status,"case_id":row.case_id}
    except Exception as exc:
        db.rollback()
        attempt=int(getattr(self.request,"retries",0))
        if attempt >= int(self.max_retries or 0):
            fail=SessionLocal()
            try:
                row=fail.get(BulkIngestRow,row_id); job=fail.get(BulkIngestJob,job_id)
                if row:
                    row.status="FAILED"; row.error_code="PROCESSING_ERROR"; row.error_detail=type(exc).__name__
                if job:
                    refresh_job_counts(fail,job)
                fail.commit()
            finally: fail.close()
            try: celery_app.send_task("cabqp.bulk.dead_letter",args=[job_id,row_id,type(exc).__name__],queue="batch_dlq")
            except Exception: logger.exception("batch_dead_letter_publish_failed")
            raise
        # self.retry carries `exc` itself; chaining would duplicate it.
        raise self.retry(exc=exc) from None
    finally:
        db.close()


@celery_app.task(name="cabqp.workers.tasks.process_bulk_job")
def process_bulk_job(job_id: str):
    db=SessionLocal()
    try:
        job=db.scalar(select(BulkIngestJob).where(BulkIngestJob.id==job_id).with_for_update())
        if not job: return {"status":"missing"}
        if job.status in {"COMPLETED","COMPLETED_WITH_ERRORS","FAILED"}:
            return {"status":job.status,"queued":0}
        rows=list(db.scalars(select(BulkIngestRow).where(BulkIngestRow.job_id==job.id,BulkIngestRow.status=="PENDING").order_by(BulkIngestRow.row_index)))
        if not rows:
            from cabqp.modules.bulk.service import refresh_job_counts
            refresh_job_counts(db,job); db.commit(); return {"status":job.status,"queued":0}
        job.status="PROCESSING"; db.commit()
        queued=0
        for row in rows:
            try:
                from cabqp.workers.local_queue import enqueue
                enqueue(process_bulk_row_task, job.id, row.id)
                queued+=1
            except Exception:
                logger.exception("bulk_row_dispatch_failed", extra={"event":{"job_id":job.id,"row_id":row.id}})
        return {"status":"PROCESSING","queued":queued,"pending":len(rows)-queued}
    finally:
        db.close()


@celery_app.task(name="cabqp.workers.tasks.reconcile_bulk_jobs")
def reconcile_bulk_jobs(limit: int = 100):
    """DB-derived recovery/finalizer. Re-dispatching PENDING rows is safe because row tasks lock the DB row."""
    from cabqp.modules.bulk.service import refresh_job_counts
    db=SessionLocal()
    try:
        jobs=list(db.scalars(select(BulkIngestJob).where(BulkIngestJob.status.in_(["QUEUED","PROCESSING"])).limit(max(1,min(limit,500)))))
        dispatch=[]
        for job in jobs:
            pending=int(db.scalar(select(func.count()).select_from(BulkIngestRow).where(BulkIngestRow.job_id==job.id,BulkIngestRow.status=="PENDING")) or 0)
            if pending:
                dispatch.append(job.id)
                job.status="QUEUED"
            else:
                refresh_job_counts(db,job)
        db.commit()
        dispatched=0
        for job_id in dispatch:
            try:
                from cabqp.workers.local_queue import enqueue
                enqueue(process_bulk_job, job_id)
                dispatched+=1
            except Exception:
                logger.exception("bulk_job_reconcile_dispatch_failed", extra={"event":{"job_id":job_id}})
        return {"checked":len(jobs),"redispatched":dispatched}
    except Exception:
        db.rollback(); logger.exception("bulk_reconcile_failed"); raise
    finally:
        db.close()

