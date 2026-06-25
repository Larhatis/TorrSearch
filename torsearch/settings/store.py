from __future__ import annotations

import json
from pathlib import Path

from torsearch.config import Config, load_config
from torsearch.db.database import Collection, as_collection


class SettingsStore:
    def __init__(
        self,
        source: Collection | str | Path,
        bootstrap_config_path: str | Path | None = None,
        migrate_from: str | Path | None = None,
    ):
        self._c = as_collection(source, "settings")
        self._bootstrap = Path(bootstrap_config_path) if bootstrap_config_path else None
        if migrate_from is not None:
            self._migrate(Path(migrate_from))

    def _migrate(self, path: Path) -> None:
        if not path.exists() or not self._c.is_empty():
            return
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        self._c.upsert("config", data)

    def load(self) -> Config:
        doc = self._c.get("config")
        if doc is not None:
            return Config(**doc)
        if self._bootstrap and self._bootstrap.exists():
            config = load_config(self._bootstrap)
            self.save(config)
            return config
        return Config()

    def save(self, config: Config) -> None:
        self._c.upsert("config", config.model_dump(mode="json"))
