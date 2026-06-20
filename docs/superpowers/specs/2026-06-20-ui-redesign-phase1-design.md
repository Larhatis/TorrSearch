# Redesign UI — Phase 1 (shell + écran Recherche) — Design

**Date :** 2026-06-20
**Statut :** validé

## Objectif

Rendre TorrSearch plus **ergonomique** sans changer sa stack ni sa philosophie de simplicité.
Phase 1 = le **shell partagé** (en-tête/nav) et l'**écran Recherche** (le cœur de l'app). Les
écrans Réglages / Téléchargements / Surveillance héritent du nouveau shell mais gardent leur
corps actuel ; ils seront repris dans des phases ultérieures (specs séparées).

Direction visuelle validée via maquette : thème dark slate/emerald conservé, lignes de résultat
aérées et scannables, filtres rendus visibles, indicateur de santé des seeders.

Non-objectifs (Phase 1) : redesign des autres pages, changement de framework/build, thème clair,
nouvelle pagination, infinite scroll.

## Contraintes techniques

- **Pas de build step.** On garde Tailwind Play CDN (`cdn.tailwindcss.com`), HTMX, Jinja.
- Ajout d'une seule dépendance front : la webfont **Tabler Icons** par CDN (`<link>`), pour les
  icônes de nav et d'actions.
- JS inline minimal, dans l'esprit de l'existant (déjà un `onclick` de copie presse-papier).
- Thème : dark slate (`slate-900/800/700`), accent `emerald-400/500`.

## Composants & fichiers

### 1. Shell — `templates/base.html` (modifié)

En-tête collant (`sticky top-0`) :
- Marque « TorrSearch » + icône.
- Nav à icônes (Recherche, Réglages, Téléchargements, Surveillance) avec **état actif** :
  le lien dont le préfixe correspond à `request.url.path` reçoit l'accent emerald + souligné.
  Helper de comparaison rendu en template (`request.url.path`).
- Bouton **Déconnexion** : inchangé, toujours conditionné à `auth_enabled` (préserve la feature
  d'auth déjà livrée).
- Ajout des `<link>`/`<script>` Tabler Icons + (déjà présents) Tailwind/HTMX dans `<head>`.

### 2. Composants réutilisables — `templates/partials/components.html` (créé)

Macros Jinja, réutilisables par les phases suivantes :
- `badge_quality(title)` → badge coloré selon `detect_quality(title)` :
  2160p (violet), 1080p (bleu), 720p (slate), 480p (slate), other (slate discret).
- `health(seeders)` → pastille + couleur du compteur : `>= 100` vert (emerald),
  `>= 10` ambre, `< 10` rouge.
- `source_chip(source)` → chip de la source (tracker).

`detect_quality` (déjà dans `torsearch/search/filters.py`) est exposé comme **global Jinja**
(enregistré dans `torsearch/web/templating.py`) pour être appelable dans les templates
(`{{ detect_quality(r.title) }}`), sans toucher au modèle (évite l'import circulaire
models ↔ filters).

### 3. Écran Recherche — `templates/index.html` (modifié)

- **Barre de recherche unifiée** : icône loupe + `input[name=q]` + `select[name=cat]` + bouton
  « Chercher », réunis dans un seul bloc arrondi. `hx-get="/search"` inchangé.
- **Panneau de filtres** : un bouton « Filtres » déplie un panneau (remplace l'actuel
  `<details>`) contenant les champs existants : `min_seeders`, `min_size_gb`, `max_size_gb`,
  `quality[]` (cases 2160p/1080p/720p/480p/other), `exclude`. Mêmes `name=` qu'aujourd'hui →
  la route `/search` est inchangée côté paramètres.
- Bannière onboarding « Aucun tracker configuré » conservée (restylée légèrement).
- `<div id="results">` inchangé comme cible HTMX.

### 4. Résultats — `templates/partials/results.html` (modifié)

- **Barre d'outils** : « N résultats » (+ liste des sources interrogées) à gauche ; contrôle de
  **tri** à droite (sélecteur sort/dir déclenchant `hx-get="/search"` + `hx-include="#search-form"`,
  même mécanique `hx-vals` que les en-têtes actuels — on remplace les `<th>` cliquables).
- **Puces de filtres actifs** : rendues côté serveur depuis les filtres effectifs passés par la
  route. Chaque puce a un « ✕ » qui efface ce filtre et relance la recherche via un petit helper
  JS (`clearFilter(name[, value])` : reset le champ correspondant dans `#search-form` puis
  `htmx.trigger('#search-form', 'submit')`). Qualité (multi) : le ✕ décoche cette valeur.
- **Lignes de résultat** (remplacent la table) : titre en avant (tronqué avec ellipsis) ; sous le
  titre `badge_quality` + `source_chip` + date ; à droite taille (Go), `health(seeders)`, bouton
  **« Envoyer »** (form `hx-post="/download"`, inchangé) + bouton-icône **Copier**
  (`navigator.clipboard`). Ligne grisée si `seeders < 10`.

### 5. Route `/search` — `torsearch/web/routes.py` (modifié, minime)

Passer au template `results.html` une structure **`active_filters`** (liste de
`{label, name, value}`) décrivant les filtres effectifs non vides, + `sources` (noms des trackers
interrogés) et le nombre de résultats. Aucune logique de recherche/tri modifiée. Le contrat des
query params reste identique.

## Flux de données

1. `index.html` : formulaire (recherche + panneau filtres) → `hx-get /search` → fragment
   `results.html` injecté dans `#results`.
2. `/search` construit `ResultFilters` (inchangé), applique (inchangé), puis calcule
   `active_filters` + `sources` et rend `results.html`.
3. Retrait d'un filtre : helper JS modifie `#search-form` et re-déclenche la soumission HTMX →
   nouveau fragment. Tri : `hx-vals` `{sort, dir}` + `hx-include="#search-form"`.

## Gestion des erreurs / cas limites

- Aucun résultat : message « Aucun résultat pour "q" » (conservé), dans le nouveau style.
- Filtres invalides (`min_seeders=abc`, tailles non numériques) : déjà tolérés par la route
  (`_to_int`/`_to_size_bytes`) → pas de 500 ; les puces n'affichent que les filtres effectifs.
- `publish_date` absent → « - » (conservé).
- Pas de tracker configuré → bannière onboarding.

## Tests

`tests/test_web.py` (mis à jour) + éventuel `tests/test_components.py` :
- **Mises à jour** : les assertions liées à l'ancien markup (en-têtes `"Seed"`, structure
  `<table>`, `hx-vals` sur `<th>`) deviennent des assertions sur le nouveau markup (présence du
  contrôle de tri avec `hx-vals`, lignes de résultat). Les assertions de fond inchangées
  (un titre présent/absent selon filtre, tri asc/desc par position dans le texte) restent.
- **Nouveaux** :
  - badge qualité : un résultat « ...1080p... » rend le libellé `1080p` ; « ...2160p... » → `2160p`.
  - santé : `seeders >= 100` rend la classe/couleur « good » ; `< 10` la classe « low ».
  - puces de filtres actifs : rechercher avec `min_seeders=10` rend une puce « Seeders ≥ 10 »
    avec un déclencheur `clearFilter`.
  - état nav actif : `GET /` marque « Recherche » actif ; `GET /downloads` marque
    « Téléchargements » actif.
  - macros `components.html` : `health()` mappe les seuils ; `badge_quality()` mappe les libellés.
- **Non-régression** : la suite existante (155 tests) reste verte (auth incluse) ; les tests
  d'auth ne dépendent pas du markup modifié.

## Décisions par défaut (validées)

- Icônes : **Tabler Icons** via CDN (le plus léger sans build).
- Puces de filtres retirables : **petit helper JS** plutôt que pur HTMX (moins fragile).
- Découpage : **par phases**, Phase 1 = shell + Recherche.
