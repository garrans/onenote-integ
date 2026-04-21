# A-T04: Unit tests for config validation and Key Vault reference pattern.

import pytest
from pydantic import ValidationError

from src.config.keyvault import is_keyvault_ref, parse_keyvault_ref, resolve_secret
from src.config.settings import AppSettings, AuthSettings, EventBusSettings, StateStoreSettings


# ---------------------------------------------------------------------------
# AuthSettings
# ---------------------------------------------------------------------------

class TestAuthSettings:
    def _valid_env(self) -> dict:
        return {
            "AUTH_TENANT_ID": "tenant-abc",
            "AUTH_CLIENT_ID": "client-xyz",
            "AUTH_CLIENT_SECRET_REF": "keyvault://my-vault/client-secret",
            "AUTH_REFRESH_TOKEN_REF": "keyvault://my-vault/refresh-token",
        }

    def test_valid(self, monkeypatch):
        for k, v in self._valid_env().items():
            monkeypatch.setenv(k, v)
        s = AuthSettings()
        assert s.tenant_id == "tenant-abc"
        assert s.client_secret_ref.startswith("keyvault://")

    def test_missing_tenant_id_raises(self, monkeypatch):
        env = self._valid_env()
        env.pop("AUTH_TENANT_ID")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValidationError):
            AuthSettings()

    def test_non_keyvault_secret_ref_raises(self, monkeypatch):
        env = self._valid_env()
        env["AUTH_CLIENT_SECRET_REF"] = "plain-text-secret"
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValidationError, match="Key Vault reference"):
            AuthSettings()

    def test_non_keyvault_refresh_token_ref_raises(self, monkeypatch):
        env = self._valid_env()
        env["AUTH_REFRESH_TOKEN_REF"] = "not-a-ref"
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValidationError, match="Key Vault reference"):
            AuthSettings()


# ---------------------------------------------------------------------------
# EventBusSettings
# ---------------------------------------------------------------------------

class TestEventBusSettings:
    def _valid_env(self) -> dict:
        return {
            "EVENTBUS_CONNECTION_STRING_REF": "keyvault://my-vault/sb-conn",
            "EVENTBUS_NAMESPACE": "my-servicebus.servicebus.windows.net",
        }

    def test_valid(self, monkeypatch):
        for k, v in self._valid_env().items():
            monkeypatch.setenv(k, v)
        s = EventBusSettings()
        assert s.namespace == "my-servicebus.servicebus.windows.net"

    def test_missing_namespace_raises(self, monkeypatch):
        env = self._valid_env()
        env.pop("EVENTBUS_NAMESPACE")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValidationError):
            EventBusSettings()

    def test_non_keyvault_conn_ref_raises(self, monkeypatch):
        env = self._valid_env()
        env["EVENTBUS_CONNECTION_STRING_REF"] = "Endpoint=sb://..."
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValidationError, match="Key Vault reference"):
            EventBusSettings()


# ---------------------------------------------------------------------------
# StateStoreSettings
# ---------------------------------------------------------------------------

class TestStateStoreSettings:
    def _valid_env(self) -> dict:
        return {
            "STATESTORE_CONNECTION_STRING_REF": "keyvault://my-vault/db-conn",
            "STATESTORE_DATABASE_NAME": "integ_db",
        }

    def test_valid(self, monkeypatch):
        for k, v in self._valid_env().items():
            monkeypatch.setenv(k, v)
        s = StateStoreSettings()
        assert s.database_name == "integ_db"

    def test_default_database_name(self, monkeypatch):
        monkeypatch.setenv(
            "STATESTORE_CONNECTION_STRING_REF", "keyvault://my-vault/db-conn"
        )
        s = StateStoreSettings()
        assert s.database_name == "onenote_integ"


# ---------------------------------------------------------------------------
# AppSettings
# ---------------------------------------------------------------------------

class TestAppSettings:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("APP_LOG_LEVEL", raising=False)
        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
        s = AppSettings()
        assert s.log_level == "INFO"
        assert s.environment == "development"

    def test_invalid_log_level_raises(self, monkeypatch):
        monkeypatch.setenv("APP_LOG_LEVEL", "VERBOSE")
        with pytest.raises(ValidationError, match="log_level"):
            AppSettings()

    def test_log_level_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("APP_LOG_LEVEL", "debug")
        s = AppSettings()
        assert s.log_level == "DEBUG"


# ---------------------------------------------------------------------------
# Key Vault reference helpers
# ---------------------------------------------------------------------------

class TestKeyVaultRef:
    def test_is_keyvault_ref_true(self):
        assert is_keyvault_ref("keyvault://my-vault/my-secret") is True

    def test_is_keyvault_ref_false(self):
        assert is_keyvault_ref("plain-text") is False
        assert is_keyvault_ref("https://my-vault.vault.azure.net/") is False

    def test_parse_valid_ref(self):
        vault, secret = parse_keyvault_ref("keyvault://my-vault/my-secret")
        assert vault == "my-vault"
        assert secret == "my-secret"

    def test_parse_invalid_ref_raises(self):
        with pytest.raises(ValueError, match="Invalid Key Vault reference"):
            parse_keyvault_ref("not-a-ref")

    def test_resolve_without_client_raises(self):
        with pytest.raises(RuntimeError, match="Key Vault client not provided"):
            resolve_secret("keyvault://my-vault/my-secret", _client=None)
