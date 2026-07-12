# Editing

Amend a branch's commit and cascade the change up through the stack.

---

## Edit a lower branch

When a reviewer asks for changes on `feat/auth` (not the branch you're currently on):

```bash
arc checkout feat/auth     # or: arc checkout 1
# make the change
git add src/auth.py
arc edit
```

`arc edit` amends the current branch's HEAD commit, then runs a cascade rebase through all branches above it — with the same pause-and-resume conflict safety as `arc sync`.

When done, push and update PRs:

```bash
arc push && arc submit
```

### Specify a branch

You can edit a branch other than the current one:

```bash
arc edit feat/auth     # no need to check it out first
```

### What arc edit does

1. Stages any changes in the index (you still need to `git add` first)
2. Runs `git commit --amend --no-edit` on the target branch
3. Cascade-rebases every branch above the target
4. Reports the result

It does **not** force-push. Run `arc push` after to update remote.

---

## Amend the commit message

```bash
arc amend
```

Appends the PR link and stack position to the HEAD commit message. Useful after `arc submit` creates a PR — `git log` on the landed commits will then trace back to the PR.

```
Add auth middleware

PR: https://github.com/owner/repo/pull/42 (stack position 1)
```

This is optional and informational only. Run `arc push` after to update the remote branch.

---

## Quick navigation for editing

When you're deep in a stack and need to find the right branch to edit:

```bash
arc status              # see all branches and their PR numbers
arc checkout 2          # jump to branch 2 by index
arc up / arc down       # step through the stack one branch at a time
arc bottom              # go to the bottommost branch
```
