from __future__ import annotations

from enum import Enum
from typing import Any


class Role(Enum):
    USER = "user"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"


_PERMISSIONS: dict[str, list[Role]] = {
    "entity:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "entity:create": [Role.ANALYST, Role.ADMIN],
    "entity:update": [Role.ANALYST, Role.ADMIN],
    "entity:delete": [Role.ADMIN],
    "relationship:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "relationship:create": [Role.ANALYST, Role.ADMIN],
    "relationship:delete": [Role.ADMIN],
    "task:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "task:create": [Role.ANALYST, Role.ADMIN],
    "evidence:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "verification:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "verification:update": [Role.REVIEWER, Role.ADMIN],
    "source:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "admin:access": [Role.ADMIN],
    "nlp:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "nlp:write": [Role.ANALYST, Role.ADMIN],
    "nlp:admin": [Role.ADMIN],
    "cognitive:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "cognitive:write": [Role.ANALYST, Role.ADMIN],
    "cognitive:admin": [Role.ADMIN],
    "agent:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "agent:write": [Role.ANALYST, Role.ADMIN],
    "agent:admin": [Role.ADMIN],
    "agent:safety": [Role.ADMIN],
    "tenant:admin": [Role.ADMIN],
    "metaintel:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "metaintel:write": [Role.ANALYST, Role.ADMIN],
    "metaintel:admin": [Role.ADMIN],
    "ucos:read": [Role.USER, Role.ANALYST, Role.REVIEWER, Role.ADMIN],
    "ucos:write": [Role.ANALYST, Role.ADMIN],
    "ucos:admin": [Role.ADMIN],
}


def get_permissions() -> dict[str, list[Role]]:
    return dict(_PERMISSIONS)


def has_permission(role: Role | str, permission: str) -> bool:
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False
    allowed = _PERMISSIONS.get(permission, [])
    return role in allowed


def user_role(user_data: dict[str, Any] | None) -> Role:
    if user_data is None:
        return Role.USER
    return Role(user_data.get("role", "user"))
