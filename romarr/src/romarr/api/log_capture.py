"""In-memory log capture for the Settings → System Logs page.

The Sonarr-style operator UI needs a "what just happened" surface
that doesn't require shelling into the container to ``docker logs``.
This module attaches a :class:`logging.Handler` to the root logger
that keeps the most recent N log records in a thread-safe ring
buffer, then exposes them through ``GET /api/v3/log``.

Design notes:

* Capacity is bounded (``DEFAULT_CAPACITY`` records). Once the
  deque is full, oldest entries fall off — this is a debugging
  aid, not an audit log.
* Records are projected to plain dicts at capture time so the
  endpoint serialises them without reaching back into the
  ``LogRecord`` (which holds frame references that would pin
  resources and aren't trivially JSON-able).
* Exceptions are pre-formatted into the ``exception_text`` field
  so the modal can show the full traceback without the API doing
  string-formatting work per request.
* The handler is process-local — multiple workers each have their
  own buffer. That's acceptable for a single-process FastAPI
  deployment; if Romarr grows a multi-worker setup the buffer
  would need to move to Redis/SQLite.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from itertools import count
from typing import Any

DEFAULT_CAPACITY = 2000
"""How many records to keep in memory. ~2000 covers a busy hour
of operation; tune via :func:`install` if needed."""


_id_counter = count(start=1)


class RingBufferHandler(logging.Handler):
    """Stores recent :class:`logging.LogRecord` projections in a
    capped deque. Thread-safe — log emission can happen from any
    thread (asyncio executor, scheduler workers, …).
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        super().__init__(level=logging.DEBUG)
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = _project_record(record)
        except Exception:
            # A failure here must never break the application's
            # logging path — drop the record silently.
            return
        with self._lock:
            self._buffer.append(entry)

    def snapshot(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        min_level: int | None = None,
        logger_substring: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return ``(records, total_after_filter)``.

        Records are returned newest-first. ``min_level`` filters
        on numeric level (``logging.WARNING`` keeps ``WARNING`` +
        ``ERROR`` + ``CRITICAL``). ``logger_substring`` is a
        case-insensitive substring match on the logger name —
        operators looking for ``importer`` get every
        ``romarr.importer.*`` line.
        """
        with self._lock:
            # Snapshot the deque under lock; do filtering /
            # pagination outside so the lock window stays short.
            items = list(self._buffer)
        # Newest-first.
        items.reverse()

        if min_level is not None:
            items = [r for r in items if r["level_no"] >= min_level]
        if logger_substring:
            needle = logger_substring.lower()
            items = [r for r in items if needle in r["logger"].lower()]

        total = len(items)
        sliced = items[offset : offset + limit]
        return sliced, total

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


def _project_record(record: logging.LogRecord) -> dict[str, Any]:
    """Convert a :class:`LogRecord` into a serialisable dict.

    The exception is pre-formatted because the LogRecord holds
    sys.exc_info() which is unsafe to ship across the async
    boundary (frame references) and tedious to format on every
    GET request.
    """
    if record.exc_info:
        formatted_exc = logging.Formatter().formatException(record.exc_info)
    else:
        formatted_exc = None

    # Use ``getMessage`` so % args / format args are interpolated.
    try:
        message = record.getMessage()
    except Exception:
        message = record.msg if isinstance(record.msg, str) else repr(record.msg)

    return {
        "id": next(_id_counter),
        "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        "level": record.levelname,
        "level_no": record.levelno,
        "logger": record.name,
        "message": message,
        "exception_text": formatted_exc,
        "module": record.module,
        "func": record.funcName,
        "line": record.lineno,
    }


# Module-level singleton — installed once at app startup.
LOG_BUFFER = RingBufferHandler()


def install(*, level: int = logging.INFO) -> None:
    """Attach :data:`LOG_BUFFER` to the root logger.

    Idempotent: re-running ``install`` does not double-attach.
    The level argument controls what the root logger ACCEPTS;
    individual handlers (stderr, the ring buffer) keep their own
    levels. Setting the root to INFO is the production default —
    test harnesses that need DEBUG can bump it.
    """
    root = logging.getLogger()
    if LOG_BUFFER not in root.handlers:
        root.addHandler(LOG_BUFFER)
    if root.level == 0 or root.level > level:
        root.setLevel(level)


__all__ = ["LOG_BUFFER", "RingBufferHandler", "install"]
