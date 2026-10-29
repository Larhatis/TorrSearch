from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from torsearch.redact import redact


@dataclass(frozen=True)
class LogEntry:
    at: datetime
    level: str
    levelno: int
    name: str
    message: str


class MemoryLogHandler(logging.Handler):
    """Keeps the latest app log lines in memory for the "Journal" page (secrets masked)."""

    def __init__(self, capacity: int = 500):
        super().__init__(logging.INFO)
        self._entries: deque[LogEntry] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._entries.append(LogEntry(
                at=datetime.fromtimestamp(record.created),
                level=record.levelname,
                levelno=record.levelno,
                name=record.name.removeprefix("torsearch."),
                message=redact(record.getMessage()),
            ))
        except Exception:
            self.handleError(record)

    def entries(self, min_level: int = logging.INFO) -> list[LogEntry]:
        """Newest first."""
        return [e for e in reversed(self._entries) if e.levelno >= min_level]

    def clear(self) -> None:
        self._entries.clear()


_handler: MemoryLogHandler | None = None


def install() -> MemoryLogHandler:
    """Attach the in-memory handler to the ``torsearch`` loggers (idempotent)."""
    global _handler
    if _handler is None:
        _handler = MemoryLogHandler()
        app_logger = logging.getLogger("torsearch")
        if app_logger.level == logging.NOTSET or app_logger.level > logging.INFO:
            app_logger.setLevel(logging.INFO)
        app_logger.addHandler(_handler)
    return _handler
