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
4. **Use `--json` for machine-readable output.** `status`, `sync`, `push`, `submit`, `land`, and `drop` all support `--json`.
5. **Use `--dry-run` before destructive operations.** Rebase, land, drop, sync, and push all support `-n`/`--dry-run`.
6. **Handle exit code 3 (conflict) explicitly.** After a conflict, resolve it with `arc rebase --continue` or abandon with `arc rebase --abort`.
7. **`arc submit` creates PRs as draft by default.** Pass `--open` to mark them ready for review.
8. **Branch order is the stack order.** Index 1 is the branch closest to trunk; the highest index is the tip.
9. **Run `arc doctor` to diagnose environment issues.** It checks git, gh, authentication, and stack validity in one command.

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
| 3 | Rebase conflict | Resolve conflicts, then `arc rebase --continue`; or `arc rebase --abort`. |
| 5 | Branch not in stack | Verify branch name with `arc status --plain`. |
| 6 | Environment not ready (git or gh missing / not authenticated) | Run `arc setup` and fix the reported issue. |
| 7 | Pre-submit hook failed | Fix the hook failure or pass `--skip-hooks` to bypass. |

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

### Land a merged PR

```bash
# Verify PR is merged first
arc status --json | python3 -c "import sys,json; s=json.load(sys.stdin); print(s['branches'][0]['is_merged'])"
arc land --force -q    # defaults to the bottommost branch
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
