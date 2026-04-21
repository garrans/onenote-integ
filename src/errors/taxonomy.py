"""
I-T01: Retryable vs terminal error taxonomy.

All application errors descend from `OneNoteIntegError`.
The hierarchy encodes retry intent:
  - RetryableError  → caller SHOULD retry (transient)
  - TerminalError   → caller MUST NOT retry (dead-letter the message)

Graph-specific subtypes re-export from here so callers only need this module.
"""

from __future__ import annotations


class OneNoteIntegError(Exception):
    """Base class for all integration errors."""


# ---------------------------------------------------------------------------
# Retryable branch
# ---------------------------------------------------------------------------

class RetryableError(OneNoteIntegError):
    """
    Transient failure — the operation may succeed if retried after a delay.

    Callers should honour the optional `retry_after_seconds` hint if present.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class GraphThrottledError(RetryableError):
    """Graph returned 429 Too Many Requests."""

    def __init__(self, message: str = "Graph throttled", *, retry_after_seconds: float = 30.0) -> None:
        super().__init__(message, retry_after_seconds=retry_after_seconds)


class GraphTransientError(RetryableError):
    """Graph returned a transient 5xx error."""

    def __init__(self, message: str = "Graph transient error", *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class BusPublishError(RetryableError):
    """Service Bus publish failed (transient connectivity)."""


class TokenRefreshError(RetryableError):
    """MSAL token refresh failed (usually transient)."""


# ---------------------------------------------------------------------------
# Terminal branch
# ---------------------------------------------------------------------------

class TerminalError(OneNoteIntegError):
    """
    Non-transient failure — retrying will not help.
    The calling bus consumer must dead-letter the message.
    """


class SchemaValidationError(TerminalError):
    """Incoming payload failed JSON Schema or Pydantic validation."""

    def __init__(self, message: str, *, raw_payload: object = None) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload


class UnsupportedVersionError(TerminalError):
    """Event schema version is not supported by this release."""

    def __init__(self, version: str) -> None:
        super().__init__(f"Unsupported schema version: {version!r}")
        self.version = version


class MappingNotFoundError(TerminalError):
    """Artifact↔page mapping is required but absent (data integrity issue)."""

    def __init__(self, artifact_id: str) -> None:
        super().__init__(f"No page mapping for artifact {artifact_id!r}")
        self.artifact_id = artifact_id


class GraphPermanentError(TerminalError):
    """Graph returned a non-retryable 4xx error (not 429)."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConflictError(TerminalError):
    """
    A user-owned OneNote block was modified externally in a way that
    conflicts with an incoming artifact update.

    The conflict must be resolved by a human or reconciliation task.
    """

    def __init__(self, page_id: str, artifact_id: str, *, detail: str = "") -> None:
        msg = f"Conflict on page {page_id!r} (artifact {artifact_id!r})"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
        self.page_id = page_id
        self.artifact_id = artifact_id
        self.detail = detail
