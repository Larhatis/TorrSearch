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

- Au **premier** demarrage, l'app lit `config.yaml` (amorcage) et ecrit `data/settings.json`.
- Ensuite, **toute la configuration se fait depuis la page Reglages** (http://localhost:8000/settings) :
  trackers, connexion Transmission, timeout. Chaque sauvegarde s'applique immediatement (pas de redemarrage).
- `data/settings.json` est la source de verite (gitignore). `config.yaml` ne sert qu'a l'amorcage initial
  et reste optionnel : sans lui, l'app demarre vide et tu ajoutes tout via l'UI.
- Bouton **Tester** sur chaque tracker pour verifier URL + passkey.
