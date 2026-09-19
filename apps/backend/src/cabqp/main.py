from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from cabqp.api import (
    admin_person_registry,
    admin_registry,
    admin_users,
    audit,
    auth,
    bulk,
    cases,
    health,
    lookup,
    reviews,
)
from cabqp.shared.logging import configure_logging
from cabqp.shared.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from cabqp.shared.settings import get_settings

configure_logging()
logger = logging.getLogger(__name__)
s = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """In the local profile the API process is also the task runner.

    The sweeper is what makes that durable: an outbox row committed by an upload
    that never got dispatched — because the process died between the commit and
    the hand-off — is picked up on the next pass rather than stranding the Case
    at RECEIVED forever.
    """
    queue = None
    if s.effective_queue_backend == "inline":
        from cabqp.workers.local_queue import get_queue

        queue = get_queue()
        queue.start_sweeper()
        logger.info(
            "local_task_runner_started",
            extra={"event": {"storage": s.effective_storage_backend, "queue": "inline"}},
        )
    try:
        yield
    finally:
        if queue is not None:
            queue.shutdown()


app = FastAPI(title=s.app_name, version="1.0.0", lifespan=lifespan)

origins = [x.strip() for x in s.cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)
# Starlette runs middleware in reverse registration order, so the last one added
# is the outermost. Security headers go outermost on purpose: a 429 from the rate
# limiter and a 500 from the exception handler carry them too.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health.router)
for router in [
    auth.router,
    lookup.router,
    cases.router,
    bulk.router,
    reviews.router,
    admin_registry.router,
    admin_person_registry.router,
    admin_users.router,
    audit.router,
]:
    app.include_router(router, prefix=s.api_prefix)


if s.metrics_enabled:
    @app.get("/metrics", include_in_schema=False)
    def metrics():
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception(
        "unhandled_request_exception",
        extra={"event": {"path": request.url.path, "error_type": type(exc).__name__}},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Unexpected server error",
                "path": request.url.path,
            }
        },
    )
