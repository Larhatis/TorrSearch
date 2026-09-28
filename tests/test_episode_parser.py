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


def test_sanitize_folder_name():
    from torsearch.library.episodes import sanitize_folder_name

    assert sanitize_folder_name("Paolo") == "Paolo"
    assert sanitize_folder_name("Marvel's What If...?") == "Marvel's What If"
    assert sanitize_folder_name("Show: Subtitle / Part 1") == "Show Subtitle Part 1"
    assert sanitize_folder_name("   ") == "Unknown"


def test_extract_season_number():
    from torsearch.library.episodes import extract_season_number

    assert extract_season_number(episodes={"S01E01"}) == 1
    assert extract_season_number(episodes={"S02E05", "S02E06"}) == 2
    assert extract_season_number(episodes={"S01", "S02"}) is None  # multi-season
    assert extract_season_number(title="Show.S03E01.1080p") == 3


def test_build_tv_download_dir_single_season():
    from torsearch.library.episodes import build_tv_download_dir

    # With base dir
    assert build_tv_download_dir("/downloads/disk2", "Paolo", {"S01E01"}) == "/downloads/disk2/Paolo/Saison 01"
    # Trailing slash trimmed cleanly
    assert build_tv_download_dir("/downloads/disk2/", "Paolo", {"S01E01"}) == "/downloads/disk2/Paolo/Saison 01"
    # Season pack
    assert build_tv_download_dir("/downloads/disk2", "Paolo", {"S02"}) == "/downloads/disk2/Paolo/Saison 02"
    # No base dir (relative path)
    assert build_tv_download_dir(None, "Paolo", {"S01E01"}) == "Paolo/Saison 01"


def test_build_tv_download_dir_multi_season():
    from torsearch.library.episodes import build_tv_download_dir

    # Multiple seasons -> placed directly in show directory
    assert build_tv_download_dir("/downloads/disk2", "Paolo", {"S01", "S02"}) == "/downloads/disk2/Paolo"


def test_find_episodes_on_disk(tmp_path):
    from torsearch.library.episodes import find_episodes_on_disk

    tv_dir = tmp_path / "TV"
    show_dir = tv_dir / "Lanterns" / "Saison 01"
    show_dir.mkdir(parents=True)

    # Valid video file with size > 10MB
    ep1 = show_dir / "Lanterns.S01E01.MULTi.1080p.mkv"
    ep1.write_bytes(b"0" * 10_000_001)

    # Valid video file in root of series folder
    ep2 = tv_dir / "Lanterns" / "Lanterns.S01E02.1080p.mp4"
    ep2.write_bytes(b"0" * 10_000_001)

    # Too small / stub file (< 10MB) -> ignored
    stub = show_dir / "Lanterns.S01E03.sample.mkv"
    stub.write_bytes(b"0" * 100)

    # Non-video file -> ignored
    nfo = show_dir / "Lanterns.S01E04.nfo"
    nfo.write_bytes(b"0" * 10_000_001)

    found = find_episodes_on_disk(str(tv_dir), "Lanterns")
    assert found == {"S01E01", "S01E02"}

