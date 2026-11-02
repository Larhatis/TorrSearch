from __future__ import annotations

import logging
from dataclasses import dataclass

from torsearch.library.linking import plan_manual_grab, record_manual_grab
from torsearch.models import Category
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
    try:
        added = await ctx.transmission.add(download_url, grab.download_dir)
    except Exception as exc:
        return SendOutcome(False, f"Erreur Transmission : {redact(str(exc))}")
    outcome = SendOutcome(True, f"Ajoute a Transmission (#{added.id})", added.id)
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
    return outcome
