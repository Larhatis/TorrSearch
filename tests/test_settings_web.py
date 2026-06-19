from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.context import AppContext
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app


def _client(tmp_path, config=None):
    store = SettingsStore(tmp_path / "settings.json")
    if config is not None:
        store.save(config)
    ctx = AppContext(store)
    return TestClient(create_app(ctx)), ctx


def test_settings_page_renders_general_and_trackers(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="torr9", url="https://torr9/api", api_key="k")])
    client, _ = _client(tmp_path, cfg)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Transmission" in resp.text
    assert "torr9" in resp.text
    assert 'name="timeout_seconds"' in resp.text


def test_general_update_persists_and_reloads(tmp_path):
    client, ctx = _client(tmp_path)
    resp = client.post("/settings/general", data={
        "host": "tr.local", "port": "9092", "username": "u", "password": "p",
        "https": "on", "timeout_seconds": "7",
    })
    assert resp.status_code == 200
    assert ctx.config.transmission.host == "tr.local"
    assert ctx.config.transmission.port == 9092
    assert ctx.config.transmission.https is True
    assert ctx.config.search.timeout_seconds == 7


def test_general_update_rejects_bad_port(tmp_path):
    client, ctx = _client(tmp_path)
    resp = client.post("/settings/general", data={
        "host": "h", "port": "abc", "timeout_seconds": "7",
    })
    assert resp.status_code == 200
    assert "Erreur" in resp.text
    assert ctx.config.transmission.host != "h"  # not saved
