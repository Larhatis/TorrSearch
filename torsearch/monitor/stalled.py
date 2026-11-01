from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from torsearch.library.episodes import parse_episodes
from torsearch.monitor.grabs import AUTO
from torsearch.monitor.history import MonitorRecord

logger = logging.getLogger(__name__)

# More candidates than this in one cycle points at a network or VPN outage, not at dead
# releases: nothing is purged then.
MAX_PURGES_PER_CYCLE = 3

# Transmission error code for a local failure (disk full, permissions): another release
# would fail the same way, so it never justifies a purge.
_LOCAL_ERROR = 3

# A registry entry vouches for a torrent only if Transmission added it at that moment: adding a
# release that is already there (added by hand) returns the older, existing torrent.
SAME_ADD_TOLERANCE = timedelta(minutes=15)

# What trackers answer for a torrent they do not (or no longer) know.
_FORGOTTEN_MARKERS = (
    "unregistered", "not registered", "torrent not found", "unknown torrent", "does not exist",
    "not exist", "n'existe pas", "introuvable", "info_hash not found", "infohash not found",
)


def tracker_forgot_torrent(error_code: int, error_string: str) -> bool:
    """Whether Transmission's error says the tracker does not know this torrent any more."""
    if error_code == _LOCAL_ERROR or not error_string:
        return False
    message = error_string.lower()
    return any(marker in message for marker in _FORGOTTEN_MARKERS)


class DailyNotice:
    """Lets a recurring warning through once per day (kept in memory, per process)."""

    def __init__(self) -> None:
        self._last: date | None = None

    def allow(self, today: date) -> bool:
        if self._last == today:
            return False
        self._last = today
        return True


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _sent_by_surveillance(grabs, t) -> bool:
    """Whether the registry records ``t`` as chosen by the surveillance, added at that time."""
    record = grabs.get(t.info_hash) if t.info_hash else None
    if record is None or record.origin != AUTO or t.date_added is None:
        return False
    return abs(_aware(t.date_added) - _aware(record.added_at)) <= SAME_ADD_TOLERANCE


def _purge_reason(t, now: datetime, window: timedelta) -> str | None:
    """"stalled" or "error" when ``t`` is certainly dead, else None (never purge on doubt)."""
    # Only an active download is judged: not a finished, paused, queued or checking one.
    if t.percent >= 100.0 or t.status.lower() != "downloading":
        return None
    # Never judge a torrent whose age is unknown, nor one younger than the grace period: a
    # fresh torrent is at 0 % without peers while it fetches metadata.
    if t.date_added is None or now - _aware(t.date_added) < window:
        return None
    if t.down_rate > 0 or t.peers_sending > 0:
        return None  # still receiving data, whatever the tracker says
    if tracker_forgot_torrent(t.error_code, t.error_string):
        return "error"
    if t.percent == 0.0:
        return "stalled"
    return None


async def _notify_suspension(notifier, config, count: int) -> None:
    body = f"{count} torrents semblent bloques en meme temps (panne reseau ou VPN ?). Aucun n'a ete supprime."
    try:
        await notifier.notify_message(config.notifications, "Purge suspendue", body)
    except Exception as exc:
        logger.warning("Notification for suspended purge failed: %s", exc)


async def handle_stalled_torrents(
    transmission,
    library=None,
    series_library=None,
    blacklist=None,
    notifier=None,
    config=None,
    now: datetime | None = None,
    history=None,
    grabs=None,
    notice: DailyNotice | None = None,
) -> list[str]:
    """Purge the surveillance's own dead torrents, blacklist them, and reset library status.

    Purging deletes data, so it only happens when the surveillance is on, for torrents the
    grab registry records as chosen by the surveillance (never one added by hand), dead for
    sure (0 % without peers past the grace period, or forgotten by the tracker), and when
    few of them die at once.

    The purged grab is also removed from the monitor history: otherwise it would still
    count as "downloading" during the ``regrab_hours`` cooldown and delay the next try.
    """
    if transmission is None or config is None or not config.monitor.enabled or grabs is None:
        return []
    try:
        torrents = await transmission.list_torrents()
    except Exception as exc:
        logger.warning("Stalled check: listing torrents failed: %s", exc)
        return []

    window = timedelta(hours=config.monitor.stalled_hours)
    current_time = now or datetime.now(UTC)
    candidates = [
        (t, reason) for t in torrents
        if _sent_by_surveillance(grabs, t) and (reason := _purge_reason(t, current_time, window))
    ]
    if len(candidates) > MAX_PURGES_PER_CYCLE:
        logger.warning("Purge suspendue : %d torrents semblent bloques en meme temps (panne reseau ou VPN ?)",
                       len(candidates))
        if notifier is not None and (notice is None or notice.allow(current_time.date())):
            await _notify_suspension(notifier, config, len(candidates))
        return []

    handled: list[str] = []
    for t, reason in candidates:
        logger.info("Purging %s torrent '%s' (id=%s)", reason, t.name, t.id)

        # 1. Blacklist
        if blacklist is not None:
            blacklist.add(t.info_hash or None, t.name, reason=f"torrent_{reason}")

        # 2. Remove from Transmission
        try:
            await transmission.remove(t.id, delete_data=True)
        except Exception as exc:
            logger.warning("Failed to remove stalled torrent %s: %s", t.id, exc)

        # 3. Reset Movie Library if matching
        if library is not None:
            for m in library.list():
                if m.status == "grabbed" and m.grabbed_title:
                    if m.grabbed_title.strip().lower() == t.name.strip().lower():
                        library.unmark_grabbed(m.tmdb_id)
                        break

        # 4. Reset Series Library if matching
        if series_library is not None:
            from torsearch.parser.release import parse_release
            from torsearch.search.matcher import match_media_title

            parsed_keys = parse_episodes(t.name)
            seasons = {k for k in parsed_keys if len(k) == 3}  # season pack tags ("S01")
            for s in series_library.list():
                rel = parse_release(t.name)
                if match_media_title(rel, target_title=s.title, target_original_title=s.original_title, is_series=True):
                    keys_to_unmark = [
                        k for k in s.grabbed if k in parsed_keys or k[:3] in seasons
                    ]
                    if keys_to_unmark:
                        series_library.unmark_grabbed(s.tmdb_id, keys_to_unmark)

        # 5. Forget the grab in the history (no cooldown for a dead download)
        if history is not None and hasattr(history, "remove_where"):
            history.remove_where(lambda r, t=t: r.kind == "grabbed" and _same_release(r, t))

        # 6. Forget it in the registry
        grabs.forget(t.info_hash)

        # 7. Notify if configured
        if notifier is not None:
            record = MonitorRecord(
                search="Torrent purge",
                title=t.name,
                source="Transmission",
                download_url="",
                kind="failed",
                at=current_time,
            )
            try:
                await notifier.notify(config.notifications, record)
            except Exception as exc:
                logger.warning("Notification for purged torrent failed: %s", exc)

        handled.append(t.name)

    return handled


def _same_release(record: MonitorRecord, torrent) -> bool:
    """Whether a history record is the grab of ``torrent`` (tracker title and torrent name differ)."""
    from torsearch.parser.release import parse_release
    from torsearch.search.matcher import normalize_title

    if record.infohash and torrent.info_hash:
        return record.infohash.lower() == torrent.info_hash.lower()
    if record.title.strip().lower() == torrent.name.strip().lower():
        return True
    rec, tor = parse_release(record.title), parse_release(torrent.name)
    if not rec.clean_title or normalize_title(rec.clean_title) != normalize_title(tor.clean_title):
        return False
    if rec.episodes or tor.episodes:
        return rec.episodes == tor.episodes
    return rec.year == tor.year
