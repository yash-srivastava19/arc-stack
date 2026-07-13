# Claude Code guidelines for arc

## Hard rules

### No git worktrees
Never use git worktrees in this repo. They have caused irreversible damage:
- A worktree with a corrupt `init` commit (deleting 93 files) was used as a base, making a PR look like a mass codebase deletion.
- `GIT_DIR` set by git hooks leaked into test subprocesses, causing test fixtures to commit into the actual repo with the wrong author identity.

Do all work directly in the main checkout.

### Use arc for all branch and PR work
Every code change goes through a proper arc workflow — no raw `git checkout -b` + `gh pr create` chains:
```
arc new <branch>      # create branch
# make changes
arc push              # push
arc submit            # open PR
```

Keep PRs small and focused. One logical change per PR. If a task has multiple parts, stack them with arc rather than bundling into one large PR.

### Check the PR diff before opening
Before running `arc submit` or `gh pr create`, always run:
```
git diff origin/main...HEAD --stat
```
Verify: no unexpected file deletions, no unrelated files, diff size matches the change.

### Never push directly to main
The repo has branch protection. All changes go through PRs. Never use `git push origin main` or `git push --force` on main.

## Test fixtures and git hooks
The `git_repo` and `stacked_repo` fixtures in `tests/conftest.py` strip `GIT_*` environment variables from subprocess calls. This prevents pre-commit hook context from leaking into test git operations. Do not remove this.
