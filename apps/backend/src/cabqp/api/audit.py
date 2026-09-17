from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.shared.db import get_db
from cabqp.shared.models import AuditLog

router = APIRouter(prefix="/admin/audit", tags=["audit"])


@router.get("")
def list_audit(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_perms(perms.AUDIT_VIEW)),
):
    rows = list(
        db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit))
    )
    return [
        {
            "id": x.id,
            "actor": x.actor,
            "role": x.role,
            "action": x.action,
            "entity_type": x.entity_type,
            "entity_id": x.entity_id,
            "metadata": x.metadata_json,
            "timestamp": x.timestamp,
        }
        for x in rows
    ]
