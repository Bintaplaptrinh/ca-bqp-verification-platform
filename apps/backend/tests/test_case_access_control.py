"""Case-level access control regressions.

Access follows permissions, not roles. An account without CASE_VIEW_ALL reaches
its own cases plus exactly the ones queued to its coverage group; CASE_VIEW_ALL
lifts that to every case. Both halves are pinned here because an administrator
toggles that permission per account, so either shape can be in force in
production.

These run against the authorisation helper the route depends on, so a change to
the rule shows up here rather than in production.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from principals import admin_principal, reviewer_principal, user_principal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.api.cases import _authorize
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal
from cabqp.shared.db import Base
from cabqp.shared.models import Case, ReviewCase, VerificationResult

#: A "cán bộ thẩm định" account whose CASE_VIEW_ALL has been switched off, so
#: only coverage scope decides what it can reach.
SCOPED_REVIEWER_PERMISSIONS = (perms.REVIEW_QUEUE, perms.REVIEW_DECIDE)


def scoped_reviewer(username, coverage_groups):
    return reviewer_principal(
        username,
        coverage_groups=coverage_groups,
        permissions=SCOPED_REVIEWER_PERMISSIONS,
    )


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _case(db: Session, owner: str = "alice") -> Case:
    case = Case(created_by=owner, input_type="TEXT", raw_text="x", input_payload={})
    db.add(case)
    db.flush()
    return case


def _queue_for_review(db: Session, case: Case, coverage_group: str | None) -> ReviewCase:
    result = VerificationResult(
        case_id=case.id, organization_type="UNKNOWN", resolution_status="AMBIGUOUS"
    )
    db.add(result)
    db.flush()
    review = ReviewCase(
        case_id=case.id,
        result_id=result.id,
        reason="AMBIGUOUS",
        coverage_group=coverage_group,
        payload={},
    )
    db.add(review)
    db.flush()
    return review


def _allowed(db: Session, case: Case, principal: Principal) -> bool:
    try:
        _authorize(db, case, principal)
        return True
    except HTTPException as exc:
        assert exc.status_code == 403
        return False


def test_owner_can_read_their_own_case(db):
    case = _case(db, owner="alice")
    assert _allowed(db, case, user_principal("alice"))


def test_another_user_cannot_read_someone_elses_case(db):
    case = _case(db, owner="alice")
    assert not _allowed(db, case, user_principal("bob"))


def test_admin_can_read_any_case(db):
    case = _case(db, owner="alice")
    assert _allowed(db, case, admin_principal())


def test_review_permissions_alone_are_not_a_licence_to_read_every_dossier(db):
    """Without CASE_VIEW_ALL, review permissions only reach queued work.

    A wildcard coverage scope widens which queue items are visible; it does not
    turn into a general read of dossiers nobody has queued for review.
    """
    case = _case(db, owner="alice")
    assert not _allowed(db, case, scoped_reviewer("rev", {"*"}))


def test_case_view_all_reads_a_case_that_is_not_queued_for_review(db):
    """The delivered "cán bộ thẩm định" preset includes CASE_VIEW_ALL."""
    case = _case(db, owner="alice")
    assert _allowed(db, case, reviewer_principal("rev"))


def test_reviewer_can_read_a_case_queued_to_their_coverage_group(db):
    case = _case(db, owner="alice")
    _queue_for_review(db, case, "BCA_NORTH")
    assert _allowed(db, case, scoped_reviewer("rev", {"BCA_NORTH"}))


def test_reviewer_with_wildcard_scope_can_read_queued_cases(db):
    case = _case(db, owner="alice")
    _queue_for_review(db, case, "BCA_NORTH")
    assert _allowed(db, case, scoped_reviewer("rev", {"*"}))


def test_reviewer_cannot_read_a_case_queued_to_another_coverage_group(db):
    case = _case(db, owner="alice")
    _queue_for_review(db, case, "BCA_NORTH")
    assert not _allowed(db, case, scoped_reviewer("rev", {"BQP_SOUTH"}))


def test_reviewer_without_any_coverage_group_reads_nothing(db):
    case = _case(db, owner="alice")
    _queue_for_review(db, case, "BCA_NORTH")
    assert not _allowed(db, case, scoped_reviewer("rev", set()))


def test_review_assigned_to_another_reviewer_is_not_readable(db):
    """An assigned review belongs to its assignee, not to everyone in the group."""
    case = _case(db, owner="alice")
    review = _queue_for_review(db, case, "BCA_NORTH")
    review.assigned_to = "reviewer-one"
    db.flush()

    assert not _allowed(db, case, scoped_reviewer("reviewer-two", {"BCA_NORTH"}))
    assert _allowed(db, case, scoped_reviewer("reviewer-one", {"BCA_NORTH"}))
