from __future__ import annotations

from datetime import date

import pytest
from principals import admin_principal, reviewer_principal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal
from cabqp.modules.bulk.service import validate_mapping
from cabqp.modules.cases.service import process_case
from cabqp.modules.review.service import decide_review
from cabqp.shared.db import Base
from cabqp.shared.models import (
    AuditLog,
    Case,
    EligibilityAssessment,
    Person,
    PolicyRule,
    ReviewCase,
    Source,
    Unit,
    VerificationResult,
)
from cabqp.shared.normalization import ascii_key, normalize_text
from cabqp.shared.schemas import ReviewDecision


def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_unit(db: Session) -> Unit:
    src = Source(authority="GOLDEN", url="https://example.invalid/unit", source_kind="OFFICIAL")
    db.add(src)
    db.flush()
    unit = Unit(
        id="unit_csgt",
        canonical_name="Cục Cảnh sát giao thông",
        normalized_key=normalize_text("Cục Cảnh sát giao thông"),
        organization_type="BCA",
        qa_status="APPROVED",
        active=True,
        source_id=src.id,
        coverage_group="TEST",
    )
    db.add(unit)
    db.flush()
    return unit


def seed_required_policy(db: Session, *, effective_from: date = date(2025, 1, 1)) -> PolicyRule:
    rule = PolicyRule(
        id="POL-REQUIRED",
        policy_type="BHXH_SCOPE",
        subject_groups=["CAND"],
        required_fields=["employment_status"],
        rule_expression={"scope_only": True},
        effective_from=effective_from,
        policy_version="policy-v1",
        source_kind="OFFICIAL",
        source_ref="golden",
        active=True,
    )
    db.add(rule)
    db.flush()
    return rule


def seed_person(db: Session, unit: Unit) -> Person:
    person = Person(
        id="person_nguyen_van_a",
        full_name="Nguyễn Văn A",
        normalized_key=normalize_text("Nguyễn Văn A"),
        ascii_key=ascii_key("Nguyễn Văn A"),
        canonical_unit_id=unit.id,
        employment_status="ACTIVE",
        subject_group_hint="CAND",
        qa_status="APPROVED",
        source_kind="PROVIDED",
        active=True,
    )
    db.add(person)
    db.flush()
    return person


def reviewer() -> Principal:
    return reviewer_principal("reviewer", coverage_groups={"*"})


def test_policy_missing_required_fact_routes_case_to_review_and_is_audited():
    db = db_session()
    unit = seed_unit(db)
    seed_person(db, unit)
    seed_required_policy(db)
    structured = {
        "subject_name": "Nguyễn Văn A",
        "position": "Sĩ quan Công an",
        "unit_name": "Cục Cảnh sát giao thông",
        "business_fields": {"subject_group": "CAND"},
        "as_of_date": "2026-02-01",
    }
    case = Case(created_by="user", input_type="TEXT", raw_text="Sĩ quan Công an", input_payload=structured)
    db.add(case)
    db.flush()

    result = process_case(db, case, structured)
    db.flush()

    assert result.resolution_status == "MATCHED"
    assert case.workflow_status == "NEED_REVIEW"
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert review is not None and review.reason == "POLICY_INSUFFICIENT_DATA"
    assessment = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert assessment is not None and assessment.status == "INSUFFICIENT_DATA"
    assert assessment.evidence["as_of_date"] == "2026-02-01"
    assert result.evidence["policy_as_of_date"] == "2026-02-01"
    assert db.scalar(select(AuditLog).where(AuditLog.entity_id == case.id, AuditLog.action == "CASE_DECISION")) is not None


def test_policy_effective_date_comes_from_case_not_wall_clock():
    db = db_session()
    unit = seed_unit(db)
    seed_person(db, unit)
    seed_required_policy(db, effective_from=date(2026, 1, 1))
    structured = {
        "subject_name": "Nguyễn Văn A",
        "position": "Sĩ quan Công an",
        "unit_name": "Cục Cảnh sát giao thông",
        "business_fields": {"subject_group": "CAND", "employment_status": "ACTIVE"},
        "as_of_date": "2025-06-01",
    }
    case = Case(created_by="user", input_type="TEXT", raw_text="Sĩ quan Công an", input_payload=structured)
    db.add(case)
    db.flush()

    result = process_case(db, case, structured)
    db.flush()

    assessments = list(db.scalars(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id)))
    assert assessments == []
    assert result.evidence["policy_as_of_date"] == "2025-06-01"
    assert case.workflow_status == "COMPLETED"


def test_review_insufficient_preserves_verified_unit():
    db = db_session()
    unit = seed_unit(db)
    seed_required_policy(db)
    case = Case(
        created_by="user",
        input_type="TEXT",
        raw_text="Sĩ quan Công an",
        input_payload={"business_fields": {"subject_group": "CAND"}, "as_of_date": "2026-02-01"},
    )
    db.add(case)
    db.flush()
    result = VerificationResult(
        case_id=case.id,
        unit_id=unit.id,
        organization_type="BCA",
        resolution_status="MATCHED",
        subject_group="CAND",
        match_method="CANONICAL_EXACT",
        source_kind="OFFICIAL",
    )
    db.add(result)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=result.id, reason="POLICY_INSUFFICIENT_DATA", coverage_group="TEST")
    db.add(review)
    db.commit()

    decide_review(
        db,
        review.id,
        ReviewDecision(decision="INSUFFICIENT", expected_version=1, note="Thiếu trạng thái công tác"),
        reviewer(),
    )
    db.commit()

    refreshed = db.get(VerificationResult, result.id)
    assert refreshed.unit_id == unit.id
    assert refreshed.organization_type == "BCA"
    assert refreshed.resolution_status == "MATCHED"
    assert db.get(Case, case.id).workflow_status == "COMPLETED"
    assessment = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert assessment is not None and assessment.status == "INSUFFICIENT_DATA"


def test_subject_group_review_can_confirm_without_reentering_matched_unit():
    db = db_session()
    unit = seed_unit(db)
    case = Case(created_by="user", input_type="TEXT", raw_text="x", input_payload={})
    db.add(case)
    db.flush()
    result = VerificationResult(
        case_id=case.id,
        unit_id=unit.id,
        organization_type="BCA",
        resolution_status="MATCHED",
        subject_group=None,
        source_kind="OFFICIAL",
    )
    db.add(result)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=result.id, reason="SUBJECT_GROUP_INSUFFICIENT", coverage_group="TEST")
    db.add(review)
    db.commit()

    decide_review(
        db,
        review.id,
        ReviewDecision(decision="CONFIRM", subject_group="CAND", expected_version=1),
        reviewer(),
    )
    db.commit()

    refreshed = db.get(VerificationResult, result.id)
    assert refreshed.unit_id == unit.id
    assert refreshed.subject_group == "CAND"
    assert refreshed.resolution_status == "MATCHED"


def test_manual_dismiss_fails_closed_instead_of_stranding_need_review_case():
    db = db_session()
    case = Case(created_by="user", input_type="FILE", raw_text=None, workflow_status="NEED_REVIEW")
    db.add(case)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=None, reason="DOCUMENT_PARSE_EMPTY", coverage_group="UNASSIGNED")
    db.add(review)
    db.commit()

    decide_review(db, review.id, ReviewDecision(decision="DISMISS", expected_version=1, note="Tài liệu không dùng được"), reviewer())
    db.commit()

    assert db.get(ReviewCase, review.id).status == "DISMISSED"
    assert db.get(Case, case.id).workflow_status == "FAILED"


def test_bulk_mapping_rejects_duplicate_or_unknown_targets():
    headers = ["Họ tên", "Tên cán bộ"]
    with pytest.raises(ValueError, match="only be mapped once"):
        validate_mapping(headers, {"Họ tên": "subject_name", "Tên cán bộ": "subject_name"})
    with pytest.raises(ValueError, match="Unsupported target fields"):
        validate_mapping(headers, {"Họ tên": "not_a_business_field", "Tên cán bộ": None})


def test_review_rejects_unknown_subject_group_and_refreshes_policy_summary():
    db = db_session()
    unit = seed_unit(db)
    seed_required_policy(db)
    case = Case(
        created_by="user",
        input_type="TEXT",
        raw_text="Sĩ quan Công an",
        input_payload={"business_fields": {"employment_status": "ACTIVE"}, "as_of_date": "2026-02-01"},
    )
    db.add(case)
    db.flush()
    result = VerificationResult(
        case_id=case.id,
        unit_id=unit.id,
        organization_type="BCA",
        resolution_status="MATCHED",
        subject_group=None,
        source_kind="OFFICIAL",
        evidence={"policy_summary": [{"status": "STALE"}]},
    )
    db.add(result)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=result.id, reason="SUBJECT_GROUP_INSUFFICIENT", coverage_group="TEST")
    db.add(review)
    db.commit()

    with pytest.raises(Exception) as exc:
        decide_review(
            db,
            review.id,
            ReviewDecision(decision="CONFIRM", subject_group="NOT_A_REAL_GROUP", expected_version=1),
            reviewer(),
        )
    assert getattr(exc.value, "status_code", None) == 422
    db.rollback()

    decide_review(
        db,
        review.id,
        ReviewDecision(decision="CONFIRM", subject_group="CAND", expected_version=1),
        reviewer(),
    )
    db.commit()
    refreshed = db.get(VerificationResult, result.id)
    assert refreshed.evidence["policy_as_of_date"] == "2026-02-01"
    assert refreshed.evidence["policy_summary"][0]["status"] == "ELIGIBLE"


def test_reviewer_case_access_is_limited_to_coverage_scope_and_bulk_is_owner_only():
    from fastapi import HTTPException

    from cabqp.api.bulk import _auth as authorize_bulk
    from cabqp.api.cases import _authorize
    from cabqp.shared.models import BulkIngestJob

    db = db_session()
    case = Case(created_by="alice", input_type="TEXT", raw_text="x", input_payload={})
    db.add(case)
    db.flush()
    review = ReviewCase(case_id=case.id, reason="TEST", coverage_group="BCA-NORTH")
    db.add(review)
    db.flush()

    # Coverage scope, with CASE_VIEW_ALL withheld: the point of the test is
    # that the scope itself is the boundary.
    scoped = (perms.REVIEW_QUEUE, perms.REVIEW_DECIDE)
    north = reviewer_principal("reviewer-north", coverage_groups={"BCA-NORTH"}, permissions=scoped)
    south = reviewer_principal("reviewer-south", coverage_groups={"BCA-SOUTH"}, permissions=scoped)
    _authorize(db, case, north)
    with pytest.raises(HTTPException) as exc:
        _authorize(db, case, south)
    assert exc.value.status_code == 403

    job = BulkIngestJob(file_name="people.xlsx", file_sha256="a" * 64, created_by="alice")
    db.add(job)
    db.flush()
    with pytest.raises(HTTPException) as exc:
        authorize_bulk(job, north)
    assert exc.value.status_code == 403
    authorize_bulk(job, admin_principal())


def test_reviewer_can_self_assign_in_scope_but_cannot_assign_another_user():
    from cabqp.api.reviews import assign_review
    from cabqp.shared.schemas import ReviewAssign

    db = db_session()
    case = Case(created_by="user", input_type="TEXT", raw_text="x", workflow_status="NEED_REVIEW")
    db.add(case); db.flush()
    review = ReviewCase(case_id=case.id, result_id=None, reason="AMBIGUOUS", coverage_group="TEST")
    db.add(review); db.commit()
    p = reviewer_principal("reviewer", coverage_groups={"TEST"})

    assigned = assign_review(review.id, ReviewAssign(assigned_to="reviewer", expected_version=1), db, p)
    assert assigned["assigned_to"] == "reviewer"
    assert assigned["version"] == 2

    with pytest.raises(Exception) as exc:
        assign_review(review.id, ReviewAssign(assigned_to="someone-else", expected_version=2), db, p)
    assert getattr(exc.value, "status_code", None) == 403


def test_reviewer_cannot_self_assign_outside_scope():
    from cabqp.api.reviews import assign_review
    from cabqp.shared.schemas import ReviewAssign

    db = db_session()
    case = Case(created_by="user", input_type="TEXT", raw_text="x", workflow_status="NEED_REVIEW")
    db.add(case); db.flush()
    review = ReviewCase(case_id=case.id, result_id=None, reason="AMBIGUOUS", coverage_group="OTHER")
    db.add(review); db.commit()
    p = reviewer_principal("reviewer", coverage_groups={"TEST"})

    with pytest.raises(Exception) as exc:
        assign_review(review.id, ReviewAssign(assigned_to="reviewer", expected_version=1), db, p)
    assert getattr(exc.value, "status_code", None) == 403


def test_review_payload_carries_subject_identity_and_gates():
    """A reviewer opening the queue must be able to tell who the review is about,
    and how far short of each gate the Case fell, without fetching the Case."""
    db = db_session()
    seed_unit(db)
    structured = {
        "subject_name": "Nguyễn Văn A",
        "subject_code": "CA-12345",
        "position": "Sĩ quan Công an",
        "unit_name": "Đơn vị không có trong danh mục",
        "business_fields": {"subject_group": "CAND", "birth_year": "1985"},
    }
    case = Case(created_by="user", input_type="TEXT", raw_text="Sĩ quan Công an", input_payload=structured)
    db.add(case)
    db.flush()

    process_case(db, case, structured)
    db.flush()

    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert review is not None
    payload = review.payload

    assert payload["subject"]["name"] == "Nguyễn Văn A"
    assert payload["subject"]["subject_code"] == "CA-12345"
    assert payload["subject"]["position"] == "Sĩ quan Công an"
    assert payload["subject"]["birth_year"] == "1985"
    # The gate is stored next to the confidence it was compared against.
    assert isinstance(payload["thresholds"]["extraction_min"], float)
    assert payload["confidence"]["extraction"] is not None
    assert payload["resolution"]["status"] == "NOT_FOUND"
    assert payload["case"]["created_by"] == "user"
    assert payload["case"]["input_type"] == "TEXT"


def test_review_queue_returns_decision_trail():
    """A RESOLVED row has to say who decided it, when, and why."""
    from cabqp.api.reviews import queue
    from cabqp.shared.enums import ReviewStatus

    db = db_session()
    case = Case(created_by="user", input_type="TEXT", raw_text="x", workflow_status="COMPLETED")
    db.add(case)
    db.flush()
    review = ReviewCase(
        case_id=case.id,
        result_id=None,
        reason="AMBIGUOUS",
        coverage_group="TEST",
        status="RESOLVED",
        reviewed_by="reviewer",
        decision_note="Đã đối chiếu tài liệu gốc",
    )
    db.add(review)
    db.commit()

    body = queue(
        status=ReviewStatus.RESOLVED,
        page=1,
        page_size=50,
        db=db,
        p=admin_principal("admin"),
    )
    row = body["items"][0]
    assert row["status"] == "RESOLVED"
    assert row["reviewed_by"] == "reviewer"
    assert row["decision_note"] == "Đã đối chiếu tài liệu gốc"
