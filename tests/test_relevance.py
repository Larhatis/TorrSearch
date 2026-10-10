from torsearch.models import Category, SearchResult
from torsearch.search.filters import ResultFilters, apply
from torsearch.search.relevance import compute_relevance
from torsearch.search.service import SearchService


def _res(title: str, seeders: int = 0, source: str = "tracker1", size: int = 1_000_000_000) -> SearchResult:
    return SearchResult(
        title=title,
        size=size,
        seeders=seeders,
        leechers=0,
        source=source,
        category=Category.MOVIES,
        download_url=f"magnet:?xt=urn:btih:{title}",
    )


def test_exact_title_match_ranks_highest():
    r_exact = _res("Inception.2010.MULTI.1080p.BluRay.x264", seeders=0)
    r_spinoff = _res("Inception.The.Cobol.Job.2010.720p", seeders=50)
    score_exact = compute_relevance(r_exact, "Inception")
    score_spinoff = compute_relevance(r_spinoff, "Inception")
    assert score_exact > score_spinoff


def test_year_matching_boosts_correct_movie():
    r_2024 = _res("Dune.Part.Two.2024.MULTI.1080p", seeders=5)
    r_2021 = _res("Dune.2021.MULTI.1080p", seeders=100)
    r_1984 = _res("Dune.1984.MULTI.1080p", seeders=20)
    score_2024 = compute_relevance(r_2024, "Dune 2024")
    score_2021 = compute_relevance(r_2021, "Dune 2024")
    score_1984 = compute_relevance(r_1984, "Dune 2024")
    assert score_2024 > score_2021
    assert score_2024 > score_1984


def test_season_matching_boosts_correct_season():
    r_s01 = _res("Severance.S01.COMPLETE.MULTI.1080p.WEB", seeders=2)
    r_s02 = _res("Severance.S02.COMPLETE.MULTI.1080p.WEB", seeders=20)
    score_s01 = compute_relevance(r_s01, "Severance S01")
    score_s02 = compute_relevance(r_s02, "Severance S01")
    assert score_s01 > score_s02


def test_banned_sources_penalized():
    r_clean = _res("Deadpool.and.Wolverine.2024.1080p.WEB", seeders=1)
    r_cam = _res("Deadpool.and.Wolverine.2024.HDCAM", seeders=200)
    assert compute_relevance(r_clean, "Deadpool & Wolverine") > compute_relevance(r_cam, "Deadpool & Wolverine")


def test_numeral_synonyms():
    r_part_two = _res("Dune.Part.Two.2024.MULTI.1080p")
    r_two = _res("Dune.2.2024.MULTI.1080p")
    score1 = compute_relevance(r_part_two, "Dune 2")
    score2 = compute_relevance(r_two, "Dune 2")
    assert score1 > 700
    assert score2 > 700


def test_multi_tracker_interleaving_with_zero_seeders():
    """Verify that results from multiple trackers are not grouped tracker-by-tracker."""
    t1_exact = _res("Severance.S01.COMPLETE.MULTI.1080p", seeders=0, source="tracker1")
    t1_other = _res("Severance.Blade.2019.FRENCH", seeders=0, source="tracker1")
    t2_exact = _res("Severance.S01E01.MULTI.1080p", seeders=0, source="tracker2")
    t2_s02 = _res("Severance.S02.COMPLETE.FRENCH.1080p", seeders=0, source="tracker2")

    # In raw input, tracker 1's items come first, then tracker 2's items
    raw = [t1_exact, t1_other, t2_exact, t2_s02]

    # When sorted by relevance for 'Severance S01':
    filtered = apply(raw, ResultFilters(sort="relevance", query="Severance S01"))
    titles = [r.title for r in filtered]

    # Both S01 releases (from tracker1 AND tracker2) must be in the top 2!
    assert titles[0] in (t1_exact.title, t2_exact.title)
    assert titles[1] in (t1_exact.title, t2_exact.title)
    # The unrelated t1_other must be at the very bottom, NOT before tracker2's matches!
    assert titles[-1] == t1_other.title


class FakeIndexer:
    def __init__(self, name: str, results: list[SearchResult]):
        self.name = name
        self.enabled = True
        self._results = results

    async def search(self, query: str, category: Category):
        return list(self._results)


async def test_search_service_sorts_by_relevance_across_trackers():
    # Tracker 1 has an exact match with 0 seeds and an unrelated match with 10 seeds
    t1_match = _res("Inception.2010.MULTI.1080p", seeders=0, source="t1")
    t1_unrelated = _res("Inception.The.Cobol.Job.720p", seeders=10, source="t1")
    # Tracker 2 has an exact match with 5 seeds
    t2_match = _res("Inception.2010.FRENCH.1080p", seeders=5, source="t2")

    service = SearchService([
        FakeIndexer("t1", [t1_match, t1_unrelated]),
        FakeIndexer("t2", [t2_match]),
    ])

    results = await service.search("Inception")
    # The two real Inception releases from t2 and t1 must be top 2, unrelated at the bottom
    top_titles = [r.title for r in results[:2]]
    assert t1_match.title in top_titles
    assert t2_match.title in top_titles
    assert results[-1].title == t1_unrelated.title
