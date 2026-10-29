from __future__ import annotations

import logging
import sys
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


class RedactFilter(logging.Filter):
    """Masks credentials in console log lines (``docker logs``)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


_handler: MemoryLogHandler | None = None


def install() -> MemoryLogHandler:
    """Attach the in-memory handler and a console handler to the ``torsearch`` loggers.

    Idempotent. The console handler keeps app events visible in ``docker logs`` (the
    in-memory handler alone would silence Python's last-resort output).
    """
    global _handler
    if _handler is None:
        _handler = MemoryLogHandler()
        app_logger = logging.getLogger("torsearch")
        if app_logger.level == logging.NOTSET or app_logger.level > logging.INFO:
            app_logger.setLevel(logging.INFO)
        app_logger.addHandler(_handler)
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        console.addFilter(RedactFilter())
        app_logger.addHandler(console)  # uvicorn leaves the root logger without handlers
    return _handler
