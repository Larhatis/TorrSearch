# Migration SQLite (document-store)

Date : 2026-06-25

## Problème

Les 6 stores (settings, monitor, library, series, users, requests) chargent un fichier
JSON entier, le mutent, le réécrivent. D'où des courses « lost-update » entre la boucle
moniteur (tâche de fond) et les requêtes web qui écrivent les mêmes fichiers.

## Approche : document-store SQLite (stdlib, zéro dépendance)

`torsearch/db/database.py` :
- `Database(path)` : connexion SQLite en **WAL**, table unique
  `documents(collection, id, data JSON, PRIMARY KEY(collection, id))`. Une connexion
  courte par opération + `busy_timeout` → SQLite sérialise les écritures au niveau fichier,
  WAL laisse lecteurs et écrivain concurrents.
- `Collection` : `all()` (ordre d'insertion via rowid), `get(id)`, `upsert(id, data)`
  (UPSERT `ON CONFLICT … DO UPDATE`, rowid stable), `delete(id)`, `replace_all(items)`,
  `count()`, `is_empty()`.

Chaque store **garde ses modèles pydantic et son API publique**, mais persiste des
**lignes** au lieu d'un fichier. Les mutations deviennent **par ligne** (`upsert`/`delete`)
→ deux opérations concurrentes sur des lignes différentes ne s'écrasent plus.

## Migration des données

Chaque store accepte `migrate_from=<ancien fichier JSON>`. Au 1ᵉʳ démarrage, si la
collection est vide et que le JSON existe, on importe son contenu (`replace_all`). Les
fichiers JSON restent en backup (jamais supprimés). Personne ne perd ses données.

`build_app` construit un `Database` unique (`data/torsearch.db`, `TORSEARCH_DB`) et passe
une `collection(...)` à chaque store migré.

## Pourquoi pas un schéma SQL par entité

Permettrait des requêtes riches par champ, mais beaucoup plus de code/risque, alors que
les accès sont surtout « tout charger » ou « get par id ». On garde la porte ouverte vers
des colonnes typées si un besoin de requête émerge.

## Livraison incrémentale (une PR par étape, tests verts à chaque fois)

1. **Fondation + UserStore** (cette PR) : `Database`/`Collection` + migration de `UserStore`.
2. `RequestStore`
3. `MovieLibrary`
4. `SeriesLibrary`
5. `MonitorHistory` (append + cap → `delete` des plus vieux)
6. `SettingsStore` (document unique `config`, bootstrap config.yaml conservé)

## Tests
- `test_db.py` : upsert/get, ordre, update en place, delete, replace_all, isolation des
  collections, persistance, WAL actif.
- Par store migré : API identique (tests existants conservés, helpers pointés sur une
  `Collection`) + un test de migration JSON→SQLite.
