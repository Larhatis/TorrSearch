# Multi-utilisateur : rôles & file de demandes

Date : 2026-06-25

## Contexte

L'auth actuelle est mono-utilisateur : un seul `TORSEARCH_USERNAME`/`PASSWORD` en
variable d'env, comparé en clair, session cookie, `AuthMiddleware` qui garde tout sauf
`/login` et `/logout`. Aucun rôle.

Objectif : passer à **plusieurs comptes avec rôles**, et un **flux de demandes**
(façon Jellyseerr) où certains utilisateurs ne peuvent que *demander*, l'admin
validant.

## Rôles

Trois rôles, ordonnés `admin > member > guest` :

| Rôle | Réglages / gestion comptes | Valider les demandes | Recherche manuelle + ajout direct | Découvrir + demander |
|------|:---:|:---:|:---:|:---:|
| **admin** | ✅ | ✅ | ✅ | ✅ |
| **member** | ❌ | ❌ | ✅ | ✅ |
| **guest** | ❌ | ❌ | ❌ | ✅ |

- **member** = tout sauf l'administration (réglages, comptes, validation des demandes
  des autres). Il a la recherche manuelle (`/search` → `/download`) et l'ajout direct.
- **guest** = Découvrir (parcourir) + **Demander** uniquement ; pas de recherche
  manuelle, pas d'ajout direct, pas de réglages.

## Décisions cadrées
- File d'attente **avec validation admin** (pas juste une notification).
- Comptes **créés par l'admin** (pas d'inscription libre).
- Le **member peut chercher/ajouter manuellement** des torrents.

## Architecture

### Stockage des comptes — `data/users.json`
Chaque entrée : `{username, password_hash, role}`. Hash via **stdlib** (aucune
dépendance ajoutée) : `hashlib.pbkdf2_hmac('sha256', pw, salt, iterations)`, stocké
`pbkdf2_sha256$iterations$salt_hex$hash_hex`, vérifié avec `hmac.compare_digest`.
Écriture atomique (`os.replace`) comme les autres stores.

### Amorçage de l'admin
Au démarrage, si `users.json` est vide et que `TORSEARCH_USERNAME`/`PASSWORD` sont
fournis, on crée un compte **admin** avec ces identifiants (porte d'entrée garantie,
rétro-compatible avec l'install mono-user).

### Auth
- `UserStore` (load/save/verify/add/remove/set_role/set_password).
- Login : vérif hashée ; la session porte `user` + `role`.
- `AuthSettings.enabled` devient « auth activée si au moins un compte existe » (ou si
  bootstrap env présent).

### Autorisation
Helper `role_at_least(session_role, needed)`. Application par **dépendances FastAPI**
explicites sur les routes (plus testable qu'un mapping de préfixes en middleware) :
- **admin only** : `/settings*`, `/users*`, validation des demandes, `/surveillance`
  (gestion de la surveillance).
- **member+** : `/search`, `/download`, ajout direct `/library/add`, `/series/add`.
- **connecté (tous rôles)** : `/`, `/discover`, vues lecture biblio, ses propres demandes.
Le rôle est passé aux templates pour que la **nav masque** ce qui est hors droits.

### Demandes — `data/requests.json`
Entrée : `{id, username, media_type, tmdb_id, title, year, poster_path,
status: "pending"|"approved"|"rejected", requested_at, decided_at, decided_by}`.
- **guest** clique **Demander** → entrée `pending`.
- **member/admin** clique **Ajouter** → demande créée `approved` immédiatement
  (auto-approbation) → ajout biblio/série dans la foulée.
- **admin** : écran **Demandes** → approuver (→ ajoute à la biblio/série, la
  surveillance récupère ensuite) / refuser.

### UI
- **Réglages → carte Utilisateurs** (admin) : liste, ajout (identifiant + mot de passe
  + rôle), changement de rôle / mot de passe, suppression. On ne peut pas se
  rétrograder/supprimer le dernier admin.
- **Nav → item Demandes** (admin) avec compteur d'« en attente ».
- **Découvrir** : non-admins voient **Demander** au lieu de *Bibliothèque/Suivre* ;
  member voit *Ajouter* (auto-approuvé).
- Nav adaptée au rôle (masquage Réglages/Demandes/Recherche selon les droits).

## Livraison en 2 lots

**Lot 1 — Fondation auth multi-user + rôles + comptes**
UserStore + hashage, bootstrap admin, login hashé, autorisation par rôle (dépendances),
carte Utilisateurs dans Réglages, nav adaptée. Les capacités existantes sont gardées par
rôle (guest ne voit ni Recherche ni Réglages). *Pas encore de file de demandes* : à ce
stade, guest peut juste parcourir Découvrir (boutons d'ajout masqués).

**Lot 2 — File de demandes + validation**
RequestStore, boutons Demander/Ajouter sur Découvrir, écran admin Demandes
(approuver/refuser), auto-approbation member/admin, compteur de nav.

## Dégradation gracieuse / compat
- Aucun compte + pas d'env auth → auth désactivée (comportement actuel, app ouverte).
- Install mono-user existante (env username/password) → l'utilisateur devient **admin**
  au 1ᵉʳ démarrage, rien ne change pour lui.

## Tests (TDD)
- `UserStore` : hash/verify, add/remove, bootstrap admin, refus suppression dernier admin.
- Auth : login hashé OK/KO, session porte le rôle.
- Autorisation : guest bloqué sur `/settings` `/search` `/download` `/users` (403/redirect) ;
  member bloqué sur `/settings` `/users` ; admin tout OK.
- Web : carte Utilisateurs (admin) ; nav masque selon rôle.
- (Lot 2) RequestStore, auto-approbation member, approbation admin → ajout biblio.

## Hors périmètre
- Inscription libre, réinitialisation de mot de passe par e-mail, OAuth/SSO.
- Quotas de demandes par utilisateur, historique de visionnage par utilisateur.
