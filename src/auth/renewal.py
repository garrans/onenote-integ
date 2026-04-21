"""
B-T04: Token renewal background task.

Starts a daemon thread that proactively refreshes the access token before it
expires, so callers never block on a token refresh at runtime.

Usage:
    provider = ServiceAccountTokenProvider(...)
    renewal = TokenRenewalTask(provider, poll_interval_seconds=120)
    renewal.start()
    # ... application lifetime ...
    renewal.stop()
"""

from __future__ import annotations

import logging
import threading
import time

from src.auth.interfaces import ITokenProvider, TokenExpiredError, TokenProviderError

log = logging.getLogger(__name__)


class TokenRenewalTask:
    """
    Background daemon thread that keeps the token cache warm.

    The thread wakes every *poll_interval_seconds* and calls
    ``provider.get_token()``.  Because ``get_token`` only refreshes when the
    cached token is near expiry, this is safe to call frequently.

    Args:
        provider:               The token provider to keep warm.
        poll_interval_seconds:  How often (in seconds) to check the token.
                                Default: 120 (check every 2 min).
    """

    def __init__(
        self,
        provider: ITokenProvider,
        *,
        poll_interval_seconds: float = 120,
    ) -> None:
        self._provider = provider
        self._poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background renewal thread."""
        if self._thread and self._thread.is_alive():
            log.warning("TokenRenewalTask already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="token-renewal",
            daemon=True,
        )
        self._thread.start()
        log.info("TokenRenewalTask started (poll_interval=%ss).", self._poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the renewal thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info("TokenRenewalTask stopped.")

    def _loop(self) -> None:
        while not self._stop_event.wait(timeout=self._poll_interval):
            try:
                self._provider.get_token()
                log.debug("Background token refresh completed.")
            except TokenExpiredError:
                log.critical(
                    "Refresh token has expired. Manual intervention required "
                    "to re-seed the Key Vault secret."
                )
                self._stop_event.set()
                break
            except TokenProviderError as exc:
                # Log but keep retrying — transient network errors should recover.
                log.warning("Token renewal failed (will retry): %s", exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("Unexpected error in token renewal loop: %s", exc)
