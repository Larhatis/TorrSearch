# Chantier 13 — espace disque : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** refuser un envoi automatique qui viderait le disque, afficher l'espace libre, prévenir.

**Architecture:** la façade Transmission expose `free_space` (RPC `free-space`, remontée aux parents) ; `monitor/diskspace.py` décide (`has_room`, `low_folders`, `folder_usage`) ; les trois points d'envoi automatiques, le runner, le panneau d'état et `send_release` l'utilisent.

**Tech Stack:** Python 3.12, FastAPI/Jinja2, transmission-rpc 7, pytest (+ faux clients async).

**Spec:** `docs/superpowers/specs/2026-11-15-chantier13-espace-disque-design.md`

## Global Constraints

- Seuil `LibraryConfig.min_free_gb`, défaut **50**, `0` = désactivé, borné 0–100000.
- Espace inconnu ⇒ envoi autorisé ; jamais d'exception depuis `free_space`.
- Pas de ligne d'historique pour un refus.
- Notification au plus une fois par jour (`DailyNotice`).
- Templates sans accents ; docstrings en anglais ; aucun JS inline.
- Appels Transmission uniquement via la façade (pool de threads).

## Review Focus

- Dossier de destination pas encore créé (`…/Serie/Saison 01`) → mesurer le parent existant.
- `paths.by_category` vide (dossier par défaut Transmission, `download_dir=None`) → mesurer le dossier de session.
- Faux Transmission des tests sans `free_space` → tout continue comme avant.
- Release de taille 0 (tracker sans taille) → jugée sur l'espace libre seul.
- Deux catégories sur le même chemin (`tv` et `anime` → `/downloads/disk2`) → une seule ligne / une seule mesure.

---

### Task 1 : `TransmissionClient.free_space`

**Files:** Modify `torsearch/transmission/client.py` · Test `tests/test_transmission_client.py` (ou fichier existant des tests de la façade)

**Interfaces:** Produces `async def free_space(self, path: str | None) -> int | None`

- [ ] Tests (faux `client_factory`) : `test_free_space_existing_path` (renvoie les octets) ; `test_free_space_walks_up_to_existing_parent` (`/d/disk2/Serie/Saison 01` → erreur, `/d/disk2/Serie` → erreur, `/d/disk2` → 638e9) ; `test_free_space_none_uses_session_dir` ; `test_free_space_relative_or_error_returns_none` (jamais d'exception).
- [ ] Les voir échouer, implémenter (parents via `PurePosixPath`, arrêt avant `/`), les voir passer, commit `feat(transmission): espace libre d'un dossier (free-space)`.

### Task 2 : `monitor/diskspace.py` + réglage `min_free_gb`

**Files:** Create `torsearch/monitor/diskspace.py` · Modify `torsearch/config.py` · Test `tests/test_diskspace.py`

**Interfaces:**
- `LibraryConfig.min_free_gb: float = 50.0` (ge=0, le=100000) + propriété `min_free_bytes -> int` (`int(gb*1e9)`).
- `async def has_room(transmission, download_dir: str | None, size: int, min_free: int) -> bool`
- `async def folder_usage(transmission, config) -> list[tuple[str, str, int | None]]` (libellé `Films`/`Series`/`Anime`/`Par defaut`, chemin, octets libres) — chemins distincts.
- `async def low_folders(transmission, config) -> list[tuple[str, str, int]]`
- `def format_bytes(n: int) -> str` (« 638 Go », « 1,9 To »).

- [ ] Tests : `has_room` vrai si assez, faux si `free - size < min_free`, vrai si `min_free == 0`, vrai si espace inconnu, vrai sans méthode `free_space` ; `folder_usage` dédoublonne `tv`/`anime` et ajoute « Par defaut » quand aucune catégorie ; `low_folders` ne garde que les dossiers sous le seuil ; `format_bytes`.
- [ ] Rouge → code → vert → commit `feat(monitor): garde-fou d'espace disque (min_free_gb, 50 Go par defaut)`.

### Task 3 : garde-fou dans les envois automatiques

**Files:** Modify `torsearch/monitor/runner.py` (`_grab_movie`, `_grab_series_release`, envoi auto de `run_cycle`) · Test `tests/test_monitor_runner.py` (ou `tests/test_diskspace_runner.py`)

- [ ] Tests avec un faux Transmission async à `free_space` réglable : film non envoyé quand le disque est plein (`add` jamais appelé, pas d'entrée d'historique, film toujours « en attente ») ; épisode idem ; recherche libre auto idem ; envoi normal quand il y a la place.
- [ ] Rouge → code (appel `has_room(transmission, download_dir, pick.size, config.library.min_free_bytes)` juste avant `add`, `logger.warning("Espace disque insuffisant pour %s (%s) : envoi reporte", …)`) → vert → commit `feat(monitor): pas d'envoi automatique sur un disque presque plein`.

### Task 4 : notification quotidienne, panneau d'état, envoi manuel, réglage UI

**Files:** Modify `torsearch/monitor/runner.py` (`MonitorRunner`), `torsearch/health.py`, `torsearch/library/sending.py`, `torsearch/web/settings_routes.py`, `torsearch/web/templates/settings.html`, README, AGENTS.md, version 0.11.0 · Tests correspondants

- [ ] Tests : `run_once` notifie « Disque presque plein » une fois même sur deux cycles le même jour ; `check_all` contient « Disques » en `ok` avec les tailles et en `error` sous le seuil, absent si Transmission ne répond pas ; `send_release` ajoute « attention : il reste » sous le seuil et rien au-dessus ; le formulaire du profil enregistre `min_free_gb` (virgule acceptée, vide = inchangé).
- [ ] Rouge → code → vert → commit `feat(settings): seuil d'espace disque, ligne Disques et alerte quotidienne (v0.11.0)`.

### Fin de chantier

- [ ] Revue indépendante de la branche, PR squash, CI verte, release v0.11.0, déploiement NAS si demandé.
