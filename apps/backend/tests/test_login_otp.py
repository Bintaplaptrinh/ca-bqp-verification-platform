"""One-time sign-in codes.

These tests are written against the properties the feature exists to hold, not
against its current output: a code expires, is single-use, cannot be ground
down, cannot be used to find out which usernames exist, and cannot be used to
send somebody unlimited mail. Each test names the failure it is guarding
against.

The code itself is never returned by the API, so the tests read it out of the
captured message the same way `test_local_auth.py` reads an issued password —
which also proves the code really travels by mail and nowhere else.
"""

from __future__ import annotations

import re
from datetime import timedelta

import mail_stub
import pytest
from fastapi.testclient import TestClient

from cabqp.modules.auth import otp as otp_service
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth import service as auth_service
from cabqp.shared.models import AppUser, LoginOtp, utcnow
from cabqp.shared.settings import get_settings

OFFICER = "otpuser"
OFFICER_EMAIL = "otpuser@cabqp.local"


@pytest.fixture
def client(monkeypatch, app_database):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OTP_LOGIN_ENABLED", "true")
    get_settings.cache_clear()
    from cabqp.main import app

    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def officer(app_database):
    """One account with a mailbox, and no OTP history."""
    from cabqp.shared.db import SessionLocal

    with SessionLocal() as session:
        session.query(LoginOtp).delete()
        session.query(AppUser).delete()
        auth_service.create_user(
            session,
            username=OFFICER,
            display_name="Cán bộ Mã Một Lần",
            password="mat-khau-cu",
            email=OFFICER_EMAIL,
            permissions=list(perms.USER_PRESET),
            must_change_password=False,
        )
        session.commit()
    yield


def _sent_code() -> str:
    """The code out of the message that was actually handed to SMTP."""
    assert mail_stub.SENT, "no message was sent"
    message = mail_stub.SENT[-1]
    assert message["To"] == OFFICER_EMAIL
    text = message.get_body(preferencelist=("plain",)).get_content()
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"no six-digit code in the delivered message:\n{text}"
    return match.group(1)


def _request(client, username: str = OFFICER):
    response = client.post("/api/v1/auth/otp/request", json={"username": username})
    assert response.status_code == 200, response.text
    return response.json()


def _verify(client, code: str, username: str = OFFICER):
    return client.post("/api/v1/auth/otp/verify", json={"username": username, "code": code})


def _age_challenges(seconds: int = 120) -> None:
    """Move every existing challenge back in time.

    This is how a test asks for a *second* code without deleting the history:
    deleting it would also hand back the hourly budgets, which several of these
    tests are specifically measuring. Ageing only clears the cooldown.
    """
    from cabqp.shared.db import SessionLocal

    with SessionLocal() as session:
        for row in session.query(LoginOtp).all():
            row.created_at = row.created_at - timedelta(seconds=seconds)
            row.expires_at = row.expires_at - timedelta(seconds=seconds)
        session.commit()


# --- The happy path ----------------------------------------------------------


def test_a_mailed_code_signs_the_officer_in(client, officer):
    _request(client)
    response = _verify(client, _sent_code())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["username"] == OFFICER
    # The session is a real one: it works on an authenticated route.
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == OFFICER


def test_the_code_is_never_in_the_response_body(client, officer):
    """The code's whole value is that it travels out of band."""
    body = _request(client)
    code = _sent_code()
    assert code not in str(body)
    assert "code" not in body


def test_the_code_is_not_in_the_subject_line(client, officer):
    """Subject lines show on lock screens, which is the shoulder-surfing path."""
    _request(client)
    message = mail_stub.SENT[-1]
    assert _sent_code() not in str(message["Subject"])


def test_the_message_is_multipart_with_an_inline_logo(client, officer):
    _request(client)
    message = mail_stub.SENT[-1]
    types = {part.get_content_type() for part in message.walk()}
    assert "text/plain" in types, "the plain-text alternative must survive"
    assert "text/html" in types
    assert "image/png" in types, "the logo must travel with the message"
    # The HTML references the logo by content id, not by a URL that would be
    # blocked or would stop resolving.
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "cid:" in html
    logo = [p for p in message.walk() if p.get_content_type() == "image/png"][0]
    assert logo.get("Content-ID", "").strip("<>") in html


# --- Guessing the code -------------------------------------------------------


def test_a_wrong_code_is_rejected_with_a_neutral_message(client, officer):
    _request(client)
    response = _verify(client, "000000")
    assert response.status_code == 401
    assert response.json()["detail"] == otp_service.INVALID_CODE_MESSAGE


def test_a_code_dies_after_the_attempt_cap_even_while_still_fresh(client, officer):
    """Otherwise 60 seconds is enough to walk a meaningful slice of 10^6."""
    _request(client)
    code = _sent_code()
    cap = get_settings().otp_max_attempts
    for i in range(cap):
        wrong = f"{(int(code) + i + 1) % 1_000_000:06d}"
        assert _verify(client, wrong).status_code == 401
    # The real code no longer works: the challenge was burned, not just counted.
    assert _verify(client, code).status_code == 401


def test_a_code_cannot_be_used_twice(client, officer):
    _request(client)
    code = _sent_code()
    assert _verify(client, code).status_code == 200
    assert _verify(client, code).status_code == 401


def test_an_expired_code_is_refused(client, officer, app_database):
    from cabqp.shared.db import SessionLocal

    _request(client)
    code = _sent_code()
    with SessionLocal() as session:
        challenge = session.query(LoginOtp).one()
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    assert _verify(client, code).status_code == 401


def test_issuing_a_new_code_kills_the_previous_one(client, officer):
    """"Resend until you like the code" must replace, not accumulate.

    Two live codes at once would double a guesser's chance per attempt for no
    benefit to the officer. The first code is aged only far enough to clear the
    cooldown, so it is still inside its own TTL when the second is issued.
    """
    _request(client)
    first = _sent_code()
    _age_challenges(seconds=65)
    _request(client)
    second = _sent_code()

    assert first != second
    assert _verify(client, first).status_code == 401, "the superseded code must be dead"
    assert _verify(client, second).status_code == 200


def test_code_guessing_locks_the_account_like_password_guessing(client, officer):
    """Without this the OTP endpoint is a way around the account lockout."""
    from cabqp.shared.db import SessionLocal

    _request(client)
    for i in range(auth_service.MAX_FAILED_ATTEMPTS):
        _verify(client, f"{i:06d}")

    with SessionLocal() as session:
        user = session.get(AppUser, OFFICER)
        assert user.locked_until is not None and user.locked_until > utcnow()

    # And the password door is shut too, not just this one.
    response = client.post("/api/v1/auth/login", json={"username": OFFICER, "password": "mat-khau-cu"})
    assert response.status_code == 401


def test_codes_are_stored_hashed(client, officer, app_database):
    """A database read must not hand over a live credential."""
    from cabqp.shared.db import SessionLocal

    _request(client)
    code = _sent_code()
    with SessionLocal() as session:
        stored = session.query(LoginOtp).one().code_hash
    assert code not in stored
    assert stored.startswith("pbkdf2_sha256$")
    assert auth_service.verify_password(code, stored)


def test_generated_codes_use_the_whole_space(client):
    """A generator that never emits a leading zero loses a tenth of the space."""
    codes = {otp_service.generate_code(6) for _ in range(400)}
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert len(codes) > 350, "codes should not repeat at this rate"
    assert any(c.startswith("0") for c in codes)


# --- Enumeration -------------------------------------------------------------


def test_requesting_a_code_never_reveals_whether_the_account_exists(client, officer):
    real = _request(client)
    mail_stub.SENT.clear()
    unknown = client.post("/api/v1/auth/otp/request", json={"username": "khongtontai"})
    assert unknown.status_code == 200
    assert unknown.json() == real, "the two answers must be indistinguishable"
    assert not mail_stub.SENT, "nothing may be sent for an account that does not exist"


def test_an_account_with_no_address_answers_the_same_way(client, officer, app_database):
    from cabqp.shared.db import SessionLocal

    with SessionLocal() as session:
        auth_service.create_user(
            session,
            username="khongthu",
            display_name="Không Có Thư",
            password="mat-khau-cu",
            must_change_password=False,
            require_email=False,
        )
        session.commit()

    baseline = _request(client)
    mail_stub.SENT.clear()
    response = client.post("/api/v1/auth/otp/request", json={"username": "khongthu"})
    assert response.status_code == 200
    assert response.json() == baseline
    assert not mail_stub.SENT


def test_verification_gives_one_message_for_every_failure(client, officer):
    _request(client)
    unknown_account = _verify(client, "123456", username="khongtontai")
    wrong_code = _verify(client, "123456")
    assert unknown_account.status_code == wrong_code.status_code == 401
    assert unknown_account.json()["detail"] == wrong_code.json()["detail"]


# --- Mail spam ---------------------------------------------------------------


def test_a_second_request_inside_the_cooldown_sends_nothing(client, officer):
    """One mailbox, one message per window. The target here is a third party."""
    _request(client)
    assert len(mail_stub.SENT) == 1
    first = mail_stub.SENT[-1]

    _request(client)  # answered identically, but nothing new goes out
    assert len(mail_stub.SENT) == 1, "the cooldown must stop a second message going out"
    assert mail_stub.SENT[-1] is first


def test_the_hourly_account_cap_bounds_the_total(client, officer, monkeypatch):
    """The cooldown alone only paces the mail; the cap is what bounds it."""
    monkeypatch.setenv("OTP_MAX_PER_ACCOUNT_PER_HOUR", "2")
    get_settings.cache_clear()

    for _ in range(5):
        _request(client)
        _age_challenges(seconds=65)  # clears the cooldown, not the hourly window

    assert len(mail_stub.SENT) == 2, "the hourly cap must hold once the cooldown is aged out"


def test_one_address_cannot_walk_a_username_list(client, officer, monkeypatch):
    """The per-account cap alone does nothing against a sprayer."""
    monkeypatch.setenv("OTP_MAX_PER_IP_PER_HOUR", "3")
    get_settings.cache_clear()
    from cabqp.shared.db import SessionLocal

    with SessionLocal() as session:
        for i in range(6):
            auth_service.create_user(
                session,
                username=f"muctieu{i}",
                display_name=f"Mục Tiêu {i}",
                password="mat-khau-cu",
                email=f"muctieu{i}@cabqp.local",
                must_change_password=False,
            )
        session.commit()

    for i in range(6):
        client.post("/api/v1/auth/otp/request", json={"username": f"muctieu{i}"})

    assert len(mail_stub.SENT) <= 3, "the address budget must bound total mail, not mail per account"


def test_a_locked_account_is_sent_nothing(client, officer, app_database):
    """A lockout that still mails codes is a lockout that still spams."""
    from cabqp.shared.db import SessionLocal

    with SessionLocal() as session:
        user = session.get(AppUser, OFFICER)
        user.locked_until = utcnow() + timedelta(minutes=10)
        session.commit()

    _request(client)
    assert not mail_stub.SENT


def test_an_inactive_account_is_sent_nothing(client, officer, app_database):
    from cabqp.shared.db import SessionLocal

    with SessionLocal() as session:
        user = session.get(AppUser, OFFICER)
        user.is_active = False
        session.commit()

    _request(client)
    assert not mail_stub.SENT


# --- Availability ------------------------------------------------------------


def test_the_feature_is_off_when_mail_is_not_configured(client, officer, monkeypatch):
    """A code that cannot be delivered must not be issuable at all."""
    monkeypatch.setenv("GMAIL_USER", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    get_settings.cache_clear()

    assert client.get("/api/v1/auth/methods").json()["otp"] is False
    assert client.post("/api/v1/auth/otp/request", json={"username": OFFICER}).status_code == 503
    assert client.post(
        "/api/v1/auth/otp/verify", json={"username": OFFICER, "code": "123456"}
    ).status_code == 503


def test_settings_refuse_a_cooldown_shorter_than_the_code_lifetime():
    """Otherwise one caller can queue a message for every second a code lives."""
    from cabqp.shared.settings import Settings

    with pytest.raises(ValueError, match="OTP_RESEND_COOLDOWN_SECONDS"):
        Settings(otp_login_enabled=True, otp_ttl_seconds=60, otp_resend_cooldown_seconds=5)


def test_expired_challenges_are_kept_past_the_budget_window():
    """Purging on expiry would hand back the issuance budget the row is spending."""
    s = get_settings()
    assert s.otp_retention_hours >= 1, "retention must outlast the one-hour budget windows"
