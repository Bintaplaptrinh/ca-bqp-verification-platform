"""one mailbox and one personal code per account

Two accounts sharing an address means the issued password and every one-time
sign-in code for both land in the same inbox, so whoever holds it can sign in as
either. Two accounts sharing a personal code make the audit trail ambiguous:
``AuditLog.actor`` points at a username, and the code is what ties that back to
a person.

Both columns are normalized first (addresses lower-cased, codes upper-cased,
blanks to NULL) so the plain unique index is case-insensitive without depending
on a database-specific collation, matching ``auth.service.normalize_email`` /
``normalize_personal_code``. NULL stays distinct from NULL in both SQLite and
PostgreSQL, so accounts with neither field set are unaffected.

If real duplicates survive normalization the upgrade stops and names them
rather than dropping or renaming somebody's account on its own.

Revision ID: 0008_unique_account_identity
Revises: 0007_login_otp
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_unique_account_identity"
down_revision = "0007_login_otp"
branch_labels = None
depends_on = None


def _fail_on_duplicates(bind, column: str, label: str) -> None:
    rows = bind.execute(
        sa.text(
            f"SELECT {column} AS value, COUNT(*) AS n FROM app_users "
            f"WHERE {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*) > 1"
        )
    ).all()
    if not rows:
        return
    listed = ", ".join(f"{r.value} ({r.n} tài khoản)" for r in rows)
    raise RuntimeError(
        f"Không thể áp dụng ràng buộc duy nhất cho {label}: đang có giá trị trùng: {listed}. "
        "Hãy sửa hoặc vô hiệu hóa các tài khoản trùng rồi chạy lại migration."
    )


def upgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE app_users SET email = "
            "CASE WHEN TRIM(email) = '' THEN NULL ELSE LOWER(TRIM(email)) END "
            "WHERE email IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE app_users SET personal_code = "
            "CASE WHEN TRIM(personal_code) = '' THEN NULL ELSE UPPER(TRIM(personal_code)) END "
            "WHERE personal_code IS NOT NULL"
        )
    )
    _fail_on_duplicates(bind, "email", "thư điện tử")
    _fail_on_duplicates(bind, "personal_code", "mã số cán bộ")

    # personal_code already carried a plain index from 0006; replace it with the
    # unique one rather than leaving both.
    with op.batch_alter_table("app_users") as batch:
        batch.drop_index("ix_app_users_personal_code")
        batch.create_index("ix_app_users_personal_code", ["personal_code"], unique=True)
        batch.create_index("ix_app_users_email", ["email"], unique=True)


def downgrade():
    with op.batch_alter_table("app_users") as batch:
        batch.drop_index("ix_app_users_email")
        batch.drop_index("ix_app_users_personal_code")
        batch.create_index("ix_app_users_personal_code", ["personal_code"], unique=False)
