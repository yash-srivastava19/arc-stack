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

**Unix first.** Every command does one thing. Output to stdout, status to stderr. `--json` makes any command machine-readable — explicit, never inferred. Composable by design: the output of one command is the input of the next.

**Functional core, imperative shell.** Domain logic is pure functions that compute what needs to happen. Side effects (git, GitHub API) live only at the edges. Separate braids, no tangles.

**Simple Made Easy.** Simple = each module has one role, one job. Easy = the common path is one command. Don't complect concerns — separate modify from navigate, push from submit, human output from machine output. State is data, not behavior.

**Fire and forget.** `arc sync && arc push && arc submit`. Users stay in control but are not burdened by mechanics.

**Conversational.** Every command suggests the next step. The tool teaches itself through use. Error messages name the fix, not just the problem.

**Agent-friendly by design.** Every command has `--json`. Exit codes are meaningful and documented. `--dry-run` everywhere. The skill document lives in the repo alongside the code and is updated in the same commit when the CLI changes.

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
cli.py   → ops.py, state.py, git.py, github.py
ops.py   → state.py only (no git, no github — pure)
state.py → nothing (pure data)
git.py   → nothing (thin shell)
github.py → nothing (thin shell)
```

`ops.py` never calls `git.py` or `github.py`. It computes plans; `cli.py` executes them. Trivially testable. Execution layer is swappable.

### Extension point: TUI

A future TUI does not go through `cli.py`. It imports `ops.py` directly for pure computations and calls `git.py` / `github.py` for side effects. `cli.py` is only the terminal text interface — not the API. `ops.py` is the API. Keep its functions small, well-named, and return-value-driven.

---

## State

State lives at `.arc/state.json` in the repo root. Git-ignored — per-clone, per-user, not shared.

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

- `version`: schema version, incremented on breaking changes. Readers reject unknown versions.
- `base`: trunk branch all stacks root from.
- `prefix`: optional, applied automatically on `arc new`.
- `branches`: ordered array, index 0 = bottom (closest to trunk).
- `metadata`: reserved for future extensibility. Always present, initially empty.

`state.py` owns all reads and writes. No other module touches this file directly.

---

## Standard flags

These flags follow clig.dev conventions and are consistent across all applicable commands.

| Flag | Short | Applicable to | Meaning |
|------|-------|---------------|---------|
| `--json` | | data-producing commands | Machine-readable JSON output to stdout. snake_case keys, nulls explicit, arrays never null. |
| `--plain` | | `arc status` | Newline-delimited branch list to stdout. For grep, awk, pipes. |
| `--dry-run` | `-n` | `arc sync`, `arc push`, `arc submit`, `arc drop` | Print what would happen, execute nothing. Safe to run anywhere. |
| `--force` | `-f` | `arc drop` | Skip confirmation prompt. Required in non-interactive environments. |
| `--quiet` | `-q` | all commands | Suppress non-essential stderr. Errors and exit codes still emitted. |
| `--no-color` | | all commands | Disable ANSI color. Also respected via `NO_COLOR` env var. |
| `--version` | | top-level `arc` | Print version and exit. |

**Color contract:** Colors are for humans. When stdout is piped, Rich automatically strips ANSI codes. `NO_COLOR=1` disables color globally. `--no-color` disables it per invocation. Output *format* never changes based on environment — only color does. This is not TTY detection for format switching; it is color hygiene.

**Dry-run contract:** `--dry-run` prints each action it *would* take, prefixed with `[dry-run]`, to stderr. Nothing is written to disk, no git commands mutate state, no GitHub calls are made. Exit code 0 if the plan is valid, non-zero if preconditions would fail.

**Quiet contract:** `-q` suppresses next-step suggestions, progress lines, and informational messages. Errors still print to stderr. Exit codes are unaffected. Designed for CI and scripts that only care about success/failure.

---

## JSON output standard

All `--json` output: snake_case keys, nulls explicit (never omitted), arrays always arrays (never null when empty). JSON is only written to stdout on exit code 0. Errors go to stderr as plain text.

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

---

## Commands

### Onboarding

```
arc setup [--json] [-q]
```

One-time environment check. Run this first on a new machine. It:
1. Verifies `git` is installed and accessible
2. Verifies `gh` is installed
3. Checks `gh auth status` — tells the user exactly what to run if not authenticated
4. Configures `git rerere.enabled true` globally (conflict memory across rebases)
5. Suggests next step: `cd` into a repo and run `arc init`

Non-destructive. Safe to re-run. Exits non-zero if any check fails — scriptable. Each failed check prints the exact command to fix it.

### Core loop

```
arc init [--base <branch>] [--prefix <prefix>] [--json] [-q]
```
Detects trunk (repo default branch) if `--base` is omitted. Creates `.arc/state.json`. Adds `.arc/` to `.gitignore` (creates the file if absent). Idempotent — safe to run again. Runs the same preflight checks as `arc setup` and fails fast with actionable messages if deps are missing.

_Next step hint (stderr):_ `Stack initialized. Run 'arc new <branch>' to create your first branch.`

```
arc new <branch> [-q]
```
Creates a new git branch from current HEAD. Applies prefix if set. Appends to stack state. Checks out the new branch. Errors with a clear message if the branch already exists.

_Next step hint (stderr):_ `Branch <name> created. Commit your changes, then run 'arc new <branch>' to add another or 'arc status' to view your stack.`

```
arc add <branch> [-q]
```
Adopts an existing branch into the stack at the top. The branch must already exist locally. Appends to state without checking out. Errors if the branch is already in the stack.

```
arc status [--json] [--plain] [-q]
```
The local representation layer. Three output modes:

**Default (human):**
```
arc  (base: main)
─────────────────────────────────────────────────────
  main
  └── feat/auth       PR #42  ✓  2 commits
      └── feat/api    PR #43  ✗  3 commits  (needs rebase)
          └── feat/ui  no PR  ✓  1 commit

→ Run 'arc sync' to rebase feat/api onto feat/auth.
```

**`--plain`** (for grep, awk, pipes — one branch per line, bottom to top):
```
feat/auth
feat/api
feat/ui
```

**`--json`:** full schema defined in the JSON output standard section.

The hint line at the bottom of human output is the "next step" — it reads the stack state and suggests the most relevant action. It does not appear with `--plain` or `--json`.

```
arc sync [-n] [-q] [--json]
```
The primary command. Fetches latest from remote, then cascades rebase bottom-up through the stack. Prints `Fetching...` to stderr within 100ms of invocation so users know it is running.

On conflict: aborts the in-progress rebase, resets every branch to the SHA it held before `sync` ran, exits code 3, and prints conflicted file paths to stderr with instructions: `Resolve conflicts in <file>, then run 'arc rebase --continue'.`

`-n` (dry-run): prints each rebase it *would* perform and whether each branch is already up to date. No git operations executed.

_Next step hint (stderr, on success):_ `Stack synced. Run 'arc push' to push to remote.`

```
arc push [-n] [-q] [--json]
```
Force-pushes all branches in stack order (`--force-with-lease --atomic`). Does not create or update PRs.

`-n` (dry-run): prints which branches would be pushed and their current SHAs.

_Next step hint (stderr, on success):_ `Pushed <n> branches. Run 'arc submit' to create pull requests.`

```
arc submit [--draft] [--open] [-n] [-q] [--json]
```
Creates or updates PRs via `gh pr create` / `gh pr edit`. Each PR targets the branch below it in the stack; the bottom branch targets `base`. Default: creates draft PRs. `--open` marks new and existing PRs as ready for review. Stores PR numbers back into state.

`-n` (dry-run): prints which PRs would be created or updated and their target bases.

`--json` output:
```json
{
  "created": [
    { "branch": "feat/ui", "pr_number": 44, "pr_url": "https://github.com/..." }
  ],
  "updated": [
    { "branch": "feat/auth", "pr_number": 42, "pr_url": "https://github.com/..." },
    { "branch": "feat/api",  "pr_number": 43, "pr_url": "https://github.com/..." }
  ]
}
```

_Next step hint (stderr, on success):_ `PRs ready. View your stack with 'arc status'.`

### Modify

```
arc drop <branch> [-f] [-n] [-q] [--json]
```
Removes a branch from the stack state. Cascades rebase for all branches above it. Does not delete the git branch.

In interactive mode (stdin is TTY), prompts: `Remove feat/auth from stack? [y/N]:` — defaults to no.
In non-interactive mode, requires `-f` / `--force` or exits code 5 with: `Use --force to drop a branch non-interactively.`

`-n` (dry-run): prints which branches would be restacked, without modifying anything.

```
arc rebase [--upstack | --downstack] [--continue | --abort] [-n] [-q] [--json]
```
Fine-grained rebase control. Default: entire stack. `--upstack`: current branch to top. `--downstack`: bottom to current. `--continue` / `--abort` for conflict resolution. Validation runs before any rebase begins — if the stack is already clean, says so and exits 0.

### Navigation

```
arc checkout <n | branch>    # by index (1-based) or branch name
arc up [n]                   # move n branches toward top (default: 1)
arc down [n]                 # move n branches toward trunk (default: 1)
arc top                      # jump to topmost branch
arc bottom                   # jump to bottommost non-merged branch
```

Thin wrappers around `git checkout`. Merged branches are skipped when navigating from active branches. Navigation commands emit one confirmation line to stderr and exit 0. No stdout output.

---

## Output contract

| Stream | Content |
|--------|---------|
| stdout | Data only: human tree, `--plain` list, or `--json`. Never mixed with status. |
| stderr | Status, progress, next-step hints, errors. Never data. |

**Progress:** Any command that makes a network call or runs a rebase prints a status line to stderr within 100ms. Users should never wonder if the process hung.

**Next-step hints:** Every command that succeeds prints one hint line to stderr suggesting the next action. Suppressed by `-q`. Not shown with `--json` or `--plain`. The hint reads current state — it is not a static string.

**Error messages:** Written in plain language. Always name the exact fix. Examples:
- `Not in a stack. Run 'arc init --base main' to create one.`
- `Branch feat/auth is not in the stack. Use 'arc add feat/auth' to adopt it.`
- `gh is not authenticated. Run 'gh auth login' then retry.`

**Ctrl-C during sync:** If interrupted mid-rebase, arc catches SIGINT, aborts the rebase in progress, resets all branches to their pre-sync SHAs, prints `Interrupted. Stack restored to previous state.` to stderr, and exits code 1. A second Ctrl-C skips cleanup and exits immediately.

---

## Exit codes

| Code | Meaning | Recovery |
|------|---------|----------|
| 0 | Success | — |
| 1 | Generic error | Read stderr |
| 2 | Not in a stack | Run `arc init` |
| 3 | Rebase conflict | Resolve files, `arc rebase --continue` or `arc rebase --abort` |
| 4 | GitHub API failure | Check `gh auth status`, retry |
| 5 | Invalid arguments | Read stderr for exact fix |
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

# Preview what status looks like
arc status

# Verify what sync would do before running it
arc sync -n

# Keep everything rebased on main
arc sync

# Dry-run push to confirm branches before force-pushing
arc push -n && arc push

# Create draft PRs
arc submit --draft

# Respond to review: go to the right branch, amend, sync everything above
arc checkout feat/auth
# ... amend commit ...
arc sync && arc push && arc submit --open

# Script-friendly: check if any branch needs rebase
arc status --json | jq '.branches[] | select(.needs_rebase) | .name'

# Plain output for quick branch listing
arc status --plain | xargs -I{} echo "Checking {}"
```

---

## Agent usage

Agents should:
- Run `arc setup` first on a new environment
- Use `arc status --json` to read state before any operation
- Always use `--json` for output parsing
- Use `-n` / `--dry-run` to preview destructive operations before running them
- Use `-f` / `--force` on `arc drop` to skip interactive confirmation
- Use `-q` to suppress hints and progress output when running in pipelines
- Use exit codes for flow control — never parse stderr
- On exit code 3: read stderr for conflicted file paths, resolve, then `arc rebase --continue`

The full agent skill is in `skills/arc.md`.

---

## Adding new features

1. Add a pure function to `ops.py` that computes what needs to happen given the current state
2. Add thin wrappers to `git.py` or `github.py` if new side effects are needed
3. Add a command to `cli.py` that reads state → calls ops → calls git/github → writes state
4. Add `--json`, `-n`, `-q` to the command following the standard flags contract
5. Add a next-step hint at the end of the success path
6. Update `skills/arc.md` in the same commit

No existing module needs to change for a new command.

---

## Distribution

Install via `pipx` — no venv management, globally available, single command:

```bash
pipx install arc-stack
```

`pipx` installs into an isolated environment and puts `arc` on `PATH`. No manual activation, no `pip install` into system Python. For CI environments, `pip install arc-stack` into whatever environment is active.

The package name is `arc-stack` (PyPI). The command is `arc`.

---

## Dependencies

| Dependency | Role |
|-----------|------|
| Python 3.11+ | Runtime |
| `click` | CLI framework, argument parsing, help generation |
| `rich` | Terminal output — tree, colors, progress. Auto-strips ANSI when piped. |
| `git` (subprocess) | All git operations |
| `gh` CLI | GitHub API (auth, PR create/edit/view) |

No GitHub API token management. Auth is delegated to `gh auth`. No telemetry, no analytics, no phone-home.

---

## What this is not

- Not a SaaS tool. No accounts, no dashboards, no telemetry.
- Not a wrapper around `gh stack`. We call `gh` for auth and PR operations only.
- Not a TUI (yet). `arc status` is the representation layer for V1. A `textual`-based TUI is a natural V2 that imports `ops.py` directly — no CLI layer needed.
- Not responsible for commit authoring. `git add` and `git commit` are yours. `arc` manages the stack, not your commits.
