# Configuration

arc reads two configuration files:

| File | Location | Who owns it |
|------|----------|-------------|
| `.arc/config.json` | In your repo, committed | Team-shared settings |
| `.arc/state.json` | In your repo, git-ignored | Per-clone state (not configuration) |

---

## .arc/config.json

Committed to the repo and shared with your team. Create it with `arc config set` or by writing the JSON directly.

### Full schema

```json
{
  "hooks": {
    "pre-submit":  ["command", "..."],
    "post-submit": ["command", "..."],
    "pre-push":    ["command", "..."],
    "post-push":   ["command", "..."],
    "pre-sync":    ["command", "..."],
    "post-sync":   ["command", "..."],
    "pre-land":    ["command", "..."],
    "post-land":   ["command", "..."]
  },
  "feedback": {
    "enabled": true
  }
}
```

All keys are optional.

### hooks

Shell commands to run on arc events. Each event takes a list of commands. Commands run in order; any non-zero exit from a `pre-*` hook aborts the arc command.

```json
{
  "hooks": {
    "pre-submit": ["npm run lint", "npm test"],
    "post-push":  ["scripts/notify-team.sh"]
  }
}
```

For richer hooks (access to branch context, JSON data on stdin), use executable files in `.arc/hooks/` instead. See [Hooks](hooks.md).

### feedback.enabled

Controls whether arc periodically shows usage hints. Default: `true`. Set to `false` to silence them:

```bash
arc config set feedback.enabled false
```

---

## arc config commands

```bash
arc config list                      # print all key=value pairs
arc config get feedback.enabled      # get one value
arc config set feedback.enabled false  # set one value
```

Keys use dot notation for nested fields (`hooks.pre-submit`).

---

## Environment variables

| Variable | Effect |
|----------|--------|
| `NO_COLOR` | Disable color output (same as `--no-color`) |
| `ARC_NO_INPUT` | Never prompt (same as `--no-input`) |
| `GH_HOST` | GitHub Enterprise Server hostname (passed through to `gh`) |
