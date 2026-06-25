from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.context import AppContext
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app


def _client(tmp_path, config=None, history=None):
    store = SettingsStore(tmp_path / "settings.json")
    if config is not None:
        store.save(config)
    ctx = AppContext(store)
    return TestClient(create_app(ctx)), ctx, history


def test_settings_page_renders_general_and_trackers(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="torr9", url="https://torr9/api", api_key="k")])
    client, _, _ = _client(tmp_path, cfg)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Transmission" in resp.text
    assert "torr9" in resp.text
    assert 'name="timeout_seconds"' in resp.text


def test_library_update_sets_upgrades_toggle(tmp_path):
    client, ctx, _ = _client(tmp_path)
    client.post("/settings/library", data={"quality": ["1080p"], "min_seeders": "2", "upgrades": "on"})
    assert ctx.config.library.upgrades is True
    client.post("/settings/library", data={"quality": ["1080p"], "min_seeders": "2"})  # checkbox absent
    assert ctx.config.library.upgrades is False


def test_general_update_persists_and_reloads(tmp_path):
    client, ctx, _ = _client(tmp_path)
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
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/settings/general", data={
        "host": "h", "port": "abc", "timeout_seconds": "7",
    })
    assert resp.status_code == 200
    assert "Erreur" in resp.text
    assert ctx.config.transmission.host != "h"  # not saved


import httpx
import respx


def test_add_indexer_appears_in_list_and_config(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/settings/indexers", data={
        "name": "torr9", "url": "https://torr9/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert "torr9" in resp.text
    assert [ix.name for ix in ctx.config.indexers] == ["torr9"]


def test_add_indexer_duplicate_shows_error(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="torr9", url="https://torr9/api", api_key="k")])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers", data={
        "name": "torr9", "url": "https://other/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert "existe" in resp.text  # error banner
    assert len(ctx.config.indexers) == 1


def test_update_indexer_changes_url_preserves_enabled(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://old/api", api_key="k", enabled=False)])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers/t", data={
        "name": "t", "url": "https://new/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert ctx.config.indexers[0].url == "https://new/api"
    assert ctx.config.indexers[0].enabled is False  # preserved (not in form)


def test_toggle_indexer_flips_enabled(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://t/api", api_key="k", enabled=True)])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/settings/indexers/t/toggle")
    assert ctx.config.indexers[0].enabled is False


def test_delete_indexer_removes_it(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://t/api", api_key="k")])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers/t/delete")
    assert resp.status_code == 200
    assert ctx.config.indexers == []


def test_test_indexer_returns_ok_toast(tmp_path):
    client, _, _ = _client(tmp_path)
    with respx.mock:
        respx.get("https://torr9/api").mock(
            return_value=httpx.Response(200, content=b'<?xml version="1.0"?><caps/>')
        )
        resp = client.post("/settings/indexers/test", data={
            "name": "torr9", "url": "https://torr9/api", "api_key": "k", "auth": "query",
        })
    assert resp.status_code == 200
    assert "OK" in resp.text


def test_test_indexer_returns_error_toast_on_401(tmp_path):
    client, _, _ = _client(tmp_path)
    with respx.mock:
        respx.get("https://torr9/api").mock(return_value=httpx.Response(401))
        resp = client.post("/settings/indexers/test", data={
            "name": "torr9", "url": "https://torr9/api", "api_key": "bad", "auth": "query",
        })
    assert resp.status_code == 200
    assert "refus" in resp.text.lower()


from torsearch.config import NotificationChannel


def test_settings_page_shows_notifications_section(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Notifications" in resp.text


def test_add_notification_channel(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/settings/notifications", data={"name": "myd", "type": "discord", "url": "https://discord/wh"})
    assert resp.status_code == 200
    assert "myd" in resp.text
    assert [c.name for c in ctx.config.notifications] == ["myd"]


def test_toggle_and_delete_notification(tmp_path):
    cfg = Config(notifications=[NotificationChannel(name="c", type="webhook", url="https://x", enabled=True)])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/settings/notifications/c/toggle")
    assert ctx.config.notifications[0].enabled is False
    client.post("/settings/notifications/c/delete")
    assert ctx.config.notifications == []


def test_test_notification_channel(tmp_path):
    cfg = Config(notifications=[NotificationChannel(name="d", type="discord", url="https://discord/wh")])
    client, _, _ = _client(tmp_path, cfg)
    with respx.mock:
        respx.post("https://discord/wh").mock(return_value=httpx.Response(204))
        resp = client.post("/settings/notifications/d/test")
    assert resp.status_code == 200
    assert "OK" in resp.text


def test_update_jellyfin_settings(tmp_path):
    from fastapi.testclient import TestClient

    from torsearch.context import AppContext
    from torsearch.settings.store import SettingsStore
    from torsearch.web.routes import create_app

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    client = TestClient(create_app(ctx))
    resp = client.post("/settings/jellyfin", data={"url": "http://jelly:8096", "api_key": "K"})
    assert resp.status_code == 200
    assert ctx.config.jellyfin.url == "http://jelly:8096"
    assert ctx.config.jellyfin.api_key == "K"


def test_update_paths(tmp_path):
    from fastapi.testclient import TestClient

    from torsearch.context import AppContext
    from torsearch.models import Category
    from torsearch.settings.store import SettingsStore
    from torsearch.web.routes import create_app

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    client = TestClient(create_app(ctx))
    resp = client.post("/settings/paths", data={"path_movies": "/data/films", "path_tv": "/data/series", "path_anime": ""})
    assert resp.status_code == 200
    assert ctx.config.paths.for_category(Category.MOVIES) == "/data/films"
    assert ctx.config.paths.for_category(Category.TV) == "/data/series"
    assert ctx.config.paths.for_category(Category.ANIME) is None
