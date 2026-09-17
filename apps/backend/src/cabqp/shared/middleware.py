from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from cabqp.shared.logging import reset_request_id, set_request_id
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)

# Collapses path segments that look like an entity id (e.g. "unit_3f9c...", a bare
# uuid, or a numeric id) so the rate limiter buckets by route shape, not by every
# distinct resource id that appears in it.
_ID_SEGMENT = re.compile(r"^[0-9a-fA-F-]{8,}$|^[A-Za-z][A-Za-z0-9]*_[0-9a-fA-F]{8,}$|^\d+$")


def _rate_limit_route_key(path: str) -> str:
    segments = [seg if not _ID_SEGMENT.match(seg) else ":id" for seg in path.split("/")]
    return "/".join(segments)

try:
    from prometheus_client import Counter, Histogram

    HTTP_REQUESTS = Counter(
        "cabqp_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    HTTP_LATENCY = Histogram(
        "cabqp_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
    )
except Exception:  # pragma: no cover - metrics dependency may be intentionally omitted
    HTTP_REQUESTS = None
    HTTP_LATENCY = None


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        token = set_request_id(request_id)
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = time.monotonic() - started
            path = request.url.path
            if HTTP_REQUESTS is not None:
                HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
                HTTP_LATENCY.labels(request.method, path).observe(elapsed)
            logger.info(
                "http_request",
                extra={
                    "event": {
                        "method": request.method,
                        "path": path,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                    }
                },
            )
            reset_request_id(token)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed fixed-window limiter with a bounded in-memory fallback.

    Redis is the authoritative limiter in production. The fallback exists so a
    transient Redis outage does not turn every request into a hard outage when
    RATE_LIMIT_FAIL_OPEN=true; production can set it false to fail closed.
    """

    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self._redis = None
        self._fallback: dict[tuple[str, int], int] = defaultdict(int)
        self._fallback_lock = asyncio.Lock()

    async def _redis_client(self):
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(self.settings.redis_url, decode_responses=True)
        return self._redis

    async def _increment(self, key: str, window: int) -> int:
        client = await self._redis_client()
        pipe = client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, 70)
        result = await pipe.execute()
        return int(result[0])

    async def _fallback_increment(self, client_key: str, window: int) -> int:
        async with self._fallback_lock:
            # Purge old minute buckets opportunistically.
            stale = [k for k in self._fallback if k[1] < window - 1]
            for k in stale:
                self._fallback.pop(k, None)
            bucket = (client_key, window)
            self._fallback[bucket] += 1
            return self._fallback[bucket]

    async def dispatch(self, request: Request, call_next):
        if not self.settings.rate_limit_enabled:
            return await call_next(request)
        if request.url.path in {"/health", "/health/live", "/health/ready", "/metrics", "/openapi.json"} or request.url.path.startswith("/docs"):
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        client_ip = forwarded or (request.client.host if request.client else "unknown")
        client_key = f"{client_ip}:{_rate_limit_route_key(request.url.path)}"
        window = int(time.time() // 60)
        redis_key = f"cabqp:ratelimit:{window}:{client_key}"
        try:
            count = await self._increment(redis_key, window)
        except Exception as exc:
            logger.warning(
                "rate_limit_redis_unavailable",
                extra={"event": {"error_type": type(exc).__name__}},
            )
            if not self.settings.rate_limit_fail_open:
                return JSONResponse(
                    status_code=503,
                    content={"error": {"code": "RATE_LIMIT_BACKEND_UNAVAILABLE", "message": "Rate limiting backend unavailable"}},
                )
            count = await self._fallback_increment(client_key, window)

        limit = self.settings.rate_limit_per_minute
        if count > limit:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60", "X-RateLimit-Limit": str(limit)},
                content={"error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response
