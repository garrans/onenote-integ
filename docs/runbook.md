# Operational Runbook

**System:** `onenote-integ` — OneNote Integration Service  
**Owner:** FFR Dev  
**Last updated:** 2025

---

## Table of Contents

1. [Token Renewal](#1-token-renewal)
2. [Dead-Letter Triage](#2-dead-letter-triage)
3. [Webhook Renewal](#3-webhook-renewal)
4. [Alerts and Escalation](#4-alerts-and-escalation)

---

## 1. Token Renewal

### What can go wrong

| Symptom | Likely cause |
|---------|-------------|
| `TokenRefreshError` in logs | MSAL refresh failed (expired client secret or network issue) |
| All Graph calls return 401 | Access token expired; renewal task dead |
| `GraphPermanentError(status_code=401)` in dead-letter | Token permanently invalid |

### Routine renewal (automatic)

`TokenRenewalTask` (in `src/auth/renewal.py`) runs on a background thread and
proactively refreshes the token before it expires.  
**No manual action is needed under normal operation.**

### Manual intervention steps

1. **Check logs** for `TokenRefreshError`:
   ```
   grep '"action": "token_refresh"' logs/onenote_integ.jsonl | tail -20
   ```

2. **Verify the client secret has not expired** in Azure Key Vault:
   - Portal → Key Vault → Secrets → `onenote-integ-client-secret`
   - If the secret shows *Expired*, rotate it (see step 3).

3. **Rotate the client secret:**
   ```bash
   # Generate a new secret in Entra ID app registration.
   az ad app credential reset --id <APP_CLIENT_ID> --years 1

   # Store the new secret in Key Vault.
   az keyvault secret set \
     --vault-name <VAULT_NAME> \
     --name onenote-integ-client-secret \
     --value "<NEW_SECRET>"
   ```

4. **Restart the renewal task** (or restart the service) so it picks up the
   new secret.

5. **Confirm recovery** — the next log entry for `token_refresh` should show
   `"outcome": "success"`.

---

## 2. Dead-Letter Triage

### What is the dead-letter queue?

`DeadLetterStore` (in `src/errors/dead_letter.py`) parks `EventEnvelope` objects
that could not be processed after all retries were exhausted or that raised a
`TerminalError`.  
Dead-lettered messages are never silently discarded; they accumulate in the store
and appear in structured logs.

### Symptoms

- `MetricsCollector.dead_letters` counter increasing
- Log records with `"action": "dead_letter_parked"` appearing in `onenote_integ`
  logger output

### Triage procedure

1. **List parked entries** (programmatic):
   ```python
   from src.errors.dead_letter import DeadLetterStore
   for entry in store.all():
       print(entry.error_type, entry.error_message, entry.envelope.artifact_id)
   ```

2. **Categorise by error type:**

   | Error type | Meaning | Action |
   |------------|---------|--------|
   | `SchemaValidationError` | Payload does not match NoteArtifact v1 | Fix source data; re-emit corrected event |
   | `MappingNotFoundError` | Artifact has no OneNote page yet | Check renderer pipeline; may need manual page creation |
   | `ConflictError` | Live page content diverges from authoritative | See conflict resolution below |
   | `GraphPermanentError` | Graph API rejected the call permanently | Check permissions; may need admin consent |
   | `GraphThrottledError` / `GraphTransientError` after exhaustion | Persistent Graph instability | Check Graph service health; retry after outage resolves |

3. **Replay a dead-lettered message** (after fixing the root cause):
   ```python
   entry = store.all()[0]           # pick the entry to replay
   pipeline.handle_event(entry.envelope)
   ```

4. **Remove resolved entries** — the current `DeadLetterStore` is in-memory and
   resets on restart.  For a production deployment, back the store with a durable
   queue (Azure Service Bus dead-letter sub-queue) and purge entries after
   successful replay.

### Conflict resolution

When `ConflictError` is raised:

1. Open the OneNote page identified by `page_id` in the error.
2. Compare the `user-notes` section (user-owned) with the owned blocks
   (`artifact-title`, `source-system`, `tags-section`, `people-section`,
   `body-section`).
3. Determine which version of the owned block should be authoritative.
4. If the source-system version wins: re-emit `ARTIFACT_UPDATED_V1` for that
   artifact.
5. If the user edit wins: update the canonical source record in the originating
   system to match and then re-emit.

---

## 3. Webhook Renewal

### Background

Microsoft Graph webhook subscriptions expire (typically after ≤4320 minutes for
OneNote resources).  `WebhookSubscriptionManager` (in `src/monitor/change_source.py`)
provides `subscribe()`, `renew()`, and `unsubscribe()` hooks but the renewal
scheduler is not yet implemented — `PollingMonitor` serves as the fallback.

### Current state (v1)

`PollingMonitor` polls every 300 seconds (configurable via `poll_interval_seconds`).
No webhook subscription maintenance is required.

### Future webhook renewal procedure (for reference)

When webhooks are enabled:

1. **Before expiry** (subscription `expirationDateTime` − 30 min):
   ```python
   manager.renew(subscription_id, new_expiry_datetime)
   ```

2. **If renewal fails** (subscription expired):
   ```python
   manager.unsubscribe(subscription_id)
   manager.subscribe(resource_url, notification_url, expiry_datetime)
   ```

3. **Verify** the new subscription by checking the Graph response `201 Created`.

4. **Monitor** subscription health via `src/observability/metrics.py`
   `events_received` counter — a sudden drop may indicate a dead subscription.

---

## 4. Alerts and Escalation

### Key metrics to watch

| Metric | Normal | Alert threshold |
|--------|--------|-----------------|
| `dead_letters` | 0 | > 0 in 5-min window |
| `errors` | 0–2 transients/hour | > 10 in 5-min window |
| `events_received` | Varies | Zero for > 10 min during business hours |
| `conflicts_detected` | 0 | > 0 requires triage |

### Log queries (JSON logs)

```bash
# Failed events in the last hour
grep '"outcome": "failure"' logs/onenote_integ.jsonl \
  | awk -F'"timestamp": "' '{print $2}' | cut -c1-19

# Dead-letter events
grep '"action": "dead_letter_parked"' logs/onenote_integ.jsonl
```

### Escalation path

| Severity | Condition | Who to notify |
|----------|-----------|---------------|
| P1 | No events processed for > 30 min during business hours | On-call engineer immediately |
| P2 | Dead-letter count > 5 in one hour | On-call engineer within 2 hours |
| P3 | Conflict detected | Assigned developer next business day |
| P4 | Transient retry storm (retries > 20/hour) | Monitoring ticket |
