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
    cfg = Config(indexers=[IndexerConfig(name="tracker1", url="https://tracker1.example/api", api_key="k")])
    client, _, _ = _client(tmp_path, cfg)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Transmission" in resp.text
    assert "tracker1" in resp.text
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
        "name": "tracker1", "url": "https://tracker1.example/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert "tracker1" in resp.text
    assert [ix.name for ix in ctx.config.indexers] == ["tracker1"]


def test_add_indexer_duplicate_shows_error(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="tracker1", url="https://tracker1.example/api", api_key="k")])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers", data={
        "name": "tracker1", "url": "https://other/api", "api_key": "k", "auth": "query",
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
        respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(200, content=b'<?xml version="1.0"?><caps/>')
        )
        resp = client.post("/settings/indexer-test", data={
            "name": "tracker1", "url": "https://tracker1.example/api", "api_key": "k", "auth": "query",
        })
    assert resp.status_code == 200
    assert "OK" in resp.text


def test_test_indexer_returns_error_toast_on_401(tmp_path):
    client, _, _ = _client(tmp_path)
    with respx.mock:
        respx.get("https://tracker1.example/api").mock(return_value=httpx.Response(401))
        resp = client.post("/settings/indexer-test", data={
            "name": "tracker1", "url": "https://tracker1.example/api", "api_key": "bad", "auth": "query",
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


from torsearch.config import JellyfinConfig, TransmissionConfig


def _secret_config():
    return Config(
        transmission=TransmissionConfig(password="tr-secret-pw"),
        indexers=[IndexerConfig(name="t", url="https://t/api", api_key="passkey-secret")],
        jellyfin=JellyfinConfig(url="http://jelly:8096", api_key="jf-secret-key"),
    )


def test_settings_page_never_renders_secrets(tmp_path):
    client, _, _ = _client(tmp_path, _secret_config())
    html = client.get("/settings").text
    for secret in ("tr-secret-pw", "passkey-secret", "jf-secret-key"):
        assert secret not in html
    assert "inchange si vide" in html
    assert 'autocomplete="new-password"' in html


def test_blank_secret_fields_keep_stored_values(tmp_path):
    # Same destination (host/URL unchanged): a blank secret field keeps the stored value.
    client, ctx, _ = _client(tmp_path, _secret_config())
    client.post("/settings/general", data={"host": "localhost", "port": "9091", "username": "u",
                                           "password": "", "timeout_seconds": "10"})
    client.post("/settings/indexers/t", data={"name": "t2", "url": "https://t/api",
                                              "api_key": "", "auth": "query"})
    client.post("/settings/jellyfin", data={"url": "http://jelly:8096", "api_key": ""})
    assert ctx.config.transmission.password == "tr-secret-pw"
    assert ctx.config.transmission.username == "u"
    assert ctx.config.indexers[0].api_key == "passkey-secret"
    assert ctx.config.indexers[0].name == "t2"  # a rename keeps the passkey (same URL)
    assert ctx.config.jellyfin.api_key == "jf-secret-key"


def test_new_secret_value_replaces_stored_one(tmp_path):
    client, ctx, _ = _client(tmp_path, _secret_config())
    client.post("/settings/general", data={"host": "h", "port": "9091", "password": "new-pw",
                                           "timeout_seconds": "10"})
    assert ctx.config.transmission.password == "new-pw"


def test_test_indexer_uses_stored_passkey_when_blank(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://tracker1.example/api", api_key="stored-key")])
    client, _, _ = _client(tmp_path, cfg)
    with respx.mock:
        route = respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(200, content=b'<?xml version="1.0"?><caps/>')
        )
        resp = client.post("/settings/indexer-test", data={
            "name": "t", "original_name": "t", "url": "https://tracker1.example/api",
            "api_key": "", "auth": "query",
        })
    assert "OK" in resp.text
    assert route.calls.last.request.url.params["apikey"] == "stored-key"


def test_settings_page_has_tmdb_field_without_leaking_key(tmp_path):
    from torsearch.config import MetadataConfig

    client, _, _ = _client(tmp_path, Config(metadata=MetadataConfig(tmdb_api_key="tmdb-secret")))
    html = client.get("/settings").text
    assert 'name="tmdb_api_key"' in html
    assert "tmdb-secret" not in html


def test_update_metadata_sets_and_keeps_tmdb_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/settings/metadata", data={"tmdb_api_key": "k1"})
    assert resp.status_code == 200
    assert ctx.config.metadata.tmdb_api_key == "k1"
    assert ctx.tmdb.enabled is True
    client.post("/settings/metadata", data={"tmdb_api_key": ""})
    assert ctx.config.metadata.tmdb_api_key == "k1"  # blank keeps the stored key


def test_tracker_named_test_can_be_updated(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="test", url="https://old/api", api_key="k")])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/settings/indexers/test", data={"name": "test", "url": "https://old/api",
                                                 "api_key": "k2", "auth": "query"})
    assert ctx.config.indexers[0].api_key == "k2"


def test_update_indexer_keeps_custom_categories(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://t/api", api_key="k",
                                         categories={"movies": [2040]})])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/settings/indexers/t", data={"name": "t", "url": "https://t/api", "api_key": "", "auth": "query"})
    assert ctx.config.indexers[0].categories == {"movies": [2040]}


def test_blank_secret_is_never_sent_to_a_new_destination(tmp_path):
    client, ctx, _ = _client(tmp_path, _secret_config())
    r1 = client.post("/settings/general", data={"host": "evil.example", "port": "9091",
                                                "password": "", "timeout_seconds": "10"})
    r2 = client.post("/settings/jellyfin", data={"url": "https://evil.example", "api_key": ""})
    r3 = client.post("/settings/indexers/t", data={"name": "t", "url": "https://evil.example/api",
                                                   "api_key": "", "auth": "query"})
    for resp in (r1, r2, r3):
        assert "Ressaisis" in resp.text
    assert ctx.config.transmission.host != "evil.example"
    assert ctx.config.jellyfin.url == "http://jelly:8096"
    assert ctx.config.indexers[0].url == "https://t/api"


def test_new_destination_with_new_secret_is_accepted(tmp_path):
    client, ctx, _ = _client(tmp_path, _secret_config())
    client.post("/settings/jellyfin", data={"url": "https://jelly2", "api_key": "new-key"})
    assert (ctx.config.jellyfin.url, ctx.config.jellyfin.api_key) == ("https://jelly2", "new-key")


def test_disabling_jellyfin_keeps_the_stored_key(tmp_path):
    client, ctx, _ = _client(tmp_path, _secret_config())
    client.post("/settings/jellyfin", data={"url": "", "api_key": ""})
    assert (ctx.config.jellyfin.url, ctx.config.jellyfin.api_key) == ("", "jf-secret-key")


def test_tester_never_sends_the_stored_passkey_to_another_url(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://tracker1.example/api", api_key="stored-key")])
    client, _, _ = _client(tmp_path, cfg)
    with respx.mock:
        evil = respx.get("https://evil.example/api").mock(return_value=httpx.Response(200, content=b"<caps/>"))
        resp = client.post("/settings/indexer-test", data={
            "name": "t", "original_name": "t", "url": "https://evil.example/api",
            "api_key": "", "auth": "query",
        })
    assert "Ressaisis" in resp.text
    assert not evil.called
