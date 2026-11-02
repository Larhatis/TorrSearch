# Conception : Chantier 11 — Claude branché sur TorrSearch (serveur MCP)

Date : 2026-11-02

## 1. Intention

L'utilisateur veut pouvoir demander à Claude, **depuis l'app Claude de son téléphone, y compris
hors de chez lui**, des choses comme « trouve-moi la meilleure version de Severance saison 2 »,
et que Claude se débrouille : il cherche sur les trackers, lit les noms de releases comme un
humain averti, choisit le meilleur rapport qualité/poids, lance le téléchargement et suit la
série pour la suite.

Ce que Claude apporte en plus du moteur de décision : du **jugement** sur le codec (AV1 ou x265
plutôt que x264), le HDR et le Dolby Vision, le poids par épisode, la langue (MULTI/VFF), la
réputation du groupe, et une explication courte de son choix. Le moteur reste la base ; Claude
arbitre entre les candidats acceptables et en parle avec l'utilisateur.

Rester dans l'esprit du projet : rien de plus à installer pour l'utilisateur qu'un connecteur
dans Claude, tout passe par TorrSearch (rangement, registre des envois, liste noire, limite de
fréquence des trackers, surveillance).

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
1. Un serveur MCP **distant** (transport Streamable HTTP) intégré à l'app TorrSearch, dans le
   même conteneur, utilisable comme « connecteur personnalisé » de claude.ai (web et mobile) et
   de Claude Desktop.
2. Des outils pour : trouver une œuvre (TMDB), chercher et comparer ses releases, lancer un
   téléchargement, suivre une série ou surveiller un film, consulter l'état (téléchargements,
   surveillance, profil de qualité).
3. Des fiches de release assez riches pour juger : codec, HDR/HDR10+/Dolby Vision, 10 bits,
   résolution, source, langue, groupe, taille et taille par épisode, épisodes couverts, seeders,
   verdict du moteur (acceptable ou non, et pourquoi).
4. Des consignes (instructions du serveur MCP, en français) qui disent à Claude comment choisir
   selon les préférences de l'utilisateur.
5. Accès protégé par une vraie connexion : l'utilisateur se connecte avec son compte
   **administrateur** TorrSearch au moment d'ajouter le connecteur ; accès révocable dans Réglages.
6. Exposition sur Internet de **ce seul point d'entrée** (et de ce qu'exige la connexion), le
   reste de l'interface restant sur le réseau local.

**Non-objectifs** : pas d'interface de discussion dans TorrSearch ; pas de serveur MCP local
(stdio) ; pas de pilotage des réglages, des comptes, des trackers ou des notifications par Claude.

**Anti-objectifs** (un échec même si « ça marche ») :
- Claude peut **supprimer** quoi que ce soit (torrent, fichier, liste noire, œuvre surveillée).
- Une adresse ou une clé de tracker sort dans une réponse d'outil.
- L'interface web entière devient joignable depuis Internet.
- Le point d'entrée est utilisable sans authentification, ou par un compte non administrateur.
- Claude enchaîne des dizaines de téléchargements dans une boucle.

## 3. Ce que l'utilisateur a décidé

- Usage depuis le téléphone, hors de chez lui (donc point d'entrée public en HTTPS).
- Claude lance directement les téléchargements qu'il juge bons, sans confirmation à chaque fois.
- Claude ne supprime rien.
- Claude ne voit jamais les adresses ni les clés des trackers.
- Le serveur MCP vit dans TorrSearch, même conteneur.

## 4. Conception technique

### 4.1 Serveur et transport
- Dépendance ajoutée : le SDK Python officiel `mcp` (FastMCP), seule nouvelle dépendance.
- Le serveur MCP est monté dans l'app FastAPI sous un préfixe dédié (ex. `/mcp`), transport
  Streamable HTTP, cycle de vie (session manager) branché sur le `lifespan` existant.
- Les outils appellent les mêmes services que l'interface (`AppContext`, `SearchService`,
  moteur de décision, `TransmissionClient`, bibliothèques, registre `GrabRegistry`) : aucune
  logique dupliquée.
- Les recherches de Claude passent par `SearchService`, donc par les limites de fréquence par
  tracker (`TrackerThrottle`).

### 4.2 Outils (noms et descriptions en français)
| Outil | Rôle |
|---|---|
| `chercher_oeuvre(titre)` | Résultats TMDB : id, type, titre FR et original, année, synopsis court, déjà dans Jellyfin, déjà surveillé. |
| `chercher_releases(requete, categorie, tmdb_id?, saison?)` | Releases trouvées sur les trackers, au plus ~40 les plus pertinentes, chacune en fiche (4.3) avec un **identifiant opaque** (`search/result_cache.py`). Avec `tmdb_id`, la recherche se fait sur le titre FR **et** le titre original (comme la surveillance) et la vérification titre/année du moteur s'applique. |
| `telecharger(release_id)` | Envoie la release à Transmission par le même chemin que `/download` : rangement (dossier film ou `Série/Saison XX`), marquage dans la surveillance si l'œuvre est suivie, inscription au registre en `manual` (jamais purgée automatiquement). |
| `suivre_serie(tmdb_id, deja_acquises?)` | Ajoute la série à la surveillance ; `deja_acquises` = saisons à marquer acquises (« reprendre à la saison 6 »). Active la surveillance globale comme le fait l'interface. |
| `surveiller_film(tmdb_id)` | Ajoute le film à la surveillance. |
| `etat_telechargements()` | Torrents en cours et récents : nom, %, débit, temps restant, statut, erreur éventuelle (masquée par `redact()`). |
| `etat_surveillance()` | Œuvres surveillées, épisodes manquants, derniers envois de la surveillance. |
| `profil_qualite()` | Profil courant : qualités, langues (VOSTFR acceptée ?), mots exclus, plafonds de taille. |

Aucun outil de suppression, de modification de réglage ou de liste noire.

### 4.3 Fiche de release
Champs : `id`, `titre`, `tracker` (nom seulement), `taille`, `taille_par_episode` (packs :
poids moyen par épisode, même calcul que le moteur), `seeders`, `resolution`, `codec`,
`hdr` (aucun / HDR10 / HDR10+ / Dolby Vision, cumul possible), `bits` (8/10), `source`,
`langue`, `groupe`, `episodes` (clés `SxxEyy` ou saisons), `en_liste_noire`, `deja_dans_transmission`
(infohash identique, sinon même titre normalisé et mêmes épisodes, comme `_same_release`),
`verdict` (acceptable selon le profil ou motif du rejet : langue, source dégradée, taille max,
mot exclu…). Jamais `download_url` ni lien magnet.

Le parseur (`parser/release.py`) gagne la détection HDR10 / HDR10+ / Dolby Vision et 10 bits.

### 4.4 Consignes données à Claude (instructions du serveur)
En français, courtes, tirées du profil courant à chaque connexion :
- langue : MULTI/VFF d'abord, puis VF/VFQ, VOSTFR seulement si le profil l'accepte ;
- jamais de CAM/TS/TC/SCR, ni de release en liste noire ;
- à qualité d'image égale, préférer AV1 ou x265 à x264 (fichiers plus légers) ;
- préférer 2160p avec HDR/DV quand le poids reste dans les plafonds, sinon 1080p ;
- pour une saison complète, un pack plutôt que des épisodes séparés ;
- assez de seeders pour démarrer (≥ le minimum du profil) ;
- expliquer le choix en une phrase ; demander seulement en cas de vrai doute ;
- vérifier `etat_telechargements` / `deja_dans_transmission` avant de relancer quelque chose.

### 4.5 Authentification
- OAuth 2.1 avec enregistrement dynamique des clients (DCR) et PKCE, en s'appuyant sur le
  support d'authentification du SDK `mcp` (serveur d'autorisation intégré à TorrSearch).
- Page d'autorisation : connexion avec un compte TorrSearch ; seul le rôle **admin** peut
  accorder l'accès ; page de consentement « Autoriser Claude à chercher, télécharger et suivre
  des œuvres » (sans accents dans le template).
- Jetons d'accès courts + jetons de rafraîchissement, stockés en base (collection dédiée,
  empreintes plutôt que jetons en clair) ; Réglages → Maintenance → « Acces Claude » liste les
  accès accordés et permet de les **révoquer**. Révoquer, changer le mot de passe ou supprimer
  le compte invalide les jetons.
- Authentification TorrSearch désactivée (`TORSEARCH_USERNAME` absent) → le point d'entrée MCP
  refuse tout (503 explicite) : jamais d'accès sans connexion.
- Le garde anti-CSRF (`CrossSiteGuardMiddleware`) et l'`AuthMiddleware` ne doivent pas bloquer
  les appels légitimes de Claude vers `/mcp` et les routes OAuth, sans s'ouvrir pour le reste.

### 4.6 Garde-fous
- Au plus **10 téléchargements par heure** lancés via MCP (au-delà : erreur explicite pour
  Claude) ; au plus 30 recherches tracker par heure via MCP.
- Journal (`logbuffer`) : chaque appel d'outil MCP est tracé (outil, arguments sans secret).
- Les réponses d'outils passent par `redact()` pour tout message d'erreur.

### 4.7 Exposition sur Internet
- Les connecteurs de claude.ai sont appelés depuis l'infrastructure d'Anthropic : le point
  d'entrée doit être public, en HTTPS.
- Le NAS n'a ni reverse proxy ni tunnel aujourd'hui (TorrSearch écoute en LAN sur le port 8585).
- L'utilisateur a un nom de domaine. Choix retenu : **Cloudflare Tunnel** (conteneur
  `cloudflared` à côté de TorrSearch, aucun port ouvert sur la box, HTTPS géré par Cloudflare)
  sur un sous-domaine dédié, avec des règles d'entrée qui ne laissent passer **que** les chemins
  MCP et OAuth (le reste répond 404). Repli si le domaine ne peut pas passer chez Cloudflare :
  reverse proxy (Caddy) + port 443 ouvert, mêmes chemins seulement.
- Le domaine de l'utilisateur n'apparaît jamais dans le dépôt (public) : exemples avec
  `torrsearch.example.com`.
- Le README documente la mise en place (conteneur `cloudflared`, règles de chemins). La mise en
  place sur le NAS est faite à part, avec l'accord de l'utilisateur.
- L'adresse publique sert à construire les URL OAuth : réglage `mcp.public_url` (onglet
  Connexions), vide = MCP désactivé.

### 4.8 Cas limites
- TMDB non configuré : `chercher_oeuvre`, `suivre_serie` et `surveiller_film` répondent un message
  clair (« clé TMDB absente dans Réglages ») ; `chercher_releases` marche sans `tmdb_id`.
- Identifiant de release expiré (cache de 6 h) : `telecharger` demande de relancer la recherche.
- Transmission injoignable : message d'erreur masqué, rien n'est inscrit.
- Les plafonds horaires sont gardés en mémoire du processus (remis à zéro au redémarrage).

### 4.9 Livraison
Version **0.10.0** ; AGENTS.md (§2, §4, nouvelle règle §6 « Claude ne supprime rien et ne voit
aucune clé ») ; README (section « Claude ») ; une PR.

## 5. Laissé au développeur
- Câblage exact du SDK (`streamable_http_app`, `AuthSettings`, fournisseur OAuth) et
  disposition des chemins (préfixe, `/.well-known/*`) compatibles avec un montage sous préfixe.
- Format de stockage des clients, codes et jetons.
- Mise en forme exacte des fiches (texte structuré ou JSON) tant que les champs de 4.3 y sont.

## 6. Décisions prises sans l'utilisateur (à relire)
- OAuth avec connexion admin plutôt qu'une URL secrète : le point d'entrée est public et peut
  lancer des téléchargements.
- Cloudflare Tunnel pour l'exposition, sur un sous-domaine du domaine de l'utilisateur.
- Les téléchargements lancés par Claude sont inscrits `manual` : jamais purgés automatiquement,
  comme un choix de l'utilisateur.
- Plafonds : 10 téléchargements et 30 recherches par heure via MCP.
- Noms d'outils en français.
