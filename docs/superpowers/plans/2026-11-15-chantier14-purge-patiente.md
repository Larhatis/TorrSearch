# Chantier 14 — purge patiente : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ne plus brûler de bonnes releases : patience quand le tracker annonce des sources, œuvre remise en recherche après une purge, état du port visible.

**Architecture:** `TorrentInfo.tracker_seeders` (façade Transmission) → `_purge_reason` ; registre des envois → démarquage ; `port_open()` → panneau d'état.

**Tech Stack:** Python 3.12, transmission-rpc 7, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-chantier14-purge-patiente-design.md`

## Global Constraints

- Patience bornée : `max(stalled_hours, 24 h)` quand des sources sont annoncées.
- Sources inconnues (`None`) ⇒ comportement actuel.
- Règles §6.9 inchangées (registre `auto`, statut `downloading`, âge, disjoncteur, 3 max).
- Appels Transmission via la façade ; jamais d'exception du test de port.

## Review Focus

- Tracker `seeder_count == -1` sur tous les trackers ⇒ `None` (pas 0, pas de patience).
- Plusieurs trackers, un à -1 et un à 12 ⇒ 12.
- Entrée du registre sans cible (amorcée depuis l'historique) ⇒ repli sur les titres.
- Cible `tv:<id>` d'une série supprimée entre-temps ⇒ rien, sans erreur.
- Faux Transmission sans `port_open` ⇒ pas de ligne « Port entrant ».

---

### Task 1 : `tracker_seeders` et patience

**Files:** `torsearch/transmission/client.py`, `torsearch/monitor/stalled.py` · Tests `tests/test_transmission.py`, `tests/test_stalled*.py`

- [ ] Tests : `_to_info` lit le max des `seeder_count >= 0` (`[54, -1]` ⇒ 54 ; `[-1]` ⇒ None ; champ absent ⇒ None) ; purge : 0 %, 3 h, `tracker_seeders=12` ⇒ pas de purge ; 25 h ⇒ purge ; `tracker_seeders=0` ou `None` à 3 h ⇒ purge (comme avant).
- [ ] Rouge → code → vert → commit `fix(purge): patience quand le tracker annonce des sources`.

### Task 2 : démarquage par la cible du registre

**Files:** `torsearch/monitor/stalled.py` · Test `tests/test_stalled*.py`

- [ ] Tests : film `grabbed` avec `grabbed_title` ≠ nom du torrent, registre `movie:1` ⇒ remis voulu après purge ; série `tv:1` ⇒ épisodes du torrent démarqués ; registre sans cible ⇒ repli titres (test existant).
- [ ] Rouge → code → vert → commit `fix(purge): remettre l'oeuvre en recherche via le registre des envois`.

### Task 3 : ligne « Port entrant »

**Files:** `torsearch/transmission/client.py` (`port_open`), `torsearch/health.py`, README, AGENTS.md, version 0.12.0 · Tests `tests/test_transmission.py`, `tests/test_health.py`

- [ ] Tests : `port_open` ⇒ True/False/None (erreur) ; `check_all` : « Port entrant » ok si ouvert, error si fermé avec explication, absente si Transmission ne répond pas ou sans méthode.
- [ ] Rouge → code → vert → commit `feat(health): ligne Port entrant (v0.12.0)`.

### Fin de chantier

- [ ] Revue indépendante, PR squash, CI verte, release, déploiement si demandé.
