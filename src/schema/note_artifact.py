"""
D-T02: Typed model classes for NoteArtifact v1.

These Pydantic models are the Python representation of spec/note-artifact-v1.schema.json.
They are the single source of truth for type checking and serialization in Python.
The JSON schema file is the cross-language source of truth.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    role: str | None = Field(None, max_length=128)

    model_config = {"frozen": True, "extra": "forbid"}


class Attachment(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    file_id: str | None = Field(None, alias="fileId", max_length=512)
    url: str | None = Field(None, max_length=2048)

    model_config = {"frozen": True, "extra": "forbid", "populate_by_name": True}


class Timestamps(BaseModel):
    created: datetime
    last_updated: datetime | None = Field(None, alias="lastUpdated")

    model_config = {"frozen": True, "extra": "forbid", "populate_by_name": True}


class Relationships(BaseModel):
    parent_artifact_id: str | None = Field(None, alias="parentArtifactId", max_length=255)
    related_artifact_ids: list[str] = Field(default_factory=list, alias="relatedArtifactIds")

    model_config = {"frozen": True, "extra": "forbid", "populate_by_name": True}


class Routing(BaseModel):
    notebook_name: str = Field(..., alias="notebookName", min_length=1, max_length=256)
    section_name: str = Field(..., alias="sectionName", min_length=1, max_length=256)
    template: str | None = Field(None, max_length=128)

    model_config = {"frozen": True, "extra": "forbid", "populate_by_name": True}


class RenderHints(BaseModel):
    layout: str | None = Field(None, max_length=64)
    priority: Literal["high", "medium", "low"] | None = None

    model_config = {"frozen": True, "extra": "forbid"}


class NoteArtifact(BaseModel):
    """
    Canonical interchange object for the OneNote integration pipeline.

    Required fields: version, artifact_id, source_system, title, body.
    All other fields are optional but should be populated by connectors
    where available.
    """

    version: str = Field("1.0", pattern=r"^\d+\.\d+$")
    artifact_id: str = Field(..., alias="artifactId", min_length=1, max_length=255)
    source_system: str = Field(..., alias="sourceSystem", min_length=1, max_length=128)
    source_record_id: str | None = Field(None, alias="sourceRecordId", max_length=2048)
    title: str = Field(..., min_length=1, max_length=512)
    body: str
    tags: list[str] = Field(default_factory=list)
    people: list[Person] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    timestamps: Timestamps | None = None
    relationships: Relationships | None = None
    routing: Routing | None = None
    render_hints: RenderHints | None = Field(None, alias="renderHints")

    model_config = {"frozen": True, "extra": "forbid", "populate_by_name": True}
