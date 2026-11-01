"""Settings > Maintenance: see the blacklist and lift an entry (chantier 10)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from torsearch.context import AppContext
from torsearch.db.database import Database
from torsearch.library.blacklist import Blacklist
from torsearch.settings.store import SettingsStore
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


def _client(tmp_path, bl, **kw):
    ctx = AppContext(SettingsStore(tmp_path / "settings.json"))
    return TestClient(create_app(ctx, blacklist=bl, **kw))


def test_maintenance_lists_blacklisted_releases(tmp_path):
    bl = Blacklist(tmp_path / "bl.db")
    bl.add("aa", "Some.Release.1080p", reason="torrent_stalled")
    page = _client(tmp_path, bl).get("/settings").text
    assert "Some.Release.1080p" in page
    assert "Bloque" in page


def test_empty_blacklist_says_so(tmp_path):
    page = _client(tmp_path, Blacklist(tmp_path / "bl.db")).get("/settings").text
    assert "Aucune release en liste noire." in page


def test_blacklist_remove_by_hash(tmp_path):
    bl = Blacklist(tmp_path / "bl.db")
    bl.add("aa", "Some.Release.1080p", reason="torrent_stalled")
    bl.add("bb", "Other.Release.720p", reason="torrent_error")
    resp = _client(tmp_path, bl).post("/settings/blacklist/remove", data={"key": "aa"})
    assert resp.status_code == 200
    assert "Some.Release.1080p" not in resp.text
    assert "Other.Release.720p" in resp.text and "Erreur tracker" in resp.text
    assert bl.is_blacklisted("aa", "Some.Release.1080p") is False


def test_blacklist_remove_title_with_slash_and_quote(tmp_path):
    bl = Blacklist(tmp_path / "bl.db")
    bl.add(None, "AC/DC l'integrale été", reason="failed_download")
    _client(tmp_path, bl).post("/settings/blacklist/remove", data={"key": "AC/DC l'integrale été"})
    assert bl.list() == []


def test_blacklist_remove_requires_admin(tmp_path):
    users = UserStore(Database(tmp_path / "u.db").collection("users"))
    users.add("admin", "pw", Role.ADMIN)
    users.add("mem", "pw", Role.MEMBER)
    bl = Blacklist(tmp_path / "bl.db")
    bl.add("aa", "Some.Release.1080p")
    client = _client(tmp_path, bl, auth=AuthSettings(enabled=True, secret_key="k"), users=users)
    client.post("/login", data={"username": "mem", "password": "pw", "next": "/"}, follow_redirects=False)
    assert client.post("/settings/blacklist/remove", data={"key": "aa"}).status_code == 403
    assert bl.is_blacklisted("aa", "Some.Release.1080p")
