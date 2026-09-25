from __future__ import annotations

import re
import unicodedata

from torsearch.parser.release import ParsedRelease

_ARTICLES_RE = re.compile(r"^(the|le|la|les|l|un|une|des)\s+", re.IGNORECASE)


def normalize_title(title: str) -> str:
    """Normalize a title for strict comparison: strip accents, punctuation and excess spaces."""
    if not title:
        return ""
    # Strip accents / diacritics
    nfkd = unicodedata.normalize("NFKD", title)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Replace punctuation and special chars with space
    clean = re.sub(r"[._\-+':;!?/\\()\[\]]+", " ", no_accents)
    # Lowercase and collapse spaces
    return re.sub(r"\s+", " ", clean).strip().lower()


def strip_articles(norm_title: str) -> str:
    return _ARTICLES_RE.sub("", norm_title).strip()


_strip_articles = strip_articles


def _alnum_only(norm_title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_title)


def match_media_title(
    release: ParsedRelease,
    target_title: str,
    target_original_title: str | None = None,
    target_year: str | int | None = None,
    is_series: bool = False,
) -> bool:
    """Check if a parsed release strictly matches a desired media target."""
    release_norm = normalize_title(release.clean_title)
    if not release_norm:
        return False

    release_alnum = _alnum_only(release_norm)
    release_no_art = _strip_articles(release_norm)

    targets = [target_title]
    if target_original_title and target_original_title.strip():
        targets.append(target_original_title)

    title_matched = False
    for tgt in targets:
        tgt_norm = normalize_title(tgt)
        if not tgt_norm:
            continue
        if release_norm == tgt_norm:
            title_matched = True
            break
        if release_no_art == _strip_articles(tgt_norm):
            title_matched = True
            break
        if release_alnum == _alnum_only(tgt_norm):
            title_matched = True
            break

    if not title_matched:
        return False

    # Check year if available on both side (for movies)
    if not is_series and target_year is not None and release.year is not None:
        try:
            ty = int(target_year)
            if abs(release.year - ty) > 1:
                return False
        except (ValueError, TypeError):
            pass

    return True
