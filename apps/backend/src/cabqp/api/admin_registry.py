from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.registry.service import RegistryService
from cabqp.shared.db import get_db
from cabqp.shared.enums import QAStatus
from cabqp.shared.models import RegistryCandidate, RegistryVersion, Unit, UnitCode, UnitName
from cabqp.shared.schemas import (
    AliasCreate,
    AliasQADecision,
    CandidateDecision,
    RegistryPublish,
    RegistryRollback,
    RegistryVersionAction,
    RegistryVersionCreate,
    UnitCodeCreate,
    UnitCodeQADecision,
    UnitCreate,
    UnitQADecision,
    UnitUpdate,
)

router = APIRouter(prefix="/admin/registry", tags=["registry-admin"])
ADMIN = Depends(require_perms(perms.REGISTRY_ADMIN))


def _svc(db: Session, p: Principal) -> RegistryService:
    return RegistryService(db, actor=p.username)


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Registry change conflicts with an existing record") from exc


@router.get("/units")
def units(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    qa_status: QAStatus | None = None,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    q = select(Unit)
    if qa_status:
        q = q.where(Unit.qa_status == qa_status.value)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(Unit.canonical_name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": u.id,
                "canonical_name": u.canonical_name,
                "organization_type": u.organization_type,
                "qa_status": u.qa_status,
                "coverage_group": u.coverage_group,
                "active": u.active,
                "source_id": u.source_id,
            }
            for u in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/units/{unit_id}")
def unit_detail(
    unit_id: str,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    aliases = list(db.scalars(select(UnitName).where(UnitName.unit_id == unit_id).order_by(UnitName.name)))
    codes = list(db.scalars(select(UnitCode).where(UnitCode.unit_id == unit_id).order_by(UnitCode.code)))
    return {
        "unit": {
            "id": unit.id,
            "canonical_name": unit.canonical_name,
            "organization_type": unit.organization_type,
            "unit_level": unit.unit_level,
            "coverage_group": unit.coverage_group,
            "parent_unit_id": unit.parent_unit_id,
            "qa_status": unit.qa_status,
            "active": unit.active,
            "source_id": unit.source_id,
            "valid_from": unit.valid_from,
            "valid_to": unit.valid_to,
        },
        "aliases": [
            {
                "id": x.id, "unit_id": x.unit_id, "name": x.name, "name_type": x.name_type,
                "qa_status": x.qa_status, "source_id": x.source_id, "valid_from": x.valid_from,
                "valid_to": x.valid_to, "approved_by": x.approved_by, "approved_at": x.approved_at,
            } for x in aliases
        ],
        "codes": [
            {
                "id": x.id, "unit_id": x.unit_id, "code": x.code, "code_type": x.code_type,
                "namespace": x.namespace, "qa_status": x.qa_status, "source_id": x.source_id,
                "valid_from": x.valid_from, "valid_to": x.valid_to, "approved_by": x.approved_by,
                "approved_at": x.approved_at,
            } for x in codes
        ],
    }


@router.post("/units")
def create_unit(
    body: UnitCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    unit = _svc(db, p).create_unit(body)
    _commit(db)
    return {"id": unit.id, "qa_status": unit.qa_status}


@router.patch("/units/{unit_id}")
def update_unit(
    unit_id: str,
    body: UnitUpdate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    _svc(db, p).update_unit(unit, body)
    _commit(db)
    return {"id": unit.id}


@router.post("/units/{unit_id}/qa")
def unit_qa(
    unit_id: str,
    body: UnitQADecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    rv = _svc(db, p).decide_unit_qa(unit, body)
    _commit(db)
    return {"id": unit.id, "qa_status": unit.qa_status, "draft_version": rv.version if rv else None}


@router.post("/units/{unit_id}/aliases")
def add_alias(
    unit_id: str,
    body: AliasCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    alias = _svc(db, p).create_alias(unit, body)
    _commit(db)
    return {"id": alias.id, "qa_status": alias.qa_status}


@router.post("/aliases/{alias_id}/qa")
def alias_qa(
    alias_id: str,
    body: AliasQADecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    alias = db.get(UnitName, alias_id)
    if not alias:
        raise HTTPException(404, "Alias not found")
    rv = _svc(db, p).decide_alias_qa(alias, body)
    _commit(db)
    return {"id": alias.id, "qa_status": alias.qa_status, "draft_version": rv.version if rv else None}


@router.post("/units/{unit_id}/codes")
def add_code(
    unit_id: str,
    body: UnitCodeCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    code = _svc(db, p).create_code(unit, body)
    _commit(db)
    return {"id": code.id, "qa_status": code.qa_status}


@router.post("/codes/{code_id}/qa")
def code_qa(
    code_id: str,
    body: UnitCodeQADecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    code = db.get(UnitCode, code_id)
    if not code:
        raise HTTPException(404, "Unit code not found")
    rv = _svc(db, p).decide_code_qa(code, body)
    _commit(db)
    return {"id": code.id, "qa_status": code.qa_status, "draft_version": rv.version if rv else None}


@router.get("/candidates")
def candidates(
    status: QAStatus = QAStatus.PENDING_QA,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    q = select(RegistryCandidate).where(RegistryCandidate.status == status.value)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(RegistryCandidate.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": x.id,
                "raw_name": x.raw_name,
                "proposed_name": x.proposed_name,
                "organization_type": x.organization_type,
                "status": x.status,
                "evidence": x.evidence,
                "created_at": x.created_at,
            }
            for x in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/candidates/{candidate_id}/decision")
def candidate_decision(
    candidate_id: str,
    body: CandidateDecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    candidate = db.get(RegistryCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    candidate, unit, rv = _svc(db, p).decide_candidate(candidate, body)
    _commit(db)
    return {
        "id": candidate.id,
        "status": candidate.status,
        "unit_id": unit.id if unit else None,
        "draft_version": rv.version if rv else None,
    }


@router.get("/versions")
def versions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    q = select(RegistryVersion)
    total = db.scalar(select(func.count()).select_from(RegistryVersion)) or 0
    rows = list(
        db.scalars(
            q.order_by(RegistryVersion.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    service = _svc(db, p)
    return {
        "items": [
            {
                "id": x.id,
                "version": x.version,
                "status": x.status,
                "published_at": x.published_at,
                "counts": service.snapshot_counts(x),
            }
            for x in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/versions")
def create_version(
    body: RegistryVersionCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    rv = _svc(db, p).create_version(body)
    _commit(db)
    return {"id": rv.id, "version": rv.version, "status": rv.status}


@router.post("/versions/{version}/validate")
def validate_version(
    version: str,
    body: RegistryVersionAction,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    service = _svc(db, p)
    rv = service.version_by_name(version)
    if not rv:
        raise HTTPException(404, "Registry version not found")
    report = service.validate_version(rv, body.notes)
    _commit(db)
    return {"version": rv.version, "status": rv.status, "validation": report}


@router.post("/versions/{version}/approve")
def approve_version(
    version: str,
    body: RegistryVersionAction,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    service = _svc(db, p)
    rv = service.version_by_name(version)
    if not rv:
        raise HTTPException(404, "Registry version not found")
    service.approve_version(rv, body.notes)
    _commit(db)
    return {"version": rv.version, "status": rv.status}


@router.post("/versions/publish")
def publish(
    body: RegistryPublish,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    service = _svc(db, p)
    rv = service.version_by_name(body.version)
    if not rv:
        raise HTTPException(404, "Registry version not found")
    try:
        service.publish_version(rv, body.notes)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Another registry version was published concurrently; reload and retry") from exc
    except Exception:
        db.rollback()
        raise
    return {"version": rv.version, "status": rv.status}


@router.get("/versions/diff")
def diff_versions(
    left: str,
    right: str,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    service = _svc(db, p)
    left_version = service.version_by_name(left)
    right_version = service.version_by_name(right)
    if not left_version or not right_version:
        raise HTTPException(404, "Registry version not found")
    return service.diff_versions(left_version, right_version)


@router.post("/versions/rollback")
def rollback(
    body: RegistryRollback,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    service = _svc(db, p)
    try:
        rv = service.rollback(body)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Rollback conflicted with a concurrent publish") from exc
    except Exception:
        db.rollback()
        raise
    return {"version": rv.version, "status": rv.status, "rolled_back_from": body.target_version}
