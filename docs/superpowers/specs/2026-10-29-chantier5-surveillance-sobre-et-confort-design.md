# Conception : Chantier 5 — surveillance sobre (RSS), calendrier, confort et exploitation

Date : 2026-10-29

## 1. Objectifs

Rapprocher TorrSearch d'un vrai remplaçant de Sonarr/Radarr/Jellyseerr tout en ménageant
les trackers, et combler les manques d'exploitation (sauvegarde, journal, santé du conteneur).

| # | Lot | Résultat attendu |
|---|-----|------------------|
| 1 | Limite de fréquence par tracker | Jamais deux requêtes simultanées sur un tracker, délai minimal entre deux, pause automatique après un HTTP 429. |
| 2 | Synchro RSS | 1 requête « derniers ajouts » par tracker et par cycle ; les œuvres surveillées sont comparées localement à ce flux. |
| 3 | Recherche guidée par les dates | La recherche ciblée n'est relancée que lorsqu'elle est « due » (fréquence selon l'âge des épisodes manquants). |
| 4 | PROPER/REPACK + upgrades épisodes | Un PROPER/REPACK d'une release récente est repris ; l'option « Upgrades » s'applique aussi aux épisodes. |
| 5 | Calendrier « A venir » | Vue des épisodes des séries suivies et des sorties des films surveillés, groupés par jour. |
| 6 | Demandes « Disponible » | Une demande approuvée passe à « Disponible » quand Jellyfin a l'œuvre, avec notification. |
| 7 | Réglages en onglets + mot de passe | Page Réglages découpée en onglets ; page « Mon compte » pour changer son mot de passe. |
| 8 | Sauvegarde | Bouton de téléchargement d'une copie cohérente de la base SQLite. |
| 9 | Journal | Page listant les derniers événements (INFO+) de l'app, secrets masqués. |
| 10 | Santé & session | Route `/healthz` + `HEALTHCHECK` Docker ; la clé de session suit le dossier de la base (`/data`). |

## 2. Conception technique

### 2.1 Limite de fréquence (`indexers/throttle.py`)
- `TrackerThrottle(min_interval, clock, sleep)` : verrou asyncio (1 requête à la fois par
  tracker) + délai minimal depuis la fin de la requête précédente ; `block(seconds)` /
  `is_blocked()` pour la pause après 429.
- Les throttles vivent dans `AppContext` (dict nom → throttle) et survivent aux
  reconstructions de clients ; `SearchService` les reçoit (sans dict : pas de limite, tests
  existants inchangés). L'attente du throttle n'est **pas** comptée dans le timeout.
- `TorznabIndexer.search` lève `RateLimited(retry_after)` sur HTTP 429 (en-tête
  `Retry-After`, sinon 15 min) ; `SearchService` met le tracker en pause et renvoie `[]`.
- Réglage `search.min_interval_seconds` (défaut 2 s) dans l'onglet Connexions.

### 2.2 Synchro RSS
- `SearchService.recent()` : `t=search` sans `q` sur chaque tracker actif (flux des derniers
  ajouts, 100 éléments), tri par date de publication.
- `MonitorRunner.run_once()` récupère ce flux **une fois** et le passe aux trois cycles
  (recherches libres, films, séries). Pour une œuvre dont la recherche ciblée n'est pas due,
  les candidats sont pris dans le flux (le moteur de décision vérifie déjà titre/année/langue ;
  pour les recherches libres : `matches_query()` exige tous les mots de la requête).
- Flux vide (aucun tracker ne gère le RSS) → comportement historique : tout est dû.

### 2.3 Planification des recherches ciblées (`monitor/schedule.py`)
- `SearchSchedule` mémorise en base (`search_schedule`) la date de dernière recherche ciblée
  par clé (`movie:<id>`, `tv:<id>`, `saved:<nom>`).
- Intervalles :
  - film ajouté depuis < 7 jours : 6 h ; sinon 24 h (upgrades compris) ;
  - série : épisode manquant diffusé depuis ≤ 2 jours → 1 h ; ≤ 14 jours → 6 h ; sinon 24 h ;
    dates inconnues (pas de TMDB) → 6 h ;
  - recherche libre : 6 h.
- « Vérifier maintenant » force une recherche ciblée de tout (`run_once(force=True)`) ; une
  œuvre nouvellement ajoutée n'a jamais été cherchée, elle est donc due immédiatement.
- `TmdbClient.air_dates(tv_id)` → `{code: date}` des épisodes diffusés (réutilise le cache des saisons).

### 2.4 PROPER/REPACK et upgrades épisodes
- Releases déjà prises : historique de surveillance (`kind == "grabbed"`).
- Séries : un candidat acceptable couvrant uniquement des épisodes déjà pris est repris si
  - c'est un PROPER/REPACK de même résolution qu'une release prise il y a ≤ 14 jours ; ou
  - « Upgrades » est actif et sa qualité est strictement meilleure dans le profil.
- Films : PROPER/REPACK de même résolution d'un film pris il y a ≤ 14 jours, repéré dans le flux.
- Jamais deux fois la même release (clé infohash/URL ou titre déjà dans l'historique).

### 2.5 Calendrier (`/calendar`, membres)
- Séries suivies : épisodes de J-7 à J+60 via `tmdb.seasons()` (cache existant).
- Films surveillés non obtenus : `TmdbClient.release_date(id)` (sortie numérique FR, sinon
  numérique toutes régions, sinon cinéma FR, sinon date TMDB), cache 12 h.
- Groupement par jour, badge « Aujourd'hui », état (acquis / manquant / à venir).

### 2.6 Demandes « Disponible »
- `RequestStatus.AVAILABLE` + `available_at`. À chaque cycle, les demandes approuvées dont
  l'œuvre est présente dans Jellyfin (`owned()`) passent « Disponible » et une notification
  « Disponible : Titre (demande de X) » part sur les canaux configurés.

### 2.7 Réglages en onglets, mot de passe
- Onglets : Connexions, Trackers, Surveillance, Notifications, Comptes, Maintenance ;
  attributs `data-settings-tab` / `data-settings-panel` gérés par `app.js` (onglet mémorisé
  dans l'ancre d'URL). Pas de JS inline.
- `/account` (tout utilisateur connecté, auth active) : mot de passe actuel + nouveau (≥ 8
  caractères) + confirmation ; l'empreinte de session est régénérée pour rester connecté.

### 2.8 Sauvegarde, journal
- `Database.backup_to(path)` via l'API `sqlite3.backup` (sûr en WAL) ; `GET /settings/backup`
  renvoie `torsearch-AAAAMMJJ-HHMM.db`. Avertissement : le fichier contient les clés API.
- `logbuffer.MemoryLogHandler` : 500 dernières entrées INFO+ des loggers `torsearch.*`,
  messages passés par `redact()`. Page `/settings/journal` avec filtre de niveau.
- Le moteur journalise ses décisions (flux RSS, recherches ciblées, aucun candidat, grabs).

### 2.9 Santé, session
- `GET /healthz` public → `{"status": "ok", "version": …}` ; `HEALTHCHECK` Docker en Python
  pur (pas de curl dans l'image slim).
- `AuthSettings.from_env(data_dir=dirname(TORSEARCH_DB))` : `.session_secret` dans `/data`.

## 3. Plan (un commit par lot, TDD)
1. Throttle + `RateLimited` + réglage.
2. `recent()`, `SearchSchedule`, `air_dates`, intégration dans les cycles (lots 2 et 3).
3. PROPER/REPACK + upgrades épisodes.
4. Calendrier.
5. Demandes « Disponible ».
6. Réglages en onglets + Mon compte.
7. Sauvegarde + journal.
8. `/healthz`, HEALTHCHECK, clé de session.
9. Docs (AGENTS.md, README), version 0.4.0, revue finale.
