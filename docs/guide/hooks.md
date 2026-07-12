# Hooks

Gate or notify on any arc event with plain executables in `.arc/hooks/`.

---

## Overview

arc fires hooks before and after major operations. Hook files live in `.arc/hooks/<event>` — any executable: a shell script, a Python script, a compiled binary.

- **`pre-*` hooks** are gates. A non-zero exit code aborts the operation with exit code `7`. The underlying operation does not run.
- **`post-*` hooks** are notifications. The exit code is ignored.

Run `arc init` to scaffold sample hook files.

---

## Events

| Event | Trigger | Type |
|-------|---------|------|
| `pre-submit` | Before creating/updating PRs | gate |
| `post-submit` | After all PRs are created/updated | notification |
| `pre-push` | Before force-pushing branches | gate |
| `post-push` | After branches are pushed | notification |
| `pre-sync` | Before cascade rebase begins | gate |
| `post-sync` | After cascade rebase completes cleanly | notification |
| `pre-land` | Before landing a PR | gate |
| `post-land` | After a PR is landed and branches restacked | notification |

---

## Environment variables

Every hook receives these environment variables:

| Variable | Value |
|----------|-------|
| `ARC_EVENT` | Event name (e.g. `pre-submit`) |
| `ARC_BRANCH` | Current branch name |
| `ARC_BASE` | Stack base branch name (e.g. `main`) |
| `ARC_STACK_SIZE` | Number of branches in the stack |
| `ARC_DRY_RUN` | `1` if `--dry-run` was passed, `0` otherwise |

---

## Stdin JSON

Each hook also receives a JSON object on stdin with event-specific data:

```json
{
  "event": "pre-submit",
  "branch": "feat/auth",
  "base": "main",
  "stack": ["feat/auth", "feat/api", "feat/ui"],
  "dry_run": false
}
```

Read stdin in a hook with `jq`:

```bash
#!/bin/sh
data=$(cat)
branch=$(echo "$data" | jq -r '.branch')
echo "Submitting $branch"
```

---

## Examples

### Lint gate before submit

```bash
# .arc/hooks/pre-submit
#!/bin/sh
set -e
npm run lint
npm test
```

```bash
chmod +x .arc/hooks/pre-submit
```

arc runs this before touching GitHub. Any non-zero exit aborts all PR creates/updates.

### Slack notification after push

```bash
# .arc/hooks/post-push
#!/bin/sh
data=$(cat)
branch=$(echo "$data" | jq -r '.branch')
curl -s -X POST "$SLACK_WEBHOOK" \
  -H 'Content-type: application/json' \
  -d "{\"text\": \"Pushed stack from $branch\"}"
```

### Bypass a hook

```bash
arc submit --skip-hooks
```

Only `pre-submit` and `post-submit` hooks can be skipped. Other hooks always run.

---

## Config-file hooks

For simple shell commands, you can also define hooks in `.arc/config.json` (committed, shared with your team):

```json
{
  "hooks": {
    "pre-submit": ["npm run lint", "npm test"],
    "post-push": ["scripts/notify.sh"]
  }
}
```

When both a config-file hook and a file hook exist for the same event, the config-file hook runs first.

See [Configuration](../reference/config.md) for the full config schema.
