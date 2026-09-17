"""Session endpoints: sign in, sign out, read own identity, change own password."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth import service as auth_service
from cabqp.modules.auth.dependencies import SESSION_COOKIE, Principal, current_principal
from cabqp.shared.db import get_db
from cabqp.shared.models import AppUser
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=auth_service.MIN_PASSWORD_LENGTH, max_length=256)


def _principal_payload(p: Principal) -> dict:
    return {
        "username": p.username,
        "display_name": p.display_name,
        "is_admin": p.is_admin,
        "permissions": sorted(p.permissions),
        "coverage_groups": sorted(p.coverage_groups),
        "must_change_password": p.must_change_password,
        # Compatibility projection over the permission set, not a second
        # authority: the server never reads roles back from the client.
        "roles": sorted(p.roles),
    }


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user, token, expires_at = auth_service.authenticate(
            db,
            body.username,
            body.password,
            user_agent=request.headers.get("user-agent"),
            client_ip=(request.client.host if request.client else None),
        )
    except auth_service.AuthError as exc:
        db.commit()  # persist the failed-attempt counter before answering
        logger.info("login_failed", extra={"event": {"username": body.username}})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    audit(
        db,
        actor=user.username,
        role="ADMIN" if user.is_admin else "USER",
        action="AUTH_LOGIN",
        entity_type="USER",
        entity_id=user.username,
        metadata={"client_ip": (request.client.host if request.client else None)},
    )
    db.commit()

    # The cookie is a convenience for same-origin browser use; the Authorization
    # header carrying the same opaque token works identically.
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
        max_age=int(auth_service.session_lifetime().total_seconds()),
        path="/",
    )
    permissions = auth_service.effective_permissions(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
            "permissions": sorted(permissions),
            "coverage_groups": sorted(str(x) for x in (user.coverage_groups or [])),
            "must_change_password": user.must_change_password,
            "roles": sorted(
                {"USER"}
                | ({"REVIEWER"} if perms.REVIEW_DECIDE in permissions else set())
                | ({"ADMIN"} if user.is_admin else set())
            ),
        },
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE)
    revoked = auth_service.revoke_session(db, token or "")
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"revoked": revoked}


@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    """The caller's own identity and effective permissions.

    The frontend uses this to render navigation. It is a description of what the
    server will allow, never the thing that allows it.
    """
    return _principal_payload(p)


@router.get("/permissions")
def permission_catalog(p: Principal = Depends(current_principal)):
    return {"items": list(perms.PERMISSION_CATALOG), "presets": {k: list(v) for k, v in perms.PRESETS.items()}}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    user = db.get(AppUser, p.username)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tài khoản không tồn tại")
    if not auth_service.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu hiện tại không đúng")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu mới phải khác mật khẩu hiện tại")
    try:
        auth_service.set_password(db, user, body.new_password, must_change=False)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit(
        db,
        actor=user.username,
        role="ADMIN" if user.is_admin else "USER",
        action="AUTH_PASSWORD_CHANGE",
        entity_type="USER",
        entity_id=user.username,
        metadata={},
    )
    db.commit()
    return {"changed": True}
