# C-T05: Azure Service Bus Topics and Subscriptions

This document specifies the required Service Bus namespace configuration.
Infrastructure provisioning is deferred to Area J (Observability) or a
separate IaC module; this file is the authoritative specification.

---

## Topics

| Topic | Event types routed to it | Retention |
|---|---|---|
| `artifact-events` | `artifact.created.v1`, `artifact.updated.v1`, `artifact.deleted.v1` | 1 day |
| `onenote-events` | `onenote.page.created.v1`, `onenote.page.edited.v1`, `onenote.page.deleted.v1` | 1 day |

---

## Subscriptions

### artifact-events topic

| Subscription | Consumer | SQL Filter |
|---|---|---|
| `renderer` | OneNote Renderer (Area F) | `1=1` (all artifact events) |
| `state-store` | State & Mapping Store writer (Area G) | `1=1` |

### onenote-events topic

| Subscription | Consumer | SQL Filter |
|---|---|---|
| `conflict-resolver` | Conflict Resolution (Area I) | `1=1` |
| `state-store` | State & Mapping Store writer (Area G) | `1=1` |

---

## Dead Letter Queue policy

- Max delivery count: **5**
- Dead-letter reason is set by the subscriber to `HandlerError` with a truncated description (max 2 048 chars).
- Dead-letter queues should be monitored via an Azure Monitor alert (Area J).

---

## Message envelope correlation

The `correlationId` application property on every Service Bus message maps to
`EventEnvelope.correlation_id`. Use this property in Service Bus message filters
to trace a single logical operation across topics.
