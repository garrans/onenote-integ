"""
A-T03: Key Vault reference placeholder pattern.

At startup, any settings field whose value matches the pattern
    keyvault://<vault-name>/<secret-name>
is resolved to the actual secret value from Azure Key Vault.

This module is the single place where secrets leave Key Vault and enter
process memory. It never writes secrets to disk or logs.
"""

from __future__ import annotations

import re

_KV_REF_PATTERN = re.compile(
    r"^keyvault://(?P<vault>[a-zA-Z0-9-]{3,24})/(?P<secret>[a-zA-Z0-9-]{1,127})$"
)


def is_keyvault_ref(value: str) -> bool:
    """Return True if *value* is a Key Vault reference string."""
    return bool(_KV_REF_PATTERN.match(value))


def parse_keyvault_ref(ref: str) -> tuple[str, str]:
    """
    Parse a Key Vault reference string.

    Returns:
        (vault_name, secret_name)

    Raises:
        ValueError: if *ref* is not a valid Key Vault reference.
    """
    m = _KV_REF_PATTERN.match(ref)
    if not m:
        raise ValueError(f"Invalid Key Vault reference: {ref!r}")
    return m.group("vault"), m.group("secret")


def resolve_secret(ref: str, *, _client=None) -> str:
    """
    Resolve a Key Vault reference to its secret value.

    In production, pass a configured ``azure.keyvault.secrets.SecretClient``
    as *_client*. If *_client* is None the function raises ``RuntimeError``
    so misconfiguration is caught immediately rather than silently falling
    through.

    Args:
        ref:     Key Vault reference string (keyvault://<vault>/<secret>).
        _client: An azure-keyvault-secrets SecretClient instance.

    Returns:
        The resolved secret string value.

    Raises:
        ValueError:   if *ref* is not a valid reference.
        RuntimeError: if *_client* is not provided (not yet wired).
    """
    vault_name, secret_name = parse_keyvault_ref(ref)

    if _client is None:
        raise RuntimeError(
            f"Key Vault client not provided. Cannot resolve secret "
            f"'{secret_name}' from vault '{vault_name}'. "
            "Wire a SecretClient via dependency injection before calling resolve_secret()."
        )

    secret = _client.get_secret(secret_name)
    return secret.value
