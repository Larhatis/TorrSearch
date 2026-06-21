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


from torsearch.models import MediaResult


def test_media_result_poster_url_built_from_path():
    m = MediaResult(tmdb_id=1, media_type="movie", title="Dune", poster_path="/p.jpg")
    assert m.poster_url == "https://image.tmdb.org/t/p/w342/p.jpg"


def test_media_result_poster_url_none_without_path():
    m = MediaResult(tmdb_id=2, media_type="tv", title="GoT")
    assert m.poster_url is None


from datetime import datetime, timezone

from torsearch.models import WantedMovie


def test_wanted_movie_defaults_and_poster_url():
    m = WantedMovie(tmdb_id=1, title="Dune", year="2024", poster_path="/p.jpg",
                    added_at=datetime(2026, 6, 20, tzinfo=timezone.utc))
    assert m.status == "wanted"
    assert m.grabbed_at is None
    assert m.poster_url == "https://image.tmdb.org/t/p/w342/p.jpg"


from torsearch.models import WantedSeries


def test_wanted_series_defaults_and_poster_url():
    s = WantedSeries(tmdb_id=1, title="Show", year="2024", poster_path="/s.jpg",
                     added_at=datetime(2026, 6, 21, tzinfo=timezone.utc))
    assert s.grabbed == []
    assert s.poster_url == "https://image.tmdb.org/t/p/w342/s.jpg"
