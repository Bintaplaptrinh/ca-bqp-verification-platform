"""Local account and session management.

Passwords are stored as PBKDF2-HMAC-SHA256 with a per-password random salt, in
a self-describing ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` string, so the
iteration count can be raised later without invalidating existing rows.

Sessions are opaque: the client receives 32 random bytes and the server keeps
only their SHA-256. Authority is never carried in the token — every request
re-reads the account row — so deactivating an account or removing a permission
takes effect on the next call rather than at the next token expiry.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.auth import permissions as perms
from cabqp.modules.notifications.email import is_valid_email
from cabqp.shared.models import AppUser, UserSession, utcnow
from cabqp.shared.settings import get_settings

if TYPE_CHECKING:
    from passwordgen import PasswordGenerator

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 240_000
_ALGORITHM = "pbkdf2_sha256"

#: Issued-password shape. 16 characters over the generator's full symbol set is
#: ~103 bits of entropy; ambiguous glyphs (0/O, 1/l/I) are excluded because the
#: password is read out of an email and retyped.
GENERATED_PASSWORD_LENGTH = 16

MAX_FAILED_ATTEMPTS = 8
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 6

#: Fallback when settings are unavailable; SESSION_HOURS setting is authoritative.
SESSION_HOURS = 12


def session_lifetime() -> timedelta:
    return timedelta(hours=get_settings().session_hours or SESSION_HOURS)


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"{_ALGORITHM}${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def _generator(length: int = GENERATED_PASSWORD_LENGTH) -> PasswordGenerator:
    from passwordgen import PasswordGenerator

    return PasswordGenerator(
        length=length,
        uppercase=True,
        lowercase=True,
        digits=True,
        symbols=True,
        exclude_ambiguous=True,
    )


def generate_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    """Generate an issued password with `passwordgen`'s CSPRNG generator.

    Delegated to https://github.com/Kagias/secure-password-generator rather than
    rolled here so the character-class handling and entropy accounting have one
    owner. Install it from that Git URL: the `passwordgen` name on PyPI is an
    unrelated package.
    """
    return _generator(length).generate()


def password_entropy_bits(length: int = GENERATED_PASSWORD_LENGTH) -> float:
    """Entropy of an issued password, for the audit record.

    This describes the generator's configuration, not any particular password,
    so it is safe to persist.
    """
    return round(_generator(length).entropy_bits, 1)


# --- Usernames ---------------------------------------------------------------


def _strip_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.replace("Đ", "D").replace("đ", "d"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def suggest_username(*, personal_code: str | None, display_name: str) -> str:
    """Derive a login id from the administrative identifiers.

    The personnel code wins when present: it is the identifier the officer
    already carries. Otherwise the name is folded to ASCII in Vietnamese order
    (given name first, then the initials of the remaining words) so
    "Nguyễn Văn Hùng" becomes "hungnv" rather than a collision-prone "nguyen".
    """
    if personal_code and personal_code.strip():
        candidate = re.sub(r"[^A-Za-z0-9]+", "", _strip_diacritics(personal_code)).lower()
        if len(candidate) >= 3:
            return candidate[:64]

    words = [w for w in re.split(r"\s+", _strip_diacritics(display_name).strip()) if w]
    if not words:
        return ""
    given = re.sub(r"[^A-Za-z0-9]+", "", words[-1]).lower()
    initials = "".join(re.sub(r"[^A-Za-z0-9]+", "", w)[:1] for w in words[:-1]).lower()
    return f"{given}{initials}"[:64]


_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def validate_username(username: str) -> str:
    value = (username or "").strip().lower()
    if not _USERNAME_RE.match(value):
        raise ValueError(
            "Tên đăng nhập phải từ 3-64 ký tự, bắt đầu bằng chữ/số, chỉ gồm chữ thường, số và . _ -"
        )
    return value


def allocate_username(db: Session, base: str) -> str:
    """Return ``base``, or ``base2``/``base3``… when it is already taken."""
    base = validate_username(base)
    if db.get(AppUser, base) is None:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[: 64 - len(str(suffix))]}{suffix}"
        if db.get(AppUser, candidate) is None:
            return candidate
    raise ValueError("Không thể cấp phát tên đăng nhập; vui lòng nhập thủ công")


# --- Accounts ----------------------------------------------------------------


def create_user(
    db: Session,
    *,
    username: str,
    display_name: str,
    password: str | None = None,
    permissions: list[str] | None = None,
    coverage_groups: list[str] | None = None,
    personal_code: str | None = None,
    birth_year: int | None = None,
    position: str | None = None,
    department: str | None = None,
    unit_name: str | None = None,
    rank: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    is_admin: bool = False,
    must_change_password: bool = True,
    created_by: str | None = None,
    enforce_password_policy: bool = True,
    require_email: bool = True,
) -> tuple[AppUser, str]:
    """Create an account and return it with the plaintext password.

    The plaintext is returned exactly once, to be shown to the administrator who
    created the account. It is never stored and cannot be read back afterwards.
    """
    username = validate_username(username)
    if db.get(AppUser, username) is not None:
        raise ValueError(f"Tài khoản '{username}' đã tồn tại")
    if not (display_name or "").strip():
        raise ValueError("Họ và tên không được để trống")
    # The issued password is delivered by email, so an account with no reachable
    # address cannot be handed over at all. The seeder's delivered accounts are
    # the one exception and pass require_email=False.
    if require_email and not is_valid_email(email):
        raise ValueError("Thư điện tử không hợp lệ hoặc chưa được nhập")

    plaintext = password or generate_password()
    if enforce_password_policy and len(plaintext) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    if not plaintext:
        raise ValueError("Mật khẩu không được để trống")

    user = AppUser(
        username=username,
        password_hash=hash_password(plaintext),
        display_name=display_name.strip(),
        personal_code=(personal_code or None),
        birth_year=birth_year,
        position=(position or None),
        department=(department or None),
        unit_name=(unit_name or None),
        rank=(rank or None),
        phone=(phone or None),
        email=((email or "").strip() or None),
        permissions=(
            sorted(perms.ALL_PERMISSIONS)
            if is_admin
            else perms.normalize(permissions if permissions is not None else perms.USER_PRESET)
        ),
        coverage_groups=[x for x in (coverage_groups or []) if str(x).strip()],
        is_admin=is_admin,
        is_active=True,
        must_change_password=must_change_password,
        created_by=created_by,
    )
    db.add(user)
    db.flush()
    return user, plaintext


def set_password(
    db: Session,
    user: AppUser,
    password: str,
    *,
    must_change: bool = False,
    enforce_password_policy: bool = True,
) -> None:
    """Set a password.

    ``enforce_password_policy=False`` exists for the seeder, which installs the
    documented ``admin``/``user`` demo credentials. Nothing a person types goes
    through that path: the change-password endpoint and the generator both keep
    the minimum length.
    """
    if not password:
        raise ValueError("Mật khẩu không được để trống")
    if enforce_password_policy and len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    user.password_hash = hash_password(password)
    user.must_change_password = must_change
    user.failed_attempts = 0
    user.locked_until = None
    db.flush()


def reset_password(db: Session, user: AppUser) -> str:
    plaintext = generate_password()
    set_password(db, user, plaintext, must_change=True)
    revoke_all_sessions(db, user.username)
    return plaintext


# --- Sessions ----------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthError(Exception):
    """Authentication failed. The message is safe to show to the caller."""


def record_failed_attempt(db: Session, user: AppUser) -> None:
    """Charge one failure against an account, locking it out at the cap.

    Shared by password and one-time-code sign-in: a code-guessing run must cost
    an account the same as a password-guessing run, or the new endpoint would be
    a way around the lockout.
    """
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        user.failed_attempts = 0
    db.flush()


def authenticate(
    db: Session,
    username: str,
    password: str,
    *,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[AppUser, str, datetime]:
    """Verify credentials and open a session. Returns (user, token, expires_at)."""
    user = db.get(AppUser, (username or "").strip().lower())

    if user is None:
        # Spend comparable time on an unknown account so response timing does
        # not tell an attacker which usernames exist.
        verify_password(password or "", hash_password("decoy"))
    usable_account(user)
    assert user is not None  # usable_account raises on None; this is for mypy

    if not verify_password(password or "", user.password_hash):
        record_failed_attempt(db, user)
        raise AuthError("Tên đăng nhập hoặc mật khẩu không đúng")

    return open_session(db, user, user_agent=user_agent, client_ip=client_ip)


def usable_account(user: AppUser | None) -> None:
    """Raise if this account cannot sign in right now, whatever the method.

    Shared by password and one-time-code sign-in so a deactivated or locked-out
    account cannot be let in through the newer door.
    """
    if user is None:
        raise AuthError("Tên đăng nhập hoặc mật khẩu không đúng")
    if not user.is_active:
        raise AuthError("Tài khoản đã bị khóa. Liên hệ quản trị viên.")
    if user.locked_until and user.locked_until > utcnow():
        raise AuthError("Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau ít phút.")


def open_session(
    db: Session,
    user: AppUser,
    *,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[AppUser, str, datetime]:
    """Clear the failure counters and issue a session token.

    Every way of signing in ends here, so SINGLE_ACTIVE_SESSION, the lockout
    reset and the session row have one implementation rather than one per
    authentication method.
    """
    now = utcnow()
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    if get_settings().single_active_session:
        # One live session per account: signing in here ends every session this
        # account already holds, so the same credentials cannot be used from two
        # devices at once and a forgotten sign-in elsewhere stops working the
        # moment the owner signs in again. Sessions carry no claims and are
        # re-read from the database per request, so the revocation takes effect
        # on the other device's very next call.
        revoked = revoke_all_sessions(db, user.username)
        if revoked:
            logger.info(
                "prior_sessions_revoked_on_login",
                extra={"event": {"username": user.username, "revoked": revoked}},
            )

    token = secrets.token_urlsafe(32)
    expires_at = now + session_lifetime()
    db.add(
        UserSession(
            token_hash=_token_hash(token),
            username=user.username,
            expires_at=expires_at,
            user_agent=(user_agent or None),
            client_ip=(client_ip or None),
        )
    )
    db.flush()
    return user, token, expires_at


def resolve_session(db: Session, token: str) -> tuple[AppUser, UserSession] | None:
    """Return the account behind a session token, or None when unusable."""
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if session is None or session.revoked_at is not None:
        return None
    now = utcnow()
    if session.expires_at <= now:
        return None
    user = db.get(AppUser, session.username)
    if user is None or not user.is_active:
        return None
    session.last_seen_at = now
    return user, session


def revoke_session(db: Session, token: str) -> bool:
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if session is None or session.revoked_at is not None:
        return False
    session.revoked_at = utcnow()
    db.flush()
    return True


def revoke_all_sessions(db: Session, username: str) -> int:
    now = utcnow()
    rows = list(
        db.scalars(
            select(UserSession).where(
                UserSession.username == username, UserSession.revoked_at.is_(None)
            )
        )
    )
    for row in rows:
        row.revoked_at = now
    db.flush()
    return len(rows)


def delete_user(db: Session, user: AppUser) -> int:
    """Remove an account and every session it holds.

    Cases and audit rows record the actor as a plain username string rather than
    a foreign key, so they are untouched: deleting the account does not erase
    what it did, which is the point of an append-only audit.
    """
    revoked = revoke_all_sessions(db, user.username)
    db.delete(user)
    db.flush()
    return revoked


def purge_expired_sessions(db: Session) -> int:
    rows = list(db.scalars(select(UserSession).where(UserSession.expires_at <= utcnow())))
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)


# --- Effective authority -----------------------------------------------------


def effective_permissions(user: AppUser) -> set[str]:
    """Permissions actually in force for an account.

    The administrator account holds the whole catalog implicitly, so a
    permission added to the catalog later never leaves the system without an
    account that can use it.
    """
    if user.is_admin:
        return set(perms.ALL_PERMISSIONS)
    return set(perms.normalize(user.permissions))
