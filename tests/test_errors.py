# I-T05: Conflict scenario tests.

from __future__ import annotations

import pytest

from src.errors.conflict import ConflictDetector, ReconciliationTask
from src.errors.dead_letter import DeadLetterHandler, DeadLetterStore, DeadLetterEntry
from src.errors.taxonomy import (
    ConflictError,
    GraphPermanentError,
    GraphThrottledError,
    GraphTransientError,
    MappingNotFoundError,
    RetryableError,
    SchemaValidationError,
    TerminalError,
    UnsupportedVersionError,
)
from src.eventbus.envelope import EventEnvelope, EventType


# ---------------------------------------------------------------------------
# Taxonomy tests (I-T01)
# ---------------------------------------------------------------------------

class TestErrorTaxonomy:
    def test_retryable_is_base_error(self):
        from src.errors.taxonomy import OneNoteIntegError
        assert issubclass(RetryableError, OneNoteIntegError)

    def test_terminal_is_base_error(self):
        from src.errors.taxonomy import OneNoteIntegError
        assert issubclass(TerminalError, OneNoteIntegError)

    def test_graph_throttled_is_retryable(self):
        assert issubclass(GraphThrottledError, RetryableError)

    def test_graph_transient_is_retryable(self):
        assert issubclass(GraphTransientError, RetryableError)

    def test_schema_validation_is_terminal(self):
        assert issubclass(SchemaValidationError, TerminalError)

    def test_unsupported_version_is_terminal(self):
        assert issubclass(UnsupportedVersionError, TerminalError)

    def test_mapping_not_found_is_terminal(self):
        assert issubclass(MappingNotFoundError, TerminalError)

    def test_conflict_error_is_terminal(self):
        assert issubclass(ConflictError, TerminalError)

    def test_graph_throttled_carries_retry_after(self):
        exc = GraphThrottledError(retry_after_seconds=42.0)
        assert exc.retry_after_seconds == 42.0

    def test_retryable_default_retry_after_is_none(self):
        exc = RetryableError("msg")
        assert exc.retry_after_seconds is None

    def test_unsupported_version_carries_version(self):
        exc = UnsupportedVersionError("2.0")
        assert exc.version == "2.0"

    def test_mapping_not_found_carries_artifact_id(self):
        exc = MappingNotFoundError("art-123")
        assert exc.artifact_id == "art-123"

    def test_conflict_error_carries_page_and_artifact(self):
        exc = ConflictError("page-1", "art-1", detail="block mismatch")
        assert exc.page_id == "page-1"
        assert exc.artifact_id == "art-1"
        assert "block mismatch" in exc.detail


# ---------------------------------------------------------------------------
# Dead-letter tests (I-T02)
# ---------------------------------------------------------------------------

def _make_envelope(**kwargs) -> EventEnvelope:
    defaults = dict(
        event_type=EventType.ARTIFACT_CREATED_V1,
        source_system="test",
        schema_version="1.0",
        payload={},
    )
    defaults.update(kwargs)
    return EventEnvelope(**defaults)


class TestDeadLetterStore:
    def test_starts_empty(self):
        store = DeadLetterStore()
        assert len(store) == 0

    def test_park_increases_count(self):
        store = DeadLetterStore()
        store.park(DeadLetterEntry(
            envelope=_make_envelope(),
            error_type="TerminalError",
            error_message="bad",
        ))
        assert len(store) == 1

    def test_all_returns_copy(self):
        store = DeadLetterStore()
        store.park(DeadLetterEntry(
            envelope=_make_envelope(), error_type="X", error_message="y"
        ))
        entries = store.all()
        entries.clear()
        assert len(store) == 1  # original unaffected


class TestDeadLetterHandler:
    def setup_method(self):
        self.store = DeadLetterStore()

    def test_successful_processor_leaves_store_empty(self):
        handler = DeadLetterHandler(lambda e: None, self.store)
        handler.handle(_make_envelope())
        assert len(self.store) == 0

    def test_terminal_error_parks_envelope(self):
        def bad(_):
            raise SchemaValidationError("oops")

        handler = DeadLetterHandler(bad, self.store)
        handler.handle(_make_envelope())
        assert len(self.store) == 1

    def test_unexpected_error_parks_envelope(self):
        def explode(_):
            raise RuntimeError("unexpected")

        handler = DeadLetterHandler(explode, self.store)
        handler.handle(_make_envelope())
        assert len(self.store) == 1
        assert self.store.all()[0].error_type == "RuntimeError"

    def test_parked_entry_records_error_type(self):
        def bad(_):
            raise UnsupportedVersionError("99.0")

        handler = DeadLetterHandler(bad, self.store)
        handler.handle(_make_envelope())
        assert self.store.all()[0].error_type == "UnsupportedVersionError"


# ---------------------------------------------------------------------------
# Conflict detection tests (I-T03)
# ---------------------------------------------------------------------------

_AUTH_HTML = """
<html><body>
<div data-id="artifact-title"><p>Inspection #42</p></div>
<div data-id="source-system"><p>InspectionsApp</p></div>
<div data-id="tags-section"><p>fire, roof</p></div>
<div data-id="people-section"><p>Alice</p></div>
<div data-id="body-section"><p>All clear.</p></div>
<div data-id="user-notes"><p>My private note</p></div>
</body></html>
"""

_LIVE_HTML_SAME = _AUTH_HTML

_LIVE_HTML_USER_NOTES_CHANGED = _AUTH_HTML.replace(
    "<p>My private note</p>", "<p>Updated by user</p>"
)

_LIVE_HTML_OWNED_CHANGED = _AUTH_HTML.replace(
    "<p>All clear.</p>", "<p>Someone changed this</p>"
)


class TestConflictDetector:
    def setup_method(self):
        self.detector = ConflictDetector()

    def test_identical_html_no_conflict(self):
        """Same HTML in auth and live: no exception raised."""
        self.detector.detect(_AUTH_HTML, _LIVE_HTML_SAME, "p1", "a1")

    def test_user_notes_change_no_conflict(self):
        """Only user-notes changed: not an owned block, no conflict."""
        self.detector.detect(_AUTH_HTML, _LIVE_HTML_USER_NOTES_CHANGED, "p1", "a1")

    def test_owned_block_change_raises_conflict(self):
        """body-section changed externally: ConflictError raised."""
        with pytest.raises(ConflictError) as exc_info:
            self.detector.detect(_AUTH_HTML, _LIVE_HTML_OWNED_CHANGED, "p1", "a1")
        assert exc_info.value.page_id == "p1"
        assert exc_info.value.artifact_id == "a1"

    def test_conflict_detail_mentions_block(self):
        with pytest.raises(ConflictError) as exc_info:
            self.detector.detect(_AUTH_HTML, _LIVE_HTML_OWNED_CHANGED, "p1", "a1")
        assert "body-section" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Reconciliation task tests (I-T04)
# ---------------------------------------------------------------------------

class TestReconciliationTask:
    def test_handle_conflict_does_not_raise(self):
        """ReconciliationTask must not propagate the conflict; just log."""
        task = ReconciliationTask()
        conflict = ConflictError("page-X", "art-X", detail="test")
        task.handle_conflict(conflict)  # should not raise
