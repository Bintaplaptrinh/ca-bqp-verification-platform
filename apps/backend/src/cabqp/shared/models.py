from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from cabqp.shared.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class RegistryVersion(Base):
    __tablename__ = "registry_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','VALIDATED','APPROVED','PUBLISHED','DEPRECATED')",
            name="ck_registry_version_status",
        ),
        Index(
            "uq_registry_single_published",
            "status",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
            sqlite_where=text("status = 'PUBLISHED'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("rv"))
    version: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_source_kind",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("src"))
    authority: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(30), default="OFFICIAL", index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        CheckConstraint("organization_type IN ('BCA','BQP','OTHER','UNKNOWN')", name="ck_unit_org"),
        CheckConstraint("qa_status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_unit_qa"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="ck_unit_validity",
        ),
        Index("ix_units_active_qa", "active", "qa_status"),
        Index("ix_units_org_active_qa", "organization_type", "active", "qa_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500), index=True)
    normalized_key: Mapped[str] = mapped_column(String(500), index=True)
    # Diacritic-folded form of normalized_key. Kept alongside it rather than replacing
    # it so an accented exact match still outranks a folded one.
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    organization_type: Mapped[str] = mapped_column(String(20), index=True)
    unit_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    coverage_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    parent_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=True
    )
    qa_status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Legacy/source version pointer kept for import compatibility; runtime resolution uses immutable snapshot tables.
    registry_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("registry_versions.id", ondelete="SET NULL"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class UnitName(Base):
    __tablename__ = "unit_names"
    __table_args__ = (
        UniqueConstraint("unit_id", "normalized_key", "name_type", name="uq_unit_name"),
        CheckConstraint("qa_status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_unit_name_qa"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="ck_unit_name_validity",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("un"))
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500), index=True)
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    name_type: Mapped[str] = mapped_column(String(30), default="ALIAS")
    qa_status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class UnitCode(Base):
    __tablename__ = "unit_codes"
    __table_args__ = (
        UniqueConstraint("code", "namespace", name="uq_unit_code_namespace"),
        CheckConstraint("qa_status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_unit_code_qa"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="ck_unit_code_validity",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("uc"))
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(160), index=True)
    code_type: Mapped[str] = mapped_column(String(80), default="UNIT_CODE")
    namespace: Mapped[str] = mapped_column(String(80), default="DEFAULT")
    qa_status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class RegistrySnapshotUnit(Base):
    __tablename__ = "registry_snapshot_units"
    __table_args__ = (
        Index("ix_snapshot_unit_version_normalized", "registry_version_id", "normalized_key"),
        Index("ix_snapshot_unit_version_ascii", "registry_version_id", "ascii_key"),
        Index("ix_snapshot_unit_version_org", "registry_version_id", "organization_type"),
    )
    registry_version_id: Mapped[str] = mapped_column(
        ForeignKey("registry_versions.id", ondelete="CASCADE"), primary_key=True
    )
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500))
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    organization_type: Mapped[str] = mapped_column(String(20))
    unit_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    coverage_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_unit_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RegistrySnapshotName(Base):
    __tablename__ = "registry_snapshot_names"
    __table_args__ = (Index("ix_snapshot_name_version_normalized", "registry_version_id", "normalized_key"),)
    registry_version_id: Mapped[str] = mapped_column(
        ForeignKey("registry_versions.id", ondelete="CASCADE"), primary_key=True
    )
    unit_name_id: Mapped[str] = mapped_column(
        ForeignKey("unit_names.id", ondelete="RESTRICT"), primary_key=True
    )
    unit_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500))
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    name_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RegistrySnapshotCode(Base):
    __tablename__ = "registry_snapshot_codes"
    __table_args__ = (Index("ix_snapshot_code_version_code", "registry_version_id", "code"),)
    registry_version_id: Mapped[str] = mapped_column(
        ForeignKey("registry_versions.id", ondelete="CASCADE"), primary_key=True
    )
    unit_code_id: Mapped[str] = mapped_column(
        ForeignKey("unit_codes.id", ondelete="RESTRICT"), primary_key=True
    )
    unit_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(160))
    code_type: Mapped[str] = mapped_column(String(80))
    namespace: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RegistryCandidate(Base):
    __tablename__ = "registry_candidates"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_registry_candidate_status"),
        Index("ix_registry_candidate_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("cand"))
    raw_name: Mapped[str] = mapped_column(String(1000))
    proposed_name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500), index=True)
    organization_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PersonRegistryVersion(Base):
    __tablename__ = "person_registry_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','VALIDATED','APPROVED','PUBLISHED','DEPRECATED')",
            name="ck_person_registry_version_status",
        ),
        Index(
            "uq_person_registry_single_published",
            "status",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
            sqlite_where=text("status = 'PUBLISHED'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("prv"))
    version: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (
        CheckConstraint(
            "employment_status IN ('ACTIVE','CONTRACT','TEMPORARY','INACTIVE','RETIRED','UNKNOWN')",
            name="ck_person_employment_status",
        ),
        CheckConstraint(
            "qa_status IN ('PENDING_QA','APPROVED','REJECTED')",
            name="ck_person_qa",
        ),
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_person_source_kind",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="ck_person_validity",
        ),
        CheckConstraint(
            "source_kind = 'SYNTHETIC_DEMO' OR synthetic_welfare_facts IS NULL",
            name="ck_person_synthetic_welfare_source",
        ),
        Index("ix_person_active_qa", "active", "qa_status"),
        Index("ix_person_normalized", "normalized_key"),
        Index("ix_person_ascii", "ascii_key"),
        Index("ix_person_unit", "canonical_unit_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(500), index=True)
    normalized_key: Mapped[str] = mapped_column(String(500), index=True)
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    canonical_unit_id: Mapped[str] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), index=True
    )
    subject_group_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    qa_status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    registry_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("person_registry_versions.id", ondelete="SET NULL"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    source_kind: Mapped[str] = mapped_column(String(30), default="PROVIDED", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    synthetic_welfare_facts: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)


class PersonName(Base):
    __tablename__ = "person_names"
    __table_args__ = (
        UniqueConstraint("person_id", "normalized_key", "name_type", name="uq_person_name"),
        CheckConstraint(
            "qa_status IN ('PENDING_QA','APPROVED','REJECTED')",
            name="ck_person_name_qa",
        ),
        Index("ix_person_name_normalized", "normalized_key"),
        Index("ix_person_name_ascii", "ascii_key"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("pn"))
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500), index=True)
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    name_type: Mapped[str] = mapped_column(String(30), default="ALIAS")
    qa_status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PersonCode(Base):
    __tablename__ = "person_codes"
    __table_args__ = (
        UniqueConstraint("code", "namespace", name="uq_person_code_namespace"),
        CheckConstraint(
            "qa_status IN ('PENDING_QA','APPROVED','REJECTED')",
            name="ck_person_code_qa",
        ),
        Index("ix_person_code_lookup", "code", "namespace"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("pc"))
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(160), index=True)
    code_type: Mapped[str] = mapped_column(String(80), default="PERSON_CODE")
    namespace: Mapped[str] = mapped_column(String(80), default="DEFAULT")
    qa_status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PersonRegistryCandidate(Base):
    __tablename__ = "person_registry_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_QA','APPROVED','REJECTED')",
            name="ck_person_registry_candidate_status",
        ),
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_person_registry_candidate_source_kind",
        ),
        CheckConstraint(
            "employment_status IN ('ACTIVE','CONTRACT','TEMPORARY','INACTIVE','RETIRED','UNKNOWN')",
            name="ck_person_registry_candidate_employment_status",
        ),
        Index("ix_person_registry_candidate_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("pcand"))
    raw_name: Mapped[str] = mapped_column(String(1000))
    proposed_name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500), index=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    subject_group_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    source_kind: Mapped[str] = mapped_column(String(30), default="PROVIDED")
    status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PersonRegistrySnapshot(Base):
    __tablename__ = "person_registry_snapshots"
    __table_args__ = (
        CheckConstraint(
            "employment_status IN ('ACTIVE','CONTRACT','TEMPORARY','INACTIVE','RETIRED','UNKNOWN')",
            name="ck_person_snapshot_employment_status",
        ),
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_person_snapshot_source_kind",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="ck_person_snapshot_validity",
        ),
        CheckConstraint(
            "source_kind = 'SYNTHETIC_DEMO' OR synthetic_welfare_facts IS NULL",
            name="ck_person_snapshot_synthetic_welfare_source",
        ),
        Index("ix_person_snapshot_version_normalized", "registry_version_id", "normalized_key"),
        Index("ix_person_snapshot_version_ascii", "registry_version_id", "ascii_key"),
        Index("ix_person_snapshot_version_unit", "registry_version_id", "canonical_unit_id"),
    )
    registry_version_id: Mapped[str] = mapped_column(
        ForeignKey("person_registry_versions.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500))
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_unit_id: Mapped[str] = mapped_column(String(64), index=True)
    subject_group_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(30), default="PROVIDED")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    synthetic_welfare_facts: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PersonNameSnapshot(Base):
    __tablename__ = "person_name_snapshots"
    __table_args__ = (
        Index("ix_person_name_snapshot_version_normalized", "registry_version_id", "normalized_key"),
        Index("ix_person_name_snapshot_version_ascii", "registry_version_id", "ascii_key"),
    )
    registry_version_id: Mapped[str] = mapped_column(
        ForeignKey("person_registry_versions.id", ondelete="CASCADE"), primary_key=True
    )
    person_name_id: Mapped[str] = mapped_column(
        ForeignKey("person_names.id", ondelete="RESTRICT"), primary_key=True
    )
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(500))
    normalized_key: Mapped[str] = mapped_column(String(500))
    ascii_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    name_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PersonCodeSnapshot(Base):
    __tablename__ = "person_code_snapshots"
    __table_args__ = (
        Index("ix_person_code_snapshot_version_code", "registry_version_id", "code"),
    )
    registry_version_id: Mapped[str] = mapped_column(
        ForeignKey("person_registry_versions.id", ondelete="CASCADE"), primary_key=True
    )
    person_code_id: Mapped[str] = mapped_column(
        ForeignKey("person_codes.id", ondelete="RESTRICT"), primary_key=True
    )
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(160))
    code_type: Mapped[str] = mapped_column(String(80))
    namespace: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("created_by", "idempotency_key", name="uq_case_actor_idempotency"),
        CheckConstraint(
            "workflow_status IN ('RECEIVED','PROCESSING','NEED_REVIEW','COMPLETED','FAILED')",
            name="ck_case_workflow_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("case"))
    created_by: Mapped[str] = mapped_column(String(255), index=True)
    input_type: Mapped[str] = mapped_column(String(30))
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("parse_status IN ('PENDING','PARSED','FAILED')", name="ck_document_parse_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("doc"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_uri: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    parse_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    parse_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExtractedRecord(Base):
    __tablename__ = "extracted_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("er"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    subject_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subject_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    position: Mapped[str | None] = mapped_column(String(300), nullable=True)
    current_unit_raw: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    former_units: Mapped[list] = mapped_column(JSON, default=list)
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    relation_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class VerificationResult(Base):
    __tablename__ = "verification_results"
    __table_args__ = (
        CheckConstraint("organization_type IN ('BCA','BQP','OTHER','UNKNOWN')", name="ck_result_org"),
        CheckConstraint(
            "resolution_status IN ('MATCHED','AMBIGUOUS','NOT_FOUND','CONFLICT')",
            name="ck_result_resolution",
        ),
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_result_source_kind",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("res"))
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), unique=True, index=True
    )
    unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )
    organization_type: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    resolution_status: Mapped[str] = mapped_column(String(30))
    subject_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolution_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_candidates: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    source_kind: Mapped[str] = mapped_column(String(30), default="PROVIDED")
    registry_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(100), default="taxonomy-2026.09")
    parser_version: Mapped[str] = mapped_column(String(100), default="parser-unknown")
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    threshold_version: Mapped[str] = mapped_column(String(100), default="threshold-2026.09")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_policy_source_kind",
        ),
    )
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    policy_type: Mapped[str] = mapped_column(String(100))
    subject_groups: Mapped[list] = mapped_column(JSON, default=list)
    required_fields: Mapped[list] = mapped_column(JSON, default=list)
    rule_expression: Mapped[dict] = mapped_column(JSON, default=dict)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(100), index=True)
    source_kind: Mapped[str] = mapped_column(String(30), default="OFFICIAL")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class EligibilityAssessment(Base):
    __tablename__ = "eligibility_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ELIGIBLE','NOT_ELIGIBLE','INSUFFICIENT_DATA','NOT_APPLICABLE')",
            name="ck_eligibility_status",
        ),
        CheckConstraint(
            "source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')",
            name="ck_eligibility_source_kind",
        ),
        UniqueConstraint("result_id", "policy_id", name="uq_assessment_result_policy"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("ea"))
    result_id: Mapped[str] = mapped_column(
        ForeignKey("verification_results.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("policy_rules.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_version: Mapped[str] = mapped_column(String(100))
    source_kind: Mapped[str] = mapped_column(String(30), default="OFFICIAL")


class ReviewCase(Base):
    __tablename__ = "review_cases"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')", name="ck_review_status"),
        Index("ix_review_status_created", "status", "created_at"),
        Index("ix_review_scope_status", "coverage_group", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("review"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    result_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_results.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    coverage_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BulkIngestJob(Base):
    __tablename__ = "bulk_ingest_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('UPLOADED','PROFILED','AWAITING_MAPPING','QUEUED','PROCESSING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')",
            name="ck_bulk_job_status",
        ),
        Index("ix_bulk_job_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("bulk"))
    file_name: Mapped[str] = mapped_column(String(500))
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_sha256: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="UPLOADED", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    mapping_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mapping_json: Mapped[dict] = mapped_column(JSON, default=dict)
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BulkIngestRow(Base):
    __tablename__ = "bulk_ingest_rows"
    __table_args__ = (
        UniqueConstraint("job_id", "row_index", name="uq_bulk_row_job_index"),
        CheckConstraint(
            "status IN ('PENDING','SUCCEEDED','FAILED','SKIPPED_DUPLICATE')",
            name="ck_bulk_row_status",
        ),
        Index("ix_bulk_row_job_status", "job_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("brow"))
    job_id: Mapped[str] = mapped_column(ForeignKey("bulk_ingest_jobs.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    row_hash: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class RowError(Base):
    __tablename__ = "bulk_row_errors"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("berr"))
    job_id: Mapped[str] = mapped_column(ForeignKey("bulk_ingest_jobs.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    column: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="ERROR")
    message_vi: Mapped[str] = mapped_column(Text)


class HeaderAliasCandidate(Base):
    __tablename__ = "header_alias_candidates"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_header_alias_candidate_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("hac"))
    canonical_field: Mapped[str] = mapped_column(String(100), index=True)
    alias: Mapped[str] = mapped_column(String(500), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING_QA", index=True)
    source_job_id: Mapped[str | None] = mapped_column(ForeignKey("bulk_ingest_jobs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_actor_timestamp", "actor", "timestamp"),
        Index("ix_audit_entity_timestamp", "entity_type", "entity_id", "timestamp"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("audit"))
    actor: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','SENT','FAILED')", name="ck_outbox_status"),
        Index("ix_outbox_status_available", "status", "available_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("outbox"))
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AppUser(Base):
    """A local account. Identity fields follow Vietnamese administrative practice.

    ``username`` is the account id an administrator hands to the officer; it is
    the primary key, so ``Case.created_by``/``AuditLog.actor`` keep pointing at a
    stable value even if the display name is later corrected.

    ``is_admin`` is not assignable through the API: exactly one administrator
    account exists and it is created by the seeder.
    """

    __tablename__ = "app_users"
    __table_args__ = (
        CheckConstraint("length(username) >= 3", name="ck_app_user_username_length"),
    )

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    #: Unique across accounts: one personal code identifies one officer, so two
    #: accounts holding the same one would make the audit trail ambiguous.
    #: Stored upper-cased (``auth.service.normalize_personal_code``) so the
    #: index is case-insensitive without a database-specific collation.
    personal_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, unique=True
    )
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rank: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: Unique across accounts: the issued password and every one-time sign-in
    #: code are delivered here, so a shared mailbox would let its holder sign
    #: in as either account. Stored lower-cased
    #: (``auth.service.normalize_email``).
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, unique=True
    )
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    coverage_groups: Mapped[list] = mapped_column(JSON, default=list)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UserSession(Base):
    """Server-side session. The client only ever holds an opaque random token.

    Only the SHA-256 of the token is stored, so a database read does not hand
    over live sessions. Nothing about the caller's authority travels in the
    token itself: permissions are re-read from ``app_users`` on every request,
    which is why revoking a permission takes effect immediately and why a
    tampered client cannot grant itself one.
    """

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("sess"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(
        ForeignKey("app_users.username", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LoginOtp(Base):
    """A one-time sign-in code that was mailed to an account's address.

    Only the code's PBKDF2 hash is stored, for the same reason session tokens
    are stored hashed: a database read must not hand over a live credential.
    The row is the whole state of one challenge — its expiry, how many wrong
    guesses it has absorbed, and whether it was spent — so verification is a
    single locked row update rather than a rule spread across services.

    Rows are kept after they are consumed or expire: they are what the per
    account and per address issuance budgets are counted from, which is the
    control that stops this endpoint being used to spam somebody's mailbox.
    ``purge_expired_otps`` clears them out well after both windows have passed.
    """

    __tablename__ = "login_otps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("otp"))
    username: Mapped[str] = mapped_column(
        ForeignKey("app_users.username", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
