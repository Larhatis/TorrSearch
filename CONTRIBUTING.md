# Contribuer à TorrSearch

Merci de ton intérêt ! Les contributions sont les bienvenues : corrections, idées,
documentation, code.

## Avant de coder

- Pour un **bug**, ouvre une issue avec les étapes de reproduction.
- Pour une **fonctionnalité**, ouvre d'abord une issue pour en discuter — ça évite de
  coder quelque chose qui ne collerait pas à la direction du projet.

## Mise en place

Prérequis : Python 3.12+.

```bash
git clone https://github.com/Larhatis/TorrSearch.git
cd TorrSearch
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Lancer l'app en local :

```bash
uvicorn torsearch.main:get_app --factory --reload   # http://localhost:8000
```

## Avant d'ouvrir une PR

La CI lance lint, typage et tests — fais-les passer en local :

```bash
ruff check torsearch tests      # style / imports
mypy                            # typage
pytest                          # tests (la suite doit rester verte)
```

`ruff check --fix` corrige automatiquement la plupart des soucis de style.

## Conventions

- **TDD** quand c'est pertinent : un test qui échoue, puis le code qui le fait passer.
- Garde les modules **petits et ciblés** ; suis les patterns existants (stores JSON
  atomiques, clients réseau résilients qui n'exigent jamais d'exception vers la couche web).
- Messages de commit clairs ; une PR = un sujet.
- Toute nouvelle fonctionnalité passe par une issue/discussion d'abord (cf. ci-dessus).

## Périmètre du projet

TorrSearch est un agrégateur de **recherche** (façon Prowlarr/Jackett) + un orchestrateur
léger Radarr/Sonarr/Jellyseerr-lite. Il **ne fournit aucun contenu** et ne vise pas à
remplacer Jellyfin (il s'y intègre). Les propositions qui sortent de ce cadre seront
probablement refusées — n'hésite pas à demander en cas de doute.
