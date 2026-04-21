"""
B-T01: Token provider interface.

Defines the contract all auth implementations must satisfy.
Concrete implementations live in token_provider.py (B-T02).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AccessToken:
    """Immutable value object for an acquired access token."""

    value: str
    expires_at: datetime
    scopes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def expires_in_seconds(self) -> float:
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(delta.total_seconds(), 0.0)


class TokenProviderError(Exception):
    """Raised when a token cannot be acquired or refreshed."""


class TokenExpiredError(TokenProviderError):
    """Raised when the stored refresh token has expired and cannot be renewed."""


class ITokenProvider(ABC):
    """
    Contract for service account delegated auth token providers.

    Implementations must be thread-safe.
    """

    @abstractmethod
    def get_token(self) -> AccessToken:
        """
        Return a valid access token, refreshing it if necessary.

        Raises:
            TokenProviderError: on any acquisition failure.
            TokenExpiredError:  when the refresh token itself has expired.
        """

    @abstractmethod
    def revoke(self) -> None:
        """
        Discard cached tokens, forcing a full re-acquisition on the next call.

        Use during graceful shutdown or after a security event.
        """
