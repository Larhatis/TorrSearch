# Chantier 12 — mises à jour sûres (design)

Date : 2026-11-15 · Version visée : v0.10.2

## Intention

Une release ne doit plus pouvoir casser la production à cause d'une dépendance qui a bougé
toute seule. Aujourd'hui `pyproject.toml` ne donne que des minimums (`fastapi>=0.111`…) : chaque
tag reconstruit l'image avec les dernières versions publiées ce jour-là. C'est ainsi qu'est arrivé
l'incident de la v0.4.1 (`transmission-rpc` 7 : `added_date` au lieu de `date_added`, la purge
supprimait des torrents tout juste ajoutés).

## Objectifs

1. **Versions exactes** : un fichier `requirements.lock` (toutes les dépendances, transitives
   comprises) utilisé comme contraintes par le Dockerfile **et** la CI. Même code ⇒ même image.
2. **Montées de version visibles** : Dependabot propose chaque semaine des PR (pip, actions
   GitHub, image Docker de base), testées par la CI avant fusion.
3. **L'image est testée avant le tag** : sur chaque PR, la CI construit l'image Docker, la démarre
   et vérifie que `/healthz` répond. Une dépendance qui casse le démarrage se voit dans la PR.

## Non-objectifs

- L'anti-doublon des recherches libres (historique limité à 1000 entrées) : abandonné. En
  production : aucune recherche libre, 40 entrées d'historique en un mois ; films et séries ont
  leur propre état.
- Hashes de paquets (`--require-hashes`) : incompatibles avec un fichier de contraintes, gain
  faible pour une app auto-hébergée.
- Pas de nouvel outil obligatoire pour contribuer : `pip install -e ".[dev]"` marche toujours.

## Anti-objectifs

- Une image qui ne démarre plus sur arm64 (le NAS) ou amd64 parce que le lock a été résolu pour
  macOS seulement.
- Un lock qui dérive en silence du `pyproject.toml`.

## Approches envisagées

| Approche | Pour | Contre |
|---|---|---|
| **`uv pip compile --universal`** (retenue) | Résolution multi-plateformes (marqueurs) depuis n'importe quelle machine ; rapide ; fichier `requirements` standard que pip et Dependabot savent lire. | uv nécessaire pour **régénérer** le lock (pas pour installer). |
| `pip-compile` (pip-tools) | Classique, reconnu par Dependabot. | Résout pour la plateforme courante seulement : il faudrait le lancer dans un conteneur Linux. |
| `pip freeze` d'un venv propre | Aucun outil. | Fige la plateforme courante, aucune trace des contraintes d'origine, régénération manuelle. |

## Conception

- `requirements.lock` à la racine, généré par
  `uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements.lock`
  (commande rappelée en tête du fichier par uv). Les outils de dev y sont aussi figés : la CI
  utilise exactement les mêmes ruff/mypy/pytest.
- Dockerfile : `pip install --no-cache-dir -c requirements.lock .`
- CI : `pip install -c requirements.lock -e ".[dev]"`, plus une étape qui vérifie que le lock
  correspond au `pyproject.toml` (`uv pip compile … --check` ou régénération + `git diff --exit-code`).
- Nouveau job CI `docker` : `docker build`, démarrage du conteneur (auth désactivée, base en
  `/tmp`), attente du `HEALTHCHECK` / requête `/healthz` (60 s max), logs affichés en cas d'échec.
  amd64 seulement (l'émulation arm64 reste au workflow de release).
- `.github/dependabot.yml` : `pip` (racine, hebdomadaire, mises à jour groupées mineures/patchs),
  `github-actions` (mensuel), `docker` (mensuel, image `python:3.12-slim`).
- Doc : README (section contribution) et AGENTS.md (§3 Démarrer, §5 Méthode, §7 Pièges).

## Laissé au constructeur

- Forme exacte de la vérification « lock à jour » selon ce que supporte la version d'uv.
- Groupement précis des PR Dependabot.
