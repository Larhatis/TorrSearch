# F3 — Téléchargements en cours (vue Transmission) — Spec de conception

> Date : 2026-06-19
> Statut : approuvé (carte blanche), en implémentation
> Construit sur F1 (branche `feat/downloads-view` par-dessus `feat/result-filters`).

## 1. Contexte & objectif

Quand on envoie un torrent à Transmission, il faut aujourd'hui ouvrir Transmission à côté pour
suivre l'avancement. Objectif : une page **/downloads** dans TorSearch qui liste ce qui tourne
dans Transmission, se rafraîchit toute seule, et permet pause / reprise / suppression.

## 2. Périmètre

### Dans F3 (in scope)

- Page **/downloads** : tableau des torrents Transmission (nom, **% avancement**, statut,
  vitesse ↓/↑, taille), **auto-rafraîchi** toutes les ~3 s (HTMX, sans rechargement de page).
- Actions par torrent : **pause**, **reprise**, **suppression** (sans supprimer les données).
- Lien **« Téléchargements »** ajouté à la navigation.
- Si Transmission est injoignable : message d'erreur clair dans la zone liste (pas de 500).

### Hors F3 (plus tard)

Suppression **avec** données · ajout manuel d'un torrent depuis cette page · tri/filtre de la
liste · détails par torrent (fichiers, trackers) · limite de débit.

## 3. Architecture

### 3.1 `TransmissionClient` (`torsearch/transmission/client.py`)

On étend le wrapper existant (qui a déjà `add` + connexion paresseuse via `client_factory`).
On normalise les torrents dans un modèle propre pour découpler de `transmission-rpc` et rester
testable.

- `TorrentInfo` (Pydantic) : `id: int`, `name: str`, `percent: float` (0–100),
  `status: str`, `down_rate: int` (octets/s), `up_rate: int`, `size: int` (octets).
- `list_torrents() -> list[TorrentInfo]` : `client.get_torrents()` → mappe chaque torrent vers
  `TorrentInfo` (lecture défensive des attributs : `id`, `name`, `progress`, `status`,
  `rate_download`, `rate_upload`, `total_size`).
- `pause(torrent_id: int)` : `client.stop_torrent(torrent_id)`.
- `resume(torrent_id: int)` : `client.start_torrent(torrent_id)`.
- `remove(torrent_id: int)` : `client.remove_torrent(torrent_id, delete_data=False)`.

> Le mapping des attributs `transmission-rpc` est isolé dans `list_torrents`, donc un seul
> endroit à ajuster si la lib change. Les tests injectent un faux client (`client_factory`).

### 3.2 Routes (`torsearch/web/downloads_routes.py`)

Nouveau `APIRouter` `downloads_router`, monté par `create_app`.

| Méthode & route | Effet |
|---|---|
| `GET /downloads` | Rend `downloads.html` (cadre + zone liste auto-rafraîchie). |
| `GET /downloads/list` | Rend `partials/downloads_list.html` (le tableau). C'est la cible du rafraîchissement HTMX `every 3s`. |
| `POST /downloads/{id}/pause` | `ctx.transmission.pause(id)` puis re-rend la liste. |
| `POST /downloads/{id}/resume` | `ctx.transmission.resume(id)` puis re-rend la liste. |
| `POST /downloads/{id}/delete` | `ctx.transmission.remove(id)` puis re-rend la liste. |

Chaque handler lit `request.app.state.ctx.transmission`. La construction de la liste est
enveloppée d'un `try/except` : si Transmission est injoignable, on rend la liste avec un
message d'erreur (`error=...`) au lieu de planter.

### 3.3 UI (templates)

- **`downloads.html`** (étend `base.html`) : titre + un conteneur
  `<div id="downloads-list" hx-get="/downloads/list" hx-trigger="load, every 3s">` qui charge et
  rafraîchit la liste toute seule.
- **`partials/downloads_list.html`** : `<div id="downloads-list">` (même id, swap `outerHTML`)
  contenant le tableau (nom, barre/`%`, statut, ↓/↑ en Ko/s, taille) et, par ligne, des boutons
  HTMX **Pause/Reprendre** et **Supprimer** (ciblant `#downloads-list`). Si `error`, affiche le
  message ; si aucun torrent, « Aucun téléchargement en cours ».
- **`base.html`** : ajouter `<a href="/downloads">Téléchargements</a>` dans la nav.

## 4. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Transmission injoignable (`list_torrents` lève) | La liste rend un message d'erreur lisible, pas de 500. |
| Action (pause/resume/delete) qui échoue | Idem : la liste se re-rend avec un message d'erreur. |
| Aucun torrent | Message « Aucun téléchargement en cours ». |

## 5. Tests (pytest, hors-ligne)

- **`TransmissionClient`** (client `transmission-rpc` mocké via `client_factory`) :
  - `list_torrents` mappe de faux torrents (objets avec `id/name/progress/status/rate_download/rate_upload/total_size`) en `TorrentInfo` corrects.
  - `pause`/`resume`/`remove` appellent respectivement `stop_torrent`/`start_torrent`/`remove_torrent` avec le bon `id` (et `delete_data=False` pour remove).
- **Routes** (`TestClient`, `FakeContext` avec une fausse `transmission` exposant
  `list_torrents`/`pause`/`resume`/`remove`) :
  - `GET /downloads` rend la page (zone `#downloads-list` + `hx-trigger`).
  - `GET /downloads/list` rend les lignes des torrents renvoyés par la fausse transmission.
  - `POST /downloads/{id}/pause|resume|delete` appellent la bonne méthode avec l'`id` et re-rendent la liste.
  - Si la fausse transmission lève sur `list_torrents`, `GET /downloads/list` renvoie 200 avec un message d'erreur (pas de 500).

## 6. Fichiers

| Fichier | Action |
|---|---|
| `torsearch/transmission/client.py` | Modifier — `+ TorrentInfo`, `list_torrents`, `pause`, `resume`, `remove`. |
| `torsearch/web/downloads_routes.py` | Créer — `downloads_router`. |
| `torsearch/web/templates/downloads.html` | Créer. |
| `torsearch/web/templates/partials/downloads_list.html` | Créer. |
| `torsearch/web/routes.py` | Modifier — `create_app` monte `downloads_router`. |
| `torsearch/web/templates/base.html` | Modifier — lien nav « Téléchargements ». |
| `tests/test_transmission.py` | Modifier — tests `list_torrents`/`pause`/`resume`/`remove`. |
| `tests/test_downloads_web.py` | Créer. |

## 7. Notes

- L'auto-rafraîchissement (`every 3s`) ne sollicite Transmission qu'au rythme de l'affichage ;
  acceptable pour un usage perso mono-utilisateur.
- `remove` ne supprime **pas** les données téléchargées (`delete_data=False`) — choix sûr par
  défaut ; une suppression « avec données » pourra venir plus tard.
- `percent` est exposé sur 0–100 pour un affichage direct ; le mapping lit `torrent.progress`
  (déjà en 0–100 dans `transmission-rpc`).
