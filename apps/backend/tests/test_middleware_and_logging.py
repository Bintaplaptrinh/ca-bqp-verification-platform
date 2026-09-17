"""Rate limiting and log-redaction regressions.

Both are cross-cutting protections that no other test touches: a limiter that blocks the
first request is as broken as one that never blocks, and structured logs must not carry
subject identities or bearer tokens.
"""
from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager

import pytest

from cabqp.shared.logging import JsonFormatter, event


@pytest.fixture
def captured_logger() -> tuple[logging.Logger, io.StringIO]:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("cabqp.tests.redaction")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, buffer


def _events(buffer: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buffer.getvalue().strip().splitlines() if line]


def test_subject_identity_is_redacted(captured_logger):
    logger, buffer = captured_logger
    event(logger, "case_created", subject_name="Nguyễn Văn A", subject_code="001082946357", unit_id="u1")

    payload = _events(buffer)[0]["event"]
    assert payload["subject_name"] == "***"
    assert payload["subject_code"] == "***"
    # Non-identifying operational context stays readable.
    assert payload["unit_id"] == "u1"
    assert "Nguyễn Văn A" not in buffer.getvalue()
    assert "001082946357" not in buffer.getvalue()


def test_credentials_are_redacted(captured_logger):
    logger, buffer = captured_logger
    event(logger, "auth_attempt", authorization="Bearer eyJhbGciOi.payload.sig", token="tok_abc", password="p")

    payload = _events(buffer)[0]["event"]
    assert payload == {"authorization": "***", "token": "***", "password": "***"}
    assert "eyJhbGciOi" not in buffer.getvalue()


def test_redaction_applies_to_nested_structures(captured_logger):
    """Payloads are often nested dicts; redaction must not stop at the top level."""
    logger, buffer = captured_logger
    event(logger, "bulk_row", payload={"inner": {"subject_name": "Trần Thị B", "raw_text": "nội dung"}})

    assert "Trần Thị B" not in buffer.getvalue()
    assert "nội dung" not in buffer.getvalue()


def test_raw_document_text_is_never_logged(captured_logger):
    logger, buffer = captured_logger
    event(logger, "parsed", raw_text="toàn bộ hồ sơ", text="trích đoạn", business_fields={"a": 1})

    payload = _events(buffer)[0]["event"]
    assert payload["raw_text"] == "***"
    assert payload["text"] == "***"
    assert payload["business_fields"] == "***"


@contextmanager
def _limited_client(per_minute: int, *, fail_open: bool = True):
    """Mount the limiter on a throwaway app.

    `cabqp.main.app` is built at import time and RateLimitMiddleware captures its
    settings in __init__, so the shared app keeps whatever configuration the first
    import saw. Building a fresh app here keeps the test independent of import order
    and of whether Redis happens to be reachable — without Redis the middleware uses
    its in-memory fallback, which enforces the same boundary.
    """
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cabqp.shared.middleware import RateLimitMiddleware
    from cabqp.shared.settings import get_settings

    previous = {
        key: os.environ.get(key)
        for key in ("RATE_LIMIT_ENABLED", "RATE_LIMIT_PER_MINUTE", "RATE_LIMIT_FAIL_OPEN", "REDIS_URL")
    }
    os.environ["RATE_LIMIT_ENABLED"] = "true"
    os.environ["RATE_LIMIT_PER_MINUTE"] = str(per_minute)
    os.environ["RATE_LIMIT_FAIL_OPEN"] = "true" if fail_open else "false"
    # A dedicated database keeps limiter counters out of the application's Redis data.
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/15"
    get_settings.cache_clear()
    try:
        app = FastAPI()

        @app.get("/api/v1/probe")
        def probe() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/health/live")
        def live() -> dict[str, bool]:
            return {"ok": True}

        app.add_middleware(RateLimitMiddleware)
        # Starlette builds the middleware stack lazily, on the first request rather than
        # at add_middleware(), so RateLimitMiddleware.__init__ reads the environment then.
        # The overrides therefore have to stay in place for the client's whole lifetime.
        yield TestClient(app)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def test_rate_limiter_allows_requests_up_to_the_limit_then_blocks(monkeypatch):
    """The first request must succeed: an off-by-one here silently denies real traffic.

    The Redis counter is deliberately disabled so the assertion depends only on the
    limiter's own arithmetic. Leaving Redis in the loop made this test depend on whether
    the server was reachable from the test event loop and on counters left in the shared
    minute window by other runs — it would pass or fail for reasons unrelated to the code.
    """
    from cabqp.shared.middleware import RateLimitMiddleware

    async def _redis_unavailable(self, key: str, window: int) -> int:
        raise RuntimeError("redis disabled for this test")

    monkeypatch.setattr(RateLimitMiddleware, "_increment", _redis_unavailable)

    limit = 5
    with _limited_client(limit) as client:
        statuses = [client.get("/api/v1/probe").status_code for _ in range(limit + 3)]

    assert 429 not in statuses[:limit], f"limiter blocked before the limit: {statuses}"
    assert statuses[limit:] == [429] * 3, statuses


def test_rate_limiter_fails_closed_when_configured(monkeypatch):
    """With fail-open disabled, a limiter backend outage must reject rather than admit."""
    from cabqp.shared.middleware import RateLimitMiddleware

    async def _redis_unavailable(self, key: str, window: int) -> int:
        raise RuntimeError("redis disabled for this test")

    monkeypatch.setattr(RateLimitMiddleware, "_increment", _redis_unavailable)

    with _limited_client(5, fail_open=False) as client:
        response = client.get("/api/v1/probe")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RATE_LIMIT_BACKEND_UNAVAILABLE"


def test_health_probes_are_exempt_from_rate_limiting():
    """Liveness probes must never be throttled, or orchestrators will kill the pod."""
    with _limited_client(1) as client:
        statuses = [client.get("/health/live").status_code for _ in range(6)]

    assert statuses == [200] * 6
