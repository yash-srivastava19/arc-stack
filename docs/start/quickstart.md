# Quickstart

Build your first stacked PR in five minutes.

!!! note "Before you begin"
    [Install](install.md) arc and run `arc setup` to verify your environment.

---

## 1. Initialize

Run once per repo (or per clone):

```bash
arc init --base main --prefix feat
```

`--base` is the branch your stack sits on top of. `--prefix` is optional — if set, `arc new auth` creates `feat/auth` instead of `auth`.

`arc init` creates `.arc/state.json` (automatically git-ignored).

---

## 2. Create branches

```bash
arc new auth
# write code
git add src/auth.py && git commit -m "Add auth middleware"

arc new api
# write code
git add src/api.py && git commit -m "Add API routes"

arc new ui
git add src/ui.py && git commit -m "Add frontend"
```

Each `arc new` creates a branch from your current HEAD and registers it in the stack. Run `arc status` to see the result:

```
Stack (base: main)
  1. feat/auth   ●  1 commit
  2. feat/api    ●  1 commit
▶ 3. feat/ui     ●  1 commit   (current)
```

---

## 3. Open PRs

```bash
arc push           # force-push all branches
arc submit --draft # open a draft PR for each branch
```

Each PR targets the branch below it. Each PR description gets a stack map:

```
---
Stack (base: main):
  1. feat/auth - PR #42 [this PR]
  2. feat/api  - PR #43
  3. feat/ui   - PR #44
```

When ready for review:

```bash
arc submit --open   # mark all drafts as ready
```

---

## 4. Keep current

When `main` moves or you amend a lower branch:

```bash
arc sync            # fetch + cascade rebase
arc push && arc submit
```

If a conflict appears, arc pauses and tells you which files to fix. See [Syncing](../guide/syncing.md) for the full conflict workflow.

---

## 5. Land a merged PR

Once `feat/auth` is approved and merged on GitHub:

```bash
arc land feat/auth
```

arc removes `feat/auth` from the stack and rebases `feat/api` and `feat/ui` onto `main`.

---

## Next steps

- [Concepts](../guide/concepts.md) — vocabulary and mental model
- [Syncing](../guide/syncing.md) — sync, rebase, and conflict recovery in depth
- [Editing](../guide/editing.md) — amend a lower branch and cascade the change
- [Command reference](../reference/commands.md) — every command and flag
