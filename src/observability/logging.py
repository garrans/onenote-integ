"""
J-T01: Structured log schema.
J-T02: Correlation ID propagation.
J-T03: Log instrumentation helpers.

Design:
- All log records share a standard set of fields (LogRecord dataclass).
- CorrelationContext is a thread-local context manager that carries the
  correlation_id through a logical operation (pipeline → monitor → bus).
- `log_event()` emits a JSON-serialisable dict via Python's standard
  logging module at the INFO level on the "onenote_integ" logger.
- Components can import `current_correlation_id()` and embed it in their
  own logging calls without needing the full LogRecord machinery.
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("onenote_integ")

# ---------------------------------------------------------------------------
# J-T02: Correlation ID — context-variable based (works with threads + asyncio)
# ---------------------------------------------------------------------------

_CORRELATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "onenote_integ_correlation_id", default=None
)


def current_correlation_id() -> str | None:
    """Return the correlation ID set for the current execution context, or None."""
    return _CORRELATION_ID.get()


class CorrelationContext:
    """
    Context manager that sets a correlation ID for the duration of a block.

    Usage::
        with CorrelationContext("envelope.correlation_id"):
            process(envelope)

    The ID is stored in a ContextVar so it is automatically scoped to the
    current thread / async Task without leaking to other concurrent operations.
    """

    def __init__(self, correlation_id: str) -> None:
        self._correlation_id = correlation_id
        self._token: contextvars.Token | None = None

    def __enter__(self) -> "CorrelationContext":
        self._token = _CORRELATION_ID.set(self._correlation_id)
        return self

    def __exit__(self, *_) -> None:
        if self._token is not None:
            _CORRELATION_ID.reset(self._token)


# ---------------------------------------------------------------------------
# J-T01: Structured log record schema
# ---------------------------------------------------------------------------

@dataclass
class LogRecord:
    """
    Canonical structured log record.

    All fields except `timestamp` and `correlation_id` are mandatory so
    that downstream log aggregation (e.g. Azure Monitor) can filter and
    group reliably.
    """

    source_system: str       # e.g. "InspectionsApp", "onenote", "renderer"
    artifact_id: str | None  # None if not yet resolved (e.g. at bus boundary)
    action: str              # e.g. "page_created", "patch_applied", "conflict_detected"
    outcome: str             # "success" | "failure" | "skipped"
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    correlation_id: str | None = field(default_factory=current_correlation_id)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# ---------------------------------------------------------------------------
# J-T03: Log instrumentation
# ---------------------------------------------------------------------------

def log_event(record: LogRecord) -> None:
    """
    Emit a structured log record via the standard logging infrastructure.

    The record is serialised to a JSON string so it can be picked up by
    Azure Monitor / Log Analytics without custom formatters.
    """
    log.info(json.dumps(record.to_dict()))
