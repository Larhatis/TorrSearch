from __future__ import annotations

from torsearch.config import Config, IndexerConfig, SearchConfig, TransmissionConfig


class SettingsError(Exception):
    """Raised when a settings mutation is invalid (e.g. duplicate tracker name)."""


def _index_of(config: Config, name: str) -> int:
    for i, ix in enumerate(config.indexers):
        if ix.name == name:
            return i
    return -1


def add_indexer(config: Config, indexer: IndexerConfig) -> Config:
    if _index_of(config, indexer.name) != -1:
        raise SettingsError(f"Un tracker nommé « {indexer.name} » existe déjà.")
    return config.model_copy(update={"indexers": [*config.indexers, indexer]})


def update_indexer(config: Config, name: str, indexer: IndexerConfig) -> Config:
    idx = _index_of(config, name)
    if idx == -1:
        raise SettingsError(f"Tracker introuvable : « {name} ».")
    if indexer.name != name and _index_of(config, indexer.name) != -1:
        raise SettingsError(f"Un tracker nommé « {indexer.name} » existe déjà.")
    new_indexers = list(config.indexers)
    new_indexers[idx] = indexer
    return config.model_copy(update={"indexers": new_indexers})


def remove_indexer(config: Config, name: str) -> Config:
    if _index_of(config, name) == -1:
        raise SettingsError(f"Tracker introuvable : « {name} ».")
    new_indexers = [ix for ix in config.indexers if ix.name != name]
    return config.model_copy(update={"indexers": new_indexers})


def set_indexer_enabled(config: Config, name: str, enabled: bool) -> Config:
    idx = _index_of(config, name)
    if idx == -1:
        raise SettingsError(f"Tracker introuvable : « {name} ».")
    new_indexers = list(config.indexers)
    new_indexers[idx] = new_indexers[idx].model_copy(update={"enabled": enabled})
    return config.model_copy(update={"indexers": new_indexers})


def set_general(config: Config, transmission: TransmissionConfig, search: SearchConfig) -> Config:
    return config.model_copy(update={"transmission": transmission, "search": search})
