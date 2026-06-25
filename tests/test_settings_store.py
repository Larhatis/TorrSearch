from torsearch.config import Config, IndexerConfig
from torsearch.db.database import Database
from torsearch.settings.store import SettingsStore


def _store(tmp_path, bootstrap=None, migrate_from=None):
    return SettingsStore(
        Database(tmp_path / "t.db").collection("settings"),
        bootstrap_config_path=bootstrap,
        migrate_from=migrate_from,
    )


def test_load_returns_empty_config_when_no_files(tmp_path):
    cfg = _store(tmp_path).load()
    assert isinstance(cfg, Config)
    assert cfg.indexers == []


def test_load_bootstraps_from_config_yaml_and_resolves_env(tmp_path, monkeypatch):
    monkeypatch.setenv("K", "secret")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("indexers:\n  - name: t\n    url: https://x/api\n    api_key: ${K}\n")
    assert _store(tmp_path, bootstrap=yaml_path).load().indexers[0].api_key == "secret"
    # persisted into the DB: a second load (no bootstrap) still returns it
    assert _store(tmp_path).load().indexers[0].api_key == "secret"


def test_existing_settings_take_precedence_over_bootstrap(tmp_path):
    _store(tmp_path).save(
        Config(indexers=[IndexerConfig(name="from_settings", url="https://s/api", api_key="k")])
    )
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("indexers:\n  - name: from_yaml\n    url: https://y/api\n    api_key: k\n")
    assert [ix.name for ix in _store(tmp_path, bootstrap=yaml_path).load().indexers] == ["from_settings"]


def test_save_round_trips(tmp_path):
    store = _store(tmp_path)
    store.save(Config(indexers=[IndexerConfig(name="a", url="https://a/api", api_key="key")]))
    loaded = store.load()
    assert loaded.indexers[0].name == "a"
    assert loaded.indexers[0].api_key == "key"


def test_migrates_legacy_settings_json(tmp_path):
    legacy = tmp_path / "settings.json"
    legacy.write_text(
        Config(indexers=[IndexerConfig(name="old", url="https://o/api", api_key="k")]).model_dump_json()
    )
    assert [ix.name for ix in _store(tmp_path, migrate_from=legacy).load().indexers] == ["old"]
