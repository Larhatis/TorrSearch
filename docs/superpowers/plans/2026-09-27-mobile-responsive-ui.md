# Plan : Interface Web Responsive Mobile

Date : 2026-09-27

## Étape 1 : En-tête et Navigation Mobile (Bottom Bar) dans `base.html`
1. Modifier `<meta name="viewport">` pour inclure `viewport-fit=cover`.
2. Mettre à jour l'en-tête `<header>` :
   - Desktop (`hidden md:flex`) : conserver les liens avec intitulés.
   - Mobile : logo compact à gauche, alertes de demandes et lien de déconnexion rapides à droite.
3. Ajouter la barre de navigation fixe basse (`<nav class="md:hidden fixed bottom-0 ...">`) :
   - Liens directs avec icône + texte : Recherche, Découvrir, Bibliothèque, Activité.
   - Bouton « Menu » dépliant (`<details class="relative">`) avec les accès complémentaires (Réglages, Surveillance, Demandes, Déconnexion).
4. Adapter les marges du conteneur `<main>` : `px-3 sm:px-6 py-4 sm:py-8 pb-24 md:pb-8`.

## Étape 2 : Recherche & Résultats Torrents
1. `index.html` :
   - Ajuster la barre de recherche : bouton avec icône visible sur mobile, catégorie compacte.
   - Ajuster le panneau des filtres : champs en largeur adaptable (`w-full sm:w-24`, etc.).
2. `partials/results.html` :
   - Transformer chaque élément de résultat torrent en carte responsive fluide à 2 étages sur mobile (`< sm`), et ligne sur desktop (`sm:`).
   - Adapter la bannière Jellyfin (`flex-col sm:flex-row`).

## Étape 3 : Découvrir, Bibliothèque & Fiches Détaillées
1. `partials/media_results.html` :
   - Onglets horizontaux à défilement fluide sans retour à la ligne forcé.
   - Grille `grid-cols-2 gap-2.5 sm:gap-4`.
   - Boutons de cartes dimensionnés pour les écrans étroits.
2. `partials/library_list.html` et `partials/series_list.html` :
   - Espacements `gap-2.5 sm:gap-4`, typographie et boutons tactiles.
3. `partials/movie_detail_content.html` & `partials/series_detail_content.html` :
   - Réduire et centrer l'affiche sur mobile (`w-32 sm:w-48 mx-auto sm:mx-0`) pour garder l'essentiel visible immédiatement.
   - Modales (`movie_detail_modal.html`, `series_detail_modal.html`, `media_detail_modal.html`) : paddings réduits `p-2 sm:p-4`, intérieur `p-3.5 sm:p-6`.

## Étape 4 : Activité & Téléchargements
1. `partials/downloads_list.html` :
   - Statistiques globales en grille 3 colonnes compacte sur mobile.
   - Filtres de statuts à défilement horizontal.
   - Ligne d'actions dédiée pour chaque torrent (Pause/Reprendre, Supprimer, + Données) évitant la collision avec le titre.

## Étape 5 : Réglages & Surveillance
1. `settings.html` :
   - Remplacer les largeurs fixes `w-72` et `w-64` par `w-full sm:w-72 max-w-full`.
2. `partials/indexer_row.html` :
   - Réagencer les champs en grille responsive avec boutons sous les champs sur mobile.
3. `partials/surveillance_body.html` :
   - Formulaires et liste de recherches surveillées adaptés aux téléphones.

## Étape 6 : Tests & Validation
1. Vérifier la conformité anti-JS inline avec `pytest tests/test_no_inline_js.py`.
2. Vérifier les tests web existants et ajouter des assertions de rendu mobile dans `tests/test_web.py`.
3. Lancer linter et tests complets : `ruff check torsearch tests`, `mypy`, `pytest -q`.
