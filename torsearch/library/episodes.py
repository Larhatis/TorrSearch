from __future__ import annotations

import re

# An episode segment after Sxx: one or more e-tokens, each optionally a range
# (eNN-eMM or eNN-MM). The (?!\d) stops a trailing resolution like "-1080p" being
# read as a range up to E10.
_SEASON_EP_RE = re.compile(
    r"s(\d{1,2})((?:[ ._-]*e\d{1,2}(?:\s*-\s*e?\d{1,2}(?!\d))?)+)", re.IGNORECASE
)
_EP_TOKEN_RE = re.compile(r"e(\d{1,2})(?:\s*-\s*e?(\d{1,2}))?", re.IGNORECASE)
_SEASON_RE = re.compile(
    r"(?:s(\d{1,2})\b|season[ ._-]*(\d{1,2})|saison[ ._-]*(\d{1,2}))", re.IGNORECASE
)


def parse_episodes(title: str) -> set[str]:
    keys: set[str] = set()
    for m in _SEASON_EP_RE.finditer(title):
        season = int(m.group(1))
        for tok in _EP_TOKEN_RE.finditer(m.group(2)):
            start = int(tok.group(1))
            end = int(tok.group(2)) if tok.group(2) else start
            if end < start:
                end = start  # inverted range -> single episode
            for ep in range(start, end + 1):
                keys.add(f"S{season:02d}E{ep:02d}")
    if keys:
        return keys
    sm = _SEASON_RE.search(title)
    if sm:
        season = int(next(g for g in sm.groups() if g))
        return {f"S{season:02d}"}
    return set()
