"""
A-T01 / A-T02: Typed settings contract and environment variable loader.

All configuration is sourced from environment variables (or a .env file for
local development). No secrets are stored in code; Key Vault references are
resolved via keyvault.py at startup.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Service account delegated auth configuration (Area B)."""

    tenant_id: str = Field(..., description="Azure AD tenant ID")
    client_id: str = Field(..., description="App registration client ID")
    # Value must be a Key Vault reference: keyvault://<vault>/<secret>
    client_secret_ref: str = Field(
        ...,
        description="Key Vault reference for the OAuth client secret",
    )
    # Value must be a Key Vault reference: keyvault://<vault>/<secret>
    refresh_token_ref: str = Field(
        ...,
        description="Key Vault reference for the OAuth refresh token",
    )

    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    @field_validator("client_secret_ref", "refresh_token_ref", mode="before")
    @classmethod
    def must_be_keyvault_ref(cls, v: str, info) -> str:
        if not v.startswith("keyvault://"):
            raise ValueError(
                f"{info.field_name} must be a Key Vault reference "
                f"(keyvault://<vault>/<secret>), got: {v!r}"
            )
        return v


class EventBusSettings(BaseSettings):
    """Azure Service Bus connection configuration (Area C)."""

    # Value must be a Key Vault reference: keyvault://<vault>/<secret>
    connection_string_ref: str = Field(
        ...,
        description="Key Vault reference for the Service Bus connection string",
    )
    namespace: str = Field(..., description="Service Bus namespace hostname")

    model_config = SettingsConfigDict(env_prefix="EVENTBUS_", env_file=".env", extra="ignore")

    @field_validator("connection_string_ref", mode="before")
    @classmethod
    def must_be_keyvault_ref(cls, v: str, info) -> str:
        if not v.startswith("keyvault://"):
            raise ValueError(
                f"{info.field_name} must be a Key Vault reference "
                f"(keyvault://<vault>/<secret>), got: {v!r}"
            )
        return v


class StateStoreSettings(BaseSettings):
    """State and mapping store configuration (Area G)."""

    # Value must be a Key Vault reference: keyvault://<vault>/<secret>
    connection_string_ref: str = Field(
        ...,
        description="Key Vault reference for the database connection string",
    )
    database_name: str = Field("onenote_integ", description="Database name")

    model_config = SettingsConfigDict(env_prefix="STATESTORE_", env_file=".env", extra="ignore")

    @field_validator("connection_string_ref", mode="before")
    @classmethod
    def must_be_keyvault_ref(cls, v: str, info) -> str:
        if not v.startswith("keyvault://"):
            raise ValueError(
                f"{info.field_name} must be a Key Vault reference "
                f"(keyvault://<vault>/<secret>), got: {v!r}"
            )
        return v


class AppSettings(BaseSettings):
    """Top-level application settings composed from sub-settings."""

    log_level: str = Field("INFO", description="Logging level")
    environment: str = Field("development", description="deployment environment name")

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    @field_validator("log_level", mode="before")
    @classmethod
    def log_level_must_be_valid(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got: {v!r}")
        return v.upper()
