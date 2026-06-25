from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

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
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[User]:
        if not self._path.exists():
            return []
        return [User.model_validate(u) for u in json.loads(self._path.read_text())]

    def _save(self, users: list[User]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([u.model_dump(mode="json") for u in users], indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[User]:
        return self._load()

    def get(self, username: str) -> User | None:
        return next((u for u in self._load() if u.username == username), None)

    def is_empty(self) -> bool:
        return not self._load()

    def count_admins(self, users: list[User] | None = None) -> int:  # type: ignore[valid-type]  # `list` method shadows builtin
        return sum(1 for u in (users if users is not None else self._load()) if u.role == Role.ADMIN)

    def verify(self, username: str, password: str) -> User | None:
        user = self.get(username)
        if user and verify_password(password, user.password_hash):
            return user
        return None

    def add(self, username: str, password: str, role: Role) -> User:
        users = self._load()
        if any(u.username == username for u in users):
            raise UserError(f"L'utilisateur « {username} » existe deja.")
        user = User(username=username, password_hash=hash_password(password), role=Role(role))
        users.append(user)
        self._save(users)
        return user

    def remove(self, username: str) -> None:
        users = self._load()
        target = next((u for u in users if u.username == username), None)
        if target is None:
            return
        if target.role == Role.ADMIN and self.count_admins(users) <= 1:
            raise UserError("Impossible de supprimer le dernier administrateur.")
        self._save([u for u in users if u.username != username])

    def set_role(self, username: str, role: Role) -> None:
        users = self._load()
        role = Role(role)
        target = next((u for u in users if u.username == username), None)
        if target is None:
            raise UserError(f"Utilisateur « {username} » introuvable.")
        if target.role == Role.ADMIN and role != Role.ADMIN and self.count_admins(users) <= 1:
            raise UserError("Impossible de retrograder le dernier administrateur.")
        for i, u in enumerate(users):
            if u.username == username:
                users[i] = u.model_copy(update={"role": role})
        self._save(users)

    def set_password(self, username: str, password: str) -> None:
        users = self._load()
        for i, u in enumerate(users):
            if u.username == username:
                users[i] = u.model_copy(update={"password_hash": hash_password(password)})
        self._save(users)

    def bootstrap_admin(self, username: str, password: str) -> bool:
        if not self.is_empty():
            return False
        self.add(username, password, Role.ADMIN)
        return True
