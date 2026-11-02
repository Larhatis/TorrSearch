from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from torsearch import __version__
from torsearch.claude.cards import release_card
from torsearch.claude.limits import HourlyLimit
from torsearch.config import LibraryConfig
from torsearch.library.sending import send_release
from torsearch.models import Category, SearchResult, WantedMovie, WantedSeries
from torsearch.redact import redact
from torsearch.search.filters import ResultFilters, apply

logger = logging.getLogger(__name__)

MAX_DOWNLOADS_PER_HOUR = 10
MAX_SEARCHES_PER_HOUR = 30
MAX_FOLLOWS_PER_HOUR = 10  # each follow can make the surveillance fetch a whole series
MAX_CARDS = 40

_NO_TMDB = "Recherche impossible : cle TMDB absente, ajoute-la dans Reglages > Decouverte."
_EXPIRED = "Resultat expire : relance la recherche."


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def claude_instructions(profile: LibraryConfig) -> str:
    """How Claude should pick releases, from the user's quality profile (French, for Claude)."""
    vostfr = ("VOSTFR acceptee en dernier recours" if profile.accept_vostfr
              else "VOSTFR refusee par l'utilisateur : ne la choisis jamais")
    caps = []
    if profile.max_movie_gb:
        caps.append(f"film <= {profile.max_movie_gb:g} Go")
    if profile.max_episode_gb:
        caps.append(f"episode <= {profile.max_episode_gb:g} Go")
    lines = [
        "Tu pilotes TorrSearch, l'outil de telechargement de l'utilisateur (trackers prives, Transmission, Jellyfin).",
        "Pour trouver une oeuvre : chercher_oeuvre, puis chercher_releases avec son tmdb_id et son type.",
        "Choisis la meilleure release parmi celles dont le verdict est « acceptable » :",
        f"- langue : MULTI ou VFF d'abord, puis VF/VFQ ; {vostfr} ; jamais de VO seule ;",
        "- jamais de CAM/TS/TC/SCR, ni de release en liste noire ;",
        "- a qualite d'image egale, AV1 ou x265 plutot que x264 (fichiers plus legers) ;",
        f"- qualites voulues : {', '.join(profile.qualities) or 'toutes'} ; 2160p avec HDR/Dolby Vision quand le poids "
        f"reste raisonnable{' (' + ', '.join(caps) + ')' if caps else ''}, sinon 1080p ;",
        "- pour une saison complete, un pack plutot que des episodes separes ;",
        f"- au moins {profile.min_seeders} seeder(s) pour demarrer.",
        "Avant de telecharger, verifie deja_dans_transmission et etat_telechargements pour ne rien relancer en double.",
        "Explique ton choix en une phrase ; ne demande a l'utilisateur qu'en cas de vrai doute.",
        "Pour une serie a suivre, utilise suivre_serie (saisons deja possedees dans saisons_acquises).",
        "Tu ne peux rien supprimer. profil_qualite donne les preferences a jour.",
    ]
    return "\n".join(lines)


def _variants(requete: str, title: str | None, original: str | None) -> list[str]:
    """The query, plus the same query on the original title when it names the French one."""
    queries = [requete]
    if title and original and original.lower() != title.lower():
        alt = re.sub(re.escape(title), original, requete, flags=re.IGNORECASE)
        if alt != requete:
            queries.append(alt)
    return queries


def _category(value: str) -> Category:
    try:
        return Category(value)
    except ValueError:
        return Category.ALL


def _enable_surveillance(state) -> None:
    """Following a work turns the surveillance on, like the web UI does."""
    ctx = state.ctx
    if hasattr(ctx, "update_settings") and not ctx.config.monitor.enabled:
        from torsearch.settings.mutations import set_monitor

        ctx.update_settings(set_monitor(ctx.config, ctx.config.monitor.model_copy(update={"enabled": True})))
    runner = getattr(state, "monitor", None)
    if runner is not None:
        runner.wake()


def build_claude_server(state, auth: AuthSettings | None = None, provider=None) -> MCPServer:
    """The MCP server Claude talks to: tools over TorrSearch's own services, nothing destructive.

    ``state`` is the app state (``ctx``, libraries, ``history``, ``grabs``, ``blacklist``,
    ``result_cache``, ``monitor``). Hourly caps live with the server instance.
    """
    server = MCPServer(
        "TorrSearch", version=__version__, instructions=claude_instructions(state.ctx.config.library),
        auth_server_provider=provider, auth=auth,
    )
    downloads = HourlyLimit(MAX_DOWNLOADS_PER_HOUR)
    searches = HourlyLimit(MAX_SEARCHES_PER_HOUR)
    follows = HourlyLimit(MAX_FOLLOWS_PER_HOUR)
    follow_limit = f"Limite atteinte : {MAX_FOLLOWS_PER_HOUR} suivis par heure. Reessaie plus tard."

    async def _torrents():
        try:
            return await state.ctx.transmission.list_torrents()
        except Exception as exc:
            logger.warning("Claude : listing Transmission impossible : %s", redact(str(exc)))
            return []

    @server.tool()
    async def chercher_oeuvre(titre: str) -> str:
        """Cherche un film ou une serie sur TMDB par son titre. Renvoie tmdb_id, type (movie/tv), titres,
        annee, synopsis, et si l'oeuvre est deja dans Jellyfin ou deja surveillee."""
        logger.info("Claude : chercher_oeuvre %r", titre)
        ctx = state.ctx
        if not ctx.tmdb.enabled:
            return _NO_TMDB
        owned: dict = {}
        if getattr(ctx.jellyfin, "enabled", False):
            try:
                owned = await ctx.jellyfin.owned()
            except Exception:
                owned = {}
        works = []
        for m in (await ctx.tmdb.search(titre))[:10]:
            store = state.library if m.media_type == "movie" else state.series_library
            works.append({
                "tmdb_id": m.tmdb_id, "type": m.media_type, "titre": m.title, "titre_original": m.original_title,
                "annee": m.year, "synopsis": (m.overview or "")[:300],
                "dans_jellyfin": f"{m.media_type}:{m.tmdb_id}" in owned,
                "surveille": bool(store is not None and store.get(m.tmdb_id) is not None),
            })
        return _json(works)

    @server.tool()
    async def chercher_releases(requete: str, categorie: str = "all", tmdb_id: int | None = None,
                                type: str | None = None) -> str:
        """Cherche des releases sur les trackers (ex. « Severance S02 »). Avec tmdb_id et type (movie/tv),
        verifie que chaque release correspond bien a l'oeuvre. Renvoie au plus 40 fiches : id (a passer a
        telecharger), taille, taille par episode, codec, HDR/Dolby Vision, bits, langue, groupe, seeders,
        verdict du profil de qualite."""
        logger.info("Claude : chercher_releases %r categorie=%s tmdb_id=%s type=%s", requete, categorie, tmdb_id, type)
        if not searches.allow():
            return f"Limite atteinte : {MAX_SEARCHES_PER_HOUR} recherches par heure. Reessaie plus tard."
        ctx = state.ctx
        target = None
        if tmdb_id is not None and type in ("movie", "tv") and ctx.tmdb.enabled:
            target = await ctx.tmdb.get_details(type, tmdb_id)
        category = _category(categorie)
        found: list[SearchResult] = []
        seen: set[str] = set()
        for query in _variants(requete, target.title if target else None, target.original_title if target else None):
            try:
                results = await ctx.search_service.search(query, category)
            except Exception as exc:
                logger.warning("Claude : recherche %r en echec : %s", query, redact(str(exc)))
                continue
            for r in results:
                key = r.infohash or r.download_url
                if key not in seen:
                    seen.add(key)
                    found.append(r)
        ranked = apply(found, ResultFilters(sort="relevance", query=requete))[:MAX_CARDS]
        torrents = await _torrents()
        year = int(target.year) if target and target.year and str(target.year).isdigit() else None
        cards = [
            release_card(r, state.result_cache.put(r), ctx.config.library, getattr(state, "blacklist", None), torrents,
                         target_title=target.title if target else None,
                         target_original_title=target.original_title if target else None,
                         target_year=year, is_series=bool(target and type == "tv"))
            for r in ranked
        ]
        return _json(cards)

    @server.tool()
    async def telecharger(release_id: str) -> str:
        """Envoie a Transmission la release dont l'id vient de chercher_releases. Elle est rangee comme le
        ferait la surveillance (dossier du film, ou Serie/Saison XX) et marquee si l'oeuvre est suivie."""
        logger.info("Claude : telecharger %s", release_id)
        result = state.result_cache.get(release_id)
        if result is None:
            return _EXPIRED
        if not downloads.allow():
            return f"Limite atteinte : {MAX_DOWNLOADS_PER_HOUR} telechargements par heure. Reessaie plus tard."
        outcome = await send_release(state, result.download_url, result.title, result.category,
                                     fallback_hash=result.infohash)
        return outcome.message

    @server.tool()
    async def suivre_serie(tmdb_id: int, saisons_acquises: list[int] | None = None) -> str:
        """Ajoute une serie a la surveillance : chaque nouvel episode sera telecharge automatiquement.
        saisons_acquises = saisons que l'utilisateur a deja (elles ne seront pas telechargees)."""
        logger.info("Claude : suivre_serie %s saisons_acquises=%s", tmdb_id, saisons_acquises)
        ctx = state.ctx
        if not ctx.tmdb.enabled:
            return _NO_TMDB
        if not follows.allow():
            return follow_limit
        details = await ctx.tmdb.get_details("tv", tmdb_id)
        if details is None:
            return "Serie introuvable sur TMDB."
        library = state.series_library
        added = library.add(WantedSeries(
            tmdb_id=tmdb_id, title=details.title, original_title=details.original_title, year=details.year,
            poster_path=details.poster_path, added_at=datetime.now(UTC),
        ))
        marked: list[int] = []
        if saisons_acquises:
            for season in await ctx.tmdb.seasons(tmdb_id):
                if season.season_number in saisons_acquises:
                    library.mark_grabbed(tmdb_id, [season.season_tag] + [ep.code for ep in season.episodes])
                    marked.append(season.season_number)
        _enable_surveillance(state)
        message = f"{details.title} : {'ajoutee a la surveillance' if added else 'deja surveillee'}"
        if marked:
            message += f" (saisons {', '.join(map(str, sorted(marked)))} marquees acquises)"
        return message + "."

    @server.tool()
    async def surveiller_film(tmdb_id: int) -> str:
        """Ajoute un film a la surveillance : il sera telecharge des qu'une release conforme au profil sort."""
        logger.info("Claude : surveiller_film %s", tmdb_id)
        ctx = state.ctx
        if not ctx.tmdb.enabled:
            return _NO_TMDB
        if not follows.allow():
            return follow_limit
        details = await ctx.tmdb.get_details("movie", tmdb_id)
        if details is None:
            return "Film introuvable sur TMDB."
        added = state.library.add(WantedMovie(
            tmdb_id=tmdb_id, title=details.title, original_title=details.original_title, year=details.year,
            poster_path=details.poster_path, status="wanted", added_at=datetime.now(UTC),
        ))
        _enable_surveillance(state)
        return f"{details.title} : {'ajoute a la surveillance' if added else 'deja surveille'}."

    @server.tool()
    async def etat_telechargements() -> str:
        """Les 30 torrents les plus recents de Transmission : progression, statut, debit, temps restant, erreur."""
        logger.info("Claude : etat_telechargements")
        torrents = sorted(await _torrents(), key=lambda t: t.date_added or datetime.min.replace(tzinfo=UTC),
                          reverse=True)[:30]
        return _json([{
            "nom": t.name, "progression": round(t.percent, 1), "statut": t.status_label,
            "debit": t.down_rate_formatted, "temps_restant": t.eta_formatted,
            "erreur": redact(t.error_string) if t.error_string else None,
        } for t in torrents])

    @server.tool()
    async def etat_surveillance() -> str:
        """Ce que la surveillance suit : films (en attente ou obtenus), series (episodes acquis),
        recherches libres, et les 10 derniers envois automatiques."""
        logger.info("Claude : etat_surveillance")
        films = [{"titre": m.title, "annee": m.year, "statut": "obtenu" if m.status == "grabbed" else "en attente"}
                 for m in (state.library.list() if state.library else [])]
        series = []
        for s in state.series_library.list() if state.series_library else []:
            episodes = sorted(k for k in s.grabbed if "E" in k)
            series.append({"titre": s.title, "episodes_acquis": len(episodes),
                           "dernier_acquis": episodes[-1] if episodes else None})
        history = getattr(state, "history", None)
        recent = [r for r in (history.records() if history else []) if r.kind == "grabbed"][:10]
        return _json({
            "films": films, "series": series,
            "recherches_libres": [s.name for s in state.ctx.config.saved_searches if s.enabled],
            "derniers_envois": [{"titre": r.title, "oeuvre": r.search, "date": r.at.isoformat()} for r in recent],
        })

    @server.tool()
    async def profil_qualite() -> str:
        """Le profil de qualite de l'utilisateur : qualites, seeders minimum, VOSTFR acceptee ou non,
        mots exclus, tailles maximales (0 = sans limite)."""
        logger.info("Claude : profil_qualite")
        p = state.ctx.config.library
        return _json({
            "qualites": p.qualities, "seeders_min": p.min_seeders, "vostfr_acceptee": p.accept_vostfr,
            "mots_exclus": p.exclude_words, "taille_max_film_go": p.max_movie_gb,
            "taille_max_episode_go": p.max_episode_gb, "upgrades": p.upgrades,
        })

    return server
