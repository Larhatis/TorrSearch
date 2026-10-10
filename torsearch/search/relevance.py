from __future__ import annotations

import math
import re
from typing import Any

from torsearch.library.episodes import covered_episodes, parse_episodes
from torsearch.models import SearchResult
from torsearch.parser.release import parse_release
from torsearch.search.matcher import normalize_title, strip_articles

_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")
_SEASON_EP_STRIP_RE = re.compile(
    r"\b(?:s\d{1,2}(?:[ ._-]*e\d{1,2})?|season[ ._-]*\d{1,2}|saison[ ._-]*\d{1,2})\b",
    re.IGNORECASE,
)

_NUMERAL_SYNONYMS: dict[str, set[str]] = {
    "1": {"1", "i", "one", "un", "premier", "premiere", "part1", "part 1"},
    "2": {"2", "ii", "two", "deux", "deuxieme", "part2", "part 2"},
    "3": {"3", "iii", "three", "trois", "troisieme", "part3", "part 3"},
    "4": {"4", "iv", "four", "quatre", "quatrieme", "part4", "part 4"},
    "5": {"5", "v", "five", "cinq", "cinquieme", "part5", "part 5"},
}


def _word_matches(query_word: str, target_words: set[str]) -> bool:
    if query_word in target_words:
        return True
    synonyms = _NUMERAL_SYNONYMS.get(query_word)
    if synonyms and any(s in target_words for s in synonyms):
        return True
    return False


def compute_relevance(result: SearchResult | Any, query: str, seeders: int | None = None) -> float:
    """Compute a relevance score for a search result given a query.

    Higher score means better match. Combines:
    - Title match (exact, prefix, word overlap)
    - Year match (if specified in query)
    - Season/Episode match (if specified in query)
    - Penalty for banned sources (CAM, TS, TC, SCREENER)
    - Bonus for quality / French language tiers
    - Logarithmic health / seeder scaling
    """
    if isinstance(result, SearchResult):
        raw_title = result.title
        seeders_val = result.seeders
    elif hasattr(result, "title"):
        raw_title = str(result.title)
        seeders_val = getattr(result, "seeders", 0) or 0
    else:
        raw_title = str(result)
        seeders_val = seeders if seeders is not None else 0

    query_str = query.strip()
    if not query_str:
        return float(seeders_val)

    q_norm = normalize_title(query_str)
    if not q_norm:
        return float(seeders_val)

    q_year_match = _YEAR_RE.search(query_str)
    q_year = int(q_year_match.group(1)) if q_year_match else None
    q_episodes = parse_episodes(query_str)

    # Strip year and season/episode tokens from query to obtain the target title
    q_title_str = _SEASON_EP_STRIP_RE.sub("", _YEAR_RE.sub("", query_str))
    q_title_norm = normalize_title(q_title_str)
    target = q_title_norm if q_title_norm else q_norm
    target_no_art = strip_articles(target)
    target_words = [w for w in target.split() if w]

    parsed = parse_release(raw_title)
    rel_norm = normalize_title(parsed.clean_title)
    rel_no_art = strip_articles(rel_norm)
    rel_words = set(rel_norm.split())

    raw_norm = normalize_title(raw_title)
    raw_no_art = strip_articles(raw_norm)
    raw_words = set(raw_norm.split())

    score = 0.0

    # 1. Title match
    if rel_norm == target or (target_no_art and rel_no_art == target_no_art):
        score += 1000.0
    elif raw_norm == target or (target_no_art and raw_no_art == target_no_art):
        score += 900.0
    elif target_words and all(_word_matches(w, rel_words) for w in target_words):
        # All target words are present in clean title
        extra_words = len(rel_words - set(target_words))
        score += max(750.0 - extra_words * 25.0, 500.0)
    elif target and (rel_norm.startswith(target) or (target_no_art and rel_no_art.startswith(target_no_art))):
        extra_len = max(len(rel_norm) - len(target), 0)
        score += max(700.0 - extra_len * 5.0, 450.0)
    elif target_words and all(_word_matches(w, raw_words) for w in target_words):
        # All target words are present in raw title
        score += 450.0
    elif target_words:
        matched = sum(1 for w in target_words if _word_matches(w, raw_words))
        if matched > 0:
            score += (matched / len(target_words)) * 300.0
        else:
            score -= 500.0
    else:
        score += 100.0

    # 2. Year matching
    if q_year is not None:
        if parsed.year == q_year:
            score += 200.0
        elif parsed.year is not None:
            diff = abs(parsed.year - q_year)
            if diff > 1:
                score -= 250.0
    elif parsed.year is not None:
        score += 15.0

    # 3. Season / Episode matching
    if q_episodes:
        if parsed.episodes and (
            bool(parsed.episodes & q_episodes)
            or bool(covered_episodes(parsed.episodes, q_episodes))
            or bool(covered_episodes(q_episodes, parsed.episodes))
        ):
            score += 250.0
        elif parsed.episodes:
            score -= 200.0

    # 4. Explicit resolution requested in query
    for res in ("2160p", "1080p", "720p", "480p"):
        if res in q_norm or (res == "2160p" and "4k" in q_norm):
            if parsed.resolution == res:
                score += 100.0
            elif parsed.resolution != "unknown":
                score -= 50.0

    # 5. Penalty for banned sources
    if parsed.is_banned_source:
        score -= 600.0

    # 6. Quality & Language preferences (French server context)
    if parsed.language in ("multi", "vff"):
        score += 30.0
    elif parsed.language in ("vf", "vfq"):
        score += 20.0
    elif parsed.language == "vostfr":
        score += 10.0
    elif parsed.language == "vo":
        score += 0.0
    else:
        score += 5.0

    if parsed.resolution in ("2160p", "1080p"):
        score += 20.0
    elif parsed.resolution == "720p":
        score += 10.0
    elif parsed.resolution == "480p":
        score += 5.0

    # 7. Health / Seeder log scaling
    if seeders_val > 0:
        score += min(math.log10(seeders_val + 1) * 20.0, 50.0)

    return score
