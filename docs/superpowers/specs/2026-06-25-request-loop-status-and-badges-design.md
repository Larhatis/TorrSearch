# Finition de la file de demandes : statut & badges

Date : 2026-06-25

## Contexte

Le Lot 2 a introduit les demandes mais la boucle n'est pas fermée :
- l'invité ne voit jamais ce que devient sa demande ;
- rien n'empêche/signale une re-demande d'un titre déjà demandé ou déjà en bibliothèque.

## #1 — L'invité suit ses demandes + l'admin est prévenu

### Page « Mes demandes »
- `RequestStore.for_user(username) -> list[MediaRequest]` (récentes d'abord).
- `GET /requests/mine` — accessible à **tout utilisateur connecté** ; affiche **ses**
  demandes avec un badge de statut (en attente / approuvée / refusée).
- Item de nav **« Mes demandes »** pour les connectés **non-admin** (l'admin a déjà la
  file complète « Demandes »).

### Ping admin sur nouvelle demande
- `Notifier.notify_message(channels, title, body)` (généralise `_send_one`, best-effort).
- À la création d'une demande, on notifie les **canaux globaux** :
  « Nouvelle demande : <titre> (<user>) ». Résilient (aucune erreur ne casse la requête).

### Hors périmètre (assumé)
- Pas de **notification individuelle au demandeur** : les comptes n'ont pas de contact
  (juste identifiant/mot de passe/rôle). Le demandeur suit le statut **dans l'app**.

## #2 — Badges d'état sur Découvrir

Les routes `discover/trending` et `discover/search` passent, en plus de `owned` :
- `in_library` = `{ "movie:<id>" } ∪ { "tv:<id>" }` présents en bibliothèque/séries.
- `requested` = `{ "<type>:<id>" }` ayant une demande **en attente**.

`media_results.html`, par carte, état prioritaire :
1. **owned** (déjà dans Jellyfin) → comportement actuel (badge + Lire).
2. **in_library** → badge « Dans la bibliothèque », bouton d'ajout/demande masqué.
3. **requested** → badge « Demandé », bouton de demande masqué.
4. sinon → boutons d'action actuels (Demander pour l'invité ; Torrents + Ajouter pour
   membre/admin). Les membres gardent « Torrents » dans tous les cas.

## Dégradation gracieuse
- Stores absents (tests sans library/requests) → ensembles vides → aucun badge, boutons
  normaux. Auth désactivée → inchangé.

## Tests (TDD)
- `RequestStore.for_user` ne renvoie que les demandes de l'utilisateur, récentes d'abord.
- `Notifier.notify_message` poste sur les canaux actifs.
- Web : `/requests/mine` montre les demandes de l'utilisateur (pas celles des autres) ;
  Découvrir affiche « Dans la bibliothèque » / « Demandé » et masque le bouton ;
  nav « Mes demandes » visible pour non-admin, pas pour admin.
