from torsearch.library.episodes import parse_episodes


def test_single_episode():
    assert parse_episodes("Show.S01E01.1080p.WEB") == {"S01E01"}


def test_multi_episode_concat():
    assert parse_episodes("Show.S02E05E06.1080p") == {"S02E05", "S02E06"}


def test_multi_episode_dash():
    assert parse_episodes("Show.S02E05-E06.x265") == {"S02E05", "S02E06"}


def test_case_insensitive_and_zero_pad():
    assert parse_episodes("show.s1e5.hdtv") == {"S01E05"}


def test_season_pack_sxx():
    assert parse_episodes("Show.S02.COMPLETE.1080p") == {"S02"}


def test_season_pack_word_en():
    assert parse_episodes("Show.Season.3.1080p") == {"S03"}


def test_season_pack_word_fr():
    assert parse_episodes("Show.Saison.1.FRENCH") == {"S01"}


def test_episode_range_expands_inner_episodes():
    assert parse_episodes("Show.S01E01-E12.1080p") == {f"S01E{n:02d}" for n in range(1, 13)}


def test_episode_range_single_e_form():
    assert parse_episodes("Show.S01E01-12.x265") == {f"S01E{n:02d}" for n in range(1, 13)}


def test_episode_range_does_not_eat_resolution():
    # "-1080p" must not be read as a range up to E10
    assert parse_episodes("Show.S01E01-1080p") == {"S01E01"}


def test_inverted_range_is_treated_as_single():
    assert parse_episodes("Show.S01E05-E03.x") == {"S01E05"}


def test_unparsable_returns_empty():
    assert parse_episodes("Show.2024.1080p.WEB") == set()
    assert parse_episodes("Random.Movie.2160p.BluRay") == set()
