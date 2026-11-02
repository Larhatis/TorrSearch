"""Release cards shown to Claude: rich enough to judge, never a tracker link (chantier 11)."""
from __future__ import annotations

import json

from torsearch.claude.cards import release_card
from torsearch.config import LibraryConfig
from torsearch.models import Category, SearchResult
from torsearch.transmission.client import TorrentInfo


def _r(title, size=1_000_000_000, seeders=20, infohash=None, url="magnet:?xt=urn:btih:x"):
    return SearchResult(title=title, size=size, seeders=seeders, leechers=0, source="trk",
                        category=Category.TV, download_url=url, infohash=infohash)


def test_card_never_exposes_the_download_url():
    card = release_card(_r("Show.S01.MULTi.2160p.DV.WEB.x265-GRP", url="https://tracker.example/dl?passkey=SECRET"),
                        "rid1", LibraryConfig(), None, [])
    dumped = json.dumps(card)
    assert "SECRET" not in dumped and "tracker.example" not in dumped
    assert card["id"] == "rid1" and card["tracker"] == "trk"


def test_card_fields_for_a_season_pack():
    card = release_card(_r("Show.S01.MULTi.2160p.DV.HDR10+.WEB.x265.10bit-GRP", size=10_000_000_000),
                        "r", LibraryConfig(), None, [])
    assert card["hdr"] == ["DV", "HDR10+"] and card["bits"] == 10 and card["codec"] != "unknown"
    assert card["groupe"] == "GRP" and card["langue"] == "multi" and card["resolution"] == "2160p"
    assert card["episodes"] == ["S01"]
    assert card["taille_go"] == 10.0
    assert card["taille_par_episode_go"] == 1.0  # a season counts 10 episodes without TMDB
    assert card["verdict"] == "acceptable"


def test_movie_has_no_per_episode_size():
    card = release_card(_r("Film.2024.MULTi.1080p.WEB.x264-GRP"), "r", LibraryConfig(), None, [])
    assert card["taille_par_episode_go"] is None and card["episodes"] == []


def test_card_verdicts():
    vost = release_card(_r("Show.S01E01.VOSTFR.1080p.WEB.x264-GRP"), "r", LibraryConfig(accept_vostfr=False), None, [])
    assert vost["verdict"] == "VOSTFR refusee par le profil"
    cam = release_card(_r("Film.2024.CAM.x264-GRP"), "r", LibraryConfig(), None, [])
    assert cam["verdict"].startswith("source degradee")
    few = release_card(_r("Film.2024.MULTi.1080p.WEB.x264-GRP", seeders=0), "r", LibraryConfig(), None, [])
    assert few["verdict"] == "pas assez de seeders"


def test_episode_size_cap_applies_per_episode():
    profile = LibraryConfig(max_episode_gb=1.5)
    pack = release_card(_r("Show.S01.MULTi.1080p.WEB.x265-GRP", size=12_000_000_000), "r", profile, None, [])
    assert pack["verdict"] == "acceptable"  # 1.2 Go per episode
    big = release_card(_r("Show.S01E01.MULTi.2160p.WEB.x265-GRP", size=4_000_000_000), "r", profile, None, [])
    assert big["verdict"] == "trop gros pour le profil"


def test_title_check_with_a_target():
    card = release_card(_r("Other.Show.S01E01.MULTi.1080p.WEB.x264-GRP"), "r", LibraryConfig(), None, [],
                        target_title="Severance", is_series=True)
    assert card["verdict"] == "ne correspond pas a l'oeuvre"


def test_card_knows_what_transmission_already_has():
    t = TorrentInfo(id=1, name="Show.S01E01.MULTi.1080p.WEB.x264-GRP", percent=50.0, status="downloading",
                    down_rate=0, up_rate=0, size=1, info_hash="abc")
    assert release_card(_r("Other.Name", infohash="ABC"), "r", LibraryConfig(), None, [t])["deja_dans_transmission"]
    assert release_card(_r("show.s01e01.multi.1080p.web.x264-grp"), "r", LibraryConfig(), None, [t])[
        "deja_dans_transmission"]
    assert not release_card(_r("Show.S01E02.MULTi.1080p.WEB.x264-GRP"), "r", LibraryConfig(), None, [t])[
        "deja_dans_transmission"]


class _Blacklist:
    def is_blacklisted(self, infohash, title):
        return title.startswith("Dead")


def test_blacklisted_release():
    card = release_card(_r("Dead.Show.S01E01.MULTi.1080p.WEB.x264-GRP"), "r", LibraryConfig(), _Blacklist(), [])
    assert card["en_liste_noire"] is True and card["verdict"] == "en liste noire"
