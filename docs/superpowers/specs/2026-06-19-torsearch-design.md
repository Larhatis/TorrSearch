# TorSearch — Spec de conception (v1)

> Date : 2026-06-19
> Statut : en relecture

## 1. Contexte & objectif

Configurer Sonarr / Radarr / Prowlarr pour brancher des trackers est jugé trop
fastidieux par l'utilisateur. **TorSearch** est un petit outil web perso, auto-hébergé,
qui résout un seul problème simplement :

> Chercher un film / une série sur **plusieurs trackers à la fois**, et envoyer le
> résultat choisi directement à **Transmission**.

C'est l'équivalent allégé et sur-mesure de Prowlarr, sans la lourdeur de configuration.

## 2. Utilisateur & usage

- **Profil** : développeur Python, usage personnel.
- **Déploiement** : conteneur Docker (tourne en permanence), accès via navigateur.
- **Pas de multi-utilisateur, pas d'authentification de l'app en v1** (réseau local / privé).

## 3. Périmètre

### Dans la v1 (in scope)

- Recherche **agrégée multi-trackers** via le protocole **Torznab**.
- 2 trackers préconfigurés, tous deux en Torznab :
  - **torr9** — `https://api.torr9.net/api/v1/torznab` + passkey (API key).
  - **c411** — `https://c411.org/api` + API key.
- Résultats **normalisés**, **dédoublonnés**, **triés par seeders** (décroissant).
- Filtre par **catégorie** : Tout / Films / Séries / Anime.
- **Envoi à Transmission** (magnet ou `.torrent`) via son API RPC.
- Bouton **« Copier le magnet »**.
- Page **statut des trackers** (activé / configuré / a répondu).
- Configuration via un fichier **`config.yaml`** (trackers + connexion Transmission).
- Packaging **Docker** (`Dockerfile` + `docker-compose.yml`).

### Hors v1 (pour plus tard)

Authentification de l'app · historique de recherche · intégration Sonarr/Radarr ·
support Cloudflare (FlareSolverr) · scrapers HTML pour sites sans API · édition de la
config depuis l'UI · notifications · gestion des téléchargements en cours.

> Note : le module scraper HTML n'est **pas** construit en v1 (les deux trackers ont une
> API Torznab), mais l'interface `Indexer` est conçue pour l'accueillir sans refonte.

## 4. Architecture

### 4.1 Vue d'ensemble

```
Navigateur (HTMX)
      │
      ▼
FastAPI  ──────────────┐  (sert l'UI + l'API)
  │                    │
  ▼                    ▼
SearchService      TransmissionClient
  │ (asyncio.gather)        │ (RPC)
  ├── TorznabIndexer(torr9) ▼
  └── TorznabIndexer(c411)  Transmission
```

Chaque indexer implémente la même interface, donc l'orchestrateur est agnostique du type
de tracker (Torznab aujourd'hui, scraper HTML demain).

### 4.2 Modules

| Module | Responsabilité |
|---|---|
| `app/models.py` | Modèles Pydantic : `SearchResult`, enum `Category`, modèles de config. |
| `app/config.py` | Charge et valide `config.yaml` (+ interpolation de variables d'env pour les secrets). Échoue vite au démarrage si invalide. |
| `app/indexers/base.py` | Classe abstraite `Indexer` : `name`, `enabled`, `async search(query, category) -> list[SearchResult]`. |
| `app/indexers/torznab.py` | `TorznabIndexer` générique : construit la requête Torznab, appelle l'API (httpx), parse le XML, mappe les catégories. Ne lève jamais vers l'orchestrateur (renvoie `[]` + log en cas d'erreur). |
| `app/indexers/registry.py` | Instancie les indexers activés à partir de la config. |
| `app/search/service.py` | `SearchService` : fan-out parallèle (`asyncio.gather`) avec timeout par indexer, fusion, dédoublonnage, tri par seeders. Résilient : un tracker en échec n'arrête pas la recherche. |
| `app/transmission/client.py` | `TransmissionClient` (wrapper `transmission-rpc`) : `add(download_url) -> id`. |
| `app/web/routes.py` | Routes FastAPI + rendu Jinja2/HTMX. |
| `app/main.py` | Point d'entrée uvicorn, montage des routes, chargement de la config. |

### 4.3 Modèle `SearchResult`

| Champ | Type | Note |
|---|---|---|
| `title` | `str` | Nom du torrent. |
| `size` | `int` | Octets. |
| `seeders` | `int` | |
| `leechers` | `int` | |
| `source` | `str` | Nom du tracker (`torr9`, `c411`). |
| `category` | `Category` | Enum normalisée. |
| `download_url` | `str` | Magnet ou URL `.torrent`. |
| `is_magnet` | `bool` | Dérivé de `download_url`. |
| `info_url` | `str \| None` | Page de détail sur le tracker. |
| `publish_date` | `datetime \| None` | |
| `infohash` | `str \| None` | Pour le dédoublonnage. |

### 4.4 Catégories

Enum `Category` : `ALL`, `MOVIES`, `TV`, `ANIME`, `OTHER`.

Mapping vers les identifiants de catégorie Newznab/Torznab (ex. `2000` films, `5000` séries,
`5070` anime), avec des valeurs par défaut raisonnables et un **override possible par
tracker** dans le `config.yaml` (les trackers ne numérotent pas toujours pareil).

### 4.5 Protocole Torznab (rappel d'implémentation)

- **Recherche** : `GET {url}?t=search&q={query}&apikey={key}[&cat={ids}]`
  (variantes `t=tvsearch`, `t=movie` selon la catégorie).
- **Réponse** : flux RSS/XML ; chaque `<item>` porte titre, `<enclosure url=... length=...>`
  (URL de téléchargement + taille) et des `<torznab:attr name="seeders|peers|..." value=...>`.
- **Auth** : la clé passe en **paramètre d'URL `apikey`** (standard Torznab pour la recherche).
  Le `Authorization: Bearer` vu côté c411 concerne l'endpoint d'**upload**, non utilisé ici.
  → `TorznabIndexer` supporte néanmoins deux modes d'auth configurables
  (`auth: query` par défaut, ou `auth: bearer`) pour ne pas être bloqué si un tracker diffère.
- **Parsing XML** : via `defusedxml` (parsing sûr).

### 4.6 Flux de recherche

1. L'utilisateur saisit une requête + catégorie dans l'UI.
2. `GET /search?q=...&cat=...` appelle `SearchService.search`.
3. `SearchService` interroge chaque indexer activé **en parallèle** (timeout ~10 s chacun).
4. Chaque `TorznabIndexer` appelle son API, parse le XML, renvoie `list[SearchResult]`.
5. Fusion → dédoublonnage (par `infohash`, sinon `title`+`size`) → tri par seeders décroissant.
6. Renvoi d'un **fragment HTMX** qui rend le tableau des résultats.

### 4.7 Flux de téléchargement

1. Clic sur « ➕ Transmission » d'une ligne → `POST /download` avec `download_url`.
2. `TransmissionClient.add()` envoie à Transmission via RPC.
3. Renvoi d'un petit toast succès/erreur (swap HTMX).

### 4.8 Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Indexer down / timeout / HTTP / XML invalide | Log warning, `[]` pour ce tracker, la recherche continue ; l'UI indique quels trackers ont répondu. |
| Transmission injoignable | Toast d'erreur explicite. |
| Config invalide au démarrage | Arrêt immédiat avec message clair. |

## 5. Interface web

- **Page recherche (`/`)** : barre de recherche + sélecteur de catégorie → tableau de
  résultats **triable** (nom · taille · seeders · leechers · badge source). Chaque ligne :
  boutons « ➕ Transmission » et « 📋 Copier magnet ». HTMX = pas de rechargement de page,
  avec état de chargement.
- **Page trackers (`/trackers`)** : liste des trackers, statut (activé / configuré / dernier
  résultat de recherche).
- **Style** : Jinja2 + HTMX + Tailwind (via CDN). Fonctionnel et minimal, pas de build JS.

## 6. Configuration (`config.yaml`)

```yaml
transmission:
  host: localhost
  port: 9091
  username: ""
  password: ""
  https: false

search:
  timeout_seconds: 10

indexers:
  - name: torr9
    type: torznab
    url: https://api.torr9.net/api/v1/torznab
    api_key: ${TORR9_API_KEY}     # interpolé depuis l'env / .env
    auth: query                   # query (défaut) | bearer
    enabled: true
  - name: c411
    type: torznab
    url: https://c411.org/api
    api_key: ${C411_API_KEY}
    auth: query
    enabled: true
```

- Les clés API **ne sont jamais commitées** : interpolation depuis l'environnement / un
  `.env` (gitignoré). Fournir `config.example.yaml` et `.env.example`.

## 7. Packaging Docker

- **`Dockerfile`** : base `python:3.12-slim`, install des dépendances, `CMD uvicorn`.
- **`docker-compose.yml`** : service `torsearch` (port `8080:8000`), volume `./config:/config`
  pour `config.yaml`, `env_file: .env`. Documenter la connexion réseau vers Transmission.

## 8. Tests (pytest)

| Cible | Test |
|---|---|
| `TorznabIndexer` | Parsing contre des **fixtures XML** sauvegardées (titre/taille/seeders/magnet, mapping catégorie) ; gestion d'erreur (XML malformé, HTTP en échec via `respx`/httpx mock). |
| `SearchService` | Faux indexers (un OK, un qui timeout/lève) → vérifie fusion/dédoublonnage/tri **et** résilience. |
| `TransmissionClient` | `transmission-rpc` mocké → `add()` appelé avec le bon magnet. |
| `config` | Chargement YAML valide/invalide, interpolation des variables d'env. |
| Web | `TestClient` : routes `200`, fragment résultats rendu, `/download` appelle le client. |

Aucun test ne touche le réseau réel (fixtures + mocks) → la suite ne casse pas quand un
tracker est down.

## 9. Stack & dépendances

`fastapi` · `uvicorn[standard]` · `httpx` · `pydantic` · `pydantic-settings` · `jinja2` ·
`python-multipart` · `transmission-rpc` · `pyyaml` · `defusedxml` · `pytest` ·
`pytest-asyncio` · `respx`. HTMX + Tailwind via CDN.

## 10. Arborescence projet

```
torsearch/
  app/
    __init__.py
    main.py
    config.py
    models.py
    indexers/
      __init__.py
      base.py
      torznab.py
      registry.py
    search/
      __init__.py
      service.py
    transmission/
      __init__.py
      client.py
    web/
      routes.py
      templates/
        base.html
        index.html
        trackers.html
        partials/results.html
      static/
  tests/
    fixtures/
    test_torznab.py
    test_search.py
    test_transmission.py
    test_config.py
    test_web.py
  config.example.yaml
  .env.example
  .gitignore
  Dockerfile
  docker-compose.yml
  pyproject.toml
  README.md
```

## 11. Risques & points ouverts

- **Mode d'auth c411** : on part sur `apikey` en query (standard Torznab). Si l'API de c411
  exige la clé autrement, le mode `auth: bearer` du `TorznabIndexer` couvre le cas → à
  vérifier au premier test réel.
- **Catégories hétérogènes** : numérotation Newznab variable selon les trackers → defaults +
  override par tracker dans le YAML.
- **Domaines mouvants** : torr9/c411 peuvent changer de domaine → l'URL étant en config, on
  édite une ligne (pas de code).
- **Cadre légal** : TorSearch est un outil de recherche/agrégation (comme Prowlarr/Jackett) ;
  l'usage et le respect du droit d'auteur relèvent de l'utilisateur. Aucun identifiant n'est
  embarqué dans le code.
