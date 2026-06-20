from torsearch.config import Config, IndexerConfig, SearchConfig
from torsearch.context import AppContext
from torsearch.settings.store import SettingsStore


def test_builds_services_from_loaded_config(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Config(indexers=[IndexerConfig(name="a", url="https://a/api", api_key="k")]))
    ctx = AppContext(store)
    assert [ix.name for ix in ctx.search_service.indexers] == ["a"]
    assert ctx.transmission is not None
    assert ctx.config.indexers[0].name == "a"


def test_update_settings_persists_and_rebuilds(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ctx = AppContext(store)
    assert ctx.search_service.indexers == []
    new = Config(
        search=SearchConfig(timeout_seconds=3),
        indexers=[IndexerConfig(name="b", url="https://b/api", api_key="k")],
    )
    ctx.update_settings(new)
    assert [ix.name for ix in ctx.search_service.indexers] == ["b"]
    assert [ix.name for ix in store.load().indexers] == ["b"]  # persisted


def test_disabled_indexers_excluded_from_search_but_kept_in_config(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ctx = AppContext(store)
    ctx.update_settings(Config(indexers=[
        IndexerConfig(name="on", url="https://on/api", api_key="k", enabled=True),
        IndexerConfig(name="off", url="https://off/api", api_key="k", enabled=False),
    ]))
    assert [ix.name for ix in ctx.search_service.indexers] == ["on"]
    assert [ix.name for ix in ctx.config.indexers] == ["on", "off"]


def test_context_exposes_tmdb_disabled_by_default(tmp_path):
    from torsearch.context import AppContext
    from torsearch.metadata.tmdb import TmdbClient
    from torsearch.settings.store import SettingsStore

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    assert isinstance(ctx.tmdb, TmdbClient)
    assert ctx.tmdb.enabled is False
