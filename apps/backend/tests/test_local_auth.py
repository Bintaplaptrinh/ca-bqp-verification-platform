"""Local account, session and permission regressions.

These replace the Keycloak JWT suite. The property that matters is different
now: a session token carries no claims, so there is nothing in it for a client
to rewrite. Authority is read from ``app_users`` on every request, which is what
makes "hide the button" irrelevant to security — the checks below drive the real
HTTP surface with real sessions.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth import service as auth_service
from cabqp.shared.db import Base
from cabqp.shared.models import AppUser
from cabqp.shared.settings import get_settings


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# --- Password hashing --------------------------------------------------------


def test_password_hash_is_salted_and_verifiable():
    first = auth_service.hash_password("Bí mật 123")
    second = auth_service.hash_password("Bí mật 123")
    assert first != second, "each hash must carry its own salt"
    assert auth_service.verify_password("Bí mật 123", first)
    assert auth_service.verify_password("Bí mật 123", second)
    assert not auth_service.verify_password("Bí mật 124", first)


def test_password_hash_never_stores_the_plaintext():
    stored = auth_service.hash_password("correct horse")
    assert "correct horse" not in stored
    assert stored.startswith("pbkdf2_sha256$")


def test_verify_password_rejects_malformed_stored_values():
    for junk in ["", "nonsense", "pbkdf2_sha256$notanint$aa$bb", None]:
        assert not auth_service.verify_password("x", junk)


# --- Username derivation -----------------------------------------------------


def test_username_is_derived_from_personnel_code_when_present():
    assert (
        auth_service.suggest_username(personal_code="CA-2026-0417", display_name="Nguyễn Văn Hùng")
        == "ca20260417"
    )


def test_username_falls_back_to_folded_vietnamese_name_order():
    """Given name first, then the initials of the preceding words."""
    assert auth_service.suggest_username(personal_code=None, display_name="Nguyễn Văn Hùng") == "hungnv"
    assert auth_service.suggest_username(personal_code=None, display_name="Trần Đức Đạt") == "dattd"


def test_username_allocation_avoids_collisions(db):
    auth_service.create_user(db, username="hungnv", display_name="Nguyễn Văn Hùng", password="secret1", email="hungnv@cabqp.local")
    assert auth_service.allocate_username(db, "hungnv") == "hungnv2"


def test_invalid_usernames_are_rejected():
    for bad in ["ab", "Nguyen Van A", "hung@vn", "-hung", ""]:
        with pytest.raises(ValueError):
            auth_service.validate_username(bad)


# --- Account creation --------------------------------------------------------


def test_created_account_gets_a_random_password_and_must_change_it(db):
    user, first = auth_service.create_user(db, username="hungnv", display_name="Nguyễn Văn Hùng", email="hungnv@cabqp.local")
    other, second = auth_service.create_user(db, username="datld", display_name="Lê Đức Đạt", email="datld@cabqp.local")
    assert first != second
    assert len(first) >= 12
    assert user.must_change_password and other.must_change_password
    assert auth_service.verify_password(first, user.password_hash)


def test_created_account_holds_only_catalog_permissions(db):
    user, _ = auth_service.create_user(
        db,
        username="hungnv",
        display_name="Nguyễn Văn Hùng",
        email="hungnv@cabqp.local",
        permissions=["CASE_CREATE", "NOT_A_REAL_PERMISSION", "USER_ADMIN"],
    )
    assert user.permissions == ["CASE_CREATE", "USER_ADMIN"]


def test_duplicate_username_is_refused(db):
    auth_service.create_user(db, username="hungnv", display_name="A", password="secret1", email="hungnv@cabqp.local")
    with pytest.raises(ValueError):
        auth_service.create_user(db, username="hungnv", display_name="B", password="secret1", email="hungnv@cabqp.local")


# --- Sessions ----------------------------------------------------------------


def test_authenticate_opens_a_session_resolvable_by_token(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    user, token, expires_at = auth_service.authenticate(db, "hungnv", "secret1")
    assert user.username == "hungnv"
    assert expires_at > user.last_login_at
    resolved = auth_service.resolve_session(db, token)
    assert resolved is not None and resolved[0].username == "hungnv"


def test_session_token_is_not_stored_in_the_clear(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    _, token, _ = auth_service.authenticate(db, "hungnv", "secret1")
    from cabqp.shared.models import UserSession

    stored = db.query(UserSession).one()
    assert stored.token_hash != token
    assert token not in stored.token_hash


def test_wrong_password_is_refused_and_counted(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    with pytest.raises(auth_service.AuthError):
        auth_service.authenticate(db, "hungnv", "wrong")
    assert db.get(AppUser, "hungnv").failed_attempts == 1


def test_repeated_failures_lock_the_account(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth_service.AuthError):
            auth_service.authenticate(db, "hungnv", "wrong")
    assert db.get(AppUser, "hungnv").locked_until is not None
    # Even the correct password is refused while the lockout is in force.
    with pytest.raises(auth_service.AuthError):
        auth_service.authenticate(db, "hungnv", "secret1")


def test_unknown_username_is_refused(db):
    with pytest.raises(auth_service.AuthError):
        auth_service.authenticate(db, "nobody", "secret1")


def test_deactivated_account_cannot_authenticate_or_resolve(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    _, token, _ = auth_service.authenticate(db, "hungnv", "secret1")
    db.get(AppUser, "hungnv").is_active = False
    db.flush()
    assert auth_service.resolve_session(db, token) is None
    with pytest.raises(auth_service.AuthError):
        auth_service.authenticate(db, "hungnv", "secret1")


def test_revoked_session_stops_resolving(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    _, token, _ = auth_service.authenticate(db, "hungnv", "secret1")
    assert auth_service.revoke_session(db, token)
    assert auth_service.resolve_session(db, token) is None


def test_expired_session_stops_resolving(db):
    from datetime import timedelta

    from cabqp.shared.models import UserSession, utcnow

    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    _, token, _ = auth_service.authenticate(db, "hungnv", "secret1")
    db.query(UserSession).one().expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert auth_service.resolve_session(db, token) is None


def test_password_reset_revokes_every_live_session(db):
    auth_service.create_user(db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local")
    _, first, _ = auth_service.authenticate(db, "hungnv", "secret1")
    _, second, _ = auth_service.authenticate(db, "hungnv", "secret1")
    new_password = auth_service.reset_password(db, db.get(AppUser, "hungnv"))
    assert auth_service.resolve_session(db, first) is None
    assert auth_service.resolve_session(db, second) is None
    assert auth_service.verify_password(new_password, db.get(AppUser, "hungnv").password_hash)


# --- Effective authority -----------------------------------------------------


def test_admin_holds_the_whole_catalog_implicitly(db):
    user, _ = auth_service.create_user(
        db,
        username="admin",
        display_name="QT",
        password="secret1",
        email="admin@cabqp.local",
        is_admin=True,
        permissions=[],
    )
    assert auth_service.effective_permissions(user) == set(perms.ALL_PERMISSIONS)


def test_reviewer_preset_is_a_permission_bundle_not_a_role():
    assert perms.REVIEW_DECIDE in perms.REVIEWER_PRESET
    assert perms.REVIEW_QUEUE in perms.REVIEWER_PRESET
    assert perms.CASE_VIEW_ALL in perms.REVIEWER_PRESET
    # A reviewer is not an administrator by another name.
    for admin_only in (perms.USER_ADMIN, perms.REGISTRY_ADMIN, perms.PERSON_REGISTRY_ADMIN):
        assert admin_only not in perms.REVIEWER_PRESET


def test_role_view_is_derived_and_never_widens_access():
    from principals import reviewer_principal, user_principal

    assert reviewer_principal("r").roles == {"USER", "REVIEWER"}
    assert user_principal("u").roles == {"USER"}
    # Permissions decide; the role projection carries no authority of its own.
    assert not user_principal("u").has(perms.REVIEW_DECIDE)


# --- HTTP surface ------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, app_database):
    """A client against the real app with authentication switched on."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    get_settings.cache_clear()
    from cabqp.main import app

    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def accounts(app_database):
    """admin/admin plus a tra cứu account, as the seeder delivers them."""
    from cabqp.shared.db import SessionLocal

    session = SessionLocal()
    try:
        session.query(AppUser).delete()
        auth_service.create_user(
            session,
            username="admin",
            display_name="Quản trị hệ thống",
            password="admin",
            is_admin=True,
            must_change_password=False,
            enforce_password_policy=False,
            require_email=False,
        )
        auth_service.create_user(
            session,
            username="user",
            display_name="Cán bộ tra cứu",
            password="user",
            permissions=list(perms.USER_PRESET),
            must_change_password=False,
            enforce_password_policy=False,
            require_email=False,
        )
        session.commit()
    finally:
        session.close()
    yield


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _issued_password(recipient: str) -> str:
    """Read the password out of the message the server actually sent.

    `mail_stub` stands in for the Gmail socket and records every EmailMessage
    the mailer handed to SMTP. Pulling the credential back out of that message —
    rather than out of the API response — is what proves delivery really
    happened: the response deliberately withholds the password once the mail
    goes out.
    """
    import mail_stub

    assert mail_stub.SENT, "no message was handed to SMTP"
    parsed = mail_stub.SENT[-1]
    assert parsed["To"] == recipient, f"last message went to {parsed['To']}, not {recipient}"
    # The message is multipart now (text + HTML + inline logo). Reading the
    # plain-text alternative rather than the HTML is deliberate: it keeps this
    # helper from depending on the markup, and it fails loudly if the text
    # alternative is ever dropped, which some clients would then render empty.
    body = parsed.get_body(preferencelist=("plain",)).get_content()
    for line in body.splitlines():
        if line.strip().startswith("Mật khẩu"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"no password line in the delivered message:\n{body}")


def _create_account(client, admin_token, **fields) -> tuple[dict, str]:
    """Create an account through the admin API; return it with its emailed password."""
    fields.setdefault("email", f"{fields.get('username', 'nguoidung')}@cabqp.local")
    response = client.post("/api/v1/admin/users", headers=_auth(admin_token), json=fields)
    assert response.status_code == 201, response.text
    body = response.json()
    return body, _issued_password(fields["email"])


def test_default_accounts_can_sign_in(client, accounts):
    assert _login(client, "admin", "admin")
    assert _login(client, "user", "user")


def test_login_rejects_a_wrong_password(client, accounts):
    response = client.post("/api/v1/auth/login", json={"username": "user", "password": "nope"})
    assert response.status_code == 401


def test_me_reports_the_accounts_own_permissions(client, accounts):
    token = _login(client, "user", "user")
    body = client.get("/api/v1/auth/me", headers=_auth(token)).json()
    assert body["username"] == "user"
    assert not body["is_admin"]
    assert set(body["permissions"]) == set(perms.USER_PRESET)


def test_admin_me_reports_the_whole_catalog(client, accounts):
    token = _login(client, "admin", "admin")
    body = client.get("/api/v1/auth/me", headers=_auth(token)).json()
    assert body["is_admin"]
    assert set(body["permissions"]) == set(perms.ALL_PERMISSIONS)


def test_default_user_cannot_reach_administration(client, accounts):
    """The server refuses regardless of what the client believes it may do.

    This is the property that makes client-side hiding a presentation choice:
    a caller who edits the bundle, or skips it entirely, still gets 403.
    """
    token = _login(client, "user", "user")
    for path in (
        "/api/v1/admin/users",
        "/api/v1/admin/registry/units",
        "/api/v1/admin/person-registry/persons",
        "/api/v1/admin/audit",
        "/api/v1/reviews",
    ):
        assert client.get(path, headers=_auth(token)).status_code == 403, path


def test_admin_can_reach_administration(client, accounts):
    token = _login(client, "admin", "admin")
    assert client.get("/api/v1/admin/users", headers=_auth(token)).status_code == 200


def test_logout_invalidates_the_session_immediately(client, accounts):
    token = _login(client, "user", "user")
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=_auth(token)).status_code == 200
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 401


def test_admin_creates_an_account_from_administrative_particulars(client, accounts):
    token = _login(client, "admin", "admin")
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth(token),
        json={
            "display_name": "Nguyễn Văn Hùng",
            "personal_code": "CA-2026-0417",
            "birth_year": 1988,
            "rank": "Thiếu tá",
            "position": "Chuyên viên",
            "department": "Phòng Tổ chức cán bộ",
            "unit_name": "Cục Tổ chức cán bộ",
            "email": "hungnv@cabqp.local",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["username"] == "ca20260417"
    assert body["user"]["display_name"] == "Nguyễn Văn Hùng"
    assert body["user"]["birth_year"] == 1988
    assert body["user"]["must_change_password"]

    # Delivery succeeded, so the response withholds the password entirely.
    assert body["email_delivery"]["ok"] is True
    assert body["initial_password"] is None

    # It went to the address given, and it is the password that actually works.
    assert _login(client, "ca20260417", _issued_password("hungnv@cabqp.local"))


def test_account_creation_requires_a_valid_email(client, accounts):
    """The password is delivered by mail, so an unreachable account is refused."""
    token = _login(client, "admin", "admin")
    for payload in (
        {"display_name": "Không Có Thư", "username": "khongthu"},
        {"display_name": "Sai Định Dạng", "username": "saidinhdang", "email": "not-an-address"},
    ):
        response = client.post("/api/v1/admin/users", headers=_auth(token), json=payload)
        assert response.status_code == 422, response.text


def test_issued_password_is_generated_by_the_passwordgen_library(client, accounts):
    """Shape and entropy come from `passwordgen`, and are recorded for audit."""
    from cabqp.modules.auth.service import GENERATED_PASSWORD_LENGTH, password_entropy_bits

    token = _login(client, "admin", "admin")
    _, password = _create_account(
        client, token, display_name="Người Dùng Mới", username="nguoimoi", email="nguoimoi@cabqp.local"
    )
    assert len(password) == GENERATED_PASSWORD_LENGTH
    # The generator is configured to drop 0/O/1/l/I, which are misread off a page.
    assert not set(password) & set("0O1lI")
    assert password_entropy_bits() > 90


def test_created_account_is_not_an_administrator(client, accounts):
    token = _login(client, "admin", "admin")
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth(token),
        # A caller asking for administrator permissions still does not become one.
        json={
            "display_name": "Kẻ Tò Mò",
            "username": "tomo",
            "email": "tomo@cabqp.local",
            "permissions": list(perms.ALL_PERMISSIONS),
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["is_admin"] is False
    issued = _login(client, "tomo", _issued_password("tomo@cabqp.local"))
    # USER_ADMIN was granted explicitly, so that endpoint opens; being an
    # administrator would additionally have meant the whole catalog implicitly.
    me = client.get("/api/v1/auth/me", headers=_auth(issued)).json()
    assert me["is_admin"] is False


def test_granting_the_reviewer_preset_opens_the_review_queue(client, accounts):
    """"Cán bộ thẩm định" is applied as permissions on an existing account."""
    token = _login(client, "admin", "admin")
    _, password = _create_account(
        client, token, display_name="Trần Thẩm Định", username="tdinh", email="tdinh@cabqp.local"
    )
    officer = _login(client, "tdinh", password)
    assert client.get("/api/v1/reviews", headers=_auth(officer)).status_code == 403

    patched = client.patch(
        "/api/v1/admin/users/tdinh",
        headers=_auth(token),
        json={"permissions": list(perms.REVIEWER_PRESET)},
    )
    assert patched.status_code == 200, patched.text
    # The change takes effect on the existing session: authority is re-read per
    # request rather than frozen into the token at sign-in.
    assert client.get("/api/v1/reviews", headers=_auth(officer)).status_code == 200
    assert client.get("/api/v1/admin/users", headers=_auth(officer)).status_code == 403


def test_revoking_a_permission_takes_effect_on_the_next_request(client, accounts):
    token = _login(client, "admin", "admin")
    _, password = _create_account(
        client,
        token,
        display_name="Trần Thẩm Định",
        username="tdinh2",
        email="tdinh2@cabqp.local",
        permissions=list(perms.REVIEWER_PRESET),
    )
    officer = _login(client, "tdinh2", password)
    assert client.get("/api/v1/reviews", headers=_auth(officer)).status_code == 200

    client.patch(
        "/api/v1/admin/users/tdinh2",
        headers=_auth(token),
        json={"permissions": list(perms.USER_PRESET)},
    )
    assert client.get("/api/v1/reviews", headers=_auth(officer)).status_code == 403


def test_deactivating_an_account_ends_its_session(client, accounts):
    token = _login(client, "admin", "admin")
    _, password = _create_account(
        client, token, display_name="Tạm Nghỉ", username="tamnghi", email="tamnghi@cabqp.local"
    )
    officer = _login(client, "tamnghi", password)
    assert client.get("/api/v1/auth/me", headers=_auth(officer)).status_code == 200

    client.patch("/api/v1/admin/users/tamnghi", headers=_auth(token), json={"is_active": False})
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=_auth(officer)).status_code == 401


def test_admin_account_is_protected_from_edits(client, accounts):
    token = _login(client, "admin", "admin")
    response = client.patch(
        "/api/v1/admin/users/admin", headers=_auth(token), json={"permissions": [], "is_active": False}
    )
    assert response.status_code == 400
    assert client.get("/api/v1/auth/me", headers=_auth(token)).json()["is_admin"]


def test_changing_own_password_requires_the_current_one(client, accounts):
    token = _login(client, "user", "user")
    bad = client.post(
        "/api/v1/auth/change-password",
        headers=_auth(token),
        json={"current_password": "wrong", "new_password": "moimatkhau"},
    )
    assert bad.status_code == 400

    good = client.post(
        "/api/v1/auth/change-password",
        headers=_auth(token),
        json={"current_password": "user", "new_password": "moimatkhau"},
    )
    assert good.status_code == 200
    assert _login(client, "user", "moimatkhau")


# --- Password delivery -------------------------------------------------------


def test_reset_password_emails_a_new_one_and_kills_old_sessions(client, accounts):
    token = _login(client, "admin", "admin")
    _, first = _create_account(
        client, token, display_name="Cần Cấp Lại", username="capllai", email="capllai@cabqp.local"
    )
    officer = _login(client, "capllai", first)
    assert client.get("/api/v1/auth/me", headers=_auth(officer)).status_code == 200

    response = client.post("/api/v1/admin/users/capllai/reset-password", headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["email_delivery"]["ok"] is True
    assert response.json()["initial_password"] is None

    second = _issued_password("capllai@cabqp.local")
    assert second != first
    client.cookies.clear()
    # The session opened with the old password is gone, and only the new one works.
    assert client.get("/api/v1/auth/me", headers=_auth(officer)).status_code == 401
    assert _login(client, "capllai", second)


def test_password_is_returned_only_when_delivery_fails(client, accounts, monkeypatch):
    """A failed send must not leave the administrator with an unusable account."""
    from cabqp.modules.notifications import email as mailer

    def refuse(*_args, **_kwargs):
        return mailer.DeliveryResult(ok=False, detail="SMTPAuthenticationError")

    monkeypatch.setattr("cabqp.api.admin_users.mailer.send_new_account_email", refuse)

    token = _login(client, "admin", "admin")
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth(token),
        json={"display_name": "Thư Hỏng", "username": "thuhong", "email": "thuhong@cabqp.local"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email_delivery"]["ok"] is False
    assert body["initial_password"], "a failed send must hand the password back"
    assert "Không gửi được thư" in body["notice"]
    assert _login(client, "thuhong", body["initial_password"])


# --- Deleting an account -----------------------------------------------------


def test_admin_deletes_an_account_and_its_sessions(client, accounts):
    token = _login(client, "admin", "admin")
    _, password = _create_account(
        client, token, display_name="Sẽ Bị Xóa", username="sebixoa", email="sebixoa@cabqp.local"
    )
    officer = _login(client, "sebixoa", password)
    assert client.get("/api/v1/auth/me", headers=_auth(officer)).status_code == 200

    response = client.delete("/api/v1/admin/users/sebixoa", headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True

    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=_auth(officer)).status_code == 401
    assert client.get("/api/v1/admin/users/sebixoa", headers=_auth(token)).status_code == 404
    # The credentials no longer authenticate at all.
    assert client.post(
        "/api/v1/auth/login", json={"username": "sebixoa", "password": password}
    ).status_code == 401


def test_deleting_an_account_leaves_its_audit_trail_intact(client, accounts):
    """Audit records the actor as a username string, so deletion cannot rewrite it."""
    token = _login(client, "admin", "admin")
    _create_account(client, token, display_name="Có Vết", username="covet", email="covet@cabqp.local")
    client.delete("/api/v1/admin/users/covet", headers=_auth(token))

    entries = client.get("/api/v1/admin/audit", headers=_auth(token), params={"limit": 200}).json()
    actions = {(x["action"], x["entity_id"]) for x in entries}
    assert ("USER_CREATE", "covet") in actions
    assert ("USER_DELETE", "covet") in actions


def test_the_administrator_account_cannot_be_deleted(client, accounts):
    token = _login(client, "admin", "admin")
    response = client.delete("/api/v1/admin/users/admin", headers=_auth(token))
    assert response.status_code == 400
    assert client.get("/api/v1/auth/me", headers=_auth(token)).json()["is_admin"]


def test_a_non_administrator_cannot_delete_accounts(client, accounts):
    token = _login(client, "admin", "admin")
    _create_account(client, token, display_name="Bình Thường", username="binhthuong", email="bt@cabqp.local")
    user_token = _login(client, "user", "user")
    assert client.delete("/api/v1/admin/users/binhthuong", headers=_auth(user_token)).status_code == 403


# --- Response projection -----------------------------------------------------


def test_account_responses_are_a_projection_not_the_row(client, accounts):
    """Routes answer with an explicit field list, never a serialized ORM object.

    `admin_users._serialize` decides what leaves the server. The property under
    test is that the credential columns are not in it: returning the row itself,
    or adding a field by looping over the model's columns, would publish the
    password hash to every administrator screen and to anyone who later reads
    the browser's network log.
    """
    token = _login(client, "admin", "admin")

    listed = client.get("/api/v1/admin/users", headers=_auth(token))
    assert listed.status_code == 200, listed.text
    me = client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200, me.text

    for response in (listed, me):
        body = response.text
        for secret in ("password_hash", "pbkdf2_sha256$", "token_hash"):
            assert secret not in body, f"{secret} must never appear in an API response"

    rows = listed.json()["items"] if isinstance(listed.json(), dict) else listed.json()
    assert rows, "the seeded accounts should be listed"
    exposed = set(rows[0])
    assert "password_hash" not in exposed
    assert "permissions" in exposed and "is_active" in exposed
