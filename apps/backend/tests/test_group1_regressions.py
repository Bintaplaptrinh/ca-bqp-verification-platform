from datetime import date

import pytest
from fastapi import HTTPException
from principals import reviewer_principal
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.auth.dependencies import Principal
from cabqp.modules.cases.service import process_case
from cabqp.modules.decisioning.policy import PolicyEngine
from cabqp.modules.document_intelligence.extraction import extract
from cabqp.modules.review.service import decide_review
from cabqp.modules.subject_group.service import classify_subject_group
from cabqp.shared.db import Base
from cabqp.shared.models import (
    AuditLog,
    Case,
    EligibilityAssessment,
    PolicyRule,
    ReviewCase,
    Source,
    Unit,
    VerificationResult,
)
from cabqp.shared.normalization import normalize_text
from cabqp.shared.schemas import ReviewDecision


def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def principal() -> Principal:
    return reviewer_principal("reviewer", coverage_groups={"*"})


def test_review_rejects_missing_result_instead_of_crashing():
    db = db_session()
    case = Case(created_by="user", input_type="TEXT", raw_text="x")
    db.add(case)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=None, reason="AMBIGUOUS")
    db.add(review)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        decide_review(
            db,
            review.id,
            ReviewDecision(decision="UNKNOWN", expected_version=1),
            principal(),
        )
    assert exc.value.status_code == 409


def test_review_optimistic_lock_blocks_stale_decision():
    db = db_session()
    case = Case(created_by="user", input_type="TEXT", raw_text="x")
    db.add(case)
    db.flush()
    result = VerificationResult(case_id=case.id, resolution_status="AMBIGUOUS")
    db.add(result)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=result.id, reason="AMBIGUOUS", version_no=2)
    db.add(review)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        decide_review(
            db,
            review.id,
            ReviewDecision(decision="UNKNOWN", expected_version=1),
            principal(),
        )
    assert exc.value.status_code == 409


def test_review_preserves_business_fields_for_policy_and_source_kind():
    db = db_session()
    src = Source(authority="official", url="https://example.invalid", source_kind="OFFICIAL")
    db.add(src)
    db.flush()
    unit = Unit(
        id="unit_1",
        canonical_name="Công an tỉnh Cà Mau",
        normalized_key=normalize_text("Công an tỉnh Cà Mau"),
        organization_type="BCA",
        qa_status="APPROVED",
        active=True,
        source_id=src.id,
    )
    db.add(unit)
    rule = PolicyRule(
        id="POL-TEST",
        policy_type="BHXH_SCOPE",
        subject_groups=["CAND"],
        required_fields=["employment_status"],
        rule_expression={"scope_only": True},
        effective_from=date(2025, 1, 1),
        policy_version="test-v1",
        source_kind="OFFICIAL",
        source_ref="test",
        active=True,
    )
    db.add(rule)
    case = Case(
        created_by="user",
        input_type="TEXT",
        raw_text="sĩ quan công an",
        input_payload={"business_fields": {"employment_status": "ACTIVE"}},
    )
    db.add(case)
    db.flush()
    result = VerificationResult(
        case_id=case.id,
        resolution_status="AMBIGUOUS",
        organization_type="UNKNOWN",
        subject_group="CAND",
        source_kind="PROVIDED",
    )
    db.add(result)
    db.flush()
    review = ReviewCase(case_id=case.id, result_id=result.id, reason="AMBIGUOUS")
    db.add(review)
    db.commit()

    body = ReviewDecision(decision="CONFIRM", unit_id=unit.id, expected_version=1)
    decide_review(db, review.id, body, principal())
    db.commit()

    refreshed = db.get(VerificationResult, result.id)
    assessment = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert refreshed.source_kind == "OFFICIAL"
    assert assessment is not None
    assert assessment.status == "ELIGIBLE"
    assert assessment.evidence["facts_used"]["employment_status"] == "ACTIVE"
    audit_row = db.scalar(select(AuditLog).where(AuditLog.entity_id == review.id, AuditLog.action == "REVIEW_DECISION"))
    assert audit_row is not None


def test_empty_subject_group_scope_fails_closed():
    db = db_session()
    rule = PolicyRule(
        id="POL-EMPTY-SCOPE",
        policy_type="BHXH_SCOPE",
        subject_groups=[],
        required_fields=[],
        rule_expression={},
        policy_version="test-v1",
        source_kind="OFFICIAL",
        source_ref="test",
        active=True,
    )
    db.add(rule)
    case = Case(created_by="user", input_type="TEXT", raw_text="x")
    db.add(case)
    db.flush()
    result = VerificationResult(case_id=case.id, resolution_status="MATCHED", organization_type="BCA")
    db.add(result)
    db.flush()

    PolicyEngine(db).evaluate(result_id=result.id, subject_group="CAND", facts={})
    db.flush()
    assessment = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert assessment.status == "NOT_APPLICABLE"
    assert "không khai báo subject_groups" in assessment.reason


def test_negated_subject_group_is_not_positive():
    group, confidence, method = classify_subject_group(
        organization_type="BCA",
        position=None,
        text="Người này không phải sĩ quan công an và đang làm việc dân sự.",
        fields={},
    )
    assert group is None
    assert confidence == 0.0
    assert method == "INSUFFICIENT_EVIDENCE"


def test_process_case_is_idempotent_for_verification_result():
    db = db_session()
    case = Case(created_by="user", input_type="TEXT", raw_text="Không có đơn vị xác định")
    db.add(case)
    db.flush()

    process_case(db, case, {})
    db.flush()
    process_case(db, case, {})
    db.flush()

    count = db.scalar(
        select(func.count()).select_from(VerificationResult).where(VerificationResult.case_id == case.id)
    )
    assert count == 1


def test_unmarked_unit_mention_without_current_marker_is_low_confidence():
    """A unit named in free text with no 'hiện công tác tại' / 'trước đây' marker at
    all must never be trusted as CURRENT_WORK_UNIT at full confidence — it can only
    be used as a low-confidence guess that routes the case to human review."""
    text = (
        "Đồng chí Nguyễn Văn A đã học tập và công tác tại Học viện Cảnh sát nhân dân "
        "trong giai đoạn 2015-2020 trước khi chuyển công tác."
    )
    x = extract(text)
    assert x.relation_confidence < 0.7


def test_multiple_unmarked_unit_mentions_do_not_guess_current_unit():
    """Several unit-like mentions with no marker at all must not collapse to a single
    guessed CURRENT_WORK_UNIT — ambiguity must surface, not be silently resolved."""
    text = "Cục Cảnh sát giao thông và Công an tỉnh Cà Mau đều được nhắc đến trong hồ sơ."
    x = extract(text)
    assert x.current_unit is None
    assert x.relation_confidence < 0.7


def test_negation_separated_by_a_copula_is_detected():
    """Vietnamese puts copulas between the negation and the noun.

    "không còn là sĩ quan" previously slipped past the guard and reported the subject as
    serving police — asserting force membership the document explicitly denies.
    """
    for text in (
        "Đồng chí không còn là sĩ quan công an",
        "Đồng chí không phải là sĩ quan công an",
        "Đồng chí không phải một chiến sĩ công an",
        "Đồng chí chưa là sĩ quan công an",
        "Đồng chí không thuộc biên chế công an nhân dân",
    ):
        group, confidence, method = classify_subject_group(
            organization_type="BCA", position=None, text=text, fields={}
        )
        assert group is None, text
        assert confidence == 0.0
        assert method == "INSUFFICIENT_EVIDENCE"


def test_negation_guard_does_not_suppress_plain_affirmatives():
    for text in ("Đồng chí là sĩ quan công an", "Đồng chí hiện là chiến sĩ công an"):
        group, _confidence, method = classify_subject_group(
            organization_type="BCA", position=None, text=text, fields={}
        )
        assert group == "CAND", text
        assert method == "RULE_TEXT"


def test_negation_separated_by_a_copula_is_detected_for_bqp():
    group, _confidence, _method = classify_subject_group(
        organization_type="BQP", position=None, text="Đồng chí không còn là quân nhân", fields={}
    )
    assert group is None


def test_historical_role_followed_by_current_exit_is_not_current_membership():
    for text in (
        "Đồng chí từng là sĩ quan công an, nhưng nay không còn công tác trong ngành.",
        "dong chi tung la si quan cong an nhung nay khong con cong tac trong nganh",
    ):
        group, confidence, method = classify_subject_group(
            organization_type="BCA",
            position=None,
            text=text,
            fields={},
        )
        assert group is None, text
        assert confidence == 0.0
        assert method == "INSUFFICIENT_EVIDENCE"
