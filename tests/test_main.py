from fastapi import FastAPI

from torsearch import main


def test_build_app_wires_context_and_bootstraps(tmp_path, monkeypatch):
    monkeypatch.setenv("TORR9_API_KEY", "secret")
    config = tmp_path / "config.yaml"
    config.write_text(
        "indexers:\n"
        "  - name: torr9\n"
        "    type: torznab\n"
        "    url: https://api.torr9.net/api/v1/torznab\n"
        "    api_key: ${TORR9_API_KEY}\n"
        "    enabled: true\n"
    )
    settings = tmp_path / "data" / "settings.json"
    app = main.build_app(settings_path=str(settings), bootstrap_config_path=str(config))
    assert isinstance(app, FastAPI)
    assert [ix.name for ix in app.state.ctx.search_service.indexers] == ["torr9"]
    assert settings.exists()
