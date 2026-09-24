"""Server-side permission catalog.

The catalog is the single authority on what an account may do. The frontend is
told an account's effective permissions only so it can render a sensible
navigation; it is never the thing that decides access. Every route resolves its
own requirement against this catalog on every request, so a client that forges
its local state, edits the bundle or calls the API directly gains nothing.

Accounts hold permissions directly — there is no separate REVIEWER role to
assign. "Cán bộ thẩm định" is the ``REVIEWER_PRESET`` bundle of permissions an
administrator toggles on an account.
"""

from __future__ import annotations

from typing import Final

# --- Catalog -----------------------------------------------------------------

CASE_CREATE: Final = "CASE_CREATE"
CASE_BULK: Final = "CASE_BULK"
CASE_VIEW_ALL: Final = "CASE_VIEW_ALL"
CASE_EXPORT: Final = "CASE_EXPORT"
LOOKUP_UNIT: Final = "LOOKUP_UNIT"
REVIEW_QUEUE: Final = "REVIEW_QUEUE"
REVIEW_DECIDE: Final = "REVIEW_DECIDE"
REGISTRY_ADMIN: Final = "REGISTRY_ADMIN"
PERSON_REGISTRY_ADMIN: Final = "PERSON_REGISTRY_ADMIN"
AUDIT_VIEW: Final = "AUDIT_VIEW"
USER_ADMIN: Final = "USER_ADMIN"

# Ordered for stable rendering in the admin screen. The Vietnamese label is the
# operator-facing name; the description states what the permission actually
# unlocks so an administrator is not guessing from the identifier.
PERMISSION_CATALOG: Final[tuple[dict[str, str], ...]] = (
    {
        "code": CASE_CREATE,
        "label": "Tạo hồ sơ tra cứu",
        "description": "Nhập text hoặc tải tài liệu để tạo Case xác minh.",
        "group": "Nghiệp vụ",
    },
    {
        "code": CASE_BULK,
        "label": "Tra cứu theo lô",
        "description": "Tải danh sách nhiều người và xử lý mỗi dòng thành một Case.",
        "group": "Nghiệp vụ",
    },
    {
        "code": LOOKUP_UNIT,
        "label": "Tra cứu đơn vị",
        "description": "Gọi resolver đơn vị trực tiếp để tra tên đơn vị.",
        "group": "Nghiệp vụ",
    },
    {
        "code": CASE_EXPORT,
        "label": "Kết xuất dữ liệu",
        "description": "Xuất kết quả và lịch sử ra CSV/XLSX.",
        "group": "Nghiệp vụ",
    },
    {
        "code": CASE_VIEW_ALL,
        "label": "Xem hồ sơ toàn hệ thống",
        "description": "Xem mọi Case, không giới hạn ở hồ sơ do tài khoản tự tạo.",
        "group": "Thẩm định",
    },
    {
        "code": REVIEW_QUEUE,
        "label": "Xem hàng đợi thẩm định",
        "description": "Mở danh sách Case đang chờ xác minh thủ công.",
        "group": "Thẩm định",
    },
    {
        "code": REVIEW_DECIDE,
        "label": "Ra quyết định thẩm định",
        "description": "Nhận việc và kết luận Case trong hàng đợi thẩm định.",
        "group": "Thẩm định",
    },
    {
        "code": REGISTRY_ADMIN,
        "label": "Quản trị danh mục đơn vị",
        "description": "QA, tạo version và publish Master Unit Registry.",
        "group": "Quản trị",
    },
    {
        "code": PERSON_REGISTRY_ADMIN,
        "label": "Quản trị danh mục nhân sự",
        "description": "QA, tạo version và publish Person Registry.",
        "group": "Quản trị",
    },
    {
        "code": AUDIT_VIEW,
        "label": "Xem nhật ký kiểm toán",
        "description": "Tra vết audit log của hệ thống.",
        "group": "Quản trị",
    },
    {
        "code": USER_ADMIN,
        "label": "Quản trị tài khoản",
        "description": "Tạo tài khoản cán bộ và cấp/thu hồi quyền.",
        "group": "Quản trị",
    },
)

ALL_PERMISSIONS: Final[frozenset[str]] = frozenset(x["code"] for x in PERMISSION_CATALOG)

# --- Presets -----------------------------------------------------------------

#: Baseline an ordinary tra cứu account gets when an administrator creates it.
USER_PRESET: Final[tuple[str, ...]] = (CASE_CREATE, CASE_BULK, LOOKUP_UNIT, CASE_EXPORT)

#: "Cán bộ thẩm định" reduced to permissions rather than a separate role.
REVIEWER_PRESET: Final[tuple[str, ...]] = (
    *USER_PRESET,
    CASE_VIEW_ALL,
    REVIEW_QUEUE,
    REVIEW_DECIDE,
)

PRESETS: Final[dict[str, tuple[str, ...]]] = {
    "USER": USER_PRESET,
    "REVIEWER": REVIEWER_PRESET,
}


def normalize(permissions) -> list[str]:
    """Drop unknown codes and return catalog order.

    Unknown codes are dropped rather than rejected so a permission retired from
    the catalog cannot keep granting access through a stale stored row.
    """
    requested = {str(x).strip().upper() for x in (permissions or [])}
    return [x["code"] for x in PERMISSION_CATALOG if x["code"] in requested]
