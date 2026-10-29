from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from torsearch.library.episodes import covered_episodes
from torsearch.models import SearchResult
from torsearch.parser.release import ParsedRelease, parse_release
from torsearch.search.filters import quality_rank
from torsearch.search.matcher import match_media_title, normalize_title


@dataclass(frozen=True)
class ReleaseEvaluation:
    acceptable: bool
    rejection_reason: str = ""
    parsed: ParsedRelease | None = None
    lang_tier: int = 999
    quality_rank: int = 999


@dataclass(frozen=True)
class ReleaseRules:
    """User preferences applied on top of the quality profile."""

    accept_vostfr: bool = True
    exclude_words: tuple[str, ...] = ()

    @classmethod
    def from_profile(cls, profile: Any) -> ReleaseRules:
        return cls(
            accept_vostfr=getattr(profile, "accept_vostfr", True),
            exclude_words=tuple(getattr(profile, "exclude_words", ()) or ()),
        )

    def excluded_word(self, title: str) -> str | None:
        """The first excluded word/phrase present as whole words in ``title``."""
        padded = f" {_words(title)} "
        for word in self.exclude_words:
            norm = _words(word)
            if norm and f" {norm} " in padded:
                return word
        return None


def _words(text: str) -> str:
    """Lowercase words without accents, any non-alphanumeric character as a separator."""
    return " ".join(w for w in re.split(r"[^0-9a-z]+", normalize_title(text)) if w)


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
    max_size: int | None = None,
    rules: ReleaseRules | None = None,
) -> ReleaseEvaluation:
    """Evaluate whether a search result is acceptable for auto-grab and rank it."""
    if result.seeders < min_seeders:
        return ReleaseEvaluation(acceptable=False, rejection_reason="low_seeders")

    if max_size and result.size > max_size:
        return ReleaseEvaluation(acceptable=False, rejection_reason="too_large")

    if blacklist is not None and blacklist.is_blacklisted(result.infohash, result.title):
        return ReleaseEvaluation(acceptable=False, rejection_reason="blacklisted")

    if rules is not None:
        word = rules.excluded_word(result.title)
        if word:
            return ReleaseEvaluation(acceptable=False, rejection_reason=f"excluded_word:{word}")

    parsed = parse_release(result.title)

    if rules is not None and not rules.accept_vostfr and parsed.language == "vostfr":
        return ReleaseEvaluation(acceptable=False, rejection_reason="vostfr_refused", parsed=parsed)

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
    max_size: int | None = None,
    rules: ReleaseRules | None = None,
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
            max_size=max_size,
            rules=rules,
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
    max_episode_size: int | None = None,
    rules: ReleaseRules | None = None,
) -> list[tuple[SearchResult, set[str]]]:
    """Select the best combination of torrents covering missing episodes.

    Greedy by language tier, quality, then size per newly covered episode (a season
    pack beats six singles when it is cheaper per episode, a single beats a huge pack
    for one gap), then seeders. A pick whose episodes end up all covered by the other
    picks is dropped, so an episode is never downloaded twice.
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
            rules=rules,
        )
        if ev.acceptable and ev.parsed and ev.parsed.episodes:
            known = set(missing_episodes or ()) | set(have_episodes or ())
            per_episode = r.size / _episode_count(ev.parsed.episodes, known, aired_known=missing_episodes is not None)
            if max_episode_size and per_episode > max_episode_size:
                continue
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

        # Sort: lang_tier (asc), quality_rank (asc), size per episode (asc), seeders (desc)
        candidates.sort(
            key=lambda item: (
                item[1].lang_tier,
                item[1].quality_rank,
                item[0].size / len(item[2]),
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

    return _drop_redundant(picks, evaluations, missing_episodes, have_episodes)


_DEFAULT_SEASON_LENGTH = 10


def _episode_count(keys: set[str], known: set[str], aired_known: bool = True) -> int:
    """Episodes in a release: its ``SxxEyy`` keys, or for a season pack the season's known
    episodes (aired/missing/have). Without TMDB (``aired_known`` False) only what we have is
    known, so a typical season length is the floor."""
    count = sum(1 for k in keys if "E" in k)
    for season in (k for k in keys if len(k) == 3):
        in_season = sum(1 for e in known if e.startswith(season + "E"))
        count += in_season if aired_known and in_season else max(in_season, _DEFAULT_SEASON_LENGTH)
    return max(count, 1)


def _drop_redundant(
    picks: list[tuple[SearchResult, set[str]]],
    evaluations: list[tuple[SearchResult, ReleaseEvaluation]],
    missing_episodes: set[str] | None,
    have_episodes: set[str] | None,
) -> list[tuple[SearchResult, set[str]]]:
    """Remove picks fully covered by the others; each kept pick claims all it covers."""
    parsed = {id(r): ev.parsed for r, ev in evaluations}
    have = set(have_episodes or ())

    def full(r: SearchResult) -> set[str]:
        p = parsed.get(id(r))
        eps = p.episodes if p is not None else set()
        if missing_episodes is not None:
            return covered_episodes(eps, set(missing_episodes))
        return {ep for ep in eps if "E" in ep} - have

    coverage = {id(r): full(r) | covered for r, covered in picks}
    kept = list(picks)
    # Smallest first: singles go before the pack that contains them.
    for r, _ in sorted(picks, key=lambda p: p[0].size):
        others = set().union(*(coverage[id(o)] for o, _ in kept if o is not r))
        if coverage[id(r)] <= others:
            kept = [p for p in kept if p[0] is not r]
    claimed: set[str] = set()
    out: list[tuple[SearchResult, set[str]]] = []
    for r, _ in kept:
        mine = coverage[id(r)] - claimed
        claimed |= mine
        out.append((r, mine))
    return out


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
    max_episode_size: int | None = None,
    rules: ReleaseRules | None = None,
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
            rules=rules,
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
        if max_episode_size and r.size / len(eps) > max_episode_size:
            continue
        if all(
            replacement_reason(ev.parsed, *previous[e], now, qualities, upgrades) for e in eps
        ):
            picks.append((r, eps))
            covered_all |= eps
    return picks
