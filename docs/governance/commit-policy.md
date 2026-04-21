# Commit Slicing Policy

## Principle
**One atomic backlog task per commit.** Every commit is self-contained, reviewable,
and independently revertable.

## Commit Message Format

```
<area-code>: <short summary (≤ 72 chars)>

[optional body — what changed and why]
[test evidence line]
```

### Area codes

| Code | Area |
|------|------|
| `phase-0` | Project scaffold |
| `area-a` | Configuration |
| `area-b` | Auth |
| `area-c` | Event bus |
| `area-d` | Schema |
| `area-e` | Connectors |
| `area-f` | Renderer |
| `area-g` | State store |
| `area-h` | Change monitor |
| `area-i` | Error handling |
| `area-j` | Observability |
| `verification` | End-to-end tests |
| `release` | Release governance |

### Test evidence

The commit message subject **must** include a test count when the commit adds or
changes tests, e.g.:

```
area-g: state store schema v1, idempotent upsert, content hash, 20 tests pass
```

When no new tests are added (docs, config, governance), omit the count.

## Rules

1. **One task per commit** — do not bundle unrelated tasks into a single commit.
2. **Green before commit** — `uv run pytest` must pass with zero failures before
   `git commit`.
3. **Push immediately** — every `git commit` is followed immediately by `git push`.
   Never let the local branch ahead-of-remote accumulate more than one commit.
4. **No `--no-verify`** — do not bypass pre-commit hooks without explicit team
   approval.
5. **Commit messages are immutable after push** — do not `git commit --amend` or
   force-push published commits.
6. **Revert, don't delete** — use `git revert <sha>` to undo a published commit.

## Worked Example

```
$ uv run pytest -q
180 passed in 0.88s

$ git add src/state/store.py tests/test_state.py tasks/atomic-backlog.md
$ git commit -m "area-g: state store schema v1, idempotent upsert, content hash, 20 tests pass"
$ git push
```
