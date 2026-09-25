# Trackers : redirections sûres et libellé « Clé API Torznab »

Date : 2026-09-25

## Constat (cas réel : TR4KER)

- `https://tr4ker.net/api` répond **301 → `https://tr4ker.net/api/`** (simple `/` final) :
  TorrSearch ne suit pas les redirections → « Erreur HTTP 301 », recherches vides.
  Prowlarr, lui, suit la redirection.
- Le champ du formulaire s'appelle « Passkey », alors que Torznab attend la **clé API**
  (souvent différente de la passkey — la doc de TR4KER le précise) : l'utilisateur y avait
  mis sa passkey.

## Conception

### Redirections (recherche et bouton Tester)

`TorznabIndexer` suit lui-même jusqu'à 5 redirections (`follow_redirects` reste désactivé
côté httpx) avec une règle stricte :

- suivie seulement vers **le même hôte** (ex. `/api` → `/api/`) ; `http` → `https` sur le
  même hôte est accepté ;
- **refusée** vers un autre hôte (la clé partirait ailleurs) ou de `https` vers `http`
  (la clé partirait en clair) ;
- à chaque saut, la requête est renvoyée vers la nouvelle adresse **avec nos propres
  paramètres** (`t`, `q`, `cat`, `apikey`) : la query de l'en-tête `Location` est ignorée.

Messages du bouton Tester / panneau d'état : « Redirection vers un autre site refusée
(hôte) : mets à jour l'URL du tracker. », « Redirection vers http refusée (non chiffré). »,
« Trop de redirections. » — jamais d'URL complète (pas de clé). En recherche, une
redirection refusée est traitée comme une erreur du tracker (journalisée, aucun résultat).

### Libellé

Le champ devient **« Cle API Torznab »** (templates sans accents), avec une aide : clé API
du tracker (souvent différente de la passkey) et URL complète de l'API
(ex. `https://tracker.example/api/`). Messages « Ressaisis la passkey… » → « Ressaisis la
clé API… » ; README aligné.

## Tests (TDD)

Redirection même hôte suivie (paramètres renvoyés), `http` → `https`, refus autre hôte (la
cible n'est jamais appelée), refus `https` → `http`, boucle → « Trop de redirections »,
recherche qui suit une redirection ; libellé présent dans Réglages.

## Hors périmètre

Suivre les redirections vers un sous-domaine ou un autre domaine ; mémoriser
automatiquement la nouvelle URL.
