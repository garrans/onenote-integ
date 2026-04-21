"""
E-T03: Reference connector — "InspectionsApp" stub.

This connector demonstrates the plug-in pattern:
- Translates a fictional InspectionsApp record into a NoteArtifact.
- Handles OneNote edit events by logging them (stub implementation;
  real write-back to InspectionsApp would go here).

It is self-contained and can be removed by simply not registering it
without affecting the event bus, renderer, or any other connector.
"""

from __future__ import annotations

import logging

from src.connectors.base import ConnectorError, IConnector
from src.eventbus.envelope import EventEnvelope
from src.schema.note_artifact import NoteArtifact, Routing, Timestamps

log = logging.getLogger(__name__)


class InspectionsAppConnector(IConnector):
    """
    Reference connector for the InspectionsApp source system.

    Expected source_data keys:
        id (str): Inspection record ID.
        title (str): Inspection title.
        description (str): Inspection description (HTML or plain text).
        status (str): e.g., 'open', 'closed'.
        assigned_to (str, optional): Assignee name.
        created_at (str, optional): ISO-8601 datetime.
        updated_at (str, optional): ISO-8601 datetime.
    """

    source_system = "InspectionsApp"

    def to_note_artifact(self, source_data: dict) -> NoteArtifact:
        try:
            record_id = str(source_data["id"])
            title = str(source_data["title"])
            description = str(source_data.get("description", ""))
            status = source_data.get("status", "unknown")
        except KeyError as exc:
            raise ConnectorError(
                f"InspectionsApp source_data missing required field: {exc}"
            ) from exc

        people = []
        if assigned_to := source_data.get("assigned_to"):
            people = [{"name": assigned_to, "role": "assignedTo"}]

        timestamps_data = None
        if source_data.get("created_at"):
            ts: dict = {"created": source_data["created_at"]}
            if source_data.get("updated_at"):
                ts["lastUpdated"] = source_data["updated_at"]
            timestamps_data = Timestamps.model_validate(ts)

        body = f"<p><strong>Status:</strong> {status}</p>\n{description}"

        return NoteArtifact.model_validate(
            {
                "version": "1.0",
                "artifactId": f"inspections-{record_id}",
                "sourceSystem": self.source_system,
                "sourceRecordId": record_id,
                "title": title,
                "body": body,
                "people": [p for p in ([{"name": a, "role": "assignedTo"} for a in [source_data.get("assigned_to")] if a])],
                "routing": {
                    "notebookName": "Operations",
                    "sectionName": "Inspections",
                    "template": "default",
                },
                **({"timestamps": timestamps_data.model_dump(by_alias=True)} if timestamps_data else {}),
            }
        )

    def handle_onenote_event(self, envelope: EventEnvelope) -> None:
        # Stub: log receipt; real implementation would write back to InspectionsApp.
        log.info(
            "InspectionsApp connector received OneNote event %s [id=%s] — write-back not yet implemented.",
            envelope.event_type.value,
            envelope.event_id,
        )
