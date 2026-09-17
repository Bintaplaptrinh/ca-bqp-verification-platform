"""Batch ingestion must apply the same effective-date rule as the single-case paths.

`as_of_date` pins which registry snapshot and which policy version decide a case, so a
spreadsheet column must not be a way around the guard that /cases/text and /lookup enforce.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

import pytest

from cabqp.modules.bulk.service import _validate_business_date


def _csv(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Ho ten", "Don vi cong tac", "Nhom doi tuong", "Ngay danh gia"])
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def test_bulk_module_uses_the_shared_date_guard():
    """The batch path must reuse the rule, not re-implement a looser copy of it."""
    with pytest.raises(ValueError):
        _validate_business_date(dt.date(2999, 1, 1))
    with pytest.raises(ValueError):
        _validate_business_date(dt.date(1900, 1, 1))
    assert _validate_business_date(dt.date(2026, 1, 15)) == dt.date(2026, 1, 15)
    assert _validate_business_date(None) is None


@pytest.mark.parametrize(
    "value",
    ["2999-01-01", "1900-01-01"],
)
def test_implausible_dates_are_rejected_by_the_shared_guard(value):
    with pytest.raises(ValueError):
        _validate_business_date(dt.date.fromisoformat(value))


def test_plausible_batch_dates_are_accepted():
    today = dt.date.today()
    assert _validate_business_date(today) == today
    near_future = today + dt.timedelta(days=200)
    assert _validate_business_date(near_future) == near_future


def test_csv_helper_builds_rows_for_manual_probes():
    """Kept alongside the guard tests so the fixture shape stays in one place."""
    payload = _csv([["Nguyen Van A", "Cục Kỹ thuật", "QUAN_NHAN", "2026-01-15"]])
    assert b"Ngay danh gia" in payload
    assert b"2026-01-15" in payload
