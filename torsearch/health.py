from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Literal

from pydantic import BaseModel

from torsearch.indexers.torznab import TorznabIndexer
from torsearch.redact import redact


class ServiceStatus(BaseModel):
    name: str
    state: Literal["ok", "error", "off"]
    message: str


async def _probe(name: str, check: Awaitable[tuple[bool, str]], timeout: float) -> ServiceStatus:
    """Run one ``test()``; a slow or broken service never breaks the panel."""
    try:
        ok, detail = await asyncio.wait_for(check, timeout)
    except TimeoutError:
        return ServiceStatus(name=name, state="error", message="Pas de réponse (délai dépassé).")
    except Exception as exc:
        return ServiceStatus(name=name, state="error", message=redact(str(exc)))
    if not ok:
        return ServiceStatus(name=name, state="error", message=detail)
    return ServiceStatus(name=name, state="ok", message="OK" if detail in ("", "OK") else f"OK · {detail}")


async def _fixed(status: ServiceStatus) -> ServiceStatus:
    return status


async def _tmdb_test(ctx) -> tuple[bool, str]:
    ok, detail = await ctx.tmdb.test()
    if ok and not ctx.config.metadata.tmdb_api_key:
        return ok, "via TMDB_API_KEY"  # stored key empty: the environment fallback is in use
    return ok, detail


async def check_all(ctx, timeout: float = 12.0) -> list[ServiceStatus]:
    """Check every external service in parallel; statuses come back in display order."""
    config = ctx.config
    off = "Non configuré"
    checks: list[Awaitable[ServiceStatus]] = [
        _probe("Transmission", ctx.transmission.test(), timeout),
        _probe("Jellyfin", ctx.jellyfin.test(), timeout) if ctx.jellyfin.enabled
        else _fixed(ServiceStatus(name="Jellyfin", state="off", message=off)),
        _probe("TMDB", _tmdb_test(ctx), timeout) if ctx.tmdb.enabled
        else _fixed(ServiceStatus(name="TMDB", state="off", message=off)),
    ]
    for ix in config.indexers:
        if ix.enabled:
            indexer = TorznabIndexer(ix, timeout=config.search.timeout_seconds)
            checks.append(_probe(ix.name, indexer.test(), timeout))
        else:
            checks.append(_fixed(ServiceStatus(name=ix.name, state="off", message="Désactivé")))
    if config.notifications:
        n = len(config.notifications)
        label = f"{n} canal{'aux' if n > 1 else ''} · test manuel dans la section Notifications"
        checks.append(_fixed(ServiceStatus(name="Notifications", state="off", message=label)))
    return list(await asyncio.gather(*checks))
