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


def covered_episodes(keys: set[str], wanted: set[str]) -> set[str]:
    """Episode keys from ``wanted`` that a torrent (its parsed ``keys``) satisfies.

    ``keys`` may hold episode keys (``S01E02``) or a season key (``S01``); a season
    key covers every wanted episode of that season.
    """
    out: set[str] = set()
    for key in keys:
        if "E" in key:
            if key in wanted:
                out.add(key)
        else:
            out |= {ep for ep in wanted if ep.startswith(key + "E")}
    return out


_INVALID_CHARS_RE = re.compile(r'[/\\?%*:|"<>]')
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_folder_name(name: str) -> str:
    """Clean a title to be safe as a directory name on Linux, Windows, and macOS."""
    cleaned = _INVALID_CHARS_RE.sub("", name)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" .")
    return cleaned or "Unknown"


def extract_season_number(
    episodes: set[str] | list[str] | None = None,
    title: str | None = None,
) -> int | None:
    """Return the single season number if all tokens/episodes belong to the same season.

    If episodes span multiple distinct seasons or none is found, returns None.
    """
    seasons: set[int] = set()
    if episodes:
        for ep in episodes:
            m = re.search(r"S(\d{1,2})", ep, re.IGNORECASE)
            if m:
                seasons.add(int(m.group(1)))
    if not seasons and title:
        parsed_eps = parse_episodes(title)
        for ep in parsed_eps:
            m = re.search(r"S(\d{1,2})", ep, re.IGNORECASE)
            if m:
                seasons.add(int(m.group(1)))
    if len(seasons) == 1:
        return next(iter(seasons))
    return None


def build_tv_download_dir(
    base_dir: str | None,
    series_title: str,
    episodes: set[str] | list[str] | None = None,
    release_title: str | None = None,
    season_number: int | None = None,
) -> str | None:
    """Build the structured download path for a TV series episode or season.

    Example:
    base_dir="/downloads/disk2", series_title="Paolo", episodes={"S01E01"}
    -> "/downloads/disk2/Paolo/Saison 01"

    If multiple seasons are included:
    base_dir="/downloads/disk2", series_title="Paolo", episodes={"S01", "S02"}
    -> "/downloads/disk2/Paolo"
    """
    clean_series = sanitize_folder_name(series_title)
    s_num = season_number if season_number is not None else extract_season_number(episodes, release_title)

    if s_num is not None:
        sub_path = f"{clean_series}/Saison {s_num:02d}"
    else:
        sub_path = clean_series

    if not base_dir:
        return sub_path

    clean_base = base_dir.rstrip("/\\")
    return f"{clean_base}/{sub_path}"
