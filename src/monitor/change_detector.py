"""
H-T02 + H-T03: Content hash comparison and change event publisher.

ChangeDetector receives ChangeEvents from any change source (webhook or polling),
compares the HTML content hash against the State Store, and publishes an
`onenote.page.edited.v1` bus event if a real change is detected.
"""

from __future__ import annotations

import logging

from src.eventbus.bus import IEventPublisher
from src.eventbus.envelope import EventEnvelope, EventType
from src.monitor.change_source import ChangeEvent
from src.state.store import IContentHashStore

log = logging.getLogger(__name__)


class ChangeDetector:
    """
    H-T02: Compare incoming content hash against stored hash.
    H-T03: If changed, publish an `ONENOTE_PAGE_EDITED_V1` event.

    The event payload contains:
        pageId (str): the OneNote page ID.
        artifactId (str): the linked artifact ID.
        contentHash (str): the new content hash.

    The publisher is responsible for delivering the event to the bus.
    """

    def __init__(
        self,
        hash_store: IContentHashStore,
        publisher: IEventPublisher,
    ) -> None:
        self._hash_store = hash_store
        self._publisher = publisher

    def handle_change_event(self, event: ChangeEvent) -> None:
        """
        Process a ChangeEvent from any change source.

        1. Compute hash of event.raw_html.
        2. Compare with stored hash for event.page_id.
        3. If different (or first time), update stored hash and publish.
        """
        if self._hash_store.matches(event.page_id, event.raw_html):
            log.debug(
                "No content change detected for page %s (artifact %s); skipping.",
                event.page_id,
                event.artifact_id,
            )
            return

        # Hash changed — update store.
        stored = self._hash_store.upsert(event.page_id, event.raw_html)
        log.info(
            "Content hash changed for page %s (artifact %s); publishing event.",
            event.page_id,
            event.artifact_id,
        )

        envelope = EventEnvelope(
            event_type=EventType.ONENOTE_PAGE_EDITED_V1,
            schema_version="1.0",
            source_system="onenote",
            payload={
                "pageId": event.page_id,
                "artifactId": event.artifact_id,
                "contentHash": stored.sha256_hex,
            },
        )
        self._publisher.publish(envelope)
