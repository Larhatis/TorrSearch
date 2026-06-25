# TorrSearch

![CI](https://github.com/Larhatis/TorrSearch/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)

Recherche un film ou une serie sur **plusieurs trackers Torznab a la fois** et envoie le
resultat choisi a **Transmission** — depuis une interface web. Une alternative legere et
auto-hebergee a Prowlarr/Jackett + Sonarr/Radarr, a configurer entierement au clic.

## Fonctionnalites

- 🔎 **Recherche multi-trackers** Torznab, en parallele, fusionnee et dedoublonnee.
- 🎬 **Decouverte (TMDB)** : **tendances** au chargement + recherche par vrai titre (affiches), puis les torrents en un clic.
- 📚 **Bibliotheque Films & Series** (Radarr-lite + Sonarr-lite) : ajoute un film/serie « voulu » ; **auto-grabbe** le film, ou **chaque nouvel episode** de la serie, des qu'une release conforme au profil de qualite apparait.
- 🎞️ **Integration Jellyfin** : marque ce que tu **possedes deja** (« Dans Jellyfin ») et ouvre la **lecture** d'un clic.
- 🛰️ **Surveillance auto** : recherches sauvegardees qui tournent en fond et envoient (ou signalent) les nouveaux resultats.
- 🔔 **Notifications** (Discord / ntfy / Telegram / webhook) sur les grabs et les trouvailles.
- 🎛️ **Tout se configure dans l'UI** (page Reglages) : trackers, Transmission, profil de qualite — rien a coder.
- 🧰 **Filtres & tri** : seeders, taille, qualite (4K/1080p…), exclusion de mots.
- ⬇️ **Envoi a Transmission** en un clic + page **Telechargements** (suivi en direct, pause/reprise/suppression).
- 🔒 **Auth multi-utilisateur optionnelle** (admin / membre / invite) avec mots de passe hashes.

## Demarrage rapide (Docker)

Pre-requis : Docker + Docker Compose.

```bash
git clone https://github.com/Larhatis/TorrSearch.git
cd TorrSearch
docker compose up -d
```

Ouvre **http://localhost:8080**. L'app demarre **vide** : va dans **Reglages** pour ajouter tes
trackers (URL Torznab + passkey). Transmission est inclus dans le compose et deja branche.

> Tu as deja ton propre Transmission ? Dans **Reglages → Transmission**, remplace l'hote
> `transmission` par l'adresse de ton instance (et retire le service `transmission` du
> `docker-compose.yml` si tu n'en veux pas).

## Configuration

- **Trackers** : Reglages → ajoute un tracker Torznab (nom, URL, passkey). Le bouton **Tester** verifie que ca repond.
- **Transmission** : Reglages → hote / port / identifiants.
- **Decouverte (TMDB)** : renseigne `TMDB_API_KEY` (cle gratuite sur [themoviedb.org](https://www.themoviedb.org/)) en variable d'environnement pour activer la page **Decouvrir** (tendances + recherche) et la **Bibliotheque**.
- **Jellyfin (optionnel)** : Reglages → URL + cle API. TorrSearch marque alors les medias deja presents dans ton Jellyfin et propose un lien de lecture (Jellyfin reste ton serveur media).
- **Auth & utilisateurs (optionnel)** : definis `TORSEARCH_USERNAME` et `TORSEARCH_PASSWORD` pour exiger un login (desactive si l'une manque). Ce compte devient l'**administrateur** au premier demarrage. L'admin gere ensuite les autres comptes dans Reglages → **Utilisateurs**, avec trois roles : **admin** (tout), **membre** (recherche manuelle + ajout direct), **invite** (parcourir et demander). Les demandes des invites arrivent dans l'ecran **Demandes** ou l'admin approuve (ajout a la bibliotheque) ou refuse. Mots de passe stockes hashes dans `data/users.json`, demandes dans `data/requests.json`. Voir `.env.example`.
- Toute la config est persistee dans `data/settings.json` (volume, jamais versionne) ; les bibliotheques dans `data/library.json` (films) et `data/series.json` (series).

## Developpement

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn torsearch.main:get_app --factory --reload   # http://localhost:8000
```

## Avertissement

TorrSearch est un outil de **recherche et d'agregation** (comme Prowlarr/Jackett). Il ne fournit
aucun contenu. L'usage que tu en fais, le respect du droit d'auteur et des regles des trackers
relevent de **ta** responsabilite et des lois de ton pays.

## Licence

[MIT](LICENSE) — contributions bienvenues (ouvre une issue ou une PR).
