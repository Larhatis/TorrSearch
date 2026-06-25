from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, SavedSearch
from torsearch.context import AppContext
from torsearch.monitor.history import MonitorHistory, MonitorRecord
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app


def _client(tmp_path, config=None, history=None):
    store = SettingsStore(tmp_path / "settings.json")
    if config is not None:
        store.save(config)
    ctx = AppContext(store)
    history = history if history is not None else MonitorHistory(tmp_path / "monitor.json")
    return TestClient(create_app(ctx, history=history)), ctx, history


def test_surveillance_page_renders(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/surveillance")
    assert resp.status_code == 200
    assert "Surveillance" in resp.text
    assert 'name="interval_minutes"' in resp.text


def test_add_saved_search(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/searches", data={"name": "MaSerie", "query": "ma serie", "cat": "tv", "mode": "notify"})
    assert resp.status_code == 200
    assert "MaSerie" in resp.text
    assert [s.name for s in ctx.config.saved_searches] == ["MaSerie"]
    assert ctx.config.saved_searches[0].mode == "notify"


def test_add_duplicate_shows_error(tmp_path):
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q")])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/surveillance/searches", data={"name": "s", "query": "q2"})
    assert "existe" in resp.text
    assert len(ctx.config.saved_searches) == 1


def test_toggle_and_delete_saved_search(tmp_path):
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q", enabled=True)])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/surveillance/searches/s/toggle")
    assert ctx.config.saved_searches[0].enabled is False
    client.post("/surveillance/searches/s/delete")
    assert ctx.config.saved_searches == []


def test_update_monitor_settings(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/monitor", data={"enabled": "on", "interval_minutes": "15"})
    assert resp.status_code == 200
    assert ctx.config.monitor.enabled is True
    assert ctx.config.monitor.interval_minutes == 15


def test_history_found_item_has_send_button(tmp_path):
    history = MonitorHistory(tmp_path / "monitor.json")
    history.add(MonitorRecord(search="s", title="Found.It", source="trk", infohash="H",
                              download_url="magnet:?xt=urn:btih:H", kind="found",
                              at=datetime(2024, 1, 1, tzinfo=UTC)))
    client, _, _ = _client(tmp_path, history=history)
    resp = client.get("/surveillance")
    assert "Found.It" in resp.text
    assert "Envoyer" in resp.text
