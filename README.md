# TorSearch

Recherche un film/serie sur plusieurs trackers Torznab a la fois et envoie le
resultat choisi a Transmission. Outil web perso, auto-heberge.

## Lancer en local

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml   # editer les trackers
cp .env.example .env                 # renseigner les passkeys
uvicorn torsearch.main:get_app --factory --reload
```

Ouvrir http://localhost:8000

## Lancer avec Docker

```bash
mkdir -p config
cp config.example.yaml config/config.yaml
cp .env.example .env                 # renseigner les passkeys
docker compose up -d --build
```

Ouvrir http://localhost:8080

## Tests

```bash
python -m pytest
```

## Configuration

- `config.yaml` : trackers (Torznab) + connexion Transmission.
- Les passkeys sont injectees via `${VAR}` depuis l'environnement / `.env`.
- Ajouter un tracker Torznab = une entree dans `indexers:` (aucun code).
