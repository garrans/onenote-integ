# E-T04: Connector isolation + contract tests.

from __future__ import annotations

import pytest

from src.connectors.base import ConnectorError, ConnectorRegistry, IConnector
from src.connectors.inspections_app import InspectionsAppConnector
from src.eventbus.envelope import EventEnvelope, EventType
from src.schema.note_artifact import NoteArtifact


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

class _MinimalConnector(IConnector):
    source_system = "MinimalSystem"

    def to_note_artifact(self, source_data: dict) -> NoteArtifact:
        return NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "min-001",
            "sourceSystem": self.source_system,
            "title": "t",
            "body": "b",
        })

    def handle_onenote_event(self, envelope: EventEnvelope) -> None:
        pass


class _AnotherConnector(IConnector):
    source_system = "AnotherSystem"

    def to_note_artifact(self, source_data: dict) -> NoteArtifact:  # pragma: no cover
        return NoteArtifact.model_validate({
            "version": "1.0",
            "artifactId": "other-001",
            "sourceSystem": self.source_system,
            "title": "t",
            "body": "b",
        })

    def handle_onenote_event(self, envelope: EventEnvelope) -> None:
        pass  # pragma: no cover


def _make_envelope() -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.ONENOTE_PAGE_EDITED_V1,
        schema_version="1.0",
        source_system="onenote",
        payload={"pageId": "p-001"},
    )


# ---------------------------------------------------------------------------
# ConnectorRegistry tests
# ---------------------------------------------------------------------------

class TestConnectorRegistry:
    def setup_method(self):
        self.registry = ConnectorRegistry()

    def test_register_and_get(self):
        conn = _MinimalConnector()
        self.registry.register(conn)
        assert self.registry.get("MinimalSystem") is conn

    def test_duplicate_register_raises(self):
        self.registry.register(_MinimalConnector())
        with pytest.raises(ValueError, match="already registered"):
            self.registry.register(_MinimalConnector())

    def test_unregister_removes_connector(self):
        self.registry.register(_MinimalConnector())
        self.registry.unregister("MinimalSystem")
        assert len(self.registry) == 0

    def test_unregister_missing_raises(self):
        with pytest.raises(KeyError):
            self.registry.unregister("Ghost")

    def test_get_missing_raises(self):
        with pytest.raises(KeyError):
            self.registry.get("NoSuch")

    def test_all_returns_all(self):
        self.registry.register(_MinimalConnector())
        self.registry.register(_AnotherConnector())
        assert len(self.registry.all()) == 2

    def test_source_systems(self):
        self.registry.register(_MinimalConnector())
        self.registry.register(_AnotherConnector())
        assert set(self.registry.source_systems()) == {"MinimalSystem", "AnotherSystem"}

    def test_len(self):
        assert len(self.registry) == 0
        self.registry.register(_MinimalConnector())
        assert len(self.registry) == 1


# ---------------------------------------------------------------------------
# Isolation test — removing reference connector does not affect bus/renderer
# ---------------------------------------------------------------------------

class TestConnectorIsolation:
    def test_removing_inspections_connector_leaves_others_intact(self):
        registry = ConnectorRegistry()
        registry.register(_MinimalConnector())
        registry.register(InspectionsAppConnector())

        registry.unregister("InspectionsApp")

        # MinimalSystem is still present and functional.
        conn = registry.get("MinimalSystem")
        art = conn.to_note_artifact({})
        assert art.source_system == "MinimalSystem"

    def test_empty_registry_produces_no_side_effects(self):
        registry = ConnectorRegistry()
        assert registry.all() == []
        assert registry.source_systems() == []


# ---------------------------------------------------------------------------
# InspectionsAppConnector contract tests
# ---------------------------------------------------------------------------

class TestInspectionsAppConnector:
    def setup_method(self):
        self.conn = InspectionsAppConnector()

    def _source_data(self, **overrides) -> dict:
        data = {
            "id": "INS-001",
            "title": "Fire Suppression Check",
            "description": "<p>All systems OK</p>",
            "status": "closed",
            "assigned_to": "Jane Smith",
        }
        data.update(overrides)
        return data

    def test_to_note_artifact_minimal(self):
        art = self.conn.to_note_artifact({"id": "1", "title": "T", "status": "open"})
        assert isinstance(art, NoteArtifact)
        assert art.source_system == "InspectionsApp"
        assert art.artifact_id == "inspections-1"

    def test_to_note_artifact_full(self):
        art = self.conn.to_note_artifact(self._source_data())
        assert art.source_record_id == "INS-001"
        assert art.routing is not None
        assert art.routing.section_name == "Inspections"

    def test_missing_required_id_raises(self):
        with pytest.raises(ConnectorError, match="missing required field"):
            self.conn.to_note_artifact({"title": "T"})

    def test_missing_required_title_raises(self):
        with pytest.raises(ConnectorError, match="missing required field"):
            self.conn.to_note_artifact({"id": "1"})

    def test_handle_onenote_event_does_not_raise(self):
        # Stub should be a no-op without error.
        self.conn.handle_onenote_event(_make_envelope())
