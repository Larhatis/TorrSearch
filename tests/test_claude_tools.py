"""The MCP tools Claude uses: search, compare, send and follow; never delete (chantier 11)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from mcp import Client

from torsearch.claude.server import build_claude_server, claude_instructions
from torsearch.config import Config, LibraryConfig
from torsearch.db.database import Database
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, MediaResult, SearchResult
from torsearch.monitor.grabs import GrabRegistry
from torsearch.monitor.history import MonitorHistory
from torsearch.search.result_cache import ResultCache
from torsearch.transmission.client import AddedTorrent

PASSKEY_URL = "https://tracker.example/download?id=1&passkey=SECRETKEY"


def _r(title, infohash=None, size=2_000_000_000, category=Category.TV):
    return SearchResult(title=title, size=size, seeders=30, leechers=1, source="trk", category=category,
                        download_url=f"{PASSKEY_URL}&t={title}", infohash=infohash)


class FakeSearch:
    def __init__(self, results):
        self._results = results
        self.queries: list[str] = []

    async def search(self, query, category, only=None):
        self.queries.append(query)
        return list(self._results)


class FakeTmdb:
    def __init__(self, enabled=True):
        self.enabled = enabled

    async def search(self, query):
        return [MediaResult(tmdb_id=95396, media_type="tv", title="Severance", original_title="Severance",
                            year="2022", overview="Des employes...")]

    async def get_details(self, media_type, tmdb_id):
        if media_type == "movie":
            return MediaResult(tmdb_id=tmdb_id, media_type="movie", title="Dune", original_title="Dune", year="2024")
        return MediaResult(tmdb_id=tmdb_id, media_type="tv", title="Severance", original_title="Severance",
                           year="2022")

    async def seasons(self, tv_id):
        return [SimpleNamespace(season_number=n, season_tag=f"S{n:02d}",
                                episodes=[SimpleNamespace(code=f"S{n:02d}E{e:02d}") for e in (1, 2)])
                for n in (1, 2)]


class FakeTransmission:
    def __init__(self):
        self.added: list[str] = []

    async def add(self, url, download_dir=None):
        self.added.append(url)
        return AddedTorrent(id=len(self.added), info_hash=f"h{len(self.added)}")

    async def list_torrents(self):
        return []


class FakeCtx:
    def __init__(self, results, tmdb_enabled=True, profile=None):
        self.config = Config(library=profile or LibraryConfig())
        self.search_service = FakeSearch(results)
        self.tmdb = FakeTmdb(tmdb_enabled)
        self.jellyfin = SimpleNamespace(enabled=False)
        self.transmission = FakeTransmission()

    def update_settings(self, config):
        self.config = config


def _state(tmp_path, results=(), **kw):
    db = Database(tmp_path / "db.sqlite")
    return SimpleNamespace(
        ctx=FakeCtx(list(results), **kw), library=MovieLibrary(db), series_library=SeriesLibrary(db),
        history=MonitorHistory(db), grabs=GrabRegistry(db), blacklist=None, result_cache=ResultCache(),
        monitor=SimpleNamespace(woken=0, wake=lambda: None),
    )


async def _call(client, name, args=None):
    result = await client.call_tool(name, args or {})
    return result.content[0].text


async def test_tool_list_has_no_destructive_tool(tmp_path):
    async with Client(build_claude_server(_state(tmp_path))) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"chercher_oeuvre", "chercher_releases", "telecharger", "suivre_serie",
                     "surveiller_film", "etat_telechargements", "etat_surveillance", "profil_qualite"}


async def test_search_returns_cards_without_urls(tmp_path):
    state = _state(tmp_path, [_r("Severance.S02.MULTi.2160p.DV.WEB.x265-GRP", infohash="A")])
    async with Client(build_claude_server(state)) as c:
        text = await _call(c, "chercher_releases", {"requete": "Severance S02"})
    assert "SECRETKEY" not in text and "tracker.example" not in text
    [card] = json.loads(text)
    assert card["hdr"] == ["DV"] and state.result_cache.get(card["id"]) is not None


async def test_search_with_a_work_checks_the_title(tmp_path):
    state = _state(tmp_path, [_r("Severance.S02.MULTi.1080p.WEB.x264-GRP"), _r("Other.Show.S02.MULTi.1080p.WEB-GRP")])
    async with Client(build_claude_server(state)) as c:
        cards = json.loads(await _call(c, "chercher_releases",
                                       {"requete": "Severance S02", "tmdb_id": 95396, "type": "tv"}))
    verdicts = {card["titre"]: card["verdict"] for card in cards}
    assert verdicts["Severance.S02.MULTi.1080p.WEB.x264-GRP"] == "acceptable"
    assert verdicts["Other.Show.S02.MULTi.1080p.WEB-GRP"] == "ne correspond pas a l'oeuvre"


async def test_download_by_id_sends_and_records_manual(tmp_path):
    state = _state(tmp_path, [_r("Severance.S02E01.MULTi.1080p.WEB.x264-GRP", infohash="A")])
    async with Client(build_claude_server(state)) as c:
        [card] = json.loads(await _call(c, "chercher_releases", {"requete": "Severance"}))
        message = await _call(c, "telecharger", {"release_id": card["id"]})
    assert "Ajoute a Transmission" in message
    assert len(state.ctx.transmission.added) == 1
    assert state.grabs.get("h1").origin == "manual"


async def test_expired_or_unknown_id_sends_nothing(tmp_path):
    state = _state(tmp_path)
    async with Client(build_claude_server(state)) as c:
        message = await _call(c, "telecharger", {"release_id": "invented"})
    assert message == "Resultat expire : relance la recherche."
    assert state.ctx.transmission.added == []


async def test_eleventh_download_of_the_hour_is_refused(tmp_path):
    state = _state(tmp_path, [_r(f"Show.S01E{n:02d}.MULTi.1080p.WEB-GRP", infohash=f"x{n}") for n in range(1, 12)])
    async with Client(build_claude_server(state)) as c:
        cards = json.loads(await _call(c, "chercher_releases", {"requete": "Show"}))
        messages = [await _call(c, "telecharger", {"release_id": card["id"]}) for card in cards[:11]]
    assert len(state.ctx.transmission.added) == 10
    assert messages[-1].startswith("Limite atteinte")


async def test_search_limit_30_per_hour(tmp_path):
    state = _state(tmp_path, [_r("Show.S01E01.MULTi.1080p.WEB-GRP")])
    async with Client(build_claude_server(state)) as c:
        for _ in range(30):
            await _call(c, "chercher_releases", {"requete": "Show"})
        message = await _call(c, "chercher_releases", {"requete": "Show"})
    assert message.startswith("Limite atteinte")
    assert len(state.ctx.search_service.queries) == 30


async def test_follow_series_marks_owned_seasons(tmp_path):
    state = _state(tmp_path)
    async with Client(build_claude_server(state)) as c:
        message = await _call(c, "suivre_serie", {"tmdb_id": 95396, "saisons_acquises": [1]})
    series = state.series_library.get(95396)
    assert series.title == "Severance" and "Severance" in message
    assert set(series.grabbed) == {"S01", "S01E01", "S01E02"}
    assert state.ctx.config.monitor.enabled is True


async def test_watch_movie_enables_surveillance(tmp_path):
    state = _state(tmp_path)
    async with Client(build_claude_server(state)) as c:
        await _call(c, "surveiller_film", {"tmdb_id": 693134})
    assert state.library.get(693134).title == "Dune"
    assert state.ctx.config.monitor.enabled is True


async def test_status_tools(tmp_path):
    state = _state(tmp_path, profile=LibraryConfig(accept_vostfr=False, max_episode_gb=2.0))
    async with Client(build_claude_server(state)) as c:
        profile = json.loads(await _call(c, "profil_qualite"))
        watch = json.loads(await _call(c, "etat_surveillance"))
        downloads = json.loads(await _call(c, "etat_telechargements"))
    assert profile["vostfr_acceptee"] is False and profile["taille_max_episode_go"] == 2.0
    assert set(watch) == {"films", "series", "recherches_libres", "derniers_envois"}
    assert downloads == []


async def test_instructions_follow_the_profile():
    assert "VOSTFR" in claude_instructions(LibraryConfig(accept_vostfr=False))
    assert "refus" in claude_instructions(LibraryConfig(accept_vostfr=False)).lower()


async def test_tmdb_missing_is_explained(tmp_path):
    async with Client(build_claude_server(_state(tmp_path, tmdb_enabled=False))) as c:
        message = await _call(c, "chercher_oeuvre", {"titre": "Severance"})
    assert "cle TMDB absente" in message


async def test_find_work(tmp_path):
    async with Client(build_claude_server(_state(tmp_path))) as c:
        [work] = json.loads(await _call(c, "chercher_oeuvre", {"titre": "Severance"}))
    assert work["tmdb_id"] == 95396 and work["type"] == "tv" and work["surveille"] is False
