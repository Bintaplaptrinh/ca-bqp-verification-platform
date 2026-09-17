"""enforce append-only business audit

The audit trail is the record of who decided what about a person's force attribution.
Application code only ever inserts, but nothing stopped a stray UPDATE/DELETE — a direct
statement silently rewrote or removed history. A trigger makes the guarantee the database's
rather than a convention the next change could forget.

Revision ID: 0004_audit_append_only
Revises: 0003_ascii_folded_resolution
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_audit_append_only"
down_revision = "0003_ascii_folded_resolution"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite is used for unit tests only and has no comparable privilege model; the
    # production guarantee is the PostgreSQL trigger below.
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION cabqp_audit_logs_append_only()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION
                    'audit_logs is append-only: % is not permitted', TG_OP
                    USING ERRCODE = 'restrict_violation';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER cabqp_audit_logs_no_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION cabqp_audit_logs_append_only();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER cabqp_audit_logs_no_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION cabqp_audit_logs_append_only();
            """
        )
    )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text("DROP TRIGGER IF EXISTS cabqp_audit_logs_no_delete ON audit_logs"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS cabqp_audit_logs_no_update ON audit_logs"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS cabqp_audit_logs_append_only()"))
