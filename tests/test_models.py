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
