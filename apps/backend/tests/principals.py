"""Principal factories for tests.

Accounts hold permissions, not roles, so tests build principals from the same
presets an administrator applies in the admin screen. Constructing them here
keeps every test honest about which permission it is actually exercising.
"""

from __future__ import annotations

from cabqp.modules.auth import permissions as perms
from cabqp.modules.auth.dependencies import Principal


def user_principal(username="alice", *, permissions=None, coverage_groups=()):
    return Principal(
        subject=f"sub-{username}",
        username=username,
        permissions=set(permissions if permissions is not None else perms.USER_PRESET),
        coverage_groups=set(coverage_groups),
        is_admin=False,
        display_name=username,
    )


def reviewer_principal(username="reviewer", *, coverage_groups=("*",), permissions=None):
    """An account carrying the "cán bộ thẩm định" permission set."""
    return user_principal(
        username,
        permissions=permissions if permissions is not None else perms.REVIEWER_PRESET,
        coverage_groups=coverage_groups,
    )


def admin_principal(username="admin"):
    return Principal(
        subject=f"sub-{username}",
        username=username,
        permissions=set(perms.ALL_PERMISSIONS),
        coverage_groups={"*"},
        is_admin=True,
        display_name=username,
    )
