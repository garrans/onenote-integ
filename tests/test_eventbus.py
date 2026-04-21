# C-T06: Unit tests for publisher/subscriber round-trip with test doubles.

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.eventbus.bus import EventBusError, IEventPublisher, IEventSubscriber, ServiceBusPublisher
from src.eventbus.envelope import EventEnvelope, EventType


# ---------------------------------------------------------------------------
# In-memory test doubles (no Azure SDK needed)
# ---------------------------------------------------------------------------

class InMemoryPublisher(IEventPublisher):
    """Test double: accumulates published envelopes in a list."""

    def __init__(self):
        self.published: list[EventEnvelope] = []

    def publish(self, envelope: EventEnvelope) -> None:
        self.published.append(envelope)

    def close(self) -> None:
        pass


class InMemorySubscriber(IEventSubscriber):
    """Test double: delivers a preset list of envelopes to the handler."""

    def __init__(self, envelopes: list[EventEnvelope]):
        self._envelopes = envelopes
        self.acked: list[str] = []
        self.deadlettered: list[str] = []

    def subscribe(self, handler) -> None:
        for env in self._envelopes:
            try:
                handler(env)
                self.acked.append(env.event_id)
            except Exception:
                self.deadlettered.append(env.event_id)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# EventEnvelope
# ---------------------------------------------------------------------------

class TestEventEnvelope:
    def test_defaults_are_generated(self):
        env = EventEnvelope(
            event_type=EventType.ARTIFACT_CREATED_V1,
            source_system="test",
        )
        assert env.event_id
        assert env.correlation_id
        assert env.timestamp.tzinfo is not None

    def test_immutable(self):
        env = EventEnvelope(
            event_type=EventType.ARTIFACT_CREATED_V1,
            source_system="test",
        )
        with pytest.raises(Exception):
            env.event_id = "changed"  # type: ignore[misc]

    def test_with_correlation(self):
        env = EventEnvelope(
            event_type=EventType.ARTIFACT_CREATED_V1,
            source_system="test",
        )
        new_env = env.with_correlation("parent-correlation-id")
        assert new_env.correlation_id == "parent-correlation-id"
        assert new_env.event_id == env.event_id  # only correlation changed

    def test_payload_roundtrip(self):
        payload = {"artifactId": "abc-123", "version": 2}
        env = EventEnvelope(
            event_type=EventType.ARTIFACT_UPDATED_V1,
            source_system="source-connector",
            payload=payload,
        )
        restored = EventEnvelope.model_validate_json(env.model_dump_json())
        assert restored.payload == payload

    def test_invalid_schema_version_raises(self):
        with pytest.raises(Exception):
            EventEnvelope(
                event_type=EventType.ARTIFACT_CREATED_V1,
                source_system="test",
                schema_version="bad",
            )

    def test_all_event_types_are_valid_strings(self):
        for et in EventType:
            env = EventEnvelope(event_type=et, source_system="test")
            assert env.event_type == et


# ---------------------------------------------------------------------------
# Publisher round-trip via in-memory double
# ---------------------------------------------------------------------------

class TestInMemoryPublisher:
    def test_publish_stores_envelope(self):
        pub = InMemoryPublisher()
        env = EventEnvelope(
            event_type=EventType.ARTIFACT_CREATED_V1,
            source_system="test",
        )
        pub.publish(env)
        assert len(pub.published) == 1
        assert pub.published[0].event_id == env.event_id

    def test_context_manager_closes(self):
        with InMemoryPublisher() as pub:
            pub.publish(
                EventEnvelope(
                    event_type=EventType.ARTIFACT_DELETED_V1,
                    source_system="test",
                )
            )
        assert len(pub.published) == 1


# ---------------------------------------------------------------------------
# Subscriber round-trip via in-memory double
# ---------------------------------------------------------------------------

class TestInMemorySubscriber:
    def _make_envelope(self, event_type=EventType.ONENOTE_PAGE_EDITED_V1) -> EventEnvelope:
        return EventEnvelope(event_type=event_type, source_system="change-monitor")

    def test_handler_called_for_each_message(self):
        envs = [self._make_envelope(), self._make_envelope()]
        received = []
        sub = InMemorySubscriber(envs)
        sub.subscribe(received.append)
        assert len(received) == 2

    def test_successful_handler_acks(self):
        env = self._make_envelope()
        sub = InMemorySubscriber([env])
        sub.subscribe(lambda e: None)
        assert env.event_id in sub.acked
        assert env.event_id not in sub.deadlettered

    def test_failing_handler_deadletters(self):
        env = self._make_envelope()
        sub = InMemorySubscriber([env])

        def bad_handler(_):
            raise ValueError("processing error")

        sub.subscribe(bad_handler)
        assert env.event_id in sub.deadlettered
        assert env.event_id not in sub.acked


# ---------------------------------------------------------------------------
# ServiceBusPublisher — construction guard (no real SDK)
# ---------------------------------------------------------------------------

class TestServiceBusPublisherGuard:
    def test_raises_runtime_error_when_sdk_missing(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "azure.servicebus", None)
        with pytest.raises((RuntimeError, ImportError)):
            ServiceBusPublisher(
                connection_string="Endpoint=sb://fake/",
                topic_name="events",
            )
