from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AuthMode(str, Enum):
    QUERY = "query"
    BEARER = "bearer"


class IndexerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: str = "torznab"
    url: str
    api_key: str = ""
    auth: AuthMode = AuthMode.QUERY
    enabled: bool = True
    categories: dict[str, list[int]] = Field(default_factory=dict)


class TransmissionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = "localhost"
    port: int = 9091
    username: str = ""
    password: str = ""
    https: bool = False


class SearchConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    timeout_seconds: float = 10.0


class Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    transmission: TransmissionConfig = Field(default_factory=TransmissionConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    indexers: list[IndexerConfig] = Field(default_factory=list)


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _interpolate(value):
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    return value


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    raw = _interpolate(raw)
    return Config(**raw)
