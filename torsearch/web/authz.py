from __future__ import annotations

from fastapi import HTTPException, Request

from torsearch.users.store import Role, role_at_least


def effective_role(request: Request) -> str:
    """Role driving authorization. Auth disabled => everyone is admin (open app)."""
    auth = getattr(request.app.state, "auth", None)
    if not (auth and getattr(auth, "enabled", False)):
        return Role.ADMIN.value
    try:
        return request.session.get("role") or Role.GUEST.value
    except (AssertionError, AttributeError):
        return Role.GUEST.value


def require_role(minimum: Role):
    async def dep(request: Request) -> None:
        if not role_at_least(effective_role(request), minimum):
            raise HTTPException(status_code=403, detail="Acces refuse")
    return dep


require_admin = require_role(Role.ADMIN)
require_member = require_role(Role.MEMBER)
