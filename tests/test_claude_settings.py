"""Settings > Maintenance > Acces Claude: see the connector address, revoke an access (chantier 11)."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

from torsearch.claude.oauth import TorrSearchOAuthProvider
from torsearch.context import AppContext
from torsearch.db.database import Database
from torsearch.settings.store import SettingsStore
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app

PUBLIC = "https://torrsearch.example.com"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _setup(tmp_path, public_url=PUBLIC):
    db = Database(tmp_path / "db.sqlite")
    users = UserStore(db.collection("users"))
    users.add("admin", "pw-admin-1", Role.ADMIN)
    users.add("mem", "pw-mem-1", Role.MEMBER)
    provider = TorrSearchOAuthProvider(db.collection("oauth"), users, "k", public_url) if public_url else None
    app = create_app(AppContext(SettingsStore(db.collection("settings"))), users=users, db=db,
                     auth=AuthSettings(enabled=True, secret_key="k"), public_url=public_url, claude_provider=provider)
    return TestClient(app), provider


def _login(client, username="admin", password="pw-admin-1"):
    client.post("/login", data={"username": username, "password": password, "next": "/"}, follow_redirects=False)


async def _grant(provider):
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await provider.register_client(client)
    url = await provider.authorize(client, AuthorizationParams(
        state=None, scopes=["torrsearch"], code_challenge="ch", redirect_uri=CALLBACK,
        redirect_uri_provided_explicitly=True))
    redirect = provider.approve(parse_qs(urlparse(url).query)["demande"][0], "admin")
    code = await provider.load_authorization_code(client, parse_qs(urlparse(redirect).query)["code"][0])
    return await provider.exchange_authorization_code(client, code)


def test_disabled_section_without_public_url(tmp_path):
    client, _ = _setup(tmp_path, public_url=None)
    _login(client)
    page = client.get("/settings").text
    assert "Definis TORSEARCH_PUBLIC_URL" in page


async def test_connector_url_and_grants_listed(tmp_path):
    client, provider = _setup(tmp_path)
    await _grant(provider)
    _login(client)
    page = client.get("/settings").text
    assert f"{PUBLIC}/mcp" in page
    assert "Claude" in page and "admin" in page


async def test_no_grant_says_so(tmp_path):
    client, _ = _setup(tmp_path)
    _login(client)
    assert "Aucun acces accorde." in client.get("/settings").text


async def test_revoke_removes_grant_and_token(tmp_path):
    client, provider = _setup(tmp_path)
    tokens = await _grant(provider)
    _login(client)
    resp = client.post("/settings/claude/revoke", data={"client_id": "c1"})
    assert resp.status_code == 200 and "Aucun acces accorde." in resp.text
    assert await provider.load_access_token(tokens.access_token) is None


async def test_member_cannot_revoke(tmp_path):
    client, provider = _setup(tmp_path)
    tokens = await _grant(provider)
    _login(client, "mem", "pw-mem-1")
    assert client.post("/settings/claude/revoke", data={"client_id": "c1"}).status_code == 403
    assert await provider.load_access_token(tokens.access_token) is not None
