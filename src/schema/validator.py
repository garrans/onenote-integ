"""
D-T03: Schema validation utility.

Validates NoteArtifact payloads arriving at the bus boundary before they
enter the pipeline. Raises a descriptive error on any schema violation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.schema.note_artifact import NoteArtifact

log = logging.getLogger(__name__)

_SCHEMA_FILE = Path(__file__).parent.parent.parent / "spec" / "note-artifact-v1.schema.json"

# Supported schema versions. Payloads with unknown versions are rejected.
_SUPPORTED_VERSIONS = {"1.0"}


class SchemaValidationError(ValueError):
    """Raised when a payload does not conform to the NoteArtifact schema."""


def validate_note_artifact(data: dict[str, Any]) -> NoteArtifact:
    """
    Validate *data* against the NoteArtifact v1 schema.

    Returns a validated, immutable NoteArtifact instance.

    Raises:
        SchemaValidationError: if the data is invalid.
    """
    # Fast version check before full Pydantic validation.
    version = data.get("version", "")
    if version not in _SUPPORTED_VERSIONS:
        raise SchemaValidationError(
            f"Unsupported NoteArtifact schema version: {version!r}. "
            f"Supported: {_SUPPORTED_VERSIONS}"
        )

    try:
        artifact = NoteArtifact.model_validate(data)
        log.debug(
            "Validated NoteArtifact artifact_id=%s source=%s",
            artifact.artifact_id,
            artifact.source_system,
        )
        return artifact
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        summary = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors
        )
        raise SchemaValidationError(f"NoteArtifact validation failed: {summary}") from exc


def load_json_schema() -> dict[str, Any]:
    """Load the raw JSON schema file for use with external validators."""
    return json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
