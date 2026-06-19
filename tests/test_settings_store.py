from torsearch.config import Config, IndexerConfig
from torsearch.settings.store import SettingsStore


def test_load_returns_empty_config_when_no_files(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    cfg = store.load()
    assert isinstance(cfg, Config)
    assert cfg.indexers == []


def test_load_bootstraps_from_config_yaml_and_resolves_env(tmp_path, monkeypatch):
    monkeypatch.setenv("K", "secret")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("indexers:\n  - name: t\n    url: https://x/api\n    api_key: ${K}\n")
    settings_path = tmp_path / "data" / "settings.json"
    store = SettingsStore(settings_path, bootstrap_config_path=yaml_path)
    cfg = store.load()
    assert cfg.indexers[0].api_key == "secret"
    assert settings_path.exists()
    assert "secret" in settings_path.read_text()
    assert "${K}" not in settings_path.read_text()


def test_existing_settings_take_precedence_over_bootstrap(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        Config(indexers=[IndexerConfig(name="from_settings", url="https://s/api", api_key="k")]).model_dump_json()
    )
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("indexers:\n  - name: from_yaml\n    url: https://y/api\n    api_key: k\n")
    store = SettingsStore(settings_path, bootstrap_config_path=yaml_path)
    assert [ix.name for ix in store.load().indexers] == ["from_settings"]


def test_save_round_trips(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    store.save(Config(indexers=[IndexerConfig(name="a", url="https://a/api", api_key="key")]))
    loaded = store.load()
    assert loaded.indexers[0].name == "a"
    assert loaded.indexers[0].api_key == "key"


def test_save_is_atomic_no_tmp_left(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    store.save(Config())
    assert settings_path.exists()
    assert not settings_path.with_name(settings_path.name + ".tmp").exists()
