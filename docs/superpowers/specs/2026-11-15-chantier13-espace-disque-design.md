# Chantier 13 — espace disque (design)

Date : 2026-11-15 · Version visée : v0.11.0

## Intention

La surveillance envoie des releases sans regarder la place qui reste. En production, le disque
des séries est plein à 84 % (595 Go libres) : un pack de saison de 60 Go sur un disque presque
plein met Transmission en erreur, et personne ne le voit (aucun canal de notification configuré).
L'app doit refuser un envoi automatique qui viderait le disque, et prévenir.

Remplace le chantier « retrait de l'ancienne copie après upgrade/PROPER » : upgrades désactivés
en production, aucun PROPER/REPACK jamais pris, 3 groupes de doublons sur 496 torrents (tous
manuels).

## Objectifs

1. **Garde-fou avant envoi automatique** (films, séries, recherches libres en mode auto) : si
   `espace libre − taille de la release < seuil`, pas d'envoi ; un avertissement au journal
   (« Espace disque insuffisant… »). L'œuvre sera retentée à sa prochaine recherche.
2. **Panneau d'état** : ligne « Disques » avec l'espace libre de chaque dossier de
   téléchargement (Films, Séries…), en erreur si l'un est sous le seuil.
3. **Notification** « Disque presque plein » une fois par jour tant qu'un dossier est sous le
   seuil (vérifié à chaque cycle de surveillance).
4. **Téléchargement manuel** (interface, Claude) : jamais bloqué ; le message de confirmation
   ajoute « attention : il reste N Go sur ce disque » sous le seuil.

## Réglage

`LibraryConfig.min_free_gb` (profil de qualité, à côté des tailles max) : **50 Go par défaut**,
`0` = garde-fou désactivé. Même saisie que `max_movie_gb` (virgule acceptée, borné 0–100000).

## Non-objectifs

- Supprimer quoi que ce soit pour faire de la place.
- Bloquer les envois manuels.
- Mesurer le disque depuis le conteneur TorrSearch (il ne monte pas les disques) : seul
  Transmission voit les dossiers.

## Anti-objectifs

- Un contrôle en panne qui bloque tous les téléchargements : **espace inconnu ⇒ on envoie**
  (journal en debug).
- Une ligne d'historique pour un envoi refusé : `seen_keys` la compterait comme déjà vue et une
  recherche libre ne la retenterait jamais (choix de conception : journal seulement).
- Un spam de notifications : une par jour au plus (`DailyNotice`).

## Approches envisagées

| Approche | Pour | Contre |
|---|---|---|
| **RPC `free-space` de Transmission, par dossier de destination** (retenue) | Mesure le vrai disque de destination (disk1 / disk2), sans monter les disques dans TorrSearch. | Un appel RPC de plus par envoi ; un dossier pas encore créé renvoie une erreur → remonter au parent. |
| `download-dir-free-space` de la session | Un seul appel. | Ne vaut que pour le dossier par défaut (disk2 ici) : faux pour les films (disk1). |
| Monter les disques dans le conteneur + `shutil.disk_usage` | Pas de RPC. | Change le déploiement (compose OMV), chemins différents selon les conteneurs. |

## Conception

- `TransmissionClient.free_space(path: str | None) -> int | None` : `None` ⇒ dossier par
  défaut de la session ; sinon essaie le chemin puis ses parents (un dossier de série/saison
  n'existe pas encore avant le premier envoi) ; chemin relatif ou toute erreur ⇒ `None`.
  Jamais d'exception.
- Module `torsearch/monitor/diskspace.py` :
  - `async def has_room(transmission, download_dir, size, min_free) -> bool` — `False`
    seulement si l'espace est connu et `free - size < min_free` ; `min_free` nul ⇒ `True` ;
    transport sans `free_space` (faux de test) ⇒ `True`.
  - `async def low_folders(transmission, config) -> list[tuple[str, str, int]]` — dossiers
    (libellé, chemin, octets libres) sous le seuil, chemins distincts des catégories + dossier
    par défaut si une catégorie n'en a pas.
  - `async def folder_usage(transmission, config) -> list[tuple[str, str, int | None]]` pour
    le panneau.
- Appels : `_grab_movie`, `_grab_series_release`, envoi auto de `run_cycle` — avant
  `transmission.add`, même `download_dir` que l'envoi.
- `MonitorRunner.run_once` : après les cycles, `low_folders` → `notify_message(config.notifications,
  "Disque presque plein", …)` filtré par un `DailyNotice` dédié.
- `health.check_all` : ligne « Disques » (OK · « Films 1,9 To · Series 638 Go libres », erreur
  sous le seuil), seulement si Transmission répond.
- `send_release` : après l'ajout, avertissement si le dossier est sous le seuil.

## Laissé au constructeur

- Format exact des tailles (Go / To) et des messages.
- Ordre des lignes du panneau.
