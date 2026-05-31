# arc — Design Spec
_2026-05-31_

## Problem

Large PRs are expensive to review. Splitting them into stacked PRs is the right answer, but managing a stack by hand is painful: cascading rebases, force-pushing in the right order, retargeting PR bases when something merges. Existing tools (Graphite, gh-stack) solve this but are either SaaS or couple you to GitHub's official extension with a clunky modify story.

`arc` is a local CLI tool that owns the full stacked-PR loop — create, sync, push, submit, modify, land — with zero ceremony.

---

## Name

**`arc`** — a trajectory of changes building toward something. One syllable. Natural in usage: `arc new`, `arc sync`, `arc submit`, `arc land`.

---

## Lineage

`arc` draws from three proven tools and takes the best of each:

| Tool | What it nailed |
|------|----------------|
| **Phabricator/Arcanist** | Pre-submit quality gates. `arc land` as a first-class landing operation. In-place diff updates (amend, don't stack commits). |
| **Gerrit** | Patch set versioning — every update is a numbered revision. Commit message as the PR description. Identity survives rebases. |
| **Critique (Google)** | Attention set — who needs to act next is always clear. Separation of concerns — the tool does one thing well. |

The commit is the unit of review, not the branch. Branches are infrastructure.

---

## Philosophy

**Unix first.** Every command does one thing. Output to stdout, status to stderr. `--json` makes any command machine-readable — explicit, never inferred. Composable by design.

**Functional core, imperative shell.** Domain logic is pure functions that compute what needs to happen. Side effects (git, GitHub API) live only at the edges. Separate braids, no tangles.

**Simple Made Easy.** Simple = each module has one role, one job. Easy = the common path is one command. Don't complect concerns.

**Fire and forget.** `arc sync && arc push && arc submit`. Users stay in control but are not burdened by mechanics.

**Conversational.** Every command suggests the next step. Error messages name the fix, not just the problem. The tool teaches itself through use.

**Agent-friendly by design.** Every command has `--json`. Exit codes are meaningful and documented. `--dry-run` everywhere. The skill document lives in the repo alongside the code.

**Adaptable by design.** New commands are additive. The state schema is versioned. `ops.py` is the stable interface — both the CLI and any future TUI consume it directly.

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

A future TUI does not go through `cli.py`. It imports `ops.py` directly for pure computations and calls `git.py` / `github.py` for side effects. `ops.py` is the API. Keep its functions small, well-named, and return-value-driven.

---

## State

State lives at `.arc/state.json` in the repo root. Git-ignored — per-clone, per-user, not shared.

```json
{
  "version": 1,
  "base": "main",
  "prefix": "feat",
  "branches": [
    { "name": "feat/auth", "pr_number": 42, "revision": 3 },
    { "name": "feat/api",  "pr_number": 43, "revision": 1 },
    { "name": "feat/ui",   "pr_number": null, "revision": 0 }
  ],
  "metadata": {}
}
```

- `version`: schema version, incremented on breaking changes. Readers reject unknown versions.
- `base`: trunk branch all stacks root from.
- `prefix`: optional, applied automatically on `arc new`.
- `branches`: ordered array, index 0 = bottom (closest to trunk).
- `revision`: how many times this branch has been pushed. 0 = never pushed. Incremented by `arc push`. Shown in PR descriptions ("Revision 3").
- `metadata`: reserved for future extensibility. Always present, initially empty.

`state.py` owns all reads and writes. No other module touches this file directly.

**V1 limitation:** one stack per repo. Multiple independent stacks in the same repo are a V2 feature.

---

## Configuration

Per-repo configuration lives at `.arc/config.json`. Git-committed — shared across the team.

```json
{
  "hooks": {
    "pre-submit": ["npm run lint", "npm test"]
  }
}
```

- `hooks.pre-submit`: list of shell commands run before `arc submit`. Each command must exit 0 or submit is aborted. Run in repo root. Skipped with `--skip-hooks`.

This is the Arcanist quality gate — checks run locally before anything goes up for review. CI still runs after push, but fast local checks catch obvious issues first.

---

## Standard flags

| Flag | Short | Applicable to | Meaning |
|------|-------|---------------|---------|
| `--json` | | data-producing commands | Machine-readable JSON output to stdout. snake_case, nulls explicit. |
| `--plain` | | `arc status` | Newline-delimited branch list. For grep, awk, pipes. |
| `--dry-run` | `-n` | `arc sync`, `arc push`, `arc submit`, `arc drop`, `arc land` | Print what would happen, execute nothing. |
| `--force` | `-f` | `arc drop`, `arc land` | Skip confirmation prompt. Required in non-interactive environments. |
| `--quiet` | `-q` | all commands | Suppress non-essential stderr. Errors and exit codes still emitted. |
| `--no-color` | | all commands | Disable ANSI color. Also respected via `NO_COLOR` env var. |
| `--skip-hooks` | | `arc submit` | Bypass pre-submit hooks. Recorded in stderr as a warning. |
| `--version` | | top-level `arc` | Print version and exit. |

**Color contract:** Colors are for humans. Rich strips ANSI automatically when piped. `NO_COLOR=1` disables globally. Output *format* never changes based on environment — only color does.

**Dry-run contract:** Prints each action prefixed with `[dry-run]` to stderr. Nothing written to disk, no git mutations, no GitHub calls. Exit 0 if plan is valid.

**Quiet contract:** Suppresses next-step hints, progress lines, informational messages. Errors still print. Exit codes unaffected.

---

## JSON output standard

All `--json` output: snake_case keys, nulls explicit, arrays always arrays. JSON written to stdout only on exit code 0. Errors go to stderr as plain text.

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
      "commits": 3,
      "revision": 1,
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
      "revision": 0,
      "needs_rebase": false,
      "is_current": false,
      "is_merged": false
    }
  ]
}
```

---

## PR description format

When `arc submit` creates or updates a PR, it generates the description from two parts:

**1. Commit content** — the commit subject becomes the PR title. The commit body becomes the PR description body. If there are multiple commits on the branch, the branch name (humanized) becomes the title.

**2. Stack map** — appended automatically as a footer block. Reviewers see where this PR sits and can navigate the stack without leaving GitHub:

```
---
**Stack** (3 PRs · base: main)
- ✅ `feat/auth` → [PR #42](url) ← **you are here**
- 🔵 `feat/api`  → [PR #43](url)
- ⚪ `feat/ui`   → no PR yet
```

Icons: ✅ merged, 🔵 open, 🔴 needs rebase, ⚪ not submitted. The stack map is regenerated on every `arc submit` run so it stays current as the stack evolves.

This is what makes the stack navigable for reviewers without any additional tooling — the PR description itself is the map.

---

## Commands

### Onboarding

```
arc setup [--json] [-q]
```

One-time environment check. Run first on a new machine:
1. Verifies `git` is installed
2. Verifies `gh` is installed
3. Checks `gh auth status` — prints exact fix command if not authenticated
4. Configures `git rerere.enabled true` globally (conflict memory across rebases)
5. Suggests: `cd` into a repo and run `arc init`

Non-destructive. Safe to re-run. Exits non-zero if any check fails — scriptable.

### Core loop

```
arc init [--base <branch>] [--prefix <prefix>] [--json] [-q]
```
Detects trunk if `--base` omitted. Creates `.arc/state.json`. Adds `.arc/` to `.gitignore` (creates if absent). Idempotent. Runs preflight checks from `arc setup` and fails fast with actionable messages.

_Hint:_ `Stack initialized. Run 'arc new <branch>' to create your first branch.`

```
arc new <branch> [-q]
```
Creates a new git branch from current HEAD. Applies prefix if set. Appends to stack state. Checks out the new branch.

_Hint:_ `Branch <name> created. Commit your changes, then run 'arc new <branch>' to add another or 'arc status' to view your stack.`

```
arc add <branch> [-q]
```
Adopts an existing branch into the stack at the top. Must exist locally. Errors if already in stack.

```
arc status [--json] [--plain] [-q]
```
The local representation layer. Three output modes:

**Default (human):**
```
arc  (base: main)
─────────────────────────────────────────────────────
  main
  └── feat/auth       PR #42  ✓  2 commits  (rev 3)
      └── feat/api    PR #43  ✗  3 commits  (rev 1)  ← needs rebase
          └── feat/ui  no PR  ✓  1 commit

→ Run 'arc sync' to rebase feat/api onto feat/auth.
```

**`--plain`** (one branch per line, bottom to top — for grep, awk, pipes):
```
feat/auth
feat/api
feat/ui
```

**`--json`:** full schema above.

The hint line reads actual stack state and suggests the most relevant action. Not shown with `--plain` or `--json`.

```
arc sync [-n] [-q] [--json]
```
The primary command. Fetches latest from remote, then cascades rebase bottom-up. Prints `Fetching...` to stderr within 100ms.

**Squash-merge detection:** If a branch's PR was squash-merged on GitHub, the original commits no longer exist in trunk history. `arc sync` detects this automatically and uses `git rebase --onto` to replay upstack commits correctly, skipping the already-landed commits. This matches Gerrit's and gh-stack's approach to squash-merge recovery.

On conflict: aborts the rebase, resets every branch to its pre-sync SHA, exits code 3, prints conflicted file paths to stderr with exact fix instructions.

_Hint:_ `Stack synced. Run 'arc push' to push to remote.`

```
arc push [-n] [-q] [--json]
```
Force-pushes all branches in stack order (`--force-with-lease --atomic`). Increments `revision` in state for each pushed branch. Does not create or update PRs.

_Hint:_ `Pushed <n> branches. Run 'arc submit' to create pull requests.`

```
arc submit [--draft] [--open] [--skip-hooks] [-n] [-q] [--json]
```
Before creating PRs: runs pre-submit hooks from `.arc/config.json`. If any hook exits non-zero, submit is aborted with the hook's output and exit code 1. Use `--skip-hooks` to bypass (logged as a warning).

Creates or updates PRs via `gh pr create` / `gh pr edit`. Each PR:
- Targets the branch below it in the stack (bottom branch targets `base`)
- Gets a description generated from commit message + stack map footer
- Stack map is regenerated on every run, always current

Default: draft PRs. `--open` marks as ready for review. Stores PR numbers back into state.

`--json` output:
```json
{
  "created": [{ "branch": "feat/ui", "pr_number": 44, "pr_url": "..." }],
  "updated": [
    { "branch": "feat/auth", "pr_number": 42, "pr_url": "...", "revision": 3 },
    { "branch": "feat/api",  "pr_number": 43, "pr_url": "...", "revision": 1 }
  ]
}
```

_Hint:_ `PRs ready. View your stack with 'arc status'.`

### Complete the loop

```
arc land [<branch>] [-f] [-n] [-q] [--keep-branch] [--json]
```
The Arcanist-inspired landing operation. Closes the loop when a PR is accepted and merged.

If `<branch>` is omitted, lands the bottommost non-merged branch with an approved PR. Supports landing any prefix of the stack — you can land the bottom 2 of 4 branches, and the remaining 2 rebase correctly.

What it does:
1. Verifies the PR is merged on GitHub (exits code 1 with message if not)
2. Detects merge strategy (regular merge vs. squash-merge)
3. Rebases all branches above it using `git rebase --onto` if squash-merged, or normal rebase if regular-merged — correctly skipping already-landed commits
4. Removes the landed branch from stack state
5. Deletes the local branch (skip with `--keep-branch`)
6. Prints what changed and the new stack state

In interactive mode: confirms before deleting the branch. Non-interactive: requires `-f`.

`-n` (dry-run): prints which branches would be restacked and the detected merge strategy, without executing anything.

_Hint:_ `feat/auth landed. <n> branches restacked. Run 'arc status' to see your updated stack.`

### Modify

```
arc amend [-q]
```
Updates the current HEAD commit message to include stack position and PR link. Appended as a footer — does not replace the commit message body. Use after `arc submit` to keep commit messages in sync with PR state.

Format appended:
```
Arc-PR: https://github.com/owner/repo/pull/42
Arc-Stack-Position: 1/3
```

When the commit is eventually landed and someone reads `git log`, they can trace back to the PR and its position in the stack. This is Gerrit's "commit message as documentation" principle.

```
arc drop <branch> [-f] [-n] [-q] [--json]
```
Removes a branch from stack state. Cascades rebase for all branches above it. Does not delete the git branch.

Interactive mode: `Remove feat/auth from stack? [y/N]:` — defaults to no.
Non-interactive: requires `-f` or exits code 5: `Use --force to drop non-interactively.`

```
arc rebase [--upstack | --downstack] [--continue | --abort] [-n] [-q] [--json]
```
Fine-grained rebase control. Default: entire stack. `--upstack`: current to top. `--downstack`: bottom to current. `--continue` / `--abort` for conflict resolution. Validates stack is not already clean before running.

### Navigation

```
arc checkout <n | branch>    # by index (1-based) or branch name
arc up [n]                   # move n branches toward top (default: 1)
arc down [n]                 # move n branches toward trunk (default: 1)
arc top                      # jump to topmost branch
arc bottom                   # jump to bottommost non-merged branch
```

Thin wrappers around `git checkout`. Merged branches skipped when navigating from active branches. One confirmation line to stderr, no stdout.

---

## Output contract

| Stream | Content |
|--------|---------|
| stdout | Data only: human tree, `--plain` list, or `--json`. Never mixed with status. |
| stderr | Status, progress, next-step hints, errors. Never data. |

**Progress:** Any network call or rebase operation prints a status line within 100ms.

**Next-step hints:** Every successful command prints one hint to stderr suggesting the next action. Suppressed by `-q`, `--json`, `--plain`.

**Error messages:** Plain language, name the exact fix:
- `Not in a stack. Run 'arc init --base main' to create one.`
- `gh is not authenticated. Run 'gh auth login' then retry.`
- `Pre-submit hook failed: npm test (exit 1). Fix the failure or use --skip-hooks.`

**Ctrl-C during sync/land:** Catches SIGINT, aborts in-progress rebase, resets all branches to pre-operation SHAs, prints `Interrupted. Stack restored to previous state.` Exits code 1. Second Ctrl-C skips cleanup and exits immediately.

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
| 7 | Pre-submit hook failed | Fix the failing check or use `--skip-hooks` |

---

## The full loop

```bash
# New machine
arc setup

# Initialize
arc init --base main --prefix feat

# Build the stack
arc new auth && git commit -m "Add auth middleware"
arc new api  && git commit -m "Add API routes"
arc new ui   && git commit -m "Add frontend"

# Check your work
arc status

# Dry-run before doing anything destructive
arc sync -n && arc sync
arc push -n && arc push
arc submit --draft

# Review feedback on a lower branch
arc checkout feat/auth
# amend commit...
arc amend                     # update commit message with PR link
arc sync && arc push && arc submit

# PR approved and merged on GitHub
arc land feat/auth            # removes from stack, rebases api and ui

# Script-friendly queries
arc status --json | jq '.branches[] | select(.needs_rebase) | .name'
arc status --plain | wc -l    # how many branches in stack
```

---

## Agent usage

Agents should:
- Run `arc setup` first on a new environment
- Use `arc status --json` to read state before any operation
- Always use `--json` for output parsing
- Use `-n` to preview destructive operations before running them
- Use `-f` on `arc drop` and `arc land` to skip interactive confirmation
- Use `-q` to suppress hints in pipelines
- Use `--skip-hooks` if pre-submit hooks are not relevant to the agent's task
- On exit code 3: read stderr for conflicted file paths, resolve, `arc rebase --continue`
- On exit code 7: read stderr for the failing hook command and its output

The full agent skill is in `skills/arc.md`.

---

## Adding new features

1. Add a pure function to `ops.py` — computes what needs to happen given current state
2. Add thin wrappers to `git.py` or `github.py` if new side effects are needed
3. Add a command to `cli.py`: read state → call ops → call git/github → write state
4. Add `--json`, `-n`, `-q` following the standard flags contract
5. Add a next-step hint at the end of the success path
6. Update `skills/arc.md` in the same commit

No existing module changes for a new command.

---

## Distribution

```bash
pipx install arc-stack
```

Package name: `arc-stack` (PyPI). Command: `arc`. No venv management, globally available.

---

## Dependencies

| Dependency | Role |
|-----------|------|
| Python 3.11+ | Runtime |
| `click` | CLI framework, argument parsing, help generation |
| `rich` | Terminal output — tree, colors, progress. Auto-strips ANSI when piped. |
| `git` (subprocess) | All git operations |
| `gh` CLI | GitHub API (auth, PR create/edit/view) |

No GitHub API token management. Auth delegated to `gh auth`. No telemetry, no analytics.

---

## What this is not

- Not a SaaS tool. No accounts, no dashboards, no telemetry.
- Not a wrapper around `gh stack`. We call `gh` for auth and PR operations only.
- Not a TUI (yet). `arc status` is the representation layer for V1. A `textual`-based TUI is a natural V2 that imports `ops.py` directly.
- Not responsible for commit authoring. `git add` and `git commit` are yours. `arc` manages the stack, not your commits.
- Not multi-stack in V1. One stack per repo. Multiple independent stacks are V2.
