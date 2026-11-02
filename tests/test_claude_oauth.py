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


# --- Final review fixes: a public endpoint must bound what strangers can store ---

from mcp.server.auth.provider import AuthorizeError, RegistrationError  # noqa: E402


async def test_registration_only_accepts_claude_callbacks(tmp_path):
    _, _, p = _setup(tmp_path)
    evil = OAuthClientInformationFull(client_id="e1", client_name="Claude", redirect_uris=["https://evil.example/cb"])
    with pytest.raises(RegistrationError) as err:
        await p.register_client(evil)
    assert err.value.error == "invalid_redirect_uri"
    assert await p.get_client("e1") is None
    ok = OAuthClientInformationFull(client_id="c2", client_name="Claude",
                                    redirect_uris=["https://claude.com/api/mcp/auth_callback"])
    await p.register_client(ok)
    assert await p.get_client("c2") is not None


async def test_registration_rejects_oversized_metadata(tmp_path):
    _, _, p = _setup(tmp_path)
    with pytest.raises(RegistrationError):
        await p.register_client(OAuthClientInformationFull(client_id="x", client_name="C" * 101, redirect_uris=[CALLBACK]))
    with pytest.raises(RegistrationError):
        await p.register_client(OAuthClientInformationFull(client_id="y", client_name="Claude", redirect_uris=[CALLBACK],
                                                           contacts=["a" * 5000]))


async def test_clients_without_access_are_capped(tmp_path):
    _, _, p = _setup(tmp_path)
    client, *_ = await _grant(p)  # c1 holds an access: never dropped
    for n in range(25):
        await p.register_client(OAuthClientInformationFull(client_id=f"spam{n}", client_name="Claude",
                                                           redirect_uris=[CALLBACK], client_id_issued_at=n + 1))
    remaining = [n for n in range(25) if await p.get_client(f"spam{n}") is not None]
    assert remaining == list(range(5, 25))  # the 20 newest
    assert await p.get_client("c1") is not None


async def test_pending_requests_are_capped_and_state_bounded(tmp_path):
    db, _, p = _setup(tmp_path)
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await p.register_client(client)

    def params(state):
        return AuthorizationParams(state=state, scopes=None, code_challenge="ch", redirect_uri=CALLBACK,
                                   redirect_uri_provided_explicitly=True)

    for _ in range(25):
        await p.authorize(client, params("s"))
    assert sum(1 for key, _ in db.collection("oauth").items() if key.startswith("pending:")) == 20
    with pytest.raises(AuthorizeError):
        await p.authorize(client, params("s" * 1025))


async def test_expired_entries_are_purged_on_write(tmp_path):
    now = [1000.0]
    db, _, p = _setup(tmp_path, now)
    client = OAuthClientInformationFull(client_id="c1", client_name="Claude", redirect_uris=[CALLBACK])
    await p.register_client(client)
    await p.authorize(client, AuthorizationParams(state=None, scopes=None, code_challenge="ch", redirect_uri=CALLBACK,
                                                  redirect_uri_provided_explicitly=True))
    now[0] += 601
    await p.register_client(OAuthClientInformationFull(client_id="c2", client_name="Claude", redirect_uris=[CALLBACK]))
    assert not any(key.startswith("pending:") for key, _ in db.collection("oauth").items())
