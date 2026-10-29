from __future__ import annotations

import re
from dataclasses import dataclass, field

from torsearch.parser.release import ParsedRelease, parse_release
from torsearch.redact import redact
from torsearch.search.decision import _get_lang_tier
from torsearch.search.matcher import normalize_title
from torsearch.transmission.client import TorrentInfo

_RESOLUTION_ORDER = ["2160p", "1080p", "720p", "480p"]

# Names that are never grouped: partial packs, multi-movie or bonus content. Deleting one
# of them "because a better copy exists" would lose files no other copy holds.
_NEVER_GROUP_RE = re.compile(
    r"\b(?:part(?:ie)?|vol(?:ume)?|pt)[ ._-]*\d"
    r"|\b(?:19|20)\d\d[ ._]*-[ ._]*(?:19|20)\d\d\b"
    r"|\b(?:trilog(?:y|ie)|integrale?|complete[ ._]series|collection|saga|coffret|bonus|extras?"
    r"|ost|soundtrack|making[ ._]of)\b",
    re.IGNORECASE,
)
# A different cut is another work for the user, not a copy.
_EDITION_RE = re.compile(r"\b(extended|director'?s?[ ._]cut|uncut|unrated)\b", re.IGNORECASE)


@dataclass
class Copy:
    torrent: TorrentInfo
    parsed: ParsedRelease
    remove: bool = False  # proposed for removal
    shares_files: bool = False  # same name as another copy: files probably shared on disk

    @property
    def usable(self) -> bool:
        """Complete with its files intact: the only copies allowed to justify a removal.

        A tracker error ("invalid passkey", code 2) leaves the local files fine; a local
        error (code 3, e.g. data not found) does not.
        """
        return self.torrent.percent >= 100.0 and self.torrent.error_code != 3

    @property
    def path(self) -> str:
        """Where the torrent's data lives (file or top folder), lowercased for comparisons."""
        return f"{self.torrent.download_dir.rstrip('/')}/{self.torrent.name.strip()}".lower()

    def shares_path_with(self, other: Copy) -> bool:
        a, b = self.path, other.path
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")

    @property
    def resolution(self) -> str:
        return self.parsed.resolution if self.parsed.resolution != "unknown" else "?"

    @property
    def language(self) -> str:
        return self.parsed.language.upper() if self.parsed.language != "unknown" else "?"


@dataclass
class DuplicateGroup:
    title: str
    scope: str  # year of the movie, or the seasons/episodes involved
    items: list[Copy] = field(default_factory=list)

    @property
    def removable(self) -> list[Copy]:
        return [c for c in self.items if c.remove]


def _quality_key(c: Copy) -> tuple:
    """Best first: better language, better resolution, bigger file."""
    p = c.parsed
    res = _RESOLUTION_ORDER.index(p.resolution) if p.resolution in _RESOLUTION_ORDER else len(_RESOLUTION_ORDER)
    return (_get_lang_tier(p.language), res, -c.torrent.size)


def units(p: ParsedRelease) -> set[str]:
    return set(p.episodes) if p.episodes else {"movie"}


def _covered(unit: str, kept: set[str]) -> bool:
    """A unit is covered by what is kept: same key, or a season pack holding the episode."""
    return unit in kept or (len(unit) > 3 and unit[:3] in kept)


def _overlap(a: set[str], b: set[str]) -> bool:
    return any(_covered(u, b) for u in a) or any(_covered(u, a) for u in b)


def _root(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _identity(t: TorrentInfo) -> tuple[str, ParsedRelease] | None:
    """Grouping key of a torrent, or None when it must never be grouped."""
    if _NEVER_GROUP_RE.search(t.name):
        return None
    p = parse_release(t.name)
    if not p.clean_title:
        return None
    if not p.episodes and p.year is None:
        return None  # a movie without year: a remake would look identical
    edition = _EDITION_RE.search(t.name)
    # The year is part of a show's identity too (Doctor Who 2005 / 2023, Charmed / Charmed 2018).
    key = f"{normalize_title(p.clean_title)}|{p.year or ''}|{edition.group(1).lower() if edition else ''}"
    return ("tv|" if p.episodes else "movie|") + key, p


def find_duplicates(torrents: list[TorrentInfo]) -> list[DuplicateGroup]:
    """Groups of torrents holding the same movie or the same episodes.

    Conservative by design, since removal deletes files: same title, same year, same cut;
    partial packs, collections and bonus content are left out. Only complete copies without
    error can make another copy removable, a pack is preferred to the episodes it holds,
    and a copy sharing its name with another is never proposed (same files on disk).
    """
    by_key: dict[str, list[Copy]] = {}
    for t in torrents:
        ident = _identity(t)
        if ident is not None:
            by_key.setdefault(ident[0], []).append(Copy(t, ident[1]))

    groups: list[DuplicateGroup] = []
    for copies in by_key.values():
        if len(copies) < 2:
            continue
        parent = list(range(len(copies)))
        for i in range(len(copies)):
            for j in range(i + 1, len(copies)):
                if _overlap(units(copies[i].parsed), units(copies[j].parsed)):
                    parent[_root(parent, i)] = _root(parent, j)
        clusters: dict[int, list[Copy]] = {}
        for i, c in enumerate(copies):
            clusters.setdefault(_root(parent, i), []).append(c)
        groups.extend(_build_group(m) for m in clusters.values() if len(m) >= 2)
    groups.sort(key=lambda g: g.title.lower())
    return groups


def _build_group(members: list[Copy]) -> DuplicateGroup:
    # Usable copies first, then wider coverage (packs before episodes), then quality.
    members.sort(key=lambda c: (not c.usable, -sum(1 for u in units(c.parsed) if len(u) == 3),
                                _quality_key(c)))
    kept: set[str] = set()
    kept_copies: list[Copy] = []
    for c in members:
        covered = all(_covered(u, kept) for u in units(c.parsed))
        if covered and any(_same_files(c, k) for k in kept_copies):
            c.shares_files = True  # never proposed: deleting would wipe the kept copy's files
        elif covered:
            c.remove = True
        elif c.usable:
            kept |= units(c.parsed)
            kept_copies.append(c)
    best = members[0].parsed
    scope = (", ".join(sorted({u for c in members for u in units(c.parsed)}))
             if best.episodes else str(best.year))
    return DuplicateGroup(title=best.clean_title, scope=scope, items=members)


def _same_files(a: Copy, b: Copy) -> bool:
    """Same name, or one copy's data inside the other's folder: deleting one hits both."""
    return a.torrent.name.strip().lower() == b.torrent.name.strip().lower() or a.shares_path_with(b)


def removal_is_safe(group: DuplicateGroup, removed_hashes: set[str]) -> str | None:
    """Why removing these copies would lose content, or None when it is safe.

    Everything the group's usable copies cover must stay covered by the remaining usable
    copies, and a copy whose name another remaining copy shares cannot be deleted.
    """
    remaining = [c for c in group.items if c.torrent.info_hash not in removed_hashes]
    if not remaining:
        return "garde au moins une copie"
    before = {u for c in group.items if c.usable for u in units(c.parsed)}
    after: set[str] = {u for c in remaining if c.usable for u in units(c.parsed)}
    if not all(_covered(u, after) for u in before):
        return "des episodes ne seraient plus couverts par aucune copie terminee"
    removed = [c for c in group.items if c.torrent.info_hash in removed_hashes]
    if any(_same_files(r, k) for r in removed for k in remaining):
        return "une copie partage ses fichiers avec une copie gardee"
    return None


def error_groups(torrents: list[TorrentInfo]) -> list[tuple[str, list[TorrentInfo]]]:
    """Torrents in error, grouped by (masked) message, biggest group first.

    Transient tracker *warnings* (Transmission error code 1, e.g. a tracker briefly down) are
    left out: removing hundreds of seeding torrents for an outage would be a mistake.
    """
    groups: dict[str, list[TorrentInfo]] = {}
    for t in torrents:
        if t.error_string and t.error_code != 1:
            groups.setdefault(redact(t.error_string), []).append(t)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
