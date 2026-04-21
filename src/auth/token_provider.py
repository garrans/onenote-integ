"""
B-T02 / B-T03: Service account OAuth token acquisition and secure token storage.

Flow (seeded-refresh-token path — ADR accepted):
  1. First call: load refresh token from Key Vault (via B-T03 storage).
  2. Use MSAL to exchange the refresh token for a fresh access + refresh token pair.
  3. Store the new refresh token back in Key Vault.
  4. Cache the access token in process memory until ~60 s before expiry.
  5. On subsequent calls within the cache window: return cached access token.

Dependencies:
  - pip/uv: msal, azure-keyvault-secrets, azure-identity
    (added in Area B commit — not yet in pyproject.toml at Area A stage)
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.keyvault.secrets import SecretClient

from src.auth.interfaces import AccessToken, ITokenProvider, TokenExpiredError, TokenProviderError
from src.config.keyvault import parse_keyvault_ref

log = logging.getLogger(__name__)

# Refresh the access token this many seconds before it actually expires.
_REFRESH_BUFFER_SECONDS = 60


class ServiceAccountTokenProvider(ITokenProvider):
    """
    MSAL-backed token provider for service account delegated auth.

    The refresh token is persisted in Azure Key Vault so it survives restarts.
    Access tokens are cached in process memory.

    Args:
        tenant_id:         Azure AD tenant GUID.
        client_id:         App registration client ID.
        client_secret:     App registration client secret (resolved from KV before construction).
        refresh_token_ref: Key Vault reference string for the refresh token secret.
        scopes:            OAuth scopes to request (e.g. ["https://graph.microsoft.com/.default"]).
        kv_client:         Configured SecretClient to read/write the refresh token.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        refresh_token_ref: str,
        scopes: list[str],
        kv_client: "SecretClient",
    ) -> None:
        try:
            import msal  # noqa: F401 — validated at construction time
        except ImportError as exc:
            raise RuntimeError(
                "msal is required for ServiceAccountTokenProvider. "
                "Add it with: uv add msal"
            ) from exc

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes
        self._kv_client = kv_client
        self._kv_vault, self._kv_secret_name = parse_keyvault_ref(refresh_token_ref)

        self._lock = threading.Lock()
        self._cached_token: AccessToken | None = None

    # ------------------------------------------------------------------
    # ITokenProvider
    # ------------------------------------------------------------------

    def get_token(self) -> AccessToken:
        with self._lock:
            if self._cached_token and not self._near_expiry(self._cached_token):
                return self._cached_token

            log.debug("Acquiring new access token via refresh token exchange.")
            token = self._acquire_via_refresh_token()
            self._cached_token = token
            return token

    def revoke(self) -> None:
        with self._lock:
            self._cached_token = None
            log.info("Cached access token revoked.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _near_expiry(token: AccessToken) -> bool:
        return token.expires_in_seconds < _REFRESH_BUFFER_SECONDS

    def _acquire_via_refresh_token(self) -> AccessToken:
        import msal

        app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
        )

        refresh_token = self._load_refresh_token()

        result = app.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=self._scopes,
        )

        if "error" in result:
            desc = result.get("error_description", "")
            if "AADSTS70043" in desc or "expired" in desc.lower():
                raise TokenExpiredError(
                    f"Refresh token has expired and cannot be renewed: {desc}"
                )
            raise TokenProviderError(
                f"Token acquisition failed [{result['error']}]: {desc}"
            )

        # Persist the rotated refresh token back to Key Vault.
        if new_rt := result.get("refresh_token"):
            self._store_refresh_token(new_rt)

        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=result.get("expires_in", 3600)
        )
        return AccessToken(
            value=result["access_token"],
            expires_at=expires_at,
            scopes=tuple(self._scopes),
        )

    def _load_refresh_token(self) -> str:
        secret = self._kv_client.get_secret(self._kv_secret_name)
        if not secret.value:
            raise TokenProviderError(
                f"Refresh token secret '{self._kv_secret_name}' in vault "
                f"'{self._kv_vault}' is empty."
            )
        return secret.value

    def _store_refresh_token(self, new_token: str) -> None:
        self._kv_client.set_secret(self._kv_secret_name, new_token)
        log.debug("Rotated refresh token stored in Key Vault: %s", self._kv_secret_name)
