from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import MediaResult, WantedMovie
from torsearch.requests.store import RequestStatus, RequestStore
from torsearch.search.service import SearchService
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


class FakeTmdb:
    enabled = True

    async def trending(self):
        return [MediaResult(tmdb_id=603, media_type="movie", title="The Matrix",
                            year="1999", overview="", poster_path="/p.jpg")]

    async def search(self, q):
        return []


class FakeJellyfin:
    base_url = ""
    enabled = False

    async def owned(self):
        return {}


class FakeCtx:
    def __init__(self):
        self.search_service = SearchService([])
        self.transmission = None
        self.config = Config()
        self.tmdb = FakeTmdb()
        self.jellyfin = FakeJellyfin()


def _client(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.add("admin", "pw", Role.ADMIN)
    store.add("mem", "pw", Role.MEMBER)
    store.add("guest", "pw", Role.GUEST)
    requests_store = RequestStore(tmp_path / "requests.json")
    library = MovieLibrary(tmp_path / "lib.json")
    client = TestClient(create_app(
        FakeCtx(), auth=AuthSettings(enabled=True, secret_key="k"), users=store,
        library=library, series_library=SeriesLibrary(tmp_path / "s.json"),
        requests_store=requests_store,
    ))
    return client, requests_store, library


def _login(client, user):
    client.post("/login", data={"username": user, "password": "pw", "next": "/"},
                follow_redirects=False)


def test_guest_sees_request_button_not_add(tmp_path):
    client, _, _ = _client(tmp_path)
    _login(client, "guest")
    html = client.get("/discover/trending").text
    assert "Demander" in html
    assert "Bibliotheque" not in html


def test_member_sees_add_not_request(tmp_path):
    client, _, _ = _client(tmp_path)
    _login(client, "mem")
    html = client.get("/discover/trending").text
    assert "Bibliotheque" in html
    assert "Demander" not in html


def test_guest_can_create_request(tmp_path):
    client, store, _ = _client(tmp_path)
    _login(client, "guest")
    resp = client.post("/requests", data={
        "media_type": "movie", "tmdb_id": "603", "title": "The Matrix", "year": "1999"})
    assert resp.status_code == 200
    assert store.count_pending() == 1
    assert store.pending()[0].username == "guest"


def test_guest_cannot_view_or_decide(tmp_path):
    client, store, _ = _client(tmp_path)
    _login(client, "guest")
    store.add("guest", "movie", 603, "The Matrix", "1999", None)
    assert client.get("/requests").status_code == 403
    rid = store.pending()[0].id
    assert client.post(f"/requests/{rid}/approve").status_code == 403


def test_admin_approves_request_adds_to_library(tmp_path):
    client, store, library = _client(tmp_path)
    req = store.add("guest", "movie", 603, "The Matrix", "1999", "/p.jpg")
    _login(client, "admin")
    resp = client.post(f"/requests/{req.id}/approve")
    assert resp.status_code == 200
    assert store.get(req.id).status == RequestStatus.APPROVED
    assert [m.tmdb_id for m in library.list()] == [603]


def test_admin_rejects_request(tmp_path):
    client, store, library = _client(tmp_path)
    req = store.add("guest", "movie", 603, "The Matrix", "1999", None)
    _login(client, "admin")
    resp = client.post(f"/requests/{req.id}/reject")
    assert resp.status_code == 200
    assert store.get(req.id).status == RequestStatus.REJECTED
    assert library.list() == []


def test_admin_page_lists_pending(tmp_path):
    client, store, _ = _client(tmp_path)
    store.add("guest", "movie", 603, "The Matrix", "1999", None)
    _login(client, "admin")
    html = client.get("/requests").text
    assert "The Matrix" in html
    assert "Approuver" in html


def test_nav_shows_requests_badge_for_admin(tmp_path):
    client, store, _ = _client(tmp_path)
    store.add("guest", "movie", 603, "The Matrix", "1999", None)
    _login(client, "admin")
    html = client.get("/").text
    assert 'href="/requests"' in html
    assert "Demandes" in html


def test_nav_hides_requests_from_guest(tmp_path):
    client, _, _ = _client(tmp_path)
    _login(client, "guest")
    html = client.get("/discover").text
    assert 'href="/requests"' not in html


def test_guest_sees_own_requests_with_status(tmp_path):
    client, store, _ = _client(tmp_path)
    store.add("guest", "movie", 603, "The Matrix", "1999", None)
    store.add("other", "tv", 1399, "GoT", "2011", None)
    _login(client, "guest")
    html = client.get("/requests/mine").text
    assert "The Matrix" in html
    assert "En attente" in html
    assert "GoT" not in html  # not this user's request


def test_nav_shows_my_requests_for_guest_not_admin(tmp_path):
    client, _, _ = _client(tmp_path)
    _login(client, "guest")
    assert 'href="/requests/mine"' in client.get("/discover").text
    _login(client, "admin")
    assert 'href="/requests/mine"' not in client.get("/").text


def test_discover_shows_in_library_badge_and_hides_button(tmp_path):
    client, _, library = _client(tmp_path)
    library.add(WantedMovie(tmdb_id=603, title="The Matrix", year="1999",
                            added_at=datetime(2026, 1, 1, tzinfo=UTC)))
    _login(client, "guest")
    html = client.get("/discover/trending").text
    assert "Dans la bibliotheque" in html
    assert "Demander" not in html


def test_discover_shows_requested_badge_and_hides_button(tmp_path):
    client, store, _ = _client(tmp_path)
    store.add("guest", "movie", 603, "The Matrix", "1999", None)
    _login(client, "guest")
    html = client.get("/discover/trending").text
    assert "Demande" in html
    assert "Demander" not in html
