from datetime import datetime, timezone

import httpx
import respx

from torsearch.config import NotificationChannel
from torsearch.monitor.history import MonitorRecord
from torsearch.notifications.notifier import Notifier, format_record


def _record(kind="grabbed"):
    return MonitorRecord(search="MaSerie", title="Show.S02E01.1080p", source="torr9",
                         infohash="H", download_url="magnet:?xt=urn:btih:H", kind=kind,
                         at=datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_format_record_grabbed_and_found():
    _, body = format_record(_record("grabbed"))
    assert "grabbé" in body and "MaSerie" in body and "Show.S02E01.1080p" in body
    _, body2 = format_record(_record("found"))
    assert "trouvé" in body2


async def test_send_discord_posts_content():
    ch = NotificationChannel(name="d", type="discord", url="https://discord/webhook")
    with respx.mock:
        route = respx.post("https://discord/webhook").mock(return_value=httpx.Response(204))
        await Notifier().notify([ch], _record())
    assert b"content" in route.calls.last.request.content


async def test_send_ntfy_posts_body_with_title_header():
    ch = NotificationChannel(name="n", type="ntfy", url="https://ntfy.sh/mytopic")
    with respx.mock:
        route = respx.post("https://ntfy.sh/mytopic").mock(return_value=httpx.Response(200))
        await Notifier().notify([ch], _record())
    req = route.calls.last.request
    assert req.headers.get("Title") is not None
    assert b"grab" in req.content


async def test_send_telegram_calls_bot_api():
    ch = NotificationChannel(name="t", type="telegram", token="BOT123", chat_id="42")
    with respx.mock:
        route = respx.post("https://api.telegram.org/botBOT123/sendMessage").mock(return_value=httpx.Response(200))
        await Notifier().notify([ch], _record())
    assert b"42" in route.calls.last.request.content


async def test_send_webhook_posts_title_and_message():
    ch = NotificationChannel(name="w", type="webhook", url="https://my/hook")
    with respx.mock:
        route = respx.post("https://my/hook").mock(return_value=httpx.Response(200))
        await Notifier().notify([ch], _record())
    body = route.calls.last.request.content
    assert b"title" in body and b"message" in body


async def test_notify_skips_disabled_and_survives_failure():
    good = NotificationChannel(name="good", type="webhook", url="https://good/hook")
    bad = NotificationChannel(name="bad", type="webhook", url="https://bad/hook")
    off = NotificationChannel(name="off", type="webhook", url="https://off/hook", enabled=False)
    with respx.mock:
        g = respx.post("https://good/hook").mock(return_value=httpx.Response(200))
        respx.post("https://bad/hook").mock(return_value=httpx.Response(500))
        o = respx.post("https://off/hook").mock(return_value=httpx.Response(200))
        await Notifier().notify([good, bad, off], _record())  # must not raise
    assert g.called
    assert not o.called


async def test_notify_message_posts_custom_title_body():
    ch = NotificationChannel(name="w", type="webhook", url="https://my/hook")
    with respx.mock:
        route = respx.post("https://my/hook").mock(return_value=httpx.Response(200))
        await Notifier().notify_message([ch], "Nouvelle demande", "Matrix (bob)")
    body = route.calls.last.request.content
    assert b"Nouvelle demande" in body and b"Matrix" in body


async def test_notify_message_noop_without_channels():
    # must not raise and not attempt any HTTP call
    await Notifier().notify_message([], "t", "b")


async def test_test_returns_ok_then_error():
    ch = NotificationChannel(name="d", type="discord", url="https://discord/webhook")
    with respx.mock:
        respx.post("https://discord/webhook").mock(return_value=httpx.Response(204))
        ok, msg = await Notifier().test(ch)
    assert ok is True and msg == "OK"
    with respx.mock:
        respx.post("https://discord/webhook").mock(return_value=httpx.Response(500))
        ok2, _ = await Notifier().test(ch)
    assert ok2 is False
