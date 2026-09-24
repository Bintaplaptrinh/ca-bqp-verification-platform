from celery import Celery

from cabqp.shared.logging import configure_logging
from cabqp.shared.settings import get_settings

configure_logging()
s = get_settings()
# `include` is required: the worker is started against this module, so without it the
# task module is never imported and every dispatched message is discarded as
# NotRegistered instead of being executed.
celery_app = Celery(
    "cabqp",
    broker=s.redis_url,
    backend=s.redis_url,
    include=["cabqp.workers.tasks"],
)
celery_app.conf.update(
    task_routes={
        "cabqp.workers.tasks.process_document": {"queue": "documents"},
        "cabqp.workers.tasks.dispatch_outbox_event": {"queue": "outbox"},
        "cabqp.workers.tasks.dispatch_pending_outbox": {"queue": "outbox"},
        "cabqp.workers.tasks.process_bulk_job": {"queue": "batch"},
        "cabqp.workers.tasks.process_bulk_row": {"queue": "batch"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_annotations={
        "cabqp.workers.tasks.process_document": {
            "soft_time_limit": s.document_soft_timeout_seconds,
        }
    },
    beat_schedule={
        "dispatch-durable-outbox": {
            "task": "cabqp.workers.tasks.dispatch_pending_outbox",
            "schedule": 30.0,
        }
    },
    timezone="UTC",
)


# Periodic DB-derived finalizer for batch jobs; no chord/group state is used.
celery_app.conf.beat_schedule = {**(celery_app.conf.beat_schedule or {}), "reconcile-bulk-jobs": {"task": "cabqp.workers.tasks.reconcile_bulk_jobs", "schedule": 30.0}}
