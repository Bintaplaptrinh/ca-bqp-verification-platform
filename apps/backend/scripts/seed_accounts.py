"""Seed the two accounts the platform is delivered with.

- ``admin`` / ``admin`` — the sole administrator. There is no API that creates
  another one, so this script is the only path to system-wide authority.
- ``user`` / ``user`` — the default tra cứu account, holding ``USER_PRESET``.

Re-running is safe: an existing account keeps its password and permissions
unless ``--force-password`` is passed, so a seed never silently resets an
account an operator has already handed out.

Both fixed passwords are development defaults. The script refuses to run
against ``APP_ENV=production`` unless ``SEED_ALLOW_PRODUCTION=true``, and
prints a warning either way.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect

_here = Path(__file__).resolve()
_candidate_root = _here.parents[3] if len(_here.parents) > 3 else None
if _candidate_root is not None and (_candidate_root / "apps/backend/src").is_dir():
    sys.path.insert(0, str(_candidate_root / "apps/backend/src"))

from cabqp.modules.auth import permissions as perms  # noqa: E402
from cabqp.modules.auth import service as auth_service  # noqa: E402
from cabqp.shared.db import SessionLocal, engine  # noqa: E402
from cabqp.shared.models import AppUser  # noqa: E402
from cabqp.shared.settings import get_settings  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
USER_USERNAME = "user"
USER_PASSWORD = "user"


def require_migrated_schema() -> None:
    tables = set(inspect(engine).get_table_names())
    if "app_users" not in tables:
        raise RuntimeError(
            "Database schema is not migrated. Run `alembic upgrade head` before seeding accounts."
        )


def _ensure(
    db,
    *,
    username: str,
    password: str,
    display_name: str,
    is_admin: bool,
    permissions: list[str],
    position: str,
    department: str,
    force_password: bool,
) -> str:
    existing = db.get(AppUser, username)
    if existing is not None:
        if force_password:
            auth_service.set_password(
                db, existing, password, must_change=False, enforce_password_policy=False
            )
            return "password-reset"
        return "exists"

    auth_service.create_user(
        db,
        username=username,
        display_name=display_name,
        password=password,
        permissions=permissions,
        is_admin=is_admin,
        position=position,
        department=department,
        # A delivered default account is usable immediately; accounts an
        # administrator issues later do require a first-login change.
        must_change_password=False,
        created_by="system",
        # The delivered demo credentials are deliberately shorter than the
        # policy a person's own password must satisfy.
        enforce_password_policy=False,
        # These two accounts are handed over in the README rather than emailed,
        # so they are the only ones allowed to exist without an address.
        require_email=False,
    )
    return "created"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-password",
        action="store_true",
        help="Reset admin/user back to their default passwords even if the accounts exist",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.is_production and not settings.seed_allow_production:
        raise SystemExit(
            "Refusing to seed default accounts in production. "
            "Set SEED_ALLOW_PRODUCTION=true only if you intend to, then change both passwords."
        )

    require_migrated_schema()
    db = SessionLocal()
    try:
        admin_state = _ensure(
            db,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Quản trị hệ thống",
            is_admin=True,
            permissions=sorted(perms.ALL_PERMISSIONS),
            position="Quản trị viên",
            department="Quản trị hệ thống",
            force_password=args.force_password,
        )
        user_state = _ensure(
            db,
            username=USER_USERNAME,
            password=USER_PASSWORD,
            display_name="Cán bộ tra cứu",
            is_admin=False,
            permissions=list(perms.USER_PRESET),
            position="Cán bộ tra cứu",
            department="Phòng nghiệp vụ",
            force_password=args.force_password,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"admin/{ADMIN_PASSWORD}: {admin_state}")
    print(f"user/{USER_PASSWORD}: {user_state}")
    print(
        "WARNING: both accounts use well-known development passwords. "
        "Change them before this instance is reachable by anyone else."
    )


if __name__ == "__main__":
    main()
