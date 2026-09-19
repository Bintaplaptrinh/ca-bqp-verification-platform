"""One import may create at most `bulk_max_rows` Cases.

This is a workload cap, not a parser guard: `document_max_spreadsheet_rows`
already refuses a file big enough to exhaust memory, while this bounds what a
single operator request queues onto the worker and what the result screen has to
render. A list over the cap is refused outright — nothing is queued and no row
is written — and the rejection has to carry the two numbers, because the client
shows the server's wording verbatim.
"""

from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from cabqp.modules.bulk.service import profile_and_validate
from cabqp.modules.document_intelligence.limits import DocumentLimitError
from cabqp.shared.models import Base, BulkIngestJob, BulkIngestRow
from cabqp.shared.settings import get_settings


def _roster(rows: int) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Họ và tên", "Chức vụ", "Đơn vị công tác"])
    for index in range(rows):
        sheet.append([f"Nguyễn Văn {index:03d}", "Cán bộ", "Cục Cảnh sát giao thông"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bulk.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _job(db: Session, name: str) -> BulkIngestJob:
    job = BulkIngestJob(file_name=name, file_sha256=name, status="UPLOADED", created_by="tester")
    db.add(job)
    db.flush()
    return job


def test_the_default_cap_is_fifty():
    assert get_settings().bulk_max_rows == 50


def test_a_list_at_the_cap_is_accepted(db):
    cap = get_settings().bulk_max_rows
    job = _job(db, "vua_du.xlsx")
    profile_and_validate(db, job, _roster(cap))
    assert job.total_rows == cap
    assert db.scalar(select(BulkIngestRow).where(BulkIngestRow.job_id == job.id)) is not None


def test_a_list_over_the_cap_is_refused_with_both_numbers(db):
    cap = get_settings().bulk_max_rows
    job = _job(db, "qua_dai.xlsx")
    with pytest.raises(DocumentLimitError) as raised:
        profile_and_validate(db, job, _roster(cap + 1))
    assert raised.value.code == "BULK_ROW_LIMIT_EXCEEDED"
    assert raised.value.details["rows"] == cap + 1
    assert raised.value.details["limit"] == cap


def test_a_refused_list_writes_no_rows(db):
    """The cap is checked before any row is written, so a rejection leaves nothing behind."""
    cap = get_settings().bulk_max_rows
    job = _job(db, "khong_ghi.xlsx")
    with pytest.raises(DocumentLimitError):
        profile_and_validate(db, job, _roster(cap + 5))
    assert db.scalars(select(BulkIngestRow).where(BulkIngestRow.job_id == job.id)).all() == []
    assert job.total_rows in (None, 0)


def test_the_rejection_detail_is_actionable_vietnamese():
    """The client renders this text as-is, so it must name both numbers."""
    from cabqp.api.bulk import _limit_detail

    detail = _limit_detail(DocumentLimitError("BULK_ROW_LIMIT_EXCEEDED", rows=73, limit=50))
    assert detail["code"] == "BULK_ROW_LIMIT_EXCEEDED"
    assert (detail["rows"], detail["limit"]) == (73, 50)
    assert "73" in detail["message"] and "50" in detail["message"]
    assert "dòng" in detail["message"]


def test_other_limit_codes_keep_their_bare_shape():
    """Only the row cap gains a structured body; nothing matching on a code breaks."""
    from cabqp.api.bulk import _limit_detail

    assert _limit_detail(DocumentLimitError("WORKSHEET_LIMIT_EXCEEDED", worksheets=99)) == (
        "WORKSHEET_LIMIT_EXCEEDED"
    )
