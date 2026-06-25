from __future__ import annotations

import logging

import httpx

from torsearch.config import NotificationChannel
from torsearch.monitor.history import MonitorRecord

logger = logging.getLogger(__name__)

_TITLE = "TorrSearch - surveillance"


def format_record(record: MonitorRecord) -> tuple[str, str]:
    kind = "grabbé" if record.kind == "grabbed" else "trouvé"
    body = f"{kind} · {record.search} : {record.title} ({record.source})"
    return _TITLE, body


class Notifier:
    def __init__(self, client_factory=httpx.AsyncClient, timeout: float = 10.0):
        self._client_factory = client_factory
        self._timeout = timeout

    async def _send_one(self, client, channel: NotificationChannel, title: str, body: str) -> None:
        if channel.type == "discord":
            response = await client.post(channel.url, json={"content": f"{title}\n{body}"})
        elif channel.type == "ntfy":
            response = await client.post(channel.url, content=body.encode("utf-8"), headers={"Title": title})
        elif channel.type == "telegram":
            url = f"https://api.telegram.org/bot{channel.token}/sendMessage"
            response = await client.post(url, json={"chat_id": channel.chat_id, "text": f"{title}\n{body}"})
        elif channel.type == "webhook":
            response = await client.post(channel.url, json={"title": title, "message": body})
        else:
            return
        response.raise_for_status()

    async def notify_message(self, channels: list[NotificationChannel], title: str, body: str) -> None:
        active = [c for c in channels if c.enabled]
        if not active:
            return
        client = self._client_factory(timeout=self._timeout)
        try:
            for channel in active:
                try:
                    await self._send_one(client, channel, title, body)
                except Exception as exc:
                    logger.warning("Notification to '%s' failed: %s", channel.name, exc)
        finally:
            await client.aclose()

    async def notify(self, channels: list[NotificationChannel], record: MonitorRecord) -> None:
        title, body = format_record(record)
        await self.notify_message(channels, title, body)

    async def test(self, channel: NotificationChannel) -> tuple[bool, str]:
        client = self._client_factory(timeout=self._timeout)
        try:
            await self._send_one(client, channel, _TITLE, "Notification de test depuis TorrSearch ✅")
            return True, "OK"
        except httpx.HTTPError as exc:
            return False, f"Echec : {exc}"
        finally:
            await client.aclose()
