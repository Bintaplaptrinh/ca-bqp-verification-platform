from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException
from principals import admin_principal, user_principal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.api.cases import get_case, request_case_review
from cabqp.api.reviews import queue
from cabqp.shared.db import Base
from cabqp.shared.enums import ReviewStatus
from cabqp.shared.models import AuditLog, Case, ExtractedRecord, ReviewCase, VerificationResult


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _reviewed_case(
    db: Session,
    *,
    case_id: str,
    name: str,
    created_at: datetime,
) -> tuple[Case, ReviewCase]:
    case = Case(
        id=case_id,
        created_by="alice",
        input_type="TEXT",
        raw_text=name,
        input_payload={},
        workflow_status="NEED_REVIEW",
        created_at=created_at,
    )
    db.add(case)
    db.flush()
    record = ExtractedRecord(case_id=case.id, subject_name=name, subject_code="CB-01")
    result = VerificationResult(
        case_id=case.id,
        resolution_status="NOT_FOUND",
        organization_type="UNKNOWN",
    )
    db.add_all([record, result])
    db.flush()
    review = ReviewCase(
        case_id=case.id,
        result_id=result.id,
        reason="NOT_FOUND",
        coverage_group="UNASSIGNED",
        created_at=created_at,
        payload={"subject": {"name": "Tên snapshot cũ"}},
    )
    db.add(review)
    db.commit()
    return case, review


def _queue(db: Session, **overrides):
    params = {
        "status": ReviewStatus.OPEN,
        "search": None,
        "date_from": None,
        "date_to": None,
        "page": 1,
        "page_size": 50,
        "db": db,
        "p": admin_principal(),
    }
    params.update(overrides)
    return queue(**params)


def test_queue_filters_by_name_displayed_case_code_and_submitted_day(db):
    _reviewed_case(
        db,
        case_id="case_ABCDEF12-old",
        name="Nguyễn Văn Minh",
        created_at=datetime(2026, 9, 20, 8, 30),
    )
    _reviewed_case(
        db,
        case_id="case_98765432-new",
        name="Trần Thu Hà",
        created_at=datetime(2026, 9, 21, 9, 45),
    )

    by_name = _queue(db, search="Nguyễn Văn Minh")
    assert by_name["total"] == 1
    assert by_name["items"][0]["subject"]["name"] == "Nguyễn Văn Minh"
    assert by_name["items"][0]["payload"]["subject"]["name"] == "Tên snapshot cũ"

    by_code = _queue(db, search="HS-2026-ABCDEF12")
    assert by_code["total"] == 1
    assert by_code["items"][0]["case_code"] == "HS-2026-ABCDEF12"

    by_day = _queue(db, date_from=date(2026, 9, 21), date_to=date(2026, 9, 21))
    assert by_day["total"] == 1
    assert by_day["items"][0]["subject"]["name"] == "Trần Thu Hà"


def test_queue_rejects_reversed_date_range(db):
    with pytest.raises(HTTPException) as exc:
        _queue(db, date_from=date(2026, 9, 22), date_to=date(2026, 9, 21))
    assert exc.value.status_code == 422


def test_inconclusive_owner_can_request_review_idempotently(db):
    case = Case(
        id="case_REVIEW01",
        created_by="alice",
        input_type="TEXT",
        raw_text="Nguyễn Văn Minh",
        input_payload={"business_fields": {"birth_year": 1985}},
        workflow_status="COMPLETED",
    )
    db.add(case)
    db.flush()
    record = ExtractedRecord(
        case_id=case.id,
        subject_name="Nguyễn Văn Minh",
        subject_code="CB-01",
        current_unit_raw="Đơn vị chưa xác định",
    )
    result = VerificationResult(
        case_id=case.id,
        resolution_status="NOT_FOUND",
        organization_type="UNKNOWN",
        evidence={"parse_method": "PLAIN_TEXT"},
    )
    db.add_all([record, result])
    db.commit()

    principal = user_principal("alice")
    first = request_case_review(case.id, db=db, p=principal)
    second = request_case_review(case.id, db=db, p=principal)

    assert first["already_requested"] is False
    assert second["already_requested"] is True
    assert db.get(Case, case.id).workflow_status == "NEED_REVIEW"
    reviews = list(db.scalars(select(ReviewCase).where(ReviewCase.case_id == case.id)))
    assert len(reviews) == 1
    assert reviews[0].reason == "USER_REQUESTED_RECONCILIATION"
    assert reviews[0].payload["subject"]["name"] == "Nguyễn Văn Minh"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "REVIEW_REQUEST")) is not None

    detail = get_case(case.id, db=db, p=principal)
    assert detail["review_request"]["id"] == reviews[0].id


def test_case_with_conclusion_cannot_be_sent_to_review(db):
    case = Case(
        created_by="alice",
        input_type="TEXT",
        raw_text="x",
        input_payload={},
        workflow_status="COMPLETED",
    )
    db.add(case)
    db.flush()
    db.add(
        VerificationResult(
            case_id=case.id,
            resolution_status="MATCHED",
            organization_type="BCA",
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc:
        request_case_review(case.id, db=db, p=user_principal("alice"))
    assert exc.value.status_code == 409


def test_case_detail_recovers_unit_from_original_structured_input(db):
    case = Case(
        id="case_UNIT_FALLBACK",
        created_by="alice",
        input_type="TEXT",
        raw_text="Nguyễn Văn Minh",
        input_payload={
            "unit_name": "Cục Kỹ thuật nghiệp vụ",
            "unit_code": "KTNV-01",
        },
        workflow_status="NEED_REVIEW",
    )
    db.add(case)
    db.flush()
    db.add_all(
        [
            ExtractedRecord(
                case_id=case.id,
                subject_name="Nguyễn Văn Minh",
                current_unit_raw=None,
                extracted_fields={"structured": dict(case.input_payload)},
            ),
            VerificationResult(
                case_id=case.id,
                resolution_status="NOT_FOUND",
                organization_type="UNKNOWN",
            ),
        ]
    )
    db.commit()

    detail = get_case(case.id, db=db, p=user_principal("alice"))

    assert detail["extracted"]["current_unit_raw"] is None
    assert detail["submitted_unit"] == {
        "name": "Cục Kỹ thuật nghiệp vụ",
        "code": "KTNV-01",
    }
