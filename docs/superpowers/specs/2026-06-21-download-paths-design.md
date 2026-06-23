# Routage des téléchargements par catégorie — Design

**Date :** 2026-06-21
**Statut :** validé

## Objectif

Placer automatiquement chaque torrent dans le bon dossier de destination selon sa **catégorie**
(films → un disque, séries → un autre), au lieu de changer le chemin à la main dans Transmission.
C'est l'équivalent des « root folders » de Sonarr/Radarr.

Design **scalable** (le projet n'est pas que pour un seul utilisateur) : une table
`catégorie → dossier` qui couvre toutes les catégories connues de l'app et s'étend sans code en dur.
Chacun remplit les chemins qu'il utilise ; les autres restent au dossier par défaut de Transmission.

Non-objectifs : déplacement/rangement de fichiers post-téléchargement, renommage, sous-dossiers
par titre/saison, chemins par tracker, multi-clients de téléchargement.

## Mécanique (Transmission)

`torrent-add` accepte un `download-dir` par torrent. Aujourd'hui `TransmissionClient.add` ne le
passe pas — c'est le seul manque. On étend `add(download_url, download_dir=None)` ; `None` → dossier
par défaut de Transmission (comportement actuel inchangé).

⚠️ Les chemins sont ceux **vus par Transmission** (dans son conteneur Docker le cas échéant), pas
ceux de l'OS hôte.

## Composants & fichiers

### 1. Config — `torsearch/config.py` (modifié)

`PathsConfig(BaseModel, frozen)` :
- `by_category: dict[str, str] = {}` (clé = valeur de `Category`, ex. `"movies"`, `"tv"`,
  `"anime"`, `"other"` ; valeur = chemin).
- `for_category(self, category: Category) -> str | None` :
  `return self.by_category.get(category.value) or None`.

Ajouté à `Config` : `paths: PathsConfig = Field(default_factory=PathsConfig)`.
(`config.py` importe déjà `Category`.)

### 2. Client — `torsearch/transmission/client.py` (modifié)

`add(self, download_url: str, download_dir: str | None = None) -> int` :
`add_torrent(download_url, download_dir=download_dir)` (transmission-rpc ignore/omet un
`download_dir=None`).

### 3. Auto-grab — `torsearch/monitor/runner.py` (modifié)

- `run_movie_cycle` : `transmission.add(pick.download_url, download_dir=config.paths.for_category(Category.MOVIES))`.
- `run_series_cycle` : `transmission.add(r.download_url, download_dir=config.paths.for_category(Category.TV))`.

### 4. Envoi manuel — `torsearch/web/routes.py` (modifié)

Route `/download` : ajouter `category: str = Form("")`. Résoudre une `Category` de façon tolérante
(valeur inconnue → `Category.OTHER`), puis
`download_dir = ctx.config.paths.for_category(category)` ;
`ctx.transmission.add(download_url, download_dir)`.

`partials/results.html` : le formulaire « Envoyer » de chaque ligne porte la catégorie du résultat :
`<input type="hidden" name="category" value="{{ r.category.value }}">`. (Chaque `SearchResult` a
déjà un champ `category`.) Résultat non catégorisé (`other`) → dossier par défaut.

### 5. Réglages — section « Dossiers de téléchargement »

`settings_page` passe `categories = list(Category)`. `settings.html` ajoute une section : une ligne
de chemin **par catégorie** (on itère `Category`, on saute `all`), `name="path_<catégorie>"`,
pré-rempli depuis `config.paths.by_category`. `POST /settings/paths` lit le formulaire de façon
**générique** (collecte tous les `path_*` non vides) → `set_paths` (mutation) → `ctx.update_settings`.

## Flux de données

1. Réglages → l'utilisateur saisit Films `/data/films`, Séries `/data/series` → `data/settings.json`.
2. Auto-grab : le moteur résout le dossier via la catégorie connue → Transmission place au bon endroit.
3. Envoi manuel : la catégorie du résultat → `for_category` → `download-dir` à l'ajout.

## Gestion des erreurs / cas limites

- Chemin vide / catégorie absente de la map → `download_dir = None` → défaut Transmission
  (comportement actuel ; aucune régression pour qui ne configure rien).
- Catégorie de formulaire inconnue/illisible → `Category.OTHER` → défaut (sauf si `other` mappé).
- Transmission refuse un chemin inexistant → l'erreur remonte déjà via le toast `/download`
  (et est loggée + ignorée par cycle dans l'auto-grab, sans casser le cycle).

## Tests

- `tests/test_config.py` : `PathsConfig` défaut vide ; `for_category` renvoie le chemin ou `None` ;
  chargement YAML d'une map `paths.by_category`.
- `tests/test_transmission.py` : `add(url, download_dir="/x")` transmet `download_dir` à
  `add_torrent` ; `add(url)` n'impose pas de dossier (passe `None`).
- `tests/test_monitor_runner.py` : `run_movie_cycle` appelle `add` avec le chemin films ;
  `run_series_cycle` avec le chemin séries (le `FakeTransmission` enregistre `download_dir`).
- `tests/test_web.py` : `POST /download` avec `category=movies` appelle `transmission.add` avec le
  chemin films ; sans chemin configuré → `None`.
- `tests/test_settings_web.py` : `POST /settings/paths` met à jour `config.paths.by_category`.
- Non-régression : suite existante (240) verte (les `FakeTransmission.add` acceptent `download_dir`).
