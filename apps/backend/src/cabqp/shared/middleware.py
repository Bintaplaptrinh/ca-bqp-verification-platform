from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from ipaddress import ip_address
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


#: Credential endpoints. These get a second, much tighter budget that counts
#: *rejected* attempts only: the account lockout in modules/auth/service.py
#: protects one account at a time, and does nothing against a sprayer walking a
#: username list or guessing names that do not exist. Counting failures rather
#: than calls means a person who signs in normally never spends the budget.
#: `/auth/otp/verify` belongs here for the same reason `/auth/login` does: it is
#: a credential check that answers 401, so failures are charged. `/auth/otp/request`
#: deliberately does *not* — it answers 200 to everyone by design, so there is
#: no failure to count. What bounds it is the per-route and per-address budgets
#: every request pays, plus the durable per-account/per-address issuance caps in
#: modules/auth/otp.py.
_AUTH_PATHS = ("/auth/login", "/auth/change-password", "/auth/otp/verify")


def _is_auth_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _AUTH_PATHS)


def _peer_is_trusted(peer: str, trusted_proxies) -> bool:
    if not peer or not trusted_proxies:
        return False
    try:
        address = ip_address(peer)
    except ValueError:
        # A peer that is not an address cannot be matched against a network, and
        # "unparseable" must never read as "trusted".
        return False
    return any(address in net for net in trusted_proxies)


def client_address(request: Request, trusted_proxies) -> str:
    """The address to hold responsible for this request.

    X-Forwarded-For is data the client sent, not a fact, so it is honoured only
    when the socket peer is a proxy we deployed (a WAF, load balancer or the
    Nginx container). Trusting it unconditionally let any caller defeat the rate
    limiter outright by putting a fresh random address in the header on every
    request.
    """
    peer = request.client.host if request.client else ""
    if _peer_is_trusted(peer, trusted_proxies):
        forwarded = request.headers.get("x-forwarded-for", "")
        # The left-most entry is the original client; entries to its right were
        # appended by each hop. Only the hop we trust may name the client.
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer or "unknown"

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

    async def _count(self, bucket: str, window: int) -> int | None:
        """Increment one bucket. None means the backend is down and we fail open."""
        try:
            return await self._increment(f"cabqp:ratelimit:{window}:{bucket}", window)
        except Exception as exc:
            logger.warning(
                "rate_limit_redis_unavailable",
                extra={"event": {"error_type": type(exc).__name__}},
            )
            if not self.settings.rate_limit_fail_open:
                return None
            return await self._fallback_increment(bucket, window)

    async def _peek(self, bucket: str, window: int) -> int:
        """Read a bucket without spending it. Unreadable counts as empty."""
        try:
            client = await self._redis_client()
            value = await client.get(f"cabqp:ratelimit:{window}:{bucket}")
            return int(value or 0)
        except Exception:
            async with self._fallback_lock:
                return self._fallback.get((bucket, window), 0)

    async def dispatch(self, request: Request, call_next):
        if not self.settings.rate_limit_enabled:
            return await call_next(request)
        if request.url.path in {"/health", "/health/live", "/health/ready", "/metrics", "/openapi.json"} or request.url.path.startswith("/docs"):
            return await call_next(request)

        client_ip = client_address(request, self.settings.trusted_proxies)
        path = request.url.path
        window = int(time.time() // 60)

        # Three budgets, all of which must hold: the route shape this call hits,
        # everything this address does across routes (so spraying many paths is
        # not a way around the first), and a much tighter one on the credential
        # endpoints. The narrowest applicable limit is the one reported.
        buckets: list[tuple[str, int]] = [
            (f"{client_ip}:{_rate_limit_route_key(path)}", self.settings.rate_limit_per_minute),
            (f"{client_ip}:__all__", self.settings.rate_limit_ip_per_minute),
        ]

        auth_bucket = f"{client_ip}:__auth_fail__" if _is_auth_path(path) else None
        auth_limit = self.settings.rate_limit_auth_per_minute
        if auth_bucket and await self._peek(auth_bucket, window) >= auth_limit:
            logger.warning(
                "credential_attempts_throttled",
                extra={"event": {"path": path, "limit": auth_limit}},
            )
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60", "X-RateLimit-Limit": str(auth_limit)},
                content={
                    "error": {
                        "code": "TOO_MANY_CREDENTIAL_ATTEMPTS",
                        "message": "Quá nhiều lần đăng nhập không thành công. Vui lòng thử lại sau một phút.",
                    }
                },
            )

        reported_limit = min(limit for _, limit in buckets)
        remaining = None
        for bucket, limit in buckets:
            count = await self._count(bucket, window)
            if count is None:
                return JSONResponse(
                    status_code=503,
                    content={"error": {"code": "RATE_LIMIT_BACKEND_UNAVAILABLE", "message": "Rate limiting backend unavailable"}},
                )
            if count > limit:
                logger.warning(
                    "rate_limited",
                    extra={"event": {"path": path, "bucket": bucket.split(":")[-1], "limit": limit}},
                )
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "60", "X-RateLimit-Limit": str(limit)},
                    content={"error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
                )
            left = max(0, limit - count)
            remaining = left if remaining is None else min(remaining, left)

        response = await call_next(request)
        if auth_bucket and response.status_code in (401, 403):
            # Only rejected credentials are charged, so an operator signing in
            # and working normally never approaches this limit while a sprayer
            # hits it within seconds.
            await self._count(auth_bucket, window)
        response.headers["X-RateLimit-Limit"] = str(reported_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining if remaining is not None else 0)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Browser-side hardening applied to every API response.

    The API answers JSON and nothing else, so the policy can be maximally strict:
    no document may frame it (clickjacking), the browser may not re-interpret a
    response as a type it was not served as (MIME sniffing), and no origin is
    allowed as a source for anything the page might try to load.

    The SPA is served by Nginx, not by this process, and carries its own copy of
    these headers in apps/web/nginx.conf. Both are needed: the two are served by
    different servers.
    """

    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        frame_ancestors = (self.settings.frame_ancestors or "'none'").strip()
        self._csp = (
            "default-src 'none'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            f"frame-ancestors {frame_ancestors}"
        )
        # X-Frame-Options is the older, coarser control. CSP frame-ancestors
        # supersedes it in current browsers, but it is kept for the ones that
        # only understand the header, and costs nothing.
        self._deny_frames = frame_ancestors == "'none'"

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not self.settings.security_headers_enabled:
            return response
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Content-Security-Policy", self._csp)
        if self._deny_frames:
            headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        headers.setdefault("Cache-Control", "no-store")
        # HSTS is only meaningful over TLS, and asserting it on a plain-HTTP POC
        # would pin a scheme the deployment does not serve yet.
        if self.settings.is_production and request.url.scheme == "https":
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={self.settings.hsts_max_age_seconds}; includeSubDomains",
            )
        return response
