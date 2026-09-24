from __future__ import annotations

import re

GB = 1024 ** 3


def to_int(value: str, default: int = 0) -> int:
    """Integer from a form field; ``default`` when blank or invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_size_bytes(value_gb: str) -> int | None:
    """Size typed in GB -> bytes; ``None`` when blank, invalid or <= 0."""
    try:
        gb = float(value_gb)
    except (TypeError, ValueError):
        return None
    return int(gb * GB) if gb > 0 else None


def split_words(value: str) -> list[str]:
    """Words of a free-text field, split on spaces and commas."""
    return [w for w in re.split(r"[\s,]+", value) if w]
