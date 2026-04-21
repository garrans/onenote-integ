# Conditional Access Requirements for Service Account

**Area:** B — Identity and Authentication  
**Task:** B-T06  
**Status:** Accepted (see ADR in arch/reference architecture.md)

---

## Summary

The integration uses a **single M365 service account** with delegated permissions.
The refresh token is seeded once via interactive auth and stored in Azure Key Vault.
All subsequent token acquisitions are non-interactive (refresh token path via MSAL).

---

## Conditional Access Policies — Required Exclusions

The service account **must be excluded** from the following Conditional Access
policy types to allow unattended operation:

| Policy type | Required action | Reason |
|---|---|---|
| MFA / strong authentication | Exclude service account | Non-interactive refresh cannot satisfy MFA challenges |
| Sign-in frequency / session controls | Set to "Persistent browser session: always" or exclude | AAD will not prompt if session is persistent |
| Compliant device / Hybrid AD join | Exclude service account | The runner environment is not a managed endpoint |
| Risky user / sign-in remediation | Exclude service account | Automated refresh patterns may trigger risk policies |
| Location / IP-based restrictions | Allow the runner IP/range | If location CA is active, the runner IP must be in a Named Location |

---

## Token Lifetime Configuration

- **Access token lifetime:** Use Azure AD default (1 hour). Do not shorten via token lifetime policies.
- **Refresh token lifetime:** Use continuous access evaluation (CAE) default (90 days sliding window). The `TokenRenewalTask` rotates the stored refresh token on every successful refresh, keeping the window alive.

---

## Re-seeding the Refresh Token

If the refresh token expires (e.g., after 90 days of inactivity, password reset,
or MFA state change), the secret must be re-seeded manually:

1. Run the one-time interactive auth script (to be implemented in a maintenance runbook).
2. Copy the returned `refresh_token` into Key Vault at the path referenced by `AUTH_REFRESH_TOKEN_REF`.
3. Restart the service. `ServiceAccountTokenProvider` will load the new token on the next `get_token()` call.

---

## Permission Scopes Required

The app registration must be granted **delegated** permissions (not application):

| Permission | API | Reason |
|---|---|---|
| `Notes.ReadWrite` | Microsoft Graph | Read and write OneNote pages and sections |
| `offline_access` | Microsoft Graph | Required to obtain a refresh token |

> **Note:** App-only Graph access to OneNote notebooks is deprecated from March 2025
> (source: ADR in arch/reference architecture.md). Delegated permissions via a
> service account remain fully supported.

---

## Security Considerations

- The service account should have the **minimum M365 license** that grants OneNote access (e.g., Microsoft 365 Business Basic).
- The account should have **no human-accessible mailbox or Teams presence** to reduce the attack surface.
- Key Vault access must be restricted to the runner's managed identity using RBAC (`Key Vault Secrets Officer` on the specific secrets only).
- Rotate the client secret on the App Registration quarterly. Update `AUTH_CLIENT_SECRET_REF` target secret after rotation.
