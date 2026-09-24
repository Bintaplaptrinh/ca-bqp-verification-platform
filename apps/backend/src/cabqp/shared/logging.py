from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_REDACT_KEYS = {
    "subject_name",
    "subject_code",
    "raw_text",
    "text",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "secret_key",
    "file_content",
    "business_fields",
    "identity_fields",
}


def set_request_id(value: str | None):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()


def _redact(value: Any):
    if isinstance(value, dict):
        return {
            str(k): ("***" if str(k).casefold() in _REDACT_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        extra = getattr(record, "event", None)
        if isinstance(extra, dict):
            payload["event"] = _redact(extra)
        if record.exc_info:
            # Keep exception class/message for operations, never request bodies or auth headers.
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    # Replace arbitrary/basicConfig handlers so JSON logs are consistent in API and worker.
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


def event(logger: logging.Logger, message: str, **fields) -> None:
    logger.info(message, extra={"event": fields})
