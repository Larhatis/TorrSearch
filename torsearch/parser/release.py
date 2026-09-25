from __future__ import annotations

import re
from dataclasses import dataclass, field

from torsearch.library.episodes import parse_episodes

# Delimiters and token patterns
_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")

_SEASON_EP_MARKER_RE = re.compile(
    r"\b(?:s\d{1,2}(?:[ ._-]*e\d{1,2})?|season[ ._-]*\d{1,2}|saison[ ._-]*\d{1,2})\b",
    re.IGNORECASE,
)

_RESOLUTION_PATTERNS = [
    ("2160p", re.compile(r"\b(2160p|4k|uhd)\b", re.IGNORECASE)),
    ("1080p", re.compile(r"\b(1080p|1080i)\b", re.IGNORECASE)),
    ("720p", re.compile(r"\b720p\b", re.IGNORECASE)),
    ("480p", re.compile(r"\b(480p|576p|sd)\b", re.IGNORECASE)),
]

_BANNED_SOURCES = [
    ("cam", re.compile(r"\b(cam|camrip|hdcam)\b", re.IGNORECASE)),
    ("ts", re.compile(r"\b(ts|telesync|hdts|pdvd)\b", re.IGNORECASE)),
    ("tc", re.compile(r"\b(tc|telecine|hdtc)\b", re.IGNORECASE)),
    ("screener", re.compile(r"\b(dvdscr|scr|screener)\b", re.IGNORECASE)),
]

_CLEAN_SOURCES = [
    ("bluray", re.compile(r"\b(bluray|bdrip|brrip)\b", re.IGNORECASE)),
    ("web-dl", re.compile(r"\b(web[-._]?dl)\b", re.IGNORECASE)),
    ("webrip", re.compile(r"\b(web[-._]?rip|web)\b", re.IGNORECASE)),
    ("hdtv", re.compile(r"\b(hdtv|pdtv|dsr)\b", re.IGNORECASE)),
    ("dvdrip", re.compile(r"\b(dvdrip|dvd)\b", re.IGNORECASE)),
]

_LANGUAGE_PATTERNS = [
    ("multi", re.compile(r"\b(multi(?:lang)?)\b", re.IGNORECASE)),
    ("vff", re.compile(r"\b(truefrench|vff)\b", re.IGNORECASE)),
    ("vfq", re.compile(r"\b(vfq)\b", re.IGNORECASE)),
    ("vf", re.compile(r"\b(french|vf|vof)\b", re.IGNORECASE)),
    ("vostfr", re.compile(r"\b(vostfr|subfrench)\b", re.IGNORECASE)),
    ("vo", re.compile(r"\b(english|eng|vo)\b", re.IGNORECASE)),
]

_CODEC_PATTERNS = [
    ("h265", re.compile(r"\b(h[-._]?265)\b", re.IGNORECASE)),
    ("x265", re.compile(r"\b(x265|hevc)\b", re.IGNORECASE)),
    ("h264", re.compile(r"\b(h[-._]?264)\b", re.IGNORECASE)),
    ("x264", re.compile(r"\b(x264|avc)\b", re.IGNORECASE)),
    ("av1", re.compile(r"\b(av1)\b", re.IGNORECASE)),
    ("xvid", re.compile(r"\b(xvid|divx)\b", re.IGNORECASE)),
]

_EDITION_PATTERNS = [
    ("remux", re.compile(r"\b(remux)\b", re.IGNORECASE)),
    ("proper", re.compile(r"\b(proper)\b", re.IGNORECASE)),
    ("repack", re.compile(r"\b(repack)\b", re.IGNORECASE)),
    ("extended", re.compile(r"\b(extended)\b", re.IGNORECASE)),
]


@dataclass(frozen=True)
class ParsedRelease:
    raw_title: str
    clean_title: str
    year: int | None = None
    episodes: set[str] = field(default_factory=set)
    resolution: str = "unknown"
    source: str = "other"
    is_banned_source: bool = False
    language: str = "unknown"
    codec: str = "unknown"
    edition: str | None = None


def parse_release(raw_title: str) -> ParsedRelease:
    """Parse a torrent release title into structured metadata."""
    title_work = raw_title.strip()

    # 1. Episodes
    episodes = parse_episodes(title_work)

    # 2. Year
    year_match = _YEAR_RE.search(title_work)
    year = int(year_match.group(1)) if year_match else None

    # 3. Resolution
    resolution = "unknown"
    res_pos = None
    for label, pat in _RESOLUTION_PATTERNS:
        m = pat.search(title_work)
        if m:
            resolution = label
            res_pos = m.start()
            break

    # 4. Source & Banned check
    source = "other"
    is_banned = False
    source_pos = None
    for label, pat in _BANNED_SOURCES:
        m = pat.search(title_work)
        if m:
            source = label
            is_banned = True
            source_pos = m.start()
            break
    if not is_banned:
        for label, pat in _CLEAN_SOURCES:
            m = pat.search(title_work)
            if m:
                source = label
                source_pos = m.start()
                break

    # 5. Language
    language = "unknown"
    lang_pos = None
    for label, pat in _LANGUAGE_PATTERNS:
        m = pat.search(title_work)
        if m:
            language = label
            lang_pos = m.start()
            break

    # 6. Codec
    codec = "unknown"
    codec_pos = None
    for label, pat in _CODEC_PATTERNS:
        m = pat.search(title_work)
        if m:
            codec = label
            codec_pos = m.start()
            break

    # 7. Edition
    edition = None
    edition_pos = None
    for label, pat in _EDITION_PATTERNS:
        m = pat.search(title_work)
        if m:
            edition = label
            edition_pos = m.start()
            break

    # 8. Clean title extraction:
    # Delimiters that mark the end of the title:
    # Season/Episode marker, Year, Resolution, Source, Language, Codec, Edition
    delimiters = []
    sm = _SEASON_EP_MARKER_RE.search(title_work)
    if sm and sm.start() > 0:
        delimiters.append(sm.start())
    if year_match and year_match.start() > 0:
        delimiters.append(year_match.start())
    if res_pos is not None and res_pos > 0:
        delimiters.append(res_pos)
    if source_pos is not None and source_pos > 0:
        delimiters.append(source_pos)
    if lang_pos is not None and lang_pos > 0:
        delimiters.append(lang_pos)
    if codec_pos is not None and codec_pos > 0:
        delimiters.append(codec_pos)
    if edition_pos is not None and edition_pos > 0:
        delimiters.append(edition_pos)

    if delimiters:
        cutoff = min(delimiters)
        clean = title_work[:cutoff]
    else:
        # Fallback: remove group tag at end if preceded by dash
        if "-" in title_work:
            clean = title_work.rsplit("-", 1)[0]
        else:
            clean = title_work

    # Normalize clean title: replace dots, underscores, dashes with spaces
    clean = re.sub(r"[._\-+]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    return ParsedRelease(
        raw_title=raw_title,
        clean_title=clean,
        year=year,
        episodes=episodes,
        resolution=resolution,
        source=source,
        is_banned_source=is_banned,
        language=language,
        codec=codec,
        edition=edition,
    )
