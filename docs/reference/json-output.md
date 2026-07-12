# JSON output

Commands that produce data support `--json`. JSON goes to stdout; status messages go to stderr. This separation makes piping safe — you never need to filter stderr from your JSON.

Print the machine-readable schema for any command's output:

```bash
arc schema status
arc schema submit
arc schema analyze
```

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

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `base` | string | Stack base branch |
| `prefix` | string \| null | Branch name prefix, or null if none |
| `current_branch` | string | Currently checked-out branch |
| `branches[].name` | string | Branch name |
| `branches[].index` | integer | 1-based position in the stack |
| `branches[].pr_number` | integer \| null | PR number, or null if no PR |
| `branches[].pr_url` | string \| null | PR URL, or null if no PR |
| `branches[].pr_state` | string \| null | `OPEN`, `MERGED`, `CLOSED`, or null |
| `branches[].commits` | integer | Commits on this branch beyond its base |
| `branches[].revision` | integer | Push counter (increments on each `arc push`) |
| `branches[].needs_rebase` | boolean | True if the branch is out of date with its parent |
| `branches[].is_current` | boolean | True if this is the currently checked-out branch |
| `branches[].is_merged` | boolean | True if the PR is merged on GitHub |

---

## arc submit --json

```bash
arc submit --json
```

```json
{
  "results": [
    {
      "branch": "feat/auth",
      "action": "update",
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo/pull/42"
    },
    {
      "branch": "feat/api",
      "action": "create",
      "pr_number": 43,
      "pr_url": "https://github.com/owner/repo/pull/43"
    }
  ]
}
```

`action` is `"create"` for new PRs, `"update"` for existing ones, `"skip"` if the branch was skipped (e.g. dry run with no changes), or `"error"` if the PR operation failed.

---

## arc stack analyze --json

```bash
arc stack analyze --json
```

```json
{
  "critical_path": ["feat/auth", "feat/api", "feat/ui"],
  "safe_to_land": ["feat/auth"],
  "blocked": [
    {
      "branch": "feat/api",
      "blocked_by": ["feat/auth"]
    }
  ]
}
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `critical_path` | string[] | Longest chain of unmerged branches, bottom to top |
| `safe_to_land` | string[] | Branches that can be landed now (no unmerged dependencies) |
| `blocked[].branch` | string | Branch that cannot yet be landed |
| `blocked[].blocked_by` | string[] | Unmerged branches that must land first |

---

## Common patterns

```bash
# Check if the stack is clean
arc status --json | jq 'all(.branches[]; .needs_rebase == false)'

# Get all PR numbers
arc status --json | jq '[.branches[].pr_number | select(. != null)]'

# Find the current branch's PR
arc status --json | jq '.branches[] | select(.is_current) | .pr_url'

# Check for merged branches still in the stack
arc status --json | jq '.branches[] | select(.is_merged) | .name'
```
