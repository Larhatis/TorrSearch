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


class FakeTransmission:
    def add(self, url, download_dir=None):
        return 1


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
        self.transmission = FakeTransmission()
        self.config = Config()
        self.tmdb = FakeTmdb()
        self.jellyfin = FakeJellyfin()


def _client(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.add("admin", "pw", Role.ADMIN)
    store.add("mem", "pw", Role.MEMBER)
    store.add("guest", "pw", Role.GUEST)
    auth = AuthSettings(enabled=True, secret_key="k")
    history = MonitorHistory(tmp_path / "m.json")
    return TestClient(create_app(
        FakeCtx(), auth=auth, users=store, history=history,
        library=MovieLibrary(tmp_path / "lib.json"),
        series_library=SeriesLibrary(tmp_path / "series.json"),
    ))


def _login(client, user):
    client.post("/login", data={"username": user, "password": "pw", "next": "/"},
                follow_redirects=False)


def test_login_sets_role_in_session(tmp_path):
    client = _client(tmp_path)
    _login(client, "mem")
    # member reaches a member route -> proves role was stored and honored
    assert client.get("/search", params={"q": "x"}).status_code == 200


def test_guest_blocked_from_admin_and_member_routes(tmp_path):
    client = _client(tmp_path)
    _login(client, "guest")
    assert client.get("/settings").status_code == 403
    assert client.get("/search", params={"q": "x"}).status_code == 403
    assert client.post("/download", data={"download_url": "magnet:?x"}).status_code == 403
    assert client.get("/surveillance").status_code == 403
    assert client.post("/library/add", data={"tmdb_id": "1", "title": "X"}).status_code == 403


def test_guest_allowed_on_open_routes(tmp_path):
    client = _client(tmp_path)
    _login(client, "guest")
    assert client.get("/").status_code == 200
    assert client.get("/discover").status_code == 200
    assert client.get("/library").status_code == 200


def test_member_blocked_from_admin_routes_only(tmp_path):
    client = _client(tmp_path)
    _login(client, "mem")
    assert client.get("/settings").status_code == 403
    assert client.get("/surveillance").status_code == 403
    # but member can use the member capabilities
    assert client.get("/search", params={"q": "x"}).status_code == 200
    assert client.get("/downloads").status_code == 200


def test_admin_allowed_everywhere(tmp_path):
    client = _client(tmp_path)
    _login(client, "admin")
    assert client.get("/settings").status_code == 200
    assert client.get("/surveillance").status_code == 200
    assert client.get("/search", params={"q": "x"}).status_code == 200


def test_guest_redirected_to_discover_after_login(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/login", data={"username": "guest", "password": "pw", "next": "/"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/discover"


def test_member_lands_on_home_after_login(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/login", data={"username": "mem", "password": "pw", "next": "/"},
                       follow_redirects=False)
    assert resp.headers["location"] == "/"
