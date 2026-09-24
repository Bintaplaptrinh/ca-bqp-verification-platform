"""HTTP-level authentication and reviewer-scope regressions.

The rest of the suite exercises services directly with a constructed Principal, so a
regression in the route/dependency layer would not be caught. These tests drive the
ASGI app itself.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from principals import admin_principal, reviewer_principal
from sqlalchemy.dialects import postgresql

from cabqp.api.cases import _reviewer_case_scope_query
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal
from cabqp.shared.settings import get_settings

#: Review permissions without CASE_VIEW_ALL, so coverage scope alone decides.
SCOPED = (perms.REVIEW_QUEUE, perms.REVIEW_DECIDE)


def scoped_reviewer(username, coverage_groups):
    return reviewer_principal(username, coverage_groups=coverage_groups, permissions=SCOPED)


PROTECTED = [
    ("get", "/api/v1/cases", None),
    ("get", "/api/v1/reviews", None),
    ("post", "/api/v1/lookup/unit", {"unit_name": "x"}),
    ("get", "/api/v1/admin/registry/units", None),
    ("get", "/api/v1/admin/person-registry/persons", None),
    ("get", "/api/v1/admin/audit", None),
]


@pytest.fixture
def authenticated_client(monkeypatch, app_database):
    """App instance with authentication actually enabled."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    get_settings.cache_clear()
    from cabqp.main import app

    yield TestClient(app)
    get_settings.cache_clear()


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_routes_reject_missing_token(authenticated_client, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    response = getattr(authenticated_client, method)(path, **kwargs)
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_routes_reject_unknown_session_token(authenticated_client, method, path, body):
    """A token that matches no live session is rejected, whatever it looks like.

    Session tokens are opaque ids with no claims in them, so there is nothing a
    caller can craft that the server will read authority out of.
    """
    kwargs = {"json": body} if body is not None else {}
    kwargs["headers"] = {"Authorization": "Bearer not-a-real-session-token"}
    response = getattr(authenticated_client, method)(path, **kwargs)
    assert response.status_code == 401


def test_liveness_probe_stays_public(authenticated_client):
    """Kubernetes/compose probes must not require a bearer token."""
    assert authenticated_client.get("/health/live").status_code == 200


def _scope_sql(principal: Principal) -> str:
    query = _reviewer_case_scope_query(principal)
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_reviewer_without_coverage_group_sees_nothing():
    """An empty coverage scope must fail closed, not degrade to an unfiltered query."""
    sql = _scope_sql(scoped_reviewer("rev", set()))
    assert "WHERE false" in sql


def test_reviewer_scope_is_restricted_to_granted_groups():
    sql = _scope_sql(scoped_reviewer("rev", {"BCA_CENTRAL_PUBLIC"}))
    assert "BCA_CENTRAL_PUBLIC" in sql
    assert "WHERE false" not in sql


def test_admin_and_wildcard_scope_are_unfiltered():
    assert "WHERE" not in _scope_sql(admin_principal())
    assert "WHERE" not in _scope_sql(scoped_reviewer("rev", {"*"}))
    # CASE_VIEW_ALL with no coverage group is also unfiltered: that is the
    # delivered "cán bộ thẩm định" preset.
    assert "WHERE" not in _scope_sql(reviewer_principal("rev", coverage_groups=()))


def test_can_review_scope_denies_other_groups_and_unscoped_reviews():
    principal = scoped_reviewer("rev", {"BCA_NORTH"})
    assert principal.can_review_scope("BCA_NORTH")
    assert not principal.can_review_scope("BQP_SOUTH")
    # A review with no coverage group must not be readable by a scoped reviewer.
    assert not principal.can_review_scope(None)
    assert admin_principal().can_review_scope("ANY")
