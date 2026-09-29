# AGENTS.md — reprendre TorrSearch

Document de passation pour un agent IA (ou un humain) qui reprend le projet. À lire en entier
avant de toucher au code. Le README s'adresse aux utilisateurs ; ce fichier aux contributeurs.

---

## 1. Le projet en une minute

**TorrSearch** est une app web auto-hébergée (Docker) qui cherche des films/séries sur
plusieurs trackers **Torznab** en parallèle et envoie le résultat choisi à **Transmission**.

**Cap (« étoile polaire »)** : devenir un **tout-en-un simple qui remplace** la pile
Prowlarr/Jackett + Radarr + Sonarr + Jellyseerr — *sans* piloter leurs API. **Jellyfin est
conservé** (lecture) et **Transmission est conservé** (téléchargement).

**Principe directeur : la simplicité.** Tout se configure au clic dans l'interface. Ne pas
réintroduire la complexité que l'utilisateur fuit (pas de profils à rallonge, pas de
dépendances lourdes, pas de build front).

L'utilisateur (propriétaire du dépôt) est francophone : **parler français**, donner une
recommandation claire plutôt qu'un catalogue d'options.

## 2. État actuel (v0.3.16)

Fonctionnel et en production chez l'utilisateur (OpenMediaVault, Docker) :

- Surveillance automatique des sorties films (« Pas encore sorti en torrent ? ») :
  - Sur la page de recherche (`/`), si une recherche renvoie 0 torrent, proposition automatique de surveillance de la requête en 1 clic (« Surveiller cette recherche ») et suggestion des films correspondants sur TMDB avec bouton « Surveiller la sortie ».
  - Dans l'onglet Découvrir et les fiches détail, remplacement du libellé ambigu « Bibliothèque » par un bouton clair « Surveiller la sortie » avec badge dynamique « En surveillance ».
  - Activation automatique de la surveillance globale et réveil immédiat du runner d'auto-grab dès l'ajout d'un film ou d'une recherche surveillée.
- Indicateur en direct de dernière vérification avec badge pulsé et rafraîchissement automatique silencieux de l'historique sur l'onglet Surveillance.
- Protection anti-doublon d'épisodes multi-couches :
  - Détection Transmission en direct (interrogation temps réel des torrents actifs ou terminés pour ne jamais renvoyer un épisode déjà en cours ou fini).
  - Détection disque (scan du dossier de destination pour ne jamais re-télécharger un épisode déjà présent sur le NAS).
  - Verrouillage asynchrone strict (`asyncio.Lock` dans `MonitorRunner`) empêchant les exécutions concurrentes entre la boucle automatique et le clic « Vérifier maintenant ».
  - Synchronisation bidirectionnelle entre « Recherches surveillées » et la « Bibliothèque Séries ».
  - Reconnaissance des épisodes déjà vus dans l'historique même en cas de renommage de recherche (ex. `Lanterns 2026` vs `Lanterns`).
- Dédoublonnage d'épisodes et envoi groupé dans les recherches surveillées : récupération de tous les épisodes disponibles en un seul cycle sans attente minute par minute, et élimination des releases doublons (ex. pas de 1080p + 2160p pour le même épisode).
- Paramètre Torznab `limit=100` pour indexer jusqu'à 100 torrents par requête au lieu des 20 par défaut.
- Gestion fine des séries & saisons acquises : possibilité de marquer des saisons ou épisodes entiers comme déjà acquis (« Marquer saison acquise », « Tout marquer acquis », « Démarquer » ou coche par épisode) afin de ne surveiller et télécharger que les saisons suivantes (ex. reprendre à la saison 6) sans re-télécharger l'existant.
- Bouton « Ne plus suivre » présent directement sur les fiches séries pour désabonner en 1 clic.
- Bouton « Vider l'historique » dans l'onglet Surveillance.
- Arborescence automatique des séries (Chantier 4) : classement automatique dans `Dossier_TV / Nom_Série / Saison XX /` directement à la racine ou dans le dossier Transmission, création récursive des dossiers, idéal pour Jellyfin / Plex.
- Surveillance avec déclenchement immédiat (bouton « Vérifier maintenant »), case d'activation stylée et réveil instantané du timer (`runner.wake()`).
- Diagnostic intelligent des indexeurs Torznab (détection des réponses HTML au lieu de XML, avec recommandation d'ajouter `/api/` ou `/api/torznab`).
- Interface entièrement responsive mobile (Barre de navigation tactile basse "Bottom Bar" avec menu popover pour les réglages/demandes, cartes de résultats fluides sans débordement horizontal, défilement d'onglets au doigt, affiches adaptées).
- Recherche multi-trackers Torznab (parallèle, dédoublonnage, filtres, tri).
- Découverte TMDB (tendances films & séries séparées, recherche par titre, affiches, redirection vers recherche tracker, ajout direct en bibliothèque avec feedback instantané, fiche détail modal avec synopsis complet).
- Fiches détaillées **Films** (`/movies/{tmdb_id}`) et **Séries** (`/series/{tmdb_id}`) : vue modale ou pleine page, synopsis, casting, genres, statut Jellyfin, release téléchargée, boutons de recherche 1-clic par qualité (Tous, 1080p, 4K, Remux) ou par épisode/saison, bouton de remplacement (« Regrab »).
- Bibliothèque **Films** (≈ Radarr-lite) et **Séries** (≈ Sonarr-lite) avec surveillance en tâche de fond et téléchargement automatique.
- Suivi des téléchargements & Vue **Activité** (Chantier 3) : débits globaux, filtres par statut (Tous, En cours, Terminés, Actifs, En pause) avec compteurs en direct, barres de progression par release, ETA restant, nombre de pairs, statuts en français, pause/reprise, suppression avec ou sans données, scan Jellyfin immédiat ou automatique à 100%.
- Détection d'échec & Bascule automatique (Torrent Stalled Fallback) : détection des torrents bloqués (0% et 0 pairs après délai configurable `stalled_hours`, ou erreur Transmission), purge du torrent, mise en liste noire (`Blacklist`) SQLite, démarquage bibliothèque et relance automatique de la surveillance pour saisir la release candidate suivante.
- Moteur de décision intelligent (chantier 2) : analyseur de release, classement MULTI/VFF/VOSTFR,
  rejet des sources dégradées (CAM/TS/TC), double recherche titre français + original TMDB,
  minimisation du nombre de releases pour couvrir les saisons/séries, liste noire SQLite.
- Intégration Jellyfin (alerte de disponibilité unitaire ou multi-titres/franchises dès la recherche manuelle, badge « Dans Jellyfin »,
  bouton Lire direct, scan après téléchargement).
- Autonomie locale complète des assets (Zéro CDN) : Tailwind, Tabler Icons et HTMX servis localement depuis `/static/`, sans dépendance externe.
- Multi-utilisateur (admin / membre / invité) + file de demandes validée par l'admin.
- Notifications (Discord, ntfy, Telegram, webhook).
- Réglages entièrement dans l'UI, dont un **panneau « État des connexions »**.
- Durcissement sécurité (chantier 1, voir §7).

Qualité : **548 tests**, ruff et mypy propres, CI GitHub Actions sur chaque push/PR.

## 3. Démarrer

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check torsearch tests    # lint
mypy                          # typage
pytest -q                     # tests (~5 s)

uvicorn torsearch.main:get_app --factory --reload   # http://localhost:8000
```

Sans `TORSEARCH_USERNAME`/`TORSEARCH_PASSWORD`, l'auth est désactivée (tout le monde est
admin) : pratique en dev. Les données vont dans `data/torsearch.db` (SQLite, gitignoré).

## 4. Architecture

Python 3.12+, **FastAPI + Jinja2 + HTMX**, Tailwind (CDN pour l'instant), **SQLite**.

| Module | Rôle |
|---|---|
| `main.py` | `build_app()` : assemble la base, les stores, le contexte, le moteur de surveillance. |
| `context.py` | `AppContext` : config courante + clients (recherche, Transmission, TMDB, Jellyfin), reconstruits à chaque changement de réglages. Repli `TMDB_API_KEY` si aucune clé en base. |
| `config.py` | Modèles pydantic **gelés** de la config (trackers, Transmission, profil, chemins…). |
| `db/database.py` | Mini document-store sur SQLite (WAL) : `collection(name)` → `get/upsert/delete/all`. |
| `settings/` | `store.py` (config persistée en base, amorcée une fois depuis un YAML) ; `mutations.py` (fonctions pures qui renvoient une nouvelle `Config`, valident les noms). |
| `indexers/torznab.py` | Client Torznab : recherche, `test()` (`t=caps`), suivi **sûr** des redirections. |
| `parser/release.py` | Parseur de nom de release (titre, année, SxxEyy, résolution, source, flag `is_banned_source`, langue, codec). |
| `search/` | `service.py` (recherche parallèle, dédoublonnage) ; `matcher.py` (vérification stricte du titre/année, rejet des suites et faux-positifs) ; `decision.py` (ranking langues/qualité, sélection optimale, couverture gloutonne des saisons) ; `filters.py` (filtres basiques). |
| `transmission/client.py` | Façade **async** sur `transmission-rpc` (bloquant) : pool de threads dédié, délais 10 s / 60 s pour l'ajout. |
| `metadata/tmdb.py` | Client TMDB (httpx) avec support `original_title`. |
| `jellyfin/client.py` | Client Jellyfin (httpx) avec cache mémoire des items (30s) et détection de présence (`find_matching()`). |
| `library/` | Films, séries, analyse `SxxEyy` (`episodes.py`), liste noire persistante (`blacklist.py`). |
| `monitor/runner.py` | Boucle de surveillance : auto-grab avec double titre (VF+VO), moteur de décision, rejet liste noire. |
| `health.py` | Panneau d'état : `check_all()` lance tous les `test()` en parallèle. |
| `redact.py` | Masque les secrets dans les messages d'erreur affichés. |
| `users/`, `requests/` | Comptes (PBKDF2) et demandes. |
| `web/` | Routes par domaine (`*_routes.py`), auth (`auth.py`, `authz.py`), `forms.py`, templates, `static/app.js`. |

Flux typique : route HTMX → `request.app.state.ctx` (AppContext) → client/service → template
partiel renvoyé et injecté par HTMX. La surveillance tourne dans la même boucle asyncio
(lifespan FastAPI), désactivée par défaut (opt-in dans l'UI).

## 5. Méthode de travail (à suivre)

- **Un chantier = une spec + un plan + une PR.** Specs et plans dans
  `docs/superpowers/specs/` et `docs/superpowers/plans/` (format daté, en français) : lire les
  plus récents pour le style.
- **TDD** : chaque correctif commence par un test qui échoue ; un commit par correctif.
- **Commits** : `type(portée): description` en français (`fix(auth): …`, `feat(settings): …`).
- **PR** fusionnées en **squash**, sujet suffixé `(#N)`. CI verte obligatoire.
- **Release** : l'image `ghcr.io/larhatis/torrsearch` (amd64 + arm64) n'est reconstruite que
  sur un **tag `v*`** (`gh release create vX.Y.Z --target <sha de main>`). L'utilisateur met à
  jour avec *Pull* puis *Up* dans son plugin Compose.
- **Langue** : docstrings et commentaires en **anglais** ; textes affichés en **français** ;
  les **templates HTML s'écrivent sans accents** (`Reglages`, `inchange si vide`) — garder
  cette convention.
- Tests : `respx` pour les appels HTTP, faux objets (fakes) pour Transmission/Jellyfin/TMDB ;
  les faux clients Transmission sont `async`.

## 6. Règles de sécurité (ne pas régresser)

1. **Aucun JS inline** dans les templates (`onclick=`, `onerror=`, `hx-on`…) : tout passe par
   des attributs `data-*` lus par `static/app.js`. Un test (`tests/test_no_inline_js.py`) le
   vérifie.
2. **Aucun secret renvoyé au navigateur** : champs secrets toujours vides, « vide = valeur
   conservée » **seulement si la destination (hôte/URL) ne change pas**, sinon ressaisie.
3. **Aucun secret dans un message d'erreur affiché** : code HTTP seul ou `redact()`.
4. Le **rôle** est relu en base à chaque requête ; la session contient une empreinte du hash
   du mot de passe (compte recréé = anciennes sessions invalides).
5. Requêtes non sûres marquées **cross-site / same-site** par le navigateur → 403
   (`CrossSiteGuardMiddleware`, actif même sans auth).
6. Redirections de tracker suivies **uniquement vers le même hôte**, jamais `https` → `http`.
7. Appels Transmission **jamais** directement dans la boucle async (toujours via la façade).

## 7. Pièges connus

- **Jellyfin 12** n'accepte plus `?api_key=` : utiliser l'en-tête
  `Authorization: MediaBrowser Token="…"` (déjà fait, ne pas revenir en arrière).
- Beaucoup de trackers attendent leur **clé API** (page de profil), **pas la passkey** ; l'URL
  doit être l'**adresse complète de l'API Torznab** (souvent `…/api/`).
- La config YAML d'amorçage (`TORSEARCH_CONFIG`) n'est lue qu'**au premier démarrage** ;
  ensuite la vérité est en base.
- En Docker, **`TORSEARCH_DB=/data/torsearch.db` est indispensable** (sinon la base reste
  dans le conteneur). Sans `TORSEARCH_SECRET_KEY`, la clé de session est générée dans le
  conteneur (hors volume) → déconnexion à chaque recréation (à corriger, voir §8).
- `transmission-rpc` est synchrone et fait un appel réseau dès la création du client.
- Les noms (trackers, recherches, canaux) servent d'identifiants dans les URL : caractères
  `/ \ ? # %`, `.`/`..` et espaces en bordure refusés.
- Attention aux **imports circulaires** : `torsearch.monitor.runner` et `torsearch.search.decision`
  ne doivent pas s'importer mutuellement à la racine. Les utilitaires d'épisodes sont dans `torsearch.library.episodes`.
- **Fakes de test & dédoublonnage** : ne pas fabriquer d'infohash fictif en tronquant le titre (`title[:12]`)
  car des releases partageant un préfixe (ex. `Avatar.2009.`) entreraient en collision et seraient dédoublonnées.
- `.gitignore` : règles **ancrées** à la racine (`/data/`, `/config.yaml`, `/transmission/`).
- **Dépôt public** : ne pas y écrire de noms de trackers privés, d'infos personnelles
  (chemins de disques, IP) ni de secrets.

## 8. Feuille de route (ordre recommandé)

**Chantier 2 — moteur de décision (terminé en v0.3.0)** : auto-grab fiable.
- Analyse des noms de release (`parser/release.py` : titre, année, SxxEyy, résolution, source, langue, codec).
- Vérification que la release correspond au titre (`search/matcher.py` : rejet des faux-positifs et des suites).
- Double recherche TMDB avec titre français + titre original.
- Profil qualité avec priorités linguistiques (MULTI/VFF > VF/VFQ > VOSTFR, rejet VO pure) et rejet automatique des sources dégradées (CAM/TS/TC/SCR).
- Minimisation gloutonne du nombre de releases pour couvrir les saisons de séries (`search/decision.py`).
- Liste noire SQLite persistante (`library/blacklist.py`) pour éviter de re-télécharger des releases mortes ou échouées.
- Détection et alerte visuelle de disponibilité Jellyfin dans la recherche manuelle.

**Chantier 3 — suivi des téléchargements (terminé en v0.3.7)** :
1. **Mémorisation de l'infohash** : stockage du hash Transmission (`info_hash`) lors du grab (films et épisodes).
2. **Statuts en direct / Vue Activité** : polling HTMX avec onglet Activité interrogeant Transmission (statuts en français, filtres avec compteurs, %, débits, ETA, pairs).
3. **Détection d'échec & bascule** : détection des torrents bloqués (0% / 0 pairs après `stalled_hours` ou erreur) → suppression du torrent, ajout à la `Blacklist` SQLite, démarquage bibliothèque et relance automatique de l'auto-grab.
4. **Rafraîchissement Jellyfin ciblé** : scan Jellyfin manuel ou automatique dès qu'un torrent atteint 100%.

**Chantier 4 — interface & expérience utilisateur (en cours)** :
- Assets servis localement (Zéro CDN : Tailwind, Tabler Icons, HTMX) : terminé en v0.3.7.
- Pages détail film et série avec synopsis, statut Jellyfin et recherche 1-clic : terminé en v0.3.7.
- Interface tactile entièrement responsive mobile (Bottom bar, cartes adaptatives, menus tactiles) : terminé en v0.3.8.
- Prochaines étapes : menu simplifié, favicon local, Réglages en onglets.

**Petits chantiers** : clé de session dans le volume `/data` ; changement de mot de passe
dans l'UI ; notifier le demandeur ; masquer les secrets dans les logs ; liens de
téléchargement sans clé de tracker côté membres (identifiants de résultat côté serveur) ;
limiter la fréquence des requêtes aux trackers ; sauvegarde/export de la base.
