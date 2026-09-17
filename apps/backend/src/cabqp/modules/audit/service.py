from sqlalchemy.orm import Session

from cabqp.shared.models import AuditLog


def audit(db: Session, *, actor: str, role: str | None, action: str, entity_type: str, entity_id: str, metadata: dict | None = None):
    db.add(AuditLog(actor=actor, role=role, action=action, entity_type=entity_type, entity_id=entity_id, metadata_json=metadata or {}))
