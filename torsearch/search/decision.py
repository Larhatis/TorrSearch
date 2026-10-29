from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from torsearch.library.episodes import covered_episodes
from torsearch.models import SearchResult
from torsearch.parser.release import ParsedRelease, parse_release
from torsearch.search.filters import quality_rank
from torsearch.search.matcher import match_media_title


@dataclass(frozen=True)
class ReleaseEvaluation:
    acceptable: bool
    rejection_reason: str = ""
    parsed: ParsedRelease | None = None
    lang_tier: int = 999
    quality_rank: int = 999


def _get_lang_tier(language: str) -> int:
    if language in ("multi", "vff"):
        return 1
    if language in ("vf", "vfq"):
        return 2
    if language == "vostfr":
        return 3
    if language == "unknown":
        return 4
    return 999


def evaluate_release(
    result: SearchResult,
    target_title: str,
    target_original_title: str | None = None,
    target_year: str | int | None = None,
    is_series: bool = False,
    qualities: list[str] | None = None,
    min_seeders: int = 1,
    blacklist: Any = None,
) -> ReleaseEvaluation:
    """Evaluate whether a search result is acceptable for auto-grab and rank it."""
    if result.seeders < min_seeders:
        return ReleaseEvaluation(acceptable=False, rejection_reason="low_seeders")

    if blacklist is not None and blacklist.is_blacklisted(result.infohash, result.title):
        return ReleaseEvaluation(acceptable=False, rejection_reason="blacklisted")

    parsed = parse_release(result.title)

    if parsed.is_banned_source:
        return ReleaseEvaluation(
            acceptable=False,
            rejection_reason=f"banned_source:{parsed.source}",
            parsed=parsed,
        )

    if not match_media_title(
        parsed,
        target_title=target_title,
        target_original_title=target_original_title,
        target_year=target_year,
        is_series=is_series,
    ):
        return ReleaseEvaluation(
            acceptable=False,
            rejection_reason="title_mismatch",
            parsed=parsed,
        )

    if qualities and parsed.resolution not in qualities:
        return ReleaseEvaluation(
            acceptable=False,
            rejection_reason=f"unsupported_quality:{parsed.resolution}",
            parsed=parsed,
        )

    if parsed.language == "vo":
        return ReleaseEvaluation(
            acceptable=False,
            rejection_reason="unsupported_language:vo",
            parsed=parsed,
        )

    lang_tier = _get_lang_tier(parsed.language)

    if qualities:
        try:
            q_rank = qualities.index(parsed.resolution)
        except ValueError:
            q_rank = 999
    else:
        q_rank = quality_rank(result.title)

    return ReleaseEvaluation(
        acceptable=True,
        parsed=parsed,
        lang_tier=lang_tier,
        quality_rank=q_rank,
    )


def select_best_movie_release(
    results: list[SearchResult],
    target_title: str,
    target_original_title: str | None = None,
    target_year: str | int | None = None,
    qualities: list[str] | None = None,
    min_seeders: int = 1,
    blacklist: Any = None,
    current_quality: str | None = None,
) -> SearchResult | None:
    """Pick the single best movie release according to preferences and quality rankings."""
    candidates: list[tuple[SearchResult, ReleaseEvaluation]] = []

    for r in results:
        ev = evaluate_release(
            r,
            target_title=target_title,
            target_original_title=target_original_title,
            target_year=target_year,
            is_series=False,
            qualities=qualities,
            min_seeders=min_seeders,
            blacklist=blacklist,
        )
        if not ev.acceptable:
            continue

        if current_quality is not None and qualities:
            try:
                curr_rank = qualities.index(current_quality)
            except ValueError:
                curr_rank = 999
            if ev.quality_rank >= curr_rank:
                continue

        candidates.append((r, ev))

    if not candidates:
        return None

    # Sort key: lang_tier (1 best), quality_rank (0 best), seeders (highest), size (lowest)
    candidates.sort(
        key=lambda item: (
            item[1].lang_tier,
            item[1].quality_rank,
            -item[0].seeders,
            item[0].size,
        )
    )
    return candidates[0][0]


def select_series_releases(
    results: list[SearchResult],
    target_title: str,
    target_original_title: str | None = None,
    missing_episodes: set[str] | None = None,
    have_episodes: set[str] | None = None,
    qualities: list[str] | None = None,
    min_seeders: int = 1,
    blacklist: Any = None,
) -> list[tuple[SearchResult, set[str]]]:
    """Select the best combination of torrents covering missing episodes.

    Prioritizes language tier, then smallest covering pack to avoid downloading
    huge season packs when a single episode satisfies the gap, then seeders.
    """
    if missing_episodes is not None and not missing_episodes:
        return []

    evaluations: list[tuple[SearchResult, ReleaseEvaluation]] = []
    for r in results:
        ev = evaluate_release(
            r,
            target_title=target_title,
            target_original_title=target_original_title,
            is_series=True,
            qualities=qualities,
            min_seeders=min_seeders,
            blacklist=blacklist,
        )
        if ev.acceptable and ev.parsed and ev.parsed.episodes:
            evaluations.append((r, ev))

    target_missing = set(missing_episodes) if missing_episodes is not None else None
    current_have = set(have_episodes) if have_episodes is not None else set()
    season_tags = {k for k in current_have if len(k) == 3 and k.startswith("S") and k[1:].isdigit()}
    picks: list[tuple[SearchResult, set[str]]] = []

    while True:
        candidates: list[tuple[SearchResult, ReleaseEvaluation, set[str]]] = []
        for r, ev in evaluations:
            assert ev.parsed is not None
            if target_missing is not None:
                covered = covered_episodes(ev.parsed.episodes, target_missing)
            else:
                raw_eps = {ep for ep in ev.parsed.episodes if "E" in ep} - current_have
                covered = {ep for ep in raw_eps if not any(ep.startswith(st + "E") for st in season_tags)}
            if covered:
                candidates.append((r, ev, covered))

        if not candidates:
            break

        # Sort: lang_tier (asc), quality_rank (asc), size (asc), seeders (desc)
        candidates.sort(
            key=lambda item: (
                item[1].lang_tier,
                item[1].quality_rank,
                item[0].size,
                -item[0].seeders,
            )
        )
        best_res, _, covered = candidates[0]
        picks.append((best_res, covered))
        current_have |= covered

        if target_missing is not None:
            target_missing -= covered
            if not target_missing:
                break

    return picks


REPACK_WINDOW = timedelta(days=14)
# Episode upgrades only follow recent grabs: enabling the option must not re-download a
# whole back catalogue (old files are not deleted).
UPGRADE_WINDOW = timedelta(days=30)
_REPACK_EDITIONS = ("proper", "repack")
_GROUP_RE = re.compile(r"-([A-Za-z0-9]+)(?:\.(?:mkv|mp4|avi))?$")


def release_group(title: str) -> str | None:
    """Release group tag at the end of a title (``...-GRP``), if any."""
    m = _GROUP_RE.search(title.strip())
    return m.group(1) if m else None


def replacement_reason(
    candidate: ParsedRelease,
    previous_title: str,
    previous_at: datetime,
    now: datetime,
    qualities: list[str] | None,
    upgrades: bool,
) -> str | None:
    """Why ``candidate`` should replace an already grabbed release, or None.

    ``"repack"``: a PROPER/REPACK of a recent grab, same resolution and (when both are
    tagged) same group. ``"upgrade"``: upgrades enabled, a grab of the last 30 days, and a
    strictly better quality of the profile without a worse language.
    """
    previous = parse_release(previous_title)
    if (
        candidate.edition in _REPACK_EDITIONS
        and previous.edition not in _REPACK_EDITIONS
        and candidate.resolution == previous.resolution
        and now - previous_at <= REPACK_WINDOW
    ):
        cand_group, prev_group = release_group(candidate.raw_title), release_group(previous_title)
        if not (cand_group and prev_group and cand_group.lower() != prev_group.lower()):
            return "repack"
    if upgrades and qualities and candidate.resolution in qualities and now - previous_at <= UPGRADE_WINDOW:
        prev_rank = qualities.index(previous.resolution) if previous.resolution in qualities else 999
        if (
            qualities.index(candidate.resolution) < prev_rank
            and _get_lang_tier(candidate.language) <= _get_lang_tier(previous.language)
        ):
            return "upgrade"
    return None


def select_series_replacements(
    results: list[SearchResult],
    target_title: str,
    target_original_title: str | None,
    previous: dict[str, tuple[str, datetime]],
    taken: set[str],
    now: datetime,
    qualities: list[str] | None = None,
    min_seeders: int = 1,
    blacklist: Any = None,
    upgrades: bool = False,
) -> list[tuple[SearchResult, set[str]]]:
    """Releases replacing already grabbed episodes (``previous``: episode -> (title, at)).

    Only releases covering episodes all grabbed before are considered; ``taken`` holds the
    lowercased titles/keys already grabbed so a replacement is never taken twice.
    """
    candidates: list[tuple[SearchResult, ReleaseEvaluation]] = []
    for r in results:
        key = (r.infohash or r.download_url or "").lower()
        if r.title.lower() in taken or key in taken:
            continue
        ev = evaluate_release(
            r, target_title=target_title, target_original_title=target_original_title,
            is_series=True, qualities=qualities, min_seeders=min_seeders, blacklist=blacklist,
        )
        if ev.acceptable and ev.parsed is not None:
            candidates.append((r, ev))
    # Best first, so a 2160p is not preceded by an intermediate 1080p download.
    candidates.sort(key=lambda c: (c[1].lang_tier, c[1].quality_rank, -c[0].seeders))

    picks: list[tuple[SearchResult, set[str]]] = []
    covered_all: set[str] = set()
    for r, ev in candidates:
        assert ev.parsed is not None
        eps = {e for e in ev.parsed.episodes if "E" in e}
        if not eps or eps & covered_all or not eps <= previous.keys():
            continue
        if all(
            replacement_reason(ev.parsed, *previous[e], now, qualities, upgrades) for e in eps
        ):
            picks.append((r, eps))
            covered_all |= eps
    return picks
