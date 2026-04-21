"""
E-T01 / E-T02: Connector base interface and registration mechanism.

Connectors are lightweight adapters that translate external system events
into canonical NoteArtifact bus events, and vice-versa for bidirectional sync.

The registry follows a plug-in pattern: adding or removing a connector
requires only registering/unregistering it — no changes to core pipeline code.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from src.eventbus.envelope import EventEnvelope, EventType
from src.schema.note_artifact import NoteArtifact

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# E-T01: Connector base interface
# ---------------------------------------------------------------------------

class IConnector(ABC):
    """
    Contract for all source-system connectors.

    Each connector:
    - Knows how to translate its source system's data into a NoteArtifact.
    - Publishes artifact events to the Event Bus.
    - Can receive `onenote.page.edited/created/deleted` events and propagate
      them back to its source system (bidirectional sync).

    Implementations must be stateless enough to be instantiated fresh per
    event, OR manage their own internal state thread-safely.
    """

    #: Human-readable name, used as the sourceSystem field in NoteArtifact.
    #: Must be unique across all registered connectors.
    source_system: ClassVar[str]

    @abstractmethod
    def to_note_artifact(self, source_data: dict) -> NoteArtifact:
        """
        Translate *source_data* (connector-specific dict) into a NoteArtifact.

        Raises:
            ConnectorError: if translation fails.
        """

    @abstractmethod
    def handle_onenote_event(self, envelope: EventEnvelope) -> None:
        """
        React to a OneNote-originated event by updating the source system.

        Only called for events whose sourceSystem does NOT match this connector
        (prevents infinite loops). For event types this connector doesn't care
        about, implementations should silently return.

        Raises:
            ConnectorError: if the back-propagation fails.
        """


class ConnectorError(Exception):
    """Raised when a connector operation fails."""


# ---------------------------------------------------------------------------
# E-T02: Connector registry
# ---------------------------------------------------------------------------

class ConnectorRegistry:
    """
    Plug-in registry for connectors.

    Connectors are registered by their `source_system` name. Adding or
    removing a connector is a single `register`/`unregister` call with
    zero changes to the event bus or renderer.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, IConnector] = {}

    def register(self, connector: IConnector) -> None:
        """Register *connector*. Raises ValueError on duplicate source_system."""
        key = connector.source_system
        if key in self._connectors:
            raise ValueError(
                f"A connector for source_system '{key}' is already registered. "
                "Unregister it first."
            )
        self._connectors[key] = connector
        log.info("Registered connector: %s", key)

    def unregister(self, source_system: str) -> None:
        """Remove the connector for *source_system*. Raises KeyError if not found."""
        if source_system not in self._connectors:
            raise KeyError(f"No connector registered for source_system '{source_system}'.")
        del self._connectors[source_system]
        log.info("Unregistered connector: %s", source_system)

    def get(self, source_system: str) -> IConnector:
        """Retrieve the connector for *source_system*. Raises KeyError if not found."""
        try:
            return self._connectors[source_system]
        except KeyError:
            raise KeyError(f"No connector registered for source_system '{source_system}'.")

    def all(self) -> list[IConnector]:
        """Return all registered connectors."""
        return list(self._connectors.values())

    def source_systems(self) -> list[str]:
        """Return all registered source system names."""
        return list(self._connectors.keys())

    def __len__(self) -> int:
        return len(self._connectors)
