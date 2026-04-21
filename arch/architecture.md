# Architecture Source

## Source Documents

- [reference architecture.md](reference%20architecture.md) — authoritative component design, canonical schema, block contract, and authentication ADR
- `Extensible App Architecture for OneNote Integration.pdf` — original source PDF (retained for reference)

## Summary

The integration platform is designed around loosely coupled components connected by an event bus.

### Core Components

| Component | Responsibility |
|---|---|
| **Connectors** | One per external system; publishes `NoteArtifact` events, subscribes to OneNote-side changes |
| **Event Bus** | Topic-based pub/sub (e.g. Azure Service Bus); routes `artifact.*` and `onenote.page.edited` events |
| **State & Mapping Store** | Tracks artifact↔page ID mappings, sync cursors, content hashes |
| **OneNote Renderer** | Subscribes to artifact events; creates/patches OneNote pages via Graph API using `data-id` blocks |
| **OneNote Change Monitor** | Detects page edits via webhook or polling; publishes change events back to the bus |
| **Microsoft Graph (OneNote API)** | All access via delegated auth (app-only deprecated March 2025) |
| **OneNote Add-In (optional)** | User-initiated triggers and conflict UI via Office JS |

### Canonical Schema

`NoteArtifact` (v1) — fields: `artifactId`, `sourceSystem`, `sourceRecordId`, `title`, `body`, `tags`, `people`, `attachments`, `timestamps`, `relationships`, `routing`, `renderHints`.

See [reference architecture.md](reference%20architecture.md) for full JSON schema.

### Block Contract

OneNote pages are divided into `data-id` blocks. Owned blocks (`summary`, `details`, `source-info`, `attachments`, `people`) are managed by the integration. The `user-notes` block is never overwritten. Graph API PATCH targets blocks individually by `data-id`.

### Authentication Decision (ADR)

**Decision:** Service account delegated auth model.  
**Rationale:** Microsoft Graph OneNote app-only auth was deprecated March 2025. Service account (single dedicated M365 account) is simpler to manage than per-user flows for a shared knowledge base.  
**Key concerns:** Token storage in Key Vault, activity auditing in our own logs, throttle limit awareness, conditional access rules on the service account.
