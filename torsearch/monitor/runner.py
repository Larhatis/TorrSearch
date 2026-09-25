from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from torsearch.library.episodes import parse_episodes
from torsearch.models import Category, SearchResult
from torsearch.monitor.history import MonitorRecord
from torsearch.notifications.notifier import Notifier
from torsearch.search.decision import select_best_movie_release, select_series_releases
from torsearch.search.filters import ResultFilters, apply, detect_quality

logger = logging.getLogger(__name__)


def grab_key(result: SearchResult) -> str:
    return result.infohash or result.download_url


def select_new(results, filters, seen):
    for result in apply(results, filters):
        if grab_key(result) not in seen:
            return result
    return None



async def run_jellyfin_refresh(transmission, jellyfin, completed_seen: set[int]) -> set[int]:
    """Refresh Jellyfin once when a torrent has newly finished. Returns finished ids."""
    if jellyfin is None or not getattr(jellyfin, "enabled", False):
        return completed_seen
    try:
        torrents = await transmission.list_torrents()
    except Exception as exc:
        logger.warning("Jellyfin refresh: listing torrents failed: %s", exc)
        return completed_seen
    done = {t.id for t in torrents if t.percent >= 100.0}
    if done - completed_seen:
        try:
            await jellyfin.refresh()
        except Exception as exc:
            logger.warning("Jellyfin refresh failed: %s", exc)
    return done


async def run_cycle(config, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
    if not config.monitor.enabled:
        return []
    created: list[MonitorRecord] = []
    for saved in config.saved_searches:
        if not saved.enabled:
            continue
        try:
            results = await search_service.search(saved.query, saved.category)
        except Exception as exc:
            logger.warning("Monitor search '%s' failed: %s", saved.name, exc)
            continue
        filters = ResultFilters(
            min_seeders=saved.min_seeders, min_size=saved.min_size, max_size=saved.max_size,
            qualities=saved.qualities, exclude=saved.exclude, sort="seeders", direction="desc",
        )
        pick = select_new(results, filters, history.seen_keys(saved.name))
        if pick is None:
            continue
        if saved.mode == "auto":
            try:
                await transmission.add(pick.download_url)
            except Exception as exc:
                logger.warning("Monitor grab for '%s' failed: %s", saved.name, exc)
                continue
            kind = "grabbed"
        else:
            kind = "found"
        record = MonitorRecord(
            search=saved.name, title=pick.title, source=pick.source,
            infohash=pick.infohash, download_url=pick.download_url,
            kind=kind, at=datetime.now(UTC),
        )
        history.add(record)
        created.append(record)
        if notifier is not None:
            try:
                await notifier.notify(config.notifications, record)
            except Exception as exc:
                logger.warning("Notification for '%s' failed: %s", saved.name, exc)
    return created


def _movie_needs_grab(movie, jellyfin, owned_map, now, window) -> bool:
    """Whether a movie should be (re)hunted this cycle.

    Never grabbed -> yes. Grabbed: with Jellyfin as truth, an absent movie past the
    cooldown window means the download failed -> re-hunt; present or still in cooldown ->
    skip. Without Jellyfin we keep ``grabbed`` permanent (no truth source).
    """
    if movie.status != "grabbed":
        return True
    if jellyfin is None or not getattr(jellyfin, "enabled", False):
        return False
    if f"movie:{movie.tmdb_id}" in owned_map:
        return False
    if movie.grabbed_at is not None:
        at = movie.grabbed_at if movie.grabbed_at.tzinfo else movie.grabbed_at.replace(tzinfo=UTC)
        if now - at <= window:
            return False
    return True


async def _grab_movie(config, movie, pick, transmission, library, history, notifier, created) -> None:
    try:
        await transmission.add(pick.download_url, download_dir=config.paths.for_category(Category.MOVIES))
    except Exception as exc:
        logger.warning("Movie grab '%s' failed: %s", movie.title, exc)
        return
    now = datetime.now(UTC)
    library.mark_grabbed(movie.tmdb_id, pick.title, now)
    record = MonitorRecord(
        search=f"{movie.title} ({movie.year})", title=pick.title, source=pick.source,
        infohash=pick.infohash, download_url=pick.download_url, kind="grabbed", at=now,
    )
    history.add(record)
    created.append(record)
    if notifier is not None:
        try:
            await notifier.notify(config.notifications, record)
        except Exception as exc:
            logger.warning("Movie notif '%s' failed: %s", movie.title, exc)


async def run_movie_cycle(config, library, search_service, transmission, history,
                          notifier=None, jellyfin=None, blacklist=None) -> list[MonitorRecord]:
    if not config.monitor.enabled or library is None:
        return []
    profile = config.library
    created: list[MonitorRecord] = []
    owned_map: dict[str, str] = {}
    if jellyfin is not None and getattr(jellyfin, "enabled", False):
        try:
            owned_map = await jellyfin.owned()
        except Exception as exc:
            logger.warning("Jellyfin owned() failed: %s", exc)
    now = datetime.now(UTC)
    window = timedelta(hours=config.monitor.regrab_hours)
    for movie in library.list():
        needs = _movie_needs_grab(movie, jellyfin, owned_map, now, window)
        upgrade = not needs and profile.upgrades and movie.status == "grabbed"
        if not needs and not upgrade:
            continue

        if needs and movie.status == "grabbed" and movie.grabbed_title and blacklist is not None:
            # Re-hunt after timeout means the previous grab failed; blacklist it.
            blacklist.add(None, movie.grabbed_title, reason="failed_download")

        queries = [f"{movie.title} {movie.year or ''}".strip()]
        if movie.original_title and movie.original_title.strip():
            orig_q = f"{movie.original_title} {movie.year or ''}".strip()
            if orig_q != queries[0]:
                queries.append(orig_q)

        all_results: list[SearchResult] = []
        seen_keys: set[str] = set()
        for q in queries:
            try:
                res = await search_service.search(q, Category.MOVIES)
                for r in res:
                    key = r.infohash or r.download_url
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_results.append(r)
            except Exception as exc:
                logger.warning("Movie search '%s' failed: %s", q, exc)

        if needs:
            pick = select_best_movie_release(
                all_results,
                target_title=movie.title,
                target_original_title=movie.original_title,
                target_year=movie.year,
                qualities=profile.qualities,
                min_seeders=profile.min_seeders,
                blacklist=blacklist,
            )
            if pick is not None:
                await _grab_movie(config, movie, pick, transmission, library, history, notifier, created)
        else:
            # Upgrade: strictly better quality
            curr_q = detect_quality(movie.grabbed_title or "")
            best = select_best_movie_release(
                all_results,
                target_title=movie.title,
                target_original_title=movie.original_title,
                target_year=movie.year,
                qualities=profile.qualities,
                min_seeders=profile.min_seeders,
                blacklist=blacklist,
                current_quality=curr_q,
            )
            if best is not None:
                await _grab_movie(config, movie, best, transmission, library, history, notifier, created)
    return created


def _history_episodes(series, records, now, window):
    """(recent, historic) grabbed episodes for a series from the monitor history.

    ``recent`` = grabbed within the cooldown window (download likely still running);
    ``historic`` = every episode ever recorded as grabbed for this series.
    """
    recent: set[str] = set()
    historic: set[str] = set()
    for r in records:
        if r.search != series.title or r.kind != "grabbed":
            continue
        keys = parse_episodes(r.title)
        historic |= keys
        at = r.at if r.at.tzinfo else r.at.replace(tzinfo=UTC)
        if now - at <= window:
            recent |= keys
    return recent, historic


async def _series_have(series, jellyfin, owned_map, records, now, window) -> set[str]:
    """Episodes considered already on hand.

    With Jellyfin as source of truth: present-on-disk + recently-grabbed (cooldown) +
    legacy grabs (recorded before timestamps existed). An episode grabbed long ago but
    absent from Jellyfin drops out -> it gets re-chased. Without Jellyfin we keep the
    permanent ``series.grabbed`` (no truth source to confirm failures against).
    """
    if jellyfin is None or not getattr(jellyfin, "enabled", False):
        return set(series.grabbed)
    present: set[str] = set()
    item_id = owned_map.get(f"tv:{series.tmdb_id}")
    if item_id:
        try:
            present = await jellyfin.episodes(item_id)
        except Exception as exc:
            logger.warning("Jellyfin episodes for '%s' failed: %s", series.title, exc)
    recent, historic = _history_episodes(series, records, now, window)
    legacy = set(series.grabbed) - historic
    return present | recent | legacy


async def _series_aired(series, tmdb) -> set[str]:
    """Episodes already aired per TMDB, or empty when TMDB is unavailable."""
    if tmdb is None or not getattr(tmdb, "enabled", False):
        return set()
    try:
        return await tmdb.episodes(series.tmdb_id)
    except Exception as exc:
        logger.warning("TMDB episodes for '%s' failed: %s", series.title, exc)
        return set()


async def run_series_cycle(config, series_library, search_service, transmission, history,
                           notifier=None, jellyfin=None, tmdb=None, blacklist=None) -> list[MonitorRecord]:
    if not config.monitor.enabled or series_library is None:
        return []
    profile = config.library
    created: list[MonitorRecord] = []
    # Fetched once per cycle (not once per series): Jellyfin ownership map + grab log.
    owned_map: dict[str, str] = {}
    if jellyfin is not None and getattr(jellyfin, "enabled", False):
        try:
            owned_map = await jellyfin.owned()
        except Exception as exc:
            logger.warning("Jellyfin owned() failed: %s", exc)
    records = history.records()
    now = datetime.now(UTC)
    window = timedelta(hours=config.monitor.regrab_hours)
    for series in series_library.list():
        have = await _series_have(series, jellyfin, owned_map, records, now, window)
        aired = await _series_aired(series, tmdb)
        # Targeted mode: we know what aired -> only chase the real gaps.
        remaining = (aired - have) if aired else None
        if remaining is not None and not remaining:
            continue  # complete & up to date

        queries = [series.title.strip()]
        if series.original_title and series.original_title.strip():
            orig_q = series.original_title.strip()
            if orig_q != queries[0]:
                queries.append(orig_q)

        all_results: list[SearchResult] = []
        seen_keys: set[str] = set()
        for q in queries:
            try:
                res = await search_service.search(q, Category.TV)
                for r in res:
                    key = r.infohash or r.download_url
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_results.append(r)
            except Exception as exc:
                logger.warning("Series search '%s' failed: %s", q, exc)

        missing = set(remaining) if remaining is not None else None
        picks = select_series_releases(
            all_results,
            target_title=series.title,
            target_original_title=series.original_title,
            missing_episodes=missing,
            have_episodes=have,
            qualities=profile.qualities,
            min_seeders=profile.min_seeders,
            blacklist=blacklist,
        )

        newly: list[str] = []
        for r, covered in picks:
            if remaining is not None and not (covered & remaining):
                continue
            try:
                await transmission.add(r.download_url, download_dir=config.paths.for_category(Category.TV))
            except Exception as exc:
                logger.warning("Series grab '%s' failed: %s", series.title, exc)
                continue
            if remaining is not None:
                remaining -= covered
            have |= covered
            newly.extend(covered)
            now = datetime.now(UTC)
            record = MonitorRecord(
                search=series.title, title=r.title, source=r.source,
                infohash=r.infohash, download_url=r.download_url, kind="grabbed", at=now,
            )
            history.add(record)
            created.append(record)
            if notifier is not None:
                try:
                    await notifier.notify(config.notifications, record)
                except Exception as exc:
                    logger.warning("Series notif '%s' failed: %s", series.title, exc)
        if newly:
            series_library.mark_grabbed(series.tmdb_id, sorted(set(newly)))
    return created


class MonitorRunner:
    def __init__(self, ctx, history, notifier=None, library=None, series_library=None, blacklist=None):
        self._ctx = ctx
        self._history = history
        self._notifier = notifier or Notifier()
        self._library = library
        self._series_library = series_library
        self._blacklist = blacklist
        self._completed_seen: set[int] = set()
        self._task = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await run_cycle(
                    self._ctx.config, self._ctx.search_service, self._ctx.transmission,
                    self._history, self._notifier,
                )
                await run_movie_cycle(
                    self._ctx.config, self._library, self._ctx.search_service,
                    self._ctx.transmission, self._history, self._notifier,
                    jellyfin=getattr(self._ctx, "jellyfin", None),
                    blacklist=self._blacklist,
                )
                await run_series_cycle(
                    self._ctx.config, self._series_library, self._ctx.search_service,
                    self._ctx.transmission, self._history, self._notifier,
                    jellyfin=getattr(self._ctx, "jellyfin", None),
                    tmdb=getattr(self._ctx, "tmdb", None),
                    blacklist=self._blacklist,
                )
                self._completed_seen = await run_jellyfin_refresh(
                    self._ctx.transmission, getattr(self._ctx, "jellyfin", None),
                    self._completed_seen,
                )
            except Exception:
                logger.exception("Monitor cycle failed")
            interval = max(self._ctx.config.monitor.interval_minutes, 1) * 60
            await asyncio.sleep(interval)
