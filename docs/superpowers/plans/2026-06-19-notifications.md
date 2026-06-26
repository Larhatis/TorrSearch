# Notifications — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notifier l'utilisateur (Discord / ntfy / Telegram / webhook) quand la surveillance grabbe ou trouve un résultat ; canaux configurables dans Réglages avec un bouton « Tester ».

**Architecture:** Un modèle `NotificationChannel` dans `Config` (persisté via SettingsStore). Un `Notifier` httpx async qui formate un message et le POST au bon format selon le type, tolérant aux pannes. `run_cycle` reçoit un `notifier` optionnel et l'appelle pour chaque `MonitorRecord` créé. Une section Notifications sur `/settings` (même patron HTMX que les trackers).

**Tech Stack:** Python 3.12+ (3.14 local) · httpx + respx · Pydantic v2 (frozen) · FastAPI + HTMX · pytest (asyncio auto).

**Base :** branche `feat/notifications` (sur `main`). Commandes via `.venv/bin/python -m pytest ...`. Code réutilisé : `torsearch/config.py` (modèles frozen, `Config`, `ConfigDict`, `Field`), `torsearch/settings/mutations.py` (`SettingsError`, `model_copy`, patron des mutations), `torsearch/monitor/history.py` (`MonitorRecord` : `search,title,source,infohash,download_url,kind,at`), `torsearch/monitor/runner.py` (`run_cycle(config, search_service, transmission, history)`, `MonitorRunner(ctx, history)`), `torsearch/web/settings_routes.py` (`settings_router`, `settings_page` rendant `settings.html` avec `{config, indexers}`, helpers `_toast`/`_list`), `torsearch/web/templates/settings.html` (sections général + trackers). Starlette : `templates.TemplateResponse(request, "name.html", {ctx})`.

---

## File Structure

| Fichier | Action |
|---|---|
| `torsearch/config.py` | Modifier — `NotificationChannel` + `Config.notifications`. |
| `torsearch/settings/mutations.py` | Modifier — `add_channel`/`remove_channel`/`set_channel_enabled`. |
| `torsearch/notifications/__init__.py` | Créer (vide). |
| `torsearch/notifications/notifier.py` | Créer — `format_record`, `Notifier`. |
| `torsearch/monitor/runner.py` | Modifier — `run_cycle(..., notifier=None)` + `MonitorRunner`. |
| `torsearch/web/settings_routes.py` | Modifier — routes notifications + `channels` au contexte. |
| `torsearch/web/templates/settings.html` | Modifier — section Notifications. |
| `torsearch/web/templates/partials/notification_list.html` | Créer. |
| `tests/test_config.py`, `tests/test_settings_mutations.py`, `tests/test_monitor_runner.py`, `tests/test_settings_web.py` | Modifier. |
| `tests/test_notifier.py` | Créer. |

---

## Task 1: Modèle NotificationChannel

**Files:**
- Modify: `torsearch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_config.py`)**

```python
def test_notification_channel_defaults():
    from torsearch.config import NotificationChannel
    ch = NotificationChannel(name="d", type="discord", url="https://x")
    assert ch.enabled is True
    assert ch.token == "" and ch.chat_id == ""


def test_config_round_trips_notifications():
    from torsearch.config import Config, NotificationChannel
    cfg = Config(notifications=[NotificationChannel(name="d", type="discord", url="https://x")])
    again = Config.model_validate_json(cfg.model_dump_json())
    assert again.notifications[0].name == "d"
    assert again.notifications[0].type == "discord"
    assert Config().notifications == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -k notification -v`
Expected: FAIL — `ImportError: cannot import name 'NotificationChannel'`.

- [ ] **Step 3: Add the model to `torsearch/config.py`**

Add this class (near `MonitorConfig`):
```python
class NotificationChannel(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    type: str  # discord | ntfy | telegram | webhook
    url: str = ""
    token: str = ""
    chat_id: str = ""
    enabled: bool = True
```
Add this field to `Config`:
```python
    notifications: list[NotificationChannel] = Field(default_factory=list)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (new + pre-existing).

- [ ] **Step 5: Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add NotificationChannel config model"
```

---

## Task 2: Mutations des canaux

**Files:**
- Modify: `torsearch/settings/mutations.py`
- Test: `tests/test_settings_mutations.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_settings_mutations.py`)**

```python
def test_add_channel_and_reject_duplicate():
    from torsearch.config import NotificationChannel
    from torsearch.settings.mutations import add_channel
    cfg = Config()
    cfg2 = add_channel(cfg, NotificationChannel(name="d", type="discord", url="https://x"))
    assert [c.name for c in cfg2.notifications] == ["d"]
    assert cfg.notifications == []
    with pytest.raises(SettingsError):
        add_channel(cfg2, NotificationChannel(name="d", type="ntfy", url="https://y"))


def test_remove_and_toggle_channel():
    from torsearch.config import NotificationChannel
    from torsearch.settings.mutations import remove_channel, set_channel_enabled
    cfg = Config(notifications=[NotificationChannel(name="d", type="discord", url="https://x", enabled=True)])
    assert set_channel_enabled(cfg, "d", False).notifications[0].enabled is False
    assert remove_channel(cfg, "d").notifications == []
    with pytest.raises(SettingsError):
        remove_channel(cfg, "nope")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_mutations.py -k channel -v`
Expected: FAIL — `ImportError: cannot import name 'add_channel'`.

- [ ] **Step 3: Append to `torsearch/settings/mutations.py`**

Extend the `from torsearch.config import ...` line to also import `NotificationChannel`. Append:
```python
def _channel_index(config: Config, name: str) -> int:
    for i, ch in enumerate(config.notifications):
        if ch.name == name:
            return i
    return -1


def add_channel(config: Config, channel: NotificationChannel) -> Config:
    if _channel_index(config, channel.name) != -1:
        raise SettingsError(f"Un canal nommé « {channel.name} » existe déjà.")
    return config.model_copy(update={"notifications": [*config.notifications, channel]})


def remove_channel(config: Config, name: str) -> Config:
    if _channel_index(config, name) == -1:
        raise SettingsError(f"Canal introuvable : « {name} ».")
    return config.model_copy(
        update={"notifications": [c for c in config.notifications if c.name != name]}
    )


def set_channel_enabled(config: Config, name: str, enabled: bool) -> Config:
    idx = _channel_index(config, name)
    if idx == -1:
        raise SettingsError(f"Canal introuvable : « {name} ».")
    new = list(config.notifications)
    new[idx] = new[idx].model_copy(update={"enabled": enabled})
    return config.model_copy(update={"notifications": new})
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_settings_mutations.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add torsearch/settings/mutations.py tests/test_settings_mutations.py
git commit -m "feat: add notification channel mutations"
```

---

## Task 3: Notifier

**Files:**
- Create: `torsearch/notifications/__init__.py` (empty), `torsearch/notifications/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing test**

`tests/test_notifier.py`:
```python
from datetime import datetime, timezone

import httpx
import respx

from torsearch.config import NotificationChannel
from torsearch.monitor.history import MonitorRecord
from torsearch.notifications.notifier import Notifier, format_record


def _record(kind="grabbed"):
    return MonitorRecord(search="MaSerie", title="Show.S02E01.1080p", source="tracker1",
                         infohash="H", download_url="magnet:?xt=urn:btih:H", kind=kind,
                         at=datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_format_record_grabbed_and_found():
    _, body = format_record(_record("grabbed"))
    assert "grabbé" in body and "MaSerie" in body and "Show.S02E01.1080p" in body
    _, body2 = format_record(_record("found"))
    assert "trouvé" in body2


async def test_send_discord_posts_content():
    ch = NotificationChannel(name="d", type="discord", url="https://discord/webhook")
    with respx.mock:
        route = respx.post("https://discord/webhook").mock(return_value=httpx.Response(204))
        await Notifier().notify([ch], _record())
    assert b"content" in route.calls.last.request.content


async def test_send_ntfy_posts_body_with_title_header():
    ch = NotificationChannel(name="n", type="ntfy", url="https://ntfy.sh/mytopic")
    with respx.mock:
        route = respx.post("https://ntfy.sh/mytopic").mock(return_value=httpx.Response(200))
        await Notifier().notify([ch], _record())
    req = route.calls.last.request
    assert req.headers.get("Title") is not None
    assert b"grab" in req.content


async def test_send_telegram_calls_bot_api():
    ch = NotificationChannel(name="t", type="telegram", token="BOT123", chat_id="42")
    with respx.mock:
        route = respx.post("https://api.telegram.org/botBOT123/sendMessage").mock(return_value=httpx.Response(200))
        await Notifier().notify([ch], _record())
    assert b"42" in route.calls.last.request.content


async def test_send_webhook_posts_title_and_message():
    ch = NotificationChannel(name="w", type="webhook", url="https://my/hook")
    with respx.mock:
        route = respx.post("https://my/hook").mock(return_value=httpx.Response(200))
        await Notifier().notify([ch], _record())
    body = route.calls.last.request.content
    assert b"title" in body and b"message" in body


async def test_notify_skips_disabled_and_survives_failure():
    good = NotificationChannel(name="good", type="webhook", url="https://good/hook")
    bad = NotificationChannel(name="bad", type="webhook", url="https://bad/hook")
    off = NotificationChannel(name="off", type="webhook", url="https://off/hook", enabled=False)
    with respx.mock:
        g = respx.post("https://good/hook").mock(return_value=httpx.Response(200))
        respx.post("https://bad/hook").mock(return_value=httpx.Response(500))
        o = respx.post("https://off/hook").mock(return_value=httpx.Response(200))
        await Notifier().notify([good, bad, off], _record())  # must not raise
    assert g.called
    assert not o.called


async def test_test_returns_ok_then_error():
    ch = NotificationChannel(name="d", type="discord", url="https://discord/webhook")
    with respx.mock:
        respx.post("https://discord/webhook").mock(return_value=httpx.Response(204))
        ok, msg = await Notifier().test(ch)
    assert ok is True and msg == "OK"
    with respx.mock:
        respx.post("https://discord/webhook").mock(return_value=httpx.Response(500))
        ok2, _ = await Notifier().test(ch)
    assert ok2 is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_notifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.notifications'`.

- [ ] **Step 3: Write the implementation**

Create empty `torsearch/notifications/__init__.py`.

`torsearch/notifications/notifier.py`:
```python
from __future__ import annotations

import logging

import httpx

from torsearch.config import NotificationChannel
from torsearch.monitor.history import MonitorRecord

logger = logging.getLogger(__name__)

_TITLE = "TorrSearch — surveillance"


def format_record(record: MonitorRecord) -> tuple[str, str]:
    kind = "grabbé" if record.kind == "grabbed" else "trouvé"
    body = f"{kind} · {record.search} : {record.title} ({record.source})"
    return _TITLE, body


class Notifier:
    def __init__(self, client_factory=httpx.AsyncClient, timeout: float = 10.0):
        self._client_factory = client_factory
        self._timeout = timeout

    async def _send_one(self, client, channel: NotificationChannel, title: str, body: str) -> None:
        if channel.type == "discord":
            response = await client.post(channel.url, json={"content": f"{title}\n{body}"})
        elif channel.type == "ntfy":
            response = await client.post(channel.url, content=body.encode("utf-8"), headers={"Title": title})
        elif channel.type == "telegram":
            url = f"https://api.telegram.org/bot{channel.token}/sendMessage"
            response = await client.post(url, json={"chat_id": channel.chat_id, "text": f"{title}\n{body}"})
        elif channel.type == "webhook":
            response = await client.post(channel.url, json={"title": title, "message": body})
        else:
            return
        response.raise_for_status()

    async def notify(self, channels: list[NotificationChannel], record: MonitorRecord) -> None:
        active = [c for c in channels if c.enabled]
        if not active:
            return
        title, body = format_record(record)
        client = self._client_factory(timeout=self._timeout)
        try:
            for channel in active:
                try:
                    await self._send_one(client, channel, title, body)
                except Exception as exc:
                    logger.warning("Notification to '%s' failed: %s", channel.name, exc)
        finally:
            await client.aclose()

    async def test(self, channel: NotificationChannel) -> tuple[bool, str]:
        client = self._client_factory(timeout=self._timeout)
        try:
            await self._send_one(client, channel, _TITLE, "Notification de test depuis TorrSearch ✅")
            return True, "OK"
        except httpx.HTTPError as exc:
            return False, f"Echec : {exc}"
        finally:
            await client.aclose()
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_notifier.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/notifications/__init__.py torsearch/notifications/notifier.py tests/test_notifier.py
git commit -m "feat: add multi-channel notifier (discord/ntfy/telegram/webhook)"
```

---

## Task 4: Brancher les notifs sur la surveillance

**Files:**
- Modify: `torsearch/monitor/runner.py`
- Test: `tests/test_monitor_runner.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_monitor_runner.py`)**

```python
class FakeNotifier:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    async def notify(self, channels, record):
        self.calls.append((channels, record))
        if self._fail:
            raise RuntimeError("notif boom")


async def test_run_cycle_notifies_on_record(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="notify")])
    notifier = FakeNotifier()
    await run_cycle(cfg, FakeSearch([_r("Found", infohash="Y")]), FakeTransmission(), history, notifier)
    assert len(notifier.calls) == 1
    assert notifier.calls[0][1].title == "Found"


async def test_run_cycle_survives_notifier_error(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="auto")])
    created = await run_cycle(cfg, FakeSearch([_r("Best", infohash="X")]), FakeTransmission(), history, FakeNotifier(fail=True))
    assert [r.kind for r in created] == ["grabbed"]  # record created despite notif failure
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_monitor_runner.py -k notif -v`
Expected: FAIL — `run_cycle()` takes no `notifier` argument.

- [ ] **Step 3: Update `torsearch/monitor/runner.py`**

Add the import near the top:
```python
from torsearch.notifications.notifier import Notifier
```
Change the `run_cycle` signature to accept `notifier=None`:
```python
async def run_cycle(config, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
```
Inside the loop, **after** `history.add(record)` and `created.append(record)`, add:
```python
        if notifier is not None:
            try:
                await notifier.notify(config.notifications, record)
            except Exception as exc:
                logger.warning("Notification for '%s' failed: %s", saved.name, exc)
```
Update `MonitorRunner` to build and pass a `Notifier`:
```python
class MonitorRunner:
    def __init__(self, ctx, history, notifier=None):
        self._ctx = ctx
        self._history = history
        self._notifier = notifier or Notifier()
        self._task = None
```
and in `_loop`, pass it:
```python
                await run_cycle(
                    self._ctx.config, self._ctx.search_service, self._ctx.transmission,
                    self._history, self._notifier,
                )
```
(Keep the rest of `start`/`stop`/`_loop` unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_monitor_runner.py -v`
Expected: PASS — the 2 new tests + all pre-existing runner tests (which call `run_cycle` without `notifier`, still valid).

- [ ] **Step 5: Commit**

```bash
git add torsearch/monitor/runner.py tests/test_monitor_runner.py
git commit -m "feat: trigger notifications from the surveillance cycle"
```

---

## Task 5: Section Notifications sur /settings

**Files:**
- Modify: `torsearch/web/settings_routes.py`, `torsearch/web/templates/settings.html`
- Create: `torsearch/web/templates/partials/notification_list.html`
- Test: `tests/test_settings_web.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_settings_web.py`)**

```python
import httpx
import respx

from torsearch.config import NotificationChannel


def test_settings_page_shows_notifications_section(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Notifications" in resp.text


def test_add_notification_channel(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/settings/notifications", data={"name": "myd", "type": "discord", "url": "https://discord/wh"})
    assert resp.status_code == 200
    assert "myd" in resp.text
    assert [c.name for c in ctx.config.notifications] == ["myd"]


def test_toggle_and_delete_notification(tmp_path):
    cfg = Config(notifications=[NotificationChannel(name="c", type="webhook", url="https://x", enabled=True)])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/settings/notifications/c/toggle")
    assert ctx.config.notifications[0].enabled is False
    client.post("/settings/notifications/c/delete")
    assert ctx.config.notifications == []


def test_test_notification_channel(tmp_path):
    cfg = Config(notifications=[NotificationChannel(name="d", type="discord", url="https://discord/wh")])
    client, _, _ = _client(tmp_path, cfg)
    with respx.mock:
        respx.post("https://discord/wh").mock(return_value=httpx.Response(204))
        resp = client.post("/settings/notifications/d/test")
    assert resp.status_code == 200
    assert "OK" in resp.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_web.py -k notif -v`
Expected: FAIL — `404` for `/settings/notifications` and "Notifications" not in the page.

- [ ] **Step 3: Add the notifications routes + context in `torsearch/web/settings_routes.py`**

Extend the imports: add `NotificationChannel` to the `from torsearch.config import ...` line, add
`from torsearch.notifications.notifier import Notifier`, and add `add_channel, remove_channel,
set_channel_enabled` to the `from torsearch.settings.mutations import (...)` line.

In `settings_page`, add `"channels": ctx.config.notifications` to the context dict passed to
`settings.html`.

Add a helper and the routes:
```python
def _notif_list(request: Request, ctx: AppContext, error: str | None = None, notice: str | None = None):
    return templates.TemplateResponse(
        request, "partials/notification_list.html",
        {"channels": ctx.config.notifications, "error": error, "notice": notice},
    )


@settings_router.post("/settings/notifications", response_class=HTMLResponse)
async def add_notification(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    url: str = Form(""),
    token: str = Form(""),
    chat_id: str = Form(""),
):
    ctx: AppContext = request.app.state.ctx
    try:
        channel = NotificationChannel(name=name, type=type, url=url, token=token, chat_id=chat_id)
        ctx.update_settings(add_channel(ctx.config, channel))
        return _notif_list(request, ctx, notice=f"Canal « {name} » ajoute.")
    except (ValidationError, SettingsError) as exc:
        return _notif_list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/notifications/{name}/toggle", response_class=HTMLResponse)
async def toggle_notification(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((c for c in ctx.config.notifications if c.name == name), None)
    try:
        ctx.update_settings(set_channel_enabled(ctx.config, name, not current.enabled if current else True))
        return _notif_list(request, ctx)
    except SettingsError as exc:
        return _notif_list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/notifications/{name}/delete", response_class=HTMLResponse)
async def delete_notification(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_channel(ctx.config, name))
        return _notif_list(request, ctx, notice=f"Canal « {name} » supprime.")
    except SettingsError as exc:
        return _notif_list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/notifications/{name}/test", response_class=HTMLResponse)
async def test_notification(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    channel = next((c for c in ctx.config.notifications if c.name == name), None)
    if channel is None:
        return _toast(request, False, "Canal introuvable.")
    ok, message = await Notifier().test(channel)
    return _toast(request, ok, f"{name} : {message}")
```

- [ ] **Step 4: Create the notifications list partial**

`torsearch/web/templates/partials/notification_list.html`:
```html
<div id="notification-list">
  {% if error %}<div class="mb-3 rounded bg-red-600 px-3 py-2 text-sm">{{ error }}</div>{% endif %}
  {% if notice %}<div class="mb-3 rounded bg-emerald-600 px-3 py-2 text-sm">{{ notice }}</div>{% endif %}
  {% for ch in channels %}
  <div class="flex items-center gap-3 border-b border-slate-800 py-2 text-sm">
    <span class="font-medium">{{ ch.name }}</span>
    <span class="rounded bg-slate-700 px-2 py-0.5 text-xs">{{ ch.type }}</span>
    <span class="ml-auto"></span>
    <button type="button" hx-post="/settings/notifications/{{ ch.name }}/test" hx-target="#toast"
            class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs">Tester</button>
    <button type="button" hx-post="/settings/notifications/{{ ch.name }}/toggle" hx-target="#notification-list" hx-swap="outerHTML"
            class="rounded {% if ch.enabled %}bg-amber-600{% else %}bg-slate-600{% endif %} px-2 py-1 text-xs">
      {{ "Desactiver" if ch.enabled else "Activer" }}</button>
    <button type="button" hx-post="/settings/notifications/{{ ch.name }}/delete" hx-target="#notification-list" hx-swap="outerHTML"
            class="rounded bg-red-700 px-2 py-1 text-xs">Supprimer</button>
  </div>
  {% else %}
  <p class="text-slate-400 text-sm">Aucun canal de notification.</p>
  {% endfor %}
</div>
```

- [ ] **Step 5: Add the Notifications section to `settings.html`**

In `torsearch/web/templates/settings.html`, add this section just before the final `{% endblock %}`
(after the existing Trackers section):
```html
<section class="mt-10">
  <h2 class="font-semibold mb-2">Notifications</h2>
  <form hx-post="/settings/notifications" hx-target="#notification-list" hx-swap="outerHTML"
        class="flex flex-wrap items-end gap-2 mb-4">
    <input name="name" placeholder="Nom" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
    <select name="type" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
      <option value="discord">Discord</option>
      <option value="ntfy">ntfy</option>
      <option value="telegram">Telegram</option>
      <option value="webhook">Webhook</option>
    </select>
    <input name="url" placeholder="URL (Discord / ntfy / webhook)" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-72">
    <input name="token" placeholder="Token (Telegram)" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
    <input name="chat_id" placeholder="Chat id (Telegram)" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-28">
    <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1 text-sm">Ajouter</button>
  </form>
  {% include "partials/notification_list.html" %}
</section>
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — the 4 new settings tests + everything pre-existing.

- [ ] **Step 7: Commit**

```bash
git add torsearch/web/settings_routes.py torsearch/web/templates/settings.html torsearch/web/templates/partials/notification_list.html tests/test_settings_web.py
git commit -m "feat: configure notification channels from settings with test button"
```

---

## Notes de vérification finale (manuel, hors TDD)

1. Lancer l'app, aller dans **Réglages → Notifications**, ajouter un canal (ex. un webhook
   Discord), cliquer **Tester** → un message doit arriver dans le salon Discord.
2. Activer la surveillance avec une recherche en mode `notify`, et au prochain résultat trouvé,
   vérifier qu'une notification arrive (et que l'historique se remplit toujours).
3. Couper le canal (URL invalide) → la surveillance continue de tourner sans planter (la notif
   échoue silencieusement, c'est loggé).
