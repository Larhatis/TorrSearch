from __future__ import annotations

from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.db.database import Database
from torsearch.search.service import SearchService
from torsearch.transmission.client import TorrentInfo
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


def _t(id, name, size=1, error=""):
    return TorrentInfo(id=id, name=name, percent=100.0, status="seeding", down_rate=0, up_rate=0,
                       size=size, error_string=error)


class FakeTransmission:
    def __init__(self, torrents):
        self.torrents = torrents
        self.removed: list[tuple[int, bool]] = []
        self.paused: list[int] = []

    async def list_torrents(self):
        return list(self.torrents)

    async def remove(self, torrent_id, delete_data=False):
        self.removed.append((torrent_id, delete_data))
        self.torrents = [t for t in self.torrents if t.id != torrent_id]

    async def pause(self, torrent_id):
        self.paused.append(torrent_id)


class Ctx:
    def __init__(self, tx):
        self.search_service = SearchService([])
        self.transmission = tx
        self.config = Config()
        self.jellyfin = None
        self.tmdb = None


def _client(torrents, **kw):
    tx = FakeTransmission(torrents)
    return TestClient(create_app(Ctx(tx), **kw)), tx


DOG = [_t(453, "The.Dog.Stars.2026.MULTi.VFQ.1080p.WEBRip-GL0P.mkv", 2),
       _t(460, "The.Dog.Stars.2026.MULTi.2160p.WEBRip-BATGirl.mkv", 5)]


def test_page_lists_duplicates_with_proposed_removal():
    client, _ = _client(DOG + [_t(1, "A", error="invalid passkey")])
    html = client.get("/downloads/cleanup").text
    assert "The Dog Stars" in html
    assert 'name="remove" value="453" checked' in html
    assert 'value="460" checked' not in html  # the best copy is kept
    assert "invalid passkey" in html
    assert 'href="/downloads/cleanup"' in client.get("/downloads").text


def test_removing_duplicates_deletes_files_but_never_the_last_copy():
    client, tx = _client(list(DOG))
    resp = client.post("/downloads/cleanup/duplicates", data={"remove": ["453", "460"]})
    assert "garde au moins une copie" in resp.text
    assert tx.removed == []
    resp = client.post("/downloads/cleanup/duplicates", data={"remove": ["453", "999"]})
    assert tx.removed == [(453, True)]  # unknown ids are ignored
    assert "1 copie(s) supprimee(s)" in resp.text


def test_error_actions_keep_files_and_only_touch_errored_torrents():
    torrents = [_t(1, "A", error="invalid passkey"), _t(2, "B", error="invalid passkey"), _t(3, "C")]
    client, tx = _client(torrents)
    client.post("/downloads/cleanup/errors", data={"ids": ["1", "3"], "action": "stop"})
    assert tx.paused == [1]
    client.post("/downloads/cleanup/errors", data={"ids": ["1", "2"], "action": "remove"})
    assert tx.removed == [(1, False), (2, False)]


def test_cleanup_is_admin_only(tmp_path):
    store = UserStore(Database(tmp_path / "t.db").collection("users"))
    store.add("bob", "password1", Role.MEMBER)
    client, tx = _client(list(DOG), auth=AuthSettings(enabled=True, secret_key="k"), users=store)
    client.post("/login", data={"username": "bob", "password": "password1", "next": "/"})
    assert client.get("/downloads/cleanup").status_code == 403
    assert client.post("/downloads/cleanup/duplicates", data={"remove": ["453"]}).status_code == 403
    assert tx.removed == []
