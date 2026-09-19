"""Account administration.

An administrator enters the officer's administrative particulars (mã số cán bộ,
họ và tên, năm sinh, cấp bậc, chức vụ, phòng/ban, đơn vị) and the system issues
the account: the login id is the username, the password is generated at random
and shown to the administrator once.

Administrator accounts are not creatable here. Exactly one exists and the
seeder owns it, so there is no path through this API that mints new
system-wide authority.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth import service as auth_service
from cabqp.modules.auth.dependencies import Principal, require_perms
from cabqp.modules.notifications import email as mailer
from cabqp.shared.db import get_db
from cabqp.shared.models import AppUser

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

USER_ADMIN = Depends(require_perms(perms.USER_ADMIN))

MIN_BIRTH_YEAR = 1900
MAX_BIRTH_YEAR = 2100


class UserCreate(BaseModel):
    """Vietnamese administrative particulars for a new account."""

    display_name: str = Field(min_length=1, max_length=255, description="Họ và tên")
    personal_code: str | None = Field(default=None, max_length=64, description="Mã số cán bộ")
    birth_year: int | None = Field(default=None, description="Năm sinh")
    rank: str | None = Field(default=None, max_length=120, description="Cấp bậc")
    position: str | None = Field(default=None, max_length=255, description="Chức vụ")
    department: str | None = Field(default=None, max_length=255, description="Phòng/Ban")
    unit_name: str | None = Field(default=None, max_length=500, description="Đơn vị công tác")
    phone: str | None = Field(default=None, max_length=40)
    email: str = Field(
        min_length=3,
        max_length=255,
        description="Bắt buộc: mật khẩu khởi tạo được gửi tới địa chỉ này",
    )
    username: str | None = Field(
        default=None, max_length=64, description="Bỏ trống để hệ thống tự sinh từ mã số/họ tên"
    )
    permissions: list[str] = Field(default_factory=lambda: list(perms.USER_PRESET))
    coverage_groups: list[str] = Field(default_factory=list)

    @field_validator("birth_year")
    @classmethod
    def _check_birth_year(cls, value: int | None) -> int | None:
        if value is not None and not (MIN_BIRTH_YEAR <= value <= MAX_BIRTH_YEAR):
            raise ValueError(f"Năm sinh phải trong khoảng {MIN_BIRTH_YEAR}-{MAX_BIRTH_YEAR}")
        return value

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        if not mailer.is_valid_email(value):
            raise ValueError("Thư điện tử không hợp lệ")
        return value.strip()


class UsernameSuggestion(BaseModel):
    """Only the fields the login id is derived from."""

    display_name: str = Field(min_length=1, max_length=255)
    personal_code: str | None = Field(default=None, max_length=64)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    personal_code: str | None = Field(default=None, max_length=64)
    birth_year: int | None = None
    rank: str | None = Field(default=None, max_length=120)
    position: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    unit_name: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = None
    coverage_groups: list[str] | None = None
    is_active: bool | None = None

    @field_validator("birth_year")
    @classmethod
    def _check_birth_year(cls, value: int | None) -> int | None:
        if value is not None and not (MIN_BIRTH_YEAR <= value <= MAX_BIRTH_YEAR):
            raise ValueError(f"Năm sinh phải trong khoảng {MIN_BIRTH_YEAR}-{MAX_BIRTH_YEAR}")
        return value

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str | None) -> str | None:
        # None means "leave unchanged"; an explicit value must still be reachable,
        # because password resets are delivered there.
        if value is None:
            return None
        if not mailer.is_valid_email(value):
            raise ValueError("Thư điện tử không hợp lệ")
        return value.strip()


def _serialize(user: AppUser) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "personal_code": user.personal_code,
        "birth_year": user.birth_year,
        "rank": user.rank,
        "position": user.position,
        "department": user.department,
        "unit_name": user.unit_name,
        "phone": user.phone,
        "email": user.email,
        "permissions": perms.normalize(user.permissions) if not user.is_admin else sorted(perms.ALL_PERMISSIONS),
        "coverage_groups": [str(x) for x in (user.coverage_groups or [])],
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "locked_until": user.locked_until,
        "last_login_at": user.last_login_at,
        "created_by": user.created_by,
        "created_at": user.created_at,
    }


def _credential_response(user: AppUser, plaintext: str, delivery) -> dict:
    """Describe where the password went — and hand it back only if it went nowhere.

    On successful delivery the password is not returned at all: showing it on
    screen as well would defeat the point of mailing it. When delivery fails the
    administrator does need it, so it is returned with the failure stated
    plainly rather than the account being left unusable.
    """
    payload = {"email": user.email, "email_delivery": delivery.as_dict()}
    if delivery.ok:
        payload["initial_password"] = None
        payload["notice"] = (
            f"Mật khẩu đã được gửi tới {user.email}. "
            "Hệ thống không hiển thị lại mật khẩu; nếu cán bộ không nhận được, hãy cấp lại."
        )
    else:
        payload["initial_password"] = plaintext
        payload["notice"] = (
            f"Không gửi được thư tới {user.email} ({delivery.detail or 'không rõ nguyên nhân'}). "
            "Mật khẩu hiển thị một lần dưới đây — hãy bàn giao trực tiếp và kiểm tra lại cấu hình thư."
        )
    return payload


def _target(db: Session, username: str) -> AppUser:
    user = db.get(AppUser, (username or "").strip().lower())
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tài khoản không tồn tại")
    return user


def _guard_admin_target(user: AppUser) -> None:
    if user.is_admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tài khoản quản trị không thể chỉnh sửa hoặc thu hồi quyền qua giao diện này",
        )


@router.get("")
def list_users(
    q: str | None = Query(default=None, max_length=120),
    include_inactive: bool = Query(default=True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    p: Principal = USER_ADMIN,
):
    query = select(AppUser)
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(AppUser.username).like(needle),
                func.lower(AppUser.display_name).like(needle),
                func.lower(func.coalesce(AppUser.personal_code, "")).like(needle),
                func.lower(func.coalesce(AppUser.department, "")).like(needle),
            )
        )
    if not include_inactive:
        query = query.where(AppUser.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(AppUser.is_admin.desc(), AppUser.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [_serialize(x) for x in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "catalog": list(perms.PERMISSION_CATALOG),
        "presets": {k: list(v) for k, v in perms.PRESETS.items()},
    }


@router.post("/suggest-username")
def suggest(body: UsernameSuggestion, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    """Preview the login id the system would issue, before creating the account."""
    base = auth_service.suggest_username(
        personal_code=body.personal_code, display_name=body.display_name
    )
    if not base:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể sinh tên đăng nhập từ thông tin đã nhập")
    try:
        return {"username": auth_service.allocate_username(db, base)}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    if body.username:
        try:
            username = auth_service.validate_username(body.username)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        if db.get(AppUser, username) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Tài khoản '{username}' đã tồn tại")
    else:
        base = auth_service.suggest_username(
            personal_code=body.personal_code, display_name=body.display_name
        )
        if not base:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Không thể sinh tên đăng nhập từ thông tin đã nhập"
            )
        try:
            username = auth_service.allocate_username(db, base)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        user, plaintext = auth_service.create_user(
            db,
            username=username,
            display_name=body.display_name,
            permissions=body.permissions,
            coverage_groups=body.coverage_groups,
            personal_code=body.personal_code,
            birth_year=body.birth_year,
            position=body.position,
            department=body.department,
            unit_name=body.unit_name,
            rank=body.rank,
            phone=body.phone,
            email=body.email,
            is_admin=False,
            must_change_password=True,
            created_by=p.username,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    delivery = mailer.send_new_account_email(
        to=user.email,
        display_name=user.display_name,
        username=user.username,
        password=plaintext,
    )
    audit(
        db,
        actor=p.username,
        role="ADMIN",
        action="USER_CREATE",
        entity_type="USER",
        entity_id=user.username,
        # The generated password itself is deliberately absent; the generator's
        # entropy and the delivery outcome are what an auditor needs.
        metadata={
            "permissions": perms.normalize(user.permissions),
            "personal_code": user.personal_code,
            "password_entropy_bits": auth_service.password_entropy_bits(),
            "email_delivery": delivery.as_dict(),
        },
    )
    db.commit()
    return {"user": _serialize(user), **_credential_response(user, plaintext, delivery)}


@router.patch("/{username}")
def update_user(
    username: str, body: UserUpdate, db: Session = Depends(get_db), p: Principal = USER_ADMIN
):
    user = _target(db, username)
    _guard_admin_target(user)

    changes: dict[str, object] = {}
    for field in (
        "display_name",
        "personal_code",
        "birth_year",
        "rank",
        "position",
        "department",
        "unit_name",
        "phone",
        "email",
        "is_active",
    ):
        value = getattr(body, field)
        if value is not None and getattr(user, field) != value:
            setattr(user, field, value)
            changes[field] = value

    if body.permissions is not None:
        normalized = perms.normalize(body.permissions)
        if normalized != perms.normalize(user.permissions):
            user.permissions = normalized
            changes["permissions"] = normalized
    if body.coverage_groups is not None:
        groups = [str(x).strip() for x in body.coverage_groups if str(x).strip()]
        if groups != [str(x) for x in (user.coverage_groups or [])]:
            user.coverage_groups = groups
            changes["coverage_groups"] = groups

    if body.is_active is False:
        # Sessions carry no authority of their own, but ending them makes a
        # deactivation visible to the operator immediately.
        auth_service.revoke_all_sessions(db, user.username)

    if not changes:
        db.commit()
        return {"user": _serialize(user), "changed": False}

    db.flush()
    audit(
        db,
        actor=p.username,
        role="ADMIN",
        action="USER_UPDATE",
        entity_type="USER",
        entity_id=user.username,
        metadata={"changes": changes},
    )
    db.commit()
    return {"user": _serialize(user), "changed": True}


@router.post("/{username}/reset-password")
def reset_user_password(username: str, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    user = _target(db, username)
    _guard_admin_target(user)
    if not mailer.is_valid_email(user.email):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tài khoản chưa có thư điện tử hợp lệ; hãy cập nhật địa chỉ trước khi cấp lại mật khẩu",
        )
    plaintext = auth_service.reset_password(db, user)
    delivery = mailer.send_password_reset_email(
        to=user.email,
        display_name=user.display_name,
        username=user.username,
        password=plaintext,
    )
    audit(
        db,
        actor=p.username,
        role="ADMIN",
        action="USER_PASSWORD_RESET",
        entity_type="USER",
        entity_id=user.username,
        metadata={
            "password_entropy_bits": auth_service.password_entropy_bits(),
            "email_delivery": delivery.as_dict(),
        },
    )
    db.commit()
    return {"username": user.username, **_credential_response(user, plaintext, delivery)}


@router.post("/{username}/unlock")
def unlock_user(username: str, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    user = _target(db, username)
    user.failed_attempts = 0
    user.locked_until = None
    db.flush()
    audit(
        db,
        actor=p.username,
        role="ADMIN",
        action="USER_UNLOCK",
        entity_type="USER",
        entity_id=user.username,
        metadata={},
    )
    db.commit()
    return {"username": user.username, "locked_until": None}


@router.post("/{username}/revoke-sessions")
def revoke_sessions(username: str, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    user = _target(db, username)
    count = auth_service.revoke_all_sessions(db, user.username)
    audit(
        db,
        actor=p.username,
        role="ADMIN",
        action="USER_SESSIONS_REVOKED",
        entity_type="USER",
        entity_id=user.username,
        metadata={"revoked": count},
    )
    db.commit()
    return {"username": user.username, "revoked": count}


@router.delete("/{username}")
def delete_user(username: str, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    """Permanently remove an account.

    The Cases it created and the audit rows naming it are left alone: both
    record the actor as a username string rather than a foreign key, so deleting
    the account never rewrites what it did. The deletion is itself audited.
    """
    user = _target(db, username)
    _guard_admin_target(user)
    if user.username == p.username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể tự xóa tài khoản đang đăng nhập")

    snapshot = {
        "display_name": user.display_name,
        "personal_code": user.personal_code,
        "email": user.email,
        "department": user.department,
        "permissions": perms.normalize(user.permissions),
    }
    revoked = auth_service.delete_user(db, user)
    audit(
        db,
        actor=p.username,
        role="ADMIN",
        action="USER_DELETE",
        entity_type="USER",
        entity_id=username,
        metadata={"deleted_account": snapshot, "sessions_revoked": revoked},
    )
    db.commit()
    return {"username": username, "deleted": True, "sessions_revoked": revoked}


@router.get("/{username}")
def get_user(username: str, db: Session = Depends(get_db), p: Principal = USER_ADMIN):
    user = _target(db, username)
    payload = _serialize(user)
    payload["catalog"] = list(perms.PERMISSION_CATALOG)
    return payload
