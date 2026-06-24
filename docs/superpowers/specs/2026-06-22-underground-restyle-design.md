# Restyle « underground » — Design

**Date :** 2026-06-22
**Statut :** validé (maquette approuvée)

## Objectif

Re-skin complet du front en **dark minimaliste, inspiré des trackers/sites underground années 2000** :
fond noir profond, accent cyan unique sur l'interactif, déco neutralisée, couleurs fonctionnelles
conservées en discret, logo pixel-art. Aucun changement de logique ni de comportement — pur visuel.

## Approche

**Levier principal : reconfigurer Tailwind (Play CDN)** dans `base.html` ET `login.html` via
`tailwind.config`, en remappant les tokens couleur déjà utilisés par les templates → tout le front
se re-skin d'un bloc. Édits ciblés seulement pour (a) garder le fonctionnel en vert/ambre/rouge,
(b) neutraliser le déco en gris, (c) le logo, (d) la page de connexion.

### Palette (remap des tokens Tailwind)

| Token actuel | Nouveau | Usage |
|---|---|---|
| `slate-900` / `950` | `#0a0a0a` | fond de page |
| `slate-800` | `#141414` | cards / surfaces / inputs |
| `slate-700` | `#2a2a2a` | bordures |
| `slate-600` | `#666666` | bordures hover / texte faible |
| `slate-500` / `400` | `#888888` | texte secondaire / placeholder |
| `slate-300` | `#aaaaaa` | sous-titres |
| `slate-100` / `50` | `#ffffff` | texte principal |
| `emerald-400/500/600` | `#00d4e8` | **accent cyan** : CTA, liens actifs, focus |
| `emerald-700` | `#00a8b8` | accent hover |
| `sky-*`, `violet-*` | gris (`#2a2a2a` / `#aaaaaa`) | **neutralise** les badges déco (qualité, type, épisodes) |

Police : `Inter, ui-sans-serif, system-ui` (Inter chargée via Google Fonts).

### Couleurs fonctionnelles gardées (édits ciblés, en `green-*` qui reste vert)

`emerald` étant remappé en cyan, on rebascule explicitement les cas fonctionnels vers `green-*` :
- `components.html` : santé `good` → `green` (ok = amber, low = red, inchangés).
- `library_list.html` : badge statut `Obtenu` → `green` (Voulu = amber, inchangé).
- `media_results.html`, `library_list.html`, `series_list.html` : badge `Dans Jellyfin` → `green`.
- `toast.html` : toast succès → `green-600` (erreur = `red-600`).

### Logo

Mark **pixel-art blanc** (SVG inline, `shape-rendering=crispEdges`, glyphe « T » géométrique façon
demoscene) + libellé « TorrSearch ». Repris dans `base.html` (marque nav) et `login.html`.

### Page de connexion (`login.html`)

Standalone (pas de navbar — déjà le cas). Restyle : card centrée (`#141414`, bordure `#2a2a2a`,
radius ~12px), logo pixel, h1 blanc « Connexion », sous-titre gris, **inputs à icône à gauche**
(user / lock, fond `#1a1a1a`), bouton cyan pleine largeur. Ajout du `<link>` Tabler Icons + du
même bloc `tailwind.config` + Inter.

### Finitions

Cards radius ~12px, boutons ~8px, zéro dégradé, ombres quasi nulles (`shadow-lg` du toast → retiré).

## Périmètre des fichiers

`base.html`, `login.html`, `partials/{components,toast,media_results,library_list,series_list,results}.html`,
`index.html`, `discover.html`, `settings.html`. (downloads/surveillance héritent du shell.)

## Tests

Pas de logique modifiée → la suite (250) doit rester verte (les tests assertent du markup/texte,
pas des couleurs). Vérifs markup légères ajoutées : présence du remap (`#00d4e8` dans `base.html`),
neutralisation déco. **Vérification principale = visuelle** (preview multi-pages + login).
