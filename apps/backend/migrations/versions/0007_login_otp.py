"""add one-time sign-in codes

A second way in: the account's own mailbox. The table holds one row per issued
challenge — hashed code, expiry, wrong-guess counter, spent marker — and the
rows outlive the challenge on purpose, because the per-account and per-address
issuance budgets are counted from them. Without that history the endpoint would
be a way to send somebody unlimited mail.

Revision ID: 0007_login_otp
Revises: 0006_local_accounts
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_login_otp"
down_revision = "0006_local_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_otps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "username",
            sa.String(64),
            sa.ForeignKey("app_users.username", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
    )
    op.create_index("ix_login_otps_username", "login_otps", ["username"])
    op.create_index("ix_login_otps_created_at", "login_otps", ["created_at"])
    op.create_index("ix_login_otps_expires_at", "login_otps", ["expires_at"])
    op.create_index("ix_login_otps_client_ip", "login_otps", ["client_ip"])
    # The issuance budgets ask "how many did this account / this address get in
    # the last window", so both counts are served straight from an index.
    op.create_index("ix_login_otps_username_created", "login_otps", ["username", "created_at"])
    op.create_index("ix_login_otps_ip_created", "login_otps", ["client_ip", "created_at"])


def downgrade():
    op.drop_index("ix_login_otps_ip_created", table_name="login_otps")
    op.drop_index("ix_login_otps_username_created", table_name="login_otps")
    op.drop_index("ix_login_otps_client_ip", table_name="login_otps")
    op.drop_index("ix_login_otps_expires_at", table_name="login_otps")
    op.drop_index("ix_login_otps_created_at", table_name="login_otps")
    op.drop_index("ix_login_otps_username", table_name="login_otps")
    op.drop_table("login_otps")
