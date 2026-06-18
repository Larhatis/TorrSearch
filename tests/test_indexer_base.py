import pytest

from torsearch.indexers.base import Indexer
from torsearch.models import Category, SearchResult


def test_cannot_instantiate_abstract_indexer():
    with pytest.raises(TypeError):
        Indexer()


async def test_concrete_subclass_can_search():
    class Dummy(Indexer):
        def __init__(self):
            self.name = "dummy"
            self.enabled = True

        async def search(self, query, category):
            return [
                SearchResult(
                    title=query,
                    size=1,
                    seeders=1,
                    leechers=0,
                    source=self.name,
                    category=category,
                    download_url="magnet:?xt=urn:btih:Z",
                )
            ]

    out = await Dummy().search("hello", Category.ALL)
    assert out[0].title == "hello"
    assert out[0].source == "dummy"
