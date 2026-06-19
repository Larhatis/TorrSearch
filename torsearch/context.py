from __future__ import annotations

from torsearch.config import Config
from torsearch.indexers.registry import build_indexers
from torsearch.search.service import SearchService
from torsearch.settings.store import SettingsStore
from torsearch.transmission.client import TransmissionClient


class AppContext:
    def __init__(self, store: SettingsStore):
        self._store = store
        self._config = store.load()
        self._rebuild()

    @property
    def config(self) -> Config:
        return self._config

    @property
    def search_service(self) -> SearchService:
        return self._search_service

    @property
    def transmission(self) -> TransmissionClient:
        return self._transmission

    def _rebuild(self) -> None:
        indexers = build_indexers(self._config)
        self._search_service = SearchService(indexers, timeout=self._config.search.timeout_seconds)
        self._transmission = TransmissionClient(self._config.transmission)

    def update_settings(self, new_config: Config) -> None:
        self._store.save(new_config)
        self._config = new_config
        self._rebuild()
