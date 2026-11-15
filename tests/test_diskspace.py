from torsearch.config import Config, LibraryConfig, PathsConfig
from torsearch.monitor.diskspace import folder_usage, format_bytes, low_folders

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


async def _room(tr, size, min_free_gb=50, path="/d/disk2"):
    from torsearch.monitor.diskspace import DiskBudget

    return await DiskBudget(tr, _config({"tv": "/d/disk2"}, min_free_gb)).has_room(path, size)


async def test_has_room_when_enough_space():
    assert await _room(SpaceTransmission({"/d/disk2": 600 * GB}), 60 * GB) is True


async def test_no_room_when_release_would_go_under_the_threshold():
    assert await _room(SpaceTransmission({"/d/disk2": 100 * GB}), 60 * GB) is False


async def test_size_zero_is_judged_on_free_space_alone():
    assert await _room(SpaceTransmission({"/d/disk2": 40 * GB}), 0) is False


async def test_threshold_zero_disables_the_check():
    tr = SpaceTransmission({"/d/disk2": 1 * GB})
    assert await _room(tr, 60 * GB, min_free_gb=0) is True
    assert tr.asked == []


async def test_unknown_space_never_blocks():
    assert await _room(SpaceTransmission(), 60 * GB) is True


async def test_transport_without_free_space_never_blocks():
    class Plain:
        async def list_torrents(self):
            return []

    assert await _room(Plain(), 60 * GB) is True


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


# --- Per-cycle reservation (review: Transmission does not reserve space on add) ---

from torsearch.monitor.diskspace import DiskBudget  # noqa: E402
from torsearch.transmission.client import TorrentInfo  # noqa: E402


def _t(name, size, percent, download_dir):
    return TorrentInfo(id=1, name=name, percent=percent, status="downloading", down_rate=0, up_rate=0,
                       size=size, download_dir=download_dir)


class BudgetTransmission(SpaceTransmission):
    def __init__(self, free=None, default=None, torrents=None):
        super().__init__(free, default)
        self.torrents = torrents or []

    async def list_torrents(self):
        return list(self.torrents)


async def test_budget_counts_sends_of_the_same_cycle():
    tr = BudgetTransmission({"/d/disk2/Show/Saison 01": 120 * GB, "/d/disk2/Show/Saison 02": 120 * GB})
    budget = DiskBudget(tr, _config({"tv": "/d/disk2"}))
    assert await budget.has_room("/d/disk2/Show/Saison 01", 40 * GB)
    budget.reserve("/d/disk2/Show/Saison 01", 40 * GB)
    assert await budget.has_room("/d/disk2/Show/Saison 02", 30 * GB)  # 120 - 40 - 30 = 50
    budget.reserve("/d/disk2/Show/Saison 02", 30 * GB)
    assert not await budget.has_room("/d/disk2/Show/Saison 02", 1 * GB)


async def test_budget_counts_what_unfinished_torrents_still_have_to_write():
    tr = BudgetTransmission(
        {"/d/disk1/Films/Dune (2024) [tmdbid-1]": 150 * GB},
        torrents=[_t("Remux", 60 * GB, 25.0, "/d/disk1/Films/Big (2020) [tmdbid-9]"),  # 45 GB to come
                  _t("Done", 80 * GB, 100.0, "/d/disk1/Films/Old (2019) [tmdbid-8]"),
                  _t("Elsewhere", 500 * GB, 0.0, "/d/disk2/Show/Saison 01")]
    )
    budget = DiskBudget(tr, _config({"movies": "/d/disk1/Films", "tv": "/d/disk2"}))
    assert await budget.has_room("/d/disk1/Films/Dune (2024) [tmdbid-1]", 55 * GB)  # 150-45-55 = 50
    assert not await budget.has_room("/d/disk1/Films/Dune (2024) [tmdbid-1]", 56 * GB)


async def test_budget_keeps_other_disks_apart():
    tr = BudgetTransmission({"/d/disk1/Films/A": 1900 * GB, "/d/disk2/S": 100 * GB})
    budget = DiskBudget(tr, _config({"movies": "/d/disk1/Films", "tv": "/d/disk2"}))
    budget.reserve("/d/disk1/Films/A", 500 * GB)
    assert await budget.has_room("/d/disk2/S", 40 * GB)


async def test_budget_unknown_space_or_threshold_zero_never_blocks():
    assert await DiskBudget(BudgetTransmission(), _config({"tv": "/d/disk2"})).has_room("/d/disk2/S", 999 * GB)
    tr = BudgetTransmission({"/d/disk2/S": 1 * GB})
    assert await DiskBudget(tr, _config({"tv": "/d/disk2"}, min_free_gb=0)).has_room("/d/disk2/S", 999 * GB)


async def test_budget_survives_a_failing_torrent_listing():
    class Broken(BudgetTransmission):
        async def list_torrents(self):
            raise RuntimeError("down")

    budget = DiskBudget(Broken({"/d/disk2/S": 100 * GB}), _config({"tv": "/d/disk2"}))
    assert await budget.has_room("/d/disk2/S", 40 * GB)


async def test_folder_usage_lists_default_folder_for_a_free_search_without_folder():
    from torsearch.config import SavedSearch
    from torsearch.models import Category

    tr = SpaceTransmission({"/d/disk1/Films": 1900 * GB, "/d/disk2": 600 * GB}, default=300 * GB)
    cfg = _config({"movies": "/d/disk1/Films", "tv": "/d/disk2"}).model_copy(
        update={"saved_searches": [SavedSearch(name="s", query="q", category=Category.ALL, mode="auto")]})
    assert [label for label, _, _ in await folder_usage(tr, cfg)] == ["Films", "Series", "Par defaut"]
