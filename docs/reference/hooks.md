# Hooks reference

Complete reference for arc's lifecycle hooks.

For a conceptual overview and examples, see [Hooks](../guide/hooks.md).

---

## Event table

| Event | Command | Type | When it fires |
|-------|---------|------|---------------|
| `pre-submit` | `arc submit` | gate | Before creating or updating any PRs |
| `post-submit` | `arc submit` | notification | After all PRs are created/updated |
| `pre-push` | `arc push` | gate | Before force-pushing branches |
| `post-push` | `arc push` | notification | After all branches are pushed |
| `pre-sync` | `arc sync` | gate | Before the cascade rebase begins |
| `post-sync` | `arc sync` | notification | After the cascade rebase completes cleanly |
| `pre-land` | `arc land` | gate | Before landing a PR |
| `post-land` | `arc land` | notification | After the PR is landed and branches restacked |

**Gate hooks** (`pre-*`): a non-zero exit code aborts the arc command with exit code `7`. The underlying operation does not run.

**Notification hooks** (`post-*`): the exit code is ignored. arc does not fail if a post hook fails.

---

## Hook file location

```
<repo>/.arc/hooks/<event>
```

The file must be executable (`chmod +x`). Any executable works: shell script, Python, compiled binary.

When both a config-file hook (`.arc/config.json` `hooks` key) and a file hook exist for the same event, the config-file commands run first, then the file hook.

---

## Environment variables

Every hook receives these environment variables:

| Variable | Type | Value |
|----------|------|-------|
| `ARC_EVENT` | string | Event name, e.g. `pre-submit` |
| `ARC_BRANCH` | string | Current branch name |
| `ARC_BASE` | string | Stack base branch, e.g. `main` |
| `ARC_STACK_SIZE` | integer | Number of branches in the stack |
| `ARC_DRY_RUN` | `0` or `1` | `1` if `--dry-run` was passed |

---

## Stdin JSON

Each hook receives a JSON object on stdin. The object always contains:

```json
{
  "event": "pre-submit",
  "branch": "feat/auth",
  "base": "main",
  "stack": ["feat/auth", "feat/api", "feat/ui"],
  "dry_run": false
}
```

Event-specific additional fields:

### pre-submit / post-submit

```json
{
  "prs": [
    { "branch": "feat/auth", "pr_number": 42, "action": "update" },
    { "branch": "feat/api",  "pr_number": null, "action": "create" }
  ]
}
```

`action` is `"create"` for new PRs and `"update"` for existing ones.

### pre-push / post-push

```json
{
  "branches": ["feat/auth", "feat/api", "feat/ui"]
}
```

### pre-sync / post-sync

```json
{
  "plan": [
    { "branch": "feat/auth", "onto": "main" },
    { "branch": "feat/api",  "onto": "feat/auth" }
  ]
}
```

### pre-land / post-land

```json
{
  "landed_branch": "feat/auth",
  "pr_number": 42,
  "merge_strategy": "squash"
}
```

`merge_strategy` is `"squash"`, `"merge"`, or `"rebase"`.

---

## Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | Hook succeeded (or is a post-hook — exit code ignored) |
| non-zero (pre-hook) | Arc command aborted, exit code `7` |

---

## Reading stdin in a hook

```bash
#!/bin/sh
data=$(cat)
branch=$(echo "$data" | jq -r '.branch')
event=$(echo "$data" | jq -r '.event')
echo "[$event] on branch $branch"
```

```python
#!/usr/bin/env python3
import json, sys
data = json.load(sys.stdin)
print(f"[{data['event']}] on branch {data['branch']}")
```
