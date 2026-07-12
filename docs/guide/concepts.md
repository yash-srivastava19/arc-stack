# Concepts

Terminology used throughout arc's documentation and commands.

---

## Stack

A **stack** is an ordered list of branches, each branching from the one below it, with the bottommost branch rooted on a **base** branch (typically `main`).

```
main
  └── feat/auth       ← bottommost
        └── feat/api
              └── feat/ui   ← topmost (stack top)
```

arc tracks the stack in `.arc/state.json`, a per-clone file that is git-ignored. The stack state is local — collaborators who clone the repo do not inherit your stack.

---

## Branch

Within a stack, **branch** means a stack branch — one of the ordered entries arc manages. Each branch corresponds to a git branch and optionally a pull request.

A branch in the stack is distinct from `main` or other branches arc doesn't manage.

---

## Base

The **base** is the git branch the bottommost stack branch is rooted on. Typically `main`. Set during `arc init --base <name>` and stored in state.

When `main` moves, the bottom of the stack needs to be rebased onto the new tip of `main`. `arc sync` does this automatically.

---

## Prefix

An optional **prefix** added to all branch names created by `arc new`. Set during `arc init --prefix <prefix>`.

With prefix `feat`, `arc new auth` creates `feat/auth`. Without a prefix, it creates `auth`.

---

## Cascade rebase

A **cascade rebase** rebases each branch in the stack onto the one below it, starting from the bottom:

1. Rebase `feat/auth` onto `main`
2. Rebase `feat/api` onto `feat/auth` (as it now is)
3. Rebase `feat/ui` onto `feat/api` (as it now is)

This is what `arc sync` runs. If a conflict occurs at step 2, arc pauses — the branches that already rebased stay in place, the conflicting branch is left mid-rebase. After you resolve and run `arc rebase --continue`, arc picks up at step 2 and continues through the rest.

---

## Stack map

The **stack map** is a footer arc injects into every PR description. It lists all branches in the stack with their PR numbers and highlights which PR is being viewed:

```
---
Stack (base: main):
  1. feat/auth - PR #42 [this PR]
  2. feat/api  - PR #43
  3. feat/ui   - no PR
```

Reviewers can navigate the whole stack from any PR without leaving GitHub.

---

## Revision

arc assigns each branch a **revision** counter, starting at `1` and incrementing every time `arc push` runs. The revision appears in `arc status` and is used by arc internals to detect whether a branch has been pushed since its last change.

---

## arc-tip

`arc-tip` is an optional local branch that always points at the topmost branch in the stack. Run `arc tip` to create or update it. Once it exists, arc keeps it current automatically whenever the stack changes shape (new branch, drop, sync).

Useful if you frequently jump to the top of the stack and want a stable shorthand: `git checkout arc-tip`.

---

## Hook

A **hook** is an executable file in `.arc/hooks/<event>`. arc fires hooks before and after major operations. `pre-*` hooks are gates: a non-zero exit aborts the command. `post-*` hooks are notifications: the exit code is ignored.

See [Hooks](hooks.md) for the full event table and environment variables.
