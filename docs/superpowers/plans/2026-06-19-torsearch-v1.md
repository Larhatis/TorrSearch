# TorSearch v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire une app web perso qui cherche un film/série sur plusieurs trackers Torznab en parallèle et envoie le résultat choisi à Transmission.

**Architecture:** FastAPI sert l'UI (Jinja2 + HTMX) et l'API. Une interface `Indexer` commune, implémentée par un `TorznabIndexer` générique, est interrogée en parallèle par un `SearchService` résilient (un tracker en échec n'arrête pas la recherche). Un `TransmissionClient` envoie le torrent choisi. Configuration via `config.yaml` (clés API en variables d'env).

**Tech Stack:** Python 3.12 · FastAPI · httpx · pydantic v2 · defusedxml · Jinja2 + HTMX + Tailwind · transmission-rpc · pytest + pytest-asyncio + respx · Docker.

**Convention de packaging :** le package Python s'appelle `torsearch` et vit directement à la racine du dépôt (`TorSearch/torsearch/...`). Les imports sont de la forme `from torsearch.models import SearchResult`. Cela affine la légère redondance `torsearch/app/` de la spec.

**Pré-requis de session :** depuis `/Users/clementcappeau/Github/TorSearch`, activer le venv avant toute commande : `source .venv/bin/activate` (créé en Task 1). Toutes les commandes `pytest` se lancent depuis la racine du dépôt.

---

## File Structure

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` | Métadonnées + dépendances + config pytest. |
| `torsearch/__init__.py` | Marqueur de package. |
| `torsearch/models.py` | `Category` (enum), `SearchResult` (pydantic). |
| `torsearch/config.py` | Modèles de config + `load_config()` avec interpolation `${VAR}`. |
| `torsearch/indexers/base.py` | ABC `Indexer`. |
| `torsearch/indexers/torznab.py` | `parse_response()`, mapping catégories, `TorznabIndexer`. |
| `torsearch/indexers/registry.py` | `build_indexers(config)`. |
| `torsearch/search/service.py` | `SearchService` (fan-out, dédoublonnage, tri). |
| `torsearch/transmission/client.py` | `TransmissionClient` (wrapper transmission-rpc). |
| `torsearch/web/routes.py` | `create_app()` + routes FastAPI. |
| `torsearch/web/templates/*` | base, index, trackers, partials. |
| `torsearch/main.py` | Câblage config → services → app. |
| `tests/*` | Tests unitaires + intégration (fixtures + mocks). |
| `config.example.yaml`, `.env.example`, `Dockerfile`, `docker-compose.yml`, `README.md` | Packaging & doc. |

---

## Task 1: Scaffolding du projet

**Files:**
- Create: `pyproject.toml`
- Create: `torsearch/__init__.py`
- Create: `torsearch/indexers/__init__.py`, `torsearch/search/__init__.py`, `torsearch/transmission/__init__.py`, `torsearch/web/__init__.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_importable():
    import torsearch

    assert torsearch is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch'` (package pas encore installé).

- [ ] **Step 3: Create pyproject + package skeleton**

`pyproject.toml`:
```toml
[project]
name = "torsearch"
version = "0.1.0"
description = "Recherche multi-trackers (Torznab) avec envoi a Transmission"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "pydantic>=2.7",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "transmission-rpc>=7.0",
    "pyyaml>=6.0",
    "defusedxml>=0.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["torsearch*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

Create empty files: `torsearch/__init__.py`, `torsearch/indexers/__init__.py`, `torsearch/search/__init__.py`, `torsearch/transmission/__init__.py`, `torsearch/web/__init__.py`.

- [ ] **Step 4: Create venv and install**

Run:
```bash
cd /Users/clementcappeau/Github/TorSearch
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: install OK (fastapi, httpx, transmission-rpc, pytest… installés).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml torsearch/ tests/test_smoke.py
git commit -m "chore: scaffold torsearch package and tooling"
```

---

## Task 2: Modèle de données (`models.py`)

**Files:**
- Create: `torsearch/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from torsearch.models import Category, SearchResult


def _result(**overrides):
    base = dict(
        title="Some.Title",
        size=1024,
        seeders=10,
        leechers=2,
        source="t1",
        category=Category.MOVIES,
        download_url="magnet:?xt=urn:btih:ABC",
    )
    base.update(overrides)
    return SearchResult(**base)


def test_is_magnet_true_for_magnet_url():
    assert _result(download_url="magnet:?xt=urn:btih:ABC").is_magnet is True


def test_is_magnet_false_for_http_url():
    assert _result(download_url="https://t/file.torrent").is_magnet is False


def test_optional_fields_default_to_none():
    r = _result()
    assert r.info_url is None
    assert r.publish_date is None
    assert r.infohash is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.models'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/models.py`:
```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, computed_field


class Category(str, Enum):
    ALL = "all"
    MOVIES = "movies"
    TV = "tv"
    ANIME = "anime"
    OTHER = "other"


class SearchResult(BaseModel):
    title: str
    size: int
    seeders: int
    leechers: int
    source: str
    category: Category
    download_url: str
    info_url: str | None = None
    publish_date: datetime | None = None
    infohash: str | None = None

    @computed_field
    @property
    def is_magnet(self) -> bool:
        return self.download_url.startswith("magnet:")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/models.py tests/test_models.py
git commit -m "feat: add SearchResult and Category models"
```

---

## Task 3: Configuration (`config.py`)

**Files:**
- Create: `torsearch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import pytest
from pydantic import ValidationError

from torsearch.config import AuthMode, Config, load_config

VALID_YAML = """
transmission:
  host: tr.local
  port: 9092
search:
  timeout_seconds: 5
indexers:
  - name: torr9
    type: torznab
    url: https://api.torr9.net/api/v1/torznab
    api_key: ${TORR9_API_KEY}
    enabled: true
  - name: c411
    type: torznab
    url: https://c411.org/api
    api_key: plain-key
    auth: bearer
    enabled: false
"""

INVALID_YAML = """
indexers:
  - name: broken
    type: torznab
"""


def test_load_config_parses_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    cfg = load_config(path)
    assert isinstance(cfg, Config)
    assert cfg.transmission.host == "tr.local"
    assert cfg.transmission.port == 9092
    assert cfg.search.timeout_seconds == 5
    assert len(cfg.indexers) == 2
    assert cfg.indexers[1].auth == AuthMode.BEARER


def test_load_config_interpolates_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TORR9_API_KEY", "secret-123")
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    cfg = load_config(path)
    assert cfg.indexers[0].api_key == "secret-123"


def test_load_config_missing_env_becomes_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("TORR9_API_KEY", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    cfg = load_config(path)
    assert cfg.indexers[0].api_key == ""


def test_load_config_rejects_missing_url(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(INVALID_YAML)
    with pytest.raises(ValidationError):
        load_config(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.config'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/config.py`:
```python
from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AuthMode(str, Enum):
    QUERY = "query"
    BEARER = "bearer"


class IndexerConfig(BaseModel):
    name: str
    type: str = "torznab"
    url: str
    api_key: str = ""
    auth: AuthMode = AuthMode.QUERY
    enabled: bool = True
    categories: dict[str, list[int]] = Field(default_factory=dict)


class TransmissionConfig(BaseModel):
    host: str = "localhost"
    port: int = 9091
    username: str = ""
    password: str = ""
    https: bool = False


class SearchConfig(BaseModel):
    timeout_seconds: float = 10.0


class Config(BaseModel):
    transmission: TransmissionConfig = Field(default_factory=TransmissionConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    indexers: list[IndexerConfig] = Field(default_factory=list)


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _interpolate(value):
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    return value


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    raw = _interpolate(raw)
    return Config(**raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add yaml config loader with env interpolation"
```

---

## Task 4: Interface Indexer (`indexers/base.py`)

**Files:**
- Create: `torsearch/indexers/base.py`
- Test: `tests/test_indexer_base.py`

- [ ] **Step 1: Write the failing test**

`tests/test_indexer_base.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_indexer_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.indexers.base'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/indexers/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod

from torsearch.models import Category, SearchResult


class Indexer(ABC):
    name: str
    enabled: bool

    @abstractmethod
    async def search(self, query: str, category: Category) -> list[SearchResult]:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_indexer_base.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/indexers/base.py tests/test_indexer_base.py
git commit -m "feat: add Indexer abstract interface"
```

---

## Task 5: Parsing Torznab (`indexers/torznab.py` — partie parsing)

**Files:**
- Create: `torsearch/indexers/torznab.py`
- Create: `tests/fixtures/torznab_sample.xml`
- Test: `tests/test_torznab_parse.py`

- [ ] **Step 1: Create the XML fixture**

`tests/fixtures/torznab_sample.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>torr9</title>
    <item>
      <title>Cool.Movie.2024.1080p.BluRay.x264</title>
      <guid>https://torr9/details/111</guid>
      <comments>https://torr9/details/111</comments>
      <pubDate>Wed, 18 Jun 2025 12:00:00 +0000</pubDate>
      <size>2147483648</size>
      <link>magnet:?xt=urn:btih:AAAA1111</link>
      <enclosure url="magnet:?xt=urn:btih:AAAA1111" length="2147483648" type="application/x-bittorrent"/>
      <torznab:attr name="category" value="2040"/>
      <torznab:attr name="seeders" value="120"/>
      <torznab:attr name="peers" value="135"/>
      <torznab:attr name="infohash" value="AAAA1111"/>
    </item>
    <item>
      <title>Great.Show.S01E02.720p</title>
      <guid>https://torr9/details/222</guid>
      <pubDate>Tue, 17 Jun 2025 09:30:00 +0000</pubDate>
      <enclosure url="https://torr9/download/222.torrent" length="734003200" type="application/x-bittorrent"/>
      <torznab:attr name="category" value="5040"/>
      <torznab:attr name="seeders" value="40"/>
      <torznab:attr name="leechers" value="8"/>
      <torznab:attr name="infohash" value="BBBB2222"/>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write the failing test**

`tests/test_torznab_parse.py`:
```python
from pathlib import Path

from torsearch.indexers.torznab import category_from_id, parse_response
from torsearch.models import Category

FIXTURE = (Path(__file__).parent / "fixtures" / "torznab_sample.xml").read_bytes()


def test_parse_returns_two_results():
    results = parse_response(FIXTURE, "torr9")
    assert len(results) == 2


def test_parse_first_item_fields():
    r = parse_response(FIXTURE, "torr9")[0]
    assert r.title == "Cool.Movie.2024.1080p.BluRay.x264"
    assert r.size == 2147483648
    assert r.seeders == 120
    assert r.leechers == 15  # peers(135) - seeders(120)
    assert r.source == "torr9"
    assert r.category == Category.MOVIES
    assert r.download_url == "magnet:?xt=urn:btih:AAAA1111"
    assert r.is_magnet is True
    assert r.infohash == "AAAA1111"
    assert r.info_url == "https://torr9/details/111"


def test_parse_second_item_uses_enclosure_size_and_direct_leechers():
    r = parse_response(FIXTURE, "torr9")[1]
    assert r.size == 734003200
    assert r.seeders == 40
    assert r.leechers == 8
    assert r.category == Category.TV
    assert r.download_url == "https://torr9/download/222.torrent"
    assert r.is_magnet is False
    assert r.info_url == "https://torr9/details/222"


def test_parse_empty_feed_returns_empty_list():
    empty = b'<?xml version="1.0"?><rss><channel></channel></rss>'
    assert parse_response(empty, "torr9") == []


def test_category_from_id_mapping():
    assert category_from_id(2040) == Category.MOVIES
    assert category_from_id(5070) == Category.ANIME
    assert category_from_id(5040) == Category.TV
    assert category_from_id(8000) == Category.OTHER
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_torznab_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.indexers.torznab'`.

- [ ] **Step 4: Write minimal implementation (parsing only)**

`torsearch/indexers/torznab.py`:
```python
from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET

from torsearch.models import Category, SearchResult

logger = logging.getLogger(__name__)

TORZNAB_NS = "{http://torznab.com/schemas/2015/feed}"

DEFAULT_CATEGORY_IDS: dict[Category, list[int]] = {
    Category.MOVIES: [2000],
    Category.TV: [5000],
    Category.ANIME: [5070],
    Category.OTHER: [8000],
}


def category_from_id(cat_id: int) -> Category:
    if cat_id == 5070:
        return Category.ANIME
    if 2000 <= cat_id < 3000:
        return Category.MOVIES
    if 5000 <= cat_id < 6000:
        return Category.TV
    return Category.OTHER


def _int(value: str | None) -> int:
    if value and value.lstrip("-").isdigit():
        return int(value)
    return 0


def parse_response(xml_bytes: bytes, source: str) -> list[SearchResult]:
    root = ET.fromstring(xml_bytes)
    results: list[SearchResult] = []
    for item in root.iter("item"):
        attrs = {a.get("name"): a.get("value") for a in item.findall(f"{TORZNAB_NS}attr")}

        title_el = item.find("title")
        title = title_el.text if title_el is not None and title_el.text else ""

        download_url = ""
        size = 0
        enclosure = item.find("enclosure")
        if enclosure is not None:
            download_url = enclosure.get("url", "")
            size = _int(enclosure.get("length"))
        if not download_url:
            link_el = item.find("link")
            if link_el is not None and link_el.text:
                download_url = link_el.text

        if size == 0:
            size_el = item.find("size")
            if size_el is not None:
                size = _int(size_el.text)
        if size == 0:
            size = _int(attrs.get("size"))

        seeders = _int(attrs.get("seeders"))
        if "leechers" in attrs:
            leechers = _int(attrs.get("leechers"))
        elif "peers" in attrs:
            leechers = max(_int(attrs.get("peers")) - seeders, 0)
        else:
            leechers = 0

        cat_value = attrs.get("category")
        category = category_from_id(int(cat_value)) if cat_value and cat_value.isdigit() else Category.OTHER

        info_url = None
        comments_el = item.find("comments")
        guid_el = item.find("guid")
        if comments_el is not None and comments_el.text:
            info_url = comments_el.text
        elif guid_el is not None and guid_el.text and guid_el.text.startswith("http"):
            info_url = guid_el.text

        publish_date = None
        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            try:
                publish_date = parsedate_to_datetime(pub_el.text)
            except (TypeError, ValueError):
                publish_date = None

        results.append(
            SearchResult(
                title=title,
                size=size,
                seeders=seeders,
                leechers=leechers,
                source=source,
                category=category,
                download_url=download_url,
                info_url=info_url,
                publish_date=publish_date,
                infohash=attrs.get("infohash"),
            )
        )
    return results
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_torznab_parse.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add torsearch/indexers/torznab.py tests/test_torznab_parse.py tests/fixtures/torznab_sample.xml
git commit -m "feat: parse torznab xml responses into SearchResult"
```

---

## Task 6: Client TorznabIndexer (`indexers/torznab.py` — requêtes HTTP)

**Files:**
- Modify: `torsearch/indexers/torznab.py` (ajouter la classe `TorznabIndexer`)
- Test: `tests/test_torznab_indexer.py`

- [ ] **Step 1: Write the failing test**

`tests/test_torznab_indexer.py`:
```python
from pathlib import Path

import httpx
import respx

from torsearch.config import AuthMode, IndexerConfig
from torsearch.indexers.torznab import TorznabIndexer
from torsearch.models import Category

FIXTURE = (Path(__file__).parent / "fixtures" / "torznab_sample.xml").read_bytes()


def _cfg(**overrides):
    base = dict(name="torr9", url="https://api.torr9.net/api/v1/torznab", api_key="KEY")
    base.update(overrides)
    return IndexerConfig(**base)


def test_build_params_query_auth_includes_apikey():
    ix = TorznabIndexer(_cfg(auth=AuthMode.QUERY))
    params = ix._build_params("dune", Category.MOVIES)
    assert params["t"] == "search"
    assert params["q"] == "dune"
    assert params["apikey"] == "KEY"
    assert params["cat"] == "2000"
    assert ix._build_headers() == {}


def test_build_params_bearer_auth_uses_header_not_query():
    ix = TorznabIndexer(_cfg(auth=AuthMode.BEARER))
    params = ix._build_params("dune", Category.ALL)
    assert "apikey" not in params
    assert "cat" not in params  # Category.ALL -> no cat filter
    assert ix._build_headers() == {"Authorization": "Bearer KEY"}


def test_category_override_from_config():
    ix = TorznabIndexer(_cfg(categories={"movies": [2010, 2040]}))
    params = ix._build_params("dune", Category.MOVIES)
    assert params["cat"] == "2010,2040"


async def test_search_success_returns_parsed_results():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://api.torr9.net/api/v1/torznab").mock(
            return_value=httpx.Response(200, content=FIXTURE)
        )
        results = await ix.search("cool", Category.ALL)
    assert len(results) == 2
    assert results[0].source == "torr9"


async def test_search_http_error_returns_empty():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://api.torr9.net/api/v1/torznab").mock(
            return_value=httpx.Response(500)
        )
        assert await ix.search("cool", Category.ALL) == []


async def test_search_malformed_xml_returns_empty():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://api.torr9.net/api/v1/torznab").mock(
            return_value=httpx.Response(200, content=b"<not-xml")
        )
        assert await ix.search("cool", Category.ALL) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_torznab_indexer.py -v`
Expected: FAIL — `AttributeError`/`ImportError`: `TorznabIndexer` n'existe pas encore.

- [ ] **Step 3: Append the implementation**

Ajouter en haut de `torsearch/indexers/torznab.py`, dans les imports :
```python
import httpx

from torsearch.config import AuthMode, IndexerConfig
from torsearch.indexers.base import Indexer
```

Ajouter à la fin de `torsearch/indexers/torznab.py` :
```python
class TorznabIndexer(Indexer):
    def __init__(
        self,
        config: IndexerConfig,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ):
        self.name = config.name
        self.enabled = config.enabled
        self._url = config.url
        self._api_key = config.api_key
        self._auth = config.auth
        self._timeout = timeout
        self._client = client
        self._category_ids = self._build_category_ids(config)

    @staticmethod
    def _build_category_ids(config: IndexerConfig) -> dict[Category, list[int]]:
        ids = dict(DEFAULT_CATEGORY_IDS)
        for key, values in config.categories.items():
            try:
                ids[Category(key)] = values
            except ValueError:
                continue
        return ids

    def _build_params(self, query: str, category: Category) -> dict[str, str]:
        params: dict[str, str] = {"t": "search", "q": query}
        if self._auth == AuthMode.QUERY:
            params["apikey"] = self._api_key
        if category != Category.ALL:
            cat_ids = self._category_ids.get(category, [])
            if cat_ids:
                params["cat"] = ",".join(str(c) for c in cat_ids)
        return params

    def _build_headers(self) -> dict[str, str]:
        if self._auth == AuthMode.BEARER:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def search(self, query: str, category: Category) -> list[SearchResult]:
        params = self._build_params(query, category)
        headers = self._build_headers()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(self._url, params=params, headers=headers)
            response.raise_for_status()
            return parse_response(response.content, self.name)
        except Exception as exc:  # resilience: never raise to the orchestrator
            logger.warning("Indexer %s failed: %s", self.name, exc)
            return []
        finally:
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_torznab_indexer.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/indexers/torznab.py tests/test_torznab_indexer.py
git commit -m "feat: add TorznabIndexer http client with auth modes"
```

---

## Task 7: Registre d'indexers (`indexers/registry.py`)

**Files:**
- Create: `torsearch/indexers/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

`tests/test_registry.py`:
```python
from torsearch.config import Config, IndexerConfig
from torsearch.indexers.registry import build_indexers
from torsearch.indexers.torznab import TorznabIndexer


def test_builds_only_enabled_torznab_indexers():
    cfg = Config(
        indexers=[
            IndexerConfig(name="torr9", url="https://a/api", api_key="x", enabled=True),
            IndexerConfig(name="c411", url="https://b/api", api_key="y", enabled=True),
            IndexerConfig(name="off", url="https://c/api", api_key="z", enabled=False),
        ]
    )
    indexers = build_indexers(cfg)
    assert len(indexers) == 2
    assert all(isinstance(ix, TorznabIndexer) for ix in indexers)
    assert {ix.name for ix in indexers} == {"torr9", "c411"}


def test_skips_unknown_indexer_type():
    cfg = Config(
        indexers=[IndexerConfig(name="weird", type="newznab", url="https://a/api", api_key="x")]
    )
    assert build_indexers(cfg) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.indexers.registry'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/indexers/registry.py`:
```python
from __future__ import annotations

from torsearch.config import Config
from torsearch.indexers.base import Indexer
from torsearch.indexers.torznab import TorznabIndexer


def build_indexers(config: Config) -> list[Indexer]:
    indexers: list[Indexer] = []
    for ic in config.indexers:
        if not ic.enabled:
            continue
        if ic.type == "torznab":
            indexers.append(TorznabIndexer(ic, timeout=config.search.timeout_seconds))
    return indexers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_registry.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/indexers/registry.py tests/test_registry.py
git commit -m "feat: build enabled indexers from config"
```

---

## Task 8: Orchestrateur de recherche (`search/service.py`)

**Files:**
- Create: `torsearch/search/service.py`
- Test: `tests/test_search_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_search_service.py`:
```python
import asyncio

from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService


def _result(title, seeders, source="t", infohash=None, size=1000):
    return SearchResult(
        title=title,
        size=size,
        seeders=seeders,
        leechers=0,
        source=source,
        category=Category.MOVIES,
        download_url=f"magnet:?xt=urn:btih:{title}",
        infohash=infohash,
    )


class FakeIndexer:
    def __init__(self, name, results=None, error=None, delay=0.0, enabled=True):
        self.name = name
        self.enabled = enabled
        self._results = results or []
        self._error = error
        self._delay = delay

    async def search(self, query, category):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return list(self._results)


async def test_merges_and_sorts_by_seeders_desc():
    a = FakeIndexer("a", [_result("low", 5, "a")])
    b = FakeIndexer("b", [_result("high", 50, "b")])
    service = SearchService([a, b])
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["high", "low"]


async def test_failing_indexer_is_ignored():
    good = FakeIndexer("good", [_result("ok", 10, "good")])
    bad = FakeIndexer("bad", error=RuntimeError("boom"))
    service = SearchService([good, bad])
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["ok"]


async def test_timed_out_indexer_is_ignored():
    slow = FakeIndexer("slow", [_result("slow", 99, "slow")], delay=0.2)
    fast = FakeIndexer("fast", [_result("fast", 1, "fast")])
    service = SearchService([slow, fast], timeout=0.05)
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["fast"]


async def test_dedupe_by_infohash_keeps_higher_seeders():
    a = FakeIndexer("a", [_result("dup", 10, "a", infohash="HASH")])
    b = FakeIndexer("b", [_result("dup", 80, "b", infohash="HASH")])
    service = SearchService([a, b])
    out = await service.search("q", Category.ALL)
    assert len(out) == 1
    assert out[0].seeders == 80


async def test_disabled_indexer_not_queried():
    enabled = FakeIndexer("on", [_result("on", 10, "on")])
    disabled = FakeIndexer("off", [_result("off", 99, "off")], enabled=False)
    service = SearchService([enabled, disabled])
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["on"]


def test_indexers_property_exposes_list():
    a = FakeIndexer("a")
    service = SearchService([a])
    assert service.indexers == [a]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_search_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.search.service'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/search/service.py`:
```python
from __future__ import annotations

import asyncio
import logging

from torsearch.indexers.base import Indexer
from torsearch.models import Category, SearchResult

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, indexers: list[Indexer], timeout: float = 10.0):
        self._indexers = indexers
        self._timeout = timeout

    @property
    def indexers(self) -> list[Indexer]:
        return self._indexers

    async def search(self, query: str, category: Category = Category.ALL) -> list[SearchResult]:
        active = [ix for ix in self._indexers if ix.enabled]
        results_lists = await asyncio.gather(*(self._search_one(ix, query, category) for ix in active))
        merged = [r for lst in results_lists for r in lst]
        deduped = self._dedupe(merged)
        deduped.sort(key=lambda r: r.seeders, reverse=True)
        return deduped

    async def _search_one(
        self, indexer: Indexer, query: str, category: Category
    ) -> list[SearchResult]:
        try:
            return await asyncio.wait_for(indexer.search(query, category), timeout=self._timeout)
        except Exception as exc:  # resilience: one tracker must not break the search
            logger.warning("Search on %s failed: %s", indexer.name, exc)
            return []

    @staticmethod
    def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
        best: dict[str, SearchResult] = {}
        for r in results:
            key = r.infohash.lower() if r.infohash else f"{r.title.lower()}|{r.size}"
            existing = best.get(key)
            if existing is None or r.seeders > existing.seeders:
                best[key] = r
        return list(best.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_search_service.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/search/service.py tests/test_search_service.py
git commit -m "feat: add resilient parallel search service"
```

---

## Task 9: Client Transmission (`transmission/client.py`)

**Files:**
- Create: `torsearch/transmission/client.py`
- Test: `tests/test_transmission.py`

- [ ] **Step 1: Write the failing test**

`tests/test_transmission.py`:
```python
from types import SimpleNamespace

from torsearch.config import TransmissionConfig
from torsearch.transmission.client import TransmissionClient


class FakeRpc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.added = []

    def add_torrent(self, url):
        self.added.append(url)
        return SimpleNamespace(id=42)


def test_add_returns_torrent_id_and_passes_url():
    created = {}

    def factory(**kwargs):
        client = FakeRpc(**kwargs)
        created["client"] = client
        return client

    cfg = TransmissionConfig(host="tr.local", port=9092, username="u", password="p")
    tc = TransmissionClient(cfg, client_factory=factory)
    torrent_id = tc.add("magnet:?xt=urn:btih:XYZ")

    assert torrent_id == 42
    assert created["client"].added == ["magnet:?xt=urn:btih:XYZ"]
    assert created["client"].kwargs["host"] == "tr.local"
    assert created["client"].kwargs["port"] == 9092
    assert created["client"].kwargs["protocol"] == "http"


def test_https_config_uses_https_protocol():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    cfg = TransmissionConfig(https=True)
    TransmissionClient(cfg, client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["protocol"] == "https"


def test_empty_credentials_become_none():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    TransmissionClient(TransmissionConfig(), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["username"] is None
    assert captured["password"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transmission.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.transmission.client'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/transmission/client.py`:
```python
from __future__ import annotations

from transmission_rpc import Client

from torsearch.config import TransmissionConfig


class TransmissionClient:
    def __init__(self, config: TransmissionConfig, client_factory=Client):
        self._config = config
        self._client_factory = client_factory
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory(
                protocol="https" if self._config.https else "http",
                host=self._config.host,
                port=self._config.port,
                username=self._config.username or None,
                password=self._config.password or None,
            )
        return self._client

    def add(self, download_url: str) -> int:
        torrent = self._get_client().add_torrent(download_url)
        return torrent.id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transmission.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/transmission/client.py tests/test_transmission.py
git commit -m "feat: add transmission rpc client wrapper"
```

---

## Task 10: Interface web (`web/routes.py` + templates)

**Files:**
- Create: `torsearch/web/routes.py`
- Create: `torsearch/web/templates/base.html`
- Create: `torsearch/web/templates/index.html`
- Create: `torsearch/web/templates/trackers.html`
- Create: `torsearch/web/templates/partials/results.html`
- Create: `torsearch/web/templates/partials/toast.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_web.py`:
```python
from fastapi.testclient import TestClient

from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService
from torsearch.web.routes import create_app


class FakeIndexer:
    def __init__(self, name, results=None):
        self.name = name
        self.enabled = True
        self._results = results or []

    async def search(self, query, category):
        return list(self._results)


class FakeTransmission:
    def __init__(self):
        self.added = []

    def add(self, download_url):
        self.added.append(download_url)
        return 7


def _make(results=None):
    service = SearchService([FakeIndexer("t1", results or [])])
    transmission = FakeTransmission()
    client = TestClient(create_app(service, transmission))
    return client, transmission


def _movie():
    return SearchResult(
        title="Cool.Movie.2024",
        size=2147483648,
        seeders=99,
        leechers=3,
        source="t1",
        category=Category.MOVIES,
        download_url="magnet:?xt=urn:btih:ABC",
    )


def test_index_renders_search_form():
    client, _ = _make()
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'name="q"' in resp.text


def test_search_renders_result_rows():
    client, _ = _make([_movie()])
    resp = client.get("/search", params={"q": "cool", "cat": "all"})
    assert resp.status_code == 200
    assert "Cool.Movie.2024" in resp.text
    assert "99" in resp.text


def test_search_empty_query_shows_placeholder():
    client, _ = _make([_movie()])
    resp = client.get("/search", params={"q": "   "})
    assert resp.status_code == 200
    assert "Aucun" in resp.text


def test_download_sends_to_transmission():
    client, transmission = _make()
    resp = client.post("/download", data={"download_url": "magnet:?xt=urn:btih:XYZ"})
    assert resp.status_code == 200
    assert transmission.added == ["magnet:?xt=urn:btih:XYZ"]
    assert "Transmission" in resp.text


def test_trackers_page_lists_indexer_names():
    client, _ = _make()
    resp = client.get("/trackers")
    assert resp.status_code == 200
    assert "t1" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.web.routes'`.

- [ ] **Step 3: Create the templates**

`torsearch/web/templates/base.html`:
```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TorSearch</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
  <header class="border-b border-slate-700 px-6 py-4 flex items-center gap-6">
    <a href="/" class="text-xl font-bold text-emerald-400">TorSearch</a>
    <nav class="flex gap-4 text-sm">
      <a href="/" class="hover:text-emerald-400">Recherche</a>
      <a href="/trackers" class="hover:text-emerald-400">Trackers</a>
    </nav>
  </header>
  <main class="max-w-5xl mx-auto px-6 py-8">
    {% block content %}{% endblock %}
  </main>
  <div id="toast" class="fixed bottom-4 right-4"></div>
</body>
</html>
```

`torsearch/web/templates/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<form hx-get="/search" hx-target="#results" hx-indicator="#spinner" class="flex flex-wrap gap-3 mb-6">
  <input type="text" name="q" placeholder="Rechercher un film, une serie..." autofocus
         class="flex-1 min-w-[240px] rounded bg-slate-800 border border-slate-700 px-4 py-2">
  <select name="cat" class="rounded bg-slate-800 border border-slate-700 px-3 py-2">
    {% for c in categories %}
    <option value="{{ c.value }}">{{ c.value | capitalize }}</option>
    {% endfor %}
  </select>
  <button type="submit" class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-5 py-2">
    Chercher
  </button>
  <span id="spinner" class="htmx-indicator self-center text-slate-400">Recherche...</span>
</form>
<div id="results"></div>
{% endblock %}
```

`torsearch/web/templates/partials/results.html`:
```html
{% if not results %}
  <p class="text-slate-400">Aucun resultat{% if query %} pour "{{ query }}"{% endif %}.</p>
{% else %}
<table class="w-full text-sm">
  <thead class="text-left text-slate-400 border-b border-slate-700">
    <tr>
      <th class="py-2">Nom</th><th>Source</th><th class="text-right">Taille</th>
      <th class="text-right">Seed</th><th class="text-right">Leech</th><th></th>
    </tr>
  </thead>
  <tbody>
  {% for r in results %}
    <tr class="border-b border-slate-800 hover:bg-slate-800/50">
      <td class="py-2 pr-3">{{ r.title }}</td>
      <td><span class="rounded bg-slate-700 px-2 py-0.5 text-xs">{{ r.source }}</span></td>
      <td class="text-right whitespace-nowrap">{{ (r.size / 1073741824) | round(2) }} Go</td>
      <td class="text-right text-emerald-400">{{ r.seeders }}</td>
      <td class="text-right text-slate-400">{{ r.leechers }}</td>
      <td class="text-right whitespace-nowrap">
        <form hx-post="/download" hx-target="#toast" class="inline">
          <input type="hidden" name="download_url" value="{{ r.download_url }}">
          <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-2 py-1 text-xs">+ Transmission</button>
        </form>
        <button class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs"
                onclick="navigator.clipboard.writeText('{{ r.download_url }}')">Copier</button>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
```

`torsearch/web/templates/partials/toast.html`:
```html
<div class="rounded px-4 py-2 shadow-lg {% if ok %}bg-emerald-600{% else %}bg-red-600{% endif %}">
  {{ message }}
</div>
```

`torsearch/web/templates/trackers.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-lg font-semibold mb-4">Trackers configures</h1>
<ul class="space-y-2">
  {% for ix in indexers %}
  <li class="flex items-center justify-between rounded bg-slate-800 px-4 py-3">
    <span>{{ ix.name }}</span>
    <span class="text-xs {% if ix.enabled %}text-emerald-400{% else %}text-slate-500{% endif %}">
      {{ "active" if ix.enabled else "desactive" }}
    </span>
  </li>
  {% else %}
  <li class="text-slate-400">Aucun tracker configure.</li>
  {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 4: Write the routes**

`torsearch/web/routes.py`:
```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from torsearch.models import Category
from torsearch.search.service import SearchService
from torsearch.transmission.client import TransmissionClient

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "categories": list(Category)}
    )


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", cat: str = "all"):
    service: SearchService = request.app.state.search_service
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    results = await service.search(q, category) if q.strip() else []
    return templates.TemplateResponse(
        "partials/results.html", {"request": request, "results": results, "query": q}
    )


@router.post("/download", response_class=HTMLResponse)
async def download(request: Request, download_url: str = Form(...)):
    transmission: TransmissionClient = request.app.state.transmission
    try:
        torrent_id = transmission.add(download_url)
        message = f"Ajoute a Transmission (#{torrent_id})"
        ok = True
    except Exception as exc:
        message = f"Erreur Transmission : {exc}"
        ok = False
    return templates.TemplateResponse(
        "partials/toast.html", {"request": request, "ok": ok, "message": message}
    )


@router.get("/trackers", response_class=HTMLResponse)
async def trackers(request: Request):
    service: SearchService = request.app.state.search_service
    return templates.TemplateResponse(
        "trackers.html", {"request": request, "indexers": service.indexers}
    )


def create_app(search_service: SearchService, transmission: TransmissionClient) -> FastAPI:
    app = FastAPI(title="TorSearch")
    app.state.search_service = search_service
    app.state.transmission = transmission
    app.include_router(router)
    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_web.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add torsearch/web/ tests/test_web.py
git commit -m "feat: add web ui with search, download and trackers pages"
```

---

## Task 11: Câblage applicatif (`main.py`)

**Files:**
- Create: `torsearch/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

`tests/test_main.py`:
```python
from fastapi import FastAPI

from torsearch import main


def test_build_app_wires_services(tmp_path, monkeypatch):
    monkeypatch.setenv("TORR9_API_KEY", "secret")
    config = tmp_path / "config.yaml"
    config.write_text(
        """
transmission:
  host: localhost
indexers:
  - name: torr9
    type: torznab
    url: https://api.torr9.net/api/v1/torznab
    api_key: ${TORR9_API_KEY}
    enabled: true
"""
    )
    app = main.build_app(str(config))
    assert isinstance(app, FastAPI)
    assert [ix.name for ix in app.state.search_service.indexers] == ["torr9"]
    assert app.state.transmission is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL — `AttributeError: module 'torsearch.main' has no attribute 'build_app'` (ou ModuleNotFound).

- [ ] **Step 3: Write minimal implementation**

`torsearch/main.py`:
```python
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
```

> Note : on expose `get_app` (factory) plutôt qu'une instance `app` au niveau module, pour ne pas charger `config.yaml` à l'import (les tests importent `torsearch.main` sans config). Uvicorn sera lancé via la factory : `uvicorn "torsearch.main:get_app" --factory`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (tous les tests des tasks 1–11).

- [ ] **Step 6: Commit**

```bash
git add torsearch/main.py tests/test_main.py
git commit -m "feat: wire config, services and app factory"
```

---

## Task 12: Packaging (config exemples, Docker, README)

**Files:**
- Create: `config.example.yaml`
- Create: `.env.example`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md`

- [ ] **Step 1: Create `config.example.yaml`**

```yaml
transmission:
  host: localhost      # hote de Transmission (ex: nom du service docker)
  port: 9091
  username: ""
  password: ""
  https: false

search:
  timeout_seconds: 10

indexers:
  - name: torr9
    type: torznab
    url: https://api.torr9.net/api/v1/torznab
    api_key: ${TORR9_API_KEY}
    auth: query          # query (defaut) | bearer
    enabled: true
  - name: c411
    type: torznab
    url: https://c411.org/api
    api_key: ${C411_API_KEY}
    auth: query
    enabled: true
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Copier vers .env et renseigner tes passkeys (jamais commite)
TORR9_API_KEY=ta-passkey-torr9
C411_API_KEY=ta-cle-c411
```

- [ ] **Step 3: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    TORSEARCH_CONFIG=/config/config.yaml

COPY pyproject.toml ./
COPY torsearch ./torsearch
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "torsearch.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  torsearch:
    build: .
    container_name: torsearch
    ports:
      - "8080:8000"
    volumes:
      - ./config:/config        # placer config.yaml dans ./config/
    env_file:
      - .env
    restart: unless-stopped
```

- [ ] **Step 5: Create `README.md`**

```markdown
# TorSearch

Recherche un film/serie sur plusieurs trackers Torznab a la fois et envoie le
resultat choisi a Transmission. Outil web perso, auto-heberge.

## Lancer en local

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml   # editer les trackers
cp .env.example .env                 # renseigner les passkeys
uvicorn torsearch.main:get_app --factory --reload
```

Ouvrir http://localhost:8000

## Lancer avec Docker

```bash
mkdir -p config
cp config.example.yaml config/config.yaml
cp .env.example .env                 # renseigner les passkeys
docker compose up -d --build
```

Ouvrir http://localhost:8080

## Tests

```bash
python -m pytest
```

## Configuration

- `config.yaml` : trackers (Torznab) + connexion Transmission.
- Les passkeys sont injectees via `${VAR}` depuis l'environnement / `.env`.
- Ajouter un tracker Torznab = une entree dans `indexers:` (aucun code).
```

- [ ] **Step 6: Verify the build and run the suite**

Run:
```bash
python -m pytest -v
python -c "from torsearch.main import build_app; print('factory OK')"
```
Expected: tous les tests PASS ; impression `factory OK`.

- [ ] **Step 7: Commit**

```bash
git add config.example.yaml .env.example Dockerfile docker-compose.yml README.md
git commit -m "chore: add config examples, docker packaging and readme"
```

---

## Notes de vérification finale (manuel, hors TDD)

Après la Task 12, avant de considérer la v1 terminée :

1. **Smoke test réel** : avec un `config.yaml` rempli (vraies passkeys torr9/c411), lancer
   `uvicorn torsearch.main:get_app --factory --reload`, chercher un titre, vérifier que des
   résultats des deux trackers remontent.
2. **Auth c411** : si c411 renvoie 401/403 en mode `auth: query`, basculer son entrée sur
   `auth: bearer` dans `config.yaml` et re-tester (l'`IndexerConfig` le supporte déjà).
3. **Transmission** : avec un Transmission joignable (Web UI/RPC activé), cliquer
   « + Transmission » sur un résultat et confirmer l'ajout côté Transmission.

Ces points dépendent de services externes et ne sont pas couverts par la suite automatique
(qui reste 100 % offline via fixtures/mocks).
