from __future__ import annotations

import os

from fastapi import FastAPI

from torsearch.config import load_config
from torsearch.indexers.registry import build_indexers
from torsearch.search.service import SearchService
from torsearch.transmission.client import TransmissionClient
from torsearch.web.routes import create_app

DEFAULT_CONFIG_PATH = os.environ.get("TORSEARCH_CONFIG", "config.yaml")


def build_app(config_path: str = DEFAULT_CONFIG_PATH) -> FastAPI:
    config = load_config(config_path)
    indexers = build_indexers(config)
    service = SearchService(indexers, timeout=config.search.timeout_seconds)
    transmission = TransmissionClient(config.transmission)
    return create_app(service, transmission)


def get_app() -> FastAPI:
    return build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
