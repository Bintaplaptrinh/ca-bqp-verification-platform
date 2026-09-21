"""The history summary counts the whole queue, not the page it fetched.

The web client used to derive "Tổng lượt tra cứu" and the three status tiles by
counting the rows `GET /cases` returned. That request asks for `page_size=200`,
so every figure froze at 200 once the queue grew past it, which reads as a
hardcoded number. The counts now come from the server, computed over the same
scoped query the listing uses.
"""
from __future__ import annotations

import pytest
from principals import admin_principal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.api.cases import list_cases
from cabqp.shared.db import Base
from cabqp.shared.models import Case, VerificationResult

PAGE_SIZE = 200


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _case(
    db: Session,
    *,
    organization_type=None,
    resolution_status=None,
    owner="alice",
    workflow_status="COMPLETED",
) -> Case:
    case = Case(
        created_by=owner,
        input_type="TEXT",
        raw_text="x",
        input_payload={},
        workflow_status=workflow_status,
    )
    db.add(case)
    db.flush()
    if resolution_status is not None or organization_type is not None:
        db.add(
            VerificationResult(
                case_id=case.id,
                organization_type=organization_type or "UNKNOWN",
                resolution_status=resolution_status,
            )
        )
        db.flush()
    return case


def _list(db, principal, page_size=PAGE_SIZE):
    return list_cases(page=1, page_size=page_size, db=db, p=principal)


def test_totals_count_the_queue_not_the_page(db):
    """The figure that used to stick at exactly the page size."""
    for _ in range(PAGE_SIZE + 17):
        _case(db, organization_type="BCA", resolution_status="MATCHED")

    body = _list(db, admin_principal("admin"))
    assert len(body["items"]) == PAGE_SIZE, "one page is still one page"
    assert body["totals"]["all"] == PAGE_SIZE + 17
    assert body["totals"]["verified"] == PAGE_SIZE + 17, "not capped at the page either"


def test_totals_split_by_the_same_rule_the_history_view_renders(db):
    _case(db, organization_type="BCA", resolution_status="MATCHED")
    _case(db, organization_type="BQP", resolution_status="MATCHED")
    # Resolved, but outside BCA/BQP: a decision, and not a verified one. It is also
    # not the absence of one, so it is counted apart from no_conclusion.
    _case(db, organization_type="OTHER", resolution_status="MATCHED")
    _case(db, organization_type="UNKNOWN", resolution_status="AMBIGUOUS")
    _case(db, organization_type="UNKNOWN", resolution_status="CONFLICT")
    _case(db, organization_type="UNKNOWN", resolution_status="NOT_FOUND")
    # Still processing: no result row at all.
    _case(db, workflow_status="RECEIVED")

    totals = _list(db, admin_principal("admin"))["totals"]
    assert totals["all"] == 7
    assert totals["verified"] == 2
    assert totals["need_review"] == 2
    assert totals["out_of_scope"] == 1
    # NOT_FOUND and the unprocessed case: no verified match, no open review, and
    # no decided out-of-scope verdict either.
    assert totals["no_conclusion"] == 2
    assert (
        totals["verified"] + totals["need_review"] + totals["out_of_scope"] + totals["no_conclusion"]
        == totals["all"]
    )


def test_unit_conclusion_outranks_review_of_other_dossier_facts(db):
    """History tiles describe unit membership, while review may concern other facts."""
    _case(db, organization_type="UNKNOWN", resolution_status="NOT_FOUND", workflow_status="NEED_REVIEW")
    _case(db, organization_type="BCA", resolution_status="MATCHED", workflow_status="NEED_REVIEW")
    _case(db, organization_type="OTHER", resolution_status="MATCHED", workflow_status="NEED_REVIEW")

    body = _list(db, admin_principal("admin"))
    totals = body["totals"]
    assert totals["need_review"] == 1
    assert totals["verified"] == 1
    assert totals["out_of_scope"] == 1
    assert totals["no_conclusion"] == 0
    assert {item["status_category"] for item in body["items"]} == {
        "NEED_REVIEW",
        "VERIFIED",
        "OUT_OF_SCOPE",
    }


def test_totals_respect_the_callers_scope(db):
    """A caller who sees only their own cases gets counts over only those."""
    for _ in range(3):
        _case(db, owner="alice", organization_type="BCA", resolution_status="MATCHED")
    for _ in range(4):
        _case(db, owner="bob", organization_type="BCA", resolution_status="MATCHED")

    from principals import user_principal

    alice = _list(db, user_principal("alice"))["totals"]
    assert alice["all"] == 3
    assert alice["verified"] == 3

    everyone = _list(db, admin_principal("admin"))["totals"]
    assert everyone["all"] == 7
