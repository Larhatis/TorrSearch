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


def _setup(tmp_path):
    store = UserStore(Database(tmp_path / "t.db").collection("users"))
    store.add("admin", "pw", Role.ADMIN)
    store.add("bob", "pw", Role.MEMBER)
    app = create_app(_Ctx(), auth=AuthSettings(enabled=True, secret_key="k"), users=store)
    return TestClient(app), store


def _login(client, username):
    resp = client.post("/login", data={"username": username, "password": "pw", "next": "/"},
                       follow_redirects=False)
    assert resp.status_code == 303


def test_deleted_user_session_is_revoked(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    assert client.get("/search", params={"q": ""}).status_code == 200
    store.remove("bob")
    resp = client.get("/search", params={"q": ""}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")
    # the stale session was cleared: still logged out on the next request
    assert client.get("/", follow_redirects=False).status_code == 303


def test_deleted_user_htmx_request_gets_hx_redirect(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    store.remove("bob")
    resp = client.get("/search", params={"q": "x"}, headers={"HX-Request": "true"},
                      follow_redirects=False)
    assert resp.status_code == 401
    assert resp.headers["HX-Redirect"] == "/login"


def test_demoted_user_loses_rights_immediately(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    store.set_role("bob", Role.GUEST)
    assert client.get("/search", params={"q": ""}).status_code == 403


def test_promoted_user_gains_rights_without_relogin(tmp_path):
    client, store = _setup(tmp_path)
    store.set_role("bob", Role.GUEST)
    _login(client, "bob")
    assert client.get("/search", params={"q": ""}).status_code == 403
    store.set_role("bob", Role.MEMBER)
    assert client.get("/search", params={"q": ""}).status_code == 200


def test_nav_reflects_role_from_store(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "admin")
    assert "ti-settings" in client.get("/").text  # admin-only nav entry
    store.add("admin2", "pw", Role.ADMIN)  # keep an admin: the last one can't be demoted
    store.set_role("admin", Role.MEMBER)
    assert "ti-settings" not in client.get("/").text


def test_revocation_clears_the_session_cookie(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    store.remove("bob")
    resp = client.get("/search", params={"q": ""}, follow_redirects=False)
    assert "session=null" in resp.headers.get("set-cookie", "")


def test_recreated_account_does_not_revive_an_old_session(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    store.remove("bob")
    store.add("bob", "new-pw", Role.MEMBER)  # the only way to reset a password today
    assert client.get("/search", params={"q": ""}, follow_redirects=False).status_code == 303


def test_empty_store_only_trusts_the_configured_admin(tmp_path):
    db = Database(tmp_path / "t.db")
    store = UserStore(db.collection("users"))
    store.add("admin", "pw", Role.ADMIN)
    store.add("bob", "pw", Role.MEMBER)
    auth = AuthSettings(enabled=True, username="admin", password="pw", secret_key="k")
    client = TestClient(create_app(_Ctx(), auth=auth, users=store))
    _login(client, "bob")
    for name in ("admin", "bob"):
        db.collection("users").delete(name)  # store emptied behind the app's back
    assert client.get("/", follow_redirects=False).status_code == 303


def test_public_path_check_ignores_the_host_header():
    from starlette.requests import Request

    from torsearch.web.auth import _route_path

    scope = {"type": "http", "method": "GET", "path": "/discover", "root_path": "",
             "query_string": b"", "headers": [(b"host", b"evil/static")]}
    assert _route_path(Request(scope)) == "/discover"
