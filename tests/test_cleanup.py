from __future__ import annotations

from torsearch.library.cleanup import error_groups, find_duplicates
from torsearch.transmission.client import TorrentInfo


def _t(id, name, size=1_000_000_000, percent=100.0, error=""):
    return TorrentInfo(id=id, name=name, percent=percent, status="seeding", down_rate=0, up_rate=0,
                       size=size, error_string=error)


def _ids(group):
    return [c.torrent.id for c in group.items], [c.torrent.id for c in group.items if c.remove]


def test_two_copies_of_a_movie_keep_the_best():
    torrents = [
        _t(441, "Spider.Man.Brand.New.Day.2026.IMAX.MULTI.VF2.2160p.WEBRip.HDR.x265-BATGirl.mkv", 7_600_000_000),
        _t(451, "Spider-Man.Brand.New.Day.2026.MULTi.TRUEFRENCH.2160p.HDR.DV.WEB-DL.H265-Slay3R.mkv", 27_600_000_000),
        _t(453, "The.Dog.Stars.2026.MULTi.VFQ.1080p.WEBRip.x265-GL0P.mkv", 2_700_000_000),
        _t(460, "The.Dog.Stars.2026.MULTi.VF2.4KLight.DV.HDR10+.WEBRip.DDP5.1.Atmos.x265-[BATGirl].mkv", 5_300_000_000),
        _t(1, "Heat.1995.MULTi.2160p.BluRay-QTZ.mkv"),
    ]
    groups = {g.title: g for g in find_duplicates(torrents)}
    assert set(groups) == {"Spider Man Brand New Day", "The Dog Stars"}
    # Same quality: the bigger copy is kept (higher bitrate)
    assert _ids(groups["Spider Man Brand New Day"]) == ([451, 441], [441])
    # 2160p beats 1080p
    assert _ids(groups["The Dog Stars"]) == ([460, 453], [453])


def test_same_title_other_year_is_not_a_duplicate():
    torrents = [_t(1, "Dune.1984.MULTi.1080p.BluRay-X"), _t(2, "Dune.2021.MULTi.2160p.BluRay-Y")]
    assert find_duplicates(torrents) == []


def test_movie_without_year_is_never_grouped():
    assert find_duplicates([_t(1, "Heat.MULTi.1080p-X"), _t(2, "Heat.MULTi.2160p-Y")]) == []


def test_season_pack_makes_single_episodes_removable_but_not_other_seasons():
    torrents = [
        _t(10, "MobLand.S01.MULTi.2160p.WEB-BATGirl", 18_700_000_000),
        _t(11, "MobLand.S01E01.MULTi.2160p.WEB-FW", 3_000_000_000),
        _t(12, "MobLand.S01E02.MULTi.2160p.WEB-FW", 3_000_000_000),
        _t(13, "MobLand.S02E01.MULTi.2160p.WEB-FW", 3_000_000_000),
    ]
    groups = find_duplicates(torrents)
    assert len(groups) == 1
    assert _ids(groups[0]) == ([10, 11, 12], [11, 12])


def test_incomplete_copy_is_the_one_removed():
    torrents = [
        _t(1, "Show.S01E01.MULTi.2160p.WEB-A", 5_000_000_000, percent=12.0),
        _t(2, "Show.S01E01.MULTi.1080p.WEB-B", 2_000_000_000),
    ]
    assert _ids(find_duplicates(torrents)[0]) == ([2, 1], [1])


def test_error_groups_by_message_with_secrets_masked():
    torrents = [
        _t(1, "A", error="invalid passkey"),
        _t(2, "B", error="invalid passkey"),
        _t(3, "C", error="Tracker gave error: https://t.example/announce?passkey=SECRET"),
        _t(4, "D"),
    ]
    groups = error_groups(torrents)
    assert [(msg, [t.id for t in items]) for msg, items in groups] == [
        ("invalid passkey", [1, 2]),
        ("Tracker gave error: https://t.example/announce?passkey=***", [3]),
    ]
