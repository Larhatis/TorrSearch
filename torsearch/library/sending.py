from __future__ import annotations

import logging
from dataclasses import dataclass

from torsearch.library.episodes import build_tv_download_dir
from torsearch.library.linking import plan_manual_grab, record_manual_grab
from torsearch.library.series_folder import choose_series_folder, remember_folder
from torsearch.models import Category
from torsearch.monitor.diskspace import format_bytes, free_bytes
from torsearch.monitor.grabs import MANUAL, added_hash
from torsearch.redact import redact

logger = logging.getLogger(__name__)


@dataclass
class SendOutcome:
    ok: bool
    message: str
    torrent_id: int | None = None


async def send_release(state, download_url: str, title: str, category: Category,
                       fallback_hash: str | None = None) -> SendOutcome:
    """Send a release chosen by a person (web UI or Claude) to Transmission.

    Files it like the surveillance would (movie folder or ``Series/Season XX``), records it
    as manual in the grab registry (never purged automatically) and marks it in the
    surveillance when it belongs to a watched work. ``state`` is the app state (or any object
    with ``ctx``, ``library``, ``series_library``, ``history`` and ``grabs``).
    """
    ctx = state.ctx
    library = getattr(state, "library", None)
    series_library = getattr(state, "series_library", None)
    grab = plan_manual_grab(title, category, ctx.config.paths, library, series_library)
    choice = None
    if grab.series is not None:
        # A followed show goes where it already lives (see library/series_folder.py).
        base = ctx.config.paths.for_category(Category.TV)
        choice = await choose_series_folder(grab.series, base, getattr(ctx, "jellyfin", None),
                                            getattr(ctx, "transmission", None))
        if choice:
            grab.download_dir = build_tv_download_dir(base, grab.series.title, grab.parsed.episodes,
                                                      release_title=title, series_dir=choice.path)
    try:
        added = await ctx.transmission.add(download_url, grab.download_dir)
    except Exception as exc:
        return SendOutcome(False, f"Erreur Transmission : {redact(str(exc))}")
    outcome = SendOutcome(True, f"Ajoute a Transmission (#{added.id})", added.id)
    if grab.series is not None:
        remember_folder(series_library, grab.series, choice)
    grabs = getattr(state, "grabs", None)
    if grabs is not None:
        try:
            # A release picked by hand is never purged automatically, even if it stalls.
            grabs.record(added_hash(added) or (fallback_hash or ""), title, MANUAL)
        except Exception as exc:  # the torrent is added: never turn that into an error
            logger.warning("Recording manual grab '%s' failed: %s", title, exc)
    if grab.watched_title:
        try:
            record_manual_grab(grab, download_url, library, series_library, getattr(state, "history", None))
            outcome.message += f" · marque acquis dans la surveillance ({grab.watched_title})"
        except Exception as exc:  # the torrent is added: never turn that into an error
            logger.warning("Manual grab bookkeeping for '%s' failed: %s", title, exc)
    min_free = ctx.config.library.min_free_bytes
    if min_free:
        free = await free_bytes(ctx.transmission, grab.download_dir)
        if free is not None and free < min_free:  # a person chose it: warn, never block
            outcome.message += f" · attention : disque presque plein ({format_bytes(free)} libres)"
    return outcome
