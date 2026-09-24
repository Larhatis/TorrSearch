import re

from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app
from torsearch.web.templating import TEMPLATES_DIR

_INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


class _Indexer:
    name = "t1"
    enabled = True

    def __init__(self, results):
        self._results = results

    async def search(self, query, category):
        return list(self._results)


class _Ctx:
    def __init__(self, results):
        self.search_service = SearchService([_Indexer(results)])
        self.transmission = None
        self.config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")])


def _result(download_url="magnet:?x"):
    return SearchResult(title="Film.1080p", size=1, seeders=5, leechers=0, source="t1",
                        category=Category.MOVIES, download_url=download_url)


def test_templates_have_no_inline_event_handlers():
    offenders = [
        f"{path.relative_to(TEMPLATES_DIR)}: {m.group(0).strip()}"
        for path in sorted(TEMPLATES_DIR.rglob("*.html"))
        for m in _INLINE_HANDLER.finditer(path.read_text())
    ]
    assert offenders == []


def test_download_url_lands_escaped_in_data_attribute():
    evil = "magnet:?xt=urn:btih:X');alert(document.domain)//"
    html = TestClient(create_app(_Ctx([_result(evil)]))).get("/search", params={"q": "film"}).text
    assert "onclick" not in html
    assert 'data-copy="magnet:?xt=urn:btih:X&#39;);alert(document.domain)//"' in html


def test_filter_chip_value_is_data_not_code():
    html = TestClient(create_app(_Ctx([_result()]))).get(
        "/search", params={"q": "film", "quality": ["1080p", "');alert(1)//"]}
    ).text
    assert "onclick" not in html
    assert 'data-value="&#39;);alert(1)//"' in html


def test_app_js_served_without_session():
    client = TestClient(create_app(_Ctx([]), auth=AuthSettings(enabled=True, secret_key="k")))
    resp = client.get("/static/app.js", follow_redirects=False)
    assert resp.status_code == 200
    assert "function clearFilter" in resp.text


def test_base_layout_loads_app_js():
    html = TestClient(create_app(_Ctx([]))).get("/").text
    assert '<script src="/static/app.js" defer></script>' in html
