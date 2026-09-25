from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from torsearch.models import SearchResult
from torsearch.monitor.runner import covered_episodes
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

    remaining = set(missing_episodes) if missing_episodes is not None else None
    picks: list[tuple[SearchResult, set[str]]] = []

    while True:
        candidates: list[tuple[SearchResult, ReleaseEvaluation, set[str]]] = []
        for r, ev in evaluations:
            assert ev.parsed is not None
            if remaining is not None:
                covered = covered_episodes(ev.parsed.episodes, remaining)
            else:
                covered = ev.parsed.episodes
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

        if remaining is not None:
            remaining -= covered
            if not remaining:
                break
        else:
            break

    return picks
