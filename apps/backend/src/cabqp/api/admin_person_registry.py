from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.person_resolution.registry_service import PersonRegistryService
from cabqp.shared.db import get_db
from cabqp.shared.enums import QAStatus
from cabqp.shared.models import (
    Person,
    PersonCode,
    PersonName,
    PersonRegistryCandidate,
    PersonRegistryVersion,
)
from cabqp.shared.schemas import (
    PersonAliasCreate,
    PersonAliasQADecision,
    PersonCandidateDecision,
    PersonCodeCreate,
    PersonCodeQADecision,
    PersonCreate,
    PersonQADecision,
    PersonUpdate,
    RegistryPublish,
    RegistryRollback,
    RegistryVersionAction,
    RegistryVersionCreate,
)

router = APIRouter(prefix="/admin/person-registry", tags=["person-registry-admin"])
ADMIN = Depends(require_perms(perms.PERSON_REGISTRY_ADMIN))


def _svc(db: Session, p: Principal) -> PersonRegistryService:
    return PersonRegistryService(db, actor=p.username)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Person registry change conflicts with an existing record") from exc


@router.get("/persons")
def persons(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    qa_status: QAStatus | None = None,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    q = select(Person)
    if qa_status:
        q = q.where(Person.qa_status == qa_status.value)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(Person.full_name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": x.id,
                "full_name": x.full_name,
                "birth_year": x.birth_year,
                "canonical_unit_id": x.canonical_unit_id,
                "subject_group_hint": x.subject_group_hint,
                "employment_status": x.employment_status,
                "qa_status": x.qa_status,
                "source_kind": x.source_kind,
                "active": x.active,
                "source_id": x.source_id,
            }
            for x in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/persons/{person_id}")
def person_detail(
    person_id: str,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    aliases = list(
        db.scalars(select(PersonName).where(PersonName.person_id == person_id).order_by(PersonName.name))
    )
    codes = list(
        db.scalars(select(PersonCode).where(PersonCode.person_id == person_id).order_by(PersonCode.code))
    )
    return {
        "person": {
            "id": person.id,
            "full_name": person.full_name,
            "birth_year": person.birth_year,
            "canonical_unit_id": person.canonical_unit_id,
            "subject_group_hint": person.subject_group_hint,
            "employment_status": person.employment_status,
            "qa_status": person.qa_status,
            "source_kind": person.source_kind,
            "active": person.active,
            "source_id": person.source_id,
            "valid_from": person.valid_from,
            "valid_to": person.valid_to,
            "synthetic_welfare_facts": person.synthetic_welfare_facts,
        },
        "aliases": [
            {
                "id": x.id,
                "person_id": x.person_id,
                "name": x.name,
                "name_type": x.name_type,
                "qa_status": x.qa_status,
                "source_id": x.source_id,
                "approved_by": x.approved_by,
                "approved_at": x.approved_at,
            }
            for x in aliases
        ],
        "codes": [
            {
                "id": x.id,
                "person_id": x.person_id,
                "code": x.code,
                "code_type": x.code_type,
                "namespace": x.namespace,
                "qa_status": x.qa_status,
                "source_id": x.source_id,
                "approved_by": x.approved_by,
                "approved_at": x.approved_at,
            }
            for x in codes
        ],
    }


@router.post("/persons")
def create_person(
    body: PersonCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    person = _svc(db, p).create_person(body)
    _commit(db)
    return {"id": person.id, "qa_status": person.qa_status}


@router.patch("/persons/{person_id}")
def update_person(
    person_id: str,
    body: PersonUpdate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    _svc(db, p).update_person(person, body)
    _commit(db)
    return {"id": person.id}


@router.post("/persons/{person_id}/qa")
def person_qa(
    person_id: str,
    body: PersonQADecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    rv = _svc(db, p).decide_person_qa(person, body)
    _commit(db)
    return {
        "id": person.id,
        "qa_status": person.qa_status,
        "draft_version": rv.version if rv else None,
    }


@router.post("/persons/{person_id}/aliases")
def add_alias(
    person_id: str,
    body: PersonAliasCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    alias = _svc(db, p).create_alias(person, body)
    _commit(db)
    return {"id": alias.id, "qa_status": alias.qa_status}


@router.post("/aliases/{alias_id}/qa")
def alias_qa(
    alias_id: str,
    body: PersonAliasQADecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    alias = db.get(PersonName, alias_id)
    if not alias:
        raise HTTPException(404, "Person alias not found")
    rv = _svc(db, p).decide_alias_qa(alias, body)
    _commit(db)
    return {
        "id": alias.id,
        "qa_status": alias.qa_status,
        "draft_version": rv.version if rv else None,
    }


@router.post("/persons/{person_id}/codes")
def add_code(
    person_id: str,
    body: PersonCodeCreate,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    code = _svc(db, p).create_code(person, body)
    _commit(db)
    return {"id": code.id, "qa_status": code.qa_status}


@router.post("/codes/{code_id}/qa")
def code_qa(
    code_id: str,
    body: PersonCodeQADecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    code = db.get(PersonCode, code_id)
    if not code:
        raise HTTPException(404, "Person code not found")
    rv = _svc(db, p).decide_code_qa(code, body)
    _commit(db)
    return {
        "id": code.id,
        "qa_status": code.qa_status,
        "draft_version": rv.version if rv else None,
    }


@router.get("/candidates")
def candidates(
    status: QAStatus = QAStatus.PENDING_QA,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    q = select(PersonRegistryCandidate).where(PersonRegistryCandidate.status == status.value)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(PersonRegistryCandidate.created_at.desc())
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
                "birth_year": x.birth_year,
                "canonical_unit_id": x.canonical_unit_id,
                "subject_group_hint": x.subject_group_hint,
                "employment_status": x.employment_status,
                "source_kind": x.source_kind,
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
    body: PersonCandidateDecision,
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    candidate = db.get(PersonRegistryCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Person candidate not found")
    candidate, person, rv = _svc(db, p).decide_candidate(candidate, body)
    _commit(db)
    return {
        "id": candidate.id,
        "status": candidate.status,
        "person_id": person.id if person else None,
        "draft_version": rv.version if rv else None,
    }


@router.get("/versions")
def versions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = ADMIN,
):
    total = db.scalar(select(func.count()).select_from(PersonRegistryVersion)) or 0
    rows = list(
        db.scalars(
            select(PersonRegistryVersion)
            .order_by(PersonRegistryVersion.created_at.desc())
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
        raise HTTPException(404, "Person registry version not found")
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
        raise HTTPException(404, "Person registry version not found")
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
        raise HTTPException(404, "Person registry version not found")
    try:
        service.publish_version(rv, body.notes)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "Another person registry version was published concurrently; reload and retry"
        ) from exc
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
        raise HTTPException(404, "Person registry version not found")
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
        raise HTTPException(409, "Person registry rollback conflicted with a concurrent publish") from exc
    except Exception:
        db.rollback()
        raise
    return {
        "version": rv.version,
        "status": rv.status,
        "rolled_back_from": body.target_version,
    }
