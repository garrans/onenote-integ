# G-T04: Persistence tests — upsert idempotency, mapping lookup, hash comparison.

from __future__ import annotations

import threading
import time

import pytest

from src.state.store import (
    InMemoryContentHashStore,
    InMemoryPageMappingStore,
    InMemorySyncCursorStore,
)


# ---------------------------------------------------------------------------
# InMemoryPageMappingStore
# ---------------------------------------------------------------------------

class TestPageMappingStore:
    def setup_method(self):
        self.store = InMemoryPageMappingStore()

    def test_get_returns_none_for_unknown(self):
        assert self.store.get("art-unknown") is None

    def test_upsert_creates_mapping(self):
        m = self.store.upsert("art-001", "page-001")
        assert m.artifact_id == "art-001"
        assert m.page_id == "page-001"

    def test_upsert_idempotent_same_page(self):
        m1 = self.store.upsert("art-001", "page-001")
        m2 = self.store.upsert("art-001", "page-001")
        assert m1.artifact_id == m2.artifact_id
        assert m1.page_id == m2.page_id
        assert m1.created_at == m2.created_at

    def test_upsert_updates_page_id(self):
        m1 = self.store.upsert("art-001", "page-001")
        m2 = self.store.upsert("art-001", "page-002")
        assert m2.page_id == "page-002"
        assert m2.created_at == m1.created_at  # created_at preserved

    def test_get_returns_upserted_record(self):
        self.store.upsert("art-001", "page-001")
        m = self.store.get("art-001")
        assert m is not None
        assert m.page_id == "page-001"

    def test_all_returns_all_records(self):
        self.store.upsert("art-001", "page-001")
        self.store.upsert("art-002", "page-002")
        assert len(self.store.all()) == 2

    def test_schema_version_is_1(self):
        assert InMemoryPageMappingStore.SCHEMA_VERSION == 1

    def test_thread_safe_concurrent_upserts(self):
        """Concurrent upserts must not corrupt state."""
        errors = []

        def worker(i):
            try:
                self.store.upsert(f"art-{i}", f"page-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(self.store.all()) == 50


# ---------------------------------------------------------------------------
# InMemorySyncCursorStore
# ---------------------------------------------------------------------------

class TestSyncCursorStore:
    def setup_method(self):
        self.store = InMemorySyncCursorStore()

    def test_get_returns_none_for_unknown(self):
        assert self.store.get("NoSystem") is None

    def test_upsert_stores_cursor(self):
        c = self.store.upsert("InspectionsApp", "tok-abc123")
        assert c.source_system == "InspectionsApp"
        assert c.cursor_value == "tok-abc123"

    def test_upsert_overwrites_cursor(self):
        self.store.upsert("InspectionsApp", "tok-old")
        c2 = self.store.upsert("InspectionsApp", "tok-new")
        assert c2.cursor_value == "tok-new"

    def test_get_returns_latest(self):
        self.store.upsert("InspectionsApp", "tok-1")
        self.store.upsert("InspectionsApp", "tok-2")
        c = self.store.get("InspectionsApp")
        assert c.cursor_value == "tok-2"


# ---------------------------------------------------------------------------
# InMemoryContentHashStore
# ---------------------------------------------------------------------------

class TestContentHashStore:
    def setup_method(self):
        self.store = InMemoryContentHashStore()

    def test_get_returns_none_for_unknown(self):
        assert self.store.get("page-unknown") is None

    def test_upsert_stores_hash(self):
        h = self.store.upsert("page-001", "<html>content</html>")
        assert len(h.sha256_hex) == 64  # SHA-256 hex

    def test_same_content_produces_same_hash(self):
        h1 = self.store.upsert("page-001", "content")
        h2 = self.store.upsert("page-001", "content")
        assert h1.sha256_hex == h2.sha256_hex

    def test_different_content_produces_different_hash(self):
        h1 = self.store.upsert("page-001", "content-a")
        h2 = self.store.upsert("page-001", "content-b")
        assert h1.sha256_hex != h2.sha256_hex

    def test_matches_returns_true_for_same_content(self):
        self.store.upsert("page-001", "<html>v1</html>")
        assert self.store.matches("page-001", "<html>v1</html>") is True

    def test_matches_returns_false_for_changed_content(self):
        self.store.upsert("page-001", "<html>v1</html>")
        assert self.store.matches("page-001", "<html>v2</html>") is False

    def test_matches_returns_false_for_unknown_page(self):
        assert self.store.matches("page-new", "anything") is False

    def test_bytes_content_accepted(self):
        h = self.store.upsert("page-002", b"<html>bytes</html>")
        assert h.sha256_hex is not None
