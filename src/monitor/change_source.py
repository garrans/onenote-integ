"""
H-T01: Graph webhook subscription management for OneNote page change notifications.
H-T01b: Polling fallback (checks lastModifiedTime and content hash on interval).

Design decisions:
- Webhook and polling are independent strategies behind a common IChangeSource interface.
- At startup, the monitor tries to register a webhook. If Graph denies it (permissions,
  network, policy), it falls back to polling silently.
- Both strategies emit ChangeEvent objects which are consumed by the ChangeDetector (H-T02+H-T03).
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from src.renderer.graph_adapter import GraphError, IGraphAdapter

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChangeEvent:
    """
    Notification that a OneNote page may have changed.

    The event carries the page ID and the raw HTML content snapshot
    so the ChangeDetector can hash-compare without a second Graph call.
    """

    page_id: str
    artifact_id: str          # resolved from page_id by mapping store
    raw_html: str             # page content at time of detection
    detected_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


ChangeHandler = Callable[[ChangeEvent], None]


# ---------------------------------------------------------------------------
# H-T01: Webhook subscription (stub — full Graph subscription API needed)
# ---------------------------------------------------------------------------

class WebhookSubscriptionManager:
    """
    Manages a Graph change-notification subscription for OneNote pages.

    On `subscribe()` the manager registers a webhook with Graph and stores
    the subscription ID for renewal. Renewal must happen before expiry
    (Graph subscriptions expire in ~3 days for OneNote).

    This is a structural stub: the actual HTTP calls are delegated to the
    IGraphAdapter; a production adapter would call
    POST /subscriptions and PATCH /subscriptions/{id}.
    """

    _SUBSCRIPTION_RESOURCE = "me/onenote/pages"
    _CHANGE_TYPE = "updated,created,deleted"
    _EXPIRY_MINUTES = 4230  # ~3 days (Graph max for OneNote)

    def __init__(self, adapter: IGraphAdapter, notification_url: str) -> None:
        self._adapter = adapter
        self._notification_url = notification_url
        self._subscription_id: str | None = None

    def subscribe(self) -> str:
        """
        Register the webhook with Graph.

        Returns the Graph subscription ID.
        Raises GraphError on failure.
        """
        # Graph POST /subscriptions is not in the minimal IGraphAdapter interface;
        # production adapter adds it.  Here we call a generic extension point.
        response = self._adapter.get_section_id("_webhook_register_", self._notification_url)
        # In production, parse subscription.id from the response body.
        self._subscription_id = f"sub-{id(self)}"
        log.info("Registered OneNote webhook subscription: %s", self._subscription_id)
        return self._subscription_id

    def renew(self) -> None:
        """Renew the subscription before it expires."""
        if self._subscription_id is None:
            raise RuntimeError("No active subscription to renew.")
        log.info("Renewed webhook subscription: %s", self._subscription_id)

    def unsubscribe(self) -> None:
        """Delete the subscription from Graph."""
        if self._subscription_id:
            log.info("Unsubscribed webhook: %s", self._subscription_id)
            self._subscription_id = None


# ---------------------------------------------------------------------------
# H-T01b: Polling fallback
# ---------------------------------------------------------------------------

class PollingMonitor:
    """
    Polls known OneNote pages for changes by comparing content hashes.

    H-T01b: runs as a daemon thread; on each interval fetches HTML for every
    tracked page_id and emits a ChangeEvent if the hash has changed.

    The caller registers a ChangeHandler to receive events.
    The mapping store (provided externally) supplies the list of tracked pages.
    """

    def __init__(
        self,
        adapter: IGraphAdapter,
        get_tracked_pages: Callable[[], list[tuple[str, str]]],
        # list of (artifact_id, page_id) tuples
        handler: ChangeHandler,
        *,
        poll_interval_seconds: float = 300.0,
    ) -> None:
        self._adapter = adapter
        self._get_tracked_pages = get_tracked_pages
        self._handler = handler
        self._poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_hashes: dict[str, str] = {}

    def start(self) -> None:
        """Start the polling thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="PollingMonitor")
        self._thread.start()
        log.info("PollingMonitor started (interval=%.0fs)", self._poll_interval)

    def stop(self) -> None:
        """Signal the polling thread to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        log.info("PollingMonitor stopped.")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(self._poll_interval)

    def _poll_once(self) -> None:
        import hashlib

        for artifact_id, page_id in self._get_tracked_pages():
            try:
                html = self._adapter.get_page_content(page_id)
                digest = hashlib.sha256(html.encode()).hexdigest()
                prev = self._last_hashes.get(page_id)
                if prev != digest:
                    self._last_hashes[page_id] = digest
                    if prev is not None:  # Don't fire on first observation.
                        evt = ChangeEvent(
                            page_id=page_id,
                            artifact_id=artifact_id,
                            raw_html=html,
                        )
                        log.info("Change detected on page %s (artifact %s)", page_id, artifact_id)
                        self._handler(evt)
            except GraphError as exc:
                log.warning("Poll failed for page %s: %s", page_id, exc)
