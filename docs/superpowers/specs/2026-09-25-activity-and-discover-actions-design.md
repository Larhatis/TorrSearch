# Conception : Suivi des téléchargements (Activité) et Actions Découvrir

Date : 2026-09-25

## 1. Objectifs

1. **Chantier 3 : Suivi des téléchargements & Onglet Activité** :
   - Transformer la vue `/downloads` en une véritable page **Activité** moderne.
   - Afficher les détails complets de chaque torrent Transmission : barre de progression, vitesse Down/Up formatée, ETA restant, pairs connectés, statut clair en français.
   - Statistiques globales (débit total descendant et montant).
   - Actions directes : Pause, Reprendre, Supprimer (avec ou sans données).
   - Déclenchement manuel et automatique du scan Jellyfin dès qu'un torrent est terminé.
2. **Amélioration Découvrir : Ajout direct en bibliothèque & Fiche détail** :
   - Permettre l'ajout direct en bibliothèque (Film ou Série) depuis chaque carte de média avec mise à jour visuelle instantanée de la carte via HTMX et notification toast.
   - Fiche détail complète (modal sans JS inline) accessible au clic sur l'affiche ou le titre (synopsis complet, note, date, statut Jellyfin, boutons d'action).

## 2. Conception technique

### 2.1 Suivi des téléchargements & Client Transmission (`torsearch/transmission/client.py`)
- Enrichir le modèle `TorrentInfo` :
  - `eta: int | None` (secondes restantes)
  - `peers_connected: int`
  - `peers_sending: int`
  - `error_string: str`
  - `info_hash: str`
  - Propriétés formatées :
    - `size_formatted`: ex. "4.25 Go", "750 Mo"
    - `down_rate_formatted`: ex. "12.4 Mo/s", "350 Ko/s"
    - `up_rate_formatted`: ex. "1.1 Mo/s", "40 Ko/s"
    - `eta_formatted`: ex. "5 min", "1 h 20 min", "Terminé", "--"
    - `status_label`: libellé français ("Téléchargement", "Partage", "En pause", "Vérification", "Erreur")
- Mettre à jour `TransmissionClient.remove(torrent_id, delete_data=False)`.

### 2.2 Routes Téléchargements / Activité (`torsearch/web/downloads_routes.py`)
- Support des alias `/downloads` et `/activity`.
- Route `POST /downloads/scan-jellyfin` pour lancer `ctx.jellyfin.refresh()` à la demande.
- Route `POST /downloads/{torrent_id}/delete` acceptant le paramètre optionnel `delete_data: bool = False`.
- Détection automatique d'achèvement : quand un torrent atteint 100% ou l'état `seeding`, déclencher `ctx.jellyfin.refresh()` si pas encore scanné pour ce torrent.
- Templates `downloads.html` et `partials/downloads_list.html` :
  - Barre de progression stylisée.
  - Résumé des vitesses globales (Total Down, Total Up, Torrents actifs).
  - Boutons d'action rapides avec confirmation sécurisée.

### 2.3 Actions Découvrir & Fiche Détail (`torsearch/web/discover_routes.py`)
- Route `POST /discover/library/add` :
  - Accepte `media_type`, `tmdb_id`, `title`, `original_title`, `year`, `poster_path`.
  - Ajoute à `library` (`WantedMovie`) ou `series_library` (`WantedSeries`).
  - Renvoie le fragment de badge mis à jour (« En bibliothèque ») pour la carte ciblée, avec déclenchement OOB ou en-tête de toast.
- Route `GET /discover/{media_type}/{tmdb_id}/modal` :
  - Récupère les métadonnées détaillées.
  - Renvoie le modal HTML (`partials/media_detail_modal.html`) injecté dans `#modal-container`.
- Support dans `torsearch/web/static/app.js` :
  - Fermeture du modal au clic sur le backdrop ou un élément `[data-modal-close]`.
  - Zéro JS inline, respect absolu de `test_no_inline_js.py`.

## 3. Plan de tests (TDD)
1. `tests/test_transmission_client.py` & `tests/test_downloads_web.py` :
   - Tester l'enrichissement de `TorrentInfo` (formats de taille, vitesse, ETA, statut).
   - Tester les routes `/downloads` et `/activity`.
   - Tester la suppression avec `delete_data`.
   - Tester la route de scan Jellyfin.
2. `tests/test_discover_web.py` :
   - Tester `POST /discover/library/add` pour films et séries.
   - Tester `GET /discover/{media_type}/{tmdb_id}/modal`.
   - Vérifier l'absence de JS inline via `tests/test_no_inline_js.py`.
