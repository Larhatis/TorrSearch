# Raffinements *arr : plus petit torrent & upgrades de qualité

Date : 2026-06-25

## R1 — Préférer le plus petit torrent qui couvre un manquant (séries)

Problème : `run_series_cycle` itère les résultats triés par seeders et grab le premier qui
couvre un épisode manquant. Un **pack de saison** (20 Go, beaucoup de seeders) peut donc
être pris pour **un seul** épisode manquant.

Correctif : pour la sélection en mode ciblé, itérer les candidats par **taille croissante**
(seeders en départage), pas par seeders seuls. Comme le `remaining` se vide au fur et à
mesure, le petit torrent épisode est pris en premier et le pack — qui ne couvre alors plus
rien de manquant — est ignoré. Le filtre qualité + `min_seeders` s'applique avant, donc on
ne tombe pas sur du 480p ou du 0-seed. Aucun changement quand un seul torrent couvre le
besoin (ex. saison entière manquante → le pack reste pris).

## R2 — Upgrades de qualité (films, opt-in)

Nouveau réglage `LibraryConfig.upgrades: bool = False` (désactivé par défaut : pas de
re-téléchargement surprise).

- Classement qualité : `quality_rank(title)` dérivé de l'ordre de `_QUALITY_PATTERNS`
  (2160p < 1080p < 720p < 480p < other ; plus petit = meilleur).
- Dans `run_movie_cycle`, pour un film **déjà grabbé** (qui n'a donc pas besoin d'un grab
  normal), si `upgrades` est actif : on cherche, on prend le **meilleur** candidat (qualité
  puis seeders) parmi ceux conformes au profil, et **s'il est strictement meilleur** que la
  qualité du `grabbed_title` courant → on le grab en remplacement et on met à jour
  `grabbed_title`/`grabbed_at`. Pas de boucle : à qualité égale, aucune action.
- Périmètre : **films uniquement**. Les séries stockent des clés d'épisodes sans qualité ;
  l'upgrade par épisode nécessiterait d'étendre le modèle → hors périmètre.

Le grab d'un film (transmission.add + mark_grabbed + record + notif) est factorisé dans un
helper réutilisé par le chemin normal et le chemin upgrade.

## Dégradation gracieuse
- R1 : sans TMDB (mode repli) le comportement de grab reste celui d'aujourd'hui.
- R2 : `upgrades=False` par défaut → aucun changement ; tests existants intacts.

## Tests (TDD)
- R1 : manquant unique + (pack volumineux vs épisode petit) → l'épisode est pris, pas le pack.
- R2 : `quality_rank` ; film 720p grabbé + 1080p dispo & `upgrades=True` → upgrade ;
  `upgrades=False` → rien ; pas d'upgrade si rien de meilleur.
