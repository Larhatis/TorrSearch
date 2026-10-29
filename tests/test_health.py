import asyncio

import httpx
import respx

from torsearch.config import Config, IndexerConfig, MetadataConfig, NotificationChannel
from torsearch.health import check_all


class _Service:
    def __init__(self, result=(True, "OK"), enabled=True, delay=0.0, error=None):
        self.enabled = enabled
        self._result, self._delay, self._error = result, delay, error

    async def test(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._result


class _Ctx:
    def __init__(self, config, transmission, jellyfin, tmdb):
        self.config, self.transmission, self.jellyfin, self.tmdb = config, transmission, jellyfin, tmdb


async def test_statuses_in_display_order_with_states():
    cfg = Config(
        metadata=MetadataConfig(tmdb_api_key="k"),
        indexers=[IndexerConfig(name="t1", url="https://t1.example/api", api_key="k"),
                  IndexerConfig(name="t2", url="https://t2.example/api", api_key="k", enabled=False)],
        notifications=[NotificationChannel(name="d", type="discord", url="https://x")],
    )
    ctx = _Ctx(cfg, _Service((True, "v4.0.6 · 3 torrents")), _Service((False, "Clé API refusée (401/403).")),
               _Service((True, "OK")))
    with respx.mock:
        respx.get("https://t1.example/api").mock(return_value=httpx.Response(200, content=b"<caps/>"))
        statuses = await check_all(ctx)
    assert [(s.name, s.state) for s in statuses] == [
        ("Transmission", "ok"), ("Jellyfin", "error"), ("TMDB", "ok"),
        ("t1", "ok"), ("t2", "off"), ("Notifications", "off"),
    ]
    assert statuses[0].message == "OK · v4.0.6 · 3 torrents"
    assert statuses[2].message == "OK"
    assert "test manuel" in statuses[5].message


async def test_unconfigured_services_are_off():
    ctx = _Ctx(Config(), _Service(), _Service(enabled=False), _Service(enabled=False))
    statuses = await check_all(ctx)
    assert [(s.name, s.state, s.message) for s in statuses[1:]] == [
        ("Jellyfin", "off", "Non configuré"), ("TMDB", "off", "Non configuré"),
    ]


async def test_tmdb_key_from_environment_is_flagged():
    ctx = _Ctx(Config(), _Service(), _Service(enabled=False), _Service((True, "OK")))  # no stored key
    statuses = await check_all(ctx)
    assert statuses[2].message == "OK · via TMDB_API_KEY"


async def test_a_hanging_service_times_out():
    ctx = _Ctx(Config(), _Service(delay=1.0), _Service(enabled=False), _Service(enabled=False))
    statuses = await check_all(ctx, timeout=0.05)
    assert (statuses[0].state, statuses[0].message) == ("error", "Pas de réponse (délai dépassé).")


async def test_an_unexpected_exception_is_masked():
    boom = RuntimeError("Invalid URL 'http://u:TR-SECRET@:9091/transmission/rpc'")
    ctx = _Ctx(Config(), _Service(error=boom), _Service(enabled=False), _Service(enabled=False))
    statuses = await check_all(ctx)
    assert statuses[0].state == "error" and "TR-SECRET" not in statuses[0].message


def test_folder_covered_across_container_mounts():
    from torsearch.health import folder_covered

    libs = ["/media/disk1/Series", "/media/disk2", "/media/disk1/Films"]
    assert folder_covered("/downloads/disk1/Films", libs)
    assert folder_covered("/downloads/disk2", libs)
    assert folder_covered("/downloads/disk1/Films/Nouveaux/", libs)  # inside a library
    assert not folder_covered("/downloads/disk1", libs)  # root of the disk: outside "Films"
    assert not folder_covered("/downloads/Films", libs)  # same last name, different disk


class _Jelly(_Service):
    def __init__(self, folders):
        super().__init__()
        self._folders = folders

    async def library_folders(self):
        return self._folders


async def test_folders_check_flags_paths_outside_jellyfin():
    from torsearch.config import PathsConfig

    folders = [("Movies", None, ["/media/disk1/Films"]), ("Shows", "tvshows", ["/media/disk2"]),
               ("Collections", "boxsets", ["/config/data/collections"])]
    cfg = Config(paths=PathsConfig(by_category={"movies": "/downloads/disk1", "tv": "/downloads/disk2"}))
    statuses = await check_all(_Ctx(cfg, _Service(), _Jelly(folders), _Service(enabled=False)))
    check = next(s for s in statuses if s.name == "Dossiers")
    assert check.state == "error"
    assert "Films (/downloads/disk1)" in check.message

    cfg = Config(paths=PathsConfig(by_category={"movies": "/downloads/disk1/Films", "tv": "/downloads/disk2"}))
    statuses = await check_all(_Ctx(cfg, _Service(), _Jelly(folders), _Service(enabled=False)))
    assert next(s for s in statuses if s.name == "Dossiers").state == "ok"


async def test_folders_check_absent_without_jellyfin():
    statuses = await check_all(_Ctx(Config(), _Service(), _Service(enabled=False), _Service(enabled=False)))
    assert all(s.name != "Dossiers" for s in statuses)
