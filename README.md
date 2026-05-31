# arc

A local CLI for managing stacked pull requests on GitHub.

Break large changes into a chain of small, reviewable PRs. `arc` handles the cascading rebases, force-pushes, and PR creation so you don't have to.

```
main
└── feat/auth        PR #42  ✓  2 commits
    └── feat/api     PR #43  ✗  3 commits  ← needs rebase
        └── feat/ui  no PR   ✓  1 commit
```

---

## Installation

```bash
pipx install arc-stack
```

Or with uv:

```bash
uv tool install arc-stack
```

**Requirements:** Python 3.11+, [git](https://git-scm.com), [gh CLI](https://cli.github.com) (authenticated)

---

## Quick start

```bash
# First time on a new machine
arc setup

# In your repo
arc init --base main --prefix feat

# Create branches as you work
arc new auth
git add . && git commit -m "Add auth middleware"
arc new api
git add . && git commit -m "Add API routes"

# Check your stack
arc status

# Sync, push, and open draft PRs
arc sync && arc push && arc submit --draft

# PR approved and merged — land it and restack
arc land feat/auth
```

---

## Commands

### Stack management

| Command | Description |
|---------|-------------|
| `arc setup` | Check environment (git, gh, auth) and configure git |
| `arc init [--base <branch>] [--prefix <prefix>]` | Initialize a stack in the current repo |
| `arc new <branch>` | Create a branch from HEAD and add it to the stack |
| `arc add <branch>` | Adopt an existing local branch into the stack |
| `arc status` | Show the stack — branch names, PR numbers, revision, sync state |
| `arc sync` | Fetch + cascade-rebase the stack bottom-up |
| `arc push` | Force-push all branches (`--force-with-lease --atomic`) |
| `arc submit [--draft] [--open]` | Create or update PRs; injects a stack map into each description |
| `arc land [<branch>]` | Land a merged PR and restack branches above it |

### Modify

| Command | Description |
|---------|-------------|
| `arc amend` | Append PR link and stack position to the current commit message |
| `arc drop <branch>` | Remove a branch from the stack and restack above it |
| `arc rebase [--upstack\|--downstack]` | Fine-grained rebase control |
| `arc rebase --continue \| --abort` | Resume or cancel a conflicted rebase |

### Navigate

| Command | Description |
|---------|-------------|
| `arc checkout <name\|index>` | Switch to a branch by name or 1-based position |
| `arc up [n]` | Move n branches toward the top |
| `arc down [n]` | Move n branches toward the trunk |
| `arc top` | Jump to the topmost branch |
| `arc bottom` | Jump to the bottommost branch |

---

## Standard flags

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Print what would happen, execute nothing |
| `--force` | `-f` | Skip confirmation prompts (required in non-interactive environments) |
| `--quiet` | `-q` | Suppress hints and progress output |
| `--json` | | Machine-readable JSON output to stdout |
| `--plain` | | Newline-delimited branch list (on `arc status`) |
| `--skip-hooks` | | Bypass pre-submit hooks (on `arc submit`) |
| `--no-color` | | Disable color; also respects `NO_COLOR` env var |

---

## Pre-submit hooks

Run local checks before `arc submit` creates any PRs. Configure in `.arc/config.json` (committed, shared with your team):

```json
{
  "hooks": {
    "pre-submit": ["npm run lint", "npm test"]
  }
}
```

Each command must exit 0 or submit is aborted. Bypass with `--skip-hooks`.

---

## For agents and scripts

Every command is non-interactive by default. Use `--json` for structured output, exit codes for flow control.

```bash
# Read stack state before acting
arc status --json | jq '.branches[] | select(.needs_rebase) | .name'

# List branches for scripting
arc status --plain | xargs -I{} echo "branch: {}"

# Dry-run the full loop
arc sync -n && arc push -n && arc submit -n
```

**`arc status --json` schema:**

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
    }
  ]
}
```

**Exit codes:**

| Code | Meaning | Recovery |
|------|---------|----------|
| 0 | Success | — |
| 1 | Generic error | Read stderr |
| 2 | Not in a stack | `arc init` |
| 3 | Rebase conflict | Resolve files, `arc rebase --continue` or `--abort` |
| 4 | GitHub API failure | `gh auth status`, retry |
| 5 | Invalid arguments | Read stderr for exact fix |
| 6 | Setup check failed | `arc setup` |
| 7 | Pre-submit hook failed | Fix the check or `--skip-hooks` |

---

## How it works

Each branch in a stack targets the branch below it as its PR base. When you run `arc sync`, it cascades a rebase bottom-up through the stack. When a PR is merged (including squash-merges), `arc land` rebases the branches above it correctly using `git rebase --onto`.

State is stored in `.arc/state.json` at the repo root — git-ignored, per-clone. Configuration (hooks) lives in `.arc/config.json` — committed and shared.

---

## License

MIT
