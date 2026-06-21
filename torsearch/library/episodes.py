from __future__ import annotations

import re

_EP_RE = re.compile(r"s(\d{1,2})((?:[ ._-]*e\d{1,2})+)", re.IGNORECASE)
_E_NUM_RE = re.compile(r"e(\d{1,2})", re.IGNORECASE)
_SEASON_RE = re.compile(
    r"(?:s(\d{1,2})\b|season[ ._-]*(\d{1,2})|saison[ ._-]*(\d{1,2}))", re.IGNORECASE
)


def parse_episodes(title: str) -> set[str]:
    keys: set[str] = set()
    for m in _EP_RE.finditer(title):
        season = int(m.group(1))
        for em in _E_NUM_RE.finditer(m.group(2)):
            keys.add(f"S{season:02d}E{int(em.group(1)):02d}")
    if keys:
        return keys
    sm = _SEASON_RE.search(title)
    if sm:
        season = int(next(g for g in sm.groups() if g))
        return {f"S{season:02d}"}
    return set()
