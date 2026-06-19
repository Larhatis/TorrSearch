# Distribution — rendre TorSearch partageable — Spec de conception

> Date : 2026-06-19
> Statut : approuvé (carte blanche), en implémentation
> Construit sur l'état actuel de `main` (v1 + Réglages + filtres/tri + downloads + surveillance).

## 1. Contexte & objectif

L'utilisateur veut que **n'importe qui puisse cloner le repo et lancer sa propre instance**,
avec **sa propre config** (modèle auto-hébergé, pas de comptes ni de multi-tenant).

> **Bonne nouvelle :** l'architecture le permet déjà — toute la config passe par l'UI, rien
> n'est codé en dur, les secrets sont gitignorés. Ce projet est donc du **polissage pour la
> distribution et la prise en main**, pas une refonte.

**Objectif :** qu'un nouveau venu fasse `docker compose up -d`, ouvre l'app, et configure tout
dans l'UI — sans éditer un seul fichier.

## 2. Décisions (brainstorming)

| Sujet | Décision |
|---|---|
| Stack Docker | **TorSearch + Transmission** embarqués et pré-câblés ; le README explique aussi comment brancher un Transmission existant. |
| Licence | **MIT**. |
| CI | **GitHub Actions** dès maintenant (pytest). |
| Auth / comptes | **Hors périmètre** (chacun héberge la sienne sur son réseau ; auth optionnelle plus tard). |

## 3. Périmètre

### Dans ce lot (in scope)

1. **`docker-compose.yml` stack complet** : services `torsearch` + `transmission`
   (`lscr.io/linuxserver/transmission`), `restart: unless-stopped`, volumes persistants, **TorSearch
   pré-câblé sur le service `transmission`** (plus `localhost`). L'app **démarre vide** ; le nouveau
   venu configure ses trackers dans `/settings`.
2. **README** réécrit pour un public externe : pitch, fonctionnalités, **quickstart Docker**,
   guide de config, « utiliser son propre Transmission », **disclaimer légal/usage**, mention de la
   licence et note « contributions bienvenues ».
3. **LICENSE** MIT (au nom de Clément Cappeau, 2026).
4. **Onboarding « état vide »** : sur la page de recherche, si **aucun tracker** n'est configuré,
   afficher un message « 👉 Ajoute tes trackers dans Réglages pour commencer » (lien vers `/settings`).
5. **CI GitHub Actions** : workflow qui installe et lance `pytest` à chaque push / pull request.

### Hors périmètre

Comptes utilisateurs · multi-tenant · auth de l'app · captures d'écran auto dans le README
(pourront être ajoutées ensuite) · publication d'une image sur un registry.

## 4. Conception détaillée

### 4.1 Pré-câblage Transmission (zéro édition de fichier)

Problème : par défaut `TransmissionConfig.host = "localhost"`, ce qui ne marche pas entre
conteneurs (il faut le nom de service `transmission`).

Solution **sans changement de code applicatif** : un fichier d'**amorçage** versionné
`deploy/bootstrap.yaml` (pas de secret dedans) :
```yaml
transmission:
  host: transmission
  port: 9091
```
Le compose le monte en lecture seule et pointe `TORSEARCH_CONFIG` dessus. Au **premier** démarrage,
`SettingsStore` amorce `data/settings.json` avec `host: transmission` → l'app parle tout de suite au
Transmission embarqué. Ensuite, tout changement se fait dans `/settings` (qui prime sur l'amorçage).

> `deploy/bootstrap.yaml` ne matche pas le motif `config.yaml` du `.gitignore`, donc il est bien
> versionné (contrairement au `config.yaml` perso qui reste ignoré).

### 4.2 `docker-compose.yml`

```yaml
services:
  torsearch:
    build: .
    container_name: torsearch
    ports: ["8080:8000"]
    environment:
      - TORSEARCH_SETTINGS=/data/settings.json
      - TORSEARCH_MONITOR=/data/monitor.json
      - TORSEARCH_CONFIG=/bootstrap/bootstrap.yaml
    volumes:
      - ./data:/data
      - ./deploy/bootstrap.yaml:/bootstrap/bootstrap.yaml:ro
    depends_on: [transmission]
    restart: unless-stopped

  transmission:
    image: lscr.io/linuxserver/transmission:latest
    container_name: transmission
    ports: ["9091:9091", "51413:51413", "51413:51413/udp"]
    environment: [PUID=1000, PGID=1000, TZ=Etc/UTC]
    volumes:
      - ./transmission/config:/config
      - ./transmission/downloads:/downloads
    restart: unless-stopped
```
`.gitignore` : ajouter `transmission/` (config + téléchargements de l'utilisateur ne doivent pas être versionnés).

### 4.3 Onboarding « état vide »

- `GET /` passe au template `has_trackers = bool(ctx.config.indexers)`.
- `index.html` : si `not has_trackers`, afficher au-dessus du formulaire une bannière discrète
  avec un lien vers `/settings`. N'affecte pas la recherche elle-même.

### 4.4 README (structure)

Titre + pitch une ligne + badge CI · « Fonctionnalités » (recherche multi-trackers Torznab,
réglages UI, filtres/tri, suivi des téléchargements, surveillance auto) · **Démarrage rapide**
(`docker compose up -d` → `http://localhost:8080` → Réglages) · **Configuration** (ajouter des
trackers Torznab, connexion Transmission, brancher un Transmission externe) · **Développement**
(venv + `pytest`) · **Disclaimer** (outil de recherche/agrégation type Prowlarr ; l'usage et le
respect du droit d'auteur et des règles des trackers relèvent de l'utilisateur) · **Licence** (MIT).

### 4.5 CI (`.github/workflows/ci.yml`)

Déclencheurs : `push` et `pull_request`. Job unique sur `ubuntu-latest`, Python **3.12** (cible
Docker) : checkout → setup-python → `pip install -e ".[dev]"` → `pytest`.

## 5. Tests

- **Onboarding** (`tests/test_web.py`) : `GET /` avec une config **sans tracker** contient le
  message d'invitation + un lien `/settings` ; avec au moins un tracker, le message **n'apparaît pas**.
- Le reste (compose, README, LICENSE, CI, bootstrap) = fichiers statiques : vérifiés par revue +
  `docker compose config` (lint du compose) et un boot réel hors-TDD.

## 6. Fichiers

| Fichier | Action |
|---|---|
| `docker-compose.yml` | Remplacer — stack TorSearch + Transmission pré-câblé. |
| `deploy/bootstrap.yaml` | Créer — amorçage `transmission.host`. |
| `.gitignore` | Modifier — `+ transmission/`. |
| `torsearch/web/routes.py` | Modifier — `GET /` passe `has_trackers`. |
| `torsearch/web/templates/index.html` | Modifier — bannière état vide. |
| `tests/test_web.py` | Modifier — tests onboarding. |
| `README.md` | Réécrire pour public externe. |
| `LICENSE` | Créer — MIT. |
| `.github/workflows/ci.yml` | Créer. |

## 7. Notes

- Le `Dockerfile` existant (python:3.12-slim, `uvicorn ... --factory`) est réutilisé tel quel.
- Aucun secret n'est versionné : trackers/passkeys/connexion s'ajoutent via l'UI (persistés dans
  `data/`, gitignoré). `deploy/bootstrap.yaml` ne contient que l'hôte du service Transmission.
- Captures d'écran du README : ajoutables ensuite (depuis l'app lancée), non bloquant.
