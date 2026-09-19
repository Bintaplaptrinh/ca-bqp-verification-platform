"""Fan-out must not consume the caller's Idempotency-Key, and status must not overstate.

Two independent regressions that both show up as a Case being reported as something
it is not:

* The document worker keyed block #0 of a multi-subject split with its own group key,
  overwriting whatever Idempotency-Key the client had sent at upload. A retry carrying
  the original key then matched nothing and uploaded the same dossier a second time.
  The synchronous text path never did this, which is the shape the worker now follows.
* ``verification_status`` was derived from workflow completion alone, so a reviewer who
  decided UNKNOWN — closing the Case with resolution_status NOT_FOUND — still had it
  reported back as "Đã xác định".
"""

from __future__ import annotations

import pytest
from principals import admin_principal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.api.cases import _existing_idempotent_case, _verification_status, list_case_subjects
from cabqp.shared.db import Base
from cabqp.shared.models import Case, VerificationResult

CLIENT_KEY = "client-supplied-key-42"
DOCUMENT_ID = "doc_abc123"


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _split_case(db: Session, *, block_index: int, idempotency_key: str | None, owner="alice") -> Case:
    """One member of a document-worker fan-out group."""
    case = Case(
        created_by=owner,
        input_type="FILE",
        raw_text=f"block {block_index}",
        input_payload={},
        idempotency_key=idempotency_key,
        workflow_status="COMPLETED",
    )
    db.add(case)
    db.flush()
    db.add(
        VerificationResult(
            case_id=case.id,
            organization_type="BQP",
            resolution_status="MATCHED",
            evidence={
                "split_source": {
                    "document_id": DOCUMENT_ID,
                    "source_case_id": None,  # filled by the caller for block 0
                    "block_index": block_index,
                    "block_count": 2,
                }
            },
        )
    )
    db.flush()
    return case


def _group(db: Session) -> tuple[Case, Case]:
    """Block #0 keeps the caller's key; block #1 carries the group key."""
    block0 = _split_case(db, block_index=0, idempotency_key=CLIENT_KEY)
    block1 = _split_case(db, block_index=1, idempotency_key=f"{DOCUMENT_ID}:1")
    for case in (block0, block1):
        result = db.scalar(select(VerificationResult).where(VerificationResult.case_id == case.id))
        evidence = dict(result.evidence)
        evidence["split_source"] = {**evidence["split_source"], "source_case_id": block0.id}
        result.evidence = evidence
    db.flush()
    return block0, block1


def test_block_zero_keeps_the_callers_idempotency_key(db):
    block0, _ = _group(db)
    assert block0.idempotency_key == CLIENT_KEY
    # The retry that used to create a duplicate Case now finds the original.
    assert _existing_idempotent_case(db, "alice", CLIENT_KEY) is block0


def test_the_group_is_still_reachable_from_either_member(db):
    """Keeping block #0's own key must not lose it from its own split group.

    The group key is how siblings are found, so block #0 is recovered through
    ``split_source.source_case_id`` instead — the mechanism the text path already
    used for exactly this reason.
    """
    block0, block1 = _group(db)
    principal = admin_principal("admin")

    from_block1 = list_case_subjects(case_id=block1.id, db=db, p=principal)
    assert from_block1["subject_count"] == 2
    assert [row["block_index"] for row in from_block1["items"]] == [0, 1]
    assert {row["case_id"] for row in from_block1["items"]} == {block0.id, block1.id}

    from_block0 = list_case_subjects(case_id=block0.id, db=db, p=principal)
    assert from_block0["subject_count"] == 2
    assert {row["case_id"] for row in from_block0["items"]} == {block0.id, block1.id}


def _status(workflow_status, resolution_status=None, organization_type="UNKNOWN") -> str:
    case = Case(
        created_by="alice",
        input_type="TEXT",
        raw_text="x",
        input_payload={},
        workflow_status=workflow_status,
    )
    result = (
        None
        if resolution_status is None
        else VerificationResult(
            case_id="case_x",
            resolution_status=resolution_status,
            organization_type=organization_type,
        )
    )
    return _verification_status(case, result)


def test_a_reviewer_decision_of_unknown_is_not_reported_as_identified():
    """The exact state POST /reviews/{id}/decision leaves behind for UNKNOWN."""
    assert _status("COMPLETED", "NOT_FOUND", "UNKNOWN") == "Chưa xác định được đơn vị"


def test_verification_status_distinguishes_out_of_scope_from_not_found():
    """NOT_FOUND != OTHER, including in the wording an operator reads."""
    assert _status("COMPLETED", "MATCHED", "BCA") == "Đã xác định"
    assert _status("COMPLETED", "MATCHED", "BQP") == "Đã xác định"
    assert _status("COMPLETED", "MATCHED", "OTHER") == "Ngoài phạm vi CA/BQP"
    assert _status("COMPLETED", "MATCHED", "OTHER") != _status("COMPLETED", "NOT_FOUND", "UNKNOWN")


def test_an_open_review_outranks_whatever_label_the_resolver_left():
    assert _status("NEED_REVIEW", "MATCHED", "BCA") == "Cần xác minh"
    assert _status("NEED_REVIEW", "AMBIGUOUS") == "Cần xác minh"
    assert _status("FAILED", "NOT_FOUND") == "Không xử lý được"
    assert _status("RECEIVED") == "Đang xử lý"
