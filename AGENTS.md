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

## 2. État actuel (v0.3.0)

Fonctionnel et en production chez l'utilisateur (OpenMediaVault, Docker) :

- Recherche multi-trackers Torznab (parallèle, dédoublonnage, filtres, tri).
- Découverte TMDB (tendances, recherche par titre, affiches).
- Bibliothèque **Films** (≈ Radarr-lite) et **Séries** (≈ Sonarr-lite) avec surveillance en
  tâche de fond et téléchargement automatique.
- Moteur de décision intelligent (chantier 2) : analyseur de release, classement MULTI/VFF/VOSTFR,
  rejet des sources dégradées (CAM/TS/TC), double recherche titre français + original TMDB,
  minimisation du nombre de releases pour couvrir les saisons/séries, liste noire SQLite.
- Intégration Jellyfin (alerte de disponibilité dès la recherche manuelle, badge « Dans Jellyfin »,
  bouton Lire direct, scan après téléchargement).
- Multi-utilisateur (admin / membre / invité) + file de demandes validée par l'admin.
- Notifications (Discord, ntfy, Telegram, webhook).
- Réglages entièrement dans l'UI, dont un **panneau « État des connexions »**.
- Durcissement sécurité (chantier 1, voir §7).

Qualité : **478 tests**, ruff et mypy propres, CI GitHub Actions sur chaque push/PR.

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
| `search/` | `service.py` (recherche parallèle, délai, dédoublonnage) ; `filters.py` (filtres, détection de qualité). |
| `transmission/client.py` | Façade **async** sur `transmission-rpc` (bloquant) : pool de threads dédié, délais 10 s / 60 s pour l'ajout. |
| `metadata/tmdb.py`, `jellyfin/client.py` | Clients HTTP (httpx), résilients (ne lèvent jamais vers le web). |
| `library/` | Films, séries, analyse `SxxEyy` (`episodes.py`). |
| `monitor/runner.py` | Boucle de surveillance : recherches sauvegardées, films, séries, refresh Jellyfin. |
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
- `.gitignore` : règles **ancrées** à la racine (`/data/`, `/config.yaml`, `/transmission/`).
- **Dépôt public** : ne pas y écrire de noms de trackers privés, d'infos personnelles
  (chemins de disques, IP) ni de secrets.

## 8. Feuille de route (ordre recommandé)

**Chantier 2 — moteur de décision (terminé en v0.3.0)** : auto-grab fiable.
- Analyse des noms de release (titre, année, SxxEyy, résolution, source, langue, codec).
- Vérification que la release correspond au titre (rejet des faux-positifs et des suites).
- Double recherche TMDB avec titre français + titre original.
- Profil qualité avec priorités linguistiques (MULTI/VFF > VF/VFQ > VOSTFR, rejet VO pure) et rejet automatique des sources dégradées (CAM/TS/TC/SCR).
- Minimisation gloutonne du nombre de releases pour couvrir les saisons de séries.
- Liste noire SQLite persistante pour éviter de re-télécharger des releases mortes ou échouées.

**Chantier 3 — suivi des téléchargements** : mémoriser le hash Transmission de chaque grab,
afficher « en file / % / terminé / bloqué », échec → liste noire → autre release, refresh
Jellyfin ciblé.

**Chantier 4 — interface** : assets servis localement (fin des CDN, CSP possible, favicon),
menu simplifié (Découvrir · Bibliothèque · Recherche · Activité · Réglages), pages détail
film/série, Réglages en onglets.

**Petits chantiers** : clé de session dans le volume `/data` ; changement de mot de passe
dans l'UI ; notifier le demandeur ; masquer les secrets dans les logs ; liens de
téléchargement sans clé de tracker côté membres (identifiants de résultat côté serveur) ;
limiter la fréquence des requêtes aux trackers ; sauvegarde/export de la base.
