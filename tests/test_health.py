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
