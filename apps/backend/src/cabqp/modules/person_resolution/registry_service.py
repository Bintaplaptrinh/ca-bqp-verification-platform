from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.shared.models import (
    Person,
    PersonCode,
    PersonCodeSnapshot,
    PersonName,
    PersonNameSnapshot,
    PersonRegistryCandidate,
    PersonRegistrySnapshot,
    PersonRegistryVersion,
    Source,
    Unit,
    uid,
    utcnow,
)
from cabqp.shared.normalization import ascii_key, normalize_text
from cabqp.shared.schemas import (
    PersonAliasCreate,
    PersonAliasQADecision,
    PersonCandidateDecision,
    PersonCodeCreate,
    PersonCodeQADecision,
    PersonCreate,
    PersonQADecision,
    PersonUpdate,
    RegistryRollback,
    RegistryVersionCreate,
)

PERSON_REGISTRY_PUBLISH_LOCK = 2288062027


def _snapshot_person(version_id: str, person: Person) -> PersonRegistrySnapshot:
    return PersonRegistrySnapshot(
        registry_version_id=version_id,
        person_id=person.id,
        full_name=person.full_name,
        normalized_key=person.normalized_key,
        ascii_key=person.ascii_key,
        birth_year=person.birth_year,
        canonical_unit_id=person.canonical_unit_id,
        subject_group_hint=person.subject_group_hint,
        employment_status=person.employment_status,
        source_id=person.source_id,
        source_kind=person.source_kind,
        active=person.active,
        valid_from=person.valid_from,
        valid_to=person.valid_to,
        synthetic_welfare_facts=person.synthetic_welfare_facts,
    )


def _snapshot_name(version_id: str, name: PersonName) -> PersonNameSnapshot:
    return PersonNameSnapshot(
        registry_version_id=version_id,
        person_name_id=name.id,
        person_id=name.person_id,
        name=name.name,
        normalized_key=name.normalized_key,
        ascii_key=name.ascii_key,
        name_type=name.name_type,
        source_id=name.source_id,
    )


def _snapshot_code(version_id: str, code: PersonCode) -> PersonCodeSnapshot:
    return PersonCodeSnapshot(
        registry_version_id=version_id,
        person_code_id=code.id,
        person_id=code.person_id,
        code=code.code,
        code_type=code.code_type,
        namespace=code.namespace,
        source_id=code.source_id,
    )


class PersonRegistryService:
    def __init__(self, db: Session, *, actor: str = "system"):
        self.db = db
        self.actor = actor

    def published(self) -> PersonRegistryVersion | None:
        return self.db.scalar(
            select(PersonRegistryVersion)
            .where(PersonRegistryVersion.status == "PUBLISHED")
            .order_by(PersonRegistryVersion.published_at.desc())
        )

    def version_by_name(self, version: str) -> PersonRegistryVersion | None:
        return self.db.scalar(
            select(PersonRegistryVersion).where(PersonRegistryVersion.version == version)
        )

    def _copy_snapshot(
        self, source: PersonRegistryVersion, target: PersonRegistryVersion
    ) -> None:
        for row in self.db.scalars(
            select(PersonRegistrySnapshot).where(
                PersonRegistrySnapshot.registry_version_id == source.id
            )
        ):
            self.db.add(
                PersonRegistrySnapshot(
                    registry_version_id=target.id,
                    person_id=row.person_id,
                    full_name=row.full_name,
                    normalized_key=row.normalized_key,
                    ascii_key=row.ascii_key,
                    birth_year=row.birth_year,
                    canonical_unit_id=row.canonical_unit_id,
                    subject_group_hint=row.subject_group_hint,
                    employment_status=row.employment_status,
                    source_id=row.source_id,
                    source_kind=row.source_kind,
                    active=row.active,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    synthetic_welfare_facts=row.synthetic_welfare_facts,
                )
            )
        for row in self.db.scalars(
            select(PersonNameSnapshot).where(
                PersonNameSnapshot.registry_version_id == source.id
            )
        ):
            self.db.add(
                PersonNameSnapshot(
                    registry_version_id=target.id,
                    person_name_id=row.person_name_id,
                    person_id=row.person_id,
                    name=row.name,
                    normalized_key=row.normalized_key,
                    ascii_key=row.ascii_key,
                    name_type=row.name_type,
                    source_id=row.source_id,
                )
            )
        for row in self.db.scalars(
            select(PersonCodeSnapshot).where(
                PersonCodeSnapshot.registry_version_id == source.id
            )
        ):
            self.db.add(
                PersonCodeSnapshot(
                    registry_version_id=target.id,
                    person_code_id=row.person_code_id,
                    person_id=row.person_id,
                    code=row.code,
                    code_type=row.code_type,
                    namespace=row.namespace,
                    source_id=row.source_id,
                )
            )

    def create_version(self, body: RegistryVersionCreate) -> PersonRegistryVersion:
        if self.version_by_name(body.version):
            raise HTTPException(409, "Person registry version already exists")
        base = self.version_by_name(body.base_version) if body.base_version else self.published()
        if body.base_version and not base:
            raise HTTPException(404, "Base person registry version not found")
        rv = PersonRegistryVersion(version=body.version, status="DRAFT", notes=body.notes)
        self.db.add(rv)
        self.db.flush()
        if base:
            self._copy_snapshot(base, rv)
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_REGISTRY_VERSION_CREATE",
            entity_type="PERSON_REGISTRY_VERSION",
            entity_id=rv.id,
            metadata={"version": rv.version, "base_version": base.version if base else None},
        )
        return rv

    def working_draft(self, requested: str | None = None) -> PersonRegistryVersion:
        if requested:
            rv = self.version_by_name(requested)
            if not rv:
                raise HTTPException(404, "Draft person registry version not found")
            if rv.status != "DRAFT":
                raise HTTPException(
                    409, "Person registry modifications are allowed only on DRAFT versions"
                )
            return rv
        rv = self.db.scalar(
            select(PersonRegistryVersion)
            .where(PersonRegistryVersion.status == "DRAFT")
            .order_by(PersonRegistryVersion.created_at.desc())
        )
        if rv:
            return rv
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return self.create_version(
            RegistryVersionCreate(
                version=f"person-draft-{stamp}", notes="Auto-created person registry draft"
            )
        )

    def create_source(
        self,
        url: str | None,
        authority: str | None = None,
        source_kind: str = "PROVIDED",
    ) -> Source | None:
        if not url:
            return None
        src = Source(
            authority=authority or source_kind,
            url=url,
            source_kind=source_kind,
            retrieved_at=utcnow(),
        )
        self.db.add(src)
        self.db.flush()
        return src

    def _trusted_unit(self, unit_id: str) -> Unit:
        unit = self.db.get(Unit, unit_id)
        if not unit:
            raise HTTPException(422, "canonical_unit_id does not exist")
        if not unit.active or unit.qa_status != "APPROVED":
            raise HTTPException(
                422, "canonical_unit_id must reference an active APPROVED unit"
            )
        return unit

    def create_person(self, body: PersonCreate) -> Person:
        if not self.db.get(Unit, body.canonical_unit_id):
            raise HTTPException(422, "canonical_unit_id does not exist")
        src = self.create_source(body.source_url, body.source_authority, body.source_kind)
        person = Person(
            id=uid("person"),
            full_name=body.full_name.strip(),
            normalized_key=normalize_text(body.full_name),
            ascii_key=ascii_key(body.full_name),
            birth_year=body.birth_year,
            canonical_unit_id=body.canonical_unit_id,
            subject_group_hint=body.subject_group_hint,
            employment_status=body.employment_status,
            qa_status="PENDING_QA",
            source_id=src.id if src else None,
            source_kind=body.source_kind,
            active=True,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
        )
        self.db.add(person)
        self.db.flush()
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_CREATE_PENDING_QA",
            entity_type="PERSON",
            entity_id=person.id,
            metadata={"canonical_unit_id": person.canonical_unit_id},
        )
        return person

    def update_person(self, person: Person, body: PersonUpdate) -> Person:
        values = body.model_dump(exclude_unset=True)
        if not values:
            return person
        if "canonical_unit_id" in values and values["canonical_unit_id"] is not None:
            if not self.db.get(Unit, values["canonical_unit_id"]):
                raise HTTPException(422, "canonical_unit_id does not exist")

        before = {key: getattr(person, key) for key in values}
        if "full_name" in values and values["full_name"] is not None:
            cleaned_name = values.pop("full_name").strip()
            person.full_name = cleaned_name
            person.normalized_key = normalize_text(cleaned_name)
            person.ascii_key = ascii_key(cleaned_name)
        for key, value in values.items():
            setattr(person, key, value)

        after = {key: getattr(person, key) for key in before}
        changed = any(before[key] != after[key] for key in before)
        if changed:
            # Master edits are never silently trusted. A published snapshot remains immutable,
            # while the edited live record must pass QA again before it can enter a new version.
            person.qa_status = "PENDING_QA"
            audit(
                self.db,
                actor=self.actor,
                role="ADMIN",
                action="PERSON_UPDATE_PENDING_QA",
                entity_type="PERSON",
                entity_id=person.id,
                metadata={"before": before, "after": after},
            )
        return person

    def decide_person_qa(
        self, person: Person, body: PersonQADecision
    ) -> PersonRegistryVersion | None:
        if person.qa_status != "PENDING_QA":
            raise HTTPException(409, "Person is no longer pending QA")
        if body.decision == "REJECT":
            person.qa_status = "REJECTED"
            rv = None
        else:
            self._trusted_unit(person.canonical_unit_id)
            if not person.source_id:
                raise HTTPException(422, "APPROVE requires provenance/source")
            person.qa_status = "APPROVED"
            rv = self.working_draft(body.draft_version)
            existing = self.db.get(
                PersonRegistrySnapshot,
                {"registry_version_id": rv.id, "person_id": person.id},
            )
            if existing:
                self.db.delete(existing)
                self.db.flush()
            self.db.add(_snapshot_person(rv.id, person))
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_QA_DECISION",
            entity_type="PERSON",
            entity_id=person.id,
            metadata={
                "decision": body.decision,
                "draft_version": rv.version if rv else None,
                "note": body.note,
            },
        )
        return rv

    def create_alias(self, person: Person, body: PersonAliasCreate) -> PersonName:
        src = self.create_source(body.source_url)
        alias = PersonName(
            person_id=person.id,
            name=body.name.strip(),
            normalized_key=normalize_text(body.name),
            ascii_key=ascii_key(body.name),
            name_type=body.name_type,
            qa_status="PENDING_QA",
            source_id=src.id if src else None,
        )
        self.db.add(alias)
        self.db.flush()
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_ALIAS_CREATE_PENDING_QA",
            entity_type="PERSON_NAME",
            entity_id=alias.id,
            metadata={"person_id": person.id},
        )
        return alias

    def decide_alias_qa(
        self, alias: PersonName, body: PersonAliasQADecision
    ) -> PersonRegistryVersion | None:
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
            existing = self.db.get(
                PersonNameSnapshot,
                {"registry_version_id": rv.id, "person_name_id": alias.id},
            )
            if existing:
                self.db.delete(existing)
                self.db.flush()
            self.db.add(_snapshot_name(rv.id, alias))
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_ALIAS_QA_DECISION",
            entity_type="PERSON_NAME",
            entity_id=alias.id,
            metadata={"decision": body.decision, "draft_version": rv.version if rv else None},
        )
        return rv

    def create_code(self, person: Person, body: PersonCodeCreate) -> PersonCode:
        src = self.create_source(body.source_url)
        code = PersonCode(
            person_id=person.id,
            code=body.code.strip(),
            code_type=body.code_type,
            namespace=body.namespace,
            qa_status="PENDING_QA",
            source_id=src.id if src else None,
        )
        self.db.add(code)
        self.db.flush()
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_CODE_CREATE_PENDING_QA",
            entity_type="PERSON_CODE",
            entity_id=code.id,
            metadata={"person_id": person.id, "code": code.code},
        )
        return code

    def decide_code_qa(
        self, code: PersonCode, body: PersonCodeQADecision
    ) -> PersonRegistryVersion | None:
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
            existing = self.db.get(
                PersonCodeSnapshot,
                {"registry_version_id": rv.id, "person_code_id": code.id},
            )
            if existing:
                self.db.delete(existing)
                self.db.flush()
            self.db.add(_snapshot_code(rv.id, code))
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_CODE_QA_DECISION",
            entity_type="PERSON_CODE",
            entity_id=code.id,
            metadata={"decision": body.decision, "draft_version": rv.version if rv else None},
        )
        return rv

    def decide_candidate(
        self, candidate: PersonRegistryCandidate, body: PersonCandidateDecision
    ) -> tuple[PersonRegistryCandidate, Person | None, PersonRegistryVersion | None]:
        if candidate.status != "PENDING_QA":
            raise HTTPException(409, "Candidate is no longer pending QA")
        candidate.reviewed_by = self.actor
        candidate.reviewed_at = utcnow()
        if body.decision == "REJECT":
            candidate.status = "REJECTED"
            person = None
            rv = None
        else:
            unit_id = body.canonical_unit_id or candidate.canonical_unit_id
            if not unit_id:
                raise HTTPException(422, "APPROVE requires canonical_unit_id")
            self._trusted_unit(unit_id)
            if not candidate.source_id and (candidate.evidence or {}).get("source") != "REVIEW_FEEDBACK":
                raise HTTPException(422, "APPROVE requires source/provenance")
            candidate.status = "APPROVED"
            name = body.full_name or candidate.proposed_name
            person = Person(
                id=uid("person"),
                full_name=name,
                normalized_key=normalize_text(name),
                ascii_key=ascii_key(name),
                birth_year=candidate.birth_year,
                canonical_unit_id=unit_id,
                subject_group_hint=candidate.subject_group_hint,
                employment_status=candidate.employment_status,
                qa_status="APPROVED",
                source_id=candidate.source_id,
                source_kind=candidate.source_kind,
                active=True,
            )
            self.db.add(person)
            self.db.flush()
            rv = self.working_draft(body.draft_version)
            self.db.add(_snapshot_person(rv.id, person))
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_CANDIDATE_QA_DECISION",
            entity_type="PERSON_REGISTRY_CANDIDATE",
            entity_id=candidate.id,
            metadata={
                "decision": body.decision,
                "person_id": person.id if person else None,
                "draft_version": rv.version if rv else None,
            },
        )
        return candidate, person, rv

    def validate_version(self, rv: PersonRegistryVersion, notes: str = "") -> dict:
        if rv.status != "DRAFT":
            raise HTTPException(409, "Only DRAFT person registry versions can be validated")
        rows = list(
            self.db.scalars(
                select(PersonRegistrySnapshot).where(
                    PersonRegistrySnapshot.registry_version_id == rv.id
                )
            )
        )
        errors: list[str] = []
        if not rows:
            errors.append("snapshot_has_no_persons")
        for row in rows:
            person = self.db.get(Person, row.person_id)
            if not person or person.qa_status != "APPROVED" or not person.active:
                errors.append(f"person_not_approved_active:{row.person_id}")
            unit = self.db.get(Unit, row.canonical_unit_id)
            if not unit or unit.qa_status != "APPROVED" or not unit.active:
                errors.append(f"unit_not_approved_active:{row.canonical_unit_id}")
            if row.source_kind != "SYNTHETIC_DEMO" and not row.source_id:
                errors.append(f"person_missing_source:{row.person_id}")
            if row.source_kind != "SYNTHETIC_DEMO" and row.synthetic_welfare_facts:
                errors.append(f"non_synthetic_has_welfare_facts:{row.person_id}")
            if row.valid_from and row.valid_to and row.valid_from > row.valid_to:
                errors.append(f"invalid_validity:{row.person_id}")
        if errors:
            raise HTTPException(
                422,
                {"message": "Person registry validation failed", "errors": sorted(set(errors))[:200]},
            )
        rv.status = "VALIDATED"
        rv.notes = notes or rv.notes
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_REGISTRY_VALIDATE",
            entity_type="PERSON_REGISTRY_VERSION",
            entity_id=rv.id,
            metadata={"version": rv.version, "person_count": len(rows)},
        )
        return {"person_count": len(rows), "errors": []}

    def approve_version(self, rv: PersonRegistryVersion, notes: str = "") -> PersonRegistryVersion:
        if rv.status != "VALIDATED":
            raise HTTPException(409, "Only VALIDATED person registry versions can be approved")
        rv.status = "APPROVED"
        rv.notes = notes or rv.notes
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_REGISTRY_APPROVE",
            entity_type="PERSON_REGISTRY_VERSION",
            entity_id=rv.id,
            metadata={"version": rv.version},
        )
        return rv

    def publish_version(self, rv: PersonRegistryVersion, notes: str = "") -> PersonRegistryVersion:
        if rv.status != "APPROVED":
            raise HTTPException(409, "Only APPROVED person registry versions can be published")
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(text(f"SELECT pg_advisory_xact_lock({PERSON_REGISTRY_PUBLISH_LOCK})"))
        for old in self.db.scalars(
            select(PersonRegistryVersion)
            .where(PersonRegistryVersion.status == "PUBLISHED")
            .with_for_update()
        ):
            old.status = "DEPRECATED"
        locked = self.db.scalar(
            select(PersonRegistryVersion)
            .where(PersonRegistryVersion.id == rv.id)
            .with_for_update()
        )
        assert locked is not None
        locked.status = "PUBLISHED"
        locked.published_at = utcnow()
        locked.notes = notes or locked.notes
        self.db.flush()
        audit(
            self.db,
            actor=self.actor,
            role="ADMIN",
            action="PERSON_REGISTRY_PUBLISH",
            entity_type="PERSON_REGISTRY_VERSION",
            entity_id=locked.id,
            metadata={"version": locked.version},
        )
        return locked

    def diff_versions(self, left: PersonRegistryVersion, right: PersonRegistryVersion) -> dict:
        def people(rv: PersonRegistryVersion) -> dict[str, PersonRegistrySnapshot]:
            return {
                x.person_id: x
                for x in self.db.scalars(
                    select(PersonRegistrySnapshot).where(
                        PersonRegistrySnapshot.registry_version_id == rv.id
                    )
                )
            }

        left_people, right_people = people(left), people(right)
        added = sorted(set(right_people) - set(left_people))
        removed = sorted(set(left_people) - set(right_people))
        fields = (
            "full_name",
            "birth_year",
            "canonical_unit_id",
            "subject_group_hint",
            "employment_status",
            "source_id",
            "source_kind",
            "active",
            "valid_from",
            "valid_to",
        )
        changed = []
        for person_id in sorted(set(left_people) & set(right_people)):
            before = {field: getattr(left_people[person_id], field) for field in fields}
            after = {field: getattr(right_people[person_id], field) for field in fields}
            if before != after:
                changed.append({"person_id": person_id, "before": before, "after": after})
        return {
            "left": left.version,
            "right": right.version,
            "added_person_ids": added,
            "removed_person_ids": removed,
            "changed_persons": changed,
        }

    def rollback(self, body: RegistryRollback) -> PersonRegistryVersion:
        target = self.version_by_name(body.target_version)
        if not target:
            raise HTTPException(404, "Target person registry version not found")
        new_name = body.new_version or f"person-rollback-{target.version}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        rv = self.create_version(
            RegistryVersionCreate(
                version=new_name,
                base_version=target.version,
                notes=body.notes or f"Rollback snapshot cloned from {target.version}",
            )
        )
        rv.status = "VALIDATED"
        rv.status = "APPROVED"
        return self.publish_version(rv, body.notes)

    def snapshot_counts(self, rv: PersonRegistryVersion) -> dict:
        return {
            "persons": self.db.scalar(
                select(func.count())
                .select_from(PersonRegistrySnapshot)
                .where(PersonRegistrySnapshot.registry_version_id == rv.id)
            )
            or 0,
            "names": self.db.scalar(
                select(func.count())
                .select_from(PersonNameSnapshot)
                .where(PersonNameSnapshot.registry_version_id == rv.id)
            )
            or 0,
            "codes": self.db.scalar(
                select(func.count())
                .select_from(PersonCodeSnapshot)
                .where(PersonCodeSnapshot.registry_version_id == rv.id)
            )
            or 0,
        }
