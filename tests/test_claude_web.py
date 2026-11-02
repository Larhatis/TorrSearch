"""Claude's connector over HTTP: OAuth with an admin login, only MCP paths public (chantier 11)."""
from __future__ import annotations

import base64
import hashlib
import secrets
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from torsearch.claude.oauth import TorrSearchOAuthProvider
from torsearch.config import Config
from torsearch.db.database import Database
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.monitor.grabs import GrabRegistry
from torsearch.monitor.history import MonitorHistory
from torsearch.search.service import SearchService
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app

PUBLIC = "https://torrsearch.example.com"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


class Ctx:
    def __init__(self):
        self.config = Config()
        self.search_service = SearchService([])
        self.tmdb = SimpleNamespace(enabled=False)
        self.jellyfin = SimpleNamespace(enabled=False)
        self.transmission = SimpleNamespace()

    def update_settings(self, config):
        self.config = config


def _app(tmp_path, auth_enabled=True, public_url=PUBLIC):
    db = Database(tmp_path / "db.sqlite")
    users = UserStore(db.collection("users"))
    users.add("admin", "pw-admin-1", Role.ADMIN)
    users.add("mem", "pw-mem-1", Role.MEMBER)
    auth = AuthSettings(enabled=True, secret_key="k") if auth_enabled else AuthSettings(enabled=False)
    provider = TorrSearchOAuthProvider(db.collection("oauth"), users, "k", public_url) if public_url and auth_enabled else None
    app = create_app(Ctx(), auth=auth, users=users, history=MonitorHistory(db), library=MovieLibrary(db),
                     series_library=SeriesLibrary(db), grabs=GrabRegistry(db), db=db,
                     public_url=public_url, claude_provider=provider)
    return app


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _start_consent(c):
    """Register Claude and open the consent page: returns (client_id, request_id, verifier)."""
    reg = c.post("/register", json={"redirect_uris": [CALLBACK], "client_name": "Claude",
                                     "token_endpoint_auth_method": "none",
                                     "grant_types": ["authorization_code", "refresh_token"],
                                     "response_types": ["code"]})
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]
    verifier, challenge = _pkce()
    resp = c.get("/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK, "state": "xyz",
        "code_challenge": challenge, "code_challenge_method": "S256", "scope": "torrsearch",
    }, follow_redirects=False)
    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert location.startswith(f"{PUBLIC}/claude/autoriser?demande=")
    return client_id, parse_qs(urlparse(location).query)["demande"][0], verifier


def _consent(c, request_id, username="admin", password="pw-admin-1", decision="autoriser"):
    return c.post("/claude/autoriser", data={"demande": request_id, "username": username, "password": password,
                                             "decision": decision}, follow_redirects=False)


def test_oauth_flow_end_to_end(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        client_id, request_id, verifier = _start_consent(c)
        page = c.get("/claude/autoriser", params={"demande": request_id})
        assert page.status_code == 200 and "Claude" in page.text
        resp = _consent(c, request_id)
        assert resp.status_code == 303
        query = parse_qs(urlparse(resp.headers["location"]).query)
        assert resp.headers["location"].startswith(CALLBACK) and query["state"] == ["xyz"]
        token = c.post("/token", data={"grant_type": "authorization_code", "code": query["code"][0],
                                       "redirect_uri": CALLBACK, "client_id": client_id,
                                       "code_verifier": verifier})
        assert token.status_code == 200, token.text
        bearer = {"authorization": f"Bearer {token.json()['access_token']}", **MCP_HEADERS}
        init = c.post("/mcp", headers=bearer, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1"}}})
        assert init.status_code == 200, init.text
        version = init.json()["result"]["protocolVersion"]
        tools = c.post("/mcp", headers={**bearer, "mcp-protocol-version": version},
                       json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert tools.status_code == 200, tools.text
        assert len(tools.json()["result"]["tools"]) == 8


def test_member_cannot_authorize(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        _, request_id, _ = _start_consent(c)
        resp = _consent(c, request_id, username="mem", password="pw-mem-1")
        assert resp.status_code == 403 and "administrateur" in resp.text
        assert "location" not in resp.headers


def test_wrong_password_is_throttled(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        _, request_id, _ = _start_consent(c)
        for _ in range(5):
            assert _consent(c, request_id, password="wrong").status_code == 401
        blocked = _consent(c, request_id)
        assert blocked.status_code == 429 and "location" not in blocked.headers


def test_deny_redirects_with_access_denied(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        _, request_id, _ = _start_consent(c)
        resp = _consent(c, request_id, decision="refuser")
        assert resp.status_code == 303
        assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["access_denied"]


def test_expired_request_is_explained(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        assert c.get("/claude/autoriser", params={"demande": "nope"}).status_code == 400


def test_mcp_without_token_is_401(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        resp = c.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert resp.status_code == 401
        assert "resource_metadata" in resp.headers["www-authenticate"]


def test_ui_stays_private_on_the_public_host(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        resp = c.get("/settings", follow_redirects=False)
        assert resp.status_code in (302, 303, 307) and "/login" in resp.headers["location"]


def test_auth_disabled_answers_503(tmp_path):
    with TestClient(_app(tmp_path, auth_enabled=False), base_url=PUBLIC) as c:
        resp = c.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert resp.status_code == 503 and "TORSEARCH_USERNAME" in resp.text
        assert c.get("/.well-known/oauth-authorization-server").status_code == 404


def test_no_public_url_mounts_nothing(tmp_path):
    with TestClient(_app(tmp_path, public_url=None), base_url=PUBLIC) as c:
        assert c.get("/.well-known/oauth-authorization-server").status_code == 404
        assert c.post("/mcp", headers=MCP_HEADERS, json={}).status_code == 404


def test_consent_page_shows_where_it_returns(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        _, request_id, _ = _start_consent(c)
        page = c.get("/claude/autoriser", params={"demande": request_id}).text
        assert "claude.ai" in page


def test_foreign_redirect_cannot_register(tmp_path):
    with TestClient(_app(tmp_path), base_url=PUBLIC) as c:
        reg = c.post("/register", json={"redirect_uris": ["https://evil.example/cb"], "client_name": "Claude",
                                         "token_endpoint_auth_method": "none"})
        assert reg.status_code == 400
