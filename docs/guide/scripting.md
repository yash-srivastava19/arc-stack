# Scripting

arc is designed for use in scripts, CI, and AI agents. All commands are non-interactive by default.

---

## Output modes

Every command that produces data supports three output modes:

| Flag | Output | Use for |
|------|--------|---------|
| _(default)_ | Human-readable, colored | Terminal use |
| `--plain` | Branch names only, one per line | Shell scripts |
| `--json` | Structured JSON to stdout | Scripts, CI, agents |

Status messages always go to **stderr**. `--json` output always goes to **stdout**. This separation makes it safe to pipe `--json` output without filtering out status messages.

---

## arc status --json

```bash
arc status --json
```

```json
{
  "base": "main",
  "prefix": "feat",
  "current_branch": "feat/api",
  "branches": [
    {
      "name": "feat/auth",
      "index": 1,
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo/pull/42",
      "pr_state": "OPEN",
      "commits": 2,
      "revision": 3,
      "needs_rebase": false,
      "is_current": false,
      "is_merged": false
    },
    {
      "name": "feat/api",
      "index": 2,
      "pr_number": 43,
      "pr_url": "https://github.com/owner/repo/pull/43",
      "pr_state": "OPEN",
      "commits": 1,
      "revision": 3,
      "needs_rebase": false,
      "is_current": true,
      "is_merged": false
    }
  ]
}
```

### Common queries

```bash
# All branch names
arc status --plain

# Branches that need rebasing
arc status --json | jq '.branches[] | select(.needs_rebase) | .name'

# PR numbers for all branches
arc status --json | jq '.branches[] | {name, pr_number}'

# Is the current branch merged?
arc status --json | jq '.branches[] | select(.is_current) | .is_merged'
```

---

## JSON schemas

Print the JSON Schema for any `--json` output:

```bash
arc schema status     # schema for arc status --json
arc schema submit     # schema for arc submit --json
arc schema analyze    # schema for arc stack analyze --json
```

Use these schemas to validate arc output in typed pipelines.

---

## Exit codes

Scripts should check exit codes, not parse stderr:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error |
| `2` | Not in a stack (`arc init` needed) |
| `3` | Rebase conflict (resolve + `arc rebase --continue`) |
| `4` | GitHub API failure |
| `5` | Invalid arguments |
| `6` | Setup check failed (`arc setup` needed) |
| `7` | Pre-hook returned non-zero |

```bash
arc sync
case $? in
  0) echo "Stack is current" ;;
  3) echo "Conflict — resolve and run arc rebase --continue" ;;
  *) echo "Error" ;;
esac
```

See [Exit codes](../reference/exit-codes.md) for the full table.

---

## Dry run

```bash
arc sync -n     # show the rebase plan without executing
arc push -n     # show what would be pushed
arc submit -n   # show what PRs would be created/updated
arc land -n     # show what would be removed and restacked
```

Chain dry runs before committing:

```bash
arc sync -n && arc push -n && arc submit -n
```

---

## Scripting patterns

### Wait for CI before landing

```bash
#!/bin/bash
set -e
branch=$(git rev-parse --abbrev-ref HEAD)
pr=$(arc status --json | jq ".branches[] | select(.name == \"$branch\") | .pr_number")

# Wait for CI using gh
gh pr checks "$pr" --watch --fail-fast
arc land "$branch" -f
```

### Check stack health in CI

```bash
# Fail if any branch needs a rebase
needs_rebase=$(arc status --json | jq '[.branches[] | select(.needs_rebase)] | length')
if [ "$needs_rebase" -gt 0 ]; then
  echo "Stack out of date — run arc sync"
  exit 1
fi
```

### Bulk submit

```bash
arc push && arc submit --open
```
