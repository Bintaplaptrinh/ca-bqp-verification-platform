from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth.dependencies import Principal
from cabqp.modules.decisioning.policy import PolicyEngine
from cabqp.modules.subject_group.service import KNOWN_GROUPS
from cabqp.shared.models import (
    Case,
    ExtractedRecord,
    RegistryCandidate,
    ReviewCase,
    Source,
    Unit,
    VerificationResult,
    utcnow,
)
from cabqp.shared.normalization import normalize_text
from cabqp.shared.schemas import ReviewDecision


def _authorize_review(review: ReviewCase, principal: Principal) -> None:
    if "ADMIN" in principal.roles:
        return
    if review.assigned_to and review.assigned_to != principal.username:
        raise HTTPException(403, "Review is assigned to another reviewer")
    if not principal.can_review_scope(review.coverage_group):
        raise HTTPException(403, "Review is outside your authorized coverage group")


def decide_review(db: Session, review_id: str, body: ReviewDecision, principal: Principal):
    review = db.scalar(select(ReviewCase).where(ReviewCase.id == review_id).with_for_update())
    if not review:
        raise HTTPException(404, "Review not found")
    _authorize_review(review, principal)
    if review.status != "OPEN":
        raise HTTPException(409, "Review is no longer open")
    if review.version_no != body.expected_version:
        raise HTTPException(409, "Review was changed by another reviewer; reload before deciding")

    case = db.get(Case, review.case_id)
    result = db.get(VerificationResult, review.result_id) if review.result_id else None
    if not case:
        raise HTTPException(409, "Review references a missing Case")
    if not result and body.decision != "DISMISS":
        raise HTTPException(409, "Review has no verification result to update")

    decision = body.decision
    if decision == "CONFIRM":
        # Subject-group or parse reviews may already have a trusted unit. In that case
        # a reviewer can confirm/correct the non-unit facts without re-entering unit_id.
        target_unit_id = body.unit_id or result.unit_id
        if not target_unit_id:
            raise HTTPException(422, "unit_id is required for CONFIRM when the Case has no matched unit")
        unit = db.get(Unit, target_unit_id)
        if not unit or unit.qa_status != "APPROVED" or not unit.active:
            raise HTTPException(400, "Unit must be active and APPROVED")
        if "ADMIN" not in principal.roles and not principal.can_review_scope(unit.coverage_group):
            raise HTTPException(403, "Target unit is outside your authorized coverage group")
        result.unit_id = unit.id
        result.organization_type = unit.organization_type
        if unit.source_id:
            source = db.get(Source, unit.source_id)
            result.source_kind = source.source_kind if source else "PROVIDED"
        else:
            result.source_kind = "PROVIDED"
        result.resolution_status = "MATCHED"
        result.match_method = "HUMAN_REVIEW"
        result.decision_confidence = 1.0
        result.evidence = {
            **(result.evidence or {}),
            "reviewer": principal.username,
            "review_id": review.id,
        }
        review.coverage_group = unit.coverage_group or review.coverage_group
    elif decision == "UNKNOWN":
        # UNKNOWN is specifically a unit-resolution outcome: authoritative evidence is
        # insufficient to identify CURRENT_WORK_UNIT, so clear the resolved unit.
        result.unit_id = None
        result.organization_type = "UNKNOWN"
        result.source_kind = "PROVIDED"
        result.resolution_status = "NOT_FOUND"
        result.match_method = "HUMAN_REVIEW"
        result.decision_confidence = 1.0
        result.evidence = {
            **(result.evidence or {}),
            "reviewer": principal.username,
            "review_id": review.id,
            "review_outcome": decision,
        }
    elif decision == "INSUFFICIENT":
        # INSUFFICIENT means business/policy facts are missing. It must not erase an
        # already verified unit; unit resolution and policy sufficiency are separate axes.
        result.evidence = {
            **(result.evidence or {}),
            "reviewer": principal.username,
            "review_id": review.id,
            "review_outcome": decision,
        }
    elif decision == "DISMISS":
        review.status = "DISMISSED"
        review.reviewed_by = principal.username
        review.reviewed_at = utcnow()
        review.decision_note = body.note
        review.version_no += 1
        # Manual dismiss is an operational closure, not a positive business decision.
        # Fail closed so a Case can never remain NEED_REVIEW with no open review item.
        case.workflow_status = "FAILED"
        audit(
            db,
            actor=principal.username,
            role="REVIEWER" if "REVIEWER" in principal.roles else "ADMIN",
            action="REVIEW_DISMISS",
            entity_type="REVIEW",
            entity_id=review.id,
            metadata={"expected_version": body.expected_version},
        )
        return review, case
    else:  # defensive; Pydantic already validates
        raise HTTPException(422, "Unsupported review decision")

    if body.subject_group:
        reviewed_group = body.subject_group.strip().upper()
        if reviewed_group not in KNOWN_GROUPS:
            raise HTTPException(422, "Unsupported subject_group")
        result.subject_group = reviewed_group
        result.evidence = {
            **(result.evidence or {}),
            "subject_group_reviewed_by": principal.username,
        }

    rec = db.scalar(select(ExtractedRecord).where(ExtractedRecord.case_id == case.id).limit(1))
    if body.corrected_current_unit and rec:
        rec.current_unit_raw = body.corrected_current_unit
        rec.extracted_fields = {
            **(rec.extracted_fields or {}),
            "review_corrected_current_unit": body.corrected_current_unit,
        }

    if body.propose_alias:
        if decision != "CONFIRM" or not body.corrected_current_unit or not result.unit_id:
            raise HTTPException(
                422,
                "CONFIRM, corrected_current_unit and a resolved unit are required when propose_alias=true",
            )
        db.add(
            RegistryCandidate(
                raw_name=body.corrected_current_unit,
                proposed_name=body.corrected_current_unit,
                normalized_key=normalize_text(body.corrected_current_unit),
                organization_type=result.organization_type,
                status="PENDING_QA",
                evidence={
                    "source": "REVIEW_FEEDBACK",
                    "case_id": case.id,
                    "suggested_unit_id": result.unit_id,
                    "review_id": review.id,
                },
            )
        )

    structured = case.input_payload or {}
    business_fields = structured.get("business_fields") or {}
    raw_as_of = structured.get("as_of_date")
    as_of = case.created_at.date() if case.created_at else date.today()
    if isinstance(raw_as_of, date):
        as_of = raw_as_of
    elif isinstance(raw_as_of, str) and raw_as_of:
        try:
            as_of = date.fromisoformat(raw_as_of)
        except ValueError:
            as_of = case.created_at.date() if case.created_at else date.today()
    facts = {
        **business_fields,
        "organization_type": result.organization_type,
        "subject_group": result.subject_group,
        "position": rec.position if rec else structured.get("position"),
        "subject_code": rec.subject_code if rec else structured.get("subject_code"),
    }
    assessments = PolicyEngine(db).evaluate(
        result_id=result.id,
        subject_group=result.subject_group,
        facts=facts,
        as_of=as_of,
        replace_existing=True,
    )
    result.evidence = {
        **(result.evidence or {}),
        "policy_summary": [
            {
                "policy_id": a.policy_id,
                "status": a.status,
                "policy_version": a.policy_version,
                "reason": a.reason,
            }
            for a in assessments
        ],
        "policy_as_of_date": as_of.isoformat(),
    }

    review.status = "RESOLVED"
    review.reviewed_by = principal.username
    review.reviewed_at = utcnow()
    review.decision_note = body.note
    review.version_no += 1
    case.workflow_status = "COMPLETED"

    audit(
        db,
        actor=principal.username,
        role="REVIEWER" if "REVIEWER" in principal.roles else "ADMIN",
        action="REVIEW_DECISION",
        entity_type="REVIEW",
        entity_id=review.id,
        metadata={
            "decision": decision,
            "unit_id": result.unit_id,
            "expected_version": body.expected_version,
            "coverage_group": review.coverage_group,
        },
    )
    return review, case
