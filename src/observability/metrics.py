"""
J-T04: Sync metrics contract.
J-T05: Audit log writer.

SyncMetrics is a thread-safe counter bag aligned to the key operational
measurements. Components increment counters as they process events; an
external reporter (Azure Monitor, Prometheus) reads the snapshot.

AuditLogWriter maps connector/event pairs to page actions and records
each step in an append-only list (in-memory baseline; swap to persistent
storage in production).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from src.eventbus.envelope import EventType

log = logging.getLogger("onenote_integ.audit")


# ---------------------------------------------------------------------------
# J-T04: Sync metrics contract
# ---------------------------------------------------------------------------

@dataclass
class SyncMetrics:
    """Cumulative sync metrics. All counters start at zero."""

    events_received: int = 0
    pages_created: int = 0
    patches_applied: int = 0
    conflicts_detected: int = 0
    dead_letters: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class MetricsCollector:
    """Thread-safe cumulative metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics = SyncMetrics()

    def increment(self, field_name: str, by: int = 1) -> None:
        with self._lock:
            current = getattr(self._metrics, field_name)
            setattr(self._metrics, field_name, current + by)

    def snapshot(self) -> SyncMetrics:
        """Return an immutable copy of the current metric values."""
        with self._lock:
            return SyncMetrics(**asdict(self._metrics))


# ---------------------------------------------------------------------------
# J-T05: Audit log writer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEntry:
    correlation_id: str | None
    source_system: str
    artifact_id: str | None
    event_type: str          # EventType value string
    page_action: str         # "created" | "patched" | "skipped" | "conflict" | "dead_lettered"
    outcome: str             # "success" | "failure"
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class AuditLogWriter:
    """
    Append-only audit log mapping connector events to page actions.

    `record()` is called after each event is processed. The log is
    queryable by artifact_id or event_type for diagnostic replay.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        log.info(
            "AUDIT source=%s artifact=%s event=%s action=%s outcome=%s corr=%s",
            entry.source_system,
            entry.artifact_id,
            entry.event_type,
            entry.page_action,
            entry.outcome,
            entry.correlation_id,
        )
        with self._lock:
            self._entries.append(entry)

    def all(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries)

    def by_artifact(self, artifact_id: str) -> list[AuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.artifact_id == artifact_id]

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
