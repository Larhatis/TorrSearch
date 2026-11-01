# Chantier 10 — purge sûre : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La purge automatique ne touche plus que les torrents envoyés par la surveillance, surveillance active, morts de façon certaine ; la liste noire devient visible et réversible ; les épisodes ≥ 100 sont lus correctement.

**Architecture:** Un registre en base (`grabs`, clé = infohash Transmission) mémorise chaque envoi et son origine (`auto` / `manual`). La purge, sortie de `runner.py` vers `monitor/stalled.py`, ne considère que les entrées `auto`, filtre les erreurs par message et s'interrompt au-delà de 3 candidats. L'infohash vient de la réponse de `add_torrent`.

**Tech Stack:** Python 3.12, FastAPI + Jinja2 + HTMX, SQLite (doc-store maison), transmission-rpc 7, pytest (+ pytest-asyncio auto).

**Spec:** `docs/superpowers/specs/2026-11-01-chantier10-purge-sure-design.md`

## Global Constraints

- Docstrings et commentaires en anglais ; textes affichés en français ; templates HTML **sans accents**.
- Aucun JS inline dans les templates (`tests/test_no_inline_js.py`).
- Appels Transmission uniquement via `TransmissionClient` (jamais dans la boucle async).
- Infohash toujours comparé en minuscules.
- Seuil du disjoncteur : **plus de 3** candidats → aucune purge. Notification de suspension au plus **une fois par jour**.
- Mots « torrent inconnu du tracker » (sans casse) : `unregistered`, `not registered`, `torrent not found`, `unknown torrent`, `does not exist`, `not exist`, `n'existe pas`, `introuvable`, `info_hash not found`, `infohash not found` ; jamais si `error_code == 3`.
- `MonitorRecord.infohash` garde l'infohash **du tracker** (ne jamais y recopier celui de Transmission).
- Commits `type(portée): description` en français, un par tâche, test rouge d'abord.
- Vérification finale : `ruff check torsearch tests`, `mypy`, `pytest -q` (venv : `/Users/clementcappeau/Github/TorrSearch/.venv/bin/`).

## Review Focus

- Le même torrent ré-ajouté à la main après un envoi auto (ou l'inverse) : l'entrée `manual` doit gagner, jamais redevenir purgeable → test Task 3.
- Transmission ne renvoie pas d'infohash (vieux démon, fake) et le tracker non plus : aucune entrée, torrent jamais purgé → test Task 4.
- Casse différente entre l'infohash du tracker (majuscules) et celui de Transmission → test Task 3.
- Frontière du disjoncteur : exactement 3 candidats sont purgés, 4 ne le sont pas → test Task 5.
- Titre en liste noire contenant `/`, apostrophe ou accents : « Retirer » doit marcher → test Task 6.

---

### Task 1: Épisodes à 3-4 chiffres

**Files:**
- Modify: `torsearch/library/episodes.py:9-12` (`_SEASON_EP_RE`, `_EP_TOKEN_RE`)
- Test: `tests/test_episode_parser.py`

- [ ] **Step 1: Tests rouges**

```python
def test_long_running_episode_numbers():
    assert parse_episodes("One.Piece.S01E1089.VOSTFR.1080p.WEB") == {"S01E1089"}
    assert parse_episodes("Detective.Conan.S21E1100.FRENCH.720p") == {"S21E1100"}
    assert parse_episodes("Show.S01E100.MULTi.1080p") == {"S01E100"}

def test_episode_range_and_resolution_still_safe():
    assert parse_episodes("Show.S01E01-E03.1080p") == {"S01E01", "S01E02", "S01E03"}
    assert parse_episodes("Show.S01E05-1080p.WEB") == {"S01E05"}
    assert parse_episodes("Show.S01E01-03.1080p") == {"S01E01", "S01E02", "S01E03"}
```

- [ ] **Step 2:** `pytest tests/test_episode_parser.py -q` → les deux tests échouent (`S01E10`).
- [ ] **Step 3:** Episode après `e` : `\d{1,4}` ; borne de plage avec `e` : `e\d{1,4}` ; borne **sans** `e` : `\d{1,2}(?!\d)` (garde de la résolution). Même découpage dans `_EP_TOKEN_RE` (groupes : début, fin avec `e`, fin sans `e`).
- [ ] **Step 4:** `pytest -q` → tout passe (aucun autre test ne dépend de l'ancienne lecture).
- [ ] **Step 5:** `git commit -m "fix(episodes): lire les numeros d'episode a 3 ou 4 chiffres"`

### Task 2: Infohash renvoyé par `add()`

**Files:**
- Modify: `torsearch/transmission/client.py` (`AddedTorrent`, `add`)
- Modify: `torsearch/web/routes.py:196` (`/download` affiche `added.id`)
- Test: `tests/test_transmission.py`, `tests/test_transmission_contract.py`
- Modify (fakes `add` qui renvoient un int sous `/download`) : `tests/test_web.py`, `tests/test_cross_site_guard.py`, `tests/test_authz.py`, `tests/test_manual_link.py`, `tests/test_hidden_tracker_keys.py`

**Interfaces:**
- Produces: `class AddedTorrent(BaseModel): id: int; info_hash: str = ""` (hash en minuscules) ; `TransmissionClient.add(download_url, download_dir=None) -> AddedTorrent`.

- [ ] **Step 1: Tests rouges**

```python
# test_transmission.py — FakeRpc.add_torrent renvoie SimpleNamespace(id=42, hash_string="ABCDEF")
async def test_add_returns_torrent_id_and_passes_url():
    added = await tc.add("magnet:?xt=urn:btih:XYZ")
    assert added.id == 42
    assert added.info_hash == "abcdef"

# test_transmission_contract.py — Rpc.add_torrent renvoie déjà Torrent(fields={"id": 77, ..., "hashString": "ff"})
async def test_add_reads_the_hash_of_a_real_torrent():
    added = await _client([]).add("magnet:?xt=urn:btih:ff")
    assert (added.id, added.info_hash) == (77, "ff")
```

- [ ] **Step 2:** `pytest tests/test_transmission.py tests/test_transmission_contract.py -q` → échec (`int` n'a pas `.id`).
- [ ] **Step 3:** `add()` construit `AddedTorrent(id=torrent.id, info_hash=str(_field(torrent, "hash_string", "") or _field(torrent, "hashString", "")).lower())` ; `/download` : `added = await ctx.transmission.add(...)` puis `#{added.id}`. Les fakes web listés renvoient `AddedTorrent(id=<valeur actuelle>, info_hash="")`.
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(transmission): add() renvoie l'infohash du torrent ajoute"`

### Task 3: Registre des envois

**Files:**
- Create: `torsearch/monitor/grabs.py`
- Modify: `torsearch/main.py` (création + amorçage + passage à `MonitorRunner` et `create_app`)
- Modify: `torsearch/web/routes.py` (`create_app(..., grabs=None)` → `app.state.grabs`)
- Test: `tests/test_grabs.py`

**Interfaces:**
- Consumes: `MonitorRecord` (`torsearch.monitor.history`), `as_collection`.
- Produces:
  - `class GrabRecord(BaseModel): info_hash: str; title: str; origin: str  # "auto" | "manual"; target: str = ""; added_at: datetime`
  - `class GrabRegistry(source: Collection | Database | str | Path)` (collection `grabs`) avec `record(info_hash: str | None, title: str, origin: str, target: str = "", at: datetime | None = None) -> None`, `get(info_hash: str) -> GrabRecord | None`, `is_auto(info_hash: str | None) -> bool`, `forget(info_hash: str) -> None`, `seed_from_history(records: list[MonitorRecord]) -> int`.
  - `added_hash(added: object) -> str` : `info_hash` de l'objet renvoyé par `add()` en minuscules, `""` si absent (les fakes renvoient un int).

- [ ] **Step 1: Tests rouges** (`tests/test_grabs.py`)

```python
def test_record_and_is_auto_ignore_case(tmp_path):
    g = GrabRegistry(tmp_path / "g.db"); g.record("ABC", "T", "auto", "movie:1")
    assert g.is_auto("abc") and g.get("Abc").target == "movie:1"

def test_empty_hash_is_not_recorded(tmp_path):
    g = GrabRegistry(tmp_path / "g.db"); g.record("", "T", "auto"); g.record(None, "T", "auto")
    assert g.is_auto("") is False and g.is_auto(None) is False

def test_manual_entry_is_never_turned_auto(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    g.record("aa", "T", "manual"); g.record("aa", "T", "auto")
    g.record("bb", "T", "auto"); g.record("bb", "T", "manual")
    assert g.is_auto("aa") is False and g.is_auto("bb") is False

def test_forget(tmp_path):
    g = GrabRegistry(tmp_path / "g.db"); g.record("aa", "T", "auto"); g.forget("AA")
    assert g.get("aa") is None

def test_seed_from_history_only_auto_grabs_with_hash(tmp_path):
    recs = [_rec(kind="grabbed", infohash="H1", source="trk"),
            _rec(kind="grabbed", infohash="H2", source="manuel"),
            _rec(kind="grabbed", infohash=None, source="trk"),
            _rec(kind="found", infohash="H3", source="trk")]
    g = GrabRegistry(tmp_path / "g.db")
    assert g.seed_from_history(recs) == 1 and g.is_auto("h1")
    assert g.seed_from_history([_rec(kind="grabbed", infohash="H9", source="trk")]) == 0  # not empty

def test_added_hash():
    assert added_hash(AddedTorrent(id=1, info_hash="FF")) == "ff"
    assert added_hash(1) == "" and added_hash(None) == ""
```

- [ ] **Step 2:** `pytest tests/test_grabs.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3:** Implémenter `grabs.py` (patron de `library/blacklist.py`, id du document = hash en minuscules). `main.build_app` : `grabs = GrabRegistry(db.collection("grabs"))`, `grabs.seed_from_history(history.records())`, puis `grabs=grabs` à `create_app` (le passage à `MonitorRunner` arrive avec son paramètre, Task 4).
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(monitor): registre des envois par infohash (auto ou manuel)"`

### Task 4: Enregistrer chaque envoi

**Files:**
- Modify: `torsearch/monitor/runner.py` (`run_cycle`, `_grab_movie`, `run_movie_cycle`, `_grab_series_release`, `run_series_cycle`, `MonitorRunner.__init__/run_once`)
- Modify: `torsearch/web/routes.py` (`/download`)
- Test: `tests/test_monitor_runner.py`, `tests/test_manual_link.py` (ou `tests/test_web.py`)

**Interfaces:**
- Consumes: `GrabRegistry.record`, `added_hash` (Task 3), `AddedTorrent` (Task 2).
- Produces: paramètre optionnel `grabs: GrabRegistry | None = None` sur `run_cycle`, `run_movie_cycle`, `run_series_cycle` ; `MonitorRunner(..., grabs=None)` le passe aux trois cycles. Hash enregistré : `added_hash(added) or (pick.infohash or "")`. Cibles : `saved:<nom>`, `movie:<tmdb_id>`, `tv:<tmdb_id>`.

- [ ] **Step 1: Tests rouges**

```python
async def test_run_cycle_records_auto_grab_with_transmission_hash(tmp_path):
    # FakeTransmission.add renvoie AddedTorrent(id=1, info_hash="tthash")
    ... await run_cycle(cfg, FakeSearch([_r("Best", infohash="X")]), tr, history, grabs=g)
    assert g.get("tthash").origin == "auto" and g.get("tthash").target == "saved:s"

async def test_run_cycle_falls_back_to_tracker_hash(tmp_path):
    # FakeTransmission.add renvoie 1 (pas de hash)
    assert g.is_auto("x")

async def test_grab_without_any_hash_records_nothing(tmp_path):
    # add renvoie AddedTorrent(id=1, info_hash=""), résultat sans infohash
    assert g._c.count() == 0  # ou list vide via une méthode publique si ajoutée

async def test_movie_and_series_grabs_are_recorded_auto(tmp_path): ...  # target movie:<id> / tv:<id>

def test_manual_download_is_recorded_manual(tmp_path):
    # app.state.grabs = registre ; POST /download (admin) ; fake add → AddedTorrent(id=7, info_hash="mm")
    assert app.state.grabs.get("mm").origin == "manual"

async def test_history_keeps_tracker_infohash(tmp_path):
    # add renvoie un hash Transmission, le résultat n'en a pas : history.seen_keys("s") == {download_url}
```

- [ ] **Step 2:** `pytest tests/test_monitor_runner.py tests/test_manual_link.py -q` → échecs (`grabs` inconnu).
- [ ] **Step 3:** Chaque site d'envoi récupère `added = await transmission.add(...)` et, si `grabs` n'est pas `None`, appelle `grabs.record(...)` après un ajout réussi. `/download` fait de même avec `origin="manual"` via `getattr(request.app.state, "grabs", None)`.
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "feat(monitor): chaque envoi est inscrit au registre avec son origine"`

### Task 5: Purge restreinte et disjoncteur

**Files:**
- Create: `torsearch/monitor/stalled.py` (`handle_stalled_torrents`, `_same_release` déplacés, `DailyNotice`, `tracker_forgot_torrent`)
- Modify: `torsearch/monitor/runner.py` (suppression des deux fonctions, import depuis `stalled`, `MonitorRunner` passe `grabs` et sa `DailyNotice`)
- Modify: `tests/test_monitor_stalled_fallback.py` (import depuis `torsearch.monitor.stalled`, config `MonitorConfig(enabled=True)` + registre `auto` dans les tests existants)

**Interfaces:**
- Consumes: `GrabRegistry.is_auto`, `GrabRegistry.forget` (Task 3).
- Produces:
  - `handle_stalled_torrents(transmission, library=None, series_library=None, blacklist=None, notifier=None, config=None, now=None, history=None, grabs=None, notice: DailyNotice | None = None) -> list[str]` (noms purgés ; `[]` si `config` est `None`, surveillance inactive ou `grabs` est `None`).
  - `tracker_forgot_torrent(error_code: int, error_string: str) -> bool`.
  - `class DailyNotice` : `allow(today: date) -> bool` (vrai une fois par jour).
  - Constante `MAX_PURGES_PER_CYCLE = 3`.

- [ ] **Step 1: Tests rouges** (dans `tests/test_monitor_stalled_fallback.py` ; helper `_old(id, **kw)` = `TorrentInfo` ajouté il y a 3 h, helper `_auto(*hashes)` = registre)

```python
async def test_nothing_purged_when_monitor_disabled(...):      # MonitorConfig(enabled=False) → [] et removed == []
async def test_torrent_not_sent_by_surveillance_is_kept(...):   # registre vide → []
async def test_manual_download_is_kept(...):                     # registre "manual" → []
async def test_nothing_purged_without_registry(...):             # grabs=None → []
async def test_tracker_warning_does_not_purge(...):              # error_code=1, "Could not connect to tracker", 40 % → []
async def test_local_error_does_not_purge(...):                  # error_code=3, "No space left on device" → []
async def test_unregistered_torrent_is_purged(...):              # error_code=2, "Unregistered torrent" → purgé, forget(hash)
async def test_dead_auto_torrent_is_purged_and_forgotten(...):   # 0 %, 0 pair → purgé, registre vidé
async def test_paused_torrent_in_error_is_kept(...):             # status "stopped" + "Unregistered torrent" → []
async def test_three_candidates_are_purged(...):                 # 3 morts auto → 3 purgés
async def test_more_than_three_candidates_suspends_the_purge(...):
    # 4 morts auto → [] ; removed == [] ; une notification « Purge suspendue » (FakeNotifier.notify_message)
async def test_suspension_is_notified_once_a_day(...):           # deux appels même jour, même DailyNotice → 1 message

def test_tracker_forgot_torrent():
    assert tracker_forgot_torrent(2, "Unregistered torrent")
    assert tracker_forgot_torrent(2, "Torrent not registered with this tracker")
    assert tracker_forgot_torrent(1, "torrent introuvable")
    assert not tracker_forgot_torrent(3, "unregistered")
    assert not tracker_forgot_torrent(2, "Tracker returned 404 Not Found")
    assert not tracker_forgot_torrent(0, "")
```

Message de suspension (`notifier.notify_message(config.notifications, title, body)`) : titre `"Purge suspendue"`, corps `f"{n} torrents semblent bloques en meme temps (panne reseau ou VPN ?). Aucun n'a ete supprime."`.

- [ ] **Step 2:** `pytest tests/test_monitor_stalled_fallback.py -q` → échecs (module absent).
- [ ] **Step 3:** Déplacer les deux fonctions, puis : sortie immédiate si `config is None or not config.monitor.enabled or grabs is None` ; boucle 1 → liste des candidats (règles de la spec §3.3, dont `"stop" in status` → ignoré et `grabs.is_auto(t.info_hash)`) ; si `len(candidats) > MAX_PURGES_PER_CYCLE` → `logger.warning(...)`, notification si `notice is None or notice.allow(current_time.date())`, `return []` ; boucle 2 → étapes de purge actuelles + `grabs.forget(t.info_hash)`. `MonitorRunner` crée `self._purge_notice = DailyNotice()` et passe `grabs=self._grabs, notice=self._purge_notice`.
- [ ] **Step 4:** `pytest -q` → tout passe.
- [ ] **Step 5:** `git commit -m "fix(monitor): ne purger que les envois de la surveillance, morts de facon certaine"`

### Task 6: Liste noire dans Réglages → Maintenance

**Files:**
- Create: `torsearch/web/templates/partials/blacklist_list.html` (section `id="blacklist-section"`)
- Modify: `torsearch/web/templates/partials/settings_maintenance.html` (inclusion, avant « A propos »)
- Modify: `torsearch/web/settings_routes.py` (contexte de `/settings`, `POST /settings/blacklist/remove`)
- Test: `tests/test_settings_web.py`

**Interfaces:**
- Consumes: `Blacklist.list()`, `Blacklist.remove(key)` (existants), `app.state.blacklist`.
- Produces: `POST /settings/blacklist/remove` (form `key` = infohash sinon titre) → partial `blacklist_list.html` ; libellés `{"torrent_error": "Erreur tracker", "torrent_stalled": "Bloque", "failed_download": "Echec de telechargement"}` (autre motif affiché tel quel), entrées triées de la plus récente à la plus ancienne. Chaque ligne : un `<form hx-post hx-target="#blacklist-section" hx-swap="outerHTML">` avec `<input type="hidden" name="key">`. Liste vide : « Aucune release en liste noire. »

- [ ] **Step 1: Tests rouges**

```python
def test_maintenance_lists_blacklisted_releases(tmp_path):
    bl = Blacklist(tmp_path / "bl.db"); bl.add("aa", "Some.Release.1080p", reason="torrent_stalled")
    client = TestClient(create_app(ctx, blacklist=bl))
    page = client.get("/settings").text
    assert "Some.Release.1080p" in page and "Bloque" in page

def test_blacklist_remove_by_hash(tmp_path):     # POST key="aa" → plus listé, bl.is_blacklisted("aa", "Some.Release.1080p") is False
def test_blacklist_remove_title_with_slash_and_quote(tmp_path):
    bl.add(None, "AC/DC l'integrale été", reason="failed_download")
    client.post("/settings/blacklist/remove", data={"key": "AC/DC l'integrale été"})
    assert bl.list() == []
def test_blacklist_remove_requires_admin(tmp_path):  # app avec auth, session membre → 403 (patron de tests/test_authz.py)
```

- [ ] **Step 2:** `pytest tests/test_settings_web.py -q` → échecs.
- [ ] **Step 3:** Implémenter route + partial (sans accents, sans JS inline, classes Tailwind des sections voisines).
- [ ] **Step 4:** `pytest -q` (dont `test_no_inline_js.py`) → tout passe.
- [ ] **Step 5:** `git commit -m "feat(settings): liste noire visible et retrait d'une release"`

### Task 7: Version et documentation

**Files:**
- Modify: `pyproject.toml`, `torsearch/__init__.py` (`0.9.0`)
- Modify: `AGENTS.md` (§2 : entrée « Chantier 10 (v0.9.0) » en tête, compte de tests ; §4 : `monitor/stalled.py`, `monitor/grabs.py` ; §8 : retirer les petits chantiers déjà faits — masquage console, liens sans clé)

- [ ] **Step 1:** Mettre à jour les fichiers.
- [ ] **Step 2:** `ruff check torsearch tests && mypy && pytest -q` → tout vert ; noter le nombre de tests dans AGENTS.md.
- [ ] **Step 3:** `git commit -m "chore(release): chantier 10 purge sure (v0.9.0)"`
