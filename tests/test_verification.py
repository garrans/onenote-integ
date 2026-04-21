# V-T01: End-to-end test — seed NoteArtifact event → OneNote page created with correct blocks.
# V-T02: Resilience test — 429 throttle, partial failure → retry + dead-letter + recovery.
# V-T03: Security test — no tokens in structured logs.
# V-T04: Isolation test — add/remove connector, rest of system unchanged.

from __future__ import annotations

import json
import logging

import pytest

from src.connectors.base import ConnectorRegistry
from src.connectors.inspections_app import InspectionsAppConnector
from src.errors.dead_letter import DeadLetterHandler, DeadLetterStore
from src.eventbus.envelope import EventEnvelope, EventType
from src.observability.logging import CorrelationContext, LogRecord, log_event
from src.renderer.graph_adapter import GraphError, GraphResponse, IGraphAdapter
from src.renderer.page_manager import PageManager
from src.renderer.pipeline import IPageMappingStore, RendererPipeline
from src.renderer.retry import with_retry
from src.renderer.templates import TemplateRegistry
from src.schema.note_artifact import NoteArtifact
from src.schema.validator import SchemaValidationError, validate_note_artifact


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

class _CapturingAdapter(IGraphAdapter):
    """Records all Graph calls for assertion."""

    def __init__(self, *, fail_times: int = 0, throttle_times: int = 0):
        self.created_pages: list[dict] = []
        self.patched_pages: list[dict] = []
        self._fail_counter = fail_times
        self._throttle_counter = throttle_times

    def _maybe_fail(self):
        from src.renderer.graph_adapter import GraphThrottledError, GraphTransientError
        if self._throttle_counter > 0:
            self._throttle_counter -= 1
            raise GraphThrottledError("throttled", retry_after_seconds=0.0)
        if self._fail_counter > 0:
            self._fail_counter -= 1
            raise GraphTransientError("transient", status_code=503)

    def get_page(self, page_id):
        return GraphResponse(200, {"id": page_id})

    def get_page_content(self, page_id):
        return "<html></html>"

    def create_page(self, section_id, html_body, title):
        self._maybe_fail()
        self.created_pages.append({"section_id": section_id, "title": title, "html": html_body})
        return GraphResponse(201, {"id": f"new-{len(self.created_pages)}"})

    def patch_page(self, page_id, patch_commands):
        self.patched_pages.append({"page_id": page_id, "commands": patch_commands})
        return GraphResponse(204)

    def get_section_id(self, notebook_name, section_name):
        return "sec-default"


class _InMemoryMappingStore(IPageMappingStore):
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_page_id(self, artifact_id):
        return self._store.get(artifact_id)

    def set_page_id(self, artifact_id, page_id):
        self._store[artifact_id] = page_id


def _make_artifact_payload(**overrides) -> dict:
    base = {
        "version": "1.0",
        "artifactId": "art-e2e-001",
        "sourceSystem": "InspectionsApp",
        "title": "Inspection #E2E",
        "body": "All systems nominal.",
        "routing": {
            "notebookName": "FFR Notebook",
            "sectionName": "Inspections",
        },
    }
    base.update(overrides)
    return base


def _make_created_envelope(payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.ARTIFACT_CREATED_V1,
        source_system="InspectionsApp",
        payload=payload or _make_artifact_payload(),
    )


# ---------------------------------------------------------------------------
# V-T01: End-to-end — seed NoteArtifact event → page created with correct blocks
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def setup_method(self):
        self.adapter = _CapturingAdapter()
        self.mapping_store = _InMemoryMappingStore()
        registry = TemplateRegistry()
        manager = PageManager(self.adapter, registry)
        self.pipeline = RendererPipeline(manager, self.mapping_store)

    def test_artifact_created_event_triggers_page_creation(self):
        envelope = _make_created_envelope()
        self.pipeline.handle_event(envelope)
        assert len(self.adapter.created_pages) == 1

    def test_created_page_has_correct_title(self):
        envelope = _make_created_envelope()
        self.pipeline.handle_event(envelope)
        assert self.adapter.created_pages[0]["title"] == "Inspection #E2E"

    def test_created_page_html_contains_owned_blocks(self):
        envelope = _make_created_envelope()
        self.pipeline.handle_event(envelope)
        html = self.adapter.created_pages[0]["html"]
        for block in ("artifact-title", "source-system", "body-section", "user-notes"):
            assert f'data-id="{block}"' in html

    def test_artifact_id_stored_in_mapping_after_creation(self):
        envelope = _make_created_envelope()
        self.pipeline.handle_event(envelope)
        assert self.mapping_store.get_page_id("art-e2e-001") is not None

    def test_second_created_event_patches_existing_page(self):
        """Second ARTIFACT_CREATED_V1 for same artifact → patch, not second create."""
        env1 = _make_created_envelope()
        env2 = _make_created_envelope(payload=_make_artifact_payload(title="Updated Title"))
        self.pipeline.handle_event(env1)
        self.pipeline.handle_event(env2)
        assert len(self.adapter.created_pages) == 1
        assert len(self.adapter.patched_pages) == 1

    def test_artifact_updated_event_patches_page(self):
        # First create
        self.pipeline.handle_event(_make_created_envelope())
        # Then update
        update_env = EventEnvelope(
            event_type=EventType.ARTIFACT_UPDATED_V1,
            source_system="InspectionsApp",
            payload=_make_artifact_payload(title="Updated Inspection"),
        )
        self.pipeline.handle_event(update_env)
        assert len(self.adapter.patched_pages) == 1

    def test_schema_validation_error_propagates(self):
        bad_env = EventEnvelope(
            event_type=EventType.ARTIFACT_CREATED_V1,
            source_system="InspectionsApp",
            payload={"bad": "payload"},
        )
        # pipeline re-raises src.schema.validator.SchemaValidationError on bad payloads
        with pytest.raises(SchemaValidationError):
            self.pipeline.handle_event(bad_env)


# ---------------------------------------------------------------------------
# V-T02: Resilience — 429 throttle, transient failure → retry, dead-letter, recovery
# ---------------------------------------------------------------------------

class TestResilience:
    def test_retry_recovers_from_throttle(self):
        """with_retry should honour Retry-After on 429 and eventually succeed."""
        call_count = 0

        from src.renderer.graph_adapter import GraphThrottledError

        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise GraphThrottledError(retry_after_seconds=0.0)
            return "ok"

        result = with_retry(eventually_succeeds, max_attempts=5, base_delay_s=0.0, sleep_fn=lambda s: None)
        assert result == "ok"
        assert call_count == 3

    def test_retry_exhaustion_parks_in_dead_letter(self):
        """Permanent transient failures → TerminalError after retries → dead-letter."""
        from src.errors.taxonomy import GraphTransientError, TerminalError
        from src.renderer.graph_adapter import GraphTransientError as GTE

        store = DeadLetterStore()

        def always_fails(envelope):
            def bad():
                raise GTE(status_code=503)

            with_retry(bad, max_attempts=3, base_delay_s=0.0, sleep_fn=lambda s: None)

        envelope = _make_created_envelope()
        handler = DeadLetterHandler(always_fails, store)
        handler.handle(envelope)
        assert len(store) == 1

    def test_dead_letter_entry_records_error_info(self):
        """Dead-lettered entry should name the error type."""
        from src.renderer.graph_adapter import GraphTransientError as GTE

        store = DeadLetterStore()

        def always_fails(envelope):
            def bad():
                raise GTE("transient", status_code=503)

            with_retry(bad, max_attempts=2, base_delay_s=0.0, sleep_fn=lambda s: None)

        handler = DeadLetterHandler(always_fails, store)
        handler.handle(_make_created_envelope())
        entry = store.all()[0]
        assert entry.error_type == "GraphTransientError"

    def test_unrelated_events_unaffected_by_failure(self):
        """A failed envelope does not prevent subsequent envelopes from processing."""
        adapter = _CapturingAdapter()
        mapping_store = _InMemoryMappingStore()
        manager = PageManager(adapter, TemplateRegistry())
        pipeline = RendererPipeline(manager, mapping_store)
        store = DeadLetterStore()

        def process(envelope):
            pipeline.handle_event(envelope)

        handler = DeadLetterHandler(process, store)

        # Bad envelope — parks in dead-letter.
        bad_env = EventEnvelope(
            event_type=EventType.ARTIFACT_CREATED_V1,
            source_system="x",
            payload={"bad": "data"},
        )
        handler.handle(bad_env)
        assert len(store) == 1  # parked

        # Good envelope — succeeds.
        handler.handle(_make_created_envelope())
        assert len(adapter.created_pages) == 1  # processed normally


# ---------------------------------------------------------------------------
# V-T03: Security — no tokens or secrets appear in structured log output
# ---------------------------------------------------------------------------

class TestSecurity:
    _SENSITIVE_PATTERNS = (
        "Bearer ",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
    )

    def test_log_record_dict_contains_no_tokens(self):
        """LogRecord serialised dict must not contain known secret field names."""
        rec = LogRecord(
            source_system="auth",
            artifact_id=None,
            action="token_refreshed",
            outcome="success",
            extra={"user": "svc-account@example.com"},
        )
        serialised = json.dumps(rec.to_dict()).lower()
        for pattern in self._SENSITIVE_PATTERNS:
            assert pattern.lower() not in serialised, (
                f"Sensitive pattern {pattern!r} found in log output"
            )

    def test_log_event_emitted_string_contains_no_tokens(self, caplog):
        rec = LogRecord(
            source_system="renderer",
            artifact_id="art-1",
            action="page_created",
            outcome="success",
        )
        with caplog.at_level(logging.INFO, logger="onenote_integ"):
            log_event(rec)
        log_text = " ".join(r.message for r in caplog.records).lower()
        for pattern in self._SENSITIVE_PATTERNS:
            assert pattern.lower() not in log_text


# ---------------------------------------------------------------------------
# V-T04: Isolation — add/remove connector, rest of system unchanged
# ---------------------------------------------------------------------------

class TestIsolation:
    def test_register_connector_does_not_affect_others(self):
        registry = ConnectorRegistry()
        registry.register(InspectionsAppConnector)

        # Add a second connector dynamically.
        from src.connectors.base import IConnector
        from src.schema.note_artifact import NoteArtifact

        class _FakeConnector(IConnector):
            source_system = "FakeSystem"

            def to_note_artifact(self, record):
                raise NotImplementedError

            def handle_onenote_event(self, event):
                pass

        registry.register(_FakeConnector)
        assert "InspectionsApp" in registry.source_systems()
        assert "FakeSystem" in registry.source_systems()

    def test_unregister_connector_does_not_affect_others(self):
        registry = ConnectorRegistry()
        from src.connectors.base import IConnector

        class _TempConnector(IConnector):
            source_system = "TempSystem"

            def to_note_artifact(self, record):
                raise NotImplementedError

            def handle_onenote_event(self, event):
                pass

        registry.register(InspectionsAppConnector)
        registry.register(_TempConnector)
        registry.unregister("TempSystem")

        assert "InspectionsApp" in registry.source_systems()
        assert "TempSystem" not in registry.source_systems()

    def test_renderer_pipeline_unaffected_by_connector_changes(self):
        """Connector registry changes must not affect the renderer pipeline."""
        adapter = _CapturingAdapter()
        mapping_store = _InMemoryMappingStore()
        manager = PageManager(adapter, TemplateRegistry())
        pipeline = RendererPipeline(manager, mapping_store)

        # Register and immediately unregister a connector.
        registry = ConnectorRegistry()
        registry.register(InspectionsAppConnector)
        registry.unregister("InspectionsApp")

        # Pipeline still processes events correctly.
        pipeline.handle_event(_make_created_envelope())
        assert len(adapter.created_pages) == 1
