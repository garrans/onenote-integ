# D-T04: Schema validation tests — valid artifact, missing required fields, unknown version.

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schema.note_artifact import Attachment, NoteArtifact, Person, Routing, Timestamps
from src.schema.validator import SchemaValidationError, load_json_schema, validate_note_artifact

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal() -> dict:
    """Minimum-viable NoteArtifact payload."""
    return {
        "version": "1.0",
        "artifactId": "art-001",
        "sourceSystem": "TestConnector",
        "title": "Test Note",
        "body": "<p>Hello world</p>",
    }


def _full() -> dict:
    """Fully populated NoteArtifact payload."""
    return {
        "version": "1.0",
        "artifactId": "art-002",
        "sourceSystem": "InspectionsApp",
        "sourceRecordId": "INS-9999",
        "title": "Inspection Report #9999",
        "body": "<p>Details here</p>",
        "tags": ["fire", "inspection"],
        "people": [{"name": "Jane Smith", "role": "author"}],
        "attachments": [{"filename": "photo.jpg", "fileId": "f-001", "url": "https://example.com/photo.jpg"}],
        "timestamps": {"created": "2026-04-20T10:00:00Z", "lastUpdated": "2026-04-20T11:00:00Z"},
        "relationships": {"parentArtifactId": "art-000", "relatedArtifactIds": ["art-003"]},
        "routing": {"notebookName": "Operations", "sectionName": "Inspections", "template": "default"},
        "renderHints": {"layout": "detailed", "priority": "high"},
    }


# ---------------------------------------------------------------------------
# NoteArtifact model
# ---------------------------------------------------------------------------

class TestNoteArtifactModel:
    def test_minimal_valid(self):
        art = NoteArtifact.model_validate(_minimal())
        assert art.artifact_id == "art-001"
        assert art.source_system == "TestConnector"

    def test_full_valid(self):
        art = NoteArtifact.model_validate(_full())
        assert art.render_hints is not None
        assert art.render_hints.priority == "high"
        assert art.routing is not None
        assert art.routing.notebook_name == "Operations"

    def test_missing_artifact_id_raises(self):
        data = _minimal()
        data.pop("artifactId")
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_missing_title_raises(self):
        data = _minimal()
        data.pop("title")
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_missing_source_system_raises(self):
        data = _minimal()
        data.pop("sourceSystem")
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_missing_body_raises(self):
        data = _minimal()
        data.pop("body")
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_invalid_version_pattern_raises(self):
        data = _minimal()
        data["version"] = "v1"
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_invalid_priority_raises(self):
        data = _full()
        data["renderHints"]["priority"] = "critical"
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_extra_fields_rejected(self):
        data = _minimal()
        data["unknownField"] = "oops"
        with pytest.raises(ValidationError):
            NoteArtifact.model_validate(data)

    def test_immutable(self):
        art = NoteArtifact.model_validate(_minimal())
        with pytest.raises(Exception):
            art.title = "changed"  # type: ignore[misc]

    def test_json_roundtrip(self):
        art = NoteArtifact.model_validate(_full())
        restored = NoteArtifact.model_validate_json(art.model_dump_json(by_alias=True))
        assert restored.artifact_id == art.artifact_id
        assert restored.routing == art.routing


# ---------------------------------------------------------------------------
# validate_note_artifact utility
# ---------------------------------------------------------------------------

class TestValidateNoteArtifact:
    def test_valid_minimal_returns_artifact(self):
        art = validate_note_artifact(_minimal())
        assert isinstance(art, NoteArtifact)

    def test_unsupported_version_raises(self):
        data = _minimal()
        data["version"] = "2.0"
        with pytest.raises(SchemaValidationError, match="Unsupported"):
            validate_note_artifact(data)

    def test_missing_version_raises(self):
        data = _minimal()
        data.pop("version")
        with pytest.raises(SchemaValidationError):
            validate_note_artifact(data)

    def test_missing_required_field_raises_schema_error(self):
        data = _minimal()
        data.pop("title")
        with pytest.raises(SchemaValidationError, match="validation failed"):
            validate_note_artifact(data)


# ---------------------------------------------------------------------------
# JSON schema file
# ---------------------------------------------------------------------------

class TestJsonSchemaFile:
    def test_loads_without_error(self):
        schema = load_json_schema()
        assert schema["$id"] == "note-artifact-v1"
        assert "properties" in schema

    def test_required_fields_present_in_schema(self):
        schema = load_json_schema()
        required = schema["required"]
        assert "artifactId" in required
        assert "sourceSystem" in required
        assert "title" in required
        assert "body" in required
