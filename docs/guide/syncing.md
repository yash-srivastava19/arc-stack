# Syncing

Keep the stack current when `main` moves or when you change a lower branch.

---

## Fetch and rebase

```bash
arc sync
```

Fetches from remote, then runs a cascade rebase bottom-up through the stack:

1. Rebase `feat/auth` onto the new tip of `main`
2. Rebase `feat/api` onto `feat/auth`
3. Rebase `feat/ui` onto `feat/api`

If everything rebases cleanly, arc exits `0` and you're done.

---

## Conflict recovery

When a conflict occurs, arc pauses and tells you what to fix:

```
✗ Conflict in feat/api
  Conflicting files:
    src/api.py

Resolve the conflict, then run:
  arc rebase --continue

To undo and return to the pre-sync state:
  arc rebase --abort
```

Arc exits with code `3`. The branches above the conflict are untouched; the branches below are already rebased.

**To continue:**

1. Open the conflicting file and fix the conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
2. Stage the resolution: `git add src/api.py`
3. Run `arc rebase --continue`

Arc finishes the rebase of `feat/api`, then cascades to `feat/ui` and any branches above. If another conflict appears, arc pauses again.

**To abort:**

```bash
arc rebase --abort
```

Rolls back every branch to exactly where it was before `arc sync` started — including branches that had already rebased cleanly during this run.

---

## Fine-grained rebase

Rebase only part of the stack without syncing from remote:

```bash
arc rebase                  # cascade the entire stack (no fetch)
arc rebase --upstack        # current branch and everything above it
arc rebase --downstack      # current branch and everything below it
```

These are useful when you've amended a commit locally and want to restack without running a full sync.

---

## Restack a single branch

```bash
arc restack feat/api
```

Rebases `feat/api` onto its parent branch in the stack without touching the branches above it. Faster than a full rebase when only one branch needs updating.

---

## Conflict prediction

Before syncing, preview what would happen:

```bash
arc sync -n
```

The dry-run output shows the rebase plan and warns if adjacent branches touch the same files — a hint that a conflict is likely, not a guarantee.

---

## Repeated conflicts and rerere

`arc setup` enables `git rerere`, which records how you resolved a conflict and replays the resolution automatically if the same conflict appears again. This means an `arc rebase --abort` followed by a retry, or a second sync after fixing the same upstream change, rarely needs you to resolve the same conflict twice.

If rerere was not set up automatically:

```bash
git config --global rerere.enabled true
```
