from __future__ import annotations

from dataclasses import dataclass, field

from torsearch.parser.release import ParsedRelease, parse_release
from torsearch.redact import redact
from torsearch.search.decision import _get_lang_tier
from torsearch.search.matcher import normalize_title
from torsearch.transmission.client import TorrentInfo

_RESOLUTION_ORDER = ["2160p", "1080p", "720p", "480p"]


@dataclass
class Copy:
    torrent: TorrentInfo
    parsed: ParsedRelease
    remove: bool = False  # recommended for removal

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
    """Best first: complete, no error, better language, better resolution, bigger file."""
    t, p = c.torrent, c.parsed
    res = _RESOLUTION_ORDER.index(p.resolution) if p.resolution in _RESOLUTION_ORDER else len(_RESOLUTION_ORDER)
    return (t.percent < 100.0, bool(t.error_string), _get_lang_tier(p.language), res, -t.size)


def _units(p: ParsedRelease) -> set[str]:
    return {k for k in p.episodes} if p.episodes else {"movie"}


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


def find_duplicates(torrents: list[TorrentInfo]) -> list[DuplicateGroup]:
    """Groups of torrents holding the same movie or the same episodes.

    A movie is identified by its title *and* year (a movie without year is never grouped:
    a remake would look identical). Episodes overlap when they share an episode, or when a
    season pack contains it. In each group the copies are sorted best first and those that
    add nothing to the better ones are marked for removal; a pack is kept over the single
    episodes it contains.
    """
    by_title: dict[str, list[Copy]] = {}
    for t in torrents:
        p = parse_release(t.name)
        if not p.clean_title or (not p.episodes and p.year is None):
            continue
        key = normalize_title(p.clean_title) + ("" if p.episodes else f"|{p.year}")
        by_title.setdefault(key, []).append(Copy(t, p))

    groups: list[DuplicateGroup] = []
    for copies in by_title.values():
        if len(copies) < 2:
            continue
        # Union-find on overlapping coverage.
        parent = list(range(len(copies)))
        for i in range(len(copies)):
            for j in range(i + 1, len(copies)):
                if _overlap(_units(copies[i].parsed), _units(copies[j].parsed)):
                    parent[_root(parent, i)] = _root(parent, j)
        clusters: dict[int, list[Copy]] = {}
        for i, c in enumerate(copies):
            clusters.setdefault(_root(parent, i), []).append(c)
        for members in clusters.values():
            if len(members) >= 2:
                groups.append(_build_group(members))
    groups.sort(key=lambda g: g.title.lower())
    return groups


def _build_group(members: list[Copy]) -> DuplicateGroup:
    # Wider coverage first (season packs before single episodes), then quality.
    members.sort(key=lambda c: (-sum(1 for u in _units(c.parsed) if len(u) == 3), _quality_key(c)))
    kept: set[str] = set()
    for c in members:
        units = _units(c.parsed)
        if all(_covered(u, kept) for u in units):
            c.remove = True
        else:
            kept |= units
    best = members[0].parsed
    if best.episodes:
        scope = ", ".join(sorted({u for c in members for u in _units(c.parsed)}))
    else:
        scope = str(best.year)
    return DuplicateGroup(title=best.clean_title, scope=scope, items=members)


def error_groups(torrents: list[TorrentInfo]) -> list[tuple[str, list[TorrentInfo]]]:
    """Torrents in error, grouped by (masked) message, biggest group first."""
    groups: dict[str, list[TorrentInfo]] = {}
    for t in torrents:
        if t.error_string:
            groups.setdefault(redact(t.error_string), []).append(t)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
