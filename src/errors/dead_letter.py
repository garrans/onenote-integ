"""
I-T02: Dead-letter queue handler.

Parks terminal failures with their full context so they can be
investigated and replayed without losing information.

Design:
- `DeadLetterStore` is an in-memory reference implementation (swap for
  SQL / blob storage in production).
- Each entry captures the original event envelope, the error, a timestamp,
  and an optional retry count for diagnostic purposes.
- The `DeadLetterHandler` wraps any event-processing callable and catches
  TerminalError (plus unexpected errors), parking them in the store.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from src.errors.taxonomy import TerminalError
from src.eventbus.envelope import EventEnvelope

log = logging.getLogger(__name__)


@dataclass
class DeadLetterEntry:
    envelope: EventEnvelope
    error_type: str
    error_message: str
    parked_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    retry_count: int = 0


class DeadLetterStore:
    """Thread-safe in-memory store for dead-lettered event envelopes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[DeadLetterEntry] = []

    def park(self, entry: DeadLetterEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def all(self) -> list[DeadLetterEntry]:
        with self._lock:
            return list(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


EventProcessor = Callable[[EventEnvelope], None]


class DeadLetterHandler:
    """
    Wraps an event processor.  On TerminalError (or any unexpected exception)
    the failed envelope is parked in the DeadLetterStore instead of
    crashing the consumer.
    """

    def __init__(self, processor: EventProcessor, store: DeadLetterStore) -> None:
        self._processor = processor
        self._store = store

    def handle(self, envelope: EventEnvelope) -> None:
        try:
            self._processor(envelope)
        except TerminalError as exc:
            log.error(
                "Terminal error processing %s — parking in dead-letter: %s",
                envelope.event_type,
                exc,
            )
            self._store.park(
                DeadLetterEntry(
                    envelope=envelope,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 — intentional catch-all
            log.exception(
                "Unexpected error processing %s — parking in dead-letter: %s",
                envelope.event_type,
                exc,
            )
            self._store.park(
                DeadLetterEntry(
                    envelope=envelope,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
