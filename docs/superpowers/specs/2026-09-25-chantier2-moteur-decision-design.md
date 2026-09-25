# Chantier 2 : Moteur de décision & auto-grab intelligent

Date : 2026-09-25

## 1. Contexte & Objectifs

L'auto-grab actuel (films et séries) souffre de limitations critiques pour un usage autonome fiable :
1. **Faux positifs de titre** : une recherche pour la série « Lost » récupère n'importe quel torrent contenant « Lost », comme `Lost.in.Space.S01E03`. De même, un film comme « Avatar » (2009) peut capturer `Avatar.The.Way.of.Water.2022`.
2. **Titres originaux ignorés** : sur les trackers francophones ou internationaux, une série comme « La Casa de Papel » ou « Game of Thrones » peut être nommée sous son titre original ou français selon les équipes de release.
3. **Absence d'analyse de release** : seule la résolution (1080p, 2160p...) est détectée. La langue (MULTI, VFF, VF, VOSTFR, VO), la source (BluRay, WEB-DL, CAM, TS) et le codec ne sont pas analysés.
4. **Releases dégradées non filtrées** : les CAM, TS, TC, TELESYNC, SCR/DVDSCR polluent parfois les résultats récents et risquent d'être téléchargées.
5. **Boucles sur torrents morts** : un torrent sans seeder ou en échec est actuellement retenté indéfiniment à l'identique une fois le délai de regrab écoulé.
6. **Historique des épisodes fragile** : l'état des épisodes d'une série est déduit de l'historique du moniteur, qui est plafonné dans le temps.

### Préférences utilisateur retenues
- **Langue** : MULTI et VFF en priorité, VOSTFR accepté en repli (la VO sans sous-titres français est écartée).
- **Sources bannies** : exclusion systématique de CAM, TS, TC, TELESYNC, SCR / DVDSCR.
- **Taille** : pas de limite stricte par défaut (se fier aux résolutions demandées).
- **Ciblage des titres** : correspondance stricte du titre extrait de la release avec le titre TMDB ou le titre original TMDB.

---

## 2. Architecture & Composants

### 2.1 Analyseur de nom de release (`torsearch/parser/release.py`)
Un parser dédié qui analyse une chaîne de release et en extrait :
- `title` : titre nettoyé (sans points, tirets, tags techniques).
- `year` : année détectée (ex: 1999, 2024).
- `episodes` : ensemble des épisodes détectés (`S01E02`, ou `S01` pour pack de saison).
- `resolution` : `2160p`, `1080p`, `720p`, `480p`, ou `unknown`.
- `source` : `bluray`, `web-dl`, `webrip`, `hdtv`, `dvdrip`, `cam`, `ts`, `tc`, `screener`, `other`.
- `is_banned_source` : booléen (`True` pour CAM, TS, TC, TELESYNC, SCR, DVDSCR).
- `language` : `multi`, `vff` (TrueFrench), `vfq`, `vf` (French), `vostfr` (SubFrench), `vo`, `unknown`.
- `codec` : `x265`, `hevc`, `x264`, `h264`, `av1`, etc.
- `edition` : `remux`, `proper`, `repack`, `extended`, etc.

### 2.2 Vérificateur de correspondance de titre (`torsearch/search/matcher.py`)
Fonction pure `match_media_title(release: ParsedRelease, target_title: str, original_title: str | None = None, target_year: str | int | None = None, is_series: bool = False) -> bool` :
- Normalisation : minuscules, suppression des accents, des signes de ponctuation, espaces multiples réduits.
- Comparaison stricte :
  - Le titre nettoyé de la release doit être égal à `target_title` ou `original_title` (avec tolérance sur les articles initiaux « The », « Le », « La », « Les »).
  - Pour les films : si une année est présente dans la release et sur la cible, `abs(release.year - target_year) <= 1` (tolérance de fin d'année / sortie décalée).
  - Rejet garanti de faux positifs : `Lost in Space` != `Lost`, `Avatar 2` != `Avatar`.

### 2.3 Moteur de décision & classement (`torsearch/search/decision.py`)
Pour une liste de résultats candidats :
1. **Élimination** :
   - Éliminer les torrents dont `is_banned_source` est vrai.
   - Éliminer les torrents dont le titre ne matche pas (`match_media_title == False`).
   - Éliminer les torrents déjà en liste noire (`Blacklist`).
   - Éliminer les torrents dont la résolution ne figure pas dans le profil demandé (`config.library.qualities`).
   - Éliminer les langues non désirées (ex: VO pure sans sous-titres français).
2. **Hiérarchisation (Score / Tri)** :
   - **Niveau de langue** :
     - Rang 1 : `MULTI` et `VFF` (TrueFrench).
     - Rang 2 : `VF` / `VFQ` (French).
     - Rang 3 : `VOSTFR` (SubFrench).
   - **Résolution** : respect de l'ordre de priorité du profil qualité (ex: 2160p > 1080p > 720p).
   - **Taille / Seeders** :
     - Pour un film ou un épisode unitaire : priorité au nombre de seeders parmi le meilleur rang langue/qualité.
     - Pour un pack de série : torrent le plus petit couvrant les épisodes manquants, puis seeders en départage.

### 2.4 Liste noire persistante (`torsearch/library/blacklist.py`)
Collection SQLite `blacklist` dans `data/torsearch.db` :
- Clé : `infohash` (ou titre si infohash absent).
- Stocke : `infohash`, `title`, `reason`, `blacklisted_at`.
- Méthodes : `is_blacklisted(infohash, title) -> bool`, `add(infohash, title, reason)`, `remove(infohash)`.
- Lors d'un échec de téléchargement ou d'un re-grab suite à timeout sans présence dans Jellyfin, le torrent précédent est automatiquement ajouté à la blacklist pour tester une autre release au cycle suivant.

### 2.5 Persistance granulaire des épisodes & Titre original
- Modèles `WantedMovie` et `WantedSeries` : ajout du champ optionnel `original_title: str | None = None`.
- Modèle `WantedSeries` : suivi granulaire des épisodes sous forme de dictionnaire d'états d'épisodes (`dict[str, EpisodeRecord]`) conservant l'infohash, le titre de la release et la date de grab, tout en maintenant la rétrocompatibilité avec la liste `grabbed: list[str]`.
- TMDB : `parse_multi` extrait systématiquement `original_title` (film) ou `original_name` (série).
- Cycles de surveillance (`run_movie_cycle`, `run_series_cycle`) :
  - Interrogent les indexeurs avec le titre courant, et également avec `original_title` si différent.
  - Fusionnent et dédoublonnent les résultats avant de passer par le moteur de décision.

---

## 3. Plan de tests (TDD)

1. `tests/test_release_parser.py` :
   - Parsing d'une vingtaine de releases représentatives du P2P francophone et anglophone.
   - Détection des langues (MULTI, TRUEFRENCH, VFF, VFQ, FRENCH, VOSTFR, VO).
   - Détection des sources (BluRay, WEB-DL, WEBRip, HDTV, CAM, TS, etc.).
   - Détection des sources bannies (`is_banned_source`).
   - Détection des résolutions et codecs.
2. `tests/test_matcher.py` :
   - Faux positifs évités : `Lost in Space` vs `Lost`, `Avatar: The Way of Water` vs `Avatar`, `The Office (US)` vs `The Office`.
   - Matching valide sur titre français ou original avec ponctuation diverse (`S.W.A.T.`, `Spider-Man: No Way Home`).
   - Tolérance sur l'année pour les films.
3. `tests/test_decision.py` :
   - Filtrage des sources bannies.
   - Préférence de langue : MULTI/VFF > VF > VOSTFR > rejet VO pure.
   - Choix du meilleur candidat selon profil et départage seeders/taille.
4. `tests/test_blacklist.py` :
   - Ajout, persistance SQLite, filtrage des torrents blacklistés.
5. `tests/test_monitor_cycle_decision.py` :
   - Cycles film et série utilisant le nouveau moteur de décision.
   - Recherche double (titre + titre original) et dédoublonnage.
   - Mise en liste noire en cas de re-grab sur échec.

---

## 4. Hors périmètre immédiat

- Édition manuelle de la liste noire dans l'interface web (prévu dans le chantier Interface).
- Choix de profil qualité par film/série individuel (un profil global suffit pour l'instant).
