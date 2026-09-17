"""input intelligence bulk ingestion

Revision ID: 0002_input_intelligence_bulk
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_input_intelligence_bulk"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bulk_ingest_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("file_sha256", sa.String(128), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mapping_version", sa.String(100), nullable=True),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('UPLOADED','PROFILED','AWAITING_MAPPING','QUEUED','PROCESSING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')", name="ck_bulk_job_status"),
    )
    op.create_index("ix_bulk_ingest_jobs_file_sha256","bulk_ingest_jobs",["file_sha256"],unique=True)
    op.create_index("ix_bulk_ingest_jobs_status","bulk_ingest_jobs",["status"])
    op.create_index("ix_bulk_ingest_jobs_created_by","bulk_ingest_jobs",["created_by"])
    op.create_index("ix_bulk_ingest_jobs_created_at","bulk_ingest_jobs",["created_at"])
    op.create_index("ix_bulk_job_status_created","bulk_ingest_jobs",["status","created_at"])
    op.create_table(
        "bulk_ingest_rows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("bulk_ingest_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("row_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("job_id","row_index",name="uq_bulk_row_job_index"),
        sa.CheckConstraint("status IN ('PENDING','SUCCEEDED','FAILED','SKIPPED_DUPLICATE')",name="ck_bulk_row_status"),
    )
    op.create_index("ix_bulk_ingest_rows_job_id","bulk_ingest_rows",["job_id"])
    op.create_index("ix_bulk_ingest_rows_row_hash","bulk_ingest_rows",["row_hash"])
    op.create_index("ix_bulk_ingest_rows_status","bulk_ingest_rows",["status"])
    op.create_index("ix_bulk_row_job_status","bulk_ingest_rows",["job_id","status"])
    op.create_table(
        "bulk_row_errors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("bulk_ingest_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("column", sa.String(500), nullable=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message_vi", sa.Text(), nullable=False),
    )
    op.create_index("ix_bulk_row_errors_job_id","bulk_row_errors",["job_id"])
    op.create_index("ix_bulk_row_errors_code","bulk_row_errors",["code"])
    op.create_table(
        "header_alias_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("canonical_field", sa.String(100), nullable=False),
        sa.Column("alias", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_job_id", sa.String(64), sa.ForeignKey("bulk_ingest_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('PENDING_QA','APPROVED','REJECTED')", name="ck_header_alias_candidate_status"),
    )
    op.create_index("ix_header_alias_candidates_canonical_field","header_alias_candidates",["canonical_field"])
    op.create_index("ix_header_alias_candidates_alias","header_alias_candidates",["alias"])
    op.create_index("ix_header_alias_candidates_status","header_alias_candidates",["status"])


def downgrade():
    op.drop_table("header_alias_candidates")
    op.drop_table("bulk_row_errors")
    op.drop_table("bulk_ingest_rows")
    op.drop_table("bulk_ingest_jobs")
