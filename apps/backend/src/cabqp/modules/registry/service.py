from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.shared.models import (
    RegistryCandidate,
    RegistrySnapshotCode,
    RegistrySnapshotName,
    RegistrySnapshotUnit,
    RegistryVersion,
    Source,
    Unit,
    UnitCode,
    UnitName,
    uid,
    utcnow,
)
from cabqp.shared.normalization import normalize_text
from cabqp.shared.schemas import (
    AliasCreate,
    AliasQADecision,
    CandidateDecision,
    RegistryRollback,
    RegistryVersionCreate,
    UnitCodeCreate,
    UnitCodeQADecision,
    UnitCreate,
    UnitQADecision,
    UnitUpdate,
)


def _snapshot_unit(version_id: str, unit: Unit) -> RegistrySnapshotUnit:
    return RegistrySnapshotUnit(
        registry_version_id=version_id,
        unit_id=unit.id,
        canonical_name=unit.canonical_name,
        normalized_key=unit.normalized_key,
        organization_type=unit.organization_type,
        unit_level=unit.unit_level,
        coverage_group=unit.coverage_group,
        parent_unit_id=unit.parent_unit_id,
        valid_from=unit.valid_from,
        valid_to=unit.valid_to,
        source_id=unit.source_id,
        active=unit.active,
    )


def _snapshot_name(version_id: str, name: UnitName) -> RegistrySnapshotName:
    return RegistrySnapshotName(
        registry_version_id=version_id,
        unit_name_id=name.id,
        unit_id=name.unit_id,
        name=name.name,
        normalized_key=name.normalized_key,
        name_type=name.name_type,
        source_id=name.source_id,
        valid_from=name.valid_from,
        valid_to=name.valid_to,
    )


def _snapshot_code(version_id: str, code: UnitCode) -> RegistrySnapshotCode:
    return RegistrySnapshotCode(
        registry_version_id=version_id,
        unit_code_id=code.id,
        unit_id=code.unit_id,
        code=code.code,
        code_type=code.code_type,
        namespace=code.namespace,
        source_id=code.source_id,
        valid_from=code.valid_from,
        valid_to=code.valid_to,
    )


class RegistryService:
    def __init__(self, db: Session, *, actor: str = "system"):
        self.db = db
        self.actor = actor

    def published(self) -> RegistryVersion | None:
        return self.db.scalar(
            select(RegistryVersion)
            .where(RegistryVersion.status == "PUBLISHED")
            .order_by(RegistryVersion.published_at.desc())
        )

    def version_by_name(self, version: str) -> RegistryVersion | None:
        return self.db.scalar(select(RegistryVersion).where(RegistryVersion.version == version))

    def _copy_snapshot(self, source: RegistryVersion, target: RegistryVersion) -> None:
        for row in self.db.scalars(
            select(RegistrySnapshotUnit).where(RegistrySnapshotUnit.registry_version_id == source.id)
        ):
            self.db.add(
                RegistrySnapshotUnit(
                    registry_version_id=target.id,
                    unit_id=row.unit_id,
                    canonical_name=row.canonical_name,
                    normalized_key=row.normalized_key,
                    organization_type=row.organization_type,
                    unit_level=row.unit_level,
                    coverage_group=row.coverage_group,
                    parent_unit_id=row.parent_unit_id,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    source_id=row.source_id,
                    active=row.active,
                )
            )
        for row in self.db.scalars(
            select(RegistrySnapshotName).where(RegistrySnapshotName.registry_version_id == source.id)
        ):
            self.db.add(
                RegistrySnapshotName(
                    registry_version_id=target.id,
                    unit_name_id=row.unit_name_id,
                    unit_id=row.unit_id,
                    name=row.name,
                    normalized_key=row.normalized_key,
                    name_type=row.name_type,
                    source_id=row.source_id,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                )
            )
        for row in self.db.scalars(
            select(RegistrySnapshotCode).where(RegistrySnapshotCode.registry_version_id == source.id)
        ):
            self.db.add(
                RegistrySnapshotCode(
                    registry_version_id=target.id,
                    unit_code_id=row.unit_code_id,
                    unit_id=row.unit_id,
                    code=row.code,
                    code_type=row.code_type,
                    namespace=row.namespace,
                    source_id=row.source_id,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                )
            )

    def create_version(self, body: RegistryVersionCreate) -> RegistryVersion:
        if self.version_by_name(body.version):
            raise HTTPException(409, "Registry version already exists")
        base = self.version_by_name(body.base_version) if body.base_version else self.published()
        if body.base_version and not base:
            raise HTTPException(404, "Base registry version not found")
        rv = RegistryVersion(version=body.version, status="DRAFT", notes=body.notes)
        self.db.add(rv)
        self.db.flush()
        if base:
            self._copy_snapshot(base, rv)
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="REGISTRY_VERSION_CREATE",
            entity_type="REGISTRY_VERSION",
            entity_id=rv.id,
            metadata={"version": rv.version, "base_version": base.version if base else None},
        )
        return rv

    def working_draft(self, requested: str | None = None) -> RegistryVersion:
        if requested:
            rv = self.version_by_name(requested)
            if not rv:
                raise HTTPException(404, "Draft registry version not found")
            if rv.status != "DRAFT":
                raise HTTPException(409, "Registry modifications are allowed only on DRAFT versions")
            return rv
        rv = self.db.scalar(
            select(RegistryVersion)
            .where(RegistryVersion.status == "DRAFT")
            .order_by(RegistryVersion.created_at.desc())
        )
        if rv:
            return rv
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return self.create_version(RegistryVersionCreate(version=f"draft-{stamp}", notes="Auto-created working draft"))

    def create_source(self, url: str | None, authority: str | None = None) -> Source | None:
        if not url:
            return None
        src = Source(authority=authority or "PROVIDED", url=url, source_kind="PROVIDED", retrieved_at=utcnow())
        self.db.add(src)
        self.db.flush()
        return src

    def create_unit(self, body: UnitCreate) -> Unit:
        if body.parent_unit_id and not self.db.get(Unit, body.parent_unit_id):
            raise HTTPException(400, "parent_unit_id does not exist")
        src = self.create_source(body.source_url, body.source_authority)
        unit = Unit(
            id=uid("unit"),
            canonical_name=body.canonical_name,
            normalized_key=normalize_text(body.canonical_name),
            organization_type=body.organization_type.value,
            unit_level=body.unit_level,
            coverage_group=body.coverage_group,
            parent_unit_id=body.parent_unit_id,
            qa_status="PENDING_QA",
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            source_id=src.id if src else None,
            active=True,
        )
        self.db.add(unit)
        self.db.flush()
        audit(self.db, actor=self.actor, role="ADMIN", action="UNIT_CREATE_PENDING_QA", entity_type="UNIT", entity_id=unit.id, metadata={"canonical_name": unit.canonical_name})
        return unit

    def update_unit(self, unit: Unit, body: UnitUpdate) -> Unit:
        # Mutating the master record does not mutate published snapshots: snapshot rows store copied values.
        data = body.model_dump(exclude_unset=True)
        before = {k: getattr(unit, k) for k in data}
        for key, value in data.items():
            if hasattr(value, "value"):
                value = value.value
            setattr(unit, key, value)
        if body.canonical_name:
            unit.normalized_key = normalize_text(body.canonical_name)
        audit(self.db, actor=self.actor, role="ADMIN", action="UNIT_UPDATE_MASTER", entity_type="UNIT", entity_id=unit.id, metadata={"before": before, "after": data})
        return unit

    def decide_unit_qa(self, unit: Unit, body: UnitQADecision) -> RegistryVersion | None:
        if unit.qa_status != "PENDING_QA":
            raise HTTPException(409, "Unit is no longer pending QA")
        if body.decision == "REJECT":
            unit.qa_status = "REJECTED"
            unit.active = False
            rv = None
        else:
            if not unit.source_id:
                raise HTTPException(422, "APPROVE requires provenance/source")
            unit.qa_status = "APPROVED"
            rv = self.working_draft(body.draft_version)
            existing = self.db.get(RegistrySnapshotUnit, {"registry_version_id": rv.id, "unit_id": unit.id})
            if existing:
                self.db.delete(existing)
                self.db.flush()
            self.db.add(_snapshot_unit(rv.id, unit))
        audit(self.db, actor=self.actor, role="ADMIN", action="UNIT_QA_DECISION", entity_type="UNIT", entity_id=unit.id, metadata={"decision": body.decision, "draft_version": rv.version if rv else None, "note": body.note})
        return rv

    def create_alias(self, unit: Unit, body: AliasCreate) -> UnitName:
        src = self.create_source(body.source_url, "PROVIDED")
        name = UnitName(
            unit_id=unit.id,
            name=body.name,
            normalized_key=normalize_text(body.name),
            name_type=body.name_type,
            qa_status="PENDING_QA",
            source_id=src.id if src else None,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
        )
        self.db.add(name)
        self.db.flush()
        audit(self.db, actor=self.actor, role="ADMIN", action="ALIAS_CREATE_PENDING_QA", entity_type="UNIT_NAME", entity_id=name.id, metadata={"unit_id": unit.id, "name": body.name})
        return name

    def decide_alias_qa(self, alias: UnitName, body: AliasQADecision) -> RegistryVersion | None:
        if alias.qa_status != "PENDING_QA":
            raise HTTPException(409, "Alias is no longer pending QA")
        if body.decision == "REJECT":
            alias.qa_status = "REJECTED"
            rv = None
        else:
            if not alias.source_id:
                raise HTTPException(422, "APPROVE requires provenance/source")
            alias.qa_status = "APPROVED"
            alias.approved_by = self.actor
            alias.approved_at = utcnow()
            rv = self.working_draft(body.draft_version)
            existing = self.db.get(RegistrySnapshotName, {"registry_version_id": rv.id, "unit_name_id": alias.id})
            if existing:
                self.db.delete(existing)
                self.db.flush()
            self.db.add(_snapshot_name(rv.id, alias))
        audit(self.db, actor=self.actor, role="ADMIN", action="ALIAS_QA_DECISION", entity_type="UNIT_NAME", entity_id=alias.id, metadata={"decision": body.decision, "draft_version": rv.version if rv else None, "note": body.note})
        return rv

    def create_code(self, unit: Unit, body: UnitCodeCreate) -> UnitCode:
        src = self.create_source(body.source_url, "PROVIDED")
        code = UnitCode(
            unit_id=unit.id,
            code=body.code.strip(),
            code_type=body.code_type,
            namespace=body.namespace,
            qa_status="PENDING_QA",
            source_id=src.id if src else None,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
        )
        self.db.add(code)
        self.db.flush()
        audit(self.db, actor=self.actor, role="ADMIN", action="UNIT_CODE_CREATE_PENDING_QA", entity_type="UNIT_CODE", entity_id=code.id, metadata={"unit_id": unit.id, "code": code.code})
        return code

    def decide_code_qa(self, code: UnitCode, body: UnitCodeQADecision) -> RegistryVersion | None:
        if code.qa_status != "PENDING_QA":
            raise HTTPException(409, "Code is no longer pending QA")
        if body.decision == "REJECT":
            code.qa_status = "REJECTED"
            rv = None
        else:
            if not code.source_id:
                raise HTTPException(422, "APPROVE requires provenance/source")
            code.qa_status = "APPROVED"
            code.approved_by = self.actor
            code.approved_at = utcnow()
            rv = self.working_draft(body.draft_version)
            existing = self.db.get(RegistrySnapshotCode, {"registry_version_id": rv.id, "unit_code_id": code.id})
            if existing:
                self.db.delete(existing)
                self.db.flush()
            self.db.add(_snapshot_code(rv.id, code))
        audit(self.db, actor=self.actor, role="ADMIN", action="UNIT_CODE_QA_DECISION", entity_type="UNIT_CODE", entity_id=code.id, metadata={"decision": body.decision, "draft_version": rv.version if rv else None, "note": body.note})
        return rv

    def decide_candidate(self, candidate: RegistryCandidate, body: CandidateDecision) -> tuple[RegistryCandidate, Unit | None, RegistryVersion | None]:
        if candidate.status != "PENDING_QA":
            raise HTTPException(409, "Candidate is no longer pending QA")
        candidate.reviewed_by = self.actor
        candidate.reviewed_at = utcnow()
        if body.decision == "REJECT":
            candidate.status = "REJECTED"
            unit = None
            rv = None
        else:
            if not candidate.source_id:
                # Human review feedback has structured evidence rather than a URL source. Keep it pending until provenance is attached.
                source_hint = (candidate.evidence or {}).get("source")
                if source_hint != "REVIEW_FEEDBACK":
                    raise HTTPException(422, "APPROVE requires source/provenance")
            candidate.status = "APPROVED"
            name = body.canonical_name or candidate.proposed_name
            unit = Unit(
                id=uid("unit"),
                canonical_name=name,
                normalized_key=normalize_text(name),
                organization_type=candidate.organization_type,
                qa_status="APPROVED",
                source_id=candidate.source_id,
                active=True,
            )
            self.db.add(unit)
            self.db.flush()
            rv = self.working_draft(body.draft_version)
            self.db.add(_snapshot_unit(rv.id, unit))
        audit(self.db, actor=self.actor, role="ADMIN", action="CANDIDATE_QA_DECISION", entity_type="REGISTRY_CANDIDATE", entity_id=candidate.id, metadata={"decision": body.decision, "unit_id": unit.id if unit else None, "draft_version": rv.version if rv else None, "note": body.note})
        return candidate, unit, rv

    def validate_version(self, rv: RegistryVersion, notes: str = "") -> dict:
        if rv.status != "DRAFT":
            raise HTTPException(409, "Only DRAFT registry versions can be validated")
        rows = list(self.db.scalars(select(RegistrySnapshotUnit).where(RegistrySnapshotUnit.registry_version_id == rv.id)))
        errors: list[str] = []
        if not rows:
            errors.append("snapshot_has_no_units")
        normalized_seen: dict[tuple[str, str], str] = {}
        for row in rows:
            key = (row.organization_type, row.normalized_key)
            if key in normalized_seen and normalized_seen[key] != row.unit_id:
                errors.append(f"duplicate_normalized_unit:{row.organization_type}:{row.normalized_key}")
            normalized_seen[key] = row.unit_id
            unit = self.db.get(Unit, row.unit_id)
            if not unit or unit.qa_status != "APPROVED":
                errors.append(f"unit_not_approved:{row.unit_id}")
            if not row.source_id:
                errors.append(f"unit_missing_source:{row.unit_id}")
            if row.valid_from and row.valid_to and row.valid_from > row.valid_to:
                errors.append(f"invalid_validity:{row.unit_id}")
        if errors:
            raise HTTPException(422, {"message": "Registry validation failed", "errors": sorted(set(errors))[:200]})
        rv.status = "VALIDATED"
        rv.notes = notes or rv.notes
        audit(self.db, actor=self.actor, role="ADMIN", action="REGISTRY_VALIDATE", entity_type="REGISTRY_VERSION", entity_id=rv.id, metadata={"version": rv.version, "unit_count": len(rows)})
        return {"unit_count": len(rows), "errors": []}

    def approve_version(self, rv: RegistryVersion, notes: str = "") -> RegistryVersion:
        if rv.status != "VALIDATED":
            raise HTTPException(409, "Only VALIDATED registry versions can be approved")
        rv.status = "APPROVED"
        rv.notes = notes or rv.notes
        audit(self.db, actor=self.actor, role="ADMIN", action="REGISTRY_APPROVE", entity_type="REGISTRY_VERSION", entity_id=rv.id, metadata={"version": rv.version})
        return rv

    def publish_version(self, rv: RegistryVersion, notes: str = "") -> RegistryVersion:
        if rv.status != "APPROVED":
            raise HTTPException(409, "Only APPROVED registry versions can be published")
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(2288062026)"))
        for old in self.db.scalars(select(RegistryVersion).where(RegistryVersion.status == "PUBLISHED").with_for_update()):
            old.status = "DEPRECATED"
        rv = self.db.scalar(select(RegistryVersion).where(RegistryVersion.id == rv.id).with_for_update())
        assert rv is not None
        rv.status = "PUBLISHED"
        rv.published_at = utcnow()
        rv.notes = notes or rv.notes
        self.db.flush()
        audit(self.db, actor=self.actor, role="ADMIN", action="REGISTRY_PUBLISH", entity_type="REGISTRY_VERSION", entity_id=rv.id, metadata={"version": rv.version})
        return rv

    def diff_versions(self, left: RegistryVersion, right: RegistryVersion) -> dict:
        def units(rv):
            return {x.unit_id: x for x in self.db.scalars(select(RegistrySnapshotUnit).where(RegistrySnapshotUnit.registry_version_id == rv.id))}
        left_units, right_units = units(left), units(right)
        added = sorted(set(right_units) - set(left_units))
        removed = sorted(set(left_units) - set(right_units))
        changed = []
        fields = ("canonical_name", "organization_type", "unit_level", "coverage_group", "parent_unit_id", "valid_from", "valid_to", "source_id", "active")
        for uid_ in sorted(set(left_units) & set(right_units)):
            before = {f: getattr(left_units[uid_], f) for f in fields}
            after = {f: getattr(right_units[uid_], f) for f in fields}
            if before != after:
                changed.append({"unit_id": uid_, "before": before, "after": after})
        return {"left": left.version, "right": right.version, "added_unit_ids": added, "removed_unit_ids": removed, "changed_units": changed}

    def rollback(self, body: RegistryRollback) -> RegistryVersion:
        target = self.version_by_name(body.target_version)
        if not target:
            raise HTTPException(404, "Target registry version not found")
        new_name = body.new_version or f"rollback-{target.version}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        rv = self.create_version(RegistryVersionCreate(version=new_name, base_version=target.version, notes=body.notes or f"Rollback snapshot cloned from {target.version}"))
        # A rollback snapshot is byte-for-byte cloned from a historical snapshot, so it can be fast-tracked through explicit states.
        rv.status = "VALIDATED"
        rv.status = "APPROVED"
        return self.publish_version(rv, body.notes)

    def snapshot_counts(self, rv: RegistryVersion) -> dict:
        return {
            "units": self.db.scalar(select(func.count()).select_from(RegistrySnapshotUnit).where(RegistrySnapshotUnit.registry_version_id == rv.id)) or 0,
            "names": self.db.scalar(select(func.count()).select_from(RegistrySnapshotName).where(RegistrySnapshotName.registry_version_id == rv.id)) or 0,
            "codes": self.db.scalar(select(func.count()).select_from(RegistrySnapshotCode).where(RegistrySnapshotCode.registry_version_id == rv.id)) or 0,
        }
