"""add local accounts and server-side sessions

Replaces the external identity provider with accounts an administrator issues
in-product. Permissions are stored on the account and re-read on every request,
so the session token stays an opaque id that carries no authority of its own.

Revision ID: 0006_local_accounts
Revises: 0005_person_registry
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_local_accounts"
down_revision = "0005_person_registry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_users",
        sa.Column("username", sa.String(64), primary_key=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("personal_code", sa.String(64), nullable=True),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("position", sa.String(255), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("unit_name", sa.String(500), nullable=True),
        sa.Column("rank", sa.String(120), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("coverage_groups", sa.JSON(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(username) >= 3", name="ck_app_user_username_length"),
    )
    op.create_index("ix_app_users_personal_code", "app_users", ["personal_code"])
    op.create_index("ix_app_users_is_admin", "app_users", ["is_admin"])
    op.create_index("ix_app_users_is_active", "app_users", ["is_active"])
    op.create_index("ix_app_users_created_at", "app_users", ["created_at"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "username",
            sa.String(64),
            sa.ForeignKey("app_users.username", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_user_session_token_hash"),
    )
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"])
    op.create_index("ix_user_sessions_username", "user_sessions", ["username"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_created_at", "user_sessions", ["created_at"])


def downgrade():
    op.drop_table("user_sessions")
    op.drop_table("app_users")
