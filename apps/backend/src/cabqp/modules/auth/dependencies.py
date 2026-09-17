"""Request-time authentication and authorization.

Every protected route resolves the caller's account from the database on each
request and checks the required permission here. Nothing in the bearer token
describes the caller's authority — the token is an opaque session id — so the
client cannot widen its own access by editing what it holds, and a permission
an administrator removes stops working on the caller's very next request.

The frontend is told the same permission set through ``GET /auth/me`` purely so
it can render a navigation that matches. Hiding a button is a convenience, not
the control: removing that check client-side just produces a 403 here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.service import effective_permissions, resolve_session
from cabqp.shared.db import get_db
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

SESSION_COOKIE = "cabqp_session"


@dataclass
class Principal:
    subject: str
    username: str
    permissions: set[str] = field(default_factory=set)
    coverage_groups: set[str] = field(default_factory=set)
    is_admin: bool = False
    display_name: str = ""
    must_change_password: bool = False

    @property
    def roles(self) -> set[str]:
        """Compatibility view over the permission set.

        Accounts carry permissions, not roles. This projection keeps the
        long-standing ``"ADMIN" in p.roles`` checks and the audit log's ``role``
        column meaningful without reintroducing a second source of authority:
        every value here is derived from ``permissions``.
        """
        derived = {"USER"}
        if perms.REVIEW_DECIDE in self.permissions:
            derived.add("REVIEWER")
        if self.is_admin:
            derived.add("ADMIN")
        return derived

    def has(self, *required: str) -> bool:
        return bool(self.permissions.intersection(required))

    def can_review_scope(self, coverage_group: str | None) -> bool:
        if self.is_admin or "*" in self.coverage_groups:
            return True
        if not self.coverage_groups:
            # An unscoped reviewer holding CASE_VIEW_ALL is trusted across the
            # whole queue; scoping only narrows, it never grants.
            return perms.CASE_VIEW_ALL in self.permissions
        return coverage_group in self.coverage_groups


def _dev_principal() -> Principal:
    return Principal(
        subject="dev-user",
        username="dev-user",
        permissions=set(perms.ALL_PERMISSIONS),
        coverage_groups={"*"},
        is_admin=True,
        display_name="Development principal",
    )


def _bearer_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    return request.cookies.get(SESSION_COOKIE)


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> Principal:
    s = get_settings()
    if s.auth_disabled:
        if s.is_production:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication misconfigured")
        return _dev_principal()

    token = _bearer_token(request, credentials)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chưa đăng nhập")

    resolved = resolve_session(db, token)
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn")

    user, _session = resolved
    return Principal(
        subject=user.username,
        username=user.username,
        permissions=effective_permissions(user),
        coverage_groups={str(x) for x in (user.coverage_groups or [])},
        is_admin=bool(user.is_admin),
        display_name=user.display_name,
        must_change_password=bool(user.must_change_password),
    )


def require_perms(*required: str):
    """Allow the request when the caller holds any one of ``required``."""
    if not required:
        raise ValueError("require_perms needs at least one permission")
    unknown = set(required) - set(perms.ALL_PERMISSIONS)
    if unknown:
        raise ValueError(f"Unknown permission(s): {sorted(unknown)}")

    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.has(*required):
            logger.info(
                "authorization_denied",
                extra={"event": {"actor": p.username, "required": sorted(required)}},
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tài khoản không có quyền thực hiện thao tác này")
        return p

    return dep


def require_admin():
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị viên được phép")
        return p

    return dep
