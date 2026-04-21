"""
C-T03 / C-T04: Publisher and subscriber abstractions.

Concrete implementations use Azure Service Bus. The abstractions use
dependency injection so unit tests can substitute in-memory test doubles
without touching the real bus.

Dependency: azure-servicebus (not yet in pyproject.toml — added in C commit).
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Callable

from src.eventbus.envelope import EventEnvelope

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-T03: Publisher abstraction
# ---------------------------------------------------------------------------

class IEventPublisher(ABC):
    """Contract for sending events to the bus."""

    @abstractmethod
    def publish(self, envelope: EventEnvelope) -> None:
        """
        Serialize and send *envelope* to the appropriate topic.

        Raises:
            EventBusError: on send failure.
        """

    @abstractmethod
    def close(self) -> None:
        """Release underlying transport resources."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class EventBusError(Exception):
    """Raised when a bus operation fails."""


class ServiceBusPublisher(IEventPublisher):
    """
    Azure Service Bus publisher.

    Sends each envelope as a JSON-serialized Service Bus message.
    The Service Bus topic is selected by the event type.

    Args:
        connection_string: Resolved (not KV reference) Service Bus connection string.
        topic_name:        Service Bus topic to publish to.
    """

    def __init__(self, *, connection_string: str, topic_name: str) -> None:
        try:
            from azure.servicebus import ServiceBusClient, ServiceBusMessage  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "azure-servicebus is required. Add it with: uv add azure-servicebus"
            ) from exc

        from azure.servicebus import ServiceBusClient
        self._client = ServiceBusClient.from_connection_string(connection_string)
        self._sender = self._client.get_topic_sender(topic_name=topic_name)
        self._topic = topic_name

    def publish(self, envelope: EventEnvelope) -> None:
        from azure.servicebus import ServiceBusMessage

        body = envelope.model_dump_json()
        msg = ServiceBusMessage(
            body=body,
            message_id=envelope.event_id,
            subject=envelope.event_type.value,
            application_properties={
                "correlationId": envelope.correlation_id,
                "sourceSystem": envelope.source_system,
                "schemaVersion": envelope.schema_version,
            },
        )
        try:
            self._sender.send_messages(msg)
            log.debug(
                "Published %s [id=%s] to topic '%s'",
                envelope.event_type.value,
                envelope.event_id,
                self._topic,
            )
        except Exception as exc:
            raise EventBusError(
                f"Failed to publish event {envelope.event_id}: {exc}"
            ) from exc

    def close(self) -> None:
        self._sender.close()
        self._client.close()


# ---------------------------------------------------------------------------
# C-T04: Subscriber abstraction
# ---------------------------------------------------------------------------

MessageHandler = Callable[[EventEnvelope], None]


class IEventSubscriber(ABC):
    """Contract for receiving events from the bus."""

    @abstractmethod
    def subscribe(self, handler: MessageHandler) -> None:
        """
        Register *handler* and start receiving messages.

        *handler* is called once per message with the deserialized envelope.
        The message is **acked** if *handler* returns normally, **nacked**
        (deadlettered) if it raises.

        Args:
            handler: Callable that accepts an EventEnvelope.
        """

    @abstractmethod
    def close(self) -> None:
        """Stop receiving and release resources."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class ServiceBusSubscriber(IEventSubscriber):
    """
    Azure Service Bus subscriber (pull mode).

    Receives messages from a topic subscription, deserializes the envelope,
    calls the registered handler, and acks or deadletters based on outcome.

    Args:
        connection_string: Resolved Service Bus connection string.
        topic_name:        Service Bus topic.
        subscription_name: Service Bus topic subscription.
        max_wait_time:     Seconds to wait for a message before returning (default 5).
    """

    def __init__(
        self,
        *,
        connection_string: str,
        topic_name: str,
        subscription_name: str,
        max_wait_time: int = 5,
    ) -> None:
        try:
            from azure.servicebus import ServiceBusClient  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "azure-servicebus is required. Add it with: uv add azure-servicebus"
            ) from exc

        from azure.servicebus import ServiceBusClient
        self._client = ServiceBusClient.from_connection_string(connection_string)
        self._receiver = self._client.get_subscription_receiver(
            topic_name=topic_name,
            subscription_name=subscription_name,
            max_wait_time=max_wait_time,
        )
        self._topic = topic_name
        self._subscription = subscription_name

    def subscribe(self, handler: MessageHandler) -> None:
        """Process one batch of messages (call in a loop for continuous consumption)."""
        for msg in self._receiver:
            body = b"".join(msg.body).decode("utf-8")
            try:
                data = json.loads(body)
                envelope = EventEnvelope.model_validate(data)
                handler(envelope)
                self._receiver.complete_message(msg)
                log.debug(
                    "Acked %s [id=%s] from '%s/%s'",
                    envelope.event_type.value,
                    envelope.event_id,
                    self._topic,
                    self._subscription,
                )
            except Exception as exc:
                log.exception(
                    "Handler failed for message '%s', deadlettering: %s",
                    getattr(msg, "message_id", "?"),
                    exc,
                )
                self._receiver.dead_letter_message(
                    msg,
                    reason="HandlerError",
                    error_description=str(exc)[:2048],
                )

    def close(self) -> None:
        self._receiver.close()
        self._client.close()
