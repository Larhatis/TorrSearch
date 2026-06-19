# F1 — Filtres + tri des résultats — Spec de conception

> Date : 2026-06-19
> Statut : approuvé (carte blanche), en implémentation
> Construit sur v1.1 (page Réglages + hot-reload).

## 1. Contexte & objectif

Une recherche peut renvoyer des dizaines/centaines de lignes brutes triées par seeders.
Objectif : pouvoir **filtrer** et **trier** les résultats pour trouver vite le bon torrent.

## 2. Périmètre

### Dans F1 (in scope)

- **Filtres** (panneau « Filtres » repliable du formulaire de recherche) :
  - **Seeders minimum** (entier).
  - **Taille** min / max (en Go, convertie en octets).
  - **Qualité** : cases à cocher par palier de résolution — `2160p`, `1080p`, `720p`, `480p`, `autre` (vide = toutes). Détectée depuis le titre.
  - **Exclure ces mots** : champ texte ; un résultat dont le titre contient l'un de ces mots (insensible à la casse) est écarté.
- **Tri** : en-têtes de colonnes cliquables (`nom`, `taille`, `seeders`, `leechers`, `date`), ascendant/descendant, avec indicateur ▲/▼. Défaut : `seeders` décroissant (comportement actuel).
- Tout **côté serveur**, re-requête via HTMX (cohérent avec l'existant). 100 % testable hors-ligne.

### Hors F1 (plus tard)

Badges qualité dans le tableau · sauvegarde des filtres par défaut · pagination · filtres
côté client. (Les badges et la pagination étaient déjà notés comme « pour plus tard ».)

## 3. Architecture

### 3.1 Module pur `torsearch/search/filters.py`

- `Quality` : on n'introduit **pas** d'enum lourde ; les paliers sont des chaînes
  (`"2160p"`, `"1080p"`, `"720p"`, `"480p"`, `"other"`).
- `detect_quality(title: str) -> str` : regex sur le titre →
  `2160p|4k|uhd → "2160p"` ; `1080p → "1080p"` ; `720p → "720p"` ; `480p|sd → "480p"` ; sinon `"other"`.
- `ResultFilters` (Pydantic) : critères + tri.
  - `min_seeders: int = 0`
  - `min_size: int | None = None` (octets) · `max_size: int | None = None` (octets)
  - `qualities: list[str] = []` (vide = toutes)
  - `exclude: list[str] = []` (mots en minuscule)
  - `sort: str = "seeders"` (∈ `{title, size, seeders, leechers, date}`)
  - `direction: str = "desc"` (∈ `{asc, desc}`)
- `apply(results: list[SearchResult], filters: ResultFilters) -> list[SearchResult]` :
  1. filtre seeders ≥ min ;
  2. filtre taille dans [min_size, max_size] si fournis ;
  3. filtre qualité : garde si `qualities` vide **ou** `detect_quality(title) ∈ qualities` ;
  4. filtre exclusion : écarte si un mot de `exclude` est sous-chaîne du titre (casse ignorée) ;
  5. trie selon `sort`/`direction` (clé `date` → `publish_date or datetime.min`, `title` → casse ignorée).

> `SearchService` reste inchangé (il renvoie fusionné/dédoublonné, trié seeders desc) ; `apply`
> ré-trie selon le choix utilisateur. Séparer « agrégation » (service) et « présentation »
> (filtres) garde chaque unité simple.

### 3.2 Route `/search` (`torsearch/web/routes.py`)

Accepte, en plus de `q`/`cat`, des paramètres optionnels :
`min_seeders`, `min_size_gb`, `max_size_gb`, `quality` (répété), `exclude`, `sort`, `dir`.
La route construit un `ResultFilters` (conversion Go→octets, split de `exclude`, validation des
valeurs `sort`/`dir` avec repli sur les défauts si invalide), appelle
`ctx.search_service.search(q, cat)` puis `filters.apply(...)`, et rend `partials/results.html`
en lui passant aussi l'état de tri courant (`sort`, `dir`).

### 3.3 UI

- **`index.html`** : sous la barre de recherche, un `<details>` « Filtres » contenant les
  champs (seeders min, tailles, cases qualité, exclure). Le formulaire `GET /search`
  (HTMX, `hx-target="#results"`) embarque tous ces champs.
- **`partials/results.html`** : les en-têtes de colonnes deviennent des liens HTMX
  (`hx-get="/search"`, `hx-include="#search-form"`, `hx-vals` portant `sort` + `dir`). La
  direction est calculée dynamiquement : si la colonne est déjà le tri courant en `asc`, le
  clic suivant envoie `desc` (et inversement) ; un indicateur ▲/▼ s'affiche sur la colonne active.
  Les filtres ne sont **pas** dupliqués dans `hx-vals` (ils viennent de `hx-include` du formulaire).

## 4. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Paramètre numérique invalide (`min_seeders=abc`) | Ignoré → repli sur le défaut (pas de filtre). |
| `sort`/`dir` inconnu | Repli sur `seeders`/`desc`. |
| `exclude` vide | Aucun filtre d'exclusion. |
| Aucun résultat après filtrage | Le placeholder « Aucun résultat » existant s'affiche. |

La route reste robuste : des filtres mal formés ne provoquent jamais d'erreur 500, juste un
repli sur les défauts.

## 5. Tests (pytest, hors-ligne)

- **`detect_quality`** : titres variés (`...2160p...`, `4K`, `1080p`, `720p`, `480p`, sans marqueur → `other`).
- **`apply`** : seeders min ; bornes de taille ; sous-ensemble qualité ; exclusion (casse ignorée) ; chaque champ de tri × direction ; combinaison filtres+tri.
- **Route `/search`** : avec `min_seeders`/`quality`/`exclude` → résultats filtrés ; `sort=size&dir=asc` → ordre correct ; paramètre invalide → repli sans 500 ; en-têtes triables présents dans le HTML.

## 6. Fichiers

| Fichier | Action |
|---|---|
| `torsearch/search/filters.py` | Créer — `detect_quality`, `ResultFilters`, `apply`. |
| `torsearch/web/routes.py` | Modifier — `/search` parse les filtres + tri, applique `filters.apply`. |
| `torsearch/web/templates/index.html` | Modifier — panneau « Filtres » + `id="search-form"`. |
| `torsearch/web/templates/partials/results.html` | Modifier — en-têtes triables + indicateur de tri. |
| `tests/test_filters.py` | Créer. |
| `tests/test_web.py` | Modifier — cas de filtrage/tri sur `/search`. |

## 7. Notes

- La détection de qualité est heuristique (basée sur le titre) : un titre sans marqueur tombe
  dans `other`. Suffisant pour un usage perso ; améliorable plus tard.
- Conversion taille : l'UI saisit des **Go** ; la route convertit en octets (`× 1024³`) avant
  de construire `ResultFilters` (qui raisonne en octets, comme `SearchResult.size`).
