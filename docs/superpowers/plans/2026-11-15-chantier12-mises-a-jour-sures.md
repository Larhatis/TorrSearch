# Chantier 12 — mises à jour sûres : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** figer toutes les dépendances, tester l'image Docker sur chaque PR, faire proposer les montées de version par Dependabot.

**Architecture:** un `requirements.lock` universel (uv) sert de fichier de contraintes (`pip install -c`) à la CI et au Dockerfile ; un job CI `docker` construit et démarre l'image ; `.github/dependabot.yml` couvre pip, actions et Docker.

**Tech Stack:** uv (régénération seulement), pip, GitHub Actions, Docker, Dependabot.

**Spec:** `docs/superpowers/specs/2026-11-15-chantier12-mises-a-jour-sures-design.md`

## Global Constraints

- Python 3.12 (`requires-python = ">=3.12"`, image `python:3.12-slim`).
- Plateformes de l'image : linux/amd64 et linux/arm64 — le lock doit être universel (`--universal`).
- `pip install -e ".[dev]"` sans lock doit continuer à marcher (contributeur sans uv).
- Commits `type(portée): description` en français ; docstrings/commentaires en anglais.
- Dépôt public : aucun nom de tracker, chemin ou IP personnelle.

## Review Focus

- Lock résolu pour macOS seulement → l'image arm64/amd64 n'installe pas : vérifier `--universal` et le build Docker du job CI.
- `pyproject.toml` modifié sans régénérer le lock → la CI doit échouer (étape « lock à jour »).
- Image qui se construit mais ne démarre pas (import cassé, dépendance manquante à l'exécution) → le job `docker` doit échouer et afficher les logs.
- `HEALTHCHECK` lent au premier démarrage → attendre jusqu'à 60 s avant de conclure.
- Dependabot qui ouvre une PR par paquet transitif → grouper mineures/patchs.

---

### Task 1 : fichier de versions exactes, utilisé par la CI et le Dockerfile

**Files:**
- Create: `requirements.lock`
- Modify: `Dockerfile` (ligne `pip install`), `.github/workflows/ci.yml` (étape Install + nouvelle étape « Lock a jour »), `.dockerignore` si besoin

**Interfaces:**
- Produces : `requirements.lock` à la racine ; commande de régénération
  `uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements.lock`

- [ ] **Step 1 :** générer le lock avec la commande ci-dessus ; vérifier qu'il contient `fastapi==`, `transmission-rpc==`, `mcp==`, `pytest==`, `ruff==`, `mypy==` et des marqueurs `sys_platform` (preuve du mode universel).
- [ ] **Step 2 :** CI — `pip install -c requirements.lock -e ".[dev]"` ; étape « Lock a jour » : installer uv (`astral-sh/setup-uv`), régénérer le lock dans un fichier temporaire avec la même commande et `diff` contre `requirements.lock` en ignorant la ligne d'en-tête de commande (échec = message « requirements.lock n'est plus a jour : relancer … »).
- [ ] **Step 3 :** Dockerfile — `COPY pyproject.toml requirements.lock ./` puis `pip install --no-cache-dir -c requirements.lock .`
- [ ] **Step 4 :** vérifier localement : venv neuf + `pip install -c requirements.lock -e ".[dev]"`, puis ruff, mypy, pytest verts ; `docker build` réussit.
- [ ] **Step 5 :** commit `build(deps): versions exactes dans requirements.lock (CI et image)`.

### Task 2 : la CI construit et démarre l'image

**Files:**
- Modify: `.github/workflows/ci.yml` (nouveau job `docker`)

- [ ] **Step 1 :** job `docker` (ubuntu-latest) : `docker build -t torsearch:ci .` ; `docker run -d --name ts -e TORSEARCH_DB=/data/torsearch.db -p 8000:8000 torsearch:ci` ; boucle jusqu'à 60 s sur `curl -fsS http://127.0.0.1:8000/healthz` ; en cas d'échec `docker logs ts` puis `exit 1`.
- [ ] **Step 2 :** vérifier la même séquence en local (Docker Desktop) : succès ; puis la casser volontairement (CMD invalide, sans commit) et constater l'échec avec logs.
- [ ] **Step 3 :** commit `ci(docker): construire et demarrer l'image sur chaque PR`.

### Task 3 : Dependabot et documentation

**Files:**
- Create: `.github/dependabot.yml`
- Modify: `README.md` (contribution), `AGENTS.md` (§2 état, §3 Démarrer, §5 Méthode, §7 Pièges), `pyproject.toml` + `torsearch/__init__.py` (version 0.10.2)

- [ ] **Step 1 :** `dependabot.yml` version 2 : `pip` (`/`, weekly, groupe `python` pour `minor`+`patch`), `github-actions` (`/`, monthly), `docker` (`/`, monthly). Messages de commit préfixés `build(deps)`.
- [ ] **Step 2 :** documenter : installation avec le lock, commande de régénération, « une PR Dependabot = lire le changelog des paquets sensibles (transmission-rpc, mcp, fastapi) avant fusion ».
- [ ] **Step 3 :** valider le YAML (`python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"` et idem pour `ci.yml`).
- [ ] **Step 4 :** commit `build(deps): Dependabot pour pip, actions et Docker (v0.10.2)`.

### Fin de chantier

- [ ] Revue de code indépendante de la branche, PR (squash, `(#N)`), CI verte (les deux jobs), release `v0.10.2`, déploiement NAS si demandé.
