from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from torsearch.db.database import Collection
from torsearch.users.passwords import hash_password, verify_password


class Role(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"


_RANK = {Role.GUEST: 0, Role.MEMBER: 1, Role.ADMIN: 2}


def role_at_least(role: str | None, needed: Role) -> bool:
    try:
        current = Role(role)
    except (ValueError, TypeError):
        return False
    return _RANK[current] >= _RANK[needed]


class User(BaseModel):
    username: str
    password_hash: str
    role: Role = Role.GUEST


class UserError(Exception):
    """Raised on invalid user-store operations (duplicate, last-admin, ...)."""


class UserStore:
    def __init__(self, collection: Collection, migrate_from: str | Path | None = None):
        self._c = collection
        if migrate_from is not None:
            self._migrate(Path(migrate_from))

    def _migrate(self, path: Path) -> None:
        """One-time import of a legacy users.json into the (empty) SQLite collection."""
        if not path.exists() or not self._c.is_empty():
            return
        try:
            items = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        self._c.replace_all([(u["username"], u) for u in items if u.get("username")])

    def list(self) -> list[User]:
        return [User.model_validate(d) for d in self._c.all()]

    def get(self, username: str) -> User | None:
        data = self._c.get(username)
        return User.model_validate(data) if data else None

    def is_empty(self) -> bool:
        return self._c.is_empty()

    def count_admins(self) -> int:
        return sum(1 for u in self.list() if u.role == Role.ADMIN)

    def verify(self, username: str, password: str) -> User | None:
        user = self.get(username)
        if user and verify_password(password, user.password_hash):
            return user
        return None

    def _put(self, user: User) -> None:
        self._c.upsert(user.username, user.model_dump(mode="json"))

    def add(self, username: str, password: str, role: Role) -> User:
        if self.get(username) is not None:
            raise UserError(f"L'utilisateur « {username} » existe deja.")
        user = User(username=username, password_hash=hash_password(password), role=Role(role))
        self._put(user)
        return user

    def remove(self, username: str) -> None:
        target = self.get(username)
        if target is None:
            return
        if target.role == Role.ADMIN and self.count_admins() <= 1:
            raise UserError("Impossible de supprimer le dernier administrateur.")
        self._c.delete(username)

    def set_role(self, username: str, role: Role) -> None:
        role = Role(role)
        target = self.get(username)
        if target is None:
            raise UserError(f"Utilisateur « {username} » introuvable.")
        if target.role == Role.ADMIN and role != Role.ADMIN and self.count_admins() <= 1:
            raise UserError("Impossible de retrograder le dernier administrateur.")
        self._put(target.model_copy(update={"role": role}))

    def set_password(self, username: str, password: str) -> None:
        target = self.get(username)
        if target is not None:
            self._put(target.model_copy(update={"password_hash": hash_password(password)}))

    def bootstrap_admin(self, username: str, password: str) -> bool:
        if not self.is_empty():
            return False
        self.add(username, password, Role.ADMIN)
        return True
