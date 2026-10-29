from __future__ import annotations

import re

from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.db.database import Database
from torsearch.models import Category, SearchResult
from torsearch.search.result_cache import ResultCache
from torsearch.search.service import SearchService
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app

SECRET_URL = "https://tracker.example/download/123?passkey=SUPERSECRET"


class Indexer:
    name = "t1"
    enabled = True

    async def search(self, query, category):
        return [SearchResult(title="Dune.Part.Two.2024.MULTi.2160p.WEB-X", size=8_000_000_000, seeders=50,
                             leechers=1, source="t1", category=Category.MOVIES, download_url=SECRET_URL)]


class Transmission:
    def __init__(self):
        self.added: list[tuple[str, str | None]] = []

    async def add(self, url, download_dir=None):
        self.added.append((url, download_dir))
        return 9


class Ctx:
    def __init__(self, tx):
        self.search_service = SearchService([Indexer()])
        self.transmission = tx
        self.config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")])
        self.jellyfin = None
        self.tmdb = None


def _member_client(tmp_path):
    store = UserStore(Database(tmp_path / "u.db").collection("users"))
    store.add("bob", "password1", Role.MEMBER)
    store.add("root", "password1", Role.ADMIN)
    tx = Transmission()
    client = TestClient(create_app(Ctx(tx), auth=AuthSettings(enabled=True, secret_key="k"), users=store))
    return client, tx


def _login(client, user):
    client.post("/login", data={"username": user, "password": "password1", "next": "/"})


def test_result_cache_roundtrip_and_expiry():
    now = [1000.0]
    cache = ResultCache(ttl_seconds=60, clock=lambda: now[0])
    r = SearchResult(title="A", size=1, seeders=1, leechers=0, source="t", category=Category.MOVIES,
                     download_url=SECRET_URL)
    rid = cache.put(r)
    assert SECRET_URL not in rid and len(rid) >= 16
    assert cache.put(r) == rid  # same result, same id
    assert cache.get(rid) == r
    now[0] += 61
    assert cache.get(rid) is None
    assert cache.get("forged") is None


def test_member_never_sees_the_tracker_key_but_can_download(tmp_path):
    client, tx = _member_client(tmp_path)
    _login(client, "bob")
    html = client.get("/search", params={"q": "dune"}).text
    assert "SUPERSECRET" not in html and "passkey" not in html
    assert 'data-copy=' not in html  # copy-link button is admin-only
    rid = re.search(r'name="result_id" value="([^"]+)"', html).group(1)
    resp = client.post("/download", data={"result_id": rid})
    assert "Ajoute a Transmission" in resp.text
    assert tx.added[0][0] == SECRET_URL


def test_member_cannot_post_a_raw_url_or_a_forged_id(tmp_path):
    client, tx = _member_client(tmp_path)
    _login(client, "bob")
    assert "expire" in client.post("/download", data={"result_id": "forged"}).text
    resp = client.post("/download", data={"download_url": "http://evil.example/x.torrent"})
    assert resp.status_code == 403
    assert tx.added == []


def test_admin_keeps_copy_link_and_raw_url(tmp_path):
    client, tx = _member_client(tmp_path)
    _login(client, "root")
    assert 'data-copy=' in client.get("/search", params={"q": "dune"}).text
    client.post("/download", data={"download_url": "magnet:?xt=urn:btih:AA", "title": "X"})
    assert tx.added[0][0] == "magnet:?xt=urn:btih:AA"
