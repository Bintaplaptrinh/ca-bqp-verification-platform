"""add independent person registry with QA/versioned snapshots

Revision ID: 0005_person_registry
Revises: 0004_audit_append_only
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_person_registry"
down_revision = "0004_audit_append_only"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "person_registry_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT','VALIDATED','APPROVED','PUBLISHED','DEPRECATED')",
            name="ck_person_registry_version_status",
        ),
        sa.UniqueConstraint("version", name="uq_person_registry_version"),
    )
    op.create_index("ix_person_registry_versions_version", "person_registry_versions", ["version"])
    op.create_index("ix_person_registry_versions_status", "person_registry_versions", ["status"])
    op.create_index("ix_person_registry_versions_created_at", "person_registry_versions", ["created_at"])
    op.create_index(
        "uq_person_registry_single_published",
        "person_registry_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
        sqlite_where=sa.text("status = 'PUBLISHED'"),
    )

    op.create_table(
        "persons",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("normalized_key", sa.String(500), nullable=False),
        sa.Column("ascii_key", sa.String(500), nullable=True),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("canonical_unit_id", sa.String(64), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject_group_hint", sa.String(100), nullable=True),
        sa.Column("employment_status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("qa_status", sa.String(30), nullable=False, server_default="PENDING_QA"),
        sa.Column("registry_version_id", sa.String(64), sa.ForeignKey("person_registry_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_kind", sa.String(30), nullable=False, server_default="PROVIDED"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("synthetic_welfare_facts", sa.JSON(none_as_null=True), nullable=True),
        sa.CheckConstraint("employment_status IN ('ACTIVE','CONTRACT','TEMPORARY','INACTIVE','RETIRED','UNKNOWN')", name="ck_person_employment_status"),
        sa.CheckConstraint("qa_status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_person_qa"),
        sa.CheckConstraint("source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')", name="ck_person_source_kind"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to", name="ck_person_validity"),
        sa.CheckConstraint("source_kind = 'SYNTHETIC_DEMO' OR synthetic_welfare_facts IS NULL", name="ck_person_synthetic_welfare_source"),
    )
    for name, cols in [
        ("ix_person_active_qa", ["active", "qa_status"]),
        ("ix_person_normalized", ["normalized_key"]),
        ("ix_person_ascii", ["ascii_key"]),
        ("ix_person_unit", ["canonical_unit_id"]),
        ("ix_persons_full_name", ["full_name"]),
        ("ix_persons_birth_year", ["birth_year"]),
        ("ix_persons_employment_status", ["employment_status"]),
        ("ix_persons_source_kind", ["source_kind"]),
        ("ix_persons_active", ["active"]),
    ]:
        op.create_index(name, "persons", cols)

    op.create_table(
        "person_names",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("person_id", sa.String(64), sa.ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("normalized_key", sa.String(500), nullable=False),
        sa.Column("ascii_key", sa.String(500), nullable=True),
        sa.Column("name_type", sa.String(30), nullable=False, server_default="ALIAS"),
        sa.Column("qa_status", sa.String(30), nullable=False, server_default="PENDING_QA"),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("person_id", "normalized_key", "name_type", name="uq_person_name"),
        sa.CheckConstraint("qa_status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_person_name_qa"),
    )
    op.create_index("ix_person_names_person_id", "person_names", ["person_id"])
    op.create_index("ix_person_name_normalized", "person_names", ["normalized_key"])
    op.create_index("ix_person_name_ascii", "person_names", ["ascii_key"])
    op.create_index("ix_person_names_qa_status", "person_names", ["qa_status"])

    op.create_table(
        "person_codes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("person_id", sa.String(64), sa.ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(160), nullable=False),
        sa.Column("code_type", sa.String(80), nullable=False, server_default="PERSON_CODE"),
        sa.Column("namespace", sa.String(80), nullable=False, server_default="DEFAULT"),
        sa.Column("qa_status", sa.String(30), nullable=False, server_default="PENDING_QA"),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code", "namespace", name="uq_person_code_namespace"),
        sa.CheckConstraint("qa_status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_person_code_qa"),
    )
    op.create_index("ix_person_codes_person_id", "person_codes", ["person_id"])
    op.create_index("ix_person_codes_code", "person_codes", ["code"])
    op.create_index("ix_person_code_lookup", "person_codes", ["code", "namespace"])
    op.create_index("ix_person_codes_qa_status", "person_codes", ["qa_status"])

    op.create_table(
        "person_registry_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("raw_name", sa.String(1000), nullable=False),
        sa.Column("proposed_name", sa.String(500), nullable=False),
        sa.Column("normalized_key", sa.String(500), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("canonical_unit_id", sa.String(64), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("subject_group_hint", sa.String(100), nullable=True),
        sa.Column("employment_status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_kind", sa.String(30), nullable=False, server_default="PROVIDED"),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_QA"),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_person_registry_candidate_status"),
        sa.CheckConstraint("source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')", name="ck_person_registry_candidate_source_kind"),
        sa.CheckConstraint("employment_status IN ('ACTIVE','CONTRACT','TEMPORARY','INACTIVE','RETIRED','UNKNOWN')", name="ck_person_registry_candidate_employment_status"),
    )
    op.create_index("ix_person_registry_candidate_status_created", "person_registry_candidates", ["status", "created_at"])
    op.create_index("ix_person_registry_candidates_normalized_key", "person_registry_candidates", ["normalized_key"])
    op.create_index("ix_person_registry_candidates_canonical_unit_id", "person_registry_candidates", ["canonical_unit_id"])

    op.create_table(
        "person_registry_snapshots",
        sa.Column("registry_version_id", sa.String(64), sa.ForeignKey("person_registry_versions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_id", sa.String(64), sa.ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("normalized_key", sa.String(500), nullable=False),
        sa.Column("ascii_key", sa.String(500), nullable=True),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("canonical_unit_id", sa.String(64), nullable=False),
        sa.Column("subject_group_hint", sa.String(100), nullable=True),
        sa.Column("employment_status", sa.String(30), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("synthetic_welfare_facts", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("included_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("employment_status IN ('ACTIVE','CONTRACT','TEMPORARY','INACTIVE','RETIRED','UNKNOWN')", name="ck_person_snapshot_employment_status"),
        sa.CheckConstraint("source_kind IN ('OFFICIAL','PROVIDED','SYNTHETIC_DEMO')", name="ck_person_snapshot_source_kind"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to", name="ck_person_snapshot_validity"),
        sa.CheckConstraint("source_kind = 'SYNTHETIC_DEMO' OR synthetic_welfare_facts IS NULL", name="ck_person_snapshot_synthetic_welfare_source"),
    )
    op.create_index("ix_person_snapshot_version_normalized", "person_registry_snapshots", ["registry_version_id", "normalized_key"])
    op.create_index("ix_person_snapshot_version_ascii", "person_registry_snapshots", ["registry_version_id", "ascii_key"])
    op.create_index("ix_person_snapshot_version_unit", "person_registry_snapshots", ["registry_version_id", "canonical_unit_id"])
    op.create_index("ix_person_registry_snapshots_canonical_unit_id", "person_registry_snapshots", ["canonical_unit_id"])

    op.create_table(
        "person_name_snapshots",
        sa.Column("registry_version_id", sa.String(64), sa.ForeignKey("person_registry_versions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_name_id", sa.String(64), sa.ForeignKey("person_names.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("person_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("normalized_key", sa.String(500), nullable=False),
        sa.Column("ascii_key", sa.String(500), nullable=True),
        sa.Column("name_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("included_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_person_name_snapshot_version_normalized", "person_name_snapshots", ["registry_version_id", "normalized_key"])
    op.create_index("ix_person_name_snapshot_version_ascii", "person_name_snapshots", ["registry_version_id", "ascii_key"])
    op.create_index("ix_person_name_snapshots_person_id", "person_name_snapshots", ["person_id"])

    op.create_table(
        "person_code_snapshots",
        sa.Column("registry_version_id", sa.String(64), sa.ForeignKey("person_registry_versions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_code_id", sa.String(64), sa.ForeignKey("person_codes.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("person_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(160), nullable=False),
        sa.Column("code_type", sa.String(80), nullable=False),
        sa.Column("namespace", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("included_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_person_code_snapshot_version_code", "person_code_snapshots", ["registry_version_id", "code"])
    op.create_index("ix_person_code_snapshots_person_id", "person_code_snapshots", ["person_id"])


def downgrade():
    op.drop_table("person_code_snapshots")
    op.drop_table("person_name_snapshots")
    op.drop_table("person_registry_snapshots")
    op.drop_table("person_registry_candidates")
    op.drop_table("person_codes")
    op.drop_table("person_names")
    op.drop_table("persons")
    op.drop_table("person_registry_versions")
