# F2 — Recherches sauvegardées + surveillance auto — Spec de conception

> Date : 2026-06-19
> Statut : approuvé (carte blanche + confirmation « les deux modes »), en implémentation
> Construit sur F1 + F3 (branche `feat/saved-searches`).

## 1. Contexte & objectif

Enregistrer des recherches et laisser TorSearch **surveiller périodiquement** les trackers,
pour soit **envoyer automatiquement** à Transmission les nouveaux résultats qui matchent, soit
simplement les **signaler**. C'est le pas vers « un Sonarr simple ».

## 2. Décisions (issues du brainstorming)

| Sujet | Décision |
|---|---|
| Modes | **Les deux**, choisis **par recherche** : `auto` (envoi auto) ou `notify` (signalé seulement, avec bouton « Envoyer » manuel). Défaut `auto`. |
| Surveillance globale | **OFF par défaut** (opt-in) + intervalle configurable (défaut **30 min**). |
| Grab par cycle | **Un seul** (le meilleur nouveau, seeders desc) par recherche et par cycle — simple et sûr. |
| Anti-doublon | Par `infohash` (repli `download_url`) ; vaut pour `auto` **et** `notify` (on ne re-signale pas deux fois la même release). |

## 3. Périmètre

### Dans F2 (in scope)

- Page **/surveillance** :
  - Enregistrer une recherche : nom (identifiant unique), requête, catégorie, filtres
    (seeders min, taille min/max, qualités, exclusion — mêmes critères que F1), **mode** (`auto`/`notify`).
  - Liste des recherches : activer/désactiver, supprimer.
  - Réglage global : surveillance **on/off** + **intervalle** (minutes).
  - **Historique** des détections : par recherche, titre, source, type (`grabbé`/`trouvé`), date ;
    les items `trouvé` (mode notify) ont un bouton **« Envoyer »** (réutilise `/download`).
- **Tâche de fond** (asyncio) : à chaque intervalle, si la surveillance globale est ON, pour
  chaque recherche **active**, rejoue la recherche → applique les filtres → sélectionne le
  meilleur résultat **pas encore vu** → `auto` : l'envoie à Transmission + enregistre `grabbé` ;
  `notify` : enregistre `trouvé` (sans envoi).
- Lien nav **« Surveillance »**.

### Hors F2 (plus tard)

Notifications externes (Discord/ntfy) · fenêtres horaires · plusieurs grabs par cycle · édition
des critères d'une recherche après création (on supprime/recrée) · quotas/limites de débit.

## 4. Architecture

### 4.1 Modèles (`torsearch/config.py`)

Modèles **frozen** (cohérents avec les autres modèles de config) :

- `SavedSearch` : `name: str`, `query: str`, `category: Category = ALL`,
  `min_seeders: int = 0`, `min_size: int | None = None`, `max_size: int | None = None`,
  `qualities: list[str] = []`, `exclude: list[str] = []`, `mode: str = "auto"`
  (∈ `{"auto", "notify"}`), `enabled: bool = True`.
- `MonitorConfig` : `enabled: bool = False`, `interval_minutes: int = 30`.
- Ajouts à `Config` : `saved_searches: list[SavedSearch] = []`, `monitor: MonitorConfig = MonitorConfig()`.

### 4.2 Mutations (`torsearch/settings/mutations.py`, étendu)

Fonctions pures (immutabilité via `model_copy`, frozen-safe), erreurs via `SettingsError` :
- `add_saved_search(config, ss)` (refus si nom déjà pris).
- `remove_saved_search(config, name)`.
- `set_saved_search_enabled(config, name, enabled)`.
- `set_monitor(config, monitor)`.

### 4.3 Historique (`torsearch/monitor/history.py`)

- `MonitorRecord` (Pydantic) : `search: str`, `title: str`, `source: str`,
  `infohash: str | None`, `download_url: str`, `kind: str` (∈ `{"grabbed", "found"}`),
  `at: datetime`.
- `MonitorHistory` : adossé à **`data/monitor.json`** (liste de `MonitorRecord`), gitignoré
  (le dossier `data/` l'est déjà). Méthodes :
  - `records() -> list[MonitorRecord]` (les plus récents d'abord).
  - `seen_keys(search_name) -> set[str]` : clés (`infohash` sinon `download_url`) déjà
    enregistrées pour cette recherche.
  - `add(record)` : ajoute + **écriture atomique** (temp + `os.replace`).

### 4.4 Logique de surveillance (`torsearch/monitor/runner.py`)

- `grab_key(result) -> str` : `result.infohash or result.download_url`.
- `select_new(results, filters, seen) -> SearchResult | None` : applique `filters.apply`
  (tri seeders desc), renvoie le premier dont `grab_key ∉ seen`, sinon `None`.
- `async run_cycle(config, search_service, transmission, history) -> list[MonitorRecord]` :
  - si `not config.monitor.enabled` → `[]`.
  - pour chaque `ss` de `config.saved_searches` si `ss.enabled` (chaque itération en
    `try/except` → une erreur n'arrête pas le cycle) :
    - `results = await search_service.search(ss.query, ss.category)` ;
    - `filters = ResultFilters(min_seeders=ss.min_seeders, min_size=ss.min_size, max_size=ss.max_size, qualities=ss.qualities, exclude=ss.exclude, sort="seeders", direction="desc")` ;
    - `pick = select_new(results, filters, history.seen_keys(ss.name))` ;
    - si `pick` : si `ss.mode == "auto"` → `transmission.add(pick.download_url)` (en `try/except` ;
      en cas d'échec, on n'enregistre pas) puis `history.add(MonitorRecord(kind="grabbed", ...))` ;
      sinon → `history.add(MonitorRecord(kind="found", ...))`.
  - renvoie la liste des `MonitorRecord` créés.
- `MonitorRunner(ctx, history)` : `async start()` crée une tâche asyncio ; `async stop()`
  l'annule proprement ; `_loop()` = `while True: try run_cycle(ctx.config, ctx.search_service,
  ctx.transmission, history) except: log ; await sleep(max(ctx.config.monitor.interval_minutes,1)*60)`.
  Le loop relit `ctx.config` à chaque tour → les changements (hot-reload) s'appliquent.

### 4.5 Câblage (`torsearch/main.py`, `torsearch/web/routes.py`)

- `create_app(ctx, history=None, monitor=None)` : pose `app.state.ctx`, `app.state.history` ;
  monte les routers (recherche, settings, downloads, **surveillance**) ; **lifespan** FastAPI qui
  démarre/arrête `monitor` **s'il est fourni** (donc inactif dans les tests web qui passent
  `monitor=None`). Rétro-compatible : les appels `create_app(ctx)` existants restent valides.
- `build_app` : construit `MonitorHistory` (chemin via env `TORSEARCH_MONITOR` défaut
  `data/monitor.json`) + `MonitorRunner(ctx, history)`, passés à `create_app`.

### 4.6 Web (`torsearch/web/surveillance_routes.py` + templates)

`surveillance_router` (HTMX, fragments + toasts comme les réglages) :

| Méthode & route | Effet |
|---|---|
| `GET /surveillance` | Page : réglage global (on/off + intervalle), formulaire d'ajout, liste des recherches, historique. |
| `POST /surveillance/monitor` | `set_monitor(...)` via `ctx.update_settings`. |
| `POST /surveillance/searches` | `add_saved_search(...)` (nom, requête, catégorie, filtres, mode). |
| `POST /surveillance/searches/{name}/toggle` | `set_saved_search_enabled(...)`. |
| `POST /surveillance/searches/{name}/delete` | `remove_saved_search(...)`. |

L'historique affiche `app.state.history.records()` ; les lignes `found` ont un bouton
« Envoyer » (`hx-post="/download"`, réutilise l'endpoint existant). Lien nav « Surveillance »
ajouté à `base.html`.

## 5. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Une recherche du cycle échoue | `try/except` par recherche → ignorée, les autres continuent. |
| `transmission.add` échoue (mode auto) | Loggé ; **pas** d'enregistrement (on ré-essaiera au prochain cycle). |
| Saisie invalide / nom en double (UI) | Bannière d'erreur, rien n'est sauvegardé (comme la page Réglages). |
| Historique injoignable / `monitor=None` (tests) | La page rend une liste vide ; pas de 500. |

## 6. Tests (pytest, hors-ligne)

- **mutations** : add (+ refus doublon), remove, toggle, set_monitor — chacune renvoie un nouveau `Config` sans muter l'entrée.
- **`MonitorHistory`** : `add` + `records` (ordre récent d'abord), `seen_keys` par recherche, round-trip persistance, écriture atomique.
- **`select_new`** : choisit le meilleur nouveau ; saute les `seen` ; respecte les filtres ; `None` si rien de nouveau.
- **`run_cycle`** (faux `search_service`, fausse `transmission`, `MonitorHistory` temp) :
  - mode `auto` → envoie à Transmission **et** enregistre `grabbed` ;
  - mode `notify` → enregistre `found` **sans** envoi ;
  - 2ᵉ passage → rien (déjà vu) ;
  - `monitor.enabled = False` → `[]` ;
  - recherche désactivée → ignorée ;
  - une recherche qui lève → les autres aboutissent.
- **`MonitorRunner`** : `start` programme une tâche, `stop` l'annule proprement (test léger, sans attendre un cycle réel).
- **Web /surveillance** (`TestClient`, `AppContext` réel sur store temp + `MonitorHistory` temp,
  `monitor=None`) : page rend réglage global + recherches + historique ; add/toggle/delete
  mettent à jour `ctx.config` ; `POST /surveillance/monitor` met à jour `monitor` ; item `found`
  porte un bouton « Envoyer ».

## 7. Fichiers

| Fichier | Action |
|---|---|
| `torsearch/config.py` | Modifier — `SavedSearch`, `MonitorConfig`, champs `Config`. |
| `torsearch/settings/mutations.py` | Modifier — mutations recherches + monitor. |
| `torsearch/monitor/__init__.py` | Créer (vide). |
| `torsearch/monitor/history.py` | Créer — `MonitorRecord`, `MonitorHistory`. |
| `torsearch/monitor/runner.py` | Créer — `grab_key`, `select_new`, `run_cycle`, `MonitorRunner`. |
| `torsearch/web/surveillance_routes.py` | Créer — `surveillance_router`. |
| `torsearch/web/templates/surveillance.html` + partials | Créer. |
| `torsearch/web/routes.py` | Modifier — `create_app(ctx, history, monitor)` + lifespan + mount. |
| `torsearch/main.py` | Modifier — historique + runner + câblage. |
| `torsearch/web/templates/base.html` | Modifier — lien nav. |
| `tests/test_monitor_history.py`, `tests/test_monitor_runner.py`, `tests/test_surveillance_web.py`, `tests/test_settings_mutations.py` (étendu) | Créer/modifier. |

## 8. Notes

- **Sécurité par défaut** : `monitor.enabled = False` → aucune action automatique tant que
  l'utilisateur n'a pas activé la surveillance dans l'UI.
- Le `MonitorRunner` n'est démarré qu'en production (via `build_app` + lifespan) ; les tests
  web passent `monitor=None`, donc déterministes. La logique (`run_cycle`) est testée à part.
- L'historique est append-only ; pour un usage perso, pas de purge automatique en F2.
