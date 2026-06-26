# TorrSearch

[![CI](https://github.com/Larhatis/TorrSearch/actions/workflows/ci.yml/badge.svg)](https://github.com/Larhatis/TorrSearch/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12+-blue)
[![Lint: Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Recherche un film ou une série sur **plusieurs trackers Torznab à la fois** et envoie le
résultat choisi à **Transmission**, depuis une interface web. Une alternative légère,
auto-hébergée et tout-en-un à la pile Prowlarr/Jackett + Radarr/Sonarr + Jellyseerr — qui
se configure entièrement au clic et s'intègre à ton serveur Jellyfin.

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Démarrage rapide](#démarrage-rapide-docker)
- [Configuration](#configuration)
- [Rôles & demandes](#rôles--demandes)
- [Sécurité & exposition](#sécurité--exposition)
- [Données](#données)
- [Développement](#développement)
- [Avertissement](#avertissement)
- [Contribuer](#contribuer) · [Licence](#licence)

## Fonctionnalités

| Domaine | Détail |
| --- | --- |
| Recherche | Multi-trackers **Torznab** en parallèle, résultats fusionnés et dédoublonnés, avec filtres et tri (seeders, taille, qualité, exclusion de mots). |
| Découverte | **TMDB** : tendances au chargement et recherche par vrai titre (affiches), puis les torrents en un clic. |
| Bibliothèque | **Films & Séries** (Radarr-lite + Sonarr-lite) : marque un titre « voulu », l'app récupère automatiquement le film ou chaque nouvel épisode dès qu'une release conforme au profil de qualité apparaît. |
| Jellyfin | Marque ce que tu possèdes déjà (« Dans Jellyfin ») et ouvre la lecture d'un clic ; Jellyfin reste ton serveur média. |
| Surveillance | Recherches sauvegardées qui tournent en tâche de fond et grabbent (ou signalent) les nouveautés. |
| Multi-utilisateur | Comptes **admin / membre / invité** avec mots de passe hachés, et une **file de demandes** validée par l'admin. |
| Notifications | Discord, ntfy, Telegram ou webhook sur les grabs et les trouvailles. |
| Téléchargements | Envoi à Transmission en un clic et page de suivi en direct (pause / reprise / suppression). |
| Configuration | Tout depuis l'interface (page **Réglages**) : trackers, Transmission, profil de qualité, Jellyfin, dossiers, comptes. |

## Démarrage rapide (Docker)

Prérequis : Docker et Docker Compose.

```bash
git clone https://github.com/Larhatis/TorrSearch.git
cd TorrSearch
cp .env.example .env        # identifiants admin + clé TMDB (facultatif)
docker compose up -d
```

Le compose tire l'image publiée `ghcr.io/larhatis/torrsearch` et démarre un Transmission
déjà branché. Ouvre ensuite **http://localhost:8080**.

L'application démarre vide : va dans **Réglages** pour ajouter tes trackers (URL Torznab +
passkey).

> **Déjà ton propre Transmission ?** Dans **Réglages → Transmission**, remplace l'hôte
> `transmission` par l'adresse de ton instance, et retire le service `transmission` du
> `docker-compose.yml` si tu n'en veux pas.

## Configuration

Tout se règle dans l'interface ; quelques options passent par l'environnement (voir
[`.env.example`](.env.example)).

| Réglage | Où | Détail |
| --- | --- | --- |
| Trackers | Réglages → Trackers | Nom, URL Torznab, passkey. Le bouton **Tester** vérifie la connexion. |
| Transmission | Réglages → Transmission | Hôte, port, identifiants. |
| Découverte | `TMDB_API_KEY` | Clé gratuite sur [themoviedb.org](https://www.themoviedb.org/) (Réglages → API). Active la page **Découvrir** et la bibliothèque. |
| Jellyfin | Réglages → Jellyfin | URL + clé API, pour marquer les médias déjà présents et proposer la lecture. |
| Authentification | `TORSEARCH_USERNAME` / `TORSEARCH_PASSWORD` | Active la connexion ; ce compte devient l'**administrateur** au premier démarrage. Désactivée si l'une manque. |

## Rôles & demandes

L'authentification activée, l'admin gère les comptes dans **Réglages → Utilisateurs**.

| Rôle | Réglages & comptes | Valider les demandes | Recherche manuelle + ajout direct | Découvrir & demander |
| --- | :---: | :---: | :---: | :---: |
| **Admin** | oui | oui | oui | oui |
| **Membre** | — | — | oui | oui |
| **Invité** | — | — | — | oui |

Les demandes des invités arrivent dans l'écran **Demandes**, où l'admin approuve (le titre
rejoint alors la bibliothèque et la surveillance le récupère) ou refuse. Chaque utilisateur
suit l'état de ses propres demandes dans **Mes demandes**.

## Sécurité & exposition

- TorrSearch **ne gère pas le TLS**. Pour une exposition hors réseau local, place-le
  **derrière un reverse proxy HTTPS** (Caddy, Traefik, Nginx Proxy Manager…) et mets
  `TORSEARCH_HTTPS=1` pour que le cookie de session soit `Secure`.
- **Active l'authentification** et choisis un **mot de passe fort** : l'app prévient au
  démarrage si le mot de passe administrateur est trivial.
- Le login est protégé contre la force brute (blocage temporaire après plusieurs échecs),
  l'app envoie des en-têtes de sécurité de base, et le conteneur tourne en **non-root**.

## Données

Toutes les données (configuration, comptes, bibliothèques, demandes, historique) sont
persistées dans une base **SQLite** `data/torsearch.db` (volume, jamais versionné). Les
anciens fichiers `data/*.json` éventuels sont importés automatiquement au premier
démarrage, puis conservés en sauvegarde.

## Développement

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check torsearch tests     # style
mypy                           # typage
pytest                         # tests

uvicorn torsearch.main:get_app --factory --reload   # http://localhost:8000
```

Stack : FastAPI, HTMX, Tailwind, Jinja2, SQLite — sans build front. La CI lance lint,
typage et la suite de tests à chaque push.

## Avertissement

TorrSearch est un outil de **recherche et d'agrégation** (comme Prowlarr/Jackett) : il ne
fournit aucun contenu. L'usage que tu en fais, le respect du droit d'auteur et des règles
des trackers relèvent de **ta** responsabilité et des lois de ton pays.

## Contribuer

Les contributions sont bienvenues — voir [CONTRIBUTING.md](CONTRIBUTING.md) pour la mise en
place et les conventions. Pour une faille de sécurité, suis [SECURITY.md](SECURITY.md)
(signalement privé, jamais d'issue publique).

## Licence

Distribué sous licence [MIT](LICENSE).
