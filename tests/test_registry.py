from torsearch.config import Config, IndexerConfig
from torsearch.indexers.registry import build_indexers
from torsearch.indexers.torznab import TorznabIndexer


def test_builds_only_enabled_torznab_indexers():
    cfg = Config(
        indexers=[
            IndexerConfig(name="tracker1", url="https://a/api", api_key="x", enabled=True),
            IndexerConfig(name="tracker2", url="https://b/api", api_key="y", enabled=True),
            IndexerConfig(name="off", url="https://c/api", api_key="z", enabled=False),
        ]
    )
    indexers = build_indexers(cfg)
    assert len(indexers) == 2
    assert all(isinstance(ix, TorznabIndexer) for ix in indexers)
    assert {ix.name for ix in indexers} == {"tracker1", "tracker2"}


def test_skips_unknown_indexer_type():
    cfg = Config(
        indexers=[IndexerConfig(name="weird", type="newznab", url="https://a/api", api_key="x")]
    )
    assert build_indexers(cfg) == []
