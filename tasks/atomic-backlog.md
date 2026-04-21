# Atomic Backlog

Each task changes **one concern only** and is independently verifiable.  
Dependency tags: `blocks:` = must be done before, `parallel:` = can run simultaneously.

---

## Phase 0 — Source Normalization and Repo Bootstrap

- [x] P0-T01 Initialize git repository and baseline project files.
- [x] P0-T02 Add reference architecture to `arch/` folder.
- [x] P0-T03 Update `arch/architecture.md` summary from reference architecture.
- [x] P0-T04 Update `docs/area-index.md` with architecture-derived areas.
- [x] P0-T05 Validate area index against reference architecture for completeness.

---

## Area A — Foundation and Configuration

- [x] A-T01 Define typed settings contract (required fields, types, defaults). `blocks: A-T02`
- [x] A-T02 Implement environment variable loader with validation. `blocks: A-T03`
- [x] A-T03 Add Key Vault reference placeholder pattern (no secrets in repo). `blocks: B-T01`
- [x] A-T04 Write unit tests for config validation (missing required fields, wrong types).

---

## Area B — Identity and Authentication

- [ ] B-T01 Define token provider interface (acquire, refresh, cache). `blocks: B-T02`
- [ ] B-T02 Implement service account OAuth token acquisition (auth code seeded refresh token path). `blocks: B-T03`
- [ ] B-T03 Implement secure token storage using Key Vault reference from A-T03. `blocks: B-T04`
- [ ] B-T04 Implement token renewal background task (refresh before expiry). `blocks: F-T02`
- [ ] B-T05 Write contract tests for token provider interface with mock identity server.
- [ ] B-T06 Document conditional access requirements for service account.

---

## Area C — Event Bus

- [ ] C-T01 Define event envelope schema (`version`, `type`, `sourceSystem`, `correlationId`, `payload`). `blocks: C-T02`
- [ ] C-T02 Define event type registry (`artifact.created.v1`, `artifact.updated.v1`, `artifact.deleted.v1`, `onenote.page.edited.v1`). `blocks: C-T03`
- [ ] C-T03 Implement publisher abstraction (send message with envelope). `blocks: E-T01, F-T06`
- [ ] C-T04 Implement subscriber abstraction (receive, deserialize, ack/nack). `blocks: E-T01, F-T06`
- [ ] C-T05 Configure Azure Service Bus topics and subscriptions per event type. `blocks: C-T03`
- [ ] C-T06 Write unit tests for publisher/subscriber round-trip with test doubles.

---

## Area D — NoteArtifact Canonical Schema

- [ ] D-T01 Write JSON schema file for NoteArtifact v1 (all fields from reference architecture). `blocks: D-T02`
- [ ] D-T02 Generate or write typed model classes from schema. `blocks: D-T03`
- [ ] D-T03 Implement schema validation utility (validates incoming events at bus boundary). `blocks: E-T01`
- [ ] D-T04 Write schema validation tests (valid artifact, missing required fields, unknown version).
- [ ] D-T05 Document versioning strategy for NoteArtifact schema evolution.

---

## Area E — Connectors

- [ ] E-T01 Define connector base interface (publish event, handle `onenote.page.edited`). `blocks: E-T02`
- [ ] E-T02 Implement connector registration mechanism (plug-in pattern; add/remove without touching core). `blocks: E-T03`
- [ ] E-T03 Implement one reference connector (stub external system → produces NoteArtifact events). `blocks: E-T04`
- [ ] E-T04 Write isolation test (removing reference connector does not affect event bus or renderer).

---

## Area F — OneNote Renderer

- [ ] F-T01 Define Graph transport adapter interface (PATCH, GET, POST to OneNote API). `blocks: F-T02`
- [ ] F-T02 Implement retry policy for transient Graph errors (429, 503). `blocks: F-T03`
- [ ] F-T03 Implement page-create logic (new NoteArtifact → new OneNote page via template). `blocks: F-T04`
- [ ] F-T04 Implement block-level PATCH logic (target `data-id` block; never overwrite `user-notes`). `blocks: F-T05`
- [ ] F-T05 Implement template registry (maps `routing.template` to page HTML structure). `blocks: F-T06`
- [ ] F-T06 Implement rendering pipeline (subscribe to artifact events → orchestrate create/patch). `blocks: I-T01`
- [ ] F-T07 Write deterministic rendering tests (given NoteArtifact, assert correct page HTML and block targets).

---

## Area G — State and Mapping Store

- [ ] G-T01 Define storage schema (artifact↔page mapping, sync cursor, content hash tables). `blocks: G-T02`
- [ ] G-T02 Implement migration baseline (schema version 1). `blocks: G-T03`
- [ ] G-T03 Implement idempotent upsert contract (lookup or create for artifact↔page mapping). `blocks: F-T03, H-T02`
- [ ] G-T04 Write persistence tests (upsert idempotency, mapping lookup, hash comparison).

---

## Area H — OneNote Change Monitor

- [ ] H-T01 Implement Graph webhook subscription for OneNote page change notifications. `blocks: H-T02`
- [ ] H-T01b Implement polling fallback (check `lastModifiedTime` and content hash on interval). `parallel: H-T01`
- [ ] H-T02 Implement content hash comparison against stored hash in State Store. `blocks: H-T03`
- [ ] H-T03 Implement change event publisher (`onenote.page.edited.v1` with affected artifactId and block hints). `blocks: I-T02`
- [ ] H-T04 Write change detection tests (simulated page edit → correct event published).

---

## Area I — Conflict and Error Handling

- [ ] I-T01 Define retryable vs terminal error taxonomy. `blocks: I-T02`
- [ ] I-T02 Implement dead-letter queue handler (park terminal failures with context). `blocks: I-T03`
- [ ] I-T03 Implement conflict detection logic (user-edited owned block → flag conflict). `blocks: I-T04`
- [ ] I-T04 Implement reconciliation task skeleton (accept or reject conflicted version). `blocks: V-T02`
- [ ] I-T05 Write conflict scenario tests (user edits owned block → conflict correctly flagged).

---

## Area J — Observability and Operations

- [ ] J-T01 Define structured log schema (timestamp, correlationId, sourceSystem, artifactId, action, outcome). `blocks: J-T02`
- [ ] J-T02 Implement correlation ID propagation (attach to event envelope; thread through all components). `blocks: J-T03`
- [ ] J-T03 Add log instrumentation to renderer, monitor, and connectors. `blocks: J-T04`
- [ ] J-T04 Define sync metrics contract (events processed, pages created, patches applied, errors, latency). `blocks: J-T05`
- [ ] J-T05 Implement audit log writer (maps connector+event→page action for traceability). `blocks: V-T03`
- [ ] J-T06 Write observability tests (assert log fields present and correlationId threads end-to-end).

---

## Verification

- [ ] V-T01 End-to-end test: seed NoteArtifact event → assert OneNote page created with correct blocks.
- [ ] V-T02 Resilience test: simulate 429 throttle and partial failure → assert retry, dead-letter, and recovery.
- [ ] V-T03 Security test: assert no tokens or secret values appear in structured logs.
- [ ] V-T04 Isolation test: add and remove a connector → assert rest of system unchanged.

---

## Release Governance

- [ ] R-T01 Define commit slicing policy (one task per commit, test evidence in message).
- [ ] R-T02 Define branch protection policy (short-lived feature branches, protected `main`, required checks).
- [ ] R-T03 Tag milestones: `M1-bootstrap`, `M2-schema+bus`, `M3-renderer`, `M4-monitor`, `M5-hardening`.
- [ ] R-T04 Create operational runbook template (token renewal, dead-letter triage, webhook renewal).

