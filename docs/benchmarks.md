---
sidebar_label: Benchmarks
---

# Benchmarks: arc vs. git

This page compares arc with plain git on 16 everyday stacked-branch tasks, run as 18 scenarios. For each task it measures whether the result is correct, how many commands you type, how long the commands take, and how many git processes run underneath. Everything on this page comes from the harness in [`bench/`](https://github.com/yash-srivastava19/arc-stack/tree/main/bench), and you can rerun it.

With arc 0.8.4, at 5 branches:

- **Correct.** arc gets the right result in all 17 scenarios it has commands for. The expert git sequence gets all 18. arc has no command to insert a branch mid-stack (S16).
- **Commands.** arc needs fewer commands than expert git in 11 scenarios, the same number in 2, and more in 4. The gap is largest when work lands on origin: a teammate's push takes 2 arc commands against 6 git commands, and a merged branch takes 2 against 4.
- **Time.** arc is 5 to 14 times slower: 146–577 ms against 21–48 ms. Each arc command spends about 62 ms starting Python before it does any work, and arc runs 2 to 7 times as many git processes.
- **Stack size.** arc's git processes grow with the number of branches, from 43 at 2 branches to 279 at 20 when trunk moves (S3). The expert git sequence stays between 15 and 17.

---

## What the benchmark measures

| Measure | How it is counted |
|---|---|
| **Correct** | A checker reads the repository after the commands finish and compares it with the expected end state. It reads git state only, plus `.arc/state.json` for arc. Exit codes don't count. |
| **Commands** | Lines that start with `git`, `arc`, or `gh`. File edits such as `printf ... > file` are the same for both and aren't counted. |
| **Time** | Wall time of the whole command sequence, in milliseconds. The page shows the median and the range over all timed runs. |
| **git processes** | Every git process the sequence starts, including the ones arc starts for you, counted with `GIT_TRACE2_EVENT`. |

### The correctness checks

A run passes only if every check passes.

| Check | What it verifies |
|---|---|
| `O0_trunk` | `main` on origin has the expected files. |
| `O1_trees` | Each branch has exactly the expected files and contents. |
| `O2_chain` | Each branch sits directly on the branch below it, and the bottom branch sits on `main` from origin. |
| `O3_commits` | Each branch has the expected number of commits, and its diff from the branch below matches. This catches lost, duplicated, and replayed commits. |
| `O4_pushed` | Each branch on origin points at the same commit as the local branch. |
| `O5_clean` | No rebase or merge is in progress, HEAD is on a branch, and the working tree has no changes other than the ones the task says to keep. |
| `O6_gone` | Branches the task removes are gone, both locally and on origin. |
| `O8_rollback` | For the abort task, every branch is back at its starting commit, locally and on origin. |
| `O9_wip_kept` | Uncommitted changes the task says to keep are still there, unchanged. |
| `O10_arc_state` | For arc, the branch list in `.arc/state.json` matches the real stack, in order. |

Before any run, a self-test (`bench/oracle_selftest.py`) runs the checker against the git sequence's end state for all 18 scenarios, which must pass, and against 11 deliberately broken end states, which must fail. The broken states are: a lost commit, an extra commit, a stale parent, an unpushed branch, a rebase left in progress, a wrong conflict resolution, a partial rollback, a deleted branch left on origin, a teammate's commit overwritten, lost uncommitted work, and a stale branch left in `.arc/state.json`.

---

## How it runs

- **Fresh repositories.** Every run builds a new repository and a bare `origin.git` next to it in a temporary directory. A second clone of origin plays the teammate who pushes to `main`, merges PRs, or pushes to your branch.
- **Isolation.** All `GIT_*` variables are removed, git uses a dedicated config file (`bench/gitconfig`) with hooks off, and system config is ignored.
- **Deterministic commits.** Author, committer, and dates are fixed, so the same steps produce the same commit IDs every time.
- **No GitHub.** origin is a local bare repository. A stub `gh` reports that you're logged in and rejects everything else, so no scenario depends on GitHub.
- **Timing.** Each scenario runs the arc sequence and the git sequence alternately, 15 times each, on a fresh repository every time. Building the repository isn't timed.
- **The arc under test.** arc is installed from source into `bench/.venv` with precompiled bytecode, so `uv run` startup isn't counted.

---

## Assumptions

- **The git side is an expert.** Its sequences use git 2.38+ features such as `rebase --update-refs`, `--onto`, `--autostash`, and `--force-with-lease`. A less experienced developer types more commands than shown here.
- **The arc side follows arc's documentation.** Where arc prints a hint, such as stashing uncommitted changes, the sequence follows the hint.
- **Small, clean stacks.** Stacks have 5 branches with one commit each. S11 repeats three tasks with 3 commits per branch. Real stacks have larger diffs and messier conflicts.
- **Local only.** Opening PRs, retargeting them, and landing them through GitHub aren't measured. Because `gh` is a stub, arc can't ask GitHub whether a PR merged, so it detects merged branches from git history alone. With a real `gh`, arc also checks PR state.
- **No network in the timings.** arc skips its once-a-day PyPI version check when its output isn't a terminal, so no timed run makes a network call.
- **One machine.** All times come from one laptop. See [Results](#results) for its state during the run. Compare arc with git within a run, not absolute times across machines.

---

## Scenarios

Each scenario starts from a pushed stack `b1 -> b2 -> b3 -> b4 -> b5` on `main`, with HEAD on `b5`, unless it says otherwise. The commands below are the exact sequences the benchmark runs.

### S1: Build a stack and push it

main is up to date. Build a stack of 5 branches named b1, b2, b3, b4, b5, each built on the previous one (b1 on main), each with exactly one commit: b1 adds file f1.txt containing exactly the line 'b1 v1'; b2 adds file f2.txt containing exactly the line 'b2 v1'; b3 adds file f3.txt containing exactly the line 'b3 v1'; b4 adds file f4.txt containing exactly the line 'b4 v1'; b5 adds file f5.txt containing exactly the line 'b5 v1'. Push every branch to origin.

**arc**

```bash
arc init --base main -q
arc new b1 -q
printf 'b1 v1\n' > f1.txt
git add f1.txt
git commit -q -m 'feat: b1'
arc new b2 -q
printf 'b2 v1\n' > f2.txt
git add f2.txt
git commit -q -m 'feat: b2'
arc new b3 -q
printf 'b3 v1\n' > f3.txt
git add f3.txt
git commit -q -m 'feat: b3'
arc new b4 -q
printf 'b4 v1\n' > f4.txt
git add f4.txt
git commit -q -m 'feat: b4'
arc new b5 -q
printf 'b5 v1\n' > f5.txt
git add f5.txt
git commit -q -m 'feat: b5'
arc push -q
```

**git**

```bash
git checkout -q -b b1
printf 'b1 v1\n' > f1.txt
git add f1.txt
git commit -q -m 'feat: b1'
git checkout -q -b b2
printf 'b2 v1\n' > f2.txt
git add f2.txt
git commit -q -m 'feat: b2'
git checkout -q -b b3
printf 'b3 v1\n' > f3.txt
git add f3.txt
git commit -q -m 'feat: b3'
git checkout -q -b b4
printf 'b4 v1\n' > f4.txt
git add f4.txt
git commit -q -m 'feat: b4'
git checkout -q -b b5
printf 'b5 v1\n' > f5.txt
git add f5.txt
git commit -q -m 'feat: b5'
git push -q origin b1 b2 b3 b4 b5
```

### S2: Amend a mid-stack branch

A reviewer asked for a change on b2: f2.txt must contain exactly the line 'b2 v2'. Fold the fix into b2's existing commit (b2 must stay a single commit), make sure every branch above b2 includes the change, and update origin.

**arc**

```bash
git checkout -q b2
printf 'b2 v2\n' > f2.txt
git add f2.txt
arc edit -q
```

**git**

```bash
printf 'b2 v2\n' > f2.txt
git add f2.txt
git commit -q --fixup=b2
GIT_SEQUENCE_EDITOR=: git rebase -q -i --autosquash --update-refs main
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S3: Trunk moved: sync

Someone merged new work into main on origin. Bring the whole stack up to date with origin's main (b1 directly on top of it) and update origin.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q
git rebase -q --update-refs origin/main
git push -q --force-with-lease origin b1 b2 b3 b4 b5
```

### S4: Sync with a conflict: resolve

Someone merged a change into main on origin. Bring the whole stack up to date with origin's main (b1 directly on top of it) and update origin. If conf.txt conflicts, resolve it so the file contains exactly two lines: 'from-b3' then 'from-main'.

**arc**

```bash
arc sync -q || true
printf 'from-b3\nfrom-main\n' > conf.txt
git add conf.txt
arc rebase --continue -q
arc push -q
```

**git**

```bash
git fetch -q
git rebase -q --update-refs origin/main || true
printf 'from-b3\nfrom-main\n' > conf.txt
git add conf.txt
git rebase --continue
git push -q --force-with-lease origin b1 b2 b3 b4 b5
```

### S5: Sync with a conflict: abort

Try to bring the stack up to date with origin's main. If that hits any conflict, do NOT resolve it: back out completely so every local branch and everything on origin is exactly as it was before you started, with a clean working tree and nothing in progress.

**arc**

```bash
arc sync -q || true
arc rebase --abort -q
```

**git**

```bash
git fetch -q
git rebase -q --update-refs origin/main || true
git rebase --abort
```

### S6: Bottom branch squash-merged

b1's pull request was just squash-merged into main on origin (the merge also deleted b1 on origin). Remove b1 locally, put the rest of the stack (b2 and up) directly on top of origin's new main without re-applying b1's change, and update origin.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q --prune
git rebase -q --update-refs --onto origin/main b1 b5
git branch -q -D b1
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S7: Drop a middle branch

The idea in b3 was abandoned. Remove b3 from the stack entirely (its change must not appear in any branch), so b4 sits directly on b2. Delete b3 locally and on origin, and update origin.

**arc**

```bash
arc drop b3 --force -q
arc push -q
git branch -q -D b3
git push -q origin --delete b3
```

**git**

```bash
git rebase -q --update-refs --onto b2 b3 b5
git branch -q -D b3
git push -q --force-with-lease origin b4 b5 :b3
```

### S8: Amend two non-adjacent branches

Review asked for two fixes: f2.txt must contain exactly the line 'b2 v2', and f4.txt exactly 'b4 v2'. Fold each fix into its branch's existing commit (every branch stays a single commit), make sure branches above include the fixes, and update origin.

**arc**

```bash
git checkout -q b2
printf 'b2 v2\n' > f2.txt
git add f2.txt
arc edit -q
git checkout -q b4
printf 'b4 v2\n' > f4.txt
git add f4.txt
arc edit -q
```

**git**

```bash
printf 'b2 v2\n' > f2.txt
git add f2.txt
git commit -q --fixup=b2
printf 'b4 v2\n' > f4.txt
git add f4.txt
git commit -q --fixup=b4
GIT_SEQUENCE_EDITOR=: git rebase -q -i --autosquash --update-refs main
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S9: Review fix as a new commit

A reviewer asked for a change on b2. Add a new commit on b2 that creates f2_fix.txt containing exactly the line 'review fix' (b2 then has two commits). Make sure every branch above b2 includes it, and update origin.

**arc**

```bash
git checkout -q b2
printf 'review fix\n' > f2_fix.txt
git add f2_fix.txt
git commit -q -m 'fix: review'
arc rebase --upstack -q
arc push -q
```

**git**

```bash
git checkout -q b2
printf 'review fix\n' > f2_fix.txt
git add f2_fix.txt
git commit -q -m 'fix: review'
git rebase -q --update-refs b2 b5
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S10: Sync with uncommitted changes

You have uncommitted edits in f5.txt on b5 that are not ready to commit. Someone merged new work into main on origin. Bring the whole stack up to date with origin's main (b1 directly on top of it) and update origin. Keep your edits to f5.txt exactly as they are, uncommitted.

**arc**

```bash
git stash -q
arc sync -q
arc push -q
git stash pop -q
```

**git**

```bash
git fetch -q
git rebase -q --autostash --update-refs origin/main
git push -q --force-with-lease origin b1 b2 b3 b4 b5
```

### S11a: Trunk moved, 3 commits per branch

Someone merged new work into main on origin. Bring the whole stack up to date with origin's main (b1 directly on top of it) and update origin.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q
git rebase -q --update-refs origin/main
git push -q --force-with-lease origin b1 b2 b3 b4 b5
```

### S11b: Squash-merged bottom, 3 commits per branch

b1's pull request was just squash-merged into main on origin (the merge also deleted b1 on origin). Remove b1 locally, put the rest of the stack (b2 and up) directly on top of origin's new main without re-applying b1's change, and update origin.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q --prune
git rebase -q --update-refs --onto origin/main b1 b5
git branch -q -D b1
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S11c: Drop a middle branch, 3 commits per branch

The idea in b3 was abandoned. Remove b3 from the stack entirely (its change must not appear in any branch), so b4 sits directly on b2. Delete b3 locally and on origin, and update origin.

**arc**

```bash
arc drop b3 --force -q
arc push -q
git branch -q -D b3
git push -q origin --delete b3
```

**git**

```bash
git rebase -q --update-refs --onto b2 b3 b5
git branch -q -D b3
git push -q --force-with-lease origin b4 b5 :b3
```

### S12: Two bottom branches squash-merged

While you were away, b1's and then b2's pull requests were both squash-merged into main on origin, and both branches were deleted on origin. Remove b1 and b2 locally, put b3 and up directly on top of origin's main without re-applying their changes, and update origin.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q --prune
git rebase -q --update-refs --onto origin/main b2 b5
git branch -q -D b1 b2
git push -q --force-with-lease origin b3 b4 b5
```

### S13: Bottom branch merged with a merge commit

b1's pull request was just merged into main on origin with a merge commit (the merge also deleted b1 on origin). Remove b1 locally, put the rest of the stack (b2 and up) directly on top of origin's new main, and update origin.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q --prune
git rebase -q --update-refs origin/main
git branch -q -D b1
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S14: Teammate pushed to a stack branch

A teammate pushed an extra commit to b2 on origin (it adds t2.txt). Separately, someone merged new work into main on origin. Bring the stack up to date so that b2 includes your teammate's commit and b1 sits directly on origin's main, then update origin without losing your teammate's work.

**arc**

```bash
arc sync -q
arc push -q
```

**git**

```bash
git fetch -q
git checkout -q b2
git merge -q --ff-only origin/b2
git rebase -q --update-refs b2 b5
git rebase -q --update-refs origin/main b5
git push -q --force-with-lease origin b1 b2 b3 b4 b5
```

### S15: Conflict during a mid-stack amend

b3's commit changes conf.txt. A reviewer asked that b2's commit also set conf.txt to exactly the line 'from-b2'. Fold this into b2's existing commit (b2 stays one commit), carry the change up the stack, and update origin. When b3 conflicts on conf.txt, resolve it so conf.txt contains exactly two lines: 'from-b2' then 'from-b3'.

**arc**

```bash
git checkout -q b2
printf 'from-b2\n' > conf.txt
git add conf.txt
arc edit -q || true
printf 'from-b2\nfrom-b3\n' > conf.txt
git add conf.txt
arc edit --continue -q
```

**git**

```bash
git checkout -q b2
printf 'from-b2\n' > conf.txt
git add conf.txt
git commit -q --amend --no-edit
git rebase -q --update-refs --onto b2 b2@{1} b5 || true
printf 'from-b2\nfrom-b3\n' > conf.txt
git add conf.txt
git rebase --continue
git push -q --force-with-lease origin b2 b3 b4 b5
```

### S16: Insert a branch mid-stack

A reviewer asked you to split out a preparatory change. Create a new branch bX between b2 and b3, with one commit that adds fx.txt containing exactly the line 'bx v1'. b3 must then sit directly on bX. Push bX and update origin.

**arc**

arc has no command for this. Use the git sequence.

**git**

```bash
git checkout -q -b bX b2
printf 'bx v1\n' > fx.txt
git add fx.txt
git commit -q -m 'feat: bX'
git rebase -q --update-refs --onto bX b2 b5
git push -q --force-with-lease origin bX b3 b4 b5
```

---

## Results

All numbers come from one run of arc 0.8.4 and git 2.55.0, with arc on Python 3.13.9. The machine was a 12-core x86_64 laptop running Linux 7.1, on AC power with the `performance` power profile. Each side ran 15 times per scenario, alternating with the other side. Times are the median, with the fastest and slowest run in parentheses. Every timed run passed the checker.

The raw results are in `bench/results/scripted-0.8.4.jsonl`.

### At 5 branches

| Scenario | Correct: arc | Correct: git | Commands: arc | Commands: git | Time ms: arc | Time ms: git | git processes: arc | git processes: git |
|---|---|---|---|---|---|---|---|---|
| S1 Build a stack and push it | pass | pass | 17 | 16 | 577 (550–774) | 48 (47–52) | 51 | 27 |
| S2 Amend a mid-stack branch | pass | pass | 3 | 4 | 146 (120–174) | 28 (21–30) | 44 | 12 |
| S3 Trunk moved: sync | pass | pass | 2 | 3 | 296 (273–514) | 37 (23–66) | 82 | 15 |
| S4 Sync with a conflict: resolve | pass | pass | 4 | 5 | 415 (363–557) | 42 (33–106) | 87 | 19 |
| S5 Sync with a conflict: abort | pass | pass | 2 | 3 | 317 (264–491) | 22 (15–32) | 65 | 9 |
| S6 Bottom branch squash-merged | pass | pass | 2 | 4 | 381 (255–453) | 38 (30–51) | 75 | 16 |
| S7 Drop a middle branch | pass | pass | 4 | 3 | 225 (194–332) | 21 (19–29) | 32 | 10 |
| S8 Amend two non-adjacent branches | pass | pass | 6 | 6 | 385 (261–461) | 41 (32–52) | 74 | 15 |
| S9 Review fix as a new commit | pass | pass | 5 | 5 | 210 (207–256) | 27 (26–28) | 44 | 13 |
| S10 Sync with uncommitted changes | pass | pass | 4 | 3 | 280 (272–302) | 41 (40–45) | 86 | 19 |
| S11a Trunk moved, 3 commits per branch | pass | pass | 2 | 3 | 290 (285–303) | 41 (38–48) | 88 | 15 |
| S11b Squash-merged bottom, 3 commits per branch | pass | pass | 2 | 4 | 279 (269–307) | 38 (37–42) | 81 | 16 |
| S11c Drop a middle branch, 3 commits per branch | pass | pass | 4 | 3 | 200 (193–224) | 24 (22–28) | 35 | 10 |
| S12 Two bottom branches squash-merged | pass | pass | 2 | 4 | 242 (236–274) | 33 (32–36) | 66 | 16 |
| S13 Bottom branch merged with a merge commit | pass | pass | 2 | 4 | 252 (244–295) | 33 (32–36) | 73 | 16 |
| S14 Teammate pushed to a stack branch | pass | pass | 2 | 6 | 278 (274–315) | 46 (42–48) | 85 | 20 |
| S15 Conflict during a mid-stack amend | pass | pass | 5 | 7 | 221 (218–254) | 36 (34–39) | 51 | 17 |
| S16 Insert a branch mid-stack | no command | pass | – | 5 | – | 27 (25–29) | – | 13 |

### As the stack grows

| Scenario | Branches | Time ms: arc | Time ms: git | git processes: arc | git processes: git |
|---|---|---|---|---|---|
| S14 | 2 | 209 (204–273) | 40 (38–40) | 47 | 20 |
| S14 | 10 | 399 (388–437) | 57 (54–61) | 151 | 21 |
| S14 | 20 | 655 (630–750) | 80 (72–86) | 282 | 22 |
| S3 | 2 | 202 (199–256) | 30 (29–31) | 43 | 15 |
| S3 | 10 | 386 (374–416) | 42 (40–47) | 148 | 16 |
| S3 | 20 | 631 (624–660) | 54 (52–64) | 279 | 17 |
| S6 | 2 | 191 (188–211) | 29 (28–30) | 36 | 16 |
| S6 | 10 | 368 (360–398) | 40 (39–43) | 141 | 17 |
| S6 | 20 | 618 (606–644) | 54 (52–62) | 272 | 18 |
| S9 | 2 | 171 (166–194) | 23 (22–23) | 23 | 13 |
| S9 | 10 | 277 (272–287) | 35 (33–40) | 80 | 14 |
| S9 | 20 | 453 (414–488) | 49 (44–56) | 151 | 15 |

### Why arc is slower

Two costs explain the gap, and both show up in every arc command:

- **Startup.** `arc --version` takes 62 ms, and `git --version` takes 1 ms. Most of arc's time goes to importing its modules, led by `importlib.metadata` and Rich. A scenario with 7 arc commands, such as S1, spends about 430 ms on startup alone.
- **git processes.** arc checks state that the expert git sequence never looks at: whether each branch is merged, whether origin moved, and whether the tree is clean. In S3 that is 82 git processes against 15, at about 2 ms each.

For a person typing commands, the difference between 0.3 s and 0.04 s rarely matters. For scripts that run arc in a loop, it adds up.

---

## What the benchmark found in arc

The first runs of this benchmark found cases where the documented arc flow gave a wrong result, usually while exiting `0`. Each was fixed with a test that reproduces it.

| Scenario | arc 0.8.2 | arc 0.8.3 | arc 0.8.4 |
|---|---|---|---|
| S1 Build a stack and push it | pass | pass | pass |
| S2 Amend a mid-stack branch | pass | pass | pass |
| S3 Trunk moved: sync | **fail** | pass | pass |
| S4 Sync with a conflict: resolve | **fail** | pass | pass |
| S5 Sync with a conflict: abort | pass | pass | pass |
| S6 Bottom branch squash-merged | **fail** | pass | pass |
| S7 Drop a middle branch | **fail** | pass | pass |
| S8 Amend two non-adjacent branches | pass | pass | pass |
| S9 Review fix as a new commit | pass | pass | pass |
| S10 Sync with uncommitted changes | **fail** | pass | pass |
| S11a Trunk moved, 3 commits per branch | **fail** | pass | pass |
| S11b Squash-merged bottom, 3 commits per branch | **fail** | **fail** | pass |
| S11c Drop a middle branch, 3 commits per branch | **fail** | pass | pass |
| S12 Two bottom branches squash-merged | **fail** | pass | pass |
| S13 Bottom branch merged with a merge commit | **fail** | pass | pass |
| S14 Teammate pushed to a stack branch | **fail** | **fail** | pass |
| S15 Conflict during a mid-stack amend | pass | pass | pass |
| S16 Insert a branch mid-stack | no command | no command | no command |

S10's arc sequence stashes the uncommitted changes first, following the hint that arc 0.8.4 prints. On 0.8.3 the same sequence passes, but arc printed git's raw error instead of the hint.

| Problem | Fixed in |
|---|---|
| `arc sync` rebased onto a stale local `main`, so nothing moved when `main` changed on origin. | 0.8.3 |
| `arc drop` of a middle branch left the dropped branch's commits in every branch above it. | 0.8.3 |
| A merged bottom branch stayed in the stack, and the next `arc push` failed on its deleted remote branch. | 0.8.3 |
| A failed PyPI version check was retried on every command. | 0.8.3 |
| `arc new` on a merged branch stacked the new branch on top of the merged one. | 0.8.3 |
| `arc sync` and `arc push` overwrote a commit a teammate pushed to a stack branch. | 0.8.4 |
| A squash-merged branch with more than one commit stayed in the stack. | 0.8.4 |
| Restacking with uncommitted changes failed partway with git's raw error. | 0.8.4 |

Still open:

- arc has no command to insert a branch in the middle of a stack (S16).
- arc starts more git processes than an expert git sequence, and each arc command pays Python's startup time.

---

## Run it yourself

You need git 2.30 or later, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/).

```bash
uv venv bench/.venv
VIRTUAL_ENV=$PWD/bench/.venv uv pip install --compile-bytecode .
cd bench
python3 oracle_selftest.py                      # the checker must pass this first
python3 run_scripted.py --out results/mine.jsonl
```

To benchmark a released arc instead of your checkout, install it into another venv and point `BENCH_VENV` at that venv. `report.py` prints the tables on this page from the files in `bench/results/`.
