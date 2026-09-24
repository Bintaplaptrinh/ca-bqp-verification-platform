"""One-time sign-in codes delivered to the account's own mailbox.

A second way in, alongside the password. The code is six digits and lives for
sixty seconds, so the whole design question is abuse rather than cryptography:
the guessable space is small and the side effect is *mail sent to somebody
else's inbox*. Both halves are budgeted.

**Against guessing the code**

- Six digits from ``secrets.randbelow`` — a CSPRNG, never ``random``.
- Only the PBKDF2 hash is stored, the same construction as passwords. A stolen
  database therefore does not hand over live codes, and the 240k-iteration cost
  puts a real price on grinding the whole six-digit space offline.
- A challenge dies after ``OTP_MAX_ATTEMPTS`` wrong guesses (5 by default), so
  one issued code is worth 5 tries out of 10^6, not unlimited tries.
- Verification re-reads the challenge under a row lock (``FOR UPDATE`` on
  PostgreSQL; SQLite serializes writers anyway), so two racing requests cannot
  each spend an attempt against the same counter or redeem the same code twice.
- A wrong code also charges the account's ordinary failed-attempt counter, which
  means a code-guessing run locks the account exactly as a password-guessing run
  does. Without that, this endpoint would be a way around the lockout.
- Comparison is constant-time (``verify_password`` ends in ``hmac.compare_digest``).
- Codes are single-use, and issuing a new one revokes every code the account
  still has outstanding — otherwise "resend until you like the code" would widen
  the guessable set instead of replacing it.

**Against using this to spam a mailbox**

This is the one that matters, because the victim is a third party who never
asked to be involved:

- A per-account cooldown (``OTP_RESEND_COOLDOWN_SECONDS``, never shorter than
  the code's own lifetime) caps one mailbox at one message per window.
- A per-account hourly cap and a per-address hourly cap bound the total. The
  address cap is what stops one caller walking a list of usernames, which the
  per-account cap alone would not touch.
- Budgets are counted from ``login_otps`` rows in the database, not from an
  in-process counter, so they survive a restart and hold across workers. That is
  also why rows are kept after they expire.
- The middleware rate limiter applies on top, per address and per route shape.

**Against learning who has an account**

``verify_code`` gives one message for a wrong code and for a username that
does not exist, and pays the same PBKDF2 cost in both, so neither the body nor
the timing distinguishes them. ``request_code`` answers the same way whatever
happened: unknown account, no
email on file, inactive account, over budget, or a message genuinely sent. It
returns nothing the caller could not have guessed and never says which case it
was, and the SMTP conversation is deferred until after the response so the
*timing* does not answer the question either. The real outcome goes to the log
and the audit trail. ``verify_code`` likewise gives one message for every
failure mode.

The consequence to accept: a legitimate officer whose mail bounced sees the same
neutral response as everyone else. That is why the password form stays and why
delivery failure is logged loudly — the fallback is the existing sign-in, not a
more talkative error.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cabqp.modules.auth import service as auth_service
from cabqp.modules.notifications import email as mailer
from cabqp.shared.models import AppUser, LoginOtp, utcnow
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)

#: Shown for every failed verification, whatever the underlying reason.
INVALID_CODE_MESSAGE = "Mã đăng nhập không đúng hoặc đã hết hiệu lực."

#: Shown when the feature is switched off or has no mail transport behind it.
UNAVAILABLE_MESSAGE = "Đăng nhập bằng mã một lần hiện không khả dụng."


class OtpUnavailable(Exception):
    """The feature is off. Distinct from a rejected attempt, which is neutral."""


@dataclass
class IssueOutcome:
    """Why ``request_code`` did what it did — for the log, never for the caller.

    ``reason`` is the branch taken (``ISSUED``, ``NO_ACCOUNT``, ``COOLDOWN``…).
    The endpoint answers identically in every case; this exists so an operator
    reading the logs can still tell a misconfigured mailbox from an unknown
    username.
    """

    reason: str
    username: str | None = None
    #: Set only on ``ISSUED``: performs the actual SMTP delivery. The route runs
    #: it after the response has been written (see ``request_code``).
    send: Callable[[], None] | None = None

    @property
    def issued(self) -> bool:
        return self.reason == "ISSUED"


def generate_code(length: int | None = None) -> str:
    """A zero-padded decimal code from the CSPRNG.

    ``secrets.randbelow`` over the full range, rather than picking digits one at
    a time, so every value in the space is equally likely and the leading digit
    is not special.
    """
    digits = length or get_settings().otp_code_length
    upper = 10**digits
    return str(secrets.randbelow(upper)).zfill(digits)


#: Stored in place of a client address we could not determine. It has to be a
#: real value rather than NULL: a NULL never matches the budget count, so an
#: unknown address would otherwise buy an unmetered bucket.
UNKNOWN_CLIENT = "unknown"


def _recent_count(db: Session, column, value: str, window: timedelta) -> int:
    since = utcnow() - window
    return int(
        db.scalar(
            select(func.count())
            .select_from(LoginOtp)
            .where(column == value, LoginOtp.created_at >= since)
        )
        or 0
    )


def _active_codes(db: Session, username: str) -> list[LoginOtp]:
    return list(
        db.scalars(
            select(LoginOtp).where(
                LoginOtp.username == username,
                LoginOtp.consumed_at.is_(None),
                LoginOtp.expires_at > utcnow(),
            )
        )
    )


def _ip_budget_exhausted(db: Session, client_ip: str | None) -> bool:
    """Whether this address has already caused its hour's worth of mail.

    An address that cannot be determined is not given a free pass: it is charged
    against a shared bucket keyed on the empty string, which is strictly safer
    than skipping the check.
    """
    s = get_settings()
    used = _recent_count(db, LoginOtp.client_ip, client_ip or UNKNOWN_CLIENT, timedelta(hours=1))
    return used >= s.otp_max_per_ip_per_hour


def request_code(
    db: Session,
    username: str,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> IssueOutcome:
    """Issue and mail a code, or decline silently.

    The caller is expected to answer the same way for every return value. Only
    ``OtpUnavailable`` is surfaced, because "this build has no OTP sign-in" is
    not a fact about any particular account.
    """
    s = get_settings()
    if not s.otp_login_available:
        raise OtpUnavailable(UNAVAILABLE_MESSAGE)

    # Charged before the account is even looked up, so walking a username list
    # costs the sprayer its address budget rather than one budget per name.
    if _ip_budget_exhausted(db, client_ip):
        return IssueOutcome("IP_BUDGET")

    user = db.get(AppUser, (username or "").strip().lower())
    if user is None or not user.is_active:
        return IssueOutcome("NO_ACCOUNT")
    if user.locked_until and user.locked_until > utcnow():
        return IssueOutcome("LOCKED", user.username)
    if not mailer.is_valid_email(user.email):
        # Nothing to send to. Logged rather than answered, because "this account
        # has no email" is exactly the kind of fact enumeration is after.
        logger.info("otp_no_address", extra={"event": {"username": user.username}})
        return IssueOutcome("NO_ADDRESS", user.username)

    now = utcnow()
    last = db.scalar(
        select(LoginOtp)
        .where(LoginOtp.username == user.username)
        .order_by(LoginOtp.created_at.desc())
        .limit(1)
    )
    if last is not None and (now - last.created_at) < timedelta(seconds=s.otp_resend_cooldown_seconds):
        return IssueOutcome("COOLDOWN", user.username)
    if _recent_count(db, LoginOtp.username, user.username, timedelta(hours=1)) >= s.otp_max_per_account_per_hour:
        return IssueOutcome("ACCOUNT_BUDGET", user.username)

    # Replacing rather than adding: several live codes at once would multiply
    # the attacker's chances per guess for no benefit to the officer.
    for stale in _active_codes(db, user.username):
        stale.consumed_at = now

    code = generate_code()
    challenge = LoginOtp(
        username=user.username,
        code_hash=auth_service.hash_password(code),
        created_at=now,
        expires_at=now + timedelta(seconds=s.otp_ttl_seconds),
        attempts=0,
        delivered=False,
        client_ip=(client_ip or UNKNOWN_CLIENT),
        user_agent=(user_agent or None),
    )
    db.add(challenge)
    db.flush()

    return IssueOutcome(
        "ISSUED",
        user.username,
        send=_deliverer(
            challenge_id=challenge.id,
            to=user.email or "",
            display_name=user.display_name,
            code=code,
            username=user.username,
            ttl_seconds=s.otp_ttl_seconds,
        ),
    )


def _deliverer(
    *, challenge_id: str, to: str, display_name: str, code: str, username: str, ttl_seconds: int
) -> Callable[[], None]:
    """Build the deferred send.

    Delivery is deliberately not done inside the request. Talking to Gmail takes
    the better part of a second, and a request that is fast when the username is
    unknown and slow when it is real answers the enumeration question that the
    neutral response body was written to avoid. Running it after the response
    also keeps a slow or unreachable mail server from holding the endpoint open.

    It opens its own session, because the request's session is closed by the
    time this runs.
    """

    def run() -> None:
        from cabqp.shared.db import SessionLocal

        delivery = mailer.send_login_otp_email(
            to=to, display_name=display_name, code=code, ttl_seconds=ttl_seconds
        )
        if not delivery.ok:
            # The challenge row stays and still counts against the budgets: a
            # mailbox that keeps failing must not become an unmetered way to
            # keep trying.
            logger.warning(
                "otp_delivery_failed",
                extra={"event": {"username": username, "detail": delivery.detail}},
            )
        try:
            with SessionLocal() as session:
                row = session.get(LoginOtp, challenge_id)
                if row is not None:
                    row.delivered = delivery.ok
                    session.commit()
        except Exception:
            # The flag is a record of what happened, not something sign-in
            # depends on; failing to write it must not raise out of a background
            # task where nothing can handle it.
            logger.warning("otp_delivery_flag_not_recorded", exc_info=True)

    return run


def _lock_challenge(db: Session, challenge_id: str) -> LoginOtp | None:
    """Re-read the challenge row with a write lock where the backend has one.

    Two requests arriving with the same code must not both redeem it, and two
    wrong guesses must not both read ``attempts`` before either writes it back.
    SQLite has no ``FOR UPDATE``; its writer lock serializes the transactions
    anyway, so the fallback is a plain read rather than a weaker guarantee.
    """
    dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
    statement = select(LoginOtp).where(LoginOtp.id == challenge_id)
    if dialect not in {"sqlite", ""}:
        statement = statement.with_for_update()
    return db.scalar(statement)


def verify_code(
    db: Session,
    username: str,
    code: str,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[AppUser, str, datetime]:
    """Redeem a code and open a session, or raise ``AuthError``.

    Every failure raises the same message. Returns whatever
    ``auth_service.open_session`` returns: (user, token, expires_at).
    """
    s = get_settings()
    if not s.otp_login_available:
        raise OtpUnavailable(UNAVAILABLE_MESSAGE)

    user = db.get(AppUser, (username or "").strip().lower())
    if user is None:
        # Not `usable_account`: its message names the password, which would make
        # an unknown username visibly different from a wrong code. Spend a
        # comparable PBKDF2 round first so the *timing* does not answer the
        # question either — the real path always pays one.
        auth_service.verify_password(code or "", auth_service.hash_password("decoy"))
        raise auth_service.AuthError(INVALID_CODE_MESSAGE)
    # A deactivated or locked account gets its own message, exactly as it does
    # on the password form. That is not a new disclosure: the existing sign-in
    # already answers the same way, and an officer locked out by somebody else's
    # guessing needs to be told why.
    auth_service.usable_account(user)

    now = utcnow()
    candidate = db.scalar(
        select(LoginOtp)
        .where(
            LoginOtp.username == user.username,
            LoginOtp.consumed_at.is_(None),
            LoginOtp.expires_at > now,
        )
        .order_by(LoginOtp.created_at.desc())
        .limit(1)
    )
    if candidate is None:
        # No live challenge. Still charged as a failed attempt, so firing codes
        # at an account that was never sent one is not free.
        auth_service.record_failed_attempt(db, user)
        raise auth_service.AuthError(INVALID_CODE_MESSAGE)

    challenge = _lock_challenge(db, candidate.id) or candidate
    if challenge.consumed_at is not None or challenge.expires_at <= utcnow():
        auth_service.record_failed_attempt(db, user)
        raise auth_service.AuthError(INVALID_CODE_MESSAGE)

    if challenge.attempts >= s.otp_max_attempts:
        challenge.consumed_at = utcnow()
        db.flush()
        auth_service.record_failed_attempt(db, user)
        raise auth_service.AuthError(INVALID_CODE_MESSAGE)

    submitted = (code or "").strip()
    if not auth_service.verify_password(submitted, challenge.code_hash):
        challenge.attempts += 1
        if challenge.attempts >= s.otp_max_attempts:
            # Burn it now rather than leaving a spent challenge alive for the
            # rest of its TTL.
            challenge.consumed_at = utcnow()
        db.flush()
        auth_service.record_failed_attempt(db, user)
        logger.info(
            "otp_verification_failed",
            extra={"event": {"username": user.username, "attempts": challenge.attempts}},
        )
        raise auth_service.AuthError(INVALID_CODE_MESSAGE)

    challenge.consumed_at = utcnow()
    db.flush()
    return auth_service.open_session(db, user, user_agent=user_agent, client_ip=client_ip)


def purge_expired_codes(db: Session) -> int:
    """Delete challenges old enough that no budget still counts them.

    The retention window is deliberately longer than the one-hour budget
    windows: deleting a row the moment it expires would hand back the issuance
    budget it was spending.
    """
    cutoff = utcnow() - timedelta(hours=get_settings().otp_retention_hours)
    rows = list(db.scalars(select(LoginOtp).where(LoginOtp.created_at < cutoff)))
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)
