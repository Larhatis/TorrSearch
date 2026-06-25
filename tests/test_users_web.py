from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.monitor.history import MonitorHistory
from torsearch.search.service import SearchService
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


class FakeIndexer:
    name = "t1"
    enabled = True

    async def search(self, q, c):
        return []


class FakeTmdb:
    enabled = True

    async def trending(self):
        return []

    async def search(self, q):
        return []


class FakeJellyfin:
    base_url = ""
    enabled = False

    async def owned(self):
        return {}


class FakeCtx:
    def __init__(self):
        self.search_service = SearchService([FakeIndexer()])
        self.transmission = None
        self.config = Config()
        self.tmdb = FakeTmdb()
        self.jellyfin = FakeJellyfin()


def _client(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.add("admin", "pw", Role.ADMIN)
    store.add("guest", "pw", Role.GUEST)
    client = TestClient(create_app(
        FakeCtx(), auth=AuthSettings(enabled=True, secret_key="k"), users=store,
        history=MonitorHistory(tmp_path / "m.json"),
        library=MovieLibrary(tmp_path / "l.json"),
        series_library=SeriesLibrary(tmp_path / "s.json"),
    ))
    return client, store


def _login(client, user):
    client.post("/login", data={"username": user, "password": "pw", "next": "/"},
                follow_redirects=False)


def test_admin_sees_users_card(tmp_path):
    client, _ = _client(tmp_path)
    _login(client, "admin")
    html = client.get("/settings").text
    assert "Utilisateurs" in html
    assert 'hx-post="/settings/users"' in html


def test_admin_can_add_user(tmp_path):
    client, store = _client(tmp_path)
    _login(client, "admin")
    resp = client.post("/settings/users",
                       data={"username": "newbie", "password": "pw", "role": "member"})
    assert resp.status_code == 200
    assert "newbie" in resp.text
    assert store.get("newbie").role == Role.MEMBER


def test_admin_can_change_role_and_delete(tmp_path):
    client, store = _client(tmp_path)
    _login(client, "admin")
    client.post("/settings/users/guest/role", data={"role": "member"})
    assert store.get("guest").role == Role.MEMBER
    client.post("/settings/users/guest/delete")
    assert store.get("guest") is None


def test_cannot_delete_last_admin_returns_error(tmp_path):
    client, store = _client(tmp_path)
    _login(client, "admin")
    resp = client.post("/settings/users/admin/delete")
    assert resp.status_code == 200
    assert "dernier administrateur" in resp.text.lower()
    assert store.get("admin") is not None


def test_nav_hides_admin_links_from_guest(tmp_path):
    client, _ = _client(tmp_path)
    _login(client, "guest")
    html = client.get("/discover").text
    assert 'href="/settings"' not in html
    assert 'href="/surveillance"' not in html


def test_nav_shows_admin_links_for_admin(tmp_path):
    client, _ = _client(tmp_path)
    _login(client, "admin")
    html = client.get("/").text
    assert 'href="/settings"' in html
    assert 'href="/surveillance"' in html
