# TorSearch — Réglages via l'UI (v1.1) — Spec de conception

> Date : 2026-06-19
> Statut : en relecture
> Construit par-dessus la v1 (`docs/superpowers/specs/2026-06-19-torsearch-design.md`).

## 1. Contexte & objectif

En v1, toute la configuration (trackers, connexion Transmission, timeout) se fait en
éditant `config.yaml` à la main, et tout changement exige un redémarrage. C'est précisément
le genre de friction que TorSearch veut éviter.

> **Objectif :** rendre **toute** la configuration éditable depuis une page **Réglages** dans
> le navigateur, avec **application immédiate** (sans redémarrage), et un bouton **« Tester »**
> par tracker pour vérifier qu'URL + passkey répondent.

## 2. Périmètre

### Dans la v1.1 (in scope)

- Page **Réglages** éditant :
  - **Trackers** : ajouter / modifier / supprimer / activer-désactiver (nom, URL, passkey, mode d'auth, catégories par défaut implicites).
  - **Transmission** : hôte, port, identifiants, https.
  - **Recherche** : timeout.
- Persistance dans **`data/settings.json`** (source de vérité runtime, gitignoré).
- **Amorçage** depuis `config.yaml` au tout premier démarrage uniquement.
- **Hot-reload** : une sauvegarde reconstruit les services en mémoire ; la recherche suivante utilise la nouvelle config.
- Bouton **« Tester »** par tracker (appel Torznab `t=caps`) avec retour ✅ / ❌ + raison.
- La page **« Trackers »** lecture-seule de la v1 est **remplacée** par la page Réglages.

### Hors v1.1 (plus tard)

Test de connexion Transmission · authentification / multi-utilisateur · import des
définitions Prowlarr/Jackett · historique des changements · édition des catégories par tracker
dans l'UI (les valeurs par défaut restent celles de la v1, override possible en éditant
`settings.json`).

## 3. Décisions de conception (issues du brainstorming)

| Sujet | Décision |
|---|---|
| Périmètre éditable | Tout (trackers + Transmission + recherche). |
| Stockage | Fichier dédié `data/settings.json`. `config.yaml` = amorçage initial seulement. |
| Application | Hot-reload immédiat à la sauvegarde. |
| Test tracker | Oui, dans cette itération. |
| Page Trackers v1 | Remplacée par la page Réglages. |
| Hot-reload, structure | Conteneur `AppContext` (option A) ; pas d'observateur ni de reconstruction éparpillée. |

## 4. Architecture

### 4.1 Vue d'ensemble

```
Navigateur (HTMX)
   │  GET/POST /settings/*
   ▼
settings_routes ──► AppContext.update_settings(new_config)
                        │ 1. SettingsStore.save(config)  → data/settings.json (atomique)
                        │ 2. rebuild: build_indexers → SearchService, TransmissionClient
                        ▼
              app.state.ctx.{search_service, transmission, config}
                        ▲
   /search, /download, /trackers(→/settings) lisent les services via ctx
```

### 4.2 `SettingsStore` (`torsearch/settings/store.py`)

Persistance pure, sans logique métier. Réutilise les modèles Pydantic existants
(`Config`, `IndexerConfig`, `TransmissionConfig`, `SearchConfig`) : `settings.json` est un
`Config` sérialisé.

- `__init__(settings_path: Path, bootstrap_config_path: Path | None)`.
- `load() -> Config` :
  1. Si `settings_path` existe → le parse en `Config` et le renvoie.
  2. Sinon si `bootstrap_config_path` existe → `load_config()` v1 (résout les `${VAR}`), écrit le résultat dans `settings_path`, le renvoie.
  3. Sinon → `Config()` vide (0 tracker, Transmission par défaut). L'app démarre quand même.
- `save(config: Config) -> None` : écriture **atomique** (écrit `settings.json.tmp` puis `os.replace`), crée le dossier `data/` si absent.

### 4.3 `AppContext` (`torsearch/context.py`)

Possède le store, la config courante et les services ; seul endroit qui sait recharger.

- `__init__(store: SettingsStore)` : `self._store = store`, `self._config = store.load()`, puis `self._rebuild()`.
- Propriétés : `config -> Config`, `search_service -> SearchService`, `transmission -> TransmissionClient`.
- `_rebuild()` : `indexers = build_indexers(self._config)` ; `self._search_service = SearchService(indexers, timeout=self._config.search.timeout_seconds)` ; `self._transmission = TransmissionClient(self._config.transmission)`.
- `update_settings(new_config: Config) -> None` : `self._store.save(new_config)` ; `self._config = new_config` ; `self._rebuild()`.

> `TransmissionClient` se connecte paresseusement, donc reconstruire ne touche pas le réseau.

### 4.4 Mutations de config (helpers, dans `torsearch/settings/mutations.py`)

Fonctions pures qui prennent un `Config` et renvoient un **nouveau** `Config` modifié (immutabilité ⇒ faciles à tester) ; elles valident l'unicité du **nom** de tracker (clé d'identité) :

- `add_indexer(config, indexer: IndexerConfig) -> Config` (erreur si nom déjà pris).
- `update_indexer(config, name: str, indexer: IndexerConfig) -> Config` (erreur si nom absent ; si le nom change, erreur si le nouveau nom collisionne).
- `remove_indexer(config, name: str) -> Config`.
- `set_indexer_enabled(config, name: str, enabled: bool) -> Config`.
- `set_general(config, transmission: TransmissionConfig, search: SearchConfig) -> Config`.

Les erreurs lèvent un `SettingsError` (exception du module) avec un message lisible.

### 4.5 Test de tracker (`torsearch/indexers/torznab.py`)

Ajouter à `TorznabIndexer` :

- `async def test() -> tuple[bool, str]` : `GET {url}?t=caps` (+ `apikey` ou header Bearer selon `auth`). Renvoie :
  - `(True, "OK")` si HTTP 200 **et** la racine XML est `<caps>` ;
  - `(False, "<raison>")` sinon (HTTP 401/403 → « clé refusée », timeout → « pas de réponse », XML invalide → « réponse inattendue », etc.).

### 4.6 Page Réglages & routes (`torsearch/web/settings_routes.py` + templates)

Nouveau `APIRouter`, monté par `create_app`. Toutes les réponses sont des fragments HTMX
(re-rendu de la liste des trackers ou toast).

| Méthode & route | Effet |
|---|---|
| `GET /settings` | Rend `settings.html` : formulaire général (Transmission + recherche) + liste des trackers. |
| `POST /settings/general` | Valide puis `ctx.update_settings(set_general(...))` ; toast. |
| `POST /settings/indexers` | Ajoute un tracker (`add_indexer`) ; re-rend la liste + toast. |
| `POST /settings/indexers/{name}` | Modifie un tracker (`update_indexer`) ; re-rend la liste + toast. |
| `POST /settings/indexers/{name}/delete` | Supprime (`remove_indexer`) ; re-rend la liste. |
| `POST /settings/indexers/{name}/toggle` | Active/désactive (`set_indexer_enabled`) ; re-rend la ligne. |
| `POST /settings/indexers/test` | Construit un `TorznabIndexer` temporaire **depuis les champs du formulaire** (test avant sauvegarde) et renvoie un toast ✅/❌. |

Templates : `settings.html` (étend `base.html`), partials `partials/indexer_list.html`,
`partials/indexer_row.html`, réutilise `partials/toast.html`. Le menu passe de
« Trackers » à **« Réglages »** (`base.html`) ; la route `/trackers` est supprimée.

### 4.7 Câblage (`torsearch/main.py`)

`build_app` construit un `SettingsStore` (chemins via env : `TORSEARCH_SETTINGS`
défaut `data/settings.json`, `TORSEARCH_CONFIG` défaut `config.yaml` pour l'amorçage), puis
un `AppContext`, passé à `create_app`. `create_app(ctx)` stocke `app.state.ctx` et monte les
deux routers (recherche + réglages).

### 4.8 Routes existantes (`torsearch/web/routes.py`)

`/search` et `/download` lisent désormais `request.app.state.ctx.search_service` /
`.transmission`. La route `/trackers` est retirée (remplacée par `/settings`).

## 5. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Champ invalide (port non numérique, URL vide…) | `ValidationError` → re-rendu du formulaire avec message ; rien n'est sauvegardé. |
| Nom de tracker en double / inexistant | `SettingsError` → toast explicite ; config inchangée. |
| Échec d'écriture disque | Toast d'erreur ; l'état mémoire **n'est pas** modifié (on sauvegarde avant de reconstruire). |
| Test tracker en échec | Toast ❌ avec la raison ; aucune modification. |

## 6. Tests (pytest, 100 % hors-ligne)

- **`SettingsStore`** : amorçage depuis un `config.yaml` quand pas de `settings.json` ; chargement d'un `settings.json` existant ; round-trip `save`/`load` ; config vide si aucun fichier ; écriture atomique (le `.tmp` n'est pas laissé, `os.replace` utilisé).
- **mutations** : add (+ rejet doublon), update (+ rejet nom absent / collision au renommage), remove, toggle, set_general — chacune renvoie un nouveau `Config` correct sans muter l'entrée.
- **`AppContext`** : `update_settings` persiste **et** reconstruit (un tracker ajouté apparaît dans `ctx.search_service.indexers` ; un timeout changé est répercuté).
- **`TorznabIndexer.test()`** : caps 200 + `<caps>` → `(True, "OK")` ; 401 → `(False, …)` ; XML invalide → `(False, …)` (httpx mocké via respx).
- **Routes settings** : `GET /settings` rend formulaire + trackers ; add/edit/delete/toggle mettent à jour et re-rendent ; `test` renvoie le bon toast (indexer mocké). `TestClient` avec un `AppContext` bâti sur un `SettingsStore` pointant un fichier temporaire.
- **Non-régression** : `/search` et `/download` fonctionnent via `ctx`.

## 7. Fichiers

| Fichier | Action |
|---|---|
| `torsearch/settings/__init__.py` | Créer. |
| `torsearch/settings/store.py` | Créer — `SettingsStore`. |
| `torsearch/settings/mutations.py` | Créer — helpers purs + `SettingsError`. |
| `torsearch/context.py` | Créer — `AppContext`. |
| `torsearch/web/settings_routes.py` | Créer — router réglages. |
| `torsearch/web/templates/settings.html` | Créer. |
| `torsearch/web/templates/partials/indexer_list.html` | Créer. |
| `torsearch/web/templates/partials/indexer_row.html` | Créer. |
| `torsearch/indexers/torznab.py` | Modifier — `+ async def test()`. |
| `torsearch/web/routes.py` | Modifier — services via `ctx` ; retirer `/trackers`. |
| `torsearch/web/templates/base.html` | Modifier — nav « Trackers » → « Réglages ». |
| `torsearch/web/templates/trackers.html` | Supprimer. |
| `torsearch/main.py` | Modifier — construit `SettingsStore` + `AppContext`. |
| `.gitignore` | Modifier — `+ data/`. |
| `docker-compose.yml` | Modifier — `+ volume ./data:/data`, env `TORSEARCH_SETTINGS=/data/settings.json`. |
| `config.example.yaml` / `README.md` | Modifier — documenter le nouveau flux (config par l'UI, `data/` persistant). |

## 8. Risques & notes

- **Secrets en clair dans `data/settings.json`** : assumé (fichier gitignoré, volume local). C'est le compromis voulu pour une édition 100 % UI.
- **Identité par nom** : renommer un tracker = supprimer/recréer du point de vue de l'identité ; l'unicité est validée. Suffisant pour un usage perso.
- **Concurrence** : mono-utilisateur ; l'écriture atomique évite un fichier corrompu en cas d'arrêt pendant la sauvegarde.
- **`t=caps`** : standard Torznab ; si un tracker ne le supporte pas, le test pourra être basculé sur une recherche à vide plus tard (non nécessaire pour torr9/c411).
