# Arc Release Process

Standard checklist for every arc release. Follow this in order — no exceptions.

---

## Pre-release checklist

### 1. Verify main is green
```bash
git checkout main && git pull origin main
uv run pytest -q                      # all tests pass
uv run ruff check arc/ tests/         # lint clean
uv run mypy arc/                      # types clean
```

### 2. Verify arc stack is clean
```bash
arc status --plain
```
Expected: **empty output** (no stale branches). If any branches appear, they were not yet merged. Either merge them or `arc drop --force` them before releasing.

### 3. Confirm all intended PRs are on main
```bash
git log --oneline v<PREV_VERSION>..HEAD
```
Every feature/fix PR should appear. If a PR is missing (merged into wrong base), cherry-pick it before proceeding.

---

## Release PR

Create a PR with exactly these changes — nothing else:

| File | Change |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `arc/cli.py` | `@click.version_option("X.Y.Z", ...)` |
| `tests/test_cli.py` | `assert "X.Y.Z" in result.output` |
| `tests/test_report.py` | `assert "X.Y.Z" in ctx` |

```bash
arc new release/vXYZ
# make the 4 changes above
git add pyproject.toml arc/cli.py tests/test_cli.py tests/test_report.py uv.lock
git commit -m "release: bump to vX.Y.Z"
arc push && arc submit --open --skip-hooks
```

PR title format: `release: vX.Y.Z`

CI must be green before merging.

---

## After the release PR merges

### 1. Drop the release branch from arc stack immediately
```bash
arc drop release/vXYZ --force -q
```
**This is mandatory.** Forgetting this causes the next `arc new` to stack on the release branch instead of main.

### 2. Trigger the release workflow
```bash
gh workflow run release.yml --field version=X.Y.Z
```
Wait for it to complete:
```bash
gh run list --workflow=release.yml --limit 1
```

### 3. Verify
```bash
gh release view vX.Y.Z --json tagName,url
```
Expected: tag exists, GitHub release page live, PyPI package updated.

---

## Versioning scheme

| Change type | Version bump | Examples |
|---|---|---|
| Bug fixes, small improvements | Patch (0.3.x) | fix:, style:, chore: |
| New commands, new flags | Minor (0.x.0) | feat: |
| Breaking changes | Major (x.0.0) | rare |

Arc follows semver. When in doubt, patch bump.

---

## Common mistakes and how to avoid them

**Mistake:** Merging a stacked PR before running `arc sync` after its parent merged.
**Result:** PR merges into a deleted branch; changes are lost.
**Prevention:** Always run `arc sync && arc push && arc submit` after any parent PR merges before merging the child.

**Mistake:** Not dropping the release branch after it merges.
**Result:** Next `arc new` stacks on the release branch; new PRs target the wrong base.
**Prevention:** `arc drop release/vXYZ --force -q` is the first thing you do after merging a release PR.

**Mistake:** Triggering the release workflow with a version that doesn't match `pyproject.toml`.
**Result:** Workflow fails at version validation.
**Prevention:** The release PR always bumps the version first; trigger with the same version.
