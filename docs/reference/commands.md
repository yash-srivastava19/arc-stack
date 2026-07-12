# Command reference

All commands accept `-h`/`--help`. Global flags (`--no-color`, `--no-input`, `--verbose`, `--version`) apply to every command and must come before the subcommand name.

---

## Quick reference

| Command | What it does |
|---------|-------------|
| [`arc setup`](#arc-setup) | Verify environment, configure git |
| [`arc init`](#arc-init) | Initialize a stack |
| [`arc new`](#arc-new) | Create a branch and add it to the stack |
| [`arc add`](#arc-add) | Adopt an existing branch into the stack |
| [`arc status`](#arc-status) | Show the stack |
| [`arc sync`](#arc-sync) | Fetch + cascade rebase |
| [`arc rebase`](#arc-rebase) | Cascade-rebase all or part of the stack |
| [`arc restack`](#arc-restack) | Restack one branch without a full sync |
| [`arc push`](#arc-push) | Force-push all branches |
| [`arc submit`](#arc-submit) | Create or update PRs |
| [`arc land`](#arc-land) | Land a merged PR, restack above |
| [`arc edit`](#arc-edit) | Amend a branch's commit and cascade the change up |
| [`arc amend`](#arc-amend) | Append PR link to commit message |
| [`arc drop`](#arc-drop) | Remove a branch, restack above |
| [`arc checkout`](#arc-checkout) | Switch to a branch by name or index |
| [`arc up`](#arc-up-arc-down) / [`arc down`](#arc-up-arc-down) | Move through the stack |
| [`arc top`](#arc-top-arc-bottom) / [`arc bottom`](#arc-top-arc-bottom) | Jump to stack ends |
| [`arc tip`](#arc-tip) | Create/update `arc-tip` branch at the stack's top |
| [`arc stack analyze`](#arc-stack-analyze) | Critical path, safe-to-land branches, blockers |
| [`arc stack snapshot`](#arc-stack-snapshot) | Full stack snapshot: status + PR health + analysis |
| [`arc doctor`](#arc-doctor) | Check environment and stack validity |
| [`arc dashboard`](#arc-dashboard) | Interactive TUI for PR status |
| [`arc config`](#arc-config) | Read and write arc configuration |
| [`arc report`](#arc-report) | File a bug or feedback issue |
| [`arc schema`](#arc-schema) | Print JSON Schema for a command's `--json` output |
| [`arc upgrade`](#arc-upgrade) | Upgrade arc to the latest version |
| [`arc completions`](#arc-completions) | Print shell completion script |

---

## arc setup

```
arc setup [-q]
```

Checks that `git` and `gh` are on `PATH`, that `gh` is authenticated, and that `git rerere` is enabled. Enables rerere if it isn't. Does not modify any repo state.

Run this on every new machine before using arc.

---

## arc init

```
arc init [--base <branch>] [--prefix <prefix>] [-q]
```

Initializes a stack in the current repo.

| Flag | Default | Description |
|------|---------|-------------|
| `--base` | repo default branch | Trunk branch the stack is rooted on |
| `--prefix` | _(none)_ | Prepended to branch names created by `arc new` |
| `-q` | `false` | Suppress output |

Creates `.arc/state.json` (git-ignored), adds it to `.gitignore`, and scaffolds `.arc/hooks/` with sample files. Safe to re-run — updates base/prefix in place.

---

## arc new

```
arc new <branch> [-q]
```

Creates a new git branch from the current HEAD, adds it to the top of the stack, and checks it out. If a prefix is set, `arc new auth` creates `feat/auth`.

---

## arc add

```
arc add <branch> [-q]
```

Adopts an existing local branch into the stack at the current position (above the current branch). The branch must already exist; `arc add` does not create it.

---

## arc status

```
arc status [--json | --plain] [-q]
```

Shows the current stack: branch names, positions, commit counts, PR numbers and states, and which branch is current.

| Flag | Description |
|------|-------------|
| `--json` | Structured JSON output (see [JSON output](json-output.md)) |
| `--plain` | Branch names only, one per line |
| `-q` | Suppress extra output |

---

## arc sync

```
arc sync [-n] [-q] [--json] [--skip-hooks]
```

Fetches from remote, then cascade-rebases the stack bottom-up. Fires `pre-sync` and `post-sync` hooks.

| Flag | Description |
|------|-------------|
| `-n` | Dry run: show the rebase plan without executing |
| `-q` | Quiet |
| `--json` | Structured output |
| `--skip-hooks` | Skip `pre-sync`/`post-sync` hooks |

If a conflict occurs, arc exits with code `3`. Resolve the conflict, then run `arc rebase --continue`. See [Syncing](../guide/syncing.md).

---

## arc rebase

```
arc rebase [--upstack | --downstack | <branch>] [--continue | --abort] [-n] [-q]
```

Cascade-rebases all or part of the stack (without fetching from remote).

| Flag | Description |
|------|-------------|
| _(no flag)_ | Rebase the entire stack |
| `--upstack` | Current branch and everything above it |
| `--downstack` | Current branch and everything below it |
| `--continue` | Resume after a conflict |
| `--abort` | Roll back all branches to their pre-rebase state |
| `-n` | Dry run |
| `-q` | Quiet |

---

## arc restack

```
arc restack [<branch>] [-n] [-q]
```

Rebases one branch onto its parent in the stack without touching the branches above it. Faster than a full `arc rebase` when only one branch needs updating.

---

## arc push

```
arc push [-n] [-q] [--json] [--skip-hooks]
```

Force-pushes all stack branches to remote in order (bottom to top). Increments each branch's revision counter. Fires `pre-push` and `post-push` hooks.

| Flag | Description |
|------|-------------|
| `-n` | Dry run |
| `-q` | Quiet |
| `--json` | Structured output |
| `--skip-hooks` | Skip `pre-push`/`post-push` hooks |

---

## arc submit

```
arc submit [--draft | --open] [--skip-hooks] [-n] [-q] [--json]
```

Creates or updates PRs for each branch in the stack. Each PR targets the branch below it (or the base for the bottommost). Injects a stack map into every PR description. Fires `pre-submit` and `post-submit` hooks.

| Flag | Description |
|------|-------------|
| `--draft` | Force all PRs to draft mode |
| `--open` | Mark all draft PRs as ready for review |
| `--skip-hooks` | Skip `pre-submit`/`post-submit` hooks |
| `-n` | Dry run |
| `-q` | Quiet |
| `--json` | Structured output |

---

## arc land

```
arc land [<branch>] [-f] [-n] [-q] [--json] [--skip-hooks] [--keep-branch]
```

Lands a merged PR: verifies the merge, detects squash-merge vs regular merge, rebases branches above onto the base, removes the branch from the stack, and deletes the local branch. Fires `pre-land` and `post-land` hooks.

| Flag | Default | Description |
|------|---------|-------------|
| `<branch>` | current branch | Branch to land |
| `-f` | `false` | Skip confirmation prompt |
| `--keep-branch` | `false` | Delete from stack but keep the local git branch |
| `-n` | `false` | Dry run |
| `-q` | `false` | Quiet |
| `--json` | `false` | Structured output |
| `--skip-hooks` | `false` | Skip hooks |

If restacking hits a conflict, arc pauses. Resolve it, run `arc rebase --continue`, then re-run `arc land -f` to finish.

---

## arc edit

```
arc edit [<branch>] [-m <message>] [--interactive] [--no-push]
         [--continue | --abort] [--skip-hooks] [--dry-run] [-q] [--json]
```

Amends a branch's HEAD commit and cascade-rebases all branches above it. Same pause-and-resume conflict safety as `arc sync`.

| Flag | Description |
|------|-------------|
| `<branch>` | Branch to amend (defaults to current branch) |
| `-m` | New commit message (omit to keep current message) |
| `--interactive` | Interactive rebase within the branch before amending |
| `--no-push` | Skip the force-push after restack |
| `--continue` | Resume after a conflict |
| `--abort` | Undo the edit and restore the original state |
| `--skip-hooks` | Skip pre-edit/post-edit hooks |
| `--dry-run` | Preview what would happen |
| `-q` | Quiet |
| `--json` | Structured output |

**Example:**

```bash
git add src/auth.py
arc edit feat/auth            # amend feat/auth, restack api and ui
arc edit feat/auth -m "fix: improve error handling"   # change message too
```

---

## arc amend

```
arc amend [-q]
```

Appends the PR link and stack position to the HEAD commit message. Run after `arc submit` to make `git log` on landed commits trace back to the PR.

---

## arc drop

```
arc drop <branch> [-f] [-n] [-q] [--json]
```

Removes a branch from the stack and restacks the branches above it. Deletes the local branch. Does not check GitHub — use `arc land` if the PR is merged.

| Flag | Description |
|------|-------------|
| `<branch>` | Branch to remove |
| `-f` | Skip confirmation |
| `-n` | Dry run |
| `-q` | Quiet |
| `--json` | Structured output |

---

## arc checkout

```
arc checkout <name | index>
```

Switches to a stack branch by name or 1-based index. `arc checkout 1` checks out the bottommost branch. `arc checkout feat/api` works exactly like `git checkout feat/api` but limited to stack branches.

---

## arc up arc down

```
arc up [n]
arc down [n]
```

Moves `n` branches toward the top (`up`) or toward the base (`down`). `n` defaults to 1.

---

## arc top arc bottom

```
arc top
arc bottom
```

Jumps to the topmost or bottommost branch in the stack.

---

## arc tip

```
arc tip
```

Creates (or updates) an `arc-tip` branch pointing at the topmost branch in the stack, and checks it out. Once `arc-tip` exists, arc keeps it current whenever the stack changes shape.

---

## arc stack analyze

```
arc stack analyze [--json]
```

Shows the critical path (longest chain of unmerged PRs), which branches are safe to land now, and which are blocked. Useful for planning the order of reviews.

---

## arc stack snapshot

```
arc stack snapshot [--json]
```

Full snapshot: `arc status` + PR health (CI status, review decisions, draft state) + analysis output in one call. Designed for dashboards and scripts.

---

## arc doctor

```
arc doctor
```

Checks git, `gh`, authentication, stack validity, and any paused rebase or edit state. Prints a pass/fail for each check and hints for what to fix.

---

## arc dashboard

```
arc dashboard
```

Launches an interactive TUI showing all PRs in the stack with their CI status, review decisions, and draft state. Use arrow keys to navigate. Press `q` to quit.

---

## arc config

```
arc config list
arc config get <key>
arc config set <key> <value>
```

Reads and writes `.arc/config.json` (committed, shared with your team). See [Configuration](config.md) for the full schema.

---

## arc report

```
arc report [--bug | --feedback] [--message <text>] [-n] [-q]
```

Files a GitHub issue in arc's own repo (`yash-srivastava19/arc-stack`), not in your current repo. Opens an interactive prompt if `--message` is omitted.

| Flag | Description |
|------|-------------|
| `--bug` | Label as a bug report |
| `--feedback` | Label as a feature request / feedback |
| `--message` | Issue body (skips interactive prompt) |
| `-n` | Dry run: print what would be filed without creating the issue |

---

## arc schema

```
arc schema {status | submit | analyze}
```

Prints the JSON Schema for a command's `--json` output. Use to validate arc output in typed pipelines.

---

## arc upgrade

```
arc upgrade
```

Upgrades arc using the package manager that installed it (Homebrew, pipx, or uv tool).

---

## arc completions

```
arc completions {bash | zsh | fish}
```

Prints the shell completion script for the given shell. See [Install](../start/install.md) for setup instructions.
