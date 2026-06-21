from __future__ import annotations

import os

from fastapi import FastAPI

from torsearch.context import AppContext
from torsearch.library.movies import MovieLibrary
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import MonitorRunner
from torsearch.settings.store import SettingsStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app

DEFAULT_SETTINGS_PATH = os.environ.get("TORSEARCH_SETTINGS", "data/settings.json")
DEFAULT_CONFIG_PATH = os.environ.get("TORSEARCH_CONFIG", "config.yaml")
DEFAULT_MONITOR_PATH = os.environ.get("TORSEARCH_MONITOR", "data/monitor.json")
DEFAULT_LIBRARY_PATH = os.environ.get("TORSEARCH_LIBRARY", "data/library.json")


def build_app(
    settings_path: str = DEFAULT_SETTINGS_PATH,
    bootstrap_config_path: str = DEFAULT_CONFIG_PATH,
    monitor_path: str = DEFAULT_MONITOR_PATH,
    library_path: str = DEFAULT_LIBRARY_PATH,
) -> FastAPI:
    store = SettingsStore(settings_path, bootstrap_config_path=bootstrap_config_path)
    ctx = AppContext(store)
    history = MonitorHistory(monitor_path)
    library = MovieLibrary(library_path)
    monitor = MonitorRunner(ctx, history, library=library)
    return create_app(ctx, history=history, monitor=monitor, auth=AuthSettings.from_env(), library=library)


def get_app() -> FastAPI:
    return build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
