# TorrSearch

![CI](https://github.com/Larhatis/TorrSearch/actions/workflows/ci.yml/badge.svg)

Recherche un film ou une serie sur **plusieurs trackers Torznab a la fois** et envoie le
resultat choisi a **Transmission** — depuis une interface web. Une alternative legere et
auto-hebergee a Prowlarr/Jackett + Sonarr/Radarr, a configurer entierement au clic.

## Fonctionnalites

- 🔎 **Recherche multi-trackers** Torznab, en parallele, fusionnee et dedoublonnee.
- 🎛️ **Tout se configure dans l'UI** (page Reglages) : trackers, connexion Transmission — rien a coder.
- 🧰 **Filtres & tri** : seeders, taille, qualite (4K/1080p…), exclusion de mots ; colonnes triables.
- ⬇️ **Envoi a Transmission** en un clic + page **Telechargements** (suivi en direct, pause/reprise/suppression).
- 🛰️ **Surveillance auto** : recherches sauvegardees qui tournent en fond et envoient (ou signalent) les nouveaux resultats.

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
- Toute la config est persistee dans `data/settings.json` (volume, jamais versionne).

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
