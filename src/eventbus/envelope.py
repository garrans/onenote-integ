"""
C-T01 / C-T02: Event envelope schema and event type registry.

All messages on the Service Bus share a common envelope so consumers can
filter, route, and trace events without parsing the payload.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# C-T02: Event type registry
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """All event types exchanged over the bus. Versioned to allow schema evolution."""

    # Source system → integration pipeline
    ARTIFACT_CREATED_V1 = "artifact.created.v1"
    ARTIFACT_UPDATED_V1 = "artifact.updated.v1"
    ARTIFACT_DELETED_V1 = "artifact.deleted.v1"

    # OneNote → integration pipeline (Change Monitor emits these)
    ONENOTE_PAGE_EDITED_V1 = "onenote.page.edited.v1"
    ONENOTE_PAGE_CREATED_V1 = "onenote.page.created.v1"
    ONENOTE_PAGE_DELETED_V1 = "onenote.page.deleted.v1"


# ---------------------------------------------------------------------------
# C-T01: Event envelope
# ---------------------------------------------------------------------------

class EventEnvelope(BaseModel):
    """
    Standard wrapper for every message on the Service Bus.

    Fields:
        event_id:       UUID v4 — unique per message (idempotency key).
        event_type:     One of the registered EventType values.
        schema_version: Semver of the *envelope* schema (not the payload).
        source_system:  Identifies the originating component, e.g. "source-connector".
        correlation_id: Propagated across all events in a logical operation.
        timestamp:      UTC ISO-8601 emission time.
        payload:        Domain-specific data for this event type.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    schema_version: str = Field("1.0", pattern=r"^\d+\.\d+$")
    source_system: str = Field(..., min_length=1, max_length=128)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def with_correlation(self, correlation_id: str) -> "EventEnvelope":
        """Return a copy with an explicit correlation ID (for chained events)."""
        return self.model_copy(update={"correlation_id": correlation_id})
