from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import UTC, datetime

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import BaseModel

from torsearch.db.database import Collection
from torsearch.users.store import Role, UserStore, role_at_least
from torsearch.web.auth import session_fingerprint

SCOPE = "torrsearch"
PENDING_TTL = 600  # the user has 10 minutes to log in on the consent page
CODE_TTL = 300
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600

# The endpoint is public: strangers can register clients and open consents, so what they can
# store is bounded, and codes only ever go back to Claude (no phishing, no open redirect).
ALLOWED_REDIRECT_URIS = frozenset({
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
})
MAX_CLIENT_NAME = 100
MAX_CLIENT_RECORD = 4096  # bytes of JSON per registered client
MAX_IDLE_CLIENTS = 20  # registered clients holding no access
MAX_PENDING = 20
MAX_STATE = 1024
_EXPIRING = ("pending", "code", "access", "refresh")


class PendingRequest(BaseModel):
    request_id: str
    client_id: str
    client_name: str
    params: AuthorizationParams
    expires_at: float


class Grant(BaseModel):
    client_id: str
    client_name: str
    username: str
    granted_at: datetime


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class TorrSearchOAuthProvider:
    """OAuth authorization server for Claude's connector (MCP SDK provider protocol).

    Only an admin account can grant access, on TorrSearch's own consent page. Codes and
    tokens are stored by SHA-256 digest, never in clear, and carry a fingerprint of the
    owner's password hash: a deleted, demoted or re-passworded account kills them.
    """

    def __init__(self, collection: Collection, users: UserStore, secret_key: str, public_url: str,
                 clock=time.time):
        self._c = collection
        self._users = users
        self._secret = secret_key
        self._public_url = public_url.rstrip("/")
        self._clock = clock

    # --- helpers ---------------------------------------------------------------------

    def _fingerprint(self, username: str) -> str | None:
        user = self._users.get(username)
        if user is None or not role_at_least(user.role, Role.ADMIN):
            return None
        return session_fingerprint(user.password_hash, self._secret)

    def _owner_valid(self, doc: dict) -> bool:
        fingerprint = self._fingerprint(doc.get("subject") or "")
        return fingerprint is not None and fingerprint == doc.get("fingerprint")

    def _live(self, key: str) -> dict | None:
        doc = self._c.get(key)
        if doc is None:
            return None
        if doc.get("expires_at") is not None and doc["expires_at"] <= self._clock():
            self._c.delete(key)
            return None
        return doc

    def _issue(self, client_id: str, scopes: list[str], subject: str, fingerprint: str,
               granted_at: str | None = None) -> OAuthToken:
        self._purge_expired()
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = self._clock()
        owner = {"client_id": client_id, "scopes": scopes, "subject": subject, "fingerprint": fingerprint}
        self._c.upsert(f"access:{_digest(access)}",
                       {**owner, "expires_at": int(now + ACCESS_TTL), "refresh": _digest(refresh)})
        self._c.upsert(f"refresh:{_digest(refresh)}", {
            **owner, "expires_at": int(now + REFRESH_TTL), "access": _digest(access),
            "granted_at": granted_at or datetime.now(UTC).isoformat(),
        })
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL, scope=" ".join(scopes), refresh_token=refresh)

    def _purge_expired(self) -> None:
        now = self._clock()
        for key, doc in self._c.items():
            if key.split(":", 1)[0] in _EXPIRING and doc.get("expires_at") is not None and doc["expires_at"] <= now:
                self._c.delete(key)

    def _prune_idle_clients(self) -> None:
        """Keep the newest ``MAX_IDLE_CLIENTS`` clients that hold no refresh token."""
        items = self._c.items()
        holders = {doc["client_id"] for key, doc in items if key.startswith("refresh:")}
        idle = sorted(((doc.get("client_id_issued_at") or 0, key) for key, doc in items
                       if key.startswith("client:") and key[len("client:"):] not in holders), reverse=True)
        for _, key in idle[MAX_IDLE_CLIENTS:]:
            self._c.delete(key)

    def _drop_pair(self, access_digest: str | None, refresh_digest: str | None) -> None:
        if access_digest:
            self._c.delete(f"access:{access_digest}")
        if refresh_digest:
            self._c.delete(f"refresh:{refresh_digest}")

    # --- clients -----------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        doc = self._c.get(f"client:{client_id}")
        return OAuthClientInformationFull.model_validate(doc) if doc else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in client_info.redirect_uris or []]
        if not uris or any(u not in ALLOWED_REDIRECT_URIS for u in uris):
            raise RegistrationError("invalid_redirect_uri", "Seul Claude (claude.ai) peut se connecter.")
        record = client_info.model_dump(mode="json")
        if len(client_info.client_name or "") > MAX_CLIENT_NAME or len(json.dumps(record)) > MAX_CLIENT_RECORD:
            raise RegistrationError("invalid_client_metadata", "Description du client trop longue.")
        self._purge_expired()
        self._c.upsert(f"client:{client_info.client_id}", record)
        self._prune_idle_clients()

    # --- consent -----------------------------------------------------------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if params.state and len(params.state) > MAX_STATE:
            raise AuthorizeError("invalid_request", "Parametre state trop long.")
        self._purge_expired()
        waiting = sorted((doc["expires_at"], key) for key, doc in self._c.items() if key.startswith("pending:"))
        for _, key in waiting[: max(0, len(waiting) - MAX_PENDING + 1)]:
            self._c.delete(key)  # the oldest consents give way
        request_id = secrets.token_urlsafe(16)
        pending = PendingRequest(request_id=request_id, client_id=client.client_id,
                                 client_name=client.client_name or client.client_id, params=params,
                                 expires_at=self._clock() + PENDING_TTL)
        self._c.upsert(f"pending:{request_id}", pending.model_dump(mode="json"))
        return f"{self._public_url}/claude/autoriser?demande={request_id}"

    def pending(self, request_id: str) -> PendingRequest | None:
        doc = self._live(f"pending:{request_id}")
        return PendingRequest.model_validate(doc) if doc else None

    def _take_pending(self, request_id: str) -> PendingRequest:
        pending = self.pending(request_id)
        if pending is None:
            raise ValueError("Demande inconnue ou expiree")
        self._c.delete(f"pending:{request_id}")
        return pending

    def approve(self, request_id: str, username: str) -> str:
        """The admin ``username`` granted access: a one-time code goes back to the client."""
        fingerprint = self._fingerprint(username)
        if fingerprint is None:
            raise ValueError("Seul un administrateur peut autoriser Claude")
        pending = self._take_pending(request_id)
        params = pending.params
        code = secrets.token_urlsafe(32)
        self._c.upsert(f"code:{_digest(code)}", {
            "client_id": pending.client_id, "scopes": params.scopes or [SCOPE],
            "expires_at": self._clock() + CODE_TTL, "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "resource": params.resource, "subject": username, "fingerprint": fingerprint,
        })
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    def deny(self, request_id: str) -> str:
        params = self._take_pending(request_id).params
        return construct_redirect_uri(str(params.redirect_uri), error="access_denied",
                                      error_description="Acces refuse par l'utilisateur", state=params.state)

    # --- codes and tokens --------------------------------------------------------------

    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        doc = self._live(f"code:{_digest(authorization_code)}")
        if doc is None or doc["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code, scopes=doc["scopes"], expires_at=doc["expires_at"],
            client_id=doc["client_id"], code_challenge=doc["code_challenge"], redirect_uri=doc["redirect_uri"],
            redirect_uri_provided_explicitly=doc["redirect_uri_provided_explicitly"], resource=doc.get("resource"),
            subject=doc["subject"],
        )

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        key = f"code:{_digest(authorization_code.code)}"
        doc = self._c.get(key) or {}
        self._c.delete(key)  # single use
        return self._issue(client.client_id, authorization_code.scopes, authorization_code.subject or "",
                           doc.get("fingerprint", ""))

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        doc = self._live(f"refresh:{_digest(refresh_token)}")
        if doc is None or doc["client_id"] != client.client_id or not self._owner_valid(doc):
            return None
        return RefreshToken(token=refresh_token, client_id=doc["client_id"], scopes=doc["scopes"],
                            expires_at=doc["expires_at"], subject=doc["subject"])

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        digest = _digest(refresh_token.token)
        doc = self._c.get(f"refresh:{digest}") or {}
        self._drop_pair(doc.get("access"), digest)  # rotation: the old pair is gone
        return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.subject or "",
                           doc.get("fingerprint", ""), granted_at=doc.get("granted_at"))

    async def load_access_token(self, token: str) -> AccessToken | None:
        doc = self._live(f"access:{_digest(token)}")
        if doc is None or not self._owner_valid(doc) or self._c.get(f"client:{doc['client_id']}") is None:
            return None
        return AccessToken(token=token, client_id=doc["client_id"], scopes=doc["scopes"],
                           expires_at=doc["expires_at"], subject=doc["subject"])

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        digest = _digest(token.token)
        if isinstance(token, AccessToken):
            doc = self._c.get(f"access:{digest}") or {}
            self._drop_pair(digest, doc.get("refresh"))
        else:
            doc = self._c.get(f"refresh:{digest}") or {}
            self._drop_pair(doc.get("access"), digest)

    # --- settings page -----------------------------------------------------------------

    def grants(self) -> list[Grant]:
        """Clients holding a live refresh token, i.e. the accesses an admin may revoke."""
        found: dict[str, Grant] = {}
        for key, doc in self._c.items():
            if not key.startswith("refresh:") or doc["client_id"] in found:
                continue
            if doc["expires_at"] <= self._clock() or not self._owner_valid(doc):
                continue
            client = self._c.get(f"client:{doc['client_id']}")
            if client is None:
                continue
            found[doc["client_id"]] = Grant(
                client_id=doc["client_id"], client_name=client.get("client_name") or doc["client_id"],
                username=doc["subject"], granted_at=datetime.fromisoformat(doc["granted_at"]),
            )
        return list(found.values())

    def revoke_client(self, client_id: str) -> None:
        """Forget a client and everything it was given (codes, tokens, pending consents)."""
        self._c.delete(f"client:{client_id}")
        for key, doc in self._c.items():
            if key.split(":", 1)[0] in ("pending", "code", "access", "refresh") and doc.get("client_id") == client_id:
                self._c.delete(key)
