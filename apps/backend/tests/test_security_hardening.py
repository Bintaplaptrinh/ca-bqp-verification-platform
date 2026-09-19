"""Transport and abuse-resistance regressions for the POC hardening pass.

These cover the parts of the security surface that are properties of the server
rather than of any one route: the response headers a browser needs in order to
refuse framing and MIME sniffing, and the rate limiter's behaviour under a
client that lies about where it is coming from or sprays many routes at once.

The limiter is exercised against a purpose-built app rather than the real one:
``tests/conftest.py`` turns rate limiting off for every other test, and these
need it on with small, fast limits.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.auth import service as auth_service
from cabqp.shared.db import Base
from cabqp.shared.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from cabqp.shared.settings import get_settings


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _limited_app(monkeypatch, *, peer: str = "203.0.113.9", **overrides) -> TestClient:
    """An app behind the real limiter, with the limits dialled down.

    The overrides are injected by patching the middleware module's settings
    lookup before the middleware is constructed, which is where it reads them.

    Redis is not running in the test environment, so every bucket resolves
    through the middleware's in-memory fallback — which is exactly the path a
    production Redis outage takes with RATE_LIMIT_FAIL_OPEN on.
    """
    settings = get_settings().model_copy(
        update={"rate_limit_enabled": True, "rate_limit_fail_open": True, **overrides}
    )
    monkeypatch.setattr("cabqp.shared.middleware.get_settings", lambda: settings)

    app = FastAPI()

    @app.get("/api/v1/thing/{item}")
    def thing(item: str):
        return {"item": item}

    @app.post("/api/v1/auth/login")
    def login(body: dict):
        if body.get("password") == "right":
            return {"ok": True}
        return JSONResponse(status_code=401, content={"error": "nope"})

    app.add_middleware(RateLimitMiddleware)
    # A real peer address, so the trusted-proxy matching has something to match.
    return TestClient(app, client=(peer, 51000))


# --- Response headers --------------------------------------------------------


def test_api_responses_carry_the_clickjacking_and_sniffing_headers():
    from cabqp.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_error_responses_carry_them_too():
    """A 404 is still a document a browser will render, so it is framed the same."""
    from cabqp.main import app

    client = TestClient(app)
    response = client.get("/api/v1/definitely-not-a-route")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_security_headers_can_be_switched_off_only_by_configuration(monkeypatch):
    settings = get_settings().model_copy(update={"security_headers_enabled": False})
    monkeypatch.setattr("cabqp.shared.middleware.get_settings", lambda: settings)

    app = FastAPI()

    @app.get("/x")
    def x():
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware)
    assert "X-Frame-Options" not in TestClient(app).get("/x").headers


def test_production_refuses_to_start_without_the_security_headers():
    from cabqp.shared.settings import Settings

    with pytest.raises(ValueError, match="security response headers"):
        Settings(
            app_env="production",
            auth_disabled=False,
            rate_limit_enabled=True,
            security_headers_enabled=False,
            antimalware_enabled=True,
            antimalware_required=True,
            gmail_user="cabqp@gmail.com",
            gmail_app_password="abcd efgh ijkl mnop",
            database_url="postgresql+psycopg://real:secret@db/cabqp",
            minio_secret_key="a-real-secret",
        )


# --- Rate limiting -----------------------------------------------------------


def test_spoofed_forwarded_for_cannot_buy_a_fresh_rate_limit_bucket(monkeypatch):
    """The header is only believed when the peer is a proxy we deployed.

    Before this, any caller could reset its own bucket on every request simply
    by sending a different X-Forwarded-For, which made the limiter decorative.
    """
    client = _limited_app(monkeypatch, rate_limit_per_minute=3, rate_limit_ip_per_minute=1000, trusted_proxy_ips="")
    statuses = [
        client.get("/api/v1/thing/a", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
        for i in range(6)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses[3:]


def test_a_trusted_proxy_may_still_identify_its_clients(monkeypatch):
    """Behind a WAF or load balancer the real client address has to come through."""
    client = _limited_app(
        monkeypatch,
        peer="192.168.44.7",
        rate_limit_per_minute=2,
        rate_limit_ip_per_minute=1000,
        # A range, not one address: a container network hands the proxy its
        # address at start-up, so a deployment cannot pin a single host.
        trusted_proxy_ips="192.168.44.0/24",
    )
    for i in range(4):
        response = client.get("/api/v1/thing/a", headers={"X-Forwarded-For": f"10.0.0.{i}"})
        assert response.status_code == 200, f"distinct clients must not share a bucket (call {i})"
    assert client.get("/api/v1/thing/a", headers={"X-Forwarded-For": "10.0.0.0"}).status_code == 200
    assert client.get("/api/v1/thing/a", headers={"X-Forwarded-For": "10.0.0.0"}).status_code == 429


def test_spraying_distinct_routes_hits_the_whole_address_budget(monkeypatch):
    """The per-route bucket alone lets a flood spread out and stay under it."""
    client = _limited_app(monkeypatch, rate_limit_per_minute=1000, rate_limit_ip_per_minute=5)
    statuses = [client.get(f"/api/v1/thing/{i}").status_code for i in range(8)]
    assert statuses[:5] == [200] * 5
    assert statuses[5:] == [429] * 3


def test_failed_logins_are_throttled_while_successful_ones_are_not(monkeypatch):
    client = _limited_app(
        monkeypatch, rate_limit_per_minute=1000, rate_limit_ip_per_minute=1000, rate_limit_auth_per_minute=3
    )
    for _ in range(3):
        assert client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code == 401

    blocked = client.post("/api/v1/auth/login", json={"password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "TOO_MANY_CREDENTIAL_ATTEMPTS"
    # The correct password is refused too while the window is open: the limiter
    # is per address, so a sprayer cannot keep guessing by getting one right.
    assert client.post("/api/v1/auth/login", json={"password": "right"}).status_code == 429


def test_a_working_sign_in_never_spends_the_credential_budget(monkeypatch):
    client = _limited_app(
        monkeypatch, rate_limit_per_minute=1000, rate_limit_ip_per_minute=1000, rate_limit_auth_per_minute=2
    )
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json={"password": "right"}).status_code == 200


# --- One live session per account -------------------------------------------


def test_second_sign_in_ends_the_first_session(db):
    auth_service.create_user(
        db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local"
    )
    _, first_token, _ = auth_service.authenticate(db, "hungnv", "secret1")
    assert auth_service.resolve_session(db, first_token) is not None

    _, second_token, _ = auth_service.authenticate(db, "hungnv", "secret1")
    assert auth_service.resolve_session(db, second_token) is not None
    assert auth_service.resolve_session(db, first_token) is None, (
        "the device that signed in first must lose its session"
    )


def test_other_accounts_are_untouched_by_a_sign_in(db):
    auth_service.create_user(
        db, username="hungnv", display_name="H", password="secret1", email="hungnv@cabqp.local"
    )
    auth_service.create_user(
        db, username="datld", display_name="D", password="secret2", email="datld@cabqp.local"
    )
    _, other_token, _ = auth_service.authenticate(db, "datld", "secret2")
    auth_service.authenticate(db, "hungnv", "secret1")
    auth_service.authenticate(db, "hungnv", "secret1")
    assert auth_service.resolve_session(db, other_token) is not None


# --- Output encoding ---------------------------------------------------------


def test_the_api_never_answers_with_html():
    """Cross-site scripting needs an HTML sink, and this API is not one.

    Every route returns JSON, so user-supplied text is carried as JSON string
    data and is escaped by whatever renders it. The SPA renders it through React,
    which escapes ``<``, ``>``, ``&`` and quotes in text nodes on its own, and
    the outgoing account emails are text/plain. Server-side HTML-escaping *into*
    the stored values would be the wrong fix: it corrupts the data (a name
    containing a quote would be stored and later re-exported as ``&quot;``) and
    still would not help a sink that does not escape.
    """
    from cabqp.main import app

    client = TestClient(app)
    for path in ("/health", "/health/live", "/api/v1/definitely-not-a-route"):
        content_type = client.get(path).headers.get("content-type", "")
        assert content_type.startswith("application/json"), f"{path} answered {content_type}"


def test_the_web_client_has_no_raw_html_sink():
    """No component may hand user text to the browser as markup.

    React escapes text nodes, so the only way to introduce XSS in this SPA is to
    opt out of that. This check lives with the Python suite because pytest is
    what CI always runs; the web build has no unit-test runner.
    """
    from pathlib import Path

    web_src = Path(__file__).resolve().parents[2] / "web" / "src"
    assert web_src.is_dir(), f"expected the web sources at {web_src}"

    forbidden = ("dangerouslySetInnerHTML", ".innerHTML", "document.write", "eval(")
    offenders = [
        f"{path.relative_to(web_src)}: {token}"
        for path in web_src.rglob("*")
        if path.suffix in {".jsx", ".tsx", ".js", ".ts"}
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]
    assert not offenders, "raw HTML/script sinks in the web client: " + ", ".join(offenders)
