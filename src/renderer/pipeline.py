"""
F-T06: Rendering pipeline.

Subscribes to artifact event types (ARTIFACT_CREATED_V1, ARTIFACT_UPDATED_V1)
and dispatches to PageManager.create_page / PageManager.patch_page.

The pipeline requires a mapping store to lookup existing page IDs for updates.
The store interface is defined minimally here; Area G provides the full implementation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from src.eventbus.bus import MessageHandler
from src.eventbus.envelope import EventEnvelope, EventType
from src.renderer.page_manager import PageManager
from src.schema.validator import SchemaValidationError, validate_note_artifact

log = logging.getLogger(__name__)


# Minimal page-mapping store interface (Area G provides a full implementation).
class IPageMappingStore(ABC):
    """Lookup and record artifact ↔ OneNote page ID mappings."""

    @abstractmethod
    def get_page_id(self, artifact_id: str) -> str | None:
        """Return the OneNote page ID for *artifact_id*, or None if unknown."""

    @abstractmethod
    def set_page_id(self, artifact_id: str, page_id: str) -> None:
        """Persist the mapping artifact_id → page_id."""


class RendererPipeline:
    """
    Event-driven rendering pipeline.

    On ARTIFACT_CREATED_V1: validate payload → create OneNote page → store mapping.
    On ARTIFACT_UPDATED_V1: validate payload → lookup page → patch owned blocks.

    Other event types are ignored.

    Usage::

        pipeline = RendererPipeline(page_manager, mapping_store)
        subscriber.subscribe(pipeline.handle_event)
    """

    HANDLED_TYPES = {EventType.ARTIFACT_CREATED_V1, EventType.ARTIFACT_UPDATED_V1}

    def __init__(self, page_manager: PageManager, mapping_store: IPageMappingStore) -> None:
        self._mgr = page_manager
        self._store = mapping_store

    @property
    def handle_event(self) -> MessageHandler:
        """Return the handler callable for use with IEventSubscriber."""
        return self._dispatch

    def _dispatch(self, envelope: EventEnvelope) -> None:
        if envelope.event_type not in self.HANDLED_TYPES:
            log.debug("Ignoring event type %s", envelope.event_type.value)
            return

        try:
            artifact = validate_note_artifact(envelope.payload)
        except SchemaValidationError as exc:
            log.error(
                "Invalid NoteArtifact payload in event %s: %s",
                envelope.event_id,
                exc,
            )
            raise  # Let subscriber dead-letter this message.

        if envelope.event_type == EventType.ARTIFACT_CREATED_V1:
            self._handle_created(envelope, artifact)
        elif envelope.event_type == EventType.ARTIFACT_UPDATED_V1:
            self._handle_updated(envelope, artifact)

    def _handle_created(self, envelope: EventEnvelope, artifact) -> None:
        existing = self._store.get_page_id(artifact.artifact_id)
        if existing:
            log.info(
                "Artifact %s already has page %s; converting create to patch.",
                artifact.artifact_id,
                existing,
            )
            self._mgr.patch_page(existing, artifact)
            return

        page_id = self._mgr.create_page(artifact)
        self._store.set_page_id(artifact.artifact_id, page_id)

    def _handle_updated(self, envelope: EventEnvelope, artifact) -> None:
        page_id = self._store.get_page_id(artifact.artifact_id)
        if page_id is None:
            log.warning(
                "Received UPDATED event for unknown artifact %s; creating new page.",
                artifact.artifact_id,
            )
            page_id = self._mgr.create_page(artifact)
            self._store.set_page_id(artifact.artifact_id, page_id)
            return

        self._mgr.patch_page(page_id, artifact)
