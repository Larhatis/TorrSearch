# Plan : rendre TorrSearch prêt pour l'open-source auto-hébergé

Date : 2026-06-25
Cible : **publier sur GitHub**, n'importe qui déploie **sa propre instance** (Docker chez soi).
Tu n'héberges pas les autres → priorité aux *bons défauts*, à la doc d'install et au packaging.

Chaque phase = une PR indépendante (TDD, CI verte avant merge).

---

## Phase 0 — Correctifs rapides (à faire en premier)

**0.1 Bug : parsing des plages d'épisodes `S01E01-E12`** *(vrai bug)*
`torsearch/library/episodes.py` ne capte que les bornes d'une plage → faux trous.
- Étendre `parse_episodes` pour développer `E01-E12` → {E01..E12}.
- Tests : packs en plage, plage multi-saison, bornes inversées ignorées.

**0.2 UX : redirection selon le rôle après login**
`torsearch/web/auth_routes.py` : un invité atterrit sur `/` (Recherche, interdite).
- Après login, rediriger l'invité vers `/discover` (sinon `next`/`/`).
- Test : login invité → 303 vers `/discover`.

Effort : faible. Valeur : haute (corrige le seul bug réel + un accroc UX).

---

## Phase 1 — Qualité & CI (crédibilité open-source)

**1.1 Lint + typage en CI**
- Ajouter `ruff` + `mypy` aux deps dev (`pyproject.toml`) + config (`[tool.ruff]`, `[tool.mypy]`).
- Étape CI `ruff check` + `mypy torsearch` dans `.github/workflows/ci.yml`.
- Corriger les remontées (imports, types, etc.).
**1.2 Badges** CI + licence + Python version dans le README.
**1.3 (option)** `pre-commit` (ruff format/lint) pour les contributeurs.

Effort : moyen (surtout corriger ce que mypy trouve). Valeur : haute (filet + sérieux du repo).

---

## Phase 2 — Bons défauts de sécurité (pour les self-hosters)

**2.1 Anti-brute-force au login**
`torsearch/web/auth.py` : plafond de tentatives + délai progressif par IP/identifiant (en mémoire, fenêtre glissante). Test : N échecs → 429/attente.
**2.2 Docker non-root**
`Dockerfile` : créer un user dédié + `USER`, droits sur `/data`.
**2.3 Refus des secrets triviaux**
Au démarrage avec auth activée : avertir (log) si le mot de passe admin est faible/par défaut ; documenter le changement. (Le secret de session est déjà géré.)
**2.4 Doc reverse-proxy / HTTPS**
README : TLS = responsabilité d'un reverse proxy (Caddy/Traefik/NPM) + exemple ; rappeler `TORSEARCH_HTTPS=1` derrière proxy.
**2.5 (option)** En-têtes de sécurité de base (`X-Content-Type-Options`, etc.).

Effort : moyen. Valeur : haute si exposé hors LAN.

---

## Phase 3 — Packaging & distribution

**3.1 LICENSE** *(décision requise — voir plus bas)*. Ajouter le fichier + en-tête repo.
**3.2 Image Docker publiée (GHCR)**
Workflow `.github/workflows/release.yml` : build multi-arch + push `ghcr.io/<user>/torrsearch` sur tag `v*`.
**3.3 Déploiement clé en main**
- `docker-compose.yml` orienté utilisateur final (image publiée, pas `build:`).
- `.env.example` exhaustif (toutes les `TORSEARCH_*` + `TMDB_API_KEY`).
**3.4 Versioning** sémantique + **Releases GitHub** (tags `vX.Y.Z`, changelog).
**3.5 README quickstart** : 3 commandes pour lancer, captures d'écran, matrice des rôles, liste des fonctions.

Effort : moyen. Valeur : haute (première expérience = adoption).

---

## Phase 4 — Hygiène projet open-source

- **SECURITY.md** (comment signaler une faille).
- **CONTRIBUTING.md** (setup dev, `uv`, lancer les tests).
- Templates d'**issues** / **PR** (`.github/`).
- (option) `CODE_OF_CONDUCT.md`.
- Doc complète des variables d'environnement.

Effort : faible. Valeur : moyenne (accueil des contributeurs).

---

## Phase 5 — Robustesse & raffinements (plus tard, non bloquant)

- **SQLite** : migrer les 6 stores JSON (settings, monitor, library, series, users,
  requests) → règle les courses « lost-update » entre la boucle moniteur et le web,
  débloque requêtes/quotas/historique par user. Gros chantier ; pas nécessaire pour un
  usage perso/familial mais utile si une instance grossit.
- Raffinements *arr* : choisir le **plus petit torrent** couvrant un manquant (éviter un
  pack pour 1 épisode) ; **upgrades de qualité** (remplacer 720p par 1080p).
- Notification **individuelle au demandeur** (nécessite un contact par compte → étend le
  modèle `User`).

---

## Décisions à prendre (toi)

1. **Licence** : MIT (permissive, recommandée pour un outil self-hosted) / Apache-2.0
   (permissive + clause brevets) / GPL-3.0 (copyleft). → défaut suggéré : **MIT**.
2. **Nom d'image / org GHCR** pour la publication Docker.
3. Périmètre du premier lot : je recommande **Phase 0 + Phase 1** d'abord (corrige le
   bug + pose le filet qualité), puis Phase 2 et 3.

## Ordre recommandé
Phase 0 → 1 → 2 → 3 → 4, et Phase 5 à la demande. Chaque phase est une PR séparée et
mergée indépendamment.
