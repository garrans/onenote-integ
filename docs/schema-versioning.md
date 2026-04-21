# D-T05: NoteArtifact Schema Versioning Strategy

**Area:** D — NoteArtifact Canonical Schema  
**Task:** D-T05

---

## Guiding Principle: Additive-only v1.x, breaking changes bump to v2

| Change type | Action |
|---|---|
| Add an optional field | Increment minor: `1.0` → `1.1`. Old consumers ignore unknown fields. |
| Make an optional field required | Bump major: `1.x` → `2.0`. Requires a migration plan. |
| Remove a field | Bump major: `1.x` → `2.0`. |
| Change a field's type | Bump major: `1.x` → `2.0`. |
| Rename a field | Bump major: `1.x` → `2.0`. |

---

## Version Negotiation

The `version` field in every `NoteArtifact` payload identifies the schema version.

- **Connectors** stamp the version at emission time.
- **Validator** (`src/schema/validator.py`) checks the `_SUPPORTED_VERSIONS` set at bus ingress. Update this set when a new version is supported.
- **Renderer and Change Monitor** must declare the versions they support. An event carrying an unsupported version is deadlettered automatically.

---

## Multiple Version Support Window

- Each component must support the **current** and **one previous** major version simultaneously during a migration window.
- The migration window closes once all connectors have been updated and at least one full sprint has passed with no v(N-1) messages on the bus.
- After the window, remove the old version from `_SUPPORTED_VERSIONS` and delete its schema file from `spec/`.

---

## Schema Files

| File | Description |
|---|---|
| `spec/note-artifact-v1.schema.json` | JSON Schema (draft 2020-12) — cross-language source of truth |
| `src/schema/note_artifact.py` | Python Pydantic models generated from schema |

When a new major version is introduced:
1. Create `spec/note-artifact-v2.schema.json`.
2. Create `src/schema/note_artifact_v2.py` with the new models.
3. Add `"2.0"` to `_SUPPORTED_VERSIONS` in `src/schema/validator.py`.
4. Update tests and connectors in a separate PR.
