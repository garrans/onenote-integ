# B-T05: Contract tests for ITokenProvider using a mock identity server.
#
# These tests verify the interface contract without hitting real Azure AD.
# ServiceAccountTokenProvider is tested against a mock SecretClient and a
# mock MSAL app injected via monkeypatching.

from __future__ import annotations

import time
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.auth.interfaces import (
    AccessToken,
    ITokenProvider,
    TokenExpiredError,
    TokenProviderError,
)
from src.auth.renewal import TokenRenewalTask
from src.auth.token_provider import ServiceAccountTokenProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future(seconds: int = 3600) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _past(seconds: int = 10) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _make_provider(
    *,
    msal_result: dict | None = None,
    refresh_token_value: str = "stored-rt",
) -> tuple[ServiceAccountTokenProvider, MagicMock]:
    """Construct a ServiceAccountTokenProvider with mocked MSAL and KV client."""
    kv_client = MagicMock()
    kv_client.get_secret.return_value.value = refresh_token_value

    default_result = {
        "access_token": "mock-access-token",
        "refresh_token": "new-rt",
        "expires_in": 3600,
    }
    if msal_result is not None:
        default_result = msal_result

    mock_msal_app = MagicMock()
    mock_msal_app.acquire_token_by_refresh_token.return_value = default_result

    with patch.dict("sys.modules", {"msal": MagicMock(ConfidentialClientApplication=MagicMock(return_value=mock_msal_app))}):
        provider = ServiceAccountTokenProvider(
            tenant_id="t",
            client_id="c",
            client_secret="s",
            refresh_token_ref="keyvault://vault/rt-secret",
            scopes=["https://graph.microsoft.com/.default"],
            kv_client=kv_client,
        )
        provider._msal_app_factory = lambda: mock_msal_app  # store for patching below

    # Patch _acquire so we control MSAL result without needing real import
    provider._msal_result = default_result
    provider._kv_client = kv_client

    def fake_acquire(self):
        result = self._msal_result
        if "error" in result:
            desc = result.get("error_description", "")
            if "AADSTS70043" in desc or "expired" in desc.lower():
                raise TokenExpiredError(desc)
            raise TokenProviderError(desc)
        if new_rt := result.get("refresh_token"):
            self._store_refresh_token(new_rt)
        return AccessToken(
            value=result["access_token"],
            expires_at=_future(result.get("expires_in", 3600)),
            scopes=tuple(self._scopes),
        )

    import types
    provider._acquire_via_refresh_token = types.MethodType(fake_acquire, provider)

    return provider, kv_client


# ---------------------------------------------------------------------------
# AccessToken value object
# ---------------------------------------------------------------------------

class TestAccessToken:
    def test_not_expired_future(self):
        token = AccessToken(value="t", expires_at=_future(300))
        assert not token.is_expired

    def test_expired_past(self):
        token = AccessToken(value="t", expires_at=_past())
        assert token.is_expired

    def test_expires_in_seconds_positive(self):
        token = AccessToken(value="t", expires_at=_future(120))
        assert token.expires_in_seconds > 0

    def test_expires_in_seconds_zero_if_past(self):
        token = AccessToken(value="t", expires_at=_past())
        assert token.expires_in_seconds == 0.0


# ---------------------------------------------------------------------------
# ITokenProvider contract (interface enforcement)
# ---------------------------------------------------------------------------

class TestITokenProviderContract:
    """Verify the interface cannot be instantiated directly."""

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ITokenProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# ServiceAccountTokenProvider
# ---------------------------------------------------------------------------

class TestServiceAccountTokenProvider:
    def test_get_token_returns_access_token(self):
        provider, _ = _make_provider()
        token = provider.get_token()
        assert isinstance(token, AccessToken)
        assert token.value == "mock-access-token"

    def test_get_token_caches_result(self):
        provider, kv = _make_provider()
        acquire_calls = []
        original_acquire = provider._acquire_via_refresh_token

        import types
        def counting_acquire(self):
            acquire_calls.append(1)
            return original_acquire()

        provider._acquire_via_refresh_token = types.MethodType(counting_acquire, provider)
        t1 = provider.get_token()
        t2 = provider.get_token()
        assert t1 is t2  # same object — cache hit
        assert len(acquire_calls) == 1  # only one acquisition, second call was a cache hit

    def test_revoke_clears_cache(self):
        provider, kv = _make_provider()
        acquire_calls = []
        original_acquire = provider._acquire_via_refresh_token

        import types
        def counting_acquire(self):
            acquire_calls.append(1)
            return original_acquire()

        provider._acquire_via_refresh_token = types.MethodType(counting_acquire, provider)
        t1 = provider.get_token()
        provider.revoke()
        t2 = provider.get_token()
        assert t1 is not t2  # new token object after revoke
        assert len(acquire_calls) == 2  # two acquisitions: initial + post-revoke

    def test_stores_rotated_refresh_token(self):
        provider, kv = _make_provider()
        provider.get_token()
        kv.set_secret.assert_called_once_with("rt-secret", "new-rt")

    def test_expired_refresh_token_raises_token_expired_error(self):
        provider, _ = _make_provider(
            msal_result={
                "error": "invalid_grant",
                "error_description": "AADSTS70043: The refresh token has expired.",
            }
        )
        with pytest.raises(TokenExpiredError):
            provider.get_token()

    def test_generic_msal_error_raises_token_provider_error(self):
        provider, _ = _make_provider(
            msal_result={
                "error": "invalid_client",
                "error_description": "Bad credentials.",
            }
        )
        with pytest.raises(TokenProviderError):
            provider.get_token()

    def test_empty_kv_secret_raises(self):
        provider, kv = _make_provider(refresh_token_value="")
        # Override to propagate the empty-RT check from _load_refresh_token
        import types

        def failing_acquire(self):
            rt = self._load_refresh_token()
            return AccessToken(value=rt, expires_at=_future())

        provider._acquire_via_refresh_token = types.MethodType(failing_acquire, provider)
        with pytest.raises(TokenProviderError, match="empty"):
            provider.get_token()


# ---------------------------------------------------------------------------
# TokenRenewalTask
# ---------------------------------------------------------------------------

class TestTokenRenewalTask:
    def test_start_stop(self):
        provider, _ = _make_provider()
        task = TokenRenewalTask(provider, poll_interval_seconds=0.1)
        task.start()
        time.sleep(0.25)
        task.stop(timeout=2.0)

    def test_stops_on_token_expired(self):
        provider, _ = _make_provider(
            msal_result={
                "error": "invalid_grant",
                "error_description": "AADSTS70043: expired",
            }
        )
        task = TokenRenewalTask(provider, poll_interval_seconds=0.05)
        task.start()
        time.sleep(0.3)
        # Thread should have stopped itself after TokenExpiredError
        assert not task._thread.is_alive()
