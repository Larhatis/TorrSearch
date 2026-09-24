from __future__ import annotations

import math
import re

GB = 1024 ** 3


def to_int(value: str, default: int = 0) -> int:
    """Integer from a form field; ``default`` when blank or invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_size_bytes(value_gb: str) -> int | None:
    """Size typed in GB -> bytes; ``None`` when blank, invalid, infinite or <= 0."""
    try:
        gb = float(value_gb)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(gb) or gb <= 0:
        return None
    return int(gb * GB)


def split_words(value: str) -> list[str]:
    """Words of a free-text field, split on spaces and commas."""
    return [w for w in re.split(r"[\s,]+", value) if w]
