from __future__ import annotations

import logging
import sqlite3

from fastapi.testclient import TestClient

from torsearch import main
from torsearch.context import AppContext
from torsearch.db.database import Database
from torsearch.logbuffer import MemoryLogHandler
from torsearch.settings.store import SettingsStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


def _client(tmp_path, **kw):
    ctx = AppContext(SettingsStore(tmp_path / "settings.json"))
    return TestClient(create_app(ctx, **kw))


def test_backup_downloads_a_consistent_sqlite_copy(tmp_path):
    db = Database(tmp_path / "torsearch.db")
    db.collection("movies").upsert("1", {"title": "Dune"})
    resp = _client(tmp_path, db=db).get("/settings/backup")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    copy = tmp_path / "copy.db"
    copy.write_bytes(resp.content)
    rows = sqlite3.connect(copy).execute("SELECT data FROM documents").fetchall()
    assert rows == [('{"title": "Dune"}',)]


def test_backup_unavailable_without_db(tmp_path):
    assert _client(tmp_path).get("/settings/backup").status_code == 404


def test_memory_log_handler_masks_secrets_and_filters_levels():
    handler = MemoryLogHandler(capacity=2)
    log = logging.getLogger("torsearch.test_logbuffer")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("first")
        log.info("GET https://t/api?apikey=SECRET failed")
        log.warning("careful")
    finally:
        log.removeHandler(handler)
    messages = [e.message for e in handler.entries()]
    assert messages == ["careful", "GET https://t/api?apikey=*** failed"]  # newest first, capacity 2
    assert [e.message for e in handler.entries(logging.WARNING)] == ["careful"]


def test_journal_page_lists_entries(tmp_path):
    handler = MemoryLogHandler()
    handler.emit(logging.LogRecord("torsearch.monitor", logging.WARNING, __file__, 1,
                                   "Tracker x en pause", None, None))
    resp = _client(tmp_path, log_handler=handler).get("/settings/journal?level=warning")
    assert resp.status_code == 200
    assert "Tracker x en pause" in resp.text


def test_healthz_is_public_even_with_auth(tmp_path):
    client = _client(tmp_path, auth=AuthSettings(enabled=True, username="a", password="b", secret_key="k"))
    resp = client.get("/healthz", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert client.get("/settings", follow_redirects=False).status_code == 303


def test_session_secret_stored_next_to_database(tmp_path, monkeypatch):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "a-strong-password")
    monkeypatch.delenv("TORSEARCH_SECRET_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    volume = tmp_path / "volume"
    main.build_app(
        settings_path=str(volume / "settings.json"),
        bootstrap_config_path=str(tmp_path / "missing.yaml"),
        monitor_path=str(volume / "monitor.json"),
        library_path=str(volume / "library.json"),
        series_path=str(volume / "series.json"),
        users_path=str(volume / "users.json"),
        requests_path=str(volume / "requests.json"),
        db_path=str(volume / "torsearch.db"),
    )
    assert (volume / ".session_secret").exists()
    assert not (tmp_path / "data" / ".session_secret").exists()
