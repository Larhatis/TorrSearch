# Chantier 14 — purge patiente (design)

Date : 2026-11-15 · Version visée : v0.12.0

## Intention

En production, la surveillance a grillé 6 releases de *Primetime* en 6 jours (3–9 novembre) :
chacune purgée ~2 h après l'envoi (0 %, aucun pair), mise en liste noire, puis la suivante. 31
releases en liste noire pour 40 envois automatiques. Deux causes : le port entrant de
Transmission est fermé (réglé côté VPN, hors code) et la purge juge le torrent sur l'activité de
*notre* client seulement, alors que le tracker annonce souvent des sources — le problème est
alors de notre côté, pas la release.

Un second défaut a coûté ~2 jours par release : après une purge, le film n'est remis « voulu »
que si son `grabbed_title` (titre du tracker) est identique au nom du torrent dans Transmission.
Ce n'est pas le cas en général (`Primetime.2026.MULTI.VFQ.1080p.WEB.DDP.5.1.H264-SUPPLY` côté
tracker, `Primetime.2026.MULTi.CA.1080p.WEB.H264-SUPPLY` côté Transmission) : le film restait
« acquis », attendait `regrab_hours` (48 h), puis était relancé avec une seconde entrée de liste
noire (« failed_download ») pour la même release.

## Objectifs

1. **Sources annoncées ⇒ patience.** Un torrent à 0 % sans pair n'est purgé comme « bloqué »
   après `stalled_hours` que si le tracker n'annonce **aucune** source (ou ne sait pas). Si le
   tracker annonce des sources, le délai passe à **24 h** (ou `stalled_hours` s'il est plus long),
   puis la purge reprend comme avant (une release injoignable ne bloque pas l'œuvre à vie).
2. **Purge ⇒ œuvre remise en recherche tout de suite**, grâce à la cible du registre des envois
   (`movie:<id>`, `tv:<id>`) plutôt qu'à la comparaison exacte des titres (gardée en repli).
3. **Panneau d'état : ligne « Port entrant »** (RPC `port-test` de Transmission) — OK ouvert,
   erreur « fermé : les releases peu partagées démarrent mal ».

## Non-objectifs

- Ouvrir le port (réglage AirVPN + compose OMV, fait par l'utilisateur).
- Changer `stalled_hours` par défaut (la règle des sources suffit ; 2 h reste pertinent pour une
  release sans aucune source).
- Nettoyer la liste noire existante (possible à la main : Réglages → Maintenance → Liste noire).

## Anti-objectifs

- Une release vraiment morte gardée indéfiniment : la patience est bornée (24 h).
- Purger un torrent ajouté à la main : règles §6.9 inchangées (registre `auto`, disjoncteur…).
- Faire échouer la purge quand Transmission ne donne pas les statistiques tracker : inconnu ⇒
  comportement actuel.

## Approches envisagées

| Approche | Pour | Contre |
|---|---|---|
| **Sources annoncées par le tracker (`trackerStats.seederCount`) + patience bornée** (retenue) | Distingue « release morte » de « chez nous ça ne passe pas » avec une donnée que Transmission a déjà. | Le compte peut être absent (-1) : alors comportement actuel. |
| Allonger `stalled_hours` pour tous | Trivial. | Retarde aussi le remplacement des releases vraiment mortes. |
| Suspendre toute purge quand le port est fermé | Simple. | Les vraies releases mortes ne seraient plus remplacées ; dépend d'un test de port ponctuel. |

## Conception

- `TorrentInfo.tracker_seeders: int | None` : max des `seeder_count >= 0` des trackers, `None`
  si aucun (champ absent ou -1). Lu par `_field` (KeyError géré).
- `stalled._purge_reason(t, now, window)` : pour la raison « stalled », si
  `t.tracker_seeders` > 0 et âge < `max(window, 24 h)` ⇒ pas de purge (journal debug). La raison
  « error » (tracker qui a oublié le torrent) est inchangée.
- `handle_stalled_torrents` : démarquage par `grabs.get(hash).target` (`movie:<id>` ⇒
  `library.unmark_grabbed(id)` ; `tv:<id>` ⇒ épisodes du torrent démarqués sur cette série),
  avant de l'oublier du registre ; la comparaison de titres actuelle reste en repli (entrées sans
  cible).
- `TransmissionClient.port_open() -> bool | None` (jamais d'exception) ; `health.check_all` :
  ligne « Port entrant » après Transmission quand Transmission répond.

## Laissé au constructeur

- Libellés exacts du panneau.
