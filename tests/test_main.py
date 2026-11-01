
from torsearch import main


def test_build_app_wires_context_history_and_bootstraps(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKER1_API_KEY", "secret")
    config = tmp_path / "config.yaml"
    config.write_text(
        "indexers:\n"
        "  - name: tracker1\n"
        "    type: torznab\n"
        "    url: https://tracker1.example/api\n"
        "    api_key: ${TRACKER1_API_KEY}\n"
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
    assert [ix.name for ix in app.state.ctx.search_service.indexers] == ["tracker1"]
    assert app.state.ctx.config.indexers[0].api_key == "secret"  # persisted into the DB
    assert app.state.history is not None
    assert app.state.history.records() == []
    assert app.state.library is not None
    assert app.state.series_library is not None


def test_build_app_seeds_the_grab_registry_from_history(tmp_path):
    from datetime import UTC, datetime

    from torsearch.db.database import Database
    from torsearch.monitor.history import MonitorHistory, MonitorRecord

    d = tmp_path / "data"
    db_path = d / "torsearch.db"
    MonitorHistory(Database(db_path).collection("monitor")).add(MonitorRecord(
        search="Fallout", title="Fallout.S02E01.MULTi.2160p", source="trk", infohash="ABC",
        download_url="magnet:?xt=urn:btih:abc", kind="grabbed", at=datetime(2026, 10, 30, tzinfo=UTC)))
    app = main.build_app(
        settings_path=str(d / "settings.json"), bootstrap_config_path=str(tmp_path / "none.yaml"),
        monitor_path=str(d / "monitor.json"), library_path=str(d / "library.json"),
        series_path=str(d / "series.json"), users_path=str(d / "users.json"),
        requests_path=str(d / "requests.json"), db_path=str(db_path),
    )
    assert app.state.grabs.is_auto("abc")
    assert app.state.monitor._grabs is app.state.grabs  # the surveillance records into the same registry
