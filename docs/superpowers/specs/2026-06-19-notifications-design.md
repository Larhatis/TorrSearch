# Notifications — Spec de conception

> Date : 2026-06-19
> Statut : approuvé (carte blanche), en implémentation
> Construit sur l'état actuel de `main` (surveillance F2 incluse).

## 1. Contexte & objectif

La surveillance (F2) tourne en fond mais l'utilisateur doit ouvrir l'app pour savoir ce qui
s'est passé. **Objectif :** envoyer une **notification** (Discord / ntfy / Telegram / webhook
générique) quand la surveillance **grabbe** ou **trouve** un résultat — pour être prévenu sans
ouvrir l'app.

## 2. Décisions (brainstorming)

| Sujet | Décision |
|---|---|
| Canaux | **4** : Discord (webhook), ntfy, Telegram (bot), webhook générique. Plusieurs configurables en même temps. |
| Événements | **Grabbé + trouvé** (les deux). Une notif par `MonitorRecord` créé. |
| Emplacement UI | Section **« Notifications » sur la page Réglages** (`/settings`). |
| Robustesse | Un canal qui échoue est loggé et **n'interrompt jamais** la surveillance ni les autres canaux. |

## 3. Périmètre

### Dans ce lot (in scope)

- Modèle **`NotificationChannel`** (dans `Config`, persisté dans `data/settings.json`) :
  `name`, `type` (`discord`/`ntfy`/`telegram`/`webhook`), `url`, `token`, `chat_id`, `enabled`.
- Un **`Notifier`** (httpx async) qui formate un message et le POST au bon format selon le type.
- **Déclenchement** depuis la surveillance : chaque `MonitorRecord` créé (grabbé/trouvé) envoie
  une notif à tous les canaux activés.
- Section **Notifications** sur `/settings` : ajouter / supprimer / activer-désactiver un canal,
  **+ bouton « Tester »** (envoie une notif de test pour valider l'URL/token).

### Hors périmètre

Notif sur téléchargements manuels · templates de message personnalisables · retries/backoff ·
notif sur erreurs (tracker down, etc.).

## 4. Architecture

### 4.1 Modèle (`torsearch/config.py`)

`NotificationChannel` (frozen, comme les autres modèles de config) :
`name: str`, `type: str` (∈ `discord|ntfy|telegram|webhook`), `url: str = ""`,
`token: str = ""`, `chat_id: str = ""`, `enabled: bool = True`.
Ajout à `Config` : `notifications: list[NotificationChannel] = []`.

Champs utiles selon le type : Discord/ntfy/webhook → `url` ; Telegram → `token` + `chat_id`.

### 4.2 Mutations (`torsearch/settings/mutations.py`)

Pures, frozen-safe, erreurs via `SettingsError` :
`add_channel` (refus doublon de `name`), `remove_channel`, `set_channel_enabled`.

### 4.3 Notifier (`torsearch/notifications/notifier.py`)

- `format_record(record: MonitorRecord) -> tuple[str, str]` : `(title, body)`, ex.
  title `"TorrSearch — surveillance"`, body
  `"grabbé · Ma Série : Great.Show.S02E01.1080p (tracker1)"` (`grabbé`/`trouvé` selon `record.kind`).
- `Notifier` (httpx async, `client_factory` injectable pour les tests) :
  - `async send(channel, title, body)` : POST selon `channel.type` —
    - **discord** → `POST url` `json={"content": f"{title}\n{body}"}`
    - **ntfy** → `POST url` corps = `body`, header `Title: {title}`
    - **telegram** → `POST https://api.telegram.org/bot{token}/sendMessage` `json={"chat_id", "text"}`
    - **webhook** → `POST url` `json={"title", "message", "event": record.kind?}` *(payload générique : `title`, `message`)*
    - `raise_for_status()` ; un type inconnu est ignoré.
  - `async notify(channels, record)` : `format_record` puis `send` sur chaque canal **activé**,
    chaque envoi en `try/except` (log, jamais propagé).
  - `async test(channel) -> tuple[bool, str]` : envoie un message de test
    (`"Notification de test depuis TorrSearch ✅"`) → `(True, "OK")` ou `(False, raison)`.

### 4.4 Intégration surveillance (`torsearch/monitor/runner.py`)

- `run_cycle(config, search_service, transmission, history, notifier=None)` : après
  `history.add(record)`, si `notifier is not None`, `await notifier.notify(config.notifications, record)`
  en `try/except` (une notif qui casse n'arrête pas le cycle). Le paramètre par défaut `None`
  garde les tests existants inchangés.
- `MonitorRunner` : construit un `Notifier` et le passe à `run_cycle` dans `_loop`.

### 4.5 Web (`torsearch/web/settings_routes.py` + `settings.html`)

Nouvelle section **Notifications** sur `/settings` (même patron HTMX que les trackers) :

| Méthode & route | Effet |
|---|---|
| `POST /settings/notifications` | `add_channel(...)` (name, type, url, token, chat_id). |
| `POST /settings/notifications/{name}/toggle` | `set_channel_enabled(...)`. |
| `POST /settings/notifications/{name}/delete` | `remove_channel(...)`. |
| `POST /settings/notifications/{name}/test` | `Notifier.test(channel)` → toast ✅/❌. |

La liste des canaux est un partial `partials/notification_list.html` (cible `#notification-list`).
La page `/settings` passe `config.notifications` au template.

## 5. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Un canal échoue à l'envoi | Loggé ; les autres canaux et la surveillance continuent. |
| `notifier=None` (tests surveillance) | Aucune notif ; comportement identique à avant. |
| Saisie invalide / nom en double (UI) | Bannière d'erreur, rien sauvegardé (comme le reste de /settings). |
| Test d'un canal qui échoue | Toast ❌ avec la raison (HTTP, timeout…). |

## 6. Tests (pytest, hors-ligne via respx)

- **mutations** : add (+ refus doublon), remove, toggle — sans muter l'entrée.
- **`format_record`** : titre/corps corrects pour `grabbed` et `found`.
- **`Notifier.send`** par type (respx) : Discord poste `content`, ntfy poste le corps + header `Title`,
  Telegram appelle l'URL `bot{token}/sendMessage` avec `chat_id`/`text`, webhook poste `title`/`message`.
- **`Notifier.notify`** : envoie à tous les canaux **activés**, saute les désactivés, un canal qui
  lève n'empêche pas les autres.
- **`Notifier.test`** : OK sur 200, erreur sur échec HTTP.
- **`run_cycle`** avec un faux notifier : un record créé déclenche `notify(config.notifications, record)` ;
  un notifier qui lève n'interrompt pas le cycle.
- **Web /settings** : section Notifications rendue ; add/toggle/delete mettent à jour `ctx.config.notifications` ;
  `test` renvoie le bon toast (Notifier mocké via respx).

## 7. Fichiers

| Fichier | Action |
|---|---|
| `torsearch/config.py` | Modifier — `NotificationChannel` + champ `Config`. |
| `torsearch/settings/mutations.py` | Modifier — mutations canaux. |
| `torsearch/notifications/__init__.py` | Créer (vide). |
| `torsearch/notifications/notifier.py` | Créer — `format_record`, `Notifier`. |
| `torsearch/monitor/runner.py` | Modifier — `run_cycle(..., notifier=None)` + `MonitorRunner`. |
| `torsearch/web/settings_routes.py` | Modifier — routes notifications. |
| `torsearch/web/templates/settings.html` + `partials/notification_list.html` | Modifier/créer. |
| `tests/test_settings_mutations.py`, `tests/test_monitor_runner.py`, `tests/test_settings_web.py` | Modifier. |
| `tests/test_notifier.py` | Créer. |

## 8. Notes

- Aucun secret codé en dur : URLs de webhook / tokens saisis dans l'UI, persistés dans `data/`
  (gitignoré). Le bouton « Tester » évite de deviner si la config est bonne.
- Le `Notifier` est **sans état** (peut être instancié à la volée par le runner et par la route
  de test) ; injection de `client_factory` pour des tests 100 % hors-ligne.
