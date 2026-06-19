import pytest

from torsearch.config import Config, IndexerConfig, SearchConfig, TransmissionConfig
from torsearch.settings.mutations import (
    SettingsError,
    add_indexer,
    remove_indexer,
    set_general,
    set_indexer_enabled,
    update_indexer,
)


def _ix(name, **o):
    base = dict(name=name, url=f"https://{name}/api", api_key="k")
    base.update(o)
    return IndexerConfig(**base)


def test_add_indexer_appends_without_mutating_original():
    cfg = Config(indexers=[_ix("a")])
    new = add_indexer(cfg, _ix("b"))
    assert [i.name for i in new.indexers] == ["a", "b"]
    assert [i.name for i in cfg.indexers] == ["a"]  # original untouched


def test_add_indexer_rejects_duplicate_name():
    cfg = Config(indexers=[_ix("a")])
    with pytest.raises(SettingsError):
        add_indexer(cfg, _ix("a"))


def test_update_indexer_replaces_in_place():
    cfg = Config(indexers=[_ix("a"), _ix("b")])
    new = update_indexer(cfg, "a", _ix("a", url="https://new/api"))
    assert new.indexers[0].url == "https://new/api"
    assert [i.name for i in new.indexers] == ["a", "b"]


def test_update_indexer_missing_raises():
    with pytest.raises(SettingsError):
        update_indexer(Config(), "nope", _ix("nope"))


def test_update_indexer_rename_collision_raises():
    cfg = Config(indexers=[_ix("a"), _ix("b")])
    with pytest.raises(SettingsError):
        update_indexer(cfg, "a", _ix("b"))  # renaming a -> b collides


def test_remove_indexer():
    cfg = Config(indexers=[_ix("a"), _ix("b")])
    assert [i.name for i in remove_indexer(cfg, "a").indexers] == ["b"]


def test_remove_indexer_missing_raises():
    with pytest.raises(SettingsError):
        remove_indexer(Config(), "nope")


def test_set_indexer_enabled():
    cfg = Config(indexers=[_ix("a", enabled=True)])
    assert set_indexer_enabled(cfg, "a", False).indexers[0].enabled is False


def test_set_general_replaces_transmission_and_search():
    cfg = Config(indexers=[_ix("a")])
    new = set_general(cfg, TransmissionConfig(host="h", port=1), SearchConfig(timeout_seconds=2))
    assert new.transmission.host == "h"
    assert new.search.timeout_seconds == 2
    assert [i.name for i in new.indexers] == ["a"]  # indexers preserved
