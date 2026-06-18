from fastapi import FastAPI

from torsearch import main


def test_build_app_wires_services(tmp_path, monkeypatch):
    monkeypatch.setenv("TORR9_API_KEY", "secret")
    config = tmp_path / "config.yaml"
    config.write_text(
        """
transmission:
  host: localhost
indexers:
  - name: torr9
    type: torznab
    url: https://api.torr9.net/api/v1/torznab
    api_key: ${TORR9_API_KEY}
    enabled: true
"""
    )
    app = main.build_app(str(config))
    assert isinstance(app, FastAPI)
    assert [ix.name for ix in app.state.search_service.indexers] == ["torr9"]
    assert app.state.transmission is not None
