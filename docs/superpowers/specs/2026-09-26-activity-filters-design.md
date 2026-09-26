# Conception : Filtres par statut dans la vue Activité

Date : 2026-09-26

## 1. Objectifs

Permettre à l'utilisateur de filtrer les torrents dans la vue **Activité** (`/downloads` / `/activity`) selon leur statut :
- **Tous** : l'intégralité des torrents présents dans Transmission.
- **En cours** : torrents en cours de téléchargement (`percent < 100` et non en pause).
- **Termines** : torrents arrivés à 100 % ou en état de partage (`seeding`).
- **Actifs** : torrents ayant un débit actif (`down_rate > 0` ou `up_rate > 0`).
- **En pause** : torrents mis en pause (`stopped`).

Chaque filtre doit afficher un compteur dynamique du nombre de torrents correspondants.
Le filtre actif doit être conservé lors du rafraîchissement automatique HTMX (toutes les 3 secondes) et lors des actions de pause, reprise ou suppression.

## 2. Conception technique

### 2.1 Logique serveur (`torsearch/web/downloads_routes.py`)
- Fonction `_filter_torrents(torrents: list[TorrentInfo], filter_status: str)` :
  - Calcule les compteurs :
    - `all`: total
    - `downloading`: `t.percent < 100.0 and t.status != "stopped"`
    - `completed`: `t.percent >= 100.0 or "seed" in t.status.lower()`
    - `active`: `t.down_rate > 0 or t.up_rate > 0`
    - `paused`: `t.status == "stopped" or t.status_label == "En pause"`
  - Filtre la liste des torrents selon `filter_status` (repli sur `all` si valeur inconnue).
  - Renvoie `filtered_torrents, counts, current_filter`.
- Mettre à jour `_render_list(request: Request, error: str | None = None, filter_status: str = "all")`.
- Routes `GET /downloads/list` et `GET /activity/list` : acceptent le paramètre query `filter: str = "all"`.
- Routes d'action (`pause`, `resume`, `delete`) : acceptent le paramètre query optionnel `filter: str = "all"` et le retransmettent à `_render_list`.

### 2.2 Template (`torsearch/web/templates/partials/downloads_list.html`)
- Ajouter la barre d'onglets de filtrage avec icônes et compteurs au-dessus de la liste.
- Style actif bien distinct (`bg-slate-700 text-white`).
- Mettre à jour `hx-get="/downloads/list?filter={{ current_filter }}"` sur le conteneur racine `#downloads-list`.
- Retransmettre `filter={{ current_filter }}` dans les formulaires/boutons d'action.
- Message explicite quand aucun torrent ne correspond au filtre actif.
- Respect strict de la règle zéro JS inline et sans accents dans le HTML.

## 3. Plan de tests (TDD)
- Tester dans `tests/test_downloads_web.py` :
  - Le calcul des compteurs pour chaque filtre.
  - Le filtrage effectif des torrents pour `filter=downloading`, `filter=completed`, `filter=active`, `filter=paused`.
  - La préservation du paramètre de filtre lors d'une action pause/resume/delete.
  - Le repli sur `all` si un filtre invalide est passé.
