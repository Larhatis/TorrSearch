# Auth simple — Design

**Date :** 2026-06-20
**Statut :** validé

## Objectif

Protéger l'accès à TorrSearch derrière une authentification **identifiant + mot de passe**,
unique et mono-utilisateur. L'app peut être exposée hors d'un réseau de confiance ; un simple
gate suffit. Priorité absolue à la **simplicité** (cf. esprit du projet : alternative allégée
à Prowlarr/Jackett).

Non-objectifs : multi-comptes, rôles/permissions, inscription, reset de mot de passe,
rate-limiting, 2FA.

## Activation & configuration

- Identifiants lus depuis l'environnement : `TORSEARCH_USERNAME` et `TORSEARCH_PASSWORD`.
- **Si l'une des deux variables est absente ou vide → auth désactivée.** L'app se comporte
  exactement comme avant ce changement (pratique en local / derrière un VPN). L'auth est donc
  **opt-in**.
- Clé de signature des sessions : `TORSEARCH_SECRET_KEY` si fournie ; sinon générée
  aléatoirement et persistée dans `data/.session_secret` (les sessions survivent aux
  redémarrages sans configuration obligatoire). Le fichier est créé avec des permissions
  restreintes (0600) si possible.
- Drapeau `secure` du cookie activable via `TORSEARCH_HTTPS` (= `1`/`true`) pour les
  déploiements derrière TLS.

Ces réglages restent **hors** de `data/settings.json` (pas éditables depuis l'UI) : un secret
ne doit pas transiter par l'interface, et ça évite un problème d'œuf-et-poule au bootstrap.

## Architecture

Trois pièces, ajoutées dans la couche `web`, isolées et testables séparément :

1. **`AuthSettings`** (lecture d'environnement) — un petit objet/`dataclass` calculé une fois au
   démarrage : `enabled`, `username`, `password`, `secret_key`, `https_only`. Centralise toute
   la logique « est-ce activé ? » et la résolution de la clé. Aucune dépendance sur FastAPI.

2. **`SessionMiddleware` (Starlette)** — gère le cookie de session signé. Paramètres :
   `secret_key`, `https_only`, `same_site="lax"`, `max_age` ≈ 14 jours (`60*60*24*14`).
   Ajouté seulement si l'auth est activée.

3. **`AuthMiddleware`** (middleware ASGI maison, `BaseHTTPMiddleware`) — applique le gate :
   - Pose toujours `request.state.auth_enabled` (utilisé par les templates).
   - Si auth désactivée → passe la main directement.
   - Laisse passer les chemins publics : `GET /login`, `POST /login`, `POST /logout`.
   - Sinon, vérifie `request.session.get("user")`. Si absent :
     - requête **HTMX** (header `HX-Request: true`) → réponse `401` avec header
       `HX-Redirect: /login` (sinon la page de login s'afficherait dans un fragment) ;
     - requête normale → redirection `303` vers `/login?next=<chemin demandé>`.

## Routes

Nouveau routeur `auth_router` (`torsearch/web/auth_routes.py`), inclus dans `create_app`.

- `GET /login` → rend `login.html`. Si déjà authentifié, redirige vers `/`.
- `POST /login` (form `username`, `password`, `next`) → compare en **temps constant**
  (`hmac.compare_digest` sur username ET password). Si OK : `request.session["user"] =
  username`, redirection `303` vers `next` (validé : doit commencer par `/` et pas `//`,
  sinon `/`). Si KO : ré-affiche `login.html` avec un message d'erreur et statut `401`.
- `POST /logout` → `request.session.clear()`, redirection `303` vers `/login`.

## Templates

- `login.html` — page **autonome** (n'étend pas `base.html` pour ne pas afficher la nav à un
  visiteur non connecté). Style Tailwind cohérent avec le thème (`bg-slate-900`,
  accent `emerald-400`). Champs identifiant/mot de passe, champ caché `next`, zone d'erreur.
- `base.html` — ajout d'un bouton/lien **« Déconnexion »** dans la nav, affiché seulement quand
  `request.state.auth_enabled` est vrai (form `POST /logout`).

## Câblage

`create_app(ctx, ...)` calcule `AuthSettings` au démarrage, ajoute conditionnellement les deux
middlewares, inclut `auth_router`, et expose le drapeau aux templates via
`request.state.auth_enabled` (posé par `AuthMiddleware`, toujours, même si désactivé → `False`).

Ordre des middlewares (du plus externe au plus interne) : `SessionMiddleware` puis
`AuthMiddleware`, pour que `AuthMiddleware` puisse lire `request.session`.

## Sécurité

- Comparaison des identifiants en temps constant (`hmac.compare_digest`).
- Cookie `httponly` (par défaut dans `SessionMiddleware`), `samesite=lax`, `secure` optionnel.
- Validation de `next` (redirection ouverte interdite).
- Le mot de passe ne transite jamais par `settings.json` ni par l'UI.

## Dépendance

Ajout de `itsdangerous>=2.0` à `pyproject.toml` (requis par `SessionMiddleware`).

## Tests (`tests/test_auth.py`)

- Auth désactivée (env non défini) → accès libre à `/`, pas de redirection.
- Auth activée, pas de session → `GET /` renvoie `303` vers `/login`.
- Auth activée, requête HTMX sans session → `401` + header `HX-Redirect: /login`.
- `GET /login` accessible sans session (`200`).
- `POST /login` bons creds → `303`, cookie de session posé, `/` accessible ensuite.
- `POST /login` mauvais creds → `401`, pas d'accès.
- `POST /logout` → session vidée, `/` re-protégé.
- Validation de `next` : `next=//evil.com` ou absolu → redirige vers `/`.
- `AuthSettings` : enabled seulement si username ET password non vides ; résolution clé
  (env vs fichier généré).
