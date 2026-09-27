# Conception : Interface Web Responsive Mobile

Date : 2026-09-27

## 1. Objectifs

Permettre une utilisation fluide, ergonomique et naturelle de TorrSearch sur smartphone (iOS / Android) :
1. **Navigation tactile au pouce** :
   - Mise en place d'une barre de navigation fixe en bas d'écran (Bottom Navigation Bar) sur mobile pour les 4 sections principales (Recherche, Découvrir, Bibliothèque, Activité) + menu tactile (Plus / Menu) permettant d'accéder aux Réglages, à la Surveillance, aux Demandes et à la Déconnexion.
   - En-tête mobile allégé (logo + alertes/demandes) sans encombrement horizontal.
   - Conservation intégrale de la navigation classique sur écran d'ordinateur (desktop).
2. **Recherche et résultats adaptés aux écrans étroits** :
   - Formulaire de recherche responsive (champ texte élastique, bouton avec icône sur mobile, sélecteur de catégorie compact).
   - Cartes de résultats torrents fluides à deux étages (titre multi-lignes sans troncature prématurée en haut, métadonnées + barre d'action tactile en bas) qui s'alignent automatiquement en ligne sur grand écran.
3. **Fiches détaillées et modales de consultation** :
   - Affiche du film ou de la série calibrée sur mobile (`w-32` au lieu de `w-full`) pour que les synopsis, statuts Jellyfin et boutons d'action soient immédiatement visibles sans scroller des centaines de pixels.
   - Modales adaptées avec marges réduites sur mobile (`p-2 sm:p-4`) et hauteur maximale confortable (`max-h-[92vh]`).
4. **Vue Activité & Téléchargements tactile** :
   - Statistiques globales (réception, envoi, actifs) en grille 3 colonnes compacte.
   - Filtres de statuts à défilement horizontal fluide (`overflow-x-auto no-scrollbar`).
   - Ligne d'actions dédiée pour chaque torrent (Pause/Reprendre, Supprimer, + Données) facilement manipulable au doigt.
5. **Formulaires et Réglages étanches au dépassement** :
   - Remplacement de toutes les largeurs fixes rigides (`w-72`, `w-64`) par des largeurs adaptatives (`w-full sm:w-72 max-w-full`).
   - Grilles modulaires pour la configuration des trackers.

## 2. Principes & Contraintes
- **Zéro JS inline** : respect absolu de la règle du projet vérifiée par `tests/test_no_inline_js.py`. Tous les comportements interactifs (modales, filtres, copie) s'appuient sur Tailwind, les balises HTML sémantiques nativement interactives (`<details>`, `<summary>`) ou la délégation d'événements dans `static/app.js`.
- **Zéro accent dans les templates HTML** : respect de la convention du projet (`Reglages`, `Bibliotheque`, `Activite`, `Decouvrir`, `Telecharge`, etc.).
- **Zéro CDN externe** : les styles s'appuient exclusivement sur le Tailwind CSS local déjà embarqué.
- **Accessibilité tactile** : zones de contact d'au moins 40-48px de hauteur pour les boutons principaux de navigation et d'action.

## 3. Détail technique par composant

### 3.1 `base.html`
- Configuration `viewport` : `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`.
- En-tête :
  - Sur desktop (`hidden md:flex`) : barre de navigation complète horizontale.
  - Sur mobile : logo à gauche, badge de demandes ou état à droite.
- Barre de navigation basse (`fixed bottom-0 left-0 right-0 z-40 md:hidden bg-slate-900/95 backdrop-blur border-t border-slate-800`):
  - Bouton Recherche (`/`)
  - Bouton Découvrir (`/discover`)
  - Bouton Bibliothèque (`/library`)
  - Bouton Activité (`/downloads`)
  - Bouton Menu (`<details class="relative">` avec menu popover vers le haut listant Réglages, Surveillance, Demandes, Déconnexion).
- Conteneur `<main>` : `px-3 sm:px-6 py-4 sm:py-8 pb-24 md:pb-8 max-w-5xl mx-auto`.

### 3.2 Recherche & Résultats (`index.html`, `partials/results.html`)
- `index.html` :
  - Barre de recherche en flexbox adaptative. Bouton de recherche : texte masqué sur petit écran, icône loupe visible.
  - Formulaire de filtres avancés : champs `w-full sm:w-24`, `w-full sm:w-48`.
- `partials/results.html` :
  - Sur petit écran (< `sm`) : affichage carte (titre `line-clamp-2 break-words` + badges, puis bordure de séparation fine et ligne d'action contenant taille, seeders et boutons d'envoi/copie).
  - Sur grand écran (`sm:`) : disposition ligne classique.
  - Alerte Jellyfin : passage en `flex-col sm:flex-row` pour éviter tout débordement.

### 3.3 Découvrir & Bibliothèque (`partials/media_results.html`, `partials/library_list.html`, `partials/series_list.html`)
- Grille : `grid grid-cols-2 gap-2.5 sm:gap-4 sm:grid-cols-3 md:grid-cols-4`.
- Cartes : `p-2 sm:p-2.5`, boutons calibrés avec typographie `text-[11px] sm:text-xs`.
- Onglets de filtrage : `flex gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar`.

### 3.4 Fiches Films & Séries (`movie_detail_content.html`, `series_detail_content.html`, modales)
- Affiche : `w-32 sm:w-48 mx-auto sm:mx-0 shrink-0` pour ne pas monopoliser l'écran verticalement.
- Zone texte & actions : centrée ou alignée à gauche avec boutons ergonomiques (`px-3 sm:px-4 py-2`).
- Modales : padding extérieur `p-2 sm:p-4`, padding intérieur `p-3.5 sm:p-6`, scroll vertical avec fermeture accessible.

### 3.5 Activité (`partials/downloads_list.html`)
- Compteurs débits : `grid grid-cols-3 gap-2 sm:flex sm:flex-wrap`.
- Filtres : barre scrollable horizontale `overflow-x-auto no-scrollbar flex-nowrap`.
- Lignes de torrents : titre au-dessus, boutons d'action (pause, supprimer, données) regroupés proprement.

### 3.6 Réglages (`settings.html`, `partials/indexer_row.html`)
- Remplacement des classes `w-72` et `w-64` par `w-full sm:w-72 max-w-full`.
- Lignes d'indexers transformées en blocs responsives avec grille d'inputs et boutons bien agencés.
