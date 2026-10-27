---
sidebar_label: Benchmarks
---

# Why arc: stacked branches without the git gymnastics

Stacking is easy in git until something changes underneath you. `main` moves, a PR gets squash-merged, a teammate pushes a fix to your branch, a reviewer wants a change three branches down. Each of those has a correct git answer, but it's a different command every time, it needs flags most people look up, and getting it slightly wrong rewrites the wrong commits or overwrites someone's work.

arc turns those moments into the same few commands. We measured it: 16 everyday stacked-branch tasks, each done once with arc and once with the shortest correct sequence an experienced git user would type. Every result was checked against the exact repository state it should produce.

---

## The short version

- **The hard moments shrink to `arc sync` and `arc push`.** When `main` moves, a branch merges, or a teammate pushes, arc takes 2 commands where expert git takes 3 to 6. Those 2 commands stay the same however many branches you have.
- **arc gets them right.** arc produced the correct repository in every task it has a command for: 17 of 17 scenarios. That includes the ones where a small git mistake replays merged commits or overwrites a teammate's commit.
- **You don't need to know the flags.** The git versions rely on `rebase --update-refs`, `--onto`, `--force-with-lease`, and `--autostash`, plus listing every branch by name. With arc, you need `sync`, `push`, `edit`, and `drop`.
- **The cost is a fraction of a second.** arc runs in Python and checks more than a hand-typed sequence does. Each task takes arc 0.14 to 0.53 seconds, against 0.02 to 0.05 seconds for git.

---

## A week with a stack

Each example starts from a stack of five branches, `b1` to `b5`, already pushed. The git side is what an expert types. The arc side is what arc's documentation tells you to type.

### `main` moved overnight

Your stack needs to sit on the new `main`.

```bash title="git"
git fetch
git rebase --update-refs origin/main          # from the top branch; moves all five
git push --force-with-lease origin b1 b2 b3 b4 b5
```

```bash title="arc"
arc sync
arc push
```

Forget `--update-refs` and only the top branch moves. The other four stay behind, and their PRs go stale.

### Your bottom PR was squash-merged

GitHub collapsed `b1` into one new commit on `main`. Your other branches still contain `b1`'s original commits.

```bash title="git"
git fetch --prune
git rebase --update-refs --onto origin/main b1 b5
git branch -D b1
git push --force-with-lease origin b2 b3 b4 b5
```

```bash title="arc"
arc sync
arc push
```

A plain `git rebase origin/main` replays `b1`'s commits on top of their squashed copy, which conflicts or duplicates the change. arc sees that `b1` is already in `main`, drops it from the stack, and moves the rest. It works the same when two branches merged while you were away, and for merge commits instead of squashes.

### A teammate pushed a fix to your branch

Someone pushed a commit to `b2` while you were working. Meanwhile, `main` also moved.

```bash title="git"
git fetch
git checkout b2
git merge --ff-only origin/b2
git rebase --update-refs b2 b5
git rebase --update-refs origin/main b5
git push --force-with-lease origin b1 b2 b3 b4 b5
```

```bash title="arc"
arc sync
arc push
```

This one bites experienced developers. After `git fetch`, `--force-with-lease` no longer protects you: it compares against the commit you just fetched, so a rebase that never included your teammate's commit overwrites it. `arc sync` brings their commit into your stack first. If it can't, `arc push` refuses to overwrite a commit your branch never had.

### A reviewer wants a change three branches down

The fix belongs in `b2`, and `b3` to `b5` must carry it.

```bash title="git"
# edit the file
git add f2.txt
git commit --fixup=b2
GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash --update-refs main
git push --force-with-lease origin b2 b3 b4 b5
```

```bash title="arc"
git checkout b2
# edit the file
git add f2.txt
arc edit
```

`arc edit` amends `b2`, restacks everything above it, and pushes the branches it changed.

### A conflict halfway up the stack

`main` changed a line that `b3` also changes.

```bash title="git"
git fetch
git rebase --update-refs origin/main
# resolve, then
git add conf.txt
git rebase --continue
git push --force-with-lease origin b1 b2 b3 b4 b5
```

```bash title="arc"
arc sync
# resolve, then
git add conf.txt
arc rebase --continue
arc push
```

The counts are close here. The difference is what happens when you change your mind: `arc rebase --abort` puts every branch back exactly where it was before the sync, including the branches that had already moved.

### Where plain git is just as good

Not every task needs arc. For these, the expert git sequence is as short or shorter:

- **Building a new stack.** It's `arc new` instead of `git checkout -b`, one per branch. Same length.
- **Adding a review commit** (not an amend) to a lower branch: 5 commands each.
- **Dropping a branch.** `arc drop` restacks the branches above it, but you still delete the old branch yourself. One `git rebase --onto` does the same job.
- **Syncing with uncommitted changes.** arc asks you to stash first, while `git rebase --autostash` stashes for you.
- **Inserting a branch mid-stack.** arc has no command for this yet.

---

## The numbers

**Commands typed and correctness**, for every scenario at 5 branches. "Correct" means the repository ended up exactly as expected: the right files and commits on every branch, every branch on the one below it, origin up to date, and nothing half-finished.

| Task | arc commands | git commands | arc correct | git correct |
|---|---|---|---|---|
| Build a stack and push it | 17 | 16 | pass | pass |
| Amend a mid-stack branch | 3 | 4 | pass | pass |
| Trunk moved: sync | 2 | 3 | pass | pass |
| Sync with a conflict: resolve | 4 | 5 | pass | pass |
| Sync with a conflict: abort | 2 | 3 | pass | pass |
| Bottom branch squash-merged | 2 | 4 | pass | pass |
| Drop a middle branch | 4 | 3 | pass | pass |
| Amend two non-adjacent branches | 6 | 6 | pass | pass |
| Review fix as a new commit | 5 | 5 | pass | pass |
| Sync with uncommitted changes | 4 | 3 | pass | pass |
| Trunk moved, 3 commits per branch | 2 | 3 | pass | pass |
| Squash-merged bottom, 3 commits per branch | 2 | 4 | pass | pass |
| Drop a middle branch, 3 commits per branch | 4 | 3 | pass | pass |
| Two bottom branches squash-merged | 2 | 4 | pass | pass |
| Bottom branch merged with a merge commit | 2 | 4 | pass | pass |
| Teammate pushed to a stack branch | 2 | 6 | pass | pass |
| Conflict during a mid-stack amend | 5 | 7 | pass | pass |
| Insert a branch mid-stack | – | 5 | no command | pass |

**Time.** We ran every scenario 15 times with each tool, alternating between them, on an AWS `c7i.large` (2 vCPU Intel Xeon Platinum 8488C, Ubuntu 24.04, git 2.43) with arc 0.8.5 from PyPI on Python 3.13. These are the medians, in milliseconds, for the moments described above:

| Moment | arc | git |
|---|---|---|
| `main` moved overnight | 308 | 35 |
| Your bottom PR was squash-merged | 298 | 33 |
| A teammate pushed to your branch | 291 | 47 |
| A reviewer wants a change three branches down | 143 | 27 |
| A conflict halfway up the stack | 416 | 42 |
| Changing your mind after a conflict | 272 | 21 |

The time goes to two places. Every arc command starts Python, which takes about 60 ms before any work happens. And arc runs the checks a careful developer would run by hand: is this branch already merged, did origin move, did a teammate push, is the working tree clean. Syncing five branches starts 82 git processes, where the expert git sequence starts 15.

The cost grows with the stack: syncing 20 branches takes arc 0.6 seconds and git 0.07 seconds. For a person typing commands, that's still well under a second. If you script arc in a tight loop, it adds up.

---

## How we measured

Every scenario runs in a fresh repository with a local `origin`, built the same way each time. A second clone plays the teammate who pushes to `main`, merges PRs, or pushes to your branch. A checker then reads the repository and compares it with the expected end state. Exit codes don't count, so a command that reports success with a wrong result fails. Before any run, the checker proves itself against 11 deliberately broken repositories, such as a lost commit or a teammate's overwritten push, and must catch every one.

Assumptions:

- **The git side is an expert.** A less experienced developer types more commands, or different ones.
- **Stacks are small and clean.** Five branches with one commit each. Three tasks repeat with three commits per branch. Real stacks have bigger diffs and messier conflicts.
- **Local only.** Opening, retargeting, and landing PRs on GitHub isn't measured.

The harness, the full method, and the exact commands for all 18 scenarios are in [`bench/`](https://github.com/yash-srivastava19/arc-stack/tree/main/bench). Its README shows how to run it yourself.
