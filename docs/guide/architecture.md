# Architecture

How arc is built and why the design choices landed where they did.

---

## Overview

arc is a Python CLI built on [Click](https://click.palletsprojects.com/) with [Rich](https://rich.readthedocs.io/) for terminal output. It wraps `git` and `gh` via subprocess rather than using libgit2 or the GitHub API directly. The source is structured so that pure logic (no I/O) is fully separated from command handlers.

```
arc/
├── cli.py              # Click group + global flags only
├── commands/           # One module per command family
│   ├── stack.py        # new, add, status, drop
│   ├── sync.py         # sync, rebase, restack
│   ├── submit.py       # submit, push
│   ├── nav.py          # checkout, up, down, top, bottom, tip
│   ├── diagnostics.py  # doctor, dashboard, stack analyze
│   └── _shared.py      # cross-command helpers (error formatting, setup check)
├── state.py            # Stack state read/write (.arc/state.json)
├── ops.py              # Pure stack logic (no I/O)
├── cascade.py          # Resumable cascade rebase engine
├── git.py              # subprocess wrappers for git
├── github.py           # subprocess wrappers for gh
├── hooks.py            # Lifecycle hook runner (stdlib-only)
├── tip.py              # arc-tip branch maintenance
├── graph.py            # Stack graph / critical path analysis
└── conflicts.py        # Conflict prediction (overlapping file detection)
```

---

## State: per-clone, not per-repo

`.arc/state.json` is **git-ignored and per-clone**. This was a deliberate choice.

**Why not committed?**

Stack shape is a property of a developer's working session, not the codebase. Two people cloning the same repo will have different stacks — or no stack at all. If state were committed, every `arc new` or `arc land` would require a commit, polluting history with bookkeeping noise and creating merge conflicts whenever two people touched the stack simultaneously.

**Schema (v1):**

```json
{
  "version": 1,
  "base": "main",
  "prefix": "feat",
  "branches": [
    { "name": "feat/auth", "pr_number": 42, "revision": 3 },
    { "name": "feat/api",  "pr_number": 43, "revision": 3 }
  ],
  "metadata": {
    "version_check_ts": 1720000000,
    "version_check_latest": "0.7.1"
  }
}
```

`branches` is ordered: index 0 is the bottommost branch, the last entry is the topmost.

---

## subprocess over libgit2

arc shells out to `git` and `gh` rather than using libgit2, pygit2, or the GitHub REST/GraphQL API directly.

For `git`: `git rebase`, `git merge`, and conflict resolution are complex behaviors with decades of edge-case handling baked into the `git` binary. libgit2 does not expose the full rebase machinery. Shelling out gets the real behavior, including rerere replay, hooks, and `.git/rebase-merge` state that `arc rebase --continue` relies on.

For `gh`: The `gh` CLI handles authentication, token refresh, and most API quirks. arc doesn't manage OAuth flows or store credentials; that's `gh`'s job. This also means arc works wherever `gh` works (GitHub.com, GitHub Enterprise Server with the right `GH_HOST`).

---

## Cascade rebase engine (`cascade.py`)

The cascade rebase is the core operation that makes stacking useful. The engine in `cascade.py` is a pure function — it takes a rebase plan and executes it step by step, returning a typed result instead of calling `sys.exit`.

**Plan step:**

```python
class RebasePlanStep(TypedDict):
    branch: str          # branch to rebase
    onto: str            # rebase onto this branch
    old_base: str        # optional: use git rebase --onto (for squash-merges)
```

**Result union:**

```python
CascadeResult = CascadeDone | CascadePaused | CascadeError
```

When a conflict occurs, the engine writes `.arc/rebase-in-progress.json` before pausing:

```
{
  "command": "sync",
  "plan": ["..."],
  "completed": ["feat/auth"],
  "pre_shas": { "feat/auth": "abc123", "feat/api": "def456", "feat/ui": "ghi789" },
  "started_at": "2026-07-12T10:00:00+00:00"
}
```

`pre_shas` records where each branch pointed before the cascade started. If the user runs `arc rebase --abort`, arc resets every branch back to its recorded SHA — including branches that had already rebased cleanly. This gives true all-or-nothing semantics even for multi-step rebases.

**`arc rebase --continue`** reads the state file, skips the completed branches, and resumes from the conflicting one.

**`arc land` and `arc drop`** also run through `cascade.py` (to restack the branches above after removing a branch). The `old_base` field enables `git rebase --onto` for squash-merge cases.

---

## `git rebase --onto` for squash-merges

When GitHub squash-merges a PR, it creates one new commit on `main` that doesn't share history with any of the commits on the PR branch. A plain `git rebase feat/api onto main` would see the squashed commits as "already applied" — but git can't match them, so they appear as duplicates.

`git rebase --onto main feat/auth feat/api` tells git to replay only the commits that are on `feat/api` but not on `feat/auth` — the commits actually added by `feat/api`, not the squashed ones. arc detects the merge strategy via the GitHub API (comparing the merge commit SHA against the branch tip) and chooses the right form automatically.

---

## Hooks: stdlib only

`arc/hooks.py` uses only the Python standard library. It does not depend on Click or Rich, so the module can be copied into another project without pulling in arc's dependencies.

Hooks receive context via environment variables (always available in shell scripts) and a JSON blob on stdin (available in any language that can read stdin). The JSON-on-stdin pattern was chosen over command-line arguments because it scales to arbitrary data without flag combinatorial explosion.

---

## `gh issue create --repo` for `arc report`

`arc report` and `arc feedback` file issues in arc's own GitHub repo (`yash-srivastava19/arc-stack`), not in the user's current repo. Without an explicit `--repo`, `gh issue create` infers the target from the cwd's git remote — which would file issues in whatever repo the user is working in.

The fix is simple: always pass `--repo yash-srivastava19/arc-stack` explicitly. The `ARC_REPO` constant in `arc/github.py` is the single source of truth.

---

## Typed exceptions and exit codes

arc uses a typed exception hierarchy (`arc/exceptions.py`) rather than `sys.exit` inside library code:

```
ArcError (base)
├── NotInitializedError   → exit 2
├── GitHubError           → exit 4
├── ValidationError       → exit 5
├── SetupError            → exit 6
└── HookError             → exit 7
```

Command handlers catch these at the top level and translate them into the appropriate exit code and error message. This makes pure logic testable without mocking `sys.exit` and ensures consistent error formatting across all commands.
