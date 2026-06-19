from __future__ import annotations

import json
import os
from pathlib import Path

from torsearch.config import Config, load_config


class SettingsStore:
    def __init__(
        self,
        settings_path: str | Path,
        bootstrap_config_path: str | Path | None = None,
    ):
        self._settings_path = Path(settings_path)
        self._bootstrap_config_path = Path(bootstrap_config_path) if bootstrap_config_path else None

    def load(self) -> Config:
        if self._settings_path.exists():
            return Config(**json.loads(self._settings_path.read_text()))
        if self._bootstrap_config_path and self._bootstrap_config_path.exists():
            config = load_config(self._bootstrap_config_path)
            self.save(config)
            return config
        return Config()

    def save(self, config: Config) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._settings_path.with_name(self._settings_path.name + ".tmp")
        tmp.write_text(config.model_dump_json(indent=2))
        os.replace(tmp, self._settings_path)
