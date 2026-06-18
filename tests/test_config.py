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
