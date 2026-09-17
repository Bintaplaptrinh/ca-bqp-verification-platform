from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.review.service import decide_review
from cabqp.shared.db import get_db
from cabqp.shared.enums import ReviewStatus
from cabqp.shared.models import ReviewCase
from cabqp.shared.schemas import ReviewAssign, ReviewDecision

router = APIRouter(prefix="/reviews", tags=["reviews"])


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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.REVIEW_QUEUE, perms.REVIEW_DECIDE)),
):
    q = select(ReviewCase).where(ReviewCase.status == status.value)
    q = _scope_query(q, p)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(ReviewCase.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": x.id,
                "case_id": x.case_id,
                "reason": x.reason,
                "status": x.status,
                "coverage_group": x.coverage_group,
                "assigned_to": x.assigned_to,
                "payload": x.payload,
                "version": x.version_no,
                "created_at": x.created_at,
                # The decision trail. A RESOLVED/DISMISSED row is otherwise
                # indistinguishable from any other in the queue listing.
                "reviewed_by": x.reviewed_by,
                "reviewed_at": x.reviewed_at,
                "decision_note": x.decision_note,
            }
            for x in rows
        ],
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
