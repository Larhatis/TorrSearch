# Conception : Chantier 10 — purge sûre des torrents bloqués

Date : 2026-11-01

## 1. Pourquoi

La purge automatique des torrents « bloqués » (`handle_stalled_torrents`, chantier 3) supprime
un torrent **avec ses données**, le met en liste noire et relance la surveillance. Elle a été
écrite pour les releases mortes que la surveillance a elle-même choisies. En pratique :

- elle tourne à chaque cycle **même surveillance désactivée** ;
- elle examine **tous** les torrents de Transmission, y compris ceux ajoutés à la main
  (dans Transmission ou par la recherche manuelle de TorrSearch) ;
- elle tient pour une erreur **n'importe quel** message de Transmission, simple avertissement
  du tracker compris (« Could not connect to tracker », VPN coupé…).

Constaté en production (journal et liste noire de l'instance de l'utilisateur) :

- quatre saisons d'une série ajoutées à la main, purgées **dans la même seconde** (deux pour
  « erreur », deux à 0 % sans pair) ; les autres saisons du même lot se sont terminées ;
- un documentaire rare ajouté à la main, purgé deux heures après son ajout (0 %, aucun pair) ;
- aucune de ces releases ne figurait dans l'historique de surveillance : elles n'avaient pas
  été choisies par la surveillance ;
- le port entrant de Transmission est fermé (`Port is open: No`) : un torrent peu partagé peut
  rester à 0 % bien plus de deux heures sans être mort. C'est un réglage du VPN, hors de
  l'app, mais cela confirme que « 0 % depuis 2 h » est un signal faible.

Au passage, deux défauts liés :

- l'infohash d'un envoi n'est connu que si le tracker le fournit (`TransmissionClient.add`
  renvoie seulement l'id) ; le reste du suivi compare des noms ;
- `parse_episodes` lit `S01E1089` comme `S01E10` (épisodes à 3-4 chiffres des séries longues) :
  la surveillance croit avoir l'épisode 10, ou prend l'épisode 1089 pour le 10.

## 2. Objectifs, non-objectifs, anti-objectifs

| # | Lot | Résultat attendu |
|---|-----|------------------|
| 1 | Registre des envois | L'app sait, par infohash, quels torrents elle a envoyés et d'où (surveillance ou manuel). |
| 2 | Purge restreinte | Seuls les torrents envoyés **par la surveillance**, surveillance active, peuvent être purgés. |
| 3 | Erreurs fiables | Seule une erreur disant que le tracker ne connaît pas (plus) le torrent justifie une purge ; jamais un avertissement, jamais une erreur locale. |
| 4 | Disjoncteur | Plus de 3 purges candidates dans un même cycle → aucune purge, avertissement au journal et notification. |
| 5 | Liste noire visible | Réglages → Maintenance liste les releases en liste noire, chacune avec un bouton « Retirer ». |
| 6 | Épisodes ≥ 100 | `S01E1089` est lu comme l'épisode 1089 (clé `S01E1089`), plus comme le 10. |

**Non-objectifs** : pas de changement de la page Ménage, ni du délai `stalled_hours` (2 h par
défaut, réglable), ni du test de port de Transmission. Pas d'étiquettes Transmission (`labels`,
Transmission 4 seulement) : le registre en base marche avec toutes les versions. Pas de
découpage complet de `runner.py` : seule la purge en sort (voir 3.6).

**Anti-objectifs** (un échec même si « ça marche ») : supprimer un torrent que la surveillance
n'a pas envoyé ; purger quand l'information manque (âge inconnu, listing en échec, registre
absent, panne générale).

## 3. Conception technique

### 3.1 Infohash à l'envoi (`transmission/client.py`)
- `add()` renvoie `AddedTorrent(id: int, info_hash: str)` : `add_torrent` de transmission-rpc
  renvoie un `Torrent` partiel (`id`, `name`, `hashString`), lu avec `_field(t, "hash_string")`
  (même repli `hashString` que `_to_info`). Un doublon (`torrent-duplicate`) renvoie le torrent
  existant : même structure.
- `/download` affiche `#{added.id}` comme avant.
- **Ne pas** recopier ce hash dans `MonitorRecord.infohash` : l'anti-doublon de l'historique
  compare `infohash or download_url` au même calcul sur les résultats du tracker ; un hash que le
  tracker ne fournit pas casserait cette comparaison. Le hash Transmission va dans le registre.

### 3.2 Registre des envois (`monitor/grabs.py`, collection `grabs`)
- Document par infohash (minuscules) : `{info_hash, title, origin, target, added_at}` avec
  `origin` = `"auto"` | `"manual"` et `target` = `movie:<id>`, `tv:<id>`, `saved:<nom>` ou `""`.
- `GrabRegistry.record(...)`, `get(hash)`, `is_auto(hash)`, `forget(hash)`. Hash vide → rien
  n'est écrit (pas d'entrée invérifiable).
- Écrit par : cycle des recherches libres, cycle films (PROPER/REPACK et upgrades compris),
  cycle séries (remplacements compris) avec `origin="auto"` ; `/download` avec `origin="manual"`
  (sert au diagnostic, jamais à la purge).
- Amorçage : si la collection est vide au démarrage, chaque entrée « grabbed » de l'historique
  ayant un infohash et une source autre que « manuel » est enregistrée en `auto`. Les envois plus
  anciens (historique vidé ou tronqué) ne sont pas connus : ils ne seront jamais purgés
  automatiquement — c'est le comportement sûr.
- Pas de nettoyage des vieilles entrées : une ligne par envoi, volume négligeable.

### 3.3 Règles de purge (`monitor/stalled.py`)
Un torrent est **candidat** si toutes ces conditions sont vraies :
1. surveillance active (`config.monitor.enabled`) — sinon la fonction ne fait rien ;
2. un registre est fourni et le torrent y figure en `auto` (comparaison par infohash) ;
3. pas en pause (statut contenant « stop »), progression < 100 % ;
4. âge connu et ≥ `stalled_hours` (règle actuelle) ;
5. et **soit** mort (0 %, aucun pair qui envoie, débit nul — règle actuelle), **soit** erreur
   « torrent inconnu du tracker » : `error_code != 3` et message contenant (sans casse) l'un de
   `unregistered`, `not registered`, `torrent not found`, `unknown torrent`, `does not exist`,
   `not exist`, `n'existe pas`, `introuvable`, `info_hash not found`, `infohash not found`.

Les autres messages (avertissements, tracker injoignable, erreurs locales comme disque plein)
ne déclenchent rien : ils restent visibles dans Activité et Ménage.

**Disjoncteur** : plus de 3 candidats dans le cycle → aucun n'est purgé ; journal
(`WARNING`) et notification « Purge suspendue : N torrents semblent bloqués en même temps
(panne réseau ou VPN ?) ». Au plus une notification par jour pour ne pas spammer les cycles
suivants (mémoire du processus, pas en base).

Pour chaque candidat purgé : étapes actuelles inchangées (liste noire, retrait avec données,
démarquage film/série, retrait de l'historique, notification) + `registry.forget(hash)`.

### 3.4 Liste noire dans Réglages → Maintenance
- Section « Liste noire » : titre, motif en français (`torrent_error` → « Erreur tracker »,
  `torrent_stalled` → « Bloque », `failed_download` → « Echec de telechargement », autre → tel
  quel), date ; bouton « Retirer » par ligne.
- `POST /settings/blacklist/remove` (admin), identifiant dans le **corps** du formulaire
  (infohash, sinon titre — un titre peut contenir `/`), réponse HTMX qui remplace la section.
- `Blacklist.list()` et `Blacklist.remove()` existent déjà. Sans JS inline, sans accents dans
  le template.

### 3.5 Épisodes ≥ 100 (`library/episodes.py`)
- Numéro d'épisode après `E` : 1 à 4 chiffres. La borne d'une plage **sans** `E`
  (`E01-05`) reste à 1-2 chiffres, suivie de `(?!\d)` : `S01E05-1080p` ne doit jamais devenir
  une plage.
- Les clés gardent le format `S{:02d}E{:02d}` (donc `S01E1089`), déjà produit tel quel par les
  clients TMDB et Jellyfin. Les tris de clés restent lexicographiques (affichage seulement).

### 3.6 Découpage minimal du moteur
- `handle_stalled_torrents` et `_same_release` passent dans `torsearch/monitor/stalled.py` ;
  `runner.py` les importe. Les tests importent depuis le nouveau module.
- Le reste de `runner.py` ne bouge pas dans ce chantier (revue plus simple, risque limité).

## 4. Tests (TDD, un commit par correctif)
- Client : `add()` renvoie id + hash (faux client transmission-rpc) ; repli `hashString`.
- Registre : enregistrement, `is_auto`, `forget`, hash vide ignoré, amorçage depuis l'historique
  (manuel exclu, sans hash exclu, collection non vide → pas d'amorçage).
- Purge : surveillance désactivée → rien ; torrent absent du registre → rien ; torrent
  `manual` → rien ; registre absent → rien ; avertissement tracker → rien ; erreur locale → rien ;
  « Unregistered torrent » → purgé ; 0 % sans pair → purgé ; en pause → rien ; 4 candidats →
  rien + une notification ; tests existants adaptés (registre fourni).
- Cycles : un grab film / série / recherche libre enregistre `auto` avec le hash Transmission ;
  `/download` enregistre `manual`.
- Liste noire : la section s'affiche (admin), « Retirer » supprime l'entrée, membre → 403,
  requête cross-site → 403.
- Parseur : `S01E1089`, `S21E1100`, plage `S01E01-E03` inchangée, `S01E05-1080p` → `S01E05`.

## 5. Livraison
- Version **0.9.0** (`pyproject.toml`, `torsearch/__init__.py`), AGENTS.md (§2 état, §8).
- PR unique, squash ; release laissée à l'utilisateur.

## 6. Décisions prises sans l'utilisateur (à relire)
- Les téléchargements lancés à la main depuis TorrSearch ne sont **jamais** purgés
  automatiquement, même liés à une œuvre surveillée : l'utilisateur a choisi cette release.
- Seuil du disjoncteur : 3 purges par cycle.
- Les erreurs locales (disque plein, droits) ne purgent plus : relancer une autre release
  échouerait de la même façon, et la liste noire punirait une release saine.
- Envois antérieurs au registre sans trace dans l'historique : jamais purgés automatiquement.
