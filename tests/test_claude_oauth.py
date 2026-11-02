"""OAuth for Claude: only an admin grants access, tokens die with the account (chantier 11)."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

from torsearch.claude.oauth import TorrSearchOAuthProvider
from torsearch.db.database import Database
from torsearch.users.store import Role, UserStore

PUBLIC = "https://torrsearch.example.com"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _setup(tmp_path, now=None):
    db = Database(tmp_path / "db.sqlite")
    users = UserStore(db.collection("users"))
    users.add("admin", "pw-admin-1", Role.ADMIN)
    users.add("mem", "pw-mem-1", Role.MEMBER)
    clock = (lambda: now[0]) if now is not None else None
    kwargs = {"clock": clock} if clock else {}
    provider = TorrSearchOAuthProvider(db.collection("oauth"), users, "secret-key", PUBLIC, **kwargs)
    return db, users, provider


async def _grant(provider, username="admin"):
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await provider.register_client(client)
    params = AuthorizationParams(state="st", scopes=["torrsearch"], code_challenge="ch", redirect_uri=CALLBACK,
                                 redirect_uri_provided_explicitly=True)
    url = await provider.authorize(client, params)
    request_id = parse_qs(urlparse(url).query)["demande"][0]
    redirect = provider.approve(request_id, username)
    code_value = parse_qs(urlparse(redirect).query)["code"][0]
    code = await provider.load_authorization_code(client, code_value)
    tokens = await provider.exchange_authorization_code(client, code)
    return client, url, redirect, code_value, tokens


async def test_full_grant_flow(tmp_path):
    _, _, p = _setup(tmp_path)
    client, url, redirect, code_value, tokens = await _grant(p)
    assert url.startswith(f"{PUBLIC}/claude/autoriser?demande=")
    assert redirect.startswith(CALLBACK) and parse_qs(urlparse(redirect).query)["state"] == ["st"]
    assert tokens.refresh_token and tokens.expires_in == 3600
    access = await p.load_access_token(tokens.access_token)
    assert access.subject == "admin" and access.scopes == ["torrsearch"]
    assert await p.load_authorization_code(client, code_value) is None  # single use
    [grant] = p.grants()
    assert (grant.client_name, grant.username) == ("Claude", "admin")


async def test_pending_request_shows_the_client(tmp_path):
    _, _, p = _setup(tmp_path)
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await p.register_client(client)
    url = await p.authorize(client, AuthorizationParams(
        state=None, scopes=None, code_challenge="ch", redirect_uri=CALLBACK, redirect_uri_provided_explicitly=True))
    request_id = parse_qs(urlparse(url).query)["demande"][0]
    assert p.pending(request_id).client_name == "Claude"
    assert parse_qs(urlparse(p.deny(request_id)).query)["error"] == ["access_denied"]
    assert p.pending(request_id) is None  # used up


async def test_only_an_admin_can_approve(tmp_path):
    _, _, p = _setup(tmp_path)
    with pytest.raises(ValueError):
        await _grant(p, username="mem")


async def test_unknown_or_expired_pending_request(tmp_path):
    now = [1000.0]
    _, _, p = _setup(tmp_path, now)
    assert p.pending("nope") is None
    with pytest.raises(ValueError):
        p.approve("nope", "admin")
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await p.register_client(client)
    url = await p.authorize(client, AuthorizationParams(
        state=None, scopes=None, code_challenge="ch", redirect_uri=CALLBACK, redirect_uri_provided_explicitly=True))
    request_id = parse_qs(urlparse(url).query)["demande"][0]
    now[0] += 601
    assert p.pending(request_id) is None


async def test_refresh_rotates(tmp_path):
    _, _, p = _setup(tmp_path)
    client, *_, tokens = await _grant(p)
    old = await p.load_refresh_token(client, tokens.refresh_token)
    fresh = await p.exchange_refresh_token(client, old, ["torrsearch"])
    assert fresh.refresh_token != tokens.refresh_token
    assert await p.load_refresh_token(client, tokens.refresh_token) is None
    assert await p.load_access_token(tokens.access_token) is None  # the old access token goes too
    assert (await p.load_access_token(fresh.access_token)).subject == "admin"


async def test_token_dies_with_password_change(tmp_path):
    _, users, p = _setup(tmp_path)
    *_, tokens = await _grant(p)
    users.set_password("admin", "new-password-2")
    assert await p.load_access_token(tokens.access_token) is None


async def test_token_dies_with_demotion(tmp_path):
    _, users, p = _setup(tmp_path)
    users.add("boss", "pw-boss-1", Role.ADMIN)  # keep an admin around
    *_, tokens = await _grant(p)
    users.set_role("admin", Role.MEMBER)
    assert await p.load_access_token(tokens.access_token) is None


async def test_revoke_client_kills_its_tokens(tmp_path):
    _, _, p = _setup(tmp_path)
    client, *_, tokens = await _grant(p)
    p.revoke_client("c1")
    assert await p.load_access_token(tokens.access_token) is None
    assert await p.load_refresh_token(client, tokens.refresh_token) is None
    assert await p.get_client("c1") is None
    assert p.grants() == []


async def test_revoke_token_endpoint(tmp_path):
    _, _, p = _setup(tmp_path)
    client, *_, tokens = await _grant(p)
    await p.revoke_token(await p.load_access_token(tokens.access_token))
    assert await p.load_access_token(tokens.access_token) is None
    assert await p.load_refresh_token(client, tokens.refresh_token) is None


async def test_expired_code_and_token(tmp_path):
    now = [1000.0]
    _, _, p = _setup(tmp_path, now)
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await p.register_client(client)
    url = await p.authorize(client, AuthorizationParams(
        state=None, scopes=["torrsearch"], code_challenge="ch", redirect_uri=CALLBACK,
        redirect_uri_provided_explicitly=True))
    redirect = p.approve(parse_qs(urlparse(url).query)["demande"][0], "admin")
    code_value = parse_qs(urlparse(redirect).query)["code"][0]
    now[0] += 301
    assert await p.load_authorization_code(client, code_value) is None
    *_, tokens = await _grant(p)
    now[0] += 3601
    assert await p.load_access_token(tokens.access_token) is None


async def test_tokens_are_stored_hashed(tmp_path):
    db, _, p = _setup(tmp_path)
    *_, tokens = await _grant(p)
    stored = json.dumps(db.collection("oauth").all())
    assert tokens.access_token not in stored and tokens.refresh_token not in stored
