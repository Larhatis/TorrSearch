# Phase D — Découverte tendances + intégration Jellyfin — Design

**Date :** 2026-06-21
**Statut :** validé

## Objectif

Achever la roadmap. Deux apports liés à l'expérience découverte/bibliothèque :
1. **Découverte soignée** : la page Découvrir affiche une grille de **tendances** (films + séries
   populaires de la semaine, TMDB) au chargement, au lieu d'un champ vide — finit le remplacement
   de Jellyseerr.
2. **Intégration Jellyfin** : TorrSearch sait ce que tu **possèdes déjà** dans ton Jellyfin et
   l'affiche (badge « Dans Jellyfin » + lien **Lire**), pour ne pas re-télécharger et lancer la
   lecture. Jellyfin reste le serveur média (on ne le remplace pas).

Non-objectifs (Phase D) : cache des appels Jellyfin (v1 = par requête), parcours par genre,
recommandations, watch-history, suppression auto de la bibliothèque quand possédé.

## Décisions (validées)

- Matching « possédé » **par `(media_type, tmdb_id)`** via `ProviderIds.Tmdb` de Jellyfin
  (le plus fiable ; clé typée pour éviter les collisions film/série).
- Jellyfin interrogé **par requête** (client résilient, pas de cache v1).
- Config Jellyfin dans **Réglages** (form + mutation, comme le profil qualité).
- Marqueurs « possédé » sur **Découvrir et Bibliothèque**.
- Les cartes gardent leur bouton Ajouter/Suivre même si possédé (pas de masquage — YAGNI).

## Partie 1 — Tendances

### `TmdbClient.trending` — `torsearch/metadata/tmdb.py` (modifié)

- `_TRENDING_URL = "https://api.themoviedb.org/3/trending/all/week"`.
- `async trending(self) -> list[MediaResult]` : si non `enabled` → `[]` ; GET avec
  `params={api_key, language: "fr-FR"}` ; **réutilise `parse_multi`** (la réponse contient
  `media_type` par item) ; résilient (toute exception → `[]`).

### Web — `discover_routes.py` + `discover.html`

- `GET /discover/trending` → `media_results.html` avec `{media: await ctx.tmdb.trending(), query: "", owned, jellyfin_url}`.
- `discover.html` : la zone `#media-results` charge les tendances au chargement
  (`hx-get="/discover/trending" hx-trigger="load"`). Une recherche remplace toujours `#media-results`.

## Partie 2 — Intégration Jellyfin

### Config — `torsearch/config.py` (modifié)

`JellyfinConfig(BaseModel, frozen)` : `url: str = ""`, `api_key: str = ""`. Ajouté à `Config` :
`jellyfin: JellyfinConfig = Field(default_factory=JellyfinConfig)`. Mutation `set_jellyfin`.

### Client — `torsearch/jellyfin/__init__.py` (vide) + `torsearch/jellyfin/client.py` (créé)

`JellyfinClient` (httpx, **résilient**, client injectable pour tests) :
- `__init__(config: JellyfinConfig, client=None, timeout=10.0)` ; `_url = url.rstrip("/")`.
- `enabled: bool` → `bool(url and api_key)`.
- `base_url: str` → `_url` (pour bâtir les liens « Lire »).
- `async owned() -> dict[str, str]` : si non `enabled` → `{}` ; GET `{url}/Items`
  `params={Recursive:"true", IncludeItemTypes:"Movie,Series", Fields:"ProviderIds", api_key}` ;
  pour chaque item avec `ProviderIds.Tmdb` → clé `f"{'movie' if Type=='Movie' else 'tv'}:{tmdb}"`,
  valeur = `Id`. Toute exception → `{}`.

### Contexte — `torsearch/context.py` (modifié)

`AppContext._rebuild` construit `self._jellyfin = JellyfinClient(self._config.jellyfin)` ; propriété
`jellyfin`. Hot-reload.

### Marqueurs « possédé » — routes + templates

- `discover_search`, `discover_trending`, `library_page` calculent
  `owned = await ctx.jellyfin.owned()` (résilient) et passent `owned` + `jellyfin_url = ctx.jellyfin.base_url`.
- `media_results.html`, `partials/library_list.html`, `partials/series_list.html` : pour chaque
  carte, `{% set jf = (owned or {}).get(media_type ~ ':' ~ tmdb_id) %}` ; si `jf` →
  badge **« Dans Jellyfin »** (emerald) + lien **« Lire »**
  (`{{ jellyfin_url }}/web/#/details?id={{ jf }}`, nouvel onglet). Films → clé `movie:{id}`,
  séries → clé `tv:{id}`. `(owned or {})` rend les templates tolérants quand un appelant ne passe
  pas `owned`.

### Réglages — section Jellyfin

Form dans `settings.html` (URL + clé) → `POST /settings/jellyfin` → mutation `set_jellyfin` →
`ctx.update_settings`. Toast.

## Flux de données

1. `/discover` → `#media-results` auto-charge `/discover/trending` → grille de tendances ; chaque
   carte marquée « Dans Jellyfin » + « Lire » si possédée.
2. Recherche → `/discover/search` (mêmes marqueurs).
3. `/library` → sections Films & Séries, chaque carte marquée si possédée.

## Gestion des erreurs / cas limites

- TMDB sans clé → page onboarding (inchangé) ; pas de tendances.
- Jellyfin désactivé/erreur → `owned()` = `{}` → aucun marqueur (dégradation silencieuse).
- Item Jellyfin sans `ProviderIds.Tmdb` → ignoré.
- Collision id film/série → évitée par la clé typée.

## Tests

- `tests/test_tmdb.py` (ajouts) : `trending` succès (respx, réutilise le fixture multi) → 2
  résultats ; désactivé → `[]` ; erreur HTTP → `[]`.
- `tests/test_jellyfin.py` : `owned` parse `ProviderIds.Tmdb` + `Type` → map typé ; item sans Tmdb
  ignoré ; désactivé → `{}` ; erreur → `{}` ; `base_url` strippe le slash final.
- `tests/test_config.py` (ajout) : `jellyfin` défauts + chargement + interpolation `${...}`.
- `tests/test_context.py` (ajout) : `AppContext.jellyfin` présent, désactivé par défaut.
- `tests/test_discover_web.py` (ajouts) : `GET /discover` contient `hx-get="/discover/trending"` ;
  `GET /discover/trending` rend des cartes ; un résultat possédé (Jellyfin) affiche
  « Dans Jellyfin » + le lien Lire.
- `tests/test_series_web.py`/`test_library_web.py` (ajout) : carte possédée → marqueur sur la
  Bibliothèque.
- `tests/test_settings_web.py` (ajout) : `POST /settings/jellyfin` met à jour la config.
- Non-régression : suite existante (226) reste verte.
