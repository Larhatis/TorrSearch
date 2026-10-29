from __future__ import annotations

from torsearch.library.cleanup import error_groups, find_duplicates, removal_is_safe
from torsearch.transmission.client import TorrentInfo


def _t(id, name, size=1_000_000_000, percent=100.0, error="", code=0, h=None):
    return TorrentInfo(id=id, name=name, percent=percent, status="seeding", down_rate=0, up_rate=0,
                       size=size, error_string=error, error_code=code, info_hash=h or f"h{id}")


def _ids(group):
    return [c.torrent.id for c in group.items], [c.torrent.id for c in group.items if c.remove]


def _groups(torrents):
    return find_duplicates(torrents)


def test_two_copies_of_a_movie_keep_the_best():
    torrents = [
        _t(441, "Spider.Man.Brand.New.Day.2026.IMAX.MULTI.VF2.2160p.WEBRip.HDR.x265-BATGirl.mkv", 7_600_000_000),
        _t(451, "Spider-Man.Brand.New.Day.2026.MULTi.TRUEFRENCH.2160p.HDR.DV.WEB-DL.H265-Slay3R.mkv", 27_600_000_000),
        _t(453, "The.Dog.Stars.2026.MULTi.VFQ.1080p.WEBRip.x265-GL0P.mkv", 2_700_000_000),
        _t(460, "The.Dog.Stars.2026.MULTi.VF2.4KLight.DV.HDR10+.WEBRip.DDP5.1.Atmos.x265-[BATGirl].mkv", 5_300_000_000),
        _t(1, "Heat.1995.MULTi.2160p.BluRay-QTZ.mkv"),
    ]
    groups = {g.title: g for g in _groups(torrents)}
    assert set(groups) == {"Spider Man Brand New Day", "The Dog Stars"}
    assert _ids(groups["Spider Man Brand New Day"]) == ([451, 441], [441])
    assert _ids(groups["The Dog Stars"]) == ([460, 453], [453])


def test_never_grouped_other_year_no_year_or_other_show():
    assert _groups([_t(1, "Dune.1984.MULTi.1080p.BluRay-X"), _t(2, "Dune.2021.MULTi.2160p.BluRay-Y")]) == []
    assert _groups([_t(1, "Heat.MULTi.1080p-X"), _t(2, "Heat.MULTi.2160p-Y")]) == []
    assert _groups([_t(1, "Doctor.Who.2005.S01E01.1080p-X"), _t(2, "Doctor.Who.2023.S01E01.2160p-Y")]) == []
    assert _groups([_t(1, "Charmed.S01E01.1080p-X"), _t(2, "Charmed.2018.S01E01.2160p-Y")]) == []


def test_collections_bonus_parts_and_cuts_are_never_grouped():
    assert _groups([_t(1, "Retour.vers.le.Futur.1985-1990.Trilogie.MULTi.1080p-X"),
                    _t(2, "Retour.vers.le.Futur.1985.MULTi.2160p-Y")]) == []
    assert _groups([_t(1, "Dune.2021.Bonus.MULTi.1080p-X"), _t(2, "Dune.2021.MULTi.2160p-Y")]) == []
    assert _groups([_t(1, "Dune.2021.OST.FLAC-X"), _t(2, "Dune.2021.MULTi.2160p-Y")]) == []
    assert _groups([_t(1, "Aliens.1986.Extended.MULTi.1080p-X"), _t(2, "Aliens.1986.MULTi.2160p-Y")]) == []
    assert _groups([_t(1, "Stranger.Things.S04.Part.1.MULTi.1080p-X"),
                    _t(2, "Stranger.Things.S04E08.MULTi.1080p-Y")]) == []
    assert _groups([_t(1, "Wednesday.S02.Partie.1.MULTi-X"), _t(2, "Wednesday.S02.Partie.2.MULTi-Y")]) == []


def test_season_pack_makes_single_episodes_removable_but_not_other_seasons():
    torrents = [
        _t(10, "MobLand.S01.MULTi.2160p.WEB-BATGirl", 18_700_000_000),
        _t(11, "MobLand.S01E01.MULTi.2160p.WEB-FW", 3_000_000_000),
        _t(12, "MobLand.S01E02.MULTi.2160p.WEB-FW", 3_000_000_000),
        _t(13, "MobLand.S02E01.MULTi.2160p.WEB-FW", 3_000_000_000),
    ]
    groups = _groups(torrents)
    assert len(groups) == 1
    assert _ids(groups[0]) == ([10, 11, 12], [11, 12])


def test_incomplete_or_errored_pack_never_justifies_removing_episodes():
    for pack in (_t(10, "Show.S01.MULTi.1080p-X", percent=3.0),
                 _t(10, "Show.S01.MULTi.1080p-X", error="No data found! Ensure your drives are connected", code=3)):
        groups = _groups([pack, _t(11, "Show.S01E01.MULTi.1080p-Y"), _t(12, "Show.S01E02.MULTi.1080p-Y")])
        # The complete episodes are kept; the broken pack may hold other episodes: not proposed either.
        assert groups[0].removable == []

    multi = [_t(1, "Show.S01-S05.MULTi.1080p-X", percent=1.0), _t(2, "Show.S02.MULTi.2160p-Y")]
    assert _groups(multi)[0].removable == []


def test_incomplete_copy_is_the_one_removed():
    torrents = [_t(1, "Show.S01E01.MULTi.2160p.WEB-A", 5_000_000_000, percent=12.0),
                _t(2, "Show.S01E01.MULTi.1080p.WEB-B", 2_000_000_000)]
    assert _ids(_groups(torrents)[0]) == ([2, 1], [1])


def test_same_name_copies_are_never_proposed():
    torrents = [_t(1, "Dune.2021.MULTi.2160p.WEB-X", h="a"), _t(2, "Dune.2021.MULTi.2160p.WEB-X", h="b")]
    group = _groups(torrents)[0]
    assert group.removable == []
    assert [c.shares_files for c in group.items] == [False, True]
    assert removal_is_safe(group, {"b"}) is not None


def test_removal_must_keep_everything_covered():
    torrents = [_t(10, "Show.S01.MULTi.2160p.WEB-X"), _t(11, "Show.S01E05.MULTi.1080p.WEB-Y")]
    group = _groups(torrents)[0]
    assert removal_is_safe(group, {"h11"}) is None
    assert removal_is_safe(group, {"h10"}) is not None  # keeping only E05 loses the season
    assert removal_is_safe(group, {"h10", "h11"}) is not None


def test_error_groups_skip_tracker_warnings_and_mask_secrets():
    torrents = [
        _t(1, "A", error="invalid passkey", code=2),
        _t(2, "B", error="invalid passkey", code=2),
        _t(3, "C", error="Tracker gave error: https://t.example/announce?passkey=SECRET", code=2),
        _t(4, "D", error="Could not connect to tracker", code=1),
        _t(5, "E"),
    ]
    groups = error_groups(torrents)
    assert [(msg, [t.id for t in items]) for msg, items in groups] == [
        ("invalid passkey", [1, 2]),
        ("Tracker gave error: https://t.example/announce?passkey=***", [3]),
    ]
