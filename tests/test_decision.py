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


def _ep_result(title, size):
    return _make_result(title, size=size, infohash=f"hash-{title}", category=Category.TV)


def test_select_series_releases_prefers_pack_by_cost_per_episode():
    missing = {f"S01E0{i}" for i in range(1, 7)}
    singles = [_ep_result(f"MobLand.S01E0{i}.MULTi.2160p.WEB-FW", 3_000_000_000) for i in range(1, 7)]
    pack = _ep_result("MobLand.S01.MULTi.2160p.WEB-BATGirl", 8_000_000_000)

    picks = select_series_releases(singles + [pack], target_title="MobLand",
                                   missing_episodes=missing, qualities=["2160p"])
    assert [(r.title, covered) for r, covered in picks] == [(pack.title, missing)]


def test_select_series_releases_drops_singles_made_redundant_by_a_pack():
    # Singles exist only for E01, E02, E04 (better language), the pack is needed for the rest.
    missing = {f"S01E0{i}" for i in range(1, 7)}
    singles = [_ep_result(f"MobLand.S01E0{i}.MULTi.2160p.WEB-FW", 3_000_000_000) for i in (1, 2, 4)]
    pack = _ep_result("MobLand.S01.2160p.WEB.x265-BATGirl", 8_000_000_000)

    picks = select_series_releases(
        singles + [pack], target_title="MobLand", missing_episodes=missing, qualities=["2160p"],
    )
    assert [r.title for r, _ in picks] == [pack.title]
    assert picks[0][1] == missing


def test_movie_over_size_cap_is_rejected():
    big = _make_result("Dune.2021.MULTi.2160p.WEB-A", size=27_000_000_000, infohash="big")
    small = _make_result("Dune.2021.MULTi.2160p.WEB-B", size=8_000_000_000, infohash="small")
    pick = select_best_movie_release([big, small], target_title="Dune", target_year=2021,
                                     qualities=["2160p"], max_size=20_000_000_000)
    assert pick is small
    assert select_best_movie_release([big], target_title="Dune", target_year=2021,
                                     qualities=["2160p"], max_size=20_000_000_000) is None


def test_series_cap_is_per_episode_for_season_packs():
    missing = {f"S01E{i:02d}" for i in range(1, 11)}
    pack = _ep_result("MobLand.S01.MULTi.2160p.WEB-BATGirl", 18_700_000_000)  # ~1.9 Go / episode
    picks = select_series_releases([pack], target_title="MobLand", missing_episodes=missing,
                                   qualities=["2160p"], max_episode_size=5_000_000_000)
    assert [r.title for r, _ in picks] == [pack.title]

    huge_single = _ep_result("MobLand.S01E01.MULTi.2160p.REMUX-X", 12_000_000_000)
    assert select_series_releases([huge_single], target_title="MobLand", missing_episodes={"S01E01"},
                                  qualities=["2160p"], max_episode_size=5_000_000_000) == []


def test_season_pack_without_tmdb_counts_a_typical_season():
    from torsearch.search.decision import _episode_count

    assert _episode_count({"S01"}, {"S01E01"}, aired_known=False) == 10
    assert _episode_count({"S01"}, {f"S01E{i:02d}" for i in range(1, 9)}, aired_known=True) == 8
    assert _episode_count({"S01E01", "S01E02"}, set()) == 2


def test_rules_reject_vostfr_and_excluded_words():
    from torsearch.search.decision import ReleaseRules

    vostfr = _make_result("The.Odyssey.2026.VOSTFR.1080p.WEB-X", infohash="v")
    stv = _make_result("The.Odyssey.2026.STV.MULTi.1080p.WEB-X", infohash="s")
    good = _make_result("The.Odyssey.2026.MULTi.1080p.WEB-X", infohash="g")
    strict = ReleaseRules(accept_vostfr=False, exclude_words=("stv",))

    assert evaluate_release(vostfr, "The Odyssey", target_year=2026, rules=strict).rejection_reason == "vostfr_refused"
    assert evaluate_release(stv, "The Odyssey", target_year=2026, rules=strict).rejection_reason == "excluded_word:stv"
    assert evaluate_release(good, "The Odyssey", target_year=2026, rules=strict).acceptable
    assert evaluate_release(vostfr, "The Odyssey", target_year=2026).acceptable  # default: accepted
    assert select_best_movie_release([vostfr, stv, good], "The Odyssey", target_year=2026, rules=strict) is good


def test_excluded_words_match_whole_words_only():
    from torsearch.search.decision import ReleaseRules

    rules = ReleaseRules(exclude_words=("ts", "hc sub"))
    assert evaluate_release(_make_result("Rush.2013.MULTi.1080p.BluRay-TSUNAMI", infohash="a"), "Rush",
                            target_year=2013, rules=rules).acceptable
    assert not evaluate_release(_make_result("Rush.2013.HC.SUB.1080p.WEB-X", infohash="b"), "Rush",
                                target_year=2013, rules=rules).acceptable


def test_multi_season_pack_is_judged_per_episode_over_all_its_seasons():
    missing = {f"S{s:02d}E{e:02d}" for s in range(1, 6) for e in range(1, 11)}
    pack = _ep_result("Breaking.Bad.S01-S05.MULTi.1080p.BluRay-X", 150_000_000_000)  # 3 Go / episode
    picks = select_series_releases([pack], target_title="Breaking Bad", missing_episodes=missing,
                                   qualities=["1080p"], max_episode_size=5_000_000_000)
    assert [r.title for r, _ in picks] == [pack.title]
    assert picks[0][1] == missing


def test_excluded_words_split_on_any_punctuation_and_vost_variants():
    from torsearch.search.decision import ReleaseRules

    rules = ReleaseRules(accept_vostfr=False, exclude_words=("stv",))
    for title in ("Rush.2013.{STV}.1080p.WEB-X", "Rush.2013.1080p.x265&STV-X"):
        assert evaluate_release(_make_result(title, infohash=title), "Rush", target_year=2013,
                                rules=rules).rejection_reason == "excluded_word:stv"
    for title in ("Rush.2013.VOST.FR.1080p.WEB-X", "Rush.2013.VOST-FR.1080p.WEB-X", "Rush.2013.VOST.1080p.WEB-X"):
        assert evaluate_release(_make_result(title, infohash=title), "Rush", target_year=2013,
                                rules=rules).rejection_reason == "vostfr_refused"
