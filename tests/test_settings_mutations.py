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


def test_add_saved_search_and_reject_duplicate():
    from torsearch.config import SavedSearch
    from torsearch.settings.mutations import add_saved_search
    cfg = Config()
    cfg2 = add_saved_search(cfg, SavedSearch(name="s", query="q"))
    assert [s.name for s in cfg2.saved_searches] == ["s"]
    assert cfg.saved_searches == []  # original untouched
    with pytest.raises(SettingsError):
        add_saved_search(cfg2, SavedSearch(name="s", query="q2"))


def test_remove_and_toggle_saved_search():
    from torsearch.config import SavedSearch
    from torsearch.settings.mutations import remove_saved_search, set_saved_search_enabled
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q", enabled=True)])
    assert set_saved_search_enabled(cfg, "s", False).saved_searches[0].enabled is False
    assert remove_saved_search(cfg, "s").saved_searches == []
    with pytest.raises(SettingsError):
        remove_saved_search(cfg, "nope")


def test_set_monitor():
    from torsearch.config import MonitorConfig
    from torsearch.settings.mutations import set_monitor
    out = set_monitor(Config(), MonitorConfig(enabled=True, interval_minutes=10))
    assert out.monitor.enabled is True
    assert out.monitor.interval_minutes == 10


def test_add_channel_and_reject_duplicate():
    from torsearch.config import NotificationChannel
    from torsearch.settings.mutations import add_channel
    cfg = Config()
    cfg2 = add_channel(cfg, NotificationChannel(name="d", type="discord", url="https://x"))
    assert [c.name for c in cfg2.notifications] == ["d"]
    assert cfg.notifications == []
    with pytest.raises(SettingsError):
        add_channel(cfg2, NotificationChannel(name="d", type="ntfy", url="https://y"))


def test_remove_and_toggle_channel():
    from torsearch.config import NotificationChannel
    from torsearch.settings.mutations import remove_channel, set_channel_enabled
    cfg = Config(notifications=[NotificationChannel(name="d", type="discord", url="https://x", enabled=True)])
    assert set_channel_enabled(cfg, "d", False).notifications[0].enabled is False
    assert remove_channel(cfg, "d").notifications == []
    with pytest.raises(SettingsError):
        remove_channel(cfg, "nope")
