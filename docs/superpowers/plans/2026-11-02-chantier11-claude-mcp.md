# Chantier 11 — Claude branché sur TorrSearch : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un serveur MCP distant intégré à TorrSearch, protégé par OAuth (compte admin), qui laisse Claude chercher, comparer, télécharger et suivre des œuvres sans jamais rien supprimer ni voir de clé de tracker.

**Architecture:** Le SDK officiel `mcp` 2.x (`mcp.server.mcpserver.MCPServer`) fournit le transport Streamable HTTP et les routes OAuth (`/.well-known/*`, `/authorize`, `/token`, `/register`, `/revoke`, `/mcp`) ; son app Starlette est montée sur `/` **après** toutes les routes FastAPI. TorrSearch fournit le fournisseur OAuth (stockage en base, page de consentement avec connexion admin) et les outils, qui réutilisent les services existants. Vérifié par un essai : routes, métadonnées et 401 sans jeton fonctionnent ainsi.

**Tech Stack:** Python 3.12, FastAPI/Starlette, SDK `mcp>=2.3,<3`, SQLite (doc-store), pytest (+ `mcp.Client(server)` en mémoire pour les tests d'outils).

**Spec:** `docs/superpowers/specs/2026-11-02-chantier11-claude-mcp-design.md`

## Global Constraints

- Seule nouvelle dépendance : `mcp>=2.3,<3` (`pyproject.toml`).
- Adresse publique : variable d'environnement **`TORSEARCH_PUBLIC_URL`** (ex. `https://torrsearch.example.com`, sans `/` final) lue au démarrage ; vide = MCP désactivé (aucune route montée). Déviation assumée de la spec (réglage UI) : l'app MCP est construite au démarrage, un réglage modifiable à chaud serait trompeur — voir ledger.
- Authentification TorrSearch désactivée + `TORSEARCH_PUBLIC_URL` défini → `/mcp` répond **503** « Activez l'authentification (TORSEARCH_USERNAME / TORSEARCH_PASSWORD) pour utiliser Claude. », aucune route OAuth.
- Scope OAuth unique : `torrsearch`. Durées : code 5 min, jeton d'accès 1 h, jeton de rafraîchissement 30 jours (rotation à chaque usage). Jetons stockés par **empreinte SHA-256**, jamais en clair.
- Seul un compte **admin** peut accorder l'accès ; un jeton devient invalide si le compte disparaît, perd le rôle admin ou change de mot de passe (empreinte `session_fingerprint(password_hash, secret_key)` mémorisée dans le jeton).
- Plafonds via MCP (mémoire du processus) : **10** téléchargements / heure, **30** recherches tracker / heure.
- Aucun outil ne supprime ni ne modifie réglages, comptes, trackers, notifications ou liste noire.
- Aucune réponse d'outil ne contient `download_url`, lien magnet, URL ou clé de tracker ; messages d'erreur passés par `redact()`.
- Les téléchargements lancés par Claude sont inscrits `manual` au registre des envois.
- Noms et descriptions d'outils en français ; templates HTML sans accents ; aucun JS inline ; docstrings/commentaires en anglais.
- Domaine de l'utilisateur jamais dans le dépôt : exemples avec `torrsearch.example.com`.
- Commits `type(portée): description` en français, un par tâche, test rouge d'abord. Vérification : `ruff check torsearch tests`, `mypy`, `pytest -q` (venv `/Users/clementcappeau/Github/TorrSearch/.venv/bin/`).

## Review Focus

- Un compte **membre** ou un mauvais mot de passe sur la page de consentement : jamais de code émis, échecs comptés par `LoginThrottle` → test Task 6.
- Un jeton valide après **changement de mot de passe** ou **rétrogradation** : doit être refusé → test Task 4.
- Une route de l'interface (ex. `/settings`) atteinte via le domaine public sans session : doit rester derrière la connexion (seuls les chemins MCP/OAuth sont publics) → test Task 6.
- Un identifiant de release **expiré** ou inventé passé à `telecharger` : message clair, rien envoyé → test Task 5.
- Le 11ᵉ téléchargement de l'heure : refusé avec un message explicite, rien envoyé → test Task 5.

---

### Task 1: Parseur — HDR, Dolby Vision, 10 bits, groupe

**Files:**
- Modify: `torsearch/parser/release.py` (`ParsedRelease`, `parse_release`)
- Test: `tests/test_release_parser.py`

**Interfaces:**
- Produces: `ParsedRelease.hdr: tuple[str, ...]` (sous-ensemble ordonné de `("DV", "HDR10+", "HDR")`, `()` si aucun), `ParsedRelease.bit_depth: int | None` (10 ou `None`), `ParsedRelease.group: str | None`.

- [ ] **Step 1: Tests rouges**

```python
def test_hdr_dolby_vision_and_bit_depth():
    rel = parse_release("Fallout.S02E01.MULTi.DV.HDR10+.2160p.WEBRip.x265.10bit-BATGirl.mkv")
    assert rel.hdr == ("DV", "HDR10+")
    assert rel.bit_depth == 10
    assert rel.group == "BATGirl"

def test_plain_hdr_and_bracketed_group():
    rel = parse_release("Show.S01E05.MULTi.4Klight.HDR.WEBRip.EAC3.x265-[PSA]-BATGirl.mkv")
    assert rel.hdr == ("HDR",)
    assert rel.group == "BATGirl"

def test_no_hdr_no_group():
    rel = parse_release("Some Movie 2020 1080p WEB H264")
    assert rel.hdr == () and rel.bit_depth is None and rel.group is None

def test_dvdrip_is_not_dolby_vision():
    assert parse_release("Old.Film.1999.DVDRip.XviD-GRP").hdr == ()
```

- [ ] **Step 2:** `pytest tests/test_release_parser.py -q` → échecs (attributs absents).
- [ ] **Step 3:** Motifs (sans casse, mots entiers) : DV = `dv|dovi|dolby[ ._-]?vision` ; HDR10+ = `hdr10(\+|plus)` ; HDR = `hdr(10)?` non suivi de `+`/`plus` ; 10 bits = `10[ ._-]?bits?` ; groupe = dernier `-<groupe>` (crochets retirés) avant l'extension `.mkv|.mp4|.avi` éventuelle, en fin de nom. Les nouveaux champs ont des valeurs par défaut (aucun appelant cassé). Ne pas couper le titre sur ces jetons (le titre est déjà coupé avant la résolution).
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(parser): HDR, Dolby Vision, 10 bits et groupe de release"`

### Task 2: Fiche de release pour Claude

**Files:**
- Create: `torsearch/claude/__init__.py` (vide), `torsearch/claude/cards.py`
- Test: `tests/test_claude_cards.py`

**Interfaces:**
- Consumes: `ParsedRelease.hdr/bit_depth/group` (Task 1), `evaluate_release`, `ReleaseRules.from_profile`, `decision._episode_count`, `stalled._same_release` n'est **pas** réutilisé (comparaison simple ci-dessous).
- Produces: `release_card(result: SearchResult, rid: str, profile: LibraryConfig, blacklist, torrents: list[TorrentInfo], target_title: str | None = None, target_original_title: str | None = None, target_year: int | None = None, is_series: bool = False) -> dict` ; `VERDICTS: dict[str, str]` (motif → texte).

Clés de la fiche (ordre libre) : `id, titre, tracker, taille_go, taille_par_episode_go, seeders, resolution, codec, hdr (liste), bits, source, langue, groupe, episodes (liste triée), en_liste_noire, deja_dans_transmission, verdict`. `verdict` = `"acceptable"` ou le texte de `VERDICTS` : `low_seeders` → « pas assez de seeders », `too_large` → « trop gros pour le profil », `blacklisted` → « en liste noire », `excluded_word:X` → « mot exclu : X », `vostfr_refused` → « VOSTFR refusee par le profil », `banned_source:X` → « source degradee (X) », `title_mismatch` → « ne correspond pas a l'oeuvre », autre → motif brut. `deja_dans_transmission` : infohash identique (minuscules) **ou** même nom de torrent (sans casse).

- [ ] **Step 1: Tests rouges**

```python
def test_card_never_exposes_the_download_url():
    card = release_card(_r("Show.S01.MULTi.2160p.DV.WEB.x265-GRP", url="https://tracker.example/dl?passkey=SECRET"), "rid1", LibraryConfig(), None, [])
    assert "SECRET" not in json.dumps(card) and "tracker.example" not in json.dumps(card)
    assert card["id"] == "rid1" and card["tracker"] == "trk"

def test_card_fields_for_a_season_pack():
    card = release_card(_r("Show.S01.MULTi.2160p.DV.HDR10+.WEB.x265.10bit-GRP", size=10_000_000_000), "r", LibraryConfig(), None, [])
    assert card["hdr"] == ["DV", "HDR10+"] and card["bits"] == 10 and card["codec"] != "unknown"
    assert card["episodes"] == ["S01"] and card["taille_par_episode_go"] == 1.0  # 10 épisodes par défaut sans TMDB

def test_card_verdicts():
    vost = release_card(_r("Show.S01E01.VOSTFR.1080p.WEB.x264-GRP"), "r", LibraryConfig(accept_vostfr=False), None, [])
    assert vost["verdict"] == "VOSTFR refusee par le profil"
    cam = release_card(_r("Film.2024.CAM.x264-GRP"), "r", LibraryConfig(), None, [])
    assert cam["verdict"].startswith("source degradee")

def test_card_knows_what_transmission_already_has():
    t = TorrentInfo(id=1, name="Show.S01E01.MULTi.1080p.WEB.x264-GRP", percent=50.0, status="downloading",
                    down_rate=0, up_rate=0, size=1, info_hash="abc")
    assert release_card(_r("Other.Name", infohash="ABC"), "r", LibraryConfig(), None, [t])["deja_dans_transmission"]
    assert release_card(_r("show.s01e01.multi.1080p.web.x264-grp"), "r", LibraryConfig(), None, [t])["deja_dans_transmission"]
```

(`_r(title, size=1_000_000_000, seeders=20, infohash=None, url="magnet:?xt=urn:btih:x")` construit un `SearchResult` avec `source="trk"`.)

- [ ] **Step 2:** `pytest tests/test_claude_cards.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3:** `evaluate_release(..., qualities=profile.qualities, min_seeders=profile.min_seeders, blacklist=blacklist, max_size=profile.max_episode_size if is_series else profile.max_movie_size, rules=ReleaseRules.from_profile(profile))` avec les cibles si fournies ; sans cible, la vérification de titre est sautée (passer le titre parsé de la release comme cible). Tailles en Go arrondies à 2 décimales ; taille par épisode via `_episode_count(parsed.episodes, set())` (packs), sinon `None` pour un film.
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(claude): fiche de release sans lien de tracker"`

### Task 3: Envoi d'une release partagé (interface et Claude)

**Files:**
- Create: `torsearch/library/sending.py`
- Modify: `torsearch/web/routes.py` (`/download` délègue)
- Test: `tests/test_sending.py` (+ tests `/download` existants inchangés)

**Interfaces:**
- Produces: `@dataclass SendOutcome: ok: bool; message: str; torrent_id: int | None = None` ; `async def send_release(state, download_url: str, title: str, category: Category, fallback_hash: str | None = None) -> SendOutcome` — `state` = `request.app.state` (ou objet équivalent avec `ctx`, `library`, `series_library`, `history`, `grabs`). Comportement = celui de `/download` aujourd'hui : `plan_manual_grab`, `transmission.add`, toast « Ajoute a Transmission (#id) » (+ « · marque acquis dans la surveillance (X) »), `record_manual_grab`, `grabs.record(added_hash or fallback_hash, title, MANUAL)` protégé par `try` ; erreur Transmission → `ok=False`, message `redact()`é.

- [ ] **Step 1: Tests rouges** (`tests/test_sending.py`, faux Transmission renvoyant `AddedTorrent(id=7, info_hash="hh")`)

```python
async def test_send_release_files_records_and_reports(tmp_path):
    out = await send_release(state, "magnet:?x", "The.Dog.Stars.2026.MULTi.1080p.WEB-GRP", Category.MOVIES)
    assert out.ok and out.torrent_id == 7 and "Ajoute a Transmission (#7)" in out.message
    assert state.grabs.get("hh").origin == "manual"

async def test_send_release_falls_back_to_the_result_hash(tmp_path):  # add() sans hash
    await send_release(state_no_hash, "magnet:?x", "T", Category.MOVIES, fallback_hash="FB")
    assert state_no_hash.grabs.get("fb").origin == "manual"

async def test_send_release_transmission_error_is_redacted(tmp_path):
    out = await send_release(state_failing, "magnet:?x", "T", Category.MOVIES)
    assert not out.ok and "SECRET" not in out.message
```

- [ ] **Step 2:** `pytest tests/test_sending.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3:** Déplacer la logique de `/download` dans `send_release` ; `/download` résout l'identifiant/URL comme avant puis appelle `send_release(request.app.state, url, title, cat, fallback_hash=cached.infohash if cached else None)` et rend le toast avec `out.ok/out.message`.
- [ ] **Step 4:** `pytest -q` → tout passe (dont tous les tests `/download` existants).
- [ ] **Step 5:** `git commit -m "refactor(download): envoi d'une release partage entre l'interface et Claude"`

### Task 4: Plafonds horaires et fournisseur OAuth

**Files:**
- Modify: `pyproject.toml` (dépendance `mcp>=2.3,<3`)
- Create: `torsearch/claude/limits.py`, `torsearch/claude/oauth.py`
- Test: `tests/test_claude_limits.py`, `tests/test_claude_oauth.py`

**Interfaces:**
- Produces:
  - `class HourlyLimit(max_calls: int, window_seconds: float = 3600, clock=time.monotonic)` avec `allow() -> bool` (enregistre l'appel s'il est permis).
  - `SCOPE = "torrsearch"` ; `class TorrSearchOAuthProvider(collection: Collection, users: UserStore, secret_key: str, public_url: str, clock=time.time)` implémentant `mcp.server.auth.provider.OAuthAuthorizationServerProvider` (`get_client, register_client, authorize, load_authorization_code, exchange_authorization_code, load_refresh_token, exchange_refresh_token, load_access_token, revoke_token`).
  - `authorize(client, params) -> str` mémorise la demande (`pending:<id>`, 10 min) et renvoie `f"{public_url}/claude/autoriser?demande={id}"`.
  - `pending(request_id: str) -> PendingRequest | None` (`client_id`, `client_name`, `params`) ; `approve(request_id: str, username: str) -> str` → crée le code (sujet = `username`, empreinte du mot de passe) et renvoie l'URL de redirection du client (`construct_redirect_uri` du SDK, avec `code` et `state`) ; `deny(request_id: str) -> str` → redirection avec `error=access_denied`.
  - `grants() -> list[Grant]` (`client_id`, `client_name`, `username`, `granted_at`) pour les clients ayant un jeton de rafraîchissement valide ; `revoke_client(client_id: str) -> None` (supprime le client, ses codes et jetons).

- [ ] **Step 1: Tests rouges**

```python
def test_hourly_limit():
    t = [0.0]; lim = HourlyLimit(2, clock=lambda: t[0])
    assert lim.allow() and lim.allow() and not lim.allow()
    t[0] = 3601; assert lim.allow()

async def test_full_grant_flow(tmp_path):
    # register_client → authorize → approve("admin") → load/exchange code → load_access_token
    ...
    assert (await p.load_access_token(tokens.access_token)).subject == "admin"
    assert p.grants()[0].client_name == "Claude"

async def test_refresh_rotates(tmp_path):     # l'ancien refresh ne marche plus après usage
async def test_token_dies_with_password_change(tmp_path):   # users.set_password → load_access_token is None
async def test_token_dies_with_demotion(tmp_path):          # users.set_role(MEMBER) → None
async def test_revoke_client_kills_its_tokens(tmp_path):    # revoke_client → access None, grants() vide
async def test_expired_code_and_token(tmp_path):            # horloge avancée : code 301 s, access 3601 s → None
def test_tokens_are_stored_hashed(tmp_path):                # aucun document ne contient le jeton en clair
async def test_unknown_or_expired_pending_request(tmp_path):  # pending("x") is None ; approve lève ValueError
```

- [ ] **Step 2:** `pytest tests/test_claude_limits.py tests/test_claude_oauth.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3:** Collection `oauth` ; ids de documents `client:<id>`, `pending:<id>`, `code:<sha>`, `access:<sha>`, `refresh:<sha>` ; jetons via `secrets.token_urlsafe(32)` ; `load_access_token` vérifie expiration + utilisateur existant, rôle admin, empreinte identique. Ajouter `mcp>=2.3,<3` aux dépendances.
- [ ] **Step 4:** `pytest -q` → tout passe ; `mypy` propre.
- [ ] **Step 5:** `git commit -m "feat(claude): fournisseur OAuth (compte admin) et plafonds horaires"`

### Task 5: Serveur MCP et outils

**Files:**
- Create: `torsearch/claude/server.py`
- Test: `tests/test_claude_tools.py`

**Interfaces:**
- Consumes: `release_card` (Task 2), `send_release` (Task 3), `HourlyLimit` (Task 4), `ResultCache` (`state.result_cache`).
- Produces: `build_claude_server(state, auth: AuthSettings | None = None, provider=None) -> MCPServer` (nom « TorrSearch », `instructions=claude_instructions(state.ctx.config.library)` recalculées à la construction) ; `claude_instructions(profile: LibraryConfig) -> str` ; outils (paramètres en français) :
  - `chercher_oeuvre(titre: str) -> list[dict]` (`tmdb_id, type, titre, titre_original, annee, synopsis` ≤ 300 car., `dans_jellyfin`, `surveille`) ;
  - `chercher_releases(requete: str, categorie: str = "all", tmdb_id: int | None = None, type: str | None = None) -> list[dict]` (≤ 40 fiches, ordre de pertinence existant `apply(..., ResultFilters(sort="relevance", query=requete))`, ids via `state.result_cache.put`) ; avec `tmdb_id`+`type`, requêtes titre FR et original via `tmdb.get_details` et cibles passées à `release_card` ;
  - `telecharger(release_id: str) -> str` (cache → `send_release(..., fallback_hash=result.infohash)`) ;
  - `suivre_serie(tmdb_id: int, saisons_acquises: list[int] | None = None) -> str` (ajout comme `/series/add`, marquage des saisons via `tmdb.seasons` : `season_tag` + codes d'épisodes ; active la surveillance globale et `monitor.wake()`) ;
  - `surveiller_film(tmdb_id: int) -> str` (comme `/library/add`) ;
  - `etat_telechargements() -> list[dict]` (`nom, progression, statut, debit, temps_restant, erreur`), 30 plus récents ;
  - `etat_surveillance() -> dict` (`films` : titre/statut, `series` : titre/nb d'épisodes acquis/dernier acquis, `recherches_libres`, `derniers_envois` : 10 derniers « grabbed » de l'historique) ;
  - `profil_qualite() -> dict` (`qualites, seeders_min, vostfr_acceptee, mots_exclus, taille_max_film_go, taille_max_episode_go, upgrades`).
  Plafonds : `chercher_releases` consomme le plafond recherches (30/h), `telecharger` le plafond téléchargements (10/h) ; dépassement → texte « Limite atteinte : … par heure. Reessaie plus tard. » sans appel. Chaque appel d'outil : `logger.info("Claude : %s %s", nom, args)`.

- [ ] **Step 1: Tests rouges** (`async with Client(build_claude_server(state)) as c:` ; faux contexte avec `SearchService` factice, TMDB factice, Transmission factice)

```python
async def test_tool_list_has_no_destructive_tool():
    names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"chercher_oeuvre", "chercher_releases", "telecharger", "suivre_serie",
                     "surveiller_film", "etat_telechargements", "etat_surveillance", "profil_qualite"}

async def test_search_returns_cards_without_urls():   # aucune "passkey"/"http" de tracker dans le texte du résultat
async def test_download_by_id_sends_and_records_manual():
async def test_expired_or_unknown_id_sends_nothing():   # "Resultat expire : relance la recherche." ; tr.added == []
async def test_eleventh_download_of_the_hour_is_refused():
async def test_search_limit_30_per_hour():
async def test_follow_series_marks_owned_seasons():     # saisons_acquises=[1] → S01 + ses épisodes marqués
async def test_watch_movie_enables_surveillance():
async def test_instructions_follow_the_profile():       # accept_vostfr=False → "VOSTFR" refusée dans claude_instructions
async def test_tmdb_missing_is_explained():             # chercher_oeuvre sans clé → message « cle TMDB absente »
```

- [ ] **Step 2:** `pytest tests/test_claude_tools.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3:** Implémenter ; plafonds stockés sur l'objet serveur (une instance `HourlyLimit` par plafond, créée dans `build_claude_server`). Consignes (`claude_instructions`) reprenant spec §4.4, avec les valeurs du profil.
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(claude): serveur MCP et outils de recherche, envoi et suivi"`

### Task 6: Montage, page de consentement et chemins publics

**Files:**
- Create: `torsearch/web/claude_routes.py`, `torsearch/web/templates/claude_consent.html` (page autonome, `<style>` en ligne, pas de script)
- Modify: `torsearch/web/routes.py` (`create_app(..., public_url: str | None = None)` : montage, lifespan), `torsearch/web/auth.py` (chemins publics), `torsearch/main.py` (lit `TORSEARCH_PUBLIC_URL`, crée le fournisseur sur `db.collection("oauth")`)
- Test: `tests/test_claude_web.py`

**Interfaces:**
- Consumes: `TorrSearchOAuthProvider` (Task 4), `build_claude_server` (Task 5), `LoginThrottle` (`app.state.login_throttle`).
- Produces: `GET /claude/autoriser?demande=<id>` (formulaire identifiant + mot de passe, nom du client, « Autoriser Claude a chercher, telecharger et suivre des oeuvres » ; boutons Autoriser / Refuser) ; `POST /claude/autoriser` (`demande`, `username`, `password`, `decision`) → 303 vers l'URL renvoyée par `approve`/`deny`, ou page avec erreur ; `app.state.claude_provider`.
- Chemins publics ajoutés dans `auth.py` : exacts `/mcp`, `/authorize`, `/token`, `/register`, `/revoke`, `/claude/autoriser` ; préfixe `/.well-known/oauth-`.
- Montage (dans `create_app`, si `public_url`) : `AuthSettings(issuer_url=public_url, resource_server_url=f"{public_url}/mcp", validate_token_resource=False, required_scopes=[SCOPE], client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]), revocation_options=RevocationOptions(enabled=True))` ; `streamable_http_app(streamable_http_path="/mcp", stateless_http=True, host="0.0.0.0", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))` monté par `app.mount("/", sub)` **après** `/static` ; `lifespan` : `async with server.session_manager.run()` autour du `yield`. Auth désactivée → route `/mcp` (toutes méthodes) en 503 avec le message des Global Constraints, rien d'autre.

- [ ] **Step 1: Tests rouges** (TestClient avec `base_url="https://torrsearch.example.com"`, `AuthSettings(enabled=True)`, comptes admin/membre)

```python
def test_oauth_flow_end_to_end():
    # POST /register (redirect_uris=["https://claude.ai/api/mcp/auth_callback"], client_name="Claude")
    # GET /authorize?... code_challenge=S256(verifier) → 302 vers /claude/autoriser?demande=…
    # POST /claude/autoriser (admin, bon mot de passe, decision=autoriser) → 303 vers le callback avec code
    # POST /token (authorization_code + code_verifier) → access_token
    # POST /mcp tools/list avec Bearer → 200 et les 8 outils
def test_member_cannot_authorize():          # membre → page d'erreur, aucun code
def test_wrong_password_is_throttled():      # 5 échecs → bloqué même avec le bon mot de passe
def test_deny_redirects_with_access_denied():
def test_mcp_without_token_is_401():
def test_ui_stays_private_on_the_public_host():  # GET /settings sans session → redirection /login (pas 200)
def test_auth_disabled_answers_503():
def test_no_public_url_mounts_nothing():     # GET /.well-known/oauth-authorization-server → 404, /mcp → 404
def test_consent_page_has_no_inline_js():    # couvert aussi par test_no_inline_js
```

- [ ] **Step 2:** `pytest tests/test_claude_web.py -q` → échecs.
- [ ] **Step 3:** Implémenter ; clé d'empreinte = `auth.secret_key` ; throttle par `request.client.host`.
- [ ] **Step 4:** `pytest -q` → tout passe (dont `test_no_inline_js.py`).
- [ ] **Step 5:** `git commit -m "feat(claude): montage MCP, consentement admin et chemins publics limites"`

### Task 7: Réglages → Maintenance → « Acces Claude »

**Files:**
- Create: `torsearch/web/templates/partials/claude_access.html` (section `id="claude-access"`)
- Modify: `torsearch/web/templates/partials/settings_maintenance.html`, `torsearch/web/settings_routes.py`
- Test: `tests/test_claude_settings.py`

**Interfaces:**
- Consumes: `app.state.claude_provider.grants()/revoke_client()` (Task 4/6), `app.state.claude_public_url`.
- Produces: section : MCP désactivé → « Definis TORSEARCH_PUBLIC_URL (adresse publique en HTTPS) pour brancher Claude. » ; actif → « Adresse du connecteur : <public_url>/mcp » + liste des accès (client, compte, date) avec « Revoquer » (`POST /settings/claude/revoke`, champ `client_id` dans le corps, réponse HTMX qui remplace la section) ; aucun accès → « Aucun acces accorde. ».

- [ ] **Step 1: Tests rouges** : section désactivée sans URL ; URL du connecteur affichée ; un accès listé ; « Revoquer » le retire et invalide son jeton ; membre → 403.
- [ ] **Step 2:** `pytest tests/test_claude_settings.py -q` → échecs.
- [ ] **Step 3:** Implémenter (sans accents, sans JS inline).
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(settings): acces Claude visibles et revocables"`

### Task 8: Documentation et version

**Files:**
- Modify: `pyproject.toml`, `torsearch/__init__.py` (`0.10.0`), `.env.example` (`TORSEARCH_PUBLIC_URL=`), `README.md` (section « Claude » : prérequis auth active, `TORSEARCH_PUBLIC_URL`, conteneur `cloudflared` d'exemple, règles d'entrée limitées aux chemins `/mcp`, `/authorize`, `/token`, `/register`, `/revoke`, `/claude/autoriser`, `/.well-known/oauth-*`, ajout du connecteur dans claude.ai → Customize → Connectors, dispo ensuite sur mobile), `AGENTS.md` (§2 entrée chantier 11, §4 `torsearch/claude/`, §6 règle 10 « Claude ne supprime rien et ne voit aucune clé ; seuls les chemins MCP/OAuth sont publics », §7 piège « SDK mcp 2.x : `MCPServer`, app montée sur `/` après les routes »)

- [ ] **Step 1:** Mettre à jour les fichiers.
- [ ] **Step 2:** `ruff check torsearch tests && mypy && pytest -q` → vert ; reporter le nombre de tests dans AGENTS.md.
- [ ] **Step 3:** `git commit -m "chore(release): chantier 11 Claude branche sur TorrSearch (v0.10.0)"`
