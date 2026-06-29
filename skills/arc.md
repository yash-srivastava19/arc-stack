---
name: arc
description: Agent-facing skill document for the arc stacked-PR CLI.
metadata_version: 1
---

# arc — stacked pull request manager

`arc` manages a linear stack of git branches that map one-to-one to pull requests. Each branch sits on top of the previous one; PRs are rebased and updated as a unit.

```
trunk (main)
  └── feature/auth          ← index 1, PR #42
        └── feature/api     ← index 2, PR #43
              └── feature/ui ← index 3 (current *), no PR yet
```

State is stored in `.arc/state.json` (gitignored). Configuration lives in `.arc/config.json`.

---

## Agent rules

1. **Always run `arc setup` before using arc in a new environment.** It checks that `git` and `gh` are installed and authenticated. Exit code 6 means the environment is not ready.
2. **Run `arc init` once per repo before any other commands.** Without initialization, every command exits with code 2.
3. **Never run commands that prompt for confirmation without `--force` or `--dry-run`.** `arc land` and `arc drop` prompt interactively when stdin is a tty. In non-interactive contexts, pass `--force` or `--dry-run`.
4. **Use `--json` for machine-readable output.** `status`, `sync`, `push`, `submit`, `land`, `drop`, and `edit` all support `--json`.
5. **Use `--dry-run` before destructive operations.** Rebase, land, drop, sync, push, and edit all support `-n`/`--dry-run`.
6. **Handle exit code 3 (conflict) explicitly.** After a conflict during `arc sync` or `arc rebase`, use `arc rebase --continue`/`--abort`. After a conflict during `arc edit`, use `arc edit --continue`/`--abort`.
7. **`arc submit` creates PRs as draft by default.** Pass `--open` to mark them ready for review.
8. **Branch order is the stack order.** Index 1 is the branch closest to trunk; the highest index is the tip.
9. **Run `arc doctor` to diagnose environment issues.** It checks git, gh, authentication, and stack validity in one command.
10. **`arc edit` saves conflict state to `.arc/edit-in-progress.json`.** If a rebase conflict pauses an edit, the state is persisted — always `arc edit --continue` or `arc edit --abort` before starting a new edit.
11. **`arc push` skips branches already merged into the base.** It checks locally (git cherry) and via GitHub PR state — you will never accidentally resurrect a merged branch's remote.

---

## Quick reference

| Command | Description |
|---------|-------------|
| `arc setup [-q]` | Check environment (git, gh) and enable `git rerere`. |
| `arc init [--base BRANCH] [--prefix PREFIX] [-q]` | Initialize a stack in the current repo. |
| `arc new BRANCH [-q]` | Create a new branch on top of the stack. |
| `arc add BRANCH [-q]` | Adopt an existing local branch into the stack. |
| `arc status [--json] [--plain] [-q]` | Show the stack with PR state and rebase status. |
| `arc sync [-n] [--json] [-q]` | Fetch from remote and cascade-rebase the stack. |
| `arc push [-n] [--json] [-q]` | Force-push all stack branches to remote. |
| `arc submit [--draft] [--open] [--skip-hooks] [-n] [--json] [-q]` | Create or update PRs for the stack. |
| `arc land [BRANCH] [-f] [-n] [--keep-branch] [--json] [-q]` | Land a merged PR and restack branches above it. |
| `arc amend [-q]` | Append `Arc-PR:` and `Arc-Stack-Position:` trailers to the current commit message. |
| `arc drop BRANCH [-f] [-n] [--json] [-q]` | Remove a branch from the stack and restack above it. |
| `arc rebase [--upstack] [--downstack] [--continue] [--abort] [-n] [-q]` | Cascade-rebase the full stack or a subset. |
| `arc checkout TARGET` | Check out a branch by name or 1-based index. |
| `arc up [N]` | Move N branches toward the tip (default: 1). |
| `arc down [N]` | Move N branches toward trunk (default: 1). |
| `arc top` | Jump to the topmost branch. |
| `arc bottom` | Jump to the bottommost branch. |
| `arc restack [BRANCH] [-n] [-q]` | Restack a single branch onto its stack parent without full sync. |
| `arc stack analyze [--json]` | Show critical path, safe-to-land branches, and blockers. |
| `arc edit [BRANCH] [--message TEXT] [--no-push] [-n] [--json] [-q]` | Amend HEAD commit of a branch and auto-restack all upstack branches. |
| `arc edit --continue` | Resume a paused edit after resolving a rebase conflict. |
| `arc edit --abort` | Abort a paused edit and restore all branches to their pre-edit SHAs. |
| `arc doctor` | Check environment: git, gh, auth, stack validity. |
| `arc report --bug [--message TEXT]` | Report a bug (opens editor in TTY, requires `--message` in non-TTY) |
| `arc report --feedback [--message TEXT]` | Share feedback or feature request |

---

## Exit codes

| Code | Meaning | Recovery |
|------|---------|----------|
| 0 | Success | — |
| 1 | Logical error (no PR, stack empty, branch not found) | Read the error message; check `arc status`. |
| 2 | Stack not initialized | Run `arc init`. |
| 3 | Rebase/edit conflict | For `arc sync`/`arc rebase`: resolve then `arc rebase --continue` or `--abort`. For `arc edit`: resolve then `arc edit --continue` or `arc edit --abort`. |
| 5 | Branch not in stack | Verify branch name with `arc status --plain`. |
| 6 | Environment not ready (git or gh missing / not authenticated) | Run `arc setup` and fix the reported issue. |
| 7 | Hook gate failed (`pre-*` hook exited non-zero) | Fix the hook failure or pass `--skip-hooks` to bypass. |

---

## `arc status --json` schema

```json
{
  "base": "main",
  "prefix": "feature",
  "current_branch": "feature/api",
  "branches": [
    {
      "name": "feature/auth",
      "index": 1,
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo/pull/42",
      "pr_state": "OPEN",
      "commits": 3,
      "revision": 2,
      "needs_rebase": false,
      "is_current": false,
      "is_merged": false
    },
    {
      "name": "feature/api",
      "index": 2,
      "pr_number": 43,
      "pr_url": "https://github.com/owner/repo/pull/43",
      "pr_state": "OPEN",
      "commits": 1,
      "revision": 1,
      "needs_rebase": false,
      "is_current": true,
      "is_merged": false
    }
  ]
}
```

Field notes:
- `prefix`: string or `null` if no prefix was configured with `arc init --prefix`.
- `pr_number`: integer or `null` if no PR has been submitted yet.
- `pr_url`: string or `null` if no PR exists or PR info could not be fetched.
- `pr_state`: `"OPEN"`, `"CLOSED"`, `"MERGED"`, or `null` if no PR.
- `revision`: number of times this branch has been pushed (0 = never pushed).
- `needs_rebase`: `true` when the branch's parent is not an ancestor of the branch tip.
- `is_merged`: `true` when `pr_state == "MERGED"`.

---

## `arc submit --json` schema

```json
{
  "created": [
    {"branch": "feature/ui", "pr_number": 44, "pr_url": "https://github.com/owner/repo/pull/44"}
  ],
  "updated": [
    {"branch": "feature/auth", "pr_number": 42, "pr_url": "https://github.com/owner/repo/pull/42", "revision": 2}
  ]
}
```

---

## `arc stack analyze --json` schema

```json
{
  "critical_path": ["feat/auth", "feat/api"],
  "safe_to_land": ["feat/auth"],
  "blocked": {
    "feat/api": "waiting on feat/auth"
  },
  "in_merge_queue": []
}
```

Field notes:
- `critical_path`: full ordered list of branches in landing order.
- `safe_to_land`: branches that are approved, CI passing, and whose parent is ready.
- `blocked`: map of branch name → reason string.
- `in_merge_queue`: branches currently in GitHub merge queue.

---

## `arc edit --json` schema

**Success (all branches restacked):**
```json
{
  "ok": true,
  "state": "done",
  "target": "feat/auth",
  "old_sha": "abc1234",
  "new_sha": "def5678",
  "restacked": ["feat/api", "feat/ui"],
  "pushed": ["feat/auth", "feat/api", "feat/ui"],
  "amendment": {
    "files_changed": ["src/auth.py"],
    "insertions": 12,
    "deletions": 3
  }
}
```

**Paused (rebase conflict mid-restack):**
```json
{
  "ok": false,
  "state": "paused",
  "conflict_branch": "feat/api",
  "conflict_sha": "abc9999",
  "restacked": ["feat/auth"],
  "remaining": ["feat/ui"],
  "hint": "resolve conflicts, then run: arc edit --continue"
}
```

**Aborted:**
```json
{
  "ok": true,
  "state": "aborted",
  "restored": ["feat/auth", "feat/api", "feat/ui"]
}
```

Field notes:
- `pushed`: branches actually force-pushed (skips branches already merged into base).
- `conflict_sha`: the SHA of the branch at the time the conflict occurred (useful for `git rebase --onto`).
- `remaining`: branches that have not yet been restacked (will be attempted after `--continue`).

---

## Configuration (`.arc/config.json`)

```json
{
  "auto_promote_on_land": true
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `auto_promote_on_land` | `true` | After `arc land`, automatically mark the new bottom-of-stack PR as ready for review. Set to `false` to keep the next PR in draft. |

---

## Common agent workflows

### Bootstrap a new stack

```bash
arc setup -q
arc init --base main --prefix feat -q
arc new auth -q        # creates feat/auth
# ... make commits ...
arc new api -q         # creates feat/api on top of feat/auth
arc status --json
```

### Publish the stack

```bash
arc push -q
arc submit --open -q
arc status --json      # confirm pr_number is set on all branches
```

### Sync after trunk changes

```bash
arc sync -q            # fetch + cascade-rebase
arc push -q            # update remote
arc submit -q          # update PR descriptions with new stack positions
```

### Check for conflicts before syncing

```bash
arc sync --dry-run     # shows what would be rebased; exits 0 even if conflicts exist
arc rebase --dry-run   # same for local rebase without fetch
```

### Land a merged PR (standard flow — no arc edit involved)

```bash
# Verify PR is merged first
arc status --json | python3 -c "import sys,json; s=json.load(sys.stdin); print(s['branches'][0]['is_merged'])"
arc land --force -q    # rebases above branches, retargets + reopens child PRs if GitHub
                       # auto-closed them, auto-promotes new bottom-of-stack PR to ready
arc push -q            # push restacked branches
arc submit -q          # update PR descriptions
```

### Drop a branch (non-interactive)

```bash
arc drop feat/api --force -q
```

### Navigate the stack

```bash
arc bottom             # jump to index 1
arc up 2               # move 2 positions toward tip
arc checkout 3         # jump to index 3 directly
arc top                # jump to highest index
```

### Amend a commit in the middle of the stack

```bash
# Stage your changes onto the target branch first
git checkout feat/auth
git add src/auth.py

# Then let arc handle the rest
arc edit feat/auth --json    # amends HEAD, cascade-rebases all upstack branches, force-pushes

# Or amend just the commit message (no staged files needed):
arc edit feat/auth --message "fix: correct token expiry logic"
```

If `arc edit` exits with code 3 (conflict in a child branch):
```bash
# Resolve the conflict in the conflicted branch, then:
git add <resolved-files>
arc edit --continue          # resumes restacking remaining branches

# Or abandon the entire edit (all branches restored to pre-edit SHAs):
arc edit --abort
```

### Land a merged PR with auto-promotion

```bash
# PR #42 (feat/auth) was merged on GitHub
arc land --force -q          # rebases feat/api (above), deletes feat/auth locally,
                             # then automatically marks feat/api's PR as ready for review
arc push -q                  # push the restacked branches
arc submit -q                # update PR descriptions
```

To suppress auto-promote: set `{ "auto_promote_on_land": false }` in `.arc/config.json`.

### Recover from a rebase conflict

```bash
# After exit code 3:
git status             # see conflicted files
# ... resolve conflicts in editor ...
git add <resolved-files>
arc rebase --continue
# If you want to abandon:
arc rebase --abort
```

### Adopt an existing branch

```bash
# Branch already exists locally; not yet in the stack
arc add my-existing-branch -q
arc status --plain
```

---

## arc report — Bug and Feedback Reporting

Users report issues in two ways:

**Interactive (TTY):**
```bash
arc report --bug    # Opens $EDITOR with environment context prefilled
arc report --feedback
```

**Non-interactive (agents, scripts):**
```bash
arc report --bug --message "squash-merge detection fails when PR has 0 commits"
arc report --feedback --message "arc status could show revision numbers"
```

**Inspect before submitting:**
```bash
arc report --bug --message "description" --dry-run
# Prints issue body, no submission
```

Issues are created on GitHub with environment context (arc version, Python version, OS). No PII is collected.

**Passive feedback:** Non-blocking hints are printed to stderr after errors and randomly (1-in-5) after successful commands. Disable in `~/.arc/config.toml`:
```toml
[feedback]
enabled = false
```

---

## Lifecycle hooks

Arc fires lifecycle hooks for 8 events: `pre-submit`, `post-submit`, `pre-land`, `post-land`, `pre-sync`, `post-sync`, `pre-push`, `post-push`.

### Hook file layout

Hooks are executable files placed at `.arc/hooks/<event>` (no extension). `arc init` scaffolds `.arc/hooks/` with a `README.md`, a `pre-submit.sample`, and a `post-land.sample`. `arc doctor` flags hook files that exist but are not executable.

### Gate vs. notify semantics

| Prefix | Behaviour on non-zero exit | Exit code |
|--------|---------------------------|-----------|
| `pre-*` | **Gate** — aborts the command immediately | 7 |
| `post-*` | **Notify** — exit code is ignored; a dim warning + the hook's stderr is shown | — |

A `pre-*` hook that cannot execute (bad shebang, permission error) is treated as a gate failure; arc always exits with code 7. The value 126 appears only inside the error message text (e.g. "pre-submit hook failed (exit 126)") when the hook binary itself could not be executed by the OS.

### JSON error shape (gate failure with `--json`)

When a `pre-*` hook fails and `--json` is active, arc emits on stdout:

```json
{
  "ok": false,
  "error": "<event> hook failed (exit N)",
  "exit_code": 7,
  "hint": "fix the hook or re-run with --skip-hooks"
}
```

### Hook context

**Environment variables** set for every hook invocation:

| Variable | Value |
|----------|-------|
| `ARC_EVENT` | Event name (e.g. `pre-submit`) |
| `ARC_BRANCH` | Current branch name |
| `ARC_BASE` | Stack base branch (e.g. `main`) |
| `ARC_ROOT` | Repo root absolute path |
| `ARC_VERSION` | arc version string |
| `ARC_PR_NUMBER` | PR number (integer string) — set on pre-submit (only when updating an existing PR), post-submit, pre-land, post-land |
| `ARC_PR_URL` | PR URL string — set on post-submit only |
| `ARC_DRAFT` | `"true"` or `"false"` — set on pre-submit only |

Booleans are lowercase strings (`"true"` / `"false"`). Variables whose value is `None` are omitted entirely.

**stdin** receives a JSON object:

```json
{
  "event": "pre-submit",
  "branch": "feat/api",
  "base": "main",
  "version": "0.5.0",
  "extra": {"pr_number": null, "draft": true},
  "stack": [
    {"name": "feat/auth", "pr_number": 42, "revision": 3},
    {"name": "feat/api", "pr_number": null, "revision": 0},
    {"name": "feat/ui", "pr_number": null, "revision": 0}
  ]
}
```

### Per-command hook firing

- **submit** — `pre-submit` / `post-submit` fire **per branch** in the stack (once per branch being created or updated).
- **sync**, **push**, **land** — `pre-<cmd>` / `post-<cmd>` fire **once per command invocation** (not per branch).

### Skipping hooks

Pass `--skip-hooks` to `arc submit`, `arc land`, `arc sync`, or `arc push` to skip all hooks for that run. Dry-run (`-n` / `--dry-run`) never fires hooks.

### Legacy config hooks

`hooks.pre-submit` (list of shell commands) in `.arc/config.json` is still supported and runs on `arc submit`, unchanged, with the same exit-7 semantics. This is separate from the file-based hook system above.

### Agent rules for hooks

- Always pass `--skip-hooks` in automation unless the hooks are known to be agent-safe.
- Check `arc doctor` output if a hook gate fails unexpectedly — it will flag non-executable files.
- Gate failures (exit 7) are retryable by fixing the root cause; `--skip-hooks` is the escape hatch.
