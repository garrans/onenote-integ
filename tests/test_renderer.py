# F-T07: Deterministic rendering tests.
#
# Given a NoteArtifact, assert:
# - correct page HTML is generated (template tests)
# - correct block targets are produced (patch command tests)
# - retry policy retries transient errors and fails on exhaustion
# - pipeline dispatches create/update correctly

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.renderer.graph_adapter import (
    GraphError,
    GraphResponse,
    GraphThrottledError,
    GraphTransientError,
    IGraphAdapter,
)
from src.renderer.page_manager import OWNED_BLOCKS, PageManager
from src.renderer.pipeline import IPageMappingStore, RendererPipeline
from src.renderer.retry import with_retry
from src.renderer.templates import TemplateRegistry
from src.eventbus.envelope import EventEnvelope, EventType
from src.schema.note_artifact import NoteArtifact, Person, Routing


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _artifact(**overrides) -> NoteArtifact:
    base = {
        "version": "1.0",
        "artifactId": "art-renderer-001",
        "sourceSystem": "TestSystem",
        "title": "My Test Note",
        "body": "<p>Content here</p>",
        "routing": {"notebookName": "Operations", "sectionName": "Inspections", "template": "default"},
        "tags": ["alpha", "beta"],
        "people": [{"name": "Alice", "role": "author"}],
    }
    base.update(overrides)
    return NoteArtifact.model_validate(base)


class _StubAdapter(IGraphAdapter):
    """In-memory test double for IGraphAdapter."""

    def __init__(self):
        self.created_pages: list[dict] = []
        self.patched_pages: list[dict] = []
        self._section_id = "sec-001"
        self._next_page_id_counter = 1

    def get_page(self, page_id: str) -> GraphResponse:
        return GraphResponse(200, {"id": page_id})

    def get_page_content(self, page_id: str) -> str:
        return "<html><body></body></html>"

    def create_page(self, section_id: str, html_body: str, title: str) -> GraphResponse:
        page_id = f"page-{self._next_page_id_counter}"
        self._next_page_id_counter += 1
        self.created_pages.append({"section_id": section_id, "html": html_body, "title": title})
        return GraphResponse(201, {"id": page_id})

    def patch_page(self, page_id: str, patch_commands: list) -> GraphResponse:
        self.patched_pages.append({"page_id": page_id, "commands": patch_commands})
        return GraphResponse(204)

    def get_section_id(self, notebook_name: str, section_name: str) -> str:
        return self._section_id


class _InMemoryMappingStore(IPageMappingStore):
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_page_id(self, artifact_id: str) -> str | None:
        return self._store.get(artifact_id)

    def set_page_id(self, artifact_id: str, page_id: str) -> None:
        self._store[artifact_id] = page_id


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------

class TestTemplateRegistry:
    def test_default_template_contains_title(self):
        reg = TemplateRegistry()
        html = reg.render(_artifact())
        assert "My Test Note" in html

    def test_default_template_contains_data_id_blocks(self):
        reg = TemplateRegistry()
        html = reg.render(_artifact())
        for block in OWNED_BLOCKS:
            assert f'data-id="{block}"' in html

    def test_default_template_contains_user_notes_block(self):
        reg = TemplateRegistry()
        html = reg.render(_artifact())
        assert 'data-id="user-notes"' in html

    def test_tags_rendered(self):
        reg = TemplateRegistry()
        html = reg.render(_artifact())
        assert "alpha" in html
        assert "beta" in html

    def test_no_routing_falls_back_to_default(self):
        art = NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "art-002",
            "sourceSystem": "S",
            "title": "No Routing",
            "body": "b",
        })
        reg = TemplateRegistry()
        html = reg.render(art)
        assert "No Routing" in html

    def test_unknown_template_falls_back_to_default(self):
        art = NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "art-003",
            "sourceSystem": "S",
            "title": "Unknown Tmpl",
            "body": "b",
            "routing": {"notebookName": "N", "sectionName": "S", "template": "nonexistent"},
        })
        reg = TemplateRegistry()
        html = reg.render(art)
        assert "Unknown Tmpl" in html

    def test_custom_template_registered(self):
        reg = TemplateRegistry()
        reg.register("compact", lambda a: f"<compact>{a.title}</compact>")
        art = NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "art-004",
            "sourceSystem": "S",
            "title": "Compact",
            "body": "b",
            "routing": {"notebookName": "N", "sectionName": "S", "template": "compact"},
        })
        result = reg.render(art)
        assert "<compact>Compact</compact>" == result


# ---------------------------------------------------------------------------
# Patch command tests (F-T04)
# ---------------------------------------------------------------------------

class TestBuildPatchCommands:
    def setup_method(self):
        self.adapter = _StubAdapter()
        self.mgr = PageManager(self.adapter, TemplateRegistry())

    def test_returns_commands_for_all_owned_blocks(self):
        cmds = self.mgr._build_patch_commands(_artifact())
        targets = {c["target"] for c in cmds}
        assert targets == set(OWNED_BLOCKS)

    def test_user_notes_not_in_commands(self):
        cmds = self.mgr._build_patch_commands(_artifact())
        assert all(c["target"] != "user-notes" for c in cmds)

    def test_all_commands_have_replace_action(self):
        cmds = self.mgr._build_patch_commands(_artifact())
        assert all(c["action"] == "replace" for c in cmds)

    def test_title_present_in_title_command(self):
        cmds = self.mgr._build_patch_commands(_artifact())
        title_cmd = next(c for c in cmds if c["target"] == "artifact-title")
        assert "My Test Note" in title_cmd["content"]

    def test_no_people_produces_placeholder(self):
        art = NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "art-005",
            "sourceSystem": "S",
            "title": "T",
            "body": "b",
        })
        cmds = self.mgr._build_patch_commands(art)
        people_cmd = next(c for c in cmds if c["target"] == "people-section")
        assert "No people listed" in people_cmd["content"]


# ---------------------------------------------------------------------------
# PageManager.create_page / patch_page (F-T03 + F-T04)
# ---------------------------------------------------------------------------

class TestPageManager:
    def setup_method(self):
        self.adapter = _StubAdapter()
        self.mgr = PageManager(self.adapter, TemplateRegistry())

    def test_create_page_returns_page_id(self):
        page_id = self.mgr.create_page(_artifact())
        assert page_id.startswith("page-")

    def test_create_page_posts_to_correct_section(self):
        self.mgr.create_page(_artifact())
        assert self.adapter.created_pages[0]["section_id"] == "sec-001"

    def test_create_page_no_routing_raises(self):
        art = NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "art-006",
            "sourceSystem": "S",
            "title": "T",
            "body": "b",
        })
        with pytest.raises(ValueError, match="no routing"):
            self.mgr.create_page(art)

    def test_patch_page_sends_commands(self):
        self.mgr.patch_page("page-99", _artifact())
        assert len(self.adapter.patched_pages) == 1
        assert self.adapter.patched_pages[0]["page_id"] == "page-99"


# ---------------------------------------------------------------------------
# Retry policy tests (F-T02)
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    def test_succeeds_on_first_try(self):
        result = with_retry(lambda: 42, sleep_fn=lambda _: None)
        assert result == 42

    def test_retries_on_throttle(self):
        calls = []

        def func():
            calls.append(1)
            if len(calls) < 3:
                raise GraphThrottledError(retry_after_seconds=1)
            return "ok"

        result = with_retry(func, sleep_fn=lambda _: None)
        assert result == "ok"
        assert len(calls) == 3

    def test_retries_on_transient(self):
        calls = []

        def func():
            calls.append(1)
            if len(calls) < 2:
                raise GraphTransientError("503", 503)
            return "done"

        result = with_retry(func, sleep_fn=lambda _: None)
        assert result == "done"
        assert len(calls) == 2

    def test_exhausted_retries_raise(self):
        with pytest.raises(GraphThrottledError):
            with_retry(
                lambda: (_ for _ in ()).throw(GraphThrottledError(1)),
                max_attempts=3,
                sleep_fn=lambda _: None,
            )

    def test_non_retryable_raises_immediately(self):
        calls = []

        def func():
            calls.append(1)
            raise GraphError("404 Not Found", 404)

        with pytest.raises(GraphError, match="404"):
            with_retry(func, sleep_fn=lambda _: None)
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# RendererPipeline tests (F-T06)
# ---------------------------------------------------------------------------

class TestRendererPipeline:
    def _make_envelope(self, event_type: EventType, artifact_dict: dict) -> EventEnvelope:
        return EventEnvelope(
            event_type=event_type,
            schema_version="1.0",
            source_system="TestSystem",
            payload=artifact_dict,
        )

    def _payload(self, artifact_id: str = "art-001") -> dict:
        return {
            "version": "1.0",
            "artifactId": artifact_id,
            "sourceSystem": "TestSystem",
            "title": "Test",
            "body": "<p>body</p>",
            "routing": {"notebookName": "N", "sectionName": "S", "template": "default"},
        }

    def setup_method(self):
        self.adapter = _StubAdapter()
        self.mgr = PageManager(self.adapter, TemplateRegistry())
        self.store = _InMemoryMappingStore()
        self.pipeline = RendererPipeline(self.mgr, self.store)

    def test_created_event_creates_page(self):
        env = self._make_envelope(EventType.ARTIFACT_CREATED_V1, self._payload())
        self.pipeline.handle_event(env)
        assert len(self.adapter.created_pages) == 1
        assert self.store.get_page_id("art-001") is not None

    def test_updated_event_patches_existing_page(self):
        self.store.set_page_id("art-001", "page-existing")
        env = self._make_envelope(EventType.ARTIFACT_UPDATED_V1, self._payload())
        self.pipeline.handle_event(env)
        assert len(self.adapter.patched_pages) == 1
        assert self.adapter.patched_pages[0]["page_id"] == "page-existing"

    def test_updated_event_creates_page_when_unknown(self):
        env = self._make_envelope(EventType.ARTIFACT_UPDATED_V1, self._payload("art-999"))
        self.pipeline.handle_event(env)
        assert len(self.adapter.created_pages) == 1

    def test_created_event_patches_when_already_exists(self):
        self.store.set_page_id("art-001", "page-existing")
        env = self._make_envelope(EventType.ARTIFACT_CREATED_V1, self._payload())
        self.pipeline.handle_event(env)
        assert len(self.adapter.patched_pages) == 1

    def test_unhandled_event_type_ignored(self):
        env = self._make_envelope(EventType.ONENOTE_PAGE_EDITED_V1, self._payload())
        self.pipeline.handle_event(env)
        assert len(self.adapter.created_pages) == 0
        assert len(self.adapter.patched_pages) == 0

    def test_invalid_payload_raises_schema_error(self):
        from src.schema.validator import SchemaValidationError
        env = self._make_envelope(EventType.ARTIFACT_CREATED_V1, {"version": "1.0"})
        with pytest.raises(SchemaValidationError):
            self.pipeline.handle_event(env)
