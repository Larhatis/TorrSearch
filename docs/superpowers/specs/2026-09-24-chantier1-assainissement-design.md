# Chantier 1 — Assainissement sécurité & fiabilité

Date : 2026-09-24

Premier des 4 chantiers de la refonte décidée après l'audit du 2026-09-24 :
**1 assainissement** → 2 moteur de décision → 3 suivi des téléchargements → 4 refonte UI.

## Objectif

Corriger les défauts de sécurité et de fiabilité constatés à l'audit, sans changer le
périmètre fonctionnel ni le modèle de données. Chaque défaut est d'abord reproduit par un
test rouge, puis corrigé.

## Défauts constatés

| # | Défaut | Preuve |
|---|---|---|
| D1 | Un utilisateur supprimé ou rétrogradé garde ses droits jusqu'à expiration du cookie (14 j) : `AuthMiddleware` ne vérifie que la présence de `session["user"]`, et `effective_role` lit `session["role"]`. | Script : après `users.remove("bob")`, `/search` et `/downloads` répondent toujours 200 avec son cookie. |
| D2 | XSS : dans `onclick="…('{{ valeur }}')"`, Jinja échappe `'` en `&#39;`, que le navigateur redécode avant d'exécuter le JS. Vecteurs : `download_url` (flux Torznab) et `quality` (paramètre d'URL de `/search`, affiché dans une puce de filtre). | Rendu Jinja de `x');alert(document.domain)//` ; `partials/results.html:24` et `:50`. |
| D3 | `transmission_rpc` est synchrone (délai max 30 s ; le constructeur fait déjà un appel réseau) et appelé directement dans du code async : si Transmission ne répond pas, tout l'event loop est bloqué. `/downloads/list` est rappelé toutes les 3 s. | 9 appels directs dans `web/routes.py`, `web/downloads_routes.py`, `monitor/runner.py`. |
| D4 | La page Réglages réaffiche les secrets dans le HTML : mot de passe Transmission, passkeys, clé Jellyfin. | `settings.html:42` et `:126`, `partials/indexer_row.html:8`. |
| D5 | Derrière un reverse proxy, `request.client.host` vaut l'IP du proxy : 5 échecs de connexion de n'importe qui bloquent tout le monde. | uvicorn ne fait confiance qu'à `127.0.0.1` par défaut (`FORWARDED_ALLOW_IPS`). |
| D6 | `POST /surveillance/monitor` reconstruit `MonitorConfig` sans `regrab_hours`, qui revient à 48 h. | `web/surveillance_routes.py:68`. |
| D7 | Les helpers de formulaire (`_to_int`, `_to_size_bytes`, `_GB`) sont dupliqués. | `web/routes.py`, `web/surveillance_routes.py`. |
| D8 | Un nom de tracker, de recherche ou de canal contenant `/`, `?`, `#` ou `%` rend ses URLs d'édition inutilisables (les noms servent d'identifiants dans les chemins). | `hx-post="/settings/indexers/{{ ix.name }}"`, etc. |
| D9 | Templates non déclarés comme données du paquet : l'image Docker ne fonctionne que parce qu'elle importe `torsearch` depuis les sources (`/app`). | `torsearch.egg-info/SOURCES.txt` ne liste aucun template. |

## Conception

### 1. Révocation des sessions (D1)

Dans `AuthMiddleware.dispatch`, pour une requête protégée (auth activée, chemin non public)
dont la session contient un `user` :

- l'utilisateur est relu avec `users.get(username)` (`users` = `request.app.state.users`) ;
- **trouvé** → son rôle **en base** est placé dans `request.state.role`, la requête continue ;
- **introuvable et store vide ou absent** (mode identifiant unique par variables
  d'environnement) → comportement actuel : la requête continue, le rôle reste celui de la
  session ;
- **introuvable et store non vide** → `request.session.clear()`, puis même réponse qu'à un
  visiteur non connecté : 303 vers `/login?next=…`, ou 401 + `HX-Redirect: /login` pour
  une requête HTMX.

`effective_role(request)` : auth désactivée → `admin` ; sinon `request.state.role` s'il est
posé, sinon `session["role"]`, sinon `guest`.

Chemins publics : `/login`, `/logout` et le préfixe `/static/`.

Conséquences : une rétrogradation s'applique à la requête suivante ; une promotion aussi,
sans reconnexion. Coût : une lecture SQLite par requête protégée.

### 2. Suppression du JS inline (D2)

Nouveau fichier `torsearch/web/static/app.js`, qui gère par délégation d'événements :

- `click` sur `[data-copy]` → `navigator.clipboard.writeText(el.dataset.copy)` ;
- `click` sur `[data-filter]` → `clearFilter(el.dataset.filter, el.dataset.value)` ; la
  fonction `clearFilter` quitte le `<script>` inline d'`index.html` ;
- `error` (phase de capture) sur `img[data-poster]` → retrait de l'image ; remplace
  `onerror="this.remove()"` dans `media_results.html`, `library_list.html`,
  `series_list.html`.

`create_app` monte `StaticFiles` sur `/static` ; `base.html` charge
`<script src="/static/app.js" defer></script>`.

Les valeurs passent désormais dans des attributs `data-*` échappés par Jinja : elles ne
sont jamais interprétées comme du code. Le `hx-vals` du bouton d'inversion du tri
(`results.html:15`) est construit avec `tojson` entre guillemets simples, comme dans
`media_results.html`.

Le script inline de configuration Tailwind (`base.html`, `login.html`) reste jusqu'au
chantier 4 : il ne contient aucune donnée interpolée.

### 3. Secrets jamais renvoyés au navigateur (D4)

Champs concernés : mot de passe Transmission et clé API Jellyfin (`settings.html`), passkey
(`partials/indexer_row.html`). Les URLs et jetons des canaux de notification ne sont déjà
pas réaffichés.

- **Rendu** : `value` toujours vide ; `placeholder="•••••• (inchangé si vide)"` quand une
  valeur est enregistrée ; `autocomplete="new-password"` pour que le navigateur n'y colle
  pas le mot de passe de connexion à TorrSearch.
- **Enregistrement** : dans `update_general` (mot de passe), `update_jellyfin` (clé API) et
  `update_indexer_route` (passkey), une valeur vide conserve la valeur enregistrée.
- **Tester** : `test_indexer_route` accepte un champ optionnel `original_name` (champ
  caché dans `indexer_row.html`). Si `api_key` est vide et qu'`original_name` désigne un
  tracker existant, sa passkey enregistrée est utilisée.

Limite assumée : effacer le mot de passe Transmission n'est plus possible depuis
l'interface. Pour désactiver Jellyfin, vider l'URL suffit.

### 4. Transmission asynchrone (D3)

`TransmissionClient` :

- `__init__(config, client_factory=Client, timeout=10.0)` ; le client `transmission_rpc`
  est créé avec `timeout=self._timeout` (au lieu des 30 s par défaut) ;
- `_get_client()` est protégé par un `threading.Lock` : une seule création paresseuse,
  même si deux appels arrivent en même temps ;
- les méthodes publiques `add`, `list_torrents`, `pause`, `resume`, `remove` deviennent
  `async` et exécutent l'appel synchrone via `asyncio.to_thread` ;
- aucun verrou autour des appels RPC eux-mêmes : si Transmission ne répond pas, les
  appels ne font pas la queue, chacun est borné par le délai de 10 s.

Appelants passés en `await` : `web/routes.py` (`/download`), `web/downloads_routes.py`
(liste, pause, reprise, suppression), `monitor/runner.py` (`run_cycle`, `_grab_movie`,
`run_series_cycle`, `run_jellyfin_refresh`).

### 5. Reverse proxy (D5)

Aucun changement de code : uvicorn active déjà `proxy_headers` et lit la variable
`FORWARDED_ALLOW_IPS`. Documentation :

- `.env.example` : exemple commenté `# FORWARDED_ALLOW_IPS=172.18.0.0/16`, avec
  l'explication (IP ou plage du proxy, ou `*` si le port de TorrSearch n'est joignable que
  par le proxy) ;
- `docker-compose.yml` : même exemple, commenté ;
- README, section « Sécurité & exposition » : une puce.

### 6. Petits correctifs (D6 à D9)

- **D6** : `update_monitor` construit
  `MonitorConfig.model_validate({**ctx.config.monitor.model_dump(), "enabled": enabled is not None, "interval_minutes": interval_minutes})`.
  La config est validée (`"30"` devient `30`) et `regrab_hours` est préservé. Un
  `model_copy(update=…)` ne conviendrait pas : il ne valide rien.
- **D7** : nouveau module `torsearch/web/forms.py` avec `GB`, `to_int(value, default=0)`,
  `to_size_bytes(value_gb)` et `split_words(value)`, utilisés par `routes.py`,
  `surveillance_routes.py` et `update_library` (seeders min).
- **D8** : `settings/mutations.py` gagne `_check_name(name, what)`, qui lève `SettingsError`
  si le nom est vide (ou fait seulement d'espaces) ou contient `/`, `?`, `#` ou `%`. Appelé par `add_indexer`,
  `update_indexer`, `add_saved_search` et `add_channel`. Pas de validateur pydantic : les
  configs existantes doivent continuer à se charger.
- **D9** : `pyproject.toml` déclare
  `[tool.setuptools.package-data] torsearch = ["web/templates/**/*.html", "web/static/**/*"]`.

## Gestion d'erreurs

- Transmission : les exceptions remontent comme aujourd'hui (message ou bandeau d'erreur
  côté web, log côté surveillance) ; le délai de 10 s borne l'attente.
- Compte supprimé : la session est effacée ; l'utilisateur voit seulement l'écran de
  connexion.
- Nom invalide : `SettingsError`, affichée dans la liste concernée (mécanisme existant).

## Compatibilité

- Aucune migration de données. Les configs existantes, même avec des noms désormais
  refusés, se chargent toujours.
- Les sessions existantes restent valides si le compte existe ; le rôle effectif devient
  celui en base.
- Mode identifiant unique (store vide ou absent) et auth désactivée : inchangés.

## Tests (TDD)

- **D1** :
  - un membre connecté puis supprimé reçoit 303 vers `/login` (401 + `HX-Redirect` en
    HTMX) et sa session est vidée ;
  - un membre rétrogradé en invité reçoit 403 sur `/search` sans reconnexion ;
  - un invité promu membre accède à `/search` sans reconnexion ;
  - le mode identifiant unique reste couvert par les tests existants.
- **D2** :
  - aucun attribut `on[a-z]+=` dans les templates (un test parcourt `templates/`) ;
  - un `download_url` contenant `');alert(1)//` ressort échappé dans `data-copy`, sans
    `onclick` ;
  - `/static/app.js` est servi (200) sans session.
- **D3** :
  - avec un faux client `transmission_rpc` lent (0,3 s, `time.sleep`), une autre coroutine
    progresse pendant `await list_torrents()` ;
  - le client est créé avec `timeout=10` ;
  - les faux clients Transmission de `tests/test_monitor_runner.py`,
    `tests/test_downloads_web.py` et `tests/test_web.py` passent en `async` ; les tests de
    `tests/test_transmission.py` attendent (`await`) les méthodes du client.
- **D4** :
  - le HTML de `/settings` ne contient aucune des valeurs secrètes configurées ;
  - un envoi avec secret vide conserve la valeur ; une nouvelle valeur la remplace ;
  - Tester avec passkey vide et `original_name` utilise la passkey enregistrée.
- **D6** : après `POST /surveillance/monitor`, `regrab_hours=72` est préservé et
  `interval_minutes` est un entier.
- **D7** : tests unitaires de `web/forms.py` ; le reste est couvert par les tests existants.
- **D8** : un nom contenant `/` est refusé à l'ajout et au renommage (tracker, recherche,
  canal) ; une config existante avec un tel nom se charge toujours.
- **D5, D9** : pas de test automatisé (documentation ; contenu de la wheel vérifié à la
  main avec `pip wheel`).

## Hors périmètre

- En-tête Content-Security-Policy : chantier 4 (il faut d'abord supprimer les CDN et le
  script inline de configuration Tailwind).
- Identifiants stables à la place des noms dans les URLs : chantiers 2 et 4.
- Client Transmission natif sur httpx, suivi des torrents par hash : chantier 3.
- Changement de mot de passe depuis l'interface, « déconnecter toutes les sessions ».

## Livraison

Une PR « Chantier 1 : assainissement sécurité & fiabilité » depuis la branche courante ;
un commit par défaut corrigé (test rouge puis correctif) ; CI verte (ruff, mypy, pytest).
