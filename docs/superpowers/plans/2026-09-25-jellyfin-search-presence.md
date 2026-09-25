# Détection de présence Jellyfin sur la page de Recherche — Plan d'implémentation

**Goal:** Afficher un bandeau d'alerte en tête de la page de recherche avec bouton direct « Lire » lorsque le titre cherché est déjà présent dans la médiathèque Jellyfin de l'utilisateur.

**Architecture:**
- `torsearch/jellyfin/client.py` : ajout de `JellyfinItem`, cache TTL 30s dans `get_items()`, méthode `find_matching(query: str) -> JellyfinItem | None`.
- `torsearch/web/routes.py` : interrogation de `ctx.jellyfin.find_matching(q)` dans la route `GET /search`.
- `torsearch/web/templates/partials/results.html` : affichage du bandeau avec badge et lien vers Jellyfin.

**Commandes :** `.venv/bin/pytest`, `.venv/bin/ruff check torsearch tests`, `.venv/bin/mypy`.

---

## Tasks

- [ ] **Task 1 : `JellyfinItem`, `get_items` et `find_matching` dans `JellyfinClient`**
  - Tests dans `tests/test_jellyfin.py` (matching titre exact, requête avec tags de release, rejet faux positif).
  - Implémentation dans `torsearch/jellyfin/client.py`.
  - Validation tests unitaires.

- [ ] **Task 2 : Intégration web et template**
  - Modification de `torsearch/web/routes.py` et `torsearch/web/templates/partials/results.html`.
  - Tests dans `tests/test_web.py`.
  - Validation `pytest`, `ruff`, `mypy`.
