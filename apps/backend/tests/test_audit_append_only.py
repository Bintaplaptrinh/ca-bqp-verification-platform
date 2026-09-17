"""Append-only guarantee for the business audit trail.

The audit rows record who attributed a person to a force. Application code only inserts,
but that is a convention; these tests pin the behaviour so a future change cannot quietly
introduce a path that edits or removes history.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.shared.models import AuditLog

POSTGRES_URL = os.environ.get("AUDIT_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
requires_postgres = pytest.mark.skipif(
    "postgresql" not in POSTGRES_URL,
    reason="append-only is enforced by a PostgreSQL trigger",
)


def test_audit_helper_only_inserts():
    """The helper must never expose an update or delete path."""
    import inspect

    from cabqp.modules.audit import service

    source = inspect.getsource(service)
    assert "db.add(" in source
    assert "delete(" not in source
    assert ".update(" not in source


def test_no_module_updates_or_deletes_audit_rows():
    """No production module may write to audit_logs except by appending."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "cabqp"
    offenders = []
    for path in src.rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        if "AuditLog" not in body:
            continue
        for marker in ("delete(AuditLog", "update(AuditLog"):
            if marker in body:
                offenders.append(f"{path.name}: {marker}")
    assert offenders == [], offenders


@requires_postgres
def test_update_on_audit_row_is_rejected():
    engine = create_engine(POSTGRES_URL)
    with Session(engine) as db:
        audit(
            db,
            actor="test",
            role="ADMIN",
            action="APPEND_ONLY_PROBE",
            entity_type="TEST",
            entity_id="probe-update",
        )
        db.flush()
        row = db.scalar(select(AuditLog).where(AuditLog.entity_id == "probe-update"))
        assert row is not None

        with pytest.raises(Exception) as exc:
            db.execute(update(AuditLog).where(AuditLog.id == row.id).values(action="TAMPERED"))
            db.flush()
        assert "append-only" in str(exc.value).lower()
        db.rollback()


@requires_postgres
def test_delete_on_audit_row_is_rejected():
    engine = create_engine(POSTGRES_URL)
    with Session(engine) as db:
        audit(
            db,
            actor="test",
            role="ADMIN",
            action="APPEND_ONLY_PROBE",
            entity_type="TEST",
            entity_id="probe-delete",
        )
        db.flush()
        row = db.scalar(select(AuditLog).where(AuditLog.entity_id == "probe-delete"))
        assert row is not None

        with pytest.raises(Exception) as exc:
            db.execute(delete(AuditLog).where(AuditLog.id == row.id))
            db.flush()
        assert "append-only" in str(exc.value).lower()
        db.rollback()


@requires_postgres
def test_insert_still_works_and_history_is_preserved():
    """The guard must block tampering without blocking legitimate appends."""
    engine = create_engine(POSTGRES_URL)
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(AuditLog)) or 0
        audit(
            db,
            actor="test",
            role="ADMIN",
            action="APPEND_ONLY_INSERT",
            entity_type="TEST",
            entity_id="probe-insert",
        )
        db.flush()
        after = db.scalar(select(func.count()).select_from(AuditLog)) or 0
        assert after == before + 1
        db.rollback()


@requires_postgres
def test_triggers_are_installed():
    engine = create_engine(POSTGRES_URL)
    with engine.connect() as conn:
        names = set(
            conn.execute(
                text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
            ).scalars()
        )
    assert {"cabqp_audit_logs_no_update", "cabqp_audit_logs_no_delete"} <= names
