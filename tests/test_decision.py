from __future__ import annotations

from torsearch.models import Category, SearchResult
from torsearch.search.decision import (
    evaluate_release,
    select_best_movie_release,
    select_series_releases,
)


def _make_result(
    title: str,
    size: int = 1_000_000_000,
    seeders: int = 10,
    download_url: str = "http://example.com/torrent",
    infohash: str | None = None,
    category: Category = Category.MOVIES,
) -> SearchResult:
    return SearchResult(
        title=title,
        size=size,
        seeders=seeders,
        leechers=1,
        source="indexer1",
        category=category,
        download_url=download_url,
        infohash=infohash or title[:10],
    )


def test_evaluate_release_rejects_banned_sources():
    res = _make_result("Avatar.2009.CAM.XViD")
    decision = evaluate_release(res, target_title="Avatar", target_year=2009)
    assert decision.acceptable is False
    assert "banned_source" in decision.rejection_reason


def test_evaluate_release_rejects_unmatched_title():
    res = _make_result("Lost.in.Space.S01E01.FRENCH.1080p.WEB-DL")
    decision = evaluate_release(res, target_title="Lost", is_series=True)
    assert decision.acceptable is False
    assert "title_mismatch" in decision.rejection_reason


def test_evaluate_release_rejects_vo_without_subs():
    res = _make_result("Succession.S01E01.ENGLISH.1080p.WEB-DL")
    decision = evaluate_release(res, target_title="Succession", is_series=True)
    assert decision.acceptable is False
    assert "unsupported_language" in decision.rejection_reason


def test_select_best_movie_language_hierarchy():
    # MULTI/VFF beats VF beats VOSTFR even if VF or VOSTFR has more seeders
    vostfr = _make_result("Inception.2010.VOSTFR.1080p.BluRay", seeders=100)
    vf = _make_result("Inception.2010.FRENCH.1080p.BluRay", seeders=50)
    vff = _make_result("Inception.2010.TRUEFRENCH.1080p.BluRay", seeders=10)
    multi = _make_result("Inception.2010.MULTi.1080p.BluRay", seeders=15)

    # Between MULTI and VFF, both are Tier 1, so seeders break tie -> MULTI (15 > 10)
    best = select_best_movie_release(
        [vostfr, vf, vff, multi],
        target_title="Inception",
        target_year=2010,
        qualities=["1080p"],
    )
    assert best is not None
    assert best.title == multi.title

    # Without MULTI or VFF, VF is chosen over VOSTFR
    best_vf = select_best_movie_release(
        [vostfr, vf],
        target_title="Inception",
        target_year=2010,
        qualities=["1080p"],
    )
    assert best_vf is not None
    assert best_vf.title == vf.title

    # VOSTFR is chosen if only VOSTFR is available
    best_vostfr = select_best_movie_release(
        [vostfr],
        target_title="Inception",
        target_year=2010,
        qualities=["1080p"],
    )
    assert best_vostfr is not None
    assert best_vostfr.title == vostfr.title


def test_select_best_movie_quality_hierarchy():
    # 2160p preferred over 1080p when configured as [2160p, 1080p]
    m_1080p = _make_result("Dune.2021.MULTi.1080p.BluRay", seeders=50)
    m_4k = _make_result("Dune.2021.MULTi.2160p.BluRay", seeders=20)

    best = select_best_movie_release(
        [m_1080p, m_4k],
        target_title="Dune",
        target_year=2021,
        qualities=["2160p", "1080p"],
    )
    assert best is not None
    assert best.title == m_4k.title


def test_select_series_releases_smallest_pack_and_language():
    # Only chase S01E03
    pack = _make_result("Lost.S01.COMPLETE.MULTi.1080p", size=25_000_000_000, seeders=30)
    single_ep = _make_result("Lost.S01E03.MULTi.1080p", size=1_500_000_000, seeders=15)
    other_ep = _make_result("Lost.S01E04.MULTi.1080p", size=1_500_000_000, seeders=20)

    picks = select_series_releases(
        [pack, single_ep, other_ep],
        target_title="Lost",
        missing_episodes={"S01E03"},
        qualities=["1080p"],
    )
    # Should pick single_ep because it covers S01E03 with smaller size than pack
    assert len(picks) == 1
    chosen_result, covered = picks[0]
    assert chosen_result.title == single_ep.title
    assert covered == {"S01E03"}
