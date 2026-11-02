from __future__ import annotations

from torsearch.config import LibraryConfig
from torsearch.models import SearchResult
from torsearch.parser.release import parse_release
from torsearch.search.decision import ReleaseRules, _episode_count, evaluate_release

# Why the decision engine refuses a release, in words Claude can repeat to the user.
VERDICTS = {
    "low_seeders": "pas assez de seeders",
    "too_large": "trop gros pour le profil",
    "blacklisted": "en liste noire",
    "excluded_word": "mot exclu : {}",
    "vostfr_refused": "VOSTFR refusee par le profil",
    "banned_source": "source degradee ({})",
    "title_mismatch": "ne correspond pas a l'oeuvre",
    "unsupported_quality": "qualite hors profil ({})",
    "unsupported_language": "VO sans francais",
}

_GB = 1e9


def _verdict(reason: str) -> str:
    key, _, detail = reason.partition(":")
    template = VERDICTS.get(key)
    if template is None:
        return reason
    return template.format(detail) if "{}" in template else template


def _already_in_transmission(result: SearchResult, torrents) -> bool:
    infohash = (result.infohash or "").lower()
    name = result.title.strip().lower()
    return any((infohash and t.info_hash.lower() == infohash) or t.name.strip().lower() == name for t in torrents)


def release_card(result: SearchResult, rid: str, profile: LibraryConfig, blacklist, torrents,
                 target_title: str | None = None, target_original_title: str | None = None,
                 target_year: int | None = None, is_series: bool = False) -> dict:
    """What Claude needs to judge one release: never its download link (it embeds a passkey)."""
    parsed = parse_release(result.title)
    per_episode = result.size / _episode_count(parsed.episodes, set(), aired_known=False) if parsed.episodes else None
    series = is_series or bool(parsed.episodes)
    evaluation = evaluate_release(
        result,
        # Without a target work, only the profile is judged: the release matches itself.
        target_title=target_title or parsed.clean_title or result.title,
        target_original_title=target_original_title,
        target_year=target_year if target_title else None,
        is_series=series,
        qualities=profile.qualities,
        min_seeders=profile.min_seeders,
        blacklist=blacklist,
        max_size=None if series else profile.max_movie_size,
        rules=ReleaseRules.from_profile(profile),
    )
    verdict = "acceptable" if evaluation.acceptable else _verdict(evaluation.rejection_reason)
    cap = profile.max_episode_size
    if evaluation.acceptable and series and cap and per_episode is not None and per_episode > cap:
        verdict = VERDICTS["too_large"]
    return {
        "id": rid,
        "titre": result.title,
        "tracker": result.source,
        "taille_go": round(result.size / _GB, 2),
        "taille_par_episode_go": round(per_episode / _GB, 2) if per_episode is not None else None,
        "seeders": result.seeders,
        "resolution": parsed.resolution,
        "codec": parsed.codec,
        "hdr": list(parsed.hdr),
        "bits": parsed.bit_depth,
        "source": parsed.source,
        "langue": parsed.language,
        "groupe": parsed.group,
        "episodes": sorted(parsed.episodes),
        "en_liste_noire": bool(blacklist is not None and blacklist.is_blacklisted(result.infohash, result.title)),
        "deja_dans_transmission": _already_in_transmission(result, torrents),
        "verdict": verdict,
    }
