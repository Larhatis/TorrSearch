
from torsearch import main


def test_build_app_wires_context_history_and_bootstraps(tmp_path, monkeypatch):
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
    d = tmp_path / "data"
    app = main.build_app(
        settings_path=str(d / "settings.json"),
        bootstrap_config_path=str(config),
        monitor_path=str(d / "monitor.json"),
        library_path=str(d / "library.json"),
        series_path=str(d / "series.json"),
        users_path=str(d / "users.json"),
        requests_path=str(d / "requests.json"),
        db_path=str(d / "torsearch.db"),
    )
    assert [ix.name for ix in app.state.ctx.search_service.indexers] == ["torr9"]
    assert app.state.ctx.config.indexers[0].api_key == "secret"  # persisted into the DB
    assert app.state.history is not None
    assert app.state.history.records() == []
    assert app.state.library is not None
    assert app.state.series_library is not None
