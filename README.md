# arc

Your PR has 47 files changed. Nobody's going to review that.

Stacked PRs fix this — break a large change into a chain of small, focused diffs that reviewers can actually follow. The problem is that managing a stack by hand is painful. Every time `main` moves, you cascade rebases through four branches manually. Every merged PR means retargeting the one above it. So you skip the stacking and ship the monster PR anyway.

`arc` removes that friction.

```
$ arc status

main
└── feat/auth        PR #42  ✓  2 commits  (rev 3)
    └── feat/api     PR #43  ✗  3 commits  (rev 1)  ← needs rebase
        └── feat/ui  no PR   ✓  1 commit

→ Run 'arc sync' to rebase feat/api onto feat/auth.
```

One command keeps the whole stack current. Another opens all the PRs — with a stack map in each description so reviewers can navigate. When a PR merges, `arc land` rebases everything above it and removes it from the stack.

---

## Install

```bash
pipx install arc-prs
# or
uv tool install arc-prs
```

**Requires:** Python 3.11+, [git](https://git-scm.com), [gh CLI](https://cli.github.com) (authenticated via `gh auth login`)

First time on a new machine:

```bash
arc setup   # checks git, gh auth, and configures git rerere
```

---

## Building a stack

Initialize `arc` in your repo once:

```bash
arc init --base main --prefix feat
```

This creates `.arc/state.json` (git-ignored, per-clone) and adds it to `.gitignore`. The `--prefix` is optional — if set, `arc new auth` creates `feat/auth` instead of `auth`.

Then build your stack branch by branch as you work:

```bash
arc new auth
# write code, run tests
git add . && git commit -m "Add auth middleware"

arc new api
# write code
git add . && git commit -m "Add API routes"

arc new ui
git add . && git commit -m "Add frontend"
```

Each `arc new` creates a branch from your current HEAD and registers it in the stack. `arc status` shows you where you are at any point.

---

## The daily loop

When `main` moves or you amend a lower branch, run:

```bash
arc sync
```

This fetches the latest from remote and cascades a rebase bottom-up through the stack — `feat/auth` onto `main`, `feat/api` onto `feat/auth`, `feat/ui` onto `feat/api`. If there's a conflict, `arc` aborts the rebase, resets every branch to where it was before, and tells you exactly which files to fix:

```
Conflict in feat/api. Resolve: src/api.py
Then run 'arc rebase --continue' or 'arc rebase --abort'.
```

When the stack is clean, push everything and open PRs:

```bash
arc push                  # force-pushes all branches atomically
arc submit --draft        # creates or updates PRs for each branch
```

Each PR targets the branch below it, not `main` directly. Reviewers see only the diff for that layer. `arc submit` also injects a stack map into every PR description:

```
---
Stack (base: main):
  1. feat/auth - PR #42 [this PR]
  2. feat/api  - PR #43
  3. feat/ui   - no PR
```

Reviewers can navigate the whole stack from any PR without hunting for context.

When you're ready to open for review, `arc submit --open` marks all drafts as ready at once.

---

## When a PR merges

Once `feat/auth` is approved and merged on GitHub:

```bash
arc land feat/auth
```

`arc` verifies the PR is merged, detects whether it was a squash-merge or a regular merge, rebases `feat/api` and `feat/ui` onto `main` correctly (using `git rebase --onto` for squash-merges, which would otherwise leave duplicate commits), removes `feat/auth` from the stack, and deletes the local branch.

You can land branches in order as they get approved. The rest of the stack stays coherent throughout.

---

## Other useful things

**If a lower branch needs changes** after review feedback:

```bash
arc checkout feat/auth   # or: arc checkout 1
# fix the issue, amend your commit
arc sync                 # cascades the change up through api and ui
arc push && arc submit
```

`arc checkout 2` navigates to the second branch in the stack. `arc up` / `arc down` / `arc top` / `arc bottom` move you through the stack without remembering branch names.

**Remove a branch** from the stack without touching the others:

```bash
arc drop feat/api -f     # restacks feat/ui onto feat/auth
```

**Keep commit messages useful** after a PR is created:

```bash
arc amend   # appends the PR link and stack position to the HEAD commit message
```

This means `git log` on the landed commits still traces back to the PR.

**Gate submissions on local checks** — configure `.arc/config.json` (committed, shared with your team):

```json
{
  "hooks": {
    "pre-submit": ["npm run lint", "npm test"]
  }
}
```

`arc submit` runs these before touching GitHub. Any non-zero exit aborts. Pass `--skip-hooks` to bypass.

**Preview destructive operations** before running them:

```bash
arc sync -n    # shows the rebase plan without executing
arc push -n    # shows which branches would be pushed
arc land -n    # shows which branches would be restacked
```

---

## Scripting and agents

Every command is non-interactive by default. `--json` sends structured output to stdout; status messages go to stderr. Exit codes carry meaning.

```bash
# Find branches that need rebasing
arc status --json | jq '.branches[] | select(.needs_rebase) | .name'

# Get all branch names for a script
arc status --plain

# Full dry-run before committing
arc sync -n && arc push -n && arc submit -n
```

**`arc status --json` output:**

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

| Code | Meaning | What to do |
|------|---------|------------|
| 0 | Success | — |
| 1 | Error | Read stderr |
| 2 | Not in a stack | `arc init` |
| 3 | Rebase conflict | Resolve, then `arc rebase --continue` or `--abort` |
| 4 | GitHub API failure | `gh auth status`, retry |
| 5 | Invalid arguments | Read stderr |
| 6 | Setup check failed | `arc setup` |
| 7 | Pre-submit hook failed | Fix the check or `--skip-hooks` |

---

## Reference

All commands accept `-q` (`--quiet`) to suppress hints and `-n` (`--dry-run`) where the operation is destructive. `--json` is available on any command that produces data.

| Command | What it does |
|---------|-------------|
| `arc setup` | Verify environment, configure git |
| `arc init [--base B] [--prefix P]` | Initialize a stack |
| `arc new <branch>` | Create branch from HEAD, add to stack |
| `arc add <branch>` | Adopt an existing local branch |
| `arc status [--json\|--plain]` | Show the stack |
| `arc sync` | Fetch + cascade rebase |
| `arc push` | Force-push all branches, increment revision |
| `arc submit [--draft\|--open] [--skip-hooks]` | Create or update PRs |
| `arc land [<branch>] [-f]` | Land a merged PR, restack above |
| `arc amend` | Append PR link to commit message |
| `arc drop <branch> [-f]` | Remove branch, restack above |
| `arc rebase [--upstack\|--downstack\|--continue\|--abort]` | Fine-grained rebase |
| `arc checkout <name\|index>` | Switch to branch by name or position |
| `arc up [n]` / `arc down [n]` | Move through the stack |
| `arc top` / `arc bottom` | Jump to ends of the stack |

---

## License

MIT
