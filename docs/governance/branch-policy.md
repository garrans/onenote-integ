# Branch Protection Policy

## Branch Model

| Branch | Purpose | Lifetime |
|--------|---------|----------|
| `main` | Production-ready code — always deployable | Permanent |
| `feat/<task-id>-<slug>` | One atomic backlog task | Short-lived (hours–days) |
| `fix/<issue-or-sha>-<slug>` | Bugfixes against `main` | Short-lived |

## `main` Branch Protection Rules

Configure these rules in **GitHub → Settings → Branches → Branch protection rules**
for pattern `main`:

| Rule | Setting |
|------|---------|
| Require pull request before merging | ✅ enabled |
| Required approving reviews | 1 |
| Dismiss stale reviews on new push | ✅ enabled |
| Require status checks to pass | ✅ enabled |
| Required status checks | `pytest` (GitHub Actions) |
| Require branches to be up to date | ✅ enabled |
| Do not allow bypassing the above settings | ✅ enabled |
| Allow force pushes | ❌ disabled |
| Allow deletions | ❌ disabled |

## Feature Branch Workflow

```bash
# 1. Create a short-lived branch from current main.
git checkout main && git pull
git checkout -b feat/g-t01-state-store

# 2. Implement the task, run tests.
uv run pytest -q   # must be green

# 3. Commit (one commit per task, see commit-policy.md).
git add ...
git commit -m "area-g: state store schema v1, 20 tests pass"

# 4. Open a pull request; require ≥1 approval.
gh pr create --fill

# 5. Merge (squash or merge commit — team decides, stay consistent).
gh pr merge --merge

# 6. Delete the branch immediately after merge.
git branch -d feat/g-t01-state-store
git push origin --delete feat/g-t01-state-store
```

## Required GitHub Actions Check

`ci.yml` must define a `pytest` job:

```yaml
name: CI
on: [push, pull_request]
jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pytest -q
```

`main` merges are blocked until this check is green.

## Hotfix Procedure

For urgent fixes on `main`:

1. Branch `fix/<sha>-<slug>` from `main`.
2. Implement the minimal fix.
3. Open an expedited PR; at least one reviewer must approve.
4. Merge, push, and delete the fix branch.
5. Create a patch git tag: `git tag -a v<major>.<minor>.<patch+1>`.
