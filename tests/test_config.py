import pytest
from pydantic import ValidationError

from torsearch.config import AuthMode, Config, load_config

VALID_YAML = """
transmission:
  host: tr.local
  port: 9092
search:
  timeout_seconds: 5
indexers:
  - name: torr9
    type: torznab
    url: https://api.torr9.net/api/v1/torznab
    api_key: ${TORR9_API_KEY}
    enabled: true
  - name: c411
    type: torznab
    url: https://c411.org/api
    api_key: plain-key
    auth: bearer
    enabled: false
"""

INVALID_YAML = """
indexers:
  - name: broken
    type: torznab
"""


def test_load_config_parses_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    cfg = load_config(path)
    assert isinstance(cfg, Config)
    assert cfg.transmission.host == "tr.local"
    assert cfg.transmission.port == 9092
    assert cfg.search.timeout_seconds == 5
    assert len(cfg.indexers) == 2
    assert cfg.indexers[1].auth == AuthMode.BEARER


def test_load_config_interpolates_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TORR9_API_KEY", "secret-123")
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    cfg = load_config(path)
    assert cfg.indexers[0].api_key == "secret-123"


def test_load_config_missing_env_becomes_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("TORR9_API_KEY", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    cfg = load_config(path)
    assert cfg.indexers[0].api_key == ""


def test_load_config_rejects_missing_url(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(INVALID_YAML)
    with pytest.raises(ValidationError):
        load_config(path)


def test_saved_search_defaults():
    from torsearch.config import SavedSearch
    ss = SavedSearch(name="x", query="q")
    assert ss.category.value == "all"
    assert ss.mode == "auto"
    assert ss.enabled is True
    assert ss.min_seeders == 0


def test_config_round_trips_saved_searches_and_monitor():
    from torsearch.config import Config, MonitorConfig, SavedSearch
    cfg = Config(
        saved_searches=[SavedSearch(name="s1", query="dune", mode="notify")],
        monitor=MonitorConfig(enabled=True, interval_minutes=15),
    )
    again = Config.model_validate_json(cfg.model_dump_json())
    assert again.saved_searches[0].name == "s1"
    assert again.saved_searches[0].mode == "notify"
    assert again.monitor.enabled is True
    assert again.monitor.interval_minutes == 15


def test_monitor_defaults_off():
    from torsearch.config import Config
    cfg = Config()
    assert cfg.monitor.enabled is False
    assert cfg.monitor.interval_minutes == 30
    assert cfg.saved_searches == []


def test_notification_channel_defaults():
    from torsearch.config import NotificationChannel
    ch = NotificationChannel(name="d", type="discord", url="https://x")
    assert ch.enabled is True
    assert ch.token == "" and ch.chat_id == ""


def test_config_round_trips_notifications():
    from torsearch.config import Config, NotificationChannel
    cfg = Config(notifications=[NotificationChannel(name="d", type="discord", url="https://x")])
    again = Config.model_validate_json(cfg.model_dump_json())
    assert again.notifications[0].name == "d"
    assert again.notifications[0].type == "discord"
    assert Config().notifications == []


def test_metadata_tmdb_key_interpolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "secret-key")
    p = tmp_path / "c.yaml"
    p.write_text("metadata:\n  tmdb_api_key: ${TMDB_API_KEY}\n")
    from torsearch.config import load_config

    cfg = load_config(p)
    assert cfg.metadata.tmdb_api_key == "secret-key"


def test_metadata_defaults_to_empty(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("{}\n")
    from torsearch.config import load_config

    assert load_config(p).metadata.tmdb_api_key == ""
