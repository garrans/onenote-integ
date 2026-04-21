# H-T04: Change detection tests.

from __future__ import annotations

import threading
import time

import pytest

from src.eventbus.envelope import EventEnvelope, EventType
from src.monitor.change_detector import ChangeDetector
from src.monitor.change_source import ChangeEvent, PollingMonitor
from src.renderer.graph_adapter import GraphResponse, IGraphAdapter
from src.state.store import InMemoryContentHashStore


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _InMemoryPublisher:
    """Captures published envelopes for assertion."""

    def __init__(self):
        self.published: list[EventEnvelope] = []

    def publish(self, envelope: EventEnvelope) -> None:
        self.published.append(envelope)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _StubGraphAdapter(IGraphAdapter):
    """Returns preset page content per page_id."""

    def __init__(self, pages: dict[str, str] | None = None):
        self._pages = pages or {}

    def get_page(self, page_id: str) -> GraphResponse:
        return GraphResponse(200, {"id": page_id})

    def get_page_content(self, page_id: str) -> str:
        return self._pages.get(page_id, "<html></html>")

    def create_page(self, section_id, html_body, title) -> GraphResponse:
        return GraphResponse(201, {"id": "new-page"})

    def patch_page(self, page_id, patch_commands) -> GraphResponse:
        return GraphResponse(204)

    def get_section_id(self, notebook_name, section_name) -> str:
        return "sec-001"


def _make_event(page_id: str = "page-001", html: str = "<html>v1</html>") -> ChangeEvent:
    return ChangeEvent(page_id=page_id, artifact_id="art-001", raw_html=html)


# ---------------------------------------------------------------------------
# ChangeDetector tests (H-T02 + H-T03)
# ---------------------------------------------------------------------------

class TestChangeDetector:
    def setup_method(self):
        self.hash_store = InMemoryContentHashStore()
        self.publisher = _InMemoryPublisher()
        self.detector = ChangeDetector(self.hash_store, self.publisher)

    def test_first_observation_publishes_event(self):
        """First time a page is seen: hash stored and event published."""
        self.detector.handle_change_event(_make_event())
        assert len(self.publisher.published) == 1
        evt = self.publisher.published[0]
        assert evt.event_type == EventType.ONENOTE_PAGE_EDITED_V1

    def test_same_content_does_not_publish(self):
        """Same HTML twice: no duplicate event."""
        self.detector.handle_change_event(_make_event(html="<html>v1</html>"))
        self.detector.handle_change_event(_make_event(html="<html>v1</html>"))
        assert len(self.publisher.published) == 1

    def test_changed_content_publishes_again(self):
        """HTML changes: second event published."""
        self.detector.handle_change_event(_make_event(html="<html>v1</html>"))
        self.detector.handle_change_event(_make_event(html="<html>v2</html>"))
        assert len(self.publisher.published) == 2

    def test_published_event_payload_contains_page_id(self):
        self.detector.handle_change_event(_make_event(page_id="page-XYZ"))
        payload = self.publisher.published[0].payload
        assert payload["pageId"] == "page-XYZ"

    def test_published_event_payload_contains_artifact_id(self):
        self.detector.handle_change_event(_make_event())
        payload = self.publisher.published[0].payload
        assert payload["artifactId"] == "art-001"

    def test_published_event_payload_contains_content_hash(self):
        self.detector.handle_change_event(_make_event())
        payload = self.publisher.published[0].payload
        assert len(payload["contentHash"]) == 64  # SHA-256 hex

    def test_hash_store_updated_after_change(self):
        self.detector.handle_change_event(_make_event(html="<html>v1</html>"))
        self.detector.handle_change_event(_make_event(html="<html>v2</html>"))
        stored = self.hash_store.get("page-001")
        assert stored is not None
        # Should reflect v2 hash.
        assert self.hash_store.matches("page-001", "<html>v2</html>")

    def test_multiple_pages_tracked_independently(self):
        self.detector.handle_change_event(ChangeEvent("page-A", "art-A", "<html>a1</html>"))
        self.detector.handle_change_event(ChangeEvent("page-B", "art-B", "<html>b1</html>"))
        self.detector.handle_change_event(ChangeEvent("page-A", "art-A", "<html>a1</html>"))
        self.detector.handle_change_event(ChangeEvent("page-B", "art-B", "<html>b2</html>"))
        # page-A: 1 event (no change on second); page-B: 2 events.
        assert len(self.publisher.published) == 3


# ---------------------------------------------------------------------------
# PollingMonitor tests (H-T01b)
# ---------------------------------------------------------------------------

class TestPollingMonitor:
    def test_no_events_on_first_poll(self):
        """First poll: hashes seeded, no events (no previous baseline)."""
        received: list = []
        adapter = _StubGraphAdapter({"p1": "<html>v1</html>"})
        monitor = PollingMonitor(
            adapter,
            lambda: [("art-1", "p1")],
            received.append,
            poll_interval_seconds=9999,
        )
        monitor._poll_once()
        assert received == []

    def test_change_detected_on_second_poll(self):
        """Two polls with changed content: event received on second poll."""
        received: list = []
        content = {"p1": "<html>v1</html>"}
        adapter = _StubGraphAdapter(content)
        monitor = PollingMonitor(
            adapter,
            lambda: [("art-1", "p1")],
            received.append,
            poll_interval_seconds=9999,
        )
        monitor._poll_once()           # seeds hash
        content["p1"] = "<html>v2</html>"
        monitor._poll_once()           # detects change
        assert len(received) == 1
        assert received[0].page_id == "p1"

    def test_no_spurious_event_when_content_unchanged(self):
        """Same content on successive polls: no event."""
        received: list = []
        adapter = _StubGraphAdapter({"p1": "<html>same</html>"})
        monitor = PollingMonitor(
            adapter,
            lambda: [("art-1", "p1")],
            received.append,
            poll_interval_seconds=9999,
        )
        monitor._poll_once()
        monitor._poll_once()
        assert received == []

    def test_graph_error_does_not_crash_monitor(self):
        """A Graph error during poll is swallowed; monitor continues."""
        from src.renderer.graph_adapter import GraphError

        class _FailingAdapter(_StubGraphAdapter):
            def get_page_content(self, page_id: str) -> str:
                raise GraphError("Simulated failure", 503)

        received: list = []
        monitor = PollingMonitor(
            _FailingAdapter(),
            lambda: [("art-1", "p1")],
            received.append,
            poll_interval_seconds=9999,
        )
        monitor._poll_once()  # must not raise
        assert received == []
