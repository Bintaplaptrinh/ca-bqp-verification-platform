from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_seconds: float = 30.0

    def __post_init__(self) -> None:
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def before_call(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            if time.monotonic() - self._opened_at >= self.recovery_seconds:
                # half-open: allow one caller to probe by resetting the open timestamp.
                self._opened_at = None
                self._failures = max(self.failure_threshold - 1, 0)
                return
            raise CircuitOpenError("External dependency circuit is open")

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()

    def call(self, fn: Callable[[], T]) -> T:
        self.before_call()
        try:
            value = fn()
        except Exception:
            self.failure()
            raise
        self.success()
        return value


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_seconds: float = 0.15,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    attempts = max(1, attempts)
    last: BaseException | None = None
    for idx in range(attempts):
        try:
            return fn()
        except retry_exceptions as exc:
            last = exc
            if idx + 1 >= attempts:
                raise
            delay = base_seconds * (2**idx)
            time.sleep(delay + random.uniform(0.0, max(delay * 0.15, 0.001)))
    assert last is not None
    raise last
