"""
G-T01 + G-T02: Storage schema and in-memory implementation.

Schema version 1 defines three tables / namespaces:

1. **page_mappings**   artifact_id (PK) → page_id, created_at
2. **sync_cursors**    source_system (PK) → cursor_value, updated_at
3. **content_hashes**  page_id (PK) → sha256_hex, updated_at

The production implementation would back these against Azure Table Storage,
SQLite, or Cosmos DB.  This module provides:
- Typed interfaces (G-T01 schema).
- An in-memory reference implementation (G-T02 migration baseline v1).
- An idempotent upsert contract (G-T03).
"""

from __future__ import annotations

import hashlib
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Data classes (schema v1)
# ---------------------------------------------------------------------------

@dataclass
class PageMapping:
    artifact_id: str
    page_id: str
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class SyncCursor:
    source_system: str
    cursor_value: str
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class ContentHash:
    page_id: str
    sha256_hex: str
    updated_at: datetime = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Interfaces (G-T01 storage schema contract)
# ---------------------------------------------------------------------------

class IPageMappingStore(ABC):
    """artifact_id ↔ page_id mappings."""

    @abstractmethod
    def get(self, artifact_id: str) -> PageMapping | None: ...

    @abstractmethod
    def upsert(self, artifact_id: str, page_id: str) -> PageMapping:
        """Idempotent: creates or updates the mapping. Returns the current record."""


class ISyncCursorStore(ABC):
    """Sync cursor per source system (e.g., delta token, timestamp)."""

    @abstractmethod
    def get(self, source_system: str) -> SyncCursor | None: ...

    @abstractmethod
    def upsert(self, source_system: str, cursor_value: str) -> SyncCursor: ...


class IContentHashStore(ABC):
    """SHA-256 content hashes per OneNote page."""

    @abstractmethod
    def get(self, page_id: str) -> ContentHash | None: ...

    @abstractmethod
    def upsert(self, page_id: str, content: str | bytes) -> ContentHash:
        """
        Compute and store the SHA-256 hash of *content*.
        Returns the stored ContentHash record.
        """


# ---------------------------------------------------------------------------
# In-memory implementations (G-T02 migration baseline — schema version 1)
# ---------------------------------------------------------------------------

class InMemoryPageMappingStore(IPageMappingStore):
    """Thread-safe in-memory page mapping store."""

    SCHEMA_VERSION = 1

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, PageMapping] = {}

    def get(self, artifact_id: str) -> PageMapping | None:
        with self._lock:
            return self._data.get(artifact_id)

    def upsert(self, artifact_id: str, page_id: str) -> PageMapping:
        """G-T03: idempotent upsert — creates or updates the artifact→page mapping."""
        with self._lock:
            existing = self._data.get(artifact_id)
            if existing is not None:
                # Update page_id if changed; preserve created_at.
                if existing.page_id == page_id:
                    return existing
                updated = PageMapping(
                    artifact_id=artifact_id,
                    page_id=page_id,
                    created_at=existing.created_at,
                )
                self._data[artifact_id] = updated
                return updated
            new = PageMapping(artifact_id=artifact_id, page_id=page_id)
            self._data[artifact_id] = new
            return new

    def all(self) -> list[PageMapping]:
        with self._lock:
            return list(self._data.values())


class InMemorySyncCursorStore(ISyncCursorStore):
    """Thread-safe in-memory sync cursor store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, SyncCursor] = {}

    def get(self, source_system: str) -> SyncCursor | None:
        with self._lock:
            return self._data.get(source_system)

    def upsert(self, source_system: str, cursor_value: str) -> SyncCursor:
        with self._lock:
            record = SyncCursor(source_system=source_system, cursor_value=cursor_value)
            self._data[source_system] = record
            return record


class InMemoryContentHashStore(IContentHashStore):
    """Thread-safe in-memory content hash store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, ContentHash] = {}

    def get(self, page_id: str) -> ContentHash | None:
        with self._lock:
            return self._data.get(page_id)

    def upsert(self, page_id: str, content: str | bytes) -> ContentHash:
        raw = content.encode() if isinstance(content, str) else content
        digest = hashlib.sha256(raw).hexdigest()
        with self._lock:
            record = ContentHash(page_id=page_id, sha256_hex=digest)
            self._data[page_id] = record
            return record

    def matches(self, page_id: str, content: str | bytes) -> bool:
        """Return True if *content* hash matches the stored hash for *page_id*."""
        raw = content.encode() if isinstance(content, str) else content
        digest = hashlib.sha256(raw).hexdigest()
        with self._lock:
            stored = self._data.get(page_id)
            return stored is not None and stored.sha256_hex == digest
