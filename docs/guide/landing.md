# Landing

Merge a PR and clean up the stack.

---

## Land a merged PR

Once a PR is merged on GitHub, remove it from the stack and restack the branches above it:

```bash
arc land feat/auth
```

arc:
1. Verifies the PR is merged on GitHub
2. Detects whether it was a squash-merge or regular merge
3. Rebases the branches above onto `main` (using `git rebase --onto` for squash-merges, which avoids duplicate commits)
4. Removes `feat/auth` from the stack
5. Deletes the local `feat/auth` branch

### Squash-merge vs regular merge

arc detects the merge strategy automatically. For squash-merges (where GitHub collapses all commits into one), `git rebase --onto` is required to avoid duplicate commits appearing on the branches above. arc handles this without any extra flags.

### Flags

| Flag | Effect |
|------|--------|
| `<branch>` | Branch to land (defaults to current branch) |
| `-f` | Skip confirmation prompt |
| `-n` | Dry run: show what would happen |

### Conflict during restacking

If rebasing the branches above `feat/auth` hits a conflict:

```bash
# arc pauses, same as arc sync
# Resolve the conflict, then:
arc rebase --continue

# Then re-run arc land to finish:
arc land feat/auth -f
```

---

## Drop a branch

Remove a branch from the stack without landing it (no GitHub interaction):

```bash
arc drop feat/api
arc drop feat/api -f    # skip confirmation
```

Rebases the branches above `feat/api` onto `feat/auth`. Use this when you want to remove a branch you're abandoning, not merging.

If the restack hits a conflict, resolve it and run `arc rebase --continue`. Then re-run `arc drop feat/api -f` to complete.

---

## Landing in order

You can land branches in order as they get approved. The rest of the stack stays coherent:

```bash
arc land feat/auth     # lands first, restacks feat/api and feat/ui
arc land feat/api      # lands second, restacks feat/ui
arc land feat/ui       # lands last
```

If a reviewer approves in a different order, land in the order GitHub approves — arc handles whatever order you choose.
