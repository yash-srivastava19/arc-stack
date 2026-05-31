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

**Functional core, imperative shell.** The domain logic is pure functions that compute what needs to happen. Side effects (git, GitHub API) live only at the edges. These are separate braids that do not touch each other.

**Simple Made Easy.** Simple = each module has one role and does not reach into another's domain. Easy = the common path is one command. Don't complect concerns — separate modify from navigate, push from submit, human output from machine output. State is data, not behavior.

**Fire and forget.** The common path is `arc sync && arc push && arc submit`. Users stay in control but are not burdened by mechanics.

**Agent-friendly by design.** Every command has `--json`. Exit codes are meaningful and documented. The skill document lives in the repo alongside the code and is updated in the same commit when the CLI changes.

**Adaptable by design.** New commands are additive. The state schema is versioned. `ops.py` is the stable interface — both the CLI and any future TUI consume it directly. Adding a feature means adding a pure function to `ops.py` and wiring it up in `cli.py`, nothing more.

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
cli.py  → ops.py, state.py, git.py, github.py
ops.py  → state.py only (no git, no github — pure)
state.py → nothing (pure data)
git.py  → nothing (thin shell)
github.py → nothing (thin shell)
```

`ops.py` never calls `git.py` or `github.py`. It computes plans; `cli.py` executes them. This makes `ops.py` trivially testable without mocks and makes the execution layer swappable.

### Extension point: TUI

A future TUI does not go through `cli.py`. It imports `ops.py` directly for pure computations and calls `git.py` / `github.py` for side effects. `cli.py` is only the terminal text interface — it is not the API. `ops.py` is the API. Keep `ops.py` functions small, well-named, and return-value-driven so they are easy to call from both surfaces.

---

## State

State lives at `.arc/state.json` in the repo root. It is git-ignored — it is per-clone, per-user, not shared.

```json
{
  "version": 1,
  "base": "main",
  "prefix": "feat",
  "branches": [
    { "name": "feat/auth", "pr_number": 42   },
    { "name": "feat/api",  "pr_number": 43   },
    { "name": "feat/ui",   "pr_number": null  }
  ],
  "metadata": {}
}
```

- `version`: schema version, incremented on breaking changes. Readers must reject unknown versions.
- `base`: the trunk branch all stacks root from.
- `prefix`: optional, applied automatically on `arc new`.
- `branches`: ordered array, index 0 = bottom (closest to trunk). Each entry has `name` (full branch name) and `pr_number` (integer or null).
- `metadata`: reserved for future extensibility. Always present, initially empty. New features write here without breaking the existing schema.

`state.py` owns all reads and writes. No other module touches this file directly. Reads always validate `version` and fail fast if unrecognized.

---

## JSON output standard

All `--json` output uses **snake_case** keys. Null fields are always present (never omitted). Arrays are always arrays (never null when empty). Exit codes signal errors — JSON output is always valid when exit code is 0.

`arc status --json` schema:

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
      "commits": 3,
      "needs_rebase": true,
      "is_current": true,
      "is_merged": false
    },
    {
      "name": "feat/ui",
      "index": 3,
      "pr_number": null,
      "pr_url": null,
      "pr_state": null,
      "commits": 1,
      "needs_rebase": false,
      "is_current": false,
      "is_merged": false
    }
  ]
}
```

Every `--json` command follows this contract: snake_case, nulls explicit, no empty fields omitted.

---

## Commands

### Onboarding

```
arc setup
```

One-time environment check. Run this before anything else on a new machine. It:
1. Verifies `git` is installed
2. Verifies `gh` is installed
3. Checks `gh auth status` — tells the user to run `gh auth login` if not authenticated
4. Configures `git rerere.enabled true` globally (remembers conflict resolutions across rebases)
5. Prints what to do next: `cd` into a repo and run `arc init`

Non-destructive. Safe to re-run. Exits non-zero if any check fails so it can be scripted.

### Core loop

```
arc init [--base <branch>] [--prefix <prefix>]
```
Detects trunk (repo default branch) if `--base` is omitted. Creates `.arc/state.json`. Adds `.arc/` to `.gitignore` (creates the file if absent). Idempotent — safe to run again. Runs the same preflight checks as `arc setup` and fails fast with a clear message if deps are missing.

```
arc new <branch>
```
Creates a new git branch from current HEAD. Applies prefix if set. Appends to stack state. Checks out the new branch.

```
arc add <branch>
```
Adopts an existing branch into the stack. The branch must already exist locally. Appends to state without creating or checking out anything. Errors if the branch is already in the stack.

```
arc status [--json]
```
The local representation layer. Default: rich tree to stdout.

Human output:
```
arc  (base: main)
─────────────────────────────────────────────────────
  main
  └── feat/auth       PR #42  ✓  2 commits
      └── feat/api    PR #43  ✗  3 commits  (needs rebase)
          └── feat/ui  no PR  ✓  1 commit
```

`--json`: full schema defined in the JSON output standard section above.

```
arc sync
```
The primary command. Fetches latest from remote, then cascades rebase bottom-up through the stack. On conflict: aborts the in-progress rebase, resets every branch to the SHA it held before `sync` ran, exits code 3, and prints conflicted file paths to stderr. The user resolves conflicts manually then uses `arc rebase --continue` / `arc rebase --abort`.

```
arc push
```
Force-pushes all branches in stack order (`--force-with-lease --atomic`). Does not create or update PRs.

```
arc submit [--draft] [--open] [--json]
```
Creates or updates PRs via `gh pr create` / `gh pr edit`. Each PR targets the branch below it in the stack; the bottom branch targets `base`. Default: creates draft PRs. `--open` marks new and existing PRs as ready for review. Stores PR numbers back into state. `--json` outputs the list of PRs created or updated.

### Modify

```
arc drop <branch> [--json]
```
Removes a branch from the stack state. Cascades rebase for all branches above it. Does not delete the git branch — that is the user's choice.

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

Navigation is thin wrappers around `git checkout`. Merged branches are skipped when navigating from active branches. Navigation commands do not output data; they emit a one-line confirmation to stderr and exit 0.

---

## Output contract

| Stream | Content |
|--------|---------|
| stdout | Data: human-readable by default, JSON with `--json` |
| stderr | Status messages: progress, warnings, errors |

Commands that are purely imperative (`arc push`, navigation) emit only stderr status and exit code — no stdout. This makes them safe to pipe without unexpected output.

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
| 6 | Setup check failed | Run `arc setup` and follow instructions |

---

## The full loop

```bash
# New machine: verify dependencies and configure git
arc setup

# In your repo: initialize the stack
arc init --base main --prefix feat

# Create branches as you work
arc new auth
# ... git add, git commit ...
arc new api
# ... git add, git commit ...
arc new ui
# ... git add, git commit ...

# Check your stack
arc status

# Keep everything rebased on main
arc sync

# Push and open draft PRs
arc push && arc submit --draft

# Respond to review feedback on a lower branch
arc checkout feat/auth
# ... amend commit ...
arc sync          # cascades rebase through api and ui automatically
arc push && arc submit

# Full one-liner once you know your way around
arc sync && arc push && arc submit --open
```

---

## Agent usage

Agents should:
- Run `arc setup` on a new environment before any other command
- Always use `--json` for parsing output
- Use exit codes for flow control, not stdout parsing
- Run `arc status --json` to understand stack state before any operation
- Use `arc rebase --continue` / `arc rebase --abort` on exit code 3
- Never run commands that require interaction — all `arc` commands are non-interactive by design

The full agent skill is in `skills/arc.md` and is the authoritative reference for agent usage.

---

## Adding new features

The extension pattern is always the same:

1. Add a pure function to `ops.py` that computes what needs to happen given the current state
2. Add thin wrappers to `git.py` or `github.py` if new side effects are needed
3. Add a command to `cli.py` that reads state → calls ops → calls git/github → writes state
4. Add `--json` output to the command following the snake_case contract
5. Update `skills/arc.md` in the same commit

No existing module needs to change for a new command. The dependency rule ensures nothing is coupled that shouldn't be.

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
- Not a TUI (yet). `arc status` is the representation layer for V1. A `textual`-based TUI is a natural V2 that imports `ops.py` directly — no CLI layer needed.
- Not responsible for commit authoring. `git add` and `git commit` are yours. `arc` manages the stack, not your commits.
