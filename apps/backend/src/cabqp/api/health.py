from __future__ import annotations

import socket

from fastapi import APIRouter, Response
from sqlalchemy import text

from cabqp.modules.document_intelligence.storage import ObjectStorage
from cabqp.shared.db import SessionLocal
from cabqp.shared.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    # Backward-compatible liveness endpoint.
    return {"status": "ok"}


@router.get("/health/live")
def live():
    return {"status": "alive"}


@router.get("/health/ready")
def ready(response: Response):
    s = get_settings()
    checks: dict[str, str] = {}
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "failed"
    finally:
        db.close()

    # Only check dependencies this profile actually relies on. Reporting a
    # missing Redis as "not ready" in the local profile would be a false alarm:
    # nothing in that profile talks to it.
    if s.effective_queue_backend == "celery":
        try:
            import redis

            client = redis.from_url(s.redis_url, socket_connect_timeout=1, socket_timeout=1)
            checks["redis"] = "ok" if client.ping() else "failed"
            client.close()
        except Exception:
            checks["redis"] = "failed"
    else:
        checks["task_queue"] = "inline"

    try:
        ObjectStorage().ensure_bucket()
        checks["object_storage"] = "ok"
    except Exception:
        checks["object_storage"] = "failed"

    # Accounts live in this platform's own database, so identity readiness is
    # the presence of an administrator, not an external discovery document.
    db = SessionLocal()
    try:
        from cabqp.shared.models import AppUser

        has_admin = db.query(AppUser).filter(AppUser.is_admin.is_(True)).first() is not None
        checks["identity"] = "ok" if has_admin else "no_admin_account"
    except Exception:
        checks["identity"] = "failed"
    finally:
        db.close()

    if s.antimalware_enabled and (s.antimalware_required or s.is_production):
        try:
            with socket.create_connection((s.clamav_host, s.clamav_port), timeout=1.0):
                checks["antimalware"] = "ok"
        except Exception:
            checks["antimalware"] = "failed"

    informational = {"task_queue"}
    if any(value != "ok" for key, value in checks.items() if key not in informational):
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}
