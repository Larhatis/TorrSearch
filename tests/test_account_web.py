from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.db.database import Database
from torsearch.search.service import SearchService
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


class _Ctx:
    def __init__(self):
        self.search_service = SearchService([])
        self.transmission = None
        self.config = Config()


def _setup(tmp_path, auth=True):
    store = UserStore(Database(tmp_path / "t.db").collection("users"))
    store.add("bob", "old-password", Role.MEMBER)
    settings = AuthSettings(enabled=auth, secret_key="k")
    client = TestClient(create_app(_Ctx(), auth=settings, users=store))
    if auth:
        resp = client.post("/login", data={"username": "bob", "password": "old-password", "next": "/"},
                           follow_redirects=False)
        assert resp.status_code == 303
    return client, store


def _change(client, current="old-password", new="new-password", confirm=None):
    return client.post("/account/password", data={
        "current_password": current, "new_password": new,
        "confirm_password": new if confirm is None else confirm,
    })


def test_account_page_renders_for_member(tmp_path):
    client, _ = _setup(tmp_path)
    resp = client.get("/account")
    assert resp.status_code == 200
    assert "bob" in resp.text
    assert 'name="current_password"' in resp.text


def test_password_change_keeps_session_and_updates_hash(tmp_path):
    client, store = _setup(tmp_path)
    resp = _change(client)
    assert "Mot de passe modifie" in resp.text
    assert store.verify("bob", "new-password") is not None
    assert store.verify("bob", "old-password") is None
    # Still logged in: the session fingerprint was refreshed.
    assert client.get("/account", follow_redirects=False).status_code == 200


def test_password_change_rejects_wrong_current(tmp_path):
    client, store = _setup(tmp_path)
    resp = _change(client, current="nope")
    assert "Mot de passe actuel incorrect" in resp.text
    assert store.verify("bob", "old-password") is not None


def test_password_change_rejects_short_or_mismatch(tmp_path):
    client, store = _setup(tmp_path)
    assert "8 caracteres" in _change(client, new="short").text
    assert "ne correspondent pas" in _change(client, confirm="different-one").text
    assert store.verify("bob", "old-password") is not None


def test_account_redirects_when_auth_disabled(tmp_path):
    client, _ = _setup(tmp_path, auth=False)
    resp = client.get("/account", follow_redirects=False)
    assert resp.status_code == 303
