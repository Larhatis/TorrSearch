from torsearch.parser.release import parse_release


def test_parse_movie_french_bluray():
    rel = parse_release("Inception.2010.TRUEFRENCH.1080p.BluRay.x264-CiNE")
    assert rel.clean_title == "Inception"
    assert rel.year == 2010
    assert rel.resolution == "1080p"
    assert rel.source == "bluray"
    assert not rel.is_banned_source
    assert rel.language == "vff"
    assert rel.codec == "x264"
    assert rel.episodes == set()


def test_parse_movie_multi_4k_webdl():
    rel = parse_release("Avatar.The.Way.of.Water.2022.MULTi.TRUEFRENCH.2160p.WEB-DL.H.265-FLUX")
    assert rel.clean_title == "Avatar The Way of Water"
    assert rel.year == 2022
    assert rel.resolution == "2160p"
    assert rel.source == "web-dl"
    assert not rel.is_banned_source
    assert rel.language == "multi"
    assert rel.codec == "h265"


def test_parse_banned_sources_cam_ts_scr():
    rel_cam = parse_release("Dune.Part.Two.2024.FRENCH.CAM.XViD-BAD")
    assert rel_cam.is_banned_source is True
    assert rel_cam.source == "cam"

    rel_ts = parse_release("The.Batman.2022.TELESYNC.1080p.H264-TS")
    assert rel_ts.is_banned_source is True
    assert rel_ts.source == "ts"

    rel_tc = parse_release("Oppenheimer.2023.TELECINE.720p")
    assert rel_tc.is_banned_source is True
    assert rel_tc.source == "tc"

    rel_scr = parse_release("Top.Gun.Maverick.2022.DVDSCR.x264")
    assert rel_scr.is_banned_source is True
    assert rel_scr.source == "screener"


def test_parse_series_episode_and_season_pack():
    rel_ep = parse_release("Lost.S01E03.FRENCH.720p.WEB-DL.x264-EXTREME")
    assert rel_ep.clean_title == "Lost"
    assert rel_ep.episodes == {"S01E03"}
    assert rel_ep.resolution == "720p"
    assert rel_ep.language == "vf"
    assert not rel_ep.is_banned_source

    rel_pack = parse_release("Severance.S01.COMPLETE.MULTi.1080p.WEB-DL.x265-ARTE")
    assert rel_pack.clean_title == "Severance"
    assert rel_pack.episodes == {"S01"}
    assert rel_pack.language == "multi"
    assert rel_pack.resolution == "1080p"


def test_parse_languages():
    assert parse_release("Show.S01E01.MULTi.1080p").language == "multi"
    assert parse_release("Show.S01E01.TRUEFRENCH.1080p").language == "vff"
    assert parse_release("Show.S01E01.VFF.1080p").language == "vff"
    assert parse_release("Show.S01E01.VFQ.1080p").language == "vfq"
    assert parse_release("Show.S01E01.FRENCH.1080p").language == "vf"
    assert parse_release("Show.S01E01.VF.1080p").language == "vf"
    assert parse_release("Show.S01E01.VOSTFR.1080p").language == "vostfr"
    assert parse_release("Show.S01E01.SUBFRENCH.1080p").language == "vostfr"
    assert parse_release("Show.S01E01.ENGLISH.1080p").language == "vo"
    assert parse_release("Show.S01E01.1080p").language == "unknown"


def test_parse_preserves_special_title_words():
    rel = parse_release("Mr.Robot.S01E01.FRENCH.1080p.WEB-DL")
    assert rel.clean_title == "Mr Robot"
    assert rel.episodes == {"S01E01"}
