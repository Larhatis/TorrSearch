from __future__ import annotations

import re

# Credentials that end up inside error messages: URL userinfo (scheme://user:pass@host),
# secret-bearing query parameters and the Telegram bot token path segment.
_PATTERNS = [
    (re.compile(r"(://)[^/\s@]+@"), r"\1***@"),
    (re.compile(r"([?&](?:apikey|api_key|passkey|token|key)=)[^&\s'\"]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(/bot)[^/\s'\"]+"), r"\1***"),
]


def redact(text: str) -> str:
    """Mask credentials embedded in URLs before an error message is shown to a user."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
