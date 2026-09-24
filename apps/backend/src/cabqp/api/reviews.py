from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.review.service import decide_review
from cabqp.shared.db import get_db
from cabqp.shared.enums import ReviewStatus
from cabqp.shared.models import Case, ExtractedRecord, ReviewCase, VerificationResult
from cabqp.shared.schemas import ReviewAssign, ReviewDecision

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _case_code(case: Case | None, case_id: str) -> str:
    """Return the stable, operator-facing code used by the review queue."""
    year = case.created_at.year if case and case.created_at else datetime.utcnow().year
    token = re.sub(r"^case_", "", str(case_id), flags=re.IGNORECASE)[:8].upper()
    return f"HS-{year}-{token}"


def _case_search_fragment(value: str) -> str:
    """Accept either an internal Case id or the displayed ``HS-YEAR-TOKEN`` code."""
    cleaned = value.strip()
    displayed = re.match(r"^#?HS-\d{4}-(.+)$", cleaned, flags=re.IGNORECASE)
    return displayed.group(1).strip() if displayed else cleaned


def _contains_pattern(value: str) -> str:
    """Build a literal SQL LIKE contains pattern; ``%`` and ``_`` are user text."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _scope_query(q, p: Principal):
    """Narrow the queue to what this account is allowed to see.

    Coverage groups only ever narrow. An account holding CASE_VIEW_ALL with no
    coverage group assigned is trusted across the whole queue, which is the
    default shape of the "cán bộ thẩm định" permission set; assigning coverage
    groups to that account is how an administrator restricts it to a slice.
    """
    if p.is_admin or "*" in p.coverage_groups:
        return q
    if not p.coverage_groups:
        if perms.CASE_VIEW_ALL in p.permissions:
            return q
        return q.where(False)
    return q.where(
        ReviewCase.coverage_group.in_(sorted(p.coverage_groups)),
        or_(ReviewCase.assigned_to.is_(None), ReviewCase.assigned_to == p.username),
    )


@router.get("")
def queue(
    status: ReviewStatus = ReviewStatus.OPEN,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.REVIEW_QUEUE, perms.REVIEW_DECIDE)),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")

    q = select(ReviewCase).where(ReviewCase.status == status.value)
    q = _scope_query(q, p)
    if date_from:
        q = q.where(ReviewCase.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.where(ReviewCase.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if search and search.strip():
        term = search.strip()
        case_fragment = _case_search_fragment(term)
        q = q.where(
            or_(
                ReviewCase.case_id.ilike(_contains_pattern(case_fragment), escape="\\"),
                exists(
                    select(ExtractedRecord.id).where(
                        ExtractedRecord.case_id == ReviewCase.case_id,
                        ExtractedRecord.subject_name.ilike(_contains_pattern(term), escape="\\"),
                    )
                ),
                ReviewCase.payload["subject"]["name"].as_string().ilike(
                    _contains_pattern(term), escape="\\"
                ),
            )
        )
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(ReviewCase.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    case_ids = [row.case_id for row in rows]
    cases = {
        row.id: row
        for row in db.scalars(select(Case).where(Case.id.in_(case_ids)))
    } if case_ids else {}
    extracted = {
        row.case_id: row
        for row in db.scalars(select(ExtractedRecord).where(ExtractedRecord.case_id.in_(case_ids)))
    } if case_ids else {}
    results = {
        row.case_id: row
        for row in db.scalars(select(VerificationResult).where(VerificationResult.case_id.in_(case_ids)))
    } if case_ids else {}

    def item(x: ReviewCase) -> dict:
        case = cases.get(x.case_id)
        record = extracted.get(x.case_id)
        result = results.get(x.case_id)
        person = ((result.evidence or {}).get("person_resolution") or {}) if result else {}
        birth_year = (
            person.get("birth_year")
            or ((record.extracted_fields or {}).get("birth_year") if record else None)
        )
        return {
            "id": x.id,
            "case_id": x.case_id,
            "case_code": _case_code(case, x.case_id),
            "reason": x.reason,
            "status": x.status,
            "coverage_group": x.coverage_group,
            "assigned_to": x.assigned_to,
            "payload": x.payload,
            # Current projections are intentionally separate from payload, which is
            # the immutable snapshot captured when the Case entered the queue.
            "subject": {
                "name": person.get("full_name") or (record.subject_name if record else None),
                "subject_code": record.subject_code if record else None,
                "birth_year": birth_year,
                "position": record.position if record else None,
            },
            "current_result": {
                "workflow_status": case.workflow_status if case else None,
                "resolution_status": result.resolution_status if result else None,
                "organization_type": result.organization_type if result else "UNKNOWN",
                "current_unit": (result.evidence or {}).get("canonical_name") if result else None,
            },
            "case_created_at": case.created_at if case else None,
            "version": x.version_no,
            "created_at": x.created_at,
            "reviewed_by": x.reviewed_by,
            "reviewed_at": x.reviewed_at,
            "decision_note": x.decision_note,
        }

    return {
        "items": [item(x) for x in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{review_id}/decision")
def decide(
    review_id: str,
    body: ReviewDecision,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.REVIEW_DECIDE)),
):
    try:
        review, case = decide_review(db, review_id, body, p)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "review_id": review.id,
        "status": review.status,
        "case_status": case.workflow_status,
        "version": review.version_no,
    }


@router.post("/{review_id}/assign")
def assign_review(
    review_id: str,
    body: ReviewAssign,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.REVIEW_DECIDE)),
):
    review = db.scalar(select(ReviewCase).where(ReviewCase.id == review_id).with_for_update())
    if not review:
        raise HTTPException(404, "Review not found")
    if review.status != "OPEN":
        raise HTTPException(409, "Only OPEN reviews can be assigned")
    if review.version_no != body.expected_version:
        raise HTTPException(409, "Review changed; reload before assigning")

    is_admin = "ADMIN" in p.roles
    if not is_admin:
        # Reviewers may only claim/release work that is visible in their own scope.
        # They cannot re-route coverage or assign a review to another user.
        if not p.can_review_scope(review.coverage_group):
            raise HTTPException(403, "Review is outside your coverage scope")
        requested_assignee = body.assigned_to
        if requested_assignee not in {None, p.username}:
            raise HTTPException(403, "Reviewers may only assign reviews to themselves")
        if review.assigned_to not in {None, p.username}:
            raise HTTPException(409, "Review is already assigned to another reviewer")
        if body.coverage_group is not None and body.coverage_group != review.coverage_group:
            raise HTTPException(403, "Reviewers cannot change coverage group")
    review.assigned_to = body.assigned_to
    if is_admin and body.coverage_group is not None:
        review.coverage_group = body.coverage_group
    review.version_no += 1
    audit(
        db,
        actor=p.username,
        role="ADMIN" if is_admin else "REVIEWER",
        action="REVIEW_ASSIGN",
        entity_type="REVIEW",
        entity_id=review.id,
        metadata={"assigned_to": review.assigned_to, "coverage_group": review.coverage_group},
    )
    db.commit()
    return {
        "review_id": review.id,
        "assigned_to": review.assigned_to,
        "coverage_group": review.coverage_group,
        "version": review.version_no,
    }
