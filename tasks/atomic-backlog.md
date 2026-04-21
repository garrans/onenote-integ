# Atomic Backlog

Each task is one concern and independently verifiable.

## Phase 0

- [x] P0-T01 Initialize git repository and baseline project files.
- [ ] P0-T02 Convert architecture source to editable Markdown.
- [ ] P0-T03 Validate heading fidelity and section completeness.

## Area A Foundation

- [ ] A-T01 Define typed configuration contract.
- [ ] A-T02 Implement environment variable validation.
- [ ] A-T03 Add secrets placeholder schema.

## Area B Identity

- [ ] B-T01 Define token provider interface.
- [ ] B-T02 Implement token cache abstraction.
- [ ] B-T03 Add auth contract tests.

## Area C API Client

- [ ] C-T01 Define Graph transport adapter interface.
- [ ] C-T02 Implement retry policy for transient failures.
- [ ] C-T03 Implement throttling handler for 429 responses.

## Area D Sync

- [ ] D-T01 Define checkpoint model.
- [ ] D-T02 Implement notebook/page discovery pipeline.
- [ ] D-T03 Add idempotent scheduler contract tests.

## Area E Normalization

- [ ] E-T01 Define canonical content block model.
- [ ] E-T02 Implement page content transformer.
- [ ] E-T03 Add deterministic transformation tests.

## Area F Persistence

- [ ] F-T01 Define persistence schema.
- [ ] F-T02 Implement idempotent upsert contract.
- [ ] F-T03 Add migration baseline and tests.

## Area G Conflicts

- [ ] G-T01 Define retryable vs terminal error taxonomy.
- [ ] G-T02 Implement dead-letter contract.
- [ ] G-T03 Add reconciliation task skeleton.

## Area H Observability

- [ ] H-T01 Define structured log schema.
- [ ] H-T02 Add trace correlation ID propagation.
- [ ] H-T03 Define sync metrics contract.

## Verification

- [ ] V-T01 End-to-end sync fixture test.
- [ ] V-T02 Resilience test for throttling and partial failures.
- [ ] V-T03 Security test for token and secret leakage in logs.
