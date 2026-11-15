from torsearch.config import Config, LibraryConfig, PathsConfig
from torsearch.monitor.diskspace import folder_usage, format_bytes, has_room, low_folders

GB = 1_000_000_000


class SpaceTransmission:
    def __init__(self, free: dict | None = None, default: int | None = None):
        self.free = free or {}
        self.default = default
        self.asked: list[str | None] = []

    async def free_space(self, path):
        self.asked.append(path)
        return self.default if path is None else self.free.get(path)


def test_min_free_defaults_to_50_gb():
    assert LibraryConfig().min_free_gb == 50
    assert LibraryConfig().min_free_bytes == 50 * GB
    assert LibraryConfig(min_free_gb=0).min_free_bytes == 0


async def test_has_room_when_enough_space():
    tr = SpaceTransmission({"/d/disk2": 600 * GB})
    assert await has_room(tr, "/d/disk2", 60 * GB, 50 * GB) is True


async def test_no_room_when_release_would_go_under_the_threshold():
    tr = SpaceTransmission({"/d/disk2": 100 * GB})
    assert await has_room(tr, "/d/disk2", 60 * GB, 50 * GB) is False


async def test_size_zero_is_judged_on_free_space_alone():
    tr = SpaceTransmission({"/d/disk2": 40 * GB})
    assert await has_room(tr, "/d/disk2", 0, 50 * GB) is False


async def test_threshold_zero_disables_the_check():
    tr = SpaceTransmission({"/d/disk2": 1 * GB})
    assert await has_room(tr, "/d/disk2", 60 * GB, 0) is True
    assert tr.asked == []


async def test_unknown_space_never_blocks():
    assert await has_room(SpaceTransmission(), "/d/disk2", 60 * GB, 50 * GB) is True


async def test_transport_without_free_space_never_blocks():
    class Plain:
        pass

    assert await has_room(Plain(), "/d/disk2", 60 * GB, 50 * GB) is True


def _config(paths: dict, min_free_gb: float = 50) -> Config:
    return Config(paths=PathsConfig(by_category=paths), library=LibraryConfig(min_free_gb=min_free_gb))


async def test_folder_usage_merges_categories_on_the_same_folder():
    tr = SpaceTransmission({"/d/disk1/Films": 1900 * GB, "/d/disk2": 600 * GB})
    cfg = _config({"movies": "/d/disk1/Films", "tv": "/d/disk2", "anime": "/d/disk2"})
    assert await folder_usage(tr, cfg) == [
        ("Films", "/d/disk1/Films", 1900 * GB),
        ("Series, Anime", "/d/disk2", 600 * GB),
    ]


async def test_folder_usage_without_folders_measures_transmission_default():
    tr = SpaceTransmission(default=300 * GB)
    assert await folder_usage(tr, _config({})) == [("Par defaut", None, 300 * GB)]


async def test_folder_usage_adds_default_when_movies_or_tv_has_no_folder():
    tr = SpaceTransmission({"/d/disk1/Films": 1900 * GB}, default=300 * GB)
    labels = [label for label, _, _ in await folder_usage(tr, _config({"movies": "/d/disk1/Films"}))]
    assert labels == ["Films", "Par defaut"]


async def test_low_folders_keeps_only_folders_under_the_threshold():
    tr = SpaceTransmission({"/d/disk1/Films": 1900 * GB, "/d/disk2": 40 * GB})
    cfg = _config({"movies": "/d/disk1/Films", "tv": "/d/disk2"})
    assert await low_folders(tr, cfg) == [("Series", "/d/disk2", 40 * GB)]
    assert await low_folders(tr, _config({"tv": "/d/disk2"}, min_free_gb=0)) == []


def test_format_bytes():
    assert format_bytes(638 * GB) == "638 Go"
    assert format_bytes(1_869 * GB) == "1,9 To"
    assert format_bytes(int(4.5 * GB)) == "4,5 Go"
