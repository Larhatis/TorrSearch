from datetime import datetime, timezone

from torsearch.models import Category, SearchResult
from torsearch.search.filters import ResultFilters, apply, detect_quality


def _r(title="X", size=1000, seeders=10, leechers=1, date=None):
    return SearchResult(
        title=title, size=size, seeders=seeders, leechers=leechers,
        source="t", category=Category.MOVIES,
        download_url="magnet:?xt=urn:btih:" + title.replace(" ", "_"),
        publish_date=date,
    )


def test_detect_quality():
    assert detect_quality("Movie.2024.2160p.x265") == "2160p"
    assert detect_quality("Movie.4K.HDR") == "2160p"
    assert detect_quality("Movie.1080p.BluRay") == "1080p"
    assert detect_quality("Show.S01.720p") == "720p"
    assert detect_quality("Old.480p.DVD") == "480p"
    assert detect_quality("Some.Release.Group") == "other"


def test_filter_min_seeders():
    out = apply([_r("A", seeders=5), _r("B", seeders=50)], ResultFilters(min_seeders=10))
    assert [r.title for r in out] == ["B"]


def test_filter_size_range():
    gb = 1024 ** 3
    out = apply([_r("small", size=gb), _r("big", size=10 * gb)], ResultFilters(min_size=2 * gb, max_size=20 * gb))
    assert [r.title for r in out] == ["big"]


def test_filter_quality_subset():
    out = apply([_r("Movie.1080p"), _r("Movie.720p")], ResultFilters(qualities=["1080p"]))
    assert [r.title for r in out] == ["Movie.1080p"]


def test_filter_quality_empty_keeps_all():
    assert len(apply([_r("Movie.1080p"), _r("Movie.720p")], ResultFilters(qualities=[]))) == 2


def test_filter_exclude_case_insensitive():
    out = apply([_r("Movie.CAM.xvid"), _r("Movie.1080p")], ResultFilters(exclude=["cam"]))
    assert [r.title for r in out] == ["Movie.1080p"]


def test_sort_size_asc():
    res = [_r("big", size=300), _r("small", size=100), _r("mid", size=200)]
    out = apply(res, ResultFilters(sort="size", direction="asc"))
    assert [r.title for r in out] == ["small", "mid", "big"]


def test_sort_seeders_desc_is_default():
    res = [_r("a", seeders=1), _r("b", seeders=9), _r("c", seeders=5)]
    assert [r.title for r in apply(res, ResultFilters())] == ["b", "c", "a"]


def test_sort_title_asc_case_insensitive():
    res = [_r("Zeta"), _r("alpha"), _r("Mango")]
    out = apply(res, ResultFilters(sort="title", direction="asc"))
    assert [r.title for r in out] == ["alpha", "Mango", "Zeta"]


def test_sort_date_desc_handles_missing_dates():
    d_old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    d_new = datetime(2024, 1, 1, tzinfo=timezone.utc)
    res = [_r("old", date=d_old), _r("new", date=d_new), _r("undated", date=None)]
    out = apply(res, ResultFilters(sort="date", direction="desc"))
    assert [r.title for r in out][:2] == ["new", "old"]


def test_invalid_sort_and_direction_fall_back():
    res = [_r("a", seeders=1), _r("b", seeders=9)]
    out = apply(res, ResultFilters(sort="bogus", direction="weird"))
    assert [r.title for r in out] == ["b", "a"]
