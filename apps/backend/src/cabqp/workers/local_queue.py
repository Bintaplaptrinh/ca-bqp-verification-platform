"""In-process task runner for the local deployment profile.

The platform's durability comes from the ``outbox_events`` table, not from the
broker: an upload commits its Document and its outbox row in one transaction, and
the row is only marked SENT once the work is durably delivered. That design does
not actually require Celery, so the local profile drops Redis entirely and runs
the same task functions on a small thread pool, with a sweeper that re-picks any
row a crash left PENDING.

What "durably delivered" means differs per profile, and the difference matters:
publishing to a broker is itself durable, submitting to this thread pool is not.
:func:`tasks._dispatch_event` therefore *runs* the document task inline before
marking the row SENT, rather than marking it at submit time — see its docstring.
Submitting work here is otherwise fire-and-forget by design, so nothing that must
survive a crash may depend on :meth:`LocalTaskQueue.submit` alone.

Retry semantics are reproduced rather than approximated: each task is invoked
through :class:`_InlineContext`, which supplies the ``self.request.retries`` and
``self.max_retries`` the task body reads, and turns ``self.retry(...)`` into a
signal this runner acts on. A task's own terminal-failure branch — marking the
Case FAILED and dead-lettering it — therefore runs on the final attempt exactly
as it would under a worker.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)

RETRY_BASE_SECONDS = 2.0
RETRY_MAX_SECONDS = 60.0
SWEEP_INTERVAL_SECONDS = 20.0


class InlineRetry(Exception):
    """Raised in place of Celery's ``Retry`` when a task asks to be retried."""

    def __init__(self, exc: BaseException | None = None, countdown: float | None = None):
        super().__init__(str(exc) if exc else "retry")
        self.exc = exc
        self.countdown = countdown


@dataclass
class _InlineRequest:
    retries: int = 0
    called_directly: bool = False
    id: str = "inline"


class _InlineContext:
    """Stands in for the Celery task instance a bound task receives as ``self``."""

    def __init__(self, retries: int, max_retries: int):
        self.request = _InlineRequest(retries=retries)
        self.max_retries = max_retries
        self.name = "inline"

    def retry(self, exc: BaseException | None = None, countdown: float | None = None, **_):
        raise InlineRetry(exc, countdown)


def _unbound(task):
    """Return ``(fn, needs_context)`` for a Celery task.

    A ``bind=True`` task's ``run`` is bound to the task instance, so the raw
    function is reached through ``__func__`` and expects ``self`` first. A plain
    task takes only its declared arguments.
    """
    run = task.run
    inner = getattr(run, "__func__", None)
    if inner is not None:
        return inner, True
    return run, False


def run_task_now(task, *args) -> object:
    """Execute ``task`` synchronously, honouring its declared retry budget.

    Returns the task's result, or re-raises once the budget is exhausted. The
    caller sees the same outcome a Celery worker would produce.
    """
    fn, needs_context = _unbound(task)
    max_retries = int(getattr(task, "max_retries", 0) or 0)
    attempt = 0
    while True:
        context = _InlineContext(retries=attempt, max_retries=max_retries)
        try:
            return fn(context, *args) if needs_context else fn(*args)
        except InlineRetry as signal:
            if attempt >= max_retries:
                # The task asked for one retry too many. Surface the original
                # error rather than the signal wrapping it.
                raise (signal.exc or signal) from None
            delay = signal.countdown
            if delay is None:
                delay = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2**attempt))
            logger.info(
                "inline_task_retry",
                extra={"event": {"task": getattr(task, "name", "?"), "attempt": attempt + 1, "delay_s": delay}},
            )
            time.sleep(delay)
            attempt += 1


class LocalTaskQueue:
    """Bounded background execution plus a durable-outbox sweeper."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cabqp-task")
        self._sweeper: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def submit(self, task, *args) -> None:
        """Queue a task without waiting for it.

        Fire-and-forget: the task is not durable until whatever it does records its
        own outcome. Callers that need a crash to be recoverable must go through the
        outbox, not through this method.
        """

        def runner():
            try:
                run_task_now(task, *args)
            except Exception:
                logger.exception(
                    "inline_task_failed",
                    extra={"event": {"task": getattr(task, "name", "?")}},
                )

        self._executor.submit(runner)

    def start_sweeper(self) -> None:
        """Begin re-dispatching outbox rows a previous run left PENDING."""
        with self._lock:
            if self._sweeper is not None and self._sweeper.is_alive():
                return
            self._stop.clear()
            self._sweeper = threading.Thread(
                target=self._sweep_loop, name="cabqp-outbox-sweeper", daemon=True
            )
            self._sweeper.start()

    def _sweep_loop(self) -> None:
        from cabqp.workers.tasks import dispatch_pending_outbox

        while not self._stop.wait(SWEEP_INTERVAL_SECONDS):
            try:
                run_task_now(dispatch_pending_outbox, 100)
            except Exception:
                logger.exception("inline_outbox_sweep_failed")

    def shutdown(self, wait: bool = False) -> None:
        self._stop.set()
        self._executor.shutdown(wait=wait, cancel_futures=not wait)


_QUEUE: LocalTaskQueue | None = None
_QUEUE_LOCK = threading.Lock()


def get_queue() -> LocalTaskQueue:
    global _QUEUE
    with _QUEUE_LOCK:
        if _QUEUE is None:
            _QUEUE = LocalTaskQueue()
        return _QUEUE


def inline_enabled() -> bool:
    return get_settings().effective_queue_backend == "inline"


def enqueue(task, *args) -> str:
    """Hand a task to the configured backend.

    Returns the backend that accepted it, so callers can report queue status
    without knowing which profile they are running under.
    """
    if inline_enabled():
        get_queue().submit(task, *args)
        return "inline"
    task.apply_async(args=list(args))
    return "celery"
