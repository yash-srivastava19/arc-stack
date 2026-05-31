# arc — Design Spec
_2026-05-31_

## Problem

Large PRs are expensive to review. Splitting them into stacked PRs is the right answer, but managing a stack by hand is painful: cascading rebases, force-pushing in the right order, retargeting PR bases when something merges. Existing tools (Graphite, gh-stack) solve this but are either SaaS or couple you to GitHub's official extension with a clunky modify story.

`arc` is a local CLI tool that owns the full stacked-PR loop — create, sync, push, submit, modify — with zero ceremony.

---

## Name

**`arc`** — a trajectory of changes building toward something. One syllable. Natural in usage: `arc new`, `arc sync`, `arc submit`.

---

## Philosophy

**Unix first.** Every command does one thing. Output goes to stdout, status messages go to stderr. `--json` on any command makes it machine-readable — explicit, not inferred. No TTY detection magic.

**Functional core, imperative shell.** The domain logic is pure functions (compute what needs to happen). Side effects (git, GitHub API) live only at the edges. These are separate braids that do not touch each other.

**No complecting.** Human output and machine output are separate flags, not environment-inferred behavior. State is data, not behavior. Each module has one job and does not reach into another's domain.

**Fire and forget.** The common path is one command: `arc sync`. For the full loop: `arc sync && arc push && arc submit`. Users stay in control but are not burdened by mechanics.

**Agent-friendly by design.** Every command has `--json`. Exit codes are meaningful and documented. The skill document lives in the repo alongside the code and is updated in the same commit when the CLI changes.

---

## Architecture

```
arc/
  arc/
    cli.py       # click commands — orchestration ONLY, no domain logic
    ops.py       # pure functions: compute rebase plans, validate stack state
    state.py     # read/write .arc/state.json, pure data transformations
    git.py       # one thin subprocess wrapper per git operation
    github.py    # one thin gh CLI wrapper per GitHub operation
  pyproject.toml
  .gitignore
  skills/
    arc.md       # agent-facing skill document, kept in sync with the CLI
```

### Dependency rule

```
cli.py → ops.py, state.py, git.py, github.py
ops.py → state.py only (no git, no github — pure)
state.py → nothing (pure data)
git.py → nothing (thin shell)
github.py → nothing (thin shell)
```

`ops.py` never calls `git.py` or `github.py`. It computes plans; `cli.py` executes them. This makes `ops.py` trivially testable without mocks and makes the execution layer swappable.

---

## State

State lives at `.arc/state.json` in the repo root. It is git-ignored — it is per-clone, per-user, not shared.

```json
{
  "version": 1,
  "base": "main",
  "prefix": "feat",
  "branches": [
    { "name": "feat/auth",       "pr": 42   },
    { "name": "feat/api",        "pr": 43   },
    { "name": "feat/ui",         "pr": null }
  ]
}
```

- `base`: the trunk branch all stacks root from
- `prefix`: optional, applied automatically on `arc new`
- `branches`: ordered array, index 0 = bottom (closest to trunk)
- `pr`: GitHub PR number, null until `arc submit` has run for that branch

`state.py` owns all reads and writes. No other module touches this file directly.

---

## Commands

### Core loop

```
arc init [--base <branch>] [--prefix <prefix>]
```
Detects trunk (repo default branch) if `--base` is omitted. Creates `.arc/state.json`. Adds `.arc/` to `.gitignore` (creates the file if absent). Idempotent — safe to run again.

```
arc new <branch>
```
Creates a new git branch from current HEAD. Applies prefix if set. Appends to stack state. Checks out the new branch.

```
arc add <branch>
```
Adopts an existing branch into the stack. The branch must already exist. Appends to state without creating or checking out anything.

```
arc status [--json]
```
The local representation layer. Default: rich tree to stdout showing branch names, PR numbers, commit count, and sync status. `--json`: structured data for agents and scripts.

Human output:
```
arc  (base: main)
─────────────────────────────────────────
  main
  └── feat/auth        PR #42  ✓  2 commits
      └── feat/api     PR #43  ✗  3 commits  (needs rebase)
          └── feat/ui  no PR   ✓  1 commit
```

JSON output:
```json
{
  "base": "main",
  "prefix": "feat",
  "current": "feat/api",
  "branches": [
    { "name": "feat/auth", "pr": 42,   "commits": 2, "needsRebase": false },
    { "name": "feat/api",  "pr": 43,   "commits": 3, "needsRebase": true  },
    { "name": "feat/ui",   "pr": null, "commits": 1, "needsRebase": false }
  ]
}
```

```
arc sync
```
The primary command. Fetches latest from remote, then cascades rebase bottom-up through the stack. On conflict: aborts the in-progress rebase and resets every branch to the SHA it held before `sync` ran, exits code 3, prints conflicted file paths to stderr. The user resolves conflicts manually then uses `arc rebase --continue` / `arc rebase --abort`.

```
arc push
```
Force-pushes all branches in stack order (`--force-with-lease --atomic`). Does not create or update PRs.

```
arc submit [--draft] [--open] [--json]
```
Creates or updates PRs via `gh pr create` / `gh pr edit`. Each PR targets the branch below it in the stack; the bottom branch targets `base`. Stores PR numbers in state. `--draft` creates draft PRs (default). `--open` marks new and existing PRs as ready for review.

### Modify

```
arc drop <branch> [--json]
```
Removes a branch from the stack. Cascades rebase for all branches above it. Does not delete the git branch — that is the user's choice.

```
arc rebase [--upstack | --downstack] [--continue | --abort] [--json]
```
Fine-grained rebase control. Default: entire stack. `--upstack`: current branch to top. `--downstack`: bottom to current branch. `--continue` / `--abort` for conflict resolution flow.

### Navigation

```
arc checkout <n | branch>    # by index (1-based) or branch name
arc up [n]                   # move n branches toward top (default: 1)
arc down [n]                 # move n branches toward trunk (default: 1)
arc top                      # jump to topmost branch
arc bottom                   # jump to bottommost non-merged branch
```

Navigation is thin wrappers around `git checkout`. Merged branches are skipped when navigating from active branches.

---

## Output contract

| Stream | Content |
|--------|---------|
| stdout | Data: human-readable tree by default, JSON with `--json` |
| stderr | Status messages: progress, warnings, errors |

Every command that produces data supports `--json`. Commands that are purely imperative (e.g. `arc push`) emit only stderr status and exit code.

---

## Exit codes

| Code | Meaning | Recovery |
|------|---------|----------|
| 0 | Success | — |
| 1 | Generic error | Read stderr |
| 2 | Not in a stack | Run `arc init` |
| 3 | Rebase conflict | Resolve files, `arc rebase --continue` or `arc rebase --abort` |
| 4 | GitHub API failure | Check `gh auth status`, retry |
| 5 | Invalid arguments | Fix invocation |

---

## The full loop

```bash
# First time: initialize the stack
arc init --base main --prefix feat

# Create branches as you work
arc new auth
# ... write code, git commit ...
arc new api
# ... write code, git commit ...
arc new ui
# ... write code, git commit ...

# Check your stack
arc status

# Keep everything rebased on main
arc sync

# Push and open draft PRs
arc push && arc submit --draft

# Respond to review feedback on a lower branch
arc checkout feat/auth
# ... amend commit ...
arc sync          # cascades rebase through api and ui
arc push
arc submit        # updates PR descriptions/bases

# Full one-liner once you know your way around
arc sync && arc push && arc submit --open
```

---

## Agent usage

Agents should:
- Always use `--json` for parsing output
- Use exit codes for flow control, not stdout parsing
- Run `arc status --json` to understand stack state before any operation
- Use `arc rebase --continue` / `arc rebase --abort` on exit code 3
- Never run commands that require interaction — all `arc` commands are non-interactive by design

The full agent skill is in `skills/arc.md` and is the authoritative reference for agent usage.

---

## Dependencies

| Dependency | Role |
|-----------|------|
| Python 3.11+ | Runtime |
| `click` | CLI framework |
| `rich` | Terminal output (tree, colors) |
| `git` (subprocess) | All git operations |
| `gh` CLI | GitHub API (auth, PR create/edit/view) |

No GitHub API token management. Auth is delegated to `gh auth`.

---

## What this is not

- Not a SaaS tool. No accounts, no dashboards, no telemetry.
- Not a wrapper around `gh stack`. We call `gh` for auth and PR operations only.
- Not a TUI (yet). `arc status` is the representation layer for V1. A `textual`-based TUI is a natural V2 that reads `arc status --json`.
- Not responsible for commit authoring. `git add` and `git commit` are yours. `arc` manages the stack, not your commits.
