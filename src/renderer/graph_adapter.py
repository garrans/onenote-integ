"""
F-T01: Graph transport adapter interface.

Defines the contract for communicating with the Microsoft Graph OneNote API.
Concrete implementations can use httpx, requests, or the Graph SDK.
Tests use the InMemoryGraphAdapter stub.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GraphResponse:
    """Parsed response from a Graph API call."""
    status_code: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


class GraphError(Exception):
    """Raised when a Graph call fails non-transiently."""
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphThrottledError(GraphError):
    """Raised on HTTP 429 Too Many Requests.  Caller should retry after retry_after_seconds."""
    def __init__(self, retry_after_seconds: int = 30) -> None:
        super().__init__(f"Graph API throttled; retry after {retry_after_seconds}s", 429)
        self.retry_after_seconds = retry_after_seconds


class GraphTransientError(GraphError):
    """Raised on HTTP 503 Service Unavailable or similar recoverable errors."""


class IGraphAdapter(ABC):
    """
    Abstract contract for Microsoft Graph OneNote API transport.

    All methods accept and return plain Python types; no SDK objects.
    Bearer token injection is the responsibility of the concrete implementation.
    """

    @abstractmethod
    def get_page(self, page_id: str) -> GraphResponse:
        """
        GET the OneNote page metadata for *page_id*.

        Returns:
            GraphResponse with page JSON in .body.
        Raises:
            GraphError on non-transient errors (4xx except 429).
            GraphThrottledError on 429.
            GraphTransientError on 503.
        """

    @abstractmethod
    def get_page_content(self, page_id: str) -> str:
        """
        GET the raw HTML content of *page_id*.

        Returns:
            HTML string.
        Raises:
            GraphError, GraphThrottledError, GraphTransientError.
        """

    @abstractmethod
    def create_page(
        self,
        section_id: str,
        html_body: str,
        title: str,
    ) -> GraphResponse:
        """
        POST a new OneNote page into *section_id*.

        Returns:
            GraphResponse with the created page JSON (includes 'id').
        Raises:
            GraphError, GraphThrottledError, GraphTransientError.
        """

    @abstractmethod
    def patch_page(
        self,
        page_id: str,
        patch_commands: list[dict[str, Any]],
    ) -> GraphResponse:
        """
        PATCH a OneNote page with *patch_commands*.

        Each command is a dict following the Graph OneNote PATCH schema:
        {"target": "<data-id>", "action": "replace", "content": "<p>…</p>"}

        Returns:
            GraphResponse (typically 204 No Content).
        Raises:
            GraphError, GraphThrottledError, GraphTransientError.
        """

    @abstractmethod
    def get_section_id(self, notebook_name: str, section_name: str) -> str:
        """
        Resolve a human-readable (notebook_name, section_name) pair to a
        Graph section ID, creating the notebook/section if they don't exist.

        Returns:
            Graph section ID string.
        Raises:
            GraphError on failure.
        """
