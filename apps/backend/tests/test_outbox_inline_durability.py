"""An outbox row is SENT only once delivery is actually durable.

Durability in this platform comes from ``outbox_events``, not from a broker: a row
stays PENDING until the work is handed somewhere that survives a crash, and the
local profile's sweeper re-dispatches whatever it finds still PENDING.

Under Celery, publishing to the broker is that durable point. The inline profile has
no broker, and the dispatcher used to mark the row SENT right after submitting the
task to an in-process thread pool — which is not a handoff at all. A crash between
the submit and the task running left the row reading SENT with the work never done,
so nothing re-picked it and the Case sat at RECEIVED for good.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.shared.db import Base
from cabqp.shared.models import OutboxEvent
from cabqp.workers import tasks


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _event(db: Session) -> OutboxEvent:
    event = OutboxEvent(
        event_type="DOCUMENT_PROCESS_REQUESTED",
        aggregate_type="CASE",
        aggregate_id="case_1",
        payload={"case_id": "case_1", "document_id": "doc_1", "storage_key": "k"},
        status="PENDING",
    )
    db.add(event)
    db.flush()
    return event


def test_inline_dispatch_runs_the_work_before_marking_the_row_sent(db, monkeypatch):
    from cabqp.workers import local_queue

    event = _event(db)
    observed: dict = {}

    def fake_run_task_now(task, *args):
        # What a crash at this instant would leave behind in the database.
        observed["status_during_work"] = db.get(OutboxEvent, event.id).status
        observed["args"] = args
        return {"status": "ok"}

    monkeypatch.setattr(local_queue, "inline_enabled", lambda: True)
    monkeypatch.setattr(local_queue, "run_task_now", fake_run_task_now)
    monkeypatch.setattr(
        local_queue, "enqueue", lambda *a, **k: pytest.fail("inline profile must not fire-and-forget")
    )

    assert tasks._dispatch_event(db, event) is True
    db.commit()

    assert observed["args"] == ("case_1", "doc_1", "k")
    # PENDING while the work is in flight is the whole point: that is the state the
    # sweeper re-dispatches from.
    assert observed["status_during_work"] == "PENDING"
    assert db.get(OutboxEvent, event.id).status == "SENT"


def test_a_permanently_failed_document_is_not_re_queued_forever(db, monkeypatch):
    """process_document owns its own retry budget and terminal branch.

    Once it has exhausted that budget it has already marked the Case FAILED and
    dead-lettered it. Delivery happened, so the row must not go back to PENDING and
    have the sweeper re-run a document that failed for good every 20 seconds.
    """
    from cabqp.workers import local_queue

    event = _event(db)

    def boom(task, *args):
        raise RuntimeError("parse failed for good")

    monkeypatch.setattr(local_queue, "inline_enabled", lambda: True)
    monkeypatch.setattr(local_queue, "run_task_now", boom)

    assert tasks._dispatch_event(db, event) is True
    db.commit()
    assert db.get(OutboxEvent, event.id).status == "SENT"


def test_celery_profile_still_marks_sent_at_publish_time(db, monkeypatch):
    """Publishing to a broker *is* durable, so that path is unchanged."""
    from cabqp.workers import local_queue

    event = _event(db)
    published: list = []

    monkeypatch.setattr(local_queue, "inline_enabled", lambda: False)
    monkeypatch.setattr(local_queue, "enqueue", lambda task, *args: published.append(args))
    monkeypatch.setattr(
        local_queue, "run_task_now", lambda *a, **k: pytest.fail("celery profile must not run inline")
    )

    assert tasks._dispatch_event(db, event) is True
    db.commit()
    assert published == [("case_1", "doc_1", "k")]
    assert db.get(OutboxEvent, event.id).status == "SENT"
