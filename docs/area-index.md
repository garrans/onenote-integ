# Area Index

Maps each implementation area to boundaries, key components, external dependencies, and non-goals.  
Source: [arch/reference architecture.md](../arch/reference%20architecture.md)

---

## A. Foundation and Configuration

- **Goal:** typed settings, environment variable validation, secret placeholder schema (no secrets in code).
- **Key deliverables:** config contract, env validation, Key Vault reference pattern.
- **Depends on:** nothing.
- **Non-goals:** runtime Graph API calls.

## B. Identity and Authentication

- **Goal:** service account delegated auth; token acquisition, secure storage, and renewal without interactive login.
- **Key deliverables:** token provider interface, OAuth refresh token storage in Key Vault, token cache abstraction, conditional access documentation.
- **Depends on:** A (config/secrets).
- **Non-goals:** per-user auth flows (deferred to future phase).

## C. Event Bus

- **Goal:** set up topic-based pub/sub backbone; define event contracts for all message types.
- **Key deliverables:** Azure Service Bus topic/subscription configuration, event envelope schema (`artifact.created.v1`, `artifact.updated.v1`, `artifact.deleted.v1`, `onenote.page.edited.v1`), publisher/subscriber abstractions.
- **Depends on:** A.
- **Non-goals:** business logic of individual connectors.

## D. NoteArtifact Canonical Schema

- **Goal:** define, validate, and version the `NoteArtifact` (v1) schema used across all producers and consumers.
- **Key deliverables:** JSON schema file, typed model classes, schema validation utility, versioning strategy.
- **Depends on:** nothing (schema is independent).
- **Non-goals:** connector-specific data mapping.

## E. Connectors

- **Goal:** one connector adapter per external system; produces `NoteArtifact` events, subscribes to `onenote.page.edited` events.
- **Key deliverables:** connector base class/interface, at least one reference connector implementation, isolation guarantee (adding/removing one connector has no effect on others).
- **Depends on:** C (event bus), D (schema).
- **Non-goals:** OneNote rendering logic.

## F. OneNote Renderer

- **Goal:** subscribe to artifact events; create and patch OneNote pages via Graph API using `data-id` block targeting.
- **Key deliverables:** Graph transport adapter, page-create logic, block-level PATCH logic, template registry, rendering pipeline.
- **Depends on:** B (auth), C (event bus), D (schema), G (state store for page ID mapping).
- **Non-goals:** change detection from OneNote side.

## G. State and Mapping Store

- **Goal:** persist artifact↔OneNote page ID mappings, sync cursors per connector, and content hashes for conflict detection.
- **Key deliverables:** storage schema, idempotent upsert contract, migration baseline.
- **Depends on:** A (config).
- **Non-goals:** business logic of renderers or connectors.

## H. OneNote Change Monitor

- **Goal:** detect OneNote page edits (webhook or polling) and publish `onenote.page.edited` events.
- **Key deliverables:** webhook handler or polling scheduler, content hash comparison, event publisher.
- **Depends on:** B (auth), C (event bus), G (state store for known page tracking).
- **Non-goals:** applying changes back to external systems (that's the connector's job).

## I. Conflict and Error Handling

- **Goal:** define retryable vs terminal error taxonomy; implement dead-letter contract and conflict reconciliation rules.
- **Key deliverables:** error taxonomy document, dead-letter queue setup, conflict detection in change monitor, reconciliation task skeleton.
- **Depends on:** C (event bus), G (state store).
- **Non-goals:** UI for conflict resolution (deferred to Optional Add-In).

## J. Observability and Operations

- **Goal:** structured logs, trace correlation IDs (per event flow), sync metrics, audit trail (connector+event→page action).
- **Key deliverables:** log schema, correlation ID propagation middleware, metrics contract, audit log writer.
- **Depends on:** A (config).
- **Non-goals:** dashboard UI tooling selection.

## K. Optional OneNote Add-In (Deferred)

- **Goal:** user-initiated triggers and conflict UI via Office JS.
- **Depends on:** F, H, I.
- **Non-goals:** core sync functionality (system works without this).
