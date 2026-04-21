# OneNote Integration Service

Extensible OneNote integration platform for the Foothills Fire Protection District.  
Handles authentication, schema validation, event-driven rendering, change monitoring, error recovery, and observability.

## Status

✅ **Complete** — All atomic backlog items delivered (196 tests passing).

| Area | Phase | Status | Commit | Tests |
|------|-------|--------|--------|-------|
| Phase 0 | Bootstrap | ✅ | `ef328d6` | — |
| Area A | Config | ✅ | `ffa4e11` | 17 |
| Area B | Auth | ✅ | `a64fe9d` | 14 |
| Area C | Event Bus | ✅ | `8b6b74f` | 12 |
| Area D | Schema | ✅ | `a37d03a` | 17 |
| Area E | Connectors | ✅ | `3bf7e56` | 15 |
| Area F | Renderer | ✅ | `b4edbda` | 27 |
| Area G | State Store | ✅ | `331701a` | 20 |
| Area H | Monitor | ✅ | `62adc45` | 12 |
| Area I | Error Handling | ✅ | `95c54b9` | 25 |
| Area J | Observability | ✅ | `e335e99` | 21 |
| Verification | Integration | ✅ | `067d9e8` | 16 |
| Release | Governance | ✅ | `06e0565` | — |

## Quick Start

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest -q

# View architecture
open arch/architecture.md
open arch/reference\ architecture.md

# Review backlog completion
cat tasks/atomic-backlog.md
```

## Milestones

- **M1-bootstrap** — Project scaffold, planning artifacts (phase 0)
- **M2-schema+bus** — Typed config, auth, event bus, NoteArtifact v1 schema
- **M3-renderer** — Graph adapter, retry policy, page create/patch, template rendering
- **M4-monitor** — State store, webhook+polling source, hash-based change detection
- **M5-hardening** — Error taxonomy, dead-letter queue, conflict detection, observability, verification

## Repository Structure

```
arch/                    Architecture documents and reference design
docs/
  governance/            Commit policy, branch policy, operational procedures
  servicebus-topology.md Service Bus infrastructure layout
  area-*.md              Area definitions and responsibilities
spec/                    JSON schemas and interface contracts
src/
  config/                Configuration and Key Vault integration
  auth/                  Token provider, OAuth, renewal task
  eventbus/              Event envelope and pub/sub abstractions
  schema/                NoteArtifact v1 schema and validation
  connectors/            Connector registry and sample InspectionsApp connector
  renderer/              Graph adapter, retry policy, page manager, rendering pipeline
  state/                 In-memory state stores (page mapping, sync cursors, content hash)
  monitor/               Change detection (webhook manager, polling, change detector)
  errors/                Error taxonomy, dead-letter store, conflict detector
  observability/         Structured logging, correlation ID, metrics, audit log
tests/                   Comprehensive test suite (196 tests)
tasks/
  atomic-backlog.md      Atomic task inventory with completion status
```

## Key Features

### Authentication (Area B)
- MSAL-based token acquisition with automatic renewal
- Key Vault integration for client secrets
- Refresh task with configurable intervals

### Event Bus (Area C)
- Type-safe event envelope with correlation ID
- Publisher/subscriber abstraction
- Azure Service Bus topology for scalability

### Schema & Validation (Area D)
- NoteArtifact v1 JSON schema with versioning strategy
- Pydantic v2 typed models (frozen, extra=forbid)
- Comprehensive validator with detailed error messages

### Rendering (Area F)
- Graph API adapter with retry policy
- Exponential backoff for transient (503) and throttled (429) errors
- Template-driven page creation and patch operations
- Owned blocks pattern for conflict-safe updates

### Monitoring (Area H)
- Polling fallback for change detection
- Hash-based content comparison
- Event-driven pipeline triggering

### Error Handling (Area I)
- Retryable vs. terminal error classification
- Dead-letter queue for unrecoverable events
- Conflict detection with owning-block preservation
- Reconciliation skeleton for future auto-merge

### Observability (Area J)
- Structured JSON logging with correlation ID propagation
- Metrics collection (events, pages, patches, errors)
- Audit log writer for traceability

## Governance

See `docs/governance/`:
- **commit-policy.md** — One atomic task per commit, green before push, no skip-push
- **branch-policy.md** — Protected `main`, short-lived feature branches, required CI checks
- **runbook.md** — Token renewal, dead-letter triage, conflict resolution, alerts

## Testing

- **Unit tests** — 180 tests across 11 areas (setup, validator, state, monitor, errors, observability)
- **Integration tests** — 16 verification tests (end-to-end, resilience, security, isolation)
- **Test framework** — pytest 9.0.3 + Pydantic v2.13.3
- **Coverage** — Critical paths: auth, schema validation, rendering, error recovery

Run all tests:
```bash
uv run pytest -q
```

## Development

### Add a feature branch

```bash
git checkout main && git pull
git checkout -b feat/<task-id>-<slug>
# Implement, test, commit
git push origin feat/<task-id>-<slug>
# Open PR, merge, delete branch
```

### Commit workflow

```bash
uv run pytest -q        # must be green
git add ...
git commit -m "area-x: <summary>, N tests pass"
git push
```

See `docs/governance/commit-policy.md` for details.

## Contact

**Owner:** FFR Dev  
**Last updated:** 2026-04-21
