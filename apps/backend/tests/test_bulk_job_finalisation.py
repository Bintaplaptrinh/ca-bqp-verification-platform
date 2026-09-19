"""A spreadsheet import must reach a terminal status once its rows are done.

Row tasks run concurrently and each one recomputes the whole job's counters from
its rows, so `refresh_job_counts` is a read-modify-write over shared state. It
used to run unsynchronised: the last writer stored an aggregate taken before its
peer committed, leaving a job whose rows were all terminal stuck at PROCESSING
with a processed count short of its total. Nothing finalises such a job in the
local profile — there is no Beat running `reconcile_bulk_jobs` — so the client
polls forever and the import never shows a result.
"""

from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from cabqp.modules.bulk.service import refresh_job_counts
from cabqp.shared.models import Base, BulkIngestJob, BulkIngestRow

POSTGRES_URL = os.environ.get("DATABASE_URL", "")
requires_postgres = pytest.mark.skipif(
    "postgresql" not in POSTGRES_URL,
    reason="the lost-update race needs real row locking, which SQLite does not provide",
)


def _job_with_rows(db: Session, statuses: list[str]) -> BulkIngestJob:
    job = BulkIngestJob(
        file_name="danh_sach.xlsx",
        file_sha256=os.urandom(16).hex(),
        status="PROCESSING",
        created_by="tester",
        total_rows=len(statuses),
    )
    db.add(job)
    db.flush()
    for index, status in enumerate(statuses, start=2):
        db.add(
            BulkIngestRow(
                job_id=job.id,
                row_index=index,
                status=status,
                raw_payload_json={},
                row_hash=f"{job.id}-{index}",
            )
        )
    db.flush()
    return job


@pytest.fixture()
def sqlite_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bulk.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_all_rows_succeeded_completes_the_job(sqlite_session):
    job = _job_with_rows(sqlite_session, ["SUCCEEDED", "SUCCEEDED", "SUCCEEDED"])
    refresh_job_counts(sqlite_session, job)
    assert job.status == "COMPLETED"
    assert (job.processed, job.succeeded) == (3, 3)


def test_a_failed_row_still_reaches_a_terminal_status(sqlite_session):
    """A row that failed validation is terminal, not a reason to stay PROCESSING."""
    job = _job_with_rows(sqlite_session, ["SUCCEEDED", "FAILED", "SUCCEEDED"])
    refresh_job_counts(sqlite_session, job)
    assert job.status == "COMPLETED_WITH_ERRORS"
    assert (job.processed, job.succeeded, job.failed) == (3, 2, 1)
    assert job.processed == job.total_rows


def test_a_pending_row_keeps_the_job_processing(sqlite_session):
    job = _job_with_rows(sqlite_session, ["SUCCEEDED", "PENDING"])
    refresh_job_counts(sqlite_session, job)
    assert job.status == "PROCESSING"


@requires_postgres
def test_concurrent_row_completions_do_not_lose_each_other():
    """Two row tasks finishing at once must still leave the job finalised.

    Each thread mimics one `process_bulk_row_task`: mark its own row terminal,
    recompute the job, commit. Whichever commits last has to observe the other's
    row, so the job ends COMPLETED with every row counted.
    """
    engine = create_engine(POSTGRES_URL)
    SessionFactory = sessionmaker(bind=engine)

    with Session(engine) as setup:
        job = _job_with_rows(setup, ["PENDING", "PENDING"])
        setup.commit()
        job_id = job.id
        row_ids = [
            r.id
            for r in setup.scalars(
                select(BulkIngestRow).where(BulkIngestRow.job_id == job_id).order_by(BulkIngestRow.row_index)
            )
        ]

    start = threading.Barrier(len(row_ids))

    def finish(row_id: str):
        db = SessionFactory()
        try:
            row = db.scalar(select(BulkIngestRow).where(BulkIngestRow.id == row_id).with_for_update())
            row.status = "SUCCEEDED"
            db.flush()
            # Both threads reach the counter refresh at the same moment, which is
            # exactly when the unsynchronised version lost one of the two rows.
            start.wait(timeout=10)
            refresh_job_counts(db, db.get(BulkIngestJob, job_id))
            db.commit()
        finally:
            db.close()

    threads = [threading.Thread(target=finish, args=(row_id,)) for row_id in row_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    with Session(engine) as check:
        final = check.get(BulkIngestJob, job_id)
        assert final.status == "COMPLETED", f"job left at {final.status}"
        assert final.succeeded == len(row_ids)
        assert final.processed == final.total_rows
        check.execute(BulkIngestRow.__table__.delete().where(BulkIngestRow.job_id == job_id))
        check.execute(BulkIngestJob.__table__.delete().where(BulkIngestJob.id == job_id))
        check.commit()
