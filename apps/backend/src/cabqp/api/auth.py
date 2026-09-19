"""Session endpoints: sign in (password or one-time code), sign out, read own
identity, change own password."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import otp as otp_service
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth import service as auth_service
from cabqp.modules.auth.dependencies import SESSION_COOKIE, Principal, current_principal
from cabqp.shared.db import get_db
from cabqp.shared.middleware import client_address
from cabqp.shared.models import AppUser
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class OtpRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class OtpVerifyRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    # Bounded so a huge body cannot be pushed through the PBKDF2 comparison; the
    # code itself is OTP_CODE_LENGTH digits.
    code: str = Field(min_length=1, max_length=16)


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
        metadata={"method": "PASSWORD", "client_ip": (request.client.host if request.client else None)},
    )
    db.commit()

    _set_session_cookie(response, token)
    return _session_payload(user, token, expires_at)


def _session_payload(user: AppUser, token: str, expires_at) -> dict:
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


def _set_session_cookie(response: Response, token: str) -> None:
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


def _otp_client_ip(request: Request) -> str:
    """The address the OTP budgets are charged to.

    Deliberately ``client_address`` — the same function the rate limiter uses —
    rather than ``request.client.host``: behind a trusted proxy the socket peer
    is the proxy, so every caller would share one budget, and in front of an
    untrusted one X-Forwarded-For must not be believed at all.
    """
    return client_address(request, get_settings().trusted_proxies)


@router.get("/methods")
def sign_in_methods():
    """Which sign-in methods this deployment actually offers.

    The frontend renders a tab from this. It is a description, not a permission:
    the OTP endpoints check the same setting themselves and refuse on their own.
    """
    s = get_settings()
    return {
        "password": True,
        "otp": s.otp_login_available,
        "otp_ttl_seconds": s.otp_ttl_seconds,
        "otp_code_length": s.otp_code_length,
        "otp_resend_after_seconds": s.otp_resend_cooldown_seconds,
    }


@router.post("/otp/request")
def request_login_otp(
    body: OtpRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Mail a one-time sign-in code.

    The response is identical whatever happened — sent, unknown account, no
    address on file, over budget — so this endpoint cannot be used to find out
    which usernames exist. Delivery itself runs after the response, which keeps
    the *timing* uninformative too and stops a slow mail server holding the
    request open. See ``modules/auth/otp.py`` for the full reasoning.
    """
    try:
        outcome = otp_service.request_code(
            db,
            body.username,
            client_ip=_otp_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except otp_service.OtpUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    if outcome.username:
        audit(
            db,
            actor=outcome.username,
            role="USER",
            action="AUTH_OTP_REQUESTED",
            entity_type="USER",
            entity_id=outcome.username,
            metadata={"reason": outcome.reason, "client_ip": _otp_client_ip(request)},
        )
    db.commit()

    logger.info(
        "otp_requested",
        extra={"event": {"reason": outcome.reason, "username": outcome.username}},
    )
    if outcome.send is not None:
        background.add_task(outcome.send)

    settings = get_settings()
    return {
        # Not "sent": the server is not telling the caller whether anything went
        # anywhere. It describes what to do next and nothing else.
        "accepted": True,
        "expires_in": settings.otp_ttl_seconds,
        "resend_after": settings.otp_resend_cooldown_seconds,
        "message": (
            "Nếu tài khoản tồn tại và có địa chỉ thư điện tử, mã đăng nhập đã được gửi tới hộp thư của tài khoản."
        ),
    }


@router.post("/otp/verify")
def verify_login_otp(
    body: OtpVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Redeem a code and open a session.

    Every failure answers 401 with one message, so a caller learns nothing from
    which code it got wrong. A wrong code also charges the account's ordinary
    failed-attempt counter, so this path locks an account out exactly as
    password guessing does.
    """
    try:
        user, token, expires_at = otp_service.verify_code(
            db,
            body.username,
            body.code,
            client_ip=_otp_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except otp_service.OtpUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except auth_service.AuthError as exc:
        db.commit()  # persist the attempt counters before answering
        logger.info("otp_login_failed", extra={"event": {"username": body.username}})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    audit(
        db,
        actor=user.username,
        role="ADMIN" if user.is_admin else "USER",
        action="AUTH_LOGIN",
        entity_type="USER",
        entity_id=user.username,
        metadata={"method": "OTP", "client_ip": _otp_client_ip(request)},
    )
    db.commit()
    _set_session_cookie(response, token)
    return _session_payload(user, token, expires_at)


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
