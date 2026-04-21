"""
F-T02: Retry policy for transient Graph errors (429, 503).

Provides a simple exponential-back-off retry wrapper that:
- Honours the Retry-After header on 429 responses (via GraphThrottledError).
- Applies jittered exponential back-off on 503 / transient errors.
- Raises immediately on non-retryable GraphError (4xx except 429).
- Calls an optional sleep_fn so tests can run instantly without monkeypatching time.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from src.renderer.graph_adapter import GraphError, GraphThrottledError, GraphTransientError

log = logging.getLogger(__name__)

_T = TypeVar("_T")

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_BASE_DELAY_S = 1.0
_DEFAULT_MAX_DELAY_S = 60.0


def with_retry(
    func: Callable[[], _T],
    *,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = _DEFAULT_BASE_DELAY_S,
    max_delay_s: float = _DEFAULT_MAX_DELAY_S,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> _T:
    """
    Call *func* with exponential-back-off retry on transient Graph errors.

    Parameters:
        func: Zero-argument callable that performs a Graph API call.
        max_attempts: Total attempts before re-raising the last error.
        base_delay_s: Seconds to wait before the second attempt (doubles each time).
        max_delay_s: Upper bound on any single wait.
        sleep_fn: Injectable sleep function (use ``lambda s: None`` in tests).

    Returns:
        The return value of *func* on success.

    Raises:
        GraphThrottledError | GraphTransientError: if all retries are exhausted.
        GraphError: immediately (non-retryable).
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except GraphThrottledError as exc:
            last_exc = exc
            wait = min(exc.retry_after_seconds + random.uniform(0, 2), max_delay_s)
            log.warning(
                "Graph 429 throttled (attempt %d/%d); sleeping %.1fs",
                attempt,
                max_attempts,
                wait,
            )
        except GraphTransientError as exc:
            last_exc = exc
            wait = min(base_delay_s * (2 ** (attempt - 1)) + random.uniform(0, 1), max_delay_s)
            log.warning(
                "Graph transient error (attempt %d/%d): %s; sleeping %.1fs",
                attempt,
                max_attempts,
                exc,
                wait,
            )
        except GraphError:
            # Non-retryable (4xx, auth errors, etc.)
            raise

        if attempt < max_attempts:
            sleep_fn(wait)

    raise last_exc  # type: ignore[misc]
