# Stacking

How to create, inspect, and navigate a stack of branches.

---

## Initialize

Run once per repo (or per clone):

```bash
arc init --base main
arc init --base main --prefix feat   # optional: prefix all branch names
```

`arc init`:

- Creates `.arc/state.json` (git-ignored)
- Adds `.arc/state.json` to `.gitignore` if not already there
- Scaffolds `.arc/hooks/` with sample hook files
- Enables `git rerere` (so conflict resolutions are remembered)

You can run `arc init` again to update the base or prefix.

---

## Create a branch

```bash
arc new auth
```

Creates a new git branch from the current HEAD and adds it to the top of the stack. If a prefix is set, `arc new auth` creates `feat/auth`.

---

## Adopt an existing branch

If a branch already exists locally:

```bash
arc add feat/auth
```

Adopts the branch into the stack at the current position (above the current branch, below the stack top). The branch must already exist in git; `arc add` does not create it.

---

## Inspect the stack

```bash
arc status
```

```
Stack (base: main)
  1. feat/auth   ●  2 commits   PR #42
▶ 2. feat/api    ●  1 commit    PR #43   (current)
  3. feat/ui     ○  0 commits   no PR
```

The `▶` marker shows the current branch. `●` means commits exist on the branch; `○` means the branch has no commits beyond its base.

```bash
arc status --json    # machine-readable
arc status --plain   # branch names only, one per line (good for scripts)
```

---

## Navigate

```bash
arc checkout feat/auth    # by name
arc checkout 1            # by position (1-based)

arc up                    # move one step toward the top
arc up 2                  # move two steps
arc down                  # move one step toward the base
arc top                   # jump to the topmost branch
arc bottom                # jump to the bottommost branch
```

`arc tip` creates (or updates) an `arc-tip` branch pointing at the topmost branch and checks it out. Useful as a persistent shortcut to the top.

---

## Remove a branch

```bash
arc drop feat/api
```

Removes `feat/api` from the stack, rebases `feat/ui` onto `feat/auth`, and deletes the local branch. Prompts for confirmation unless `-f` is passed.

```bash
arc drop feat/api -f       # skip confirmation
arc drop feat/api -n       # dry run: show what would happen
```

If the rebase hits a conflict, arc pauses. Resolve the conflict and run `arc rebase --continue`. See [Syncing](syncing.md) for the full conflict workflow.

---

## Check environment

```bash
arc doctor
```

Reports any issues with git, `gh`, auth, stack state, or paused rebases. Run this when something seems wrong before filing a bug report.
