from __future__ import annotations

from torsearch.config import Config, IndexerConfig, LibraryConfig, MonitorConfig, NotificationChannel, SavedSearch, SearchConfig, TransmissionConfig


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


def _saved_index(config: Config, name: str) -> int:
    for i, ss in enumerate(config.saved_searches):
        if ss.name == name:
            return i
    return -1


def add_saved_search(config: Config, saved_search: SavedSearch) -> Config:
    if _saved_index(config, saved_search.name) != -1:
        raise SettingsError(f"Une recherche nommée « {saved_search.name} » existe déjà.")
    return config.model_copy(update={"saved_searches": [*config.saved_searches, saved_search]})


def remove_saved_search(config: Config, name: str) -> Config:
    if _saved_index(config, name) == -1:
        raise SettingsError(f"Recherche introuvable : « {name} ».")
    return config.model_copy(
        update={"saved_searches": [s for s in config.saved_searches if s.name != name]}
    )


def set_saved_search_enabled(config: Config, name: str, enabled: bool) -> Config:
    idx = _saved_index(config, name)
    if idx == -1:
        raise SettingsError(f"Recherche introuvable : « {name} ».")
    new = list(config.saved_searches)
    new[idx] = new[idx].model_copy(update={"enabled": enabled})
    return config.model_copy(update={"saved_searches": new})


def set_monitor(config: Config, monitor: MonitorConfig) -> Config:
    return config.model_copy(update={"monitor": monitor})


def set_library(config: Config, library: LibraryConfig) -> Config:
    return config.model_copy(update={"library": library})


def _channel_index(config: Config, name: str) -> int:
    for i, ch in enumerate(config.notifications):
        if ch.name == name:
            return i
    return -1


def add_channel(config: Config, channel: NotificationChannel) -> Config:
    if _channel_index(config, channel.name) != -1:
        raise SettingsError(f"Un canal nommé « {channel.name} » existe déjà.")
    return config.model_copy(update={"notifications": [*config.notifications, channel]})


def remove_channel(config: Config, name: str) -> Config:
    if _channel_index(config, name) == -1:
        raise SettingsError(f"Canal introuvable : « {name} ».")
    return config.model_copy(
        update={"notifications": [c for c in config.notifications if c.name != name]}
    )


def set_channel_enabled(config: Config, name: str, enabled: bool) -> Config:
    idx = _channel_index(config, name)
    if idx == -1:
        raise SettingsError(f"Canal introuvable : « {name} ».")
    new = list(config.notifications)
    new[idx] = new[idx].model_copy(update={"enabled": enabled})
    return config.model_copy(update={"notifications": new})
