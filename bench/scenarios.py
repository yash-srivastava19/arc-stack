"""Scenarios: fixture setup, expected end state, scripted command sequences, agent prompt.

Every scripted sequence runs with `bash -e` in work/, with HEAD on the top branch.
The `arc` sequence follows arc's documentation. The `git` sequence is the shortest
correct sequence an expert would type with git 2.38+ (`rebase --update-refs`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lib import (
    Spec,
    arc_adopt,
    base_trunk,
    branch_commits,
    build_repo,
    merge_commit_on_origin,
    push_to_branch,
    snapshot_refs,
    squash_merge_on_origin,
    stack,
    upstream_commit,
)


@dataclass
class Scenario:
    id: str
    title: str
    setup: Callable  # (root, env, arm, n) -> pre_refs | None
    expected: Callable  # (n) -> Spec | None (None means "everything rolled back")
    arc: Callable | None  # (n) -> list[str]; None when arc has no command for it
    git: Callable
    prompt: Callable  # (n) -> str


def names(n, lo=1, skip=()):
    return " ".join(f"b{i}" for i in range(lo, n + 1) if i not in skip)


def push_all(n, lo=1, skip=()):
    return f"git push -q --force-with-lease origin {names(n, lo, skip)}"


def write(path, content):
    return f"printf '{content.replace(chr(10), chr(92) + 'n')}' > {path}"


def setup_stack(root: Path, env, arm, n, conflict_b=None, k=1):
    work = build_repo(root, Spec(base_trunk(), stack(n, conflict_b, k)), env)
    if arm == "arc":
        arc_adopt(work, env, [f"b{i}" for i in range(1, n + 1)])
    return work


def expect(n, k=1, conflict_b=None, trunk_extra=(), edits=None, drop=(), merged=(), wip=None):
    """The stack after a scenario. `edits` maps branch index to replacement commits."""
    br = []
    for name, commits in stack(n, conflict_b, k):
        i = int(name[1:])
        if i in drop or i in merged:
            continue
        br.append((name, (edits or {}).get(i, commits)))
    trunk = base_trunk() + list(trunk_extra) + [c for i in merged for c in branch_commits(i, k)]
    gone = [f"b{i}" for i in (*drop, *merged)]
    return Spec(trunk, br, gone, wip or {})


DONE = " When you are finished, reply with DONE and a one-line summary."


def ctx(n, k=1):
    each = "one commit" if k == 1 else f"{k} commits"
    return (
        "The repository is in ./work (current directory is its parent). Its remote 'origin' is the "
        "bare repo ./origin.git, which stands in for GitHub. The developer's stacked branches are "
        + " -> ".join(f"b{i}" for i in range(1, n + 1))
        + f", each with {each}, each built on the previous one; b1 is built on main. "
        "The stack has already been pushed to origin. Nothing on origin should be force-pushed "
        "except stack branches. "
    )


SYNC_ARC = lambda n: ["arc sync -q", "arc push -q"]  # noqa: E731
SYNC_GIT = lambda n: [  # noqa: E731
    "git fetch -q",
    "git rebase -q --update-refs origin/main",
    push_all(n),
]
TRUNK_MOVED = [{"main.txt": "m1\n"}]
RESOLVED = "from-b3\nfrom-main\n"


# ---------------------------------------------------------------- S1 build


def s1_setup(root, env, arm, n):
    build_repo(root, Spec(base_trunk(), []), env)


def s1_arc(n):
    out = ["arc init --base main -q", "seed-arc-cache"]
    for i in range(1, n + 1):
        out += [f"arc new b{i} -q", write(f"f{i}.txt", f"b{i} v1\n"), f"git add f{i}.txt"]
        out += [f"git commit -q -m 'feat: b{i}'"]
    return out + ["arc push -q"]


def s1_git(n):
    out = []
    for i in range(1, n + 1):
        out += [f"git checkout -q -b b{i}", write(f"f{i}.txt", f"b{i} v1\n"), f"git add f{i}.txt"]
        out += [f"git commit -q -m 'feat: b{i}'"]
    return out + [f"git push -q origin {names(n)}"]


def s1_prompt(n):
    files = "; ".join(
        f"b{i} adds file f{i}.txt containing exactly the line 'b{i} v1'" for i in range(1, n + 1)
    )
    return (
        "The repository is in ./work (current directory is its parent); its remote 'origin' is the bare "
        "repo ./origin.git, which stands in for GitHub. main is up to date. Build a stack of "
        f"{n} branches named "
        + ", ".join(f"b{i}" for i in range(1, n + 1))
        + ", each built on the "
        f"previous one (b1 on main), each with exactly one commit: {files}. Push every branch to origin."
        + DONE
    )


# ---------------------------------------------------------------- S2 / S8 amend mid-stack


def _plain(root, env, arm, n):
    setup_stack(root, env, arm, n)


def s2_arc(n):
    return ["git checkout -q b2", write("f2.txt", "b2 v2\n"), "git add f2.txt", "arc edit -q"]


def s2_git(n):
    return [
        write("f2.txt", "b2 v2\n"),
        "git add f2.txt",
        "git commit -q --fixup=b2",
        "GIT_SEQUENCE_EDITOR=: git rebase -q -i --autosquash --update-refs main",
        push_all(n, lo=2),
    ]


def s2_prompt(n):
    return ctx(n) + (
        "A reviewer asked for a change on b2: f2.txt must contain exactly the line 'b2 v2'. Fold the fix "
        "into b2's existing commit (b2 must stay a single commit), make sure every branch above b2 "
        "includes the change, and update origin." + DONE
    )


def s8_arc(n):
    return s2_arc(n) + [
        "git checkout -q b4",
        write("f4.txt", "b4 v2\n"),
        "git add f4.txt",
        "arc edit -q",
    ]


def s8_git(n):
    return [
        write("f2.txt", "b2 v2\n"),
        "git add f2.txt",
        "git commit -q --fixup=b2",
        write("f4.txt", "b4 v2\n"),
        "git add f4.txt",
        "git commit -q --fixup=b4",
        "GIT_SEQUENCE_EDITOR=: git rebase -q -i --autosquash --update-refs main",
        push_all(n, lo=2),
    ]


def s8_prompt(n):
    return ctx(n) + (
        "Review asked for two fixes: f2.txt must contain exactly the line 'b2 v2', and f4.txt exactly "
        "'b4 v2'. Fold each fix into its branch's existing commit (every branch stays a single commit), "
        "make sure branches above include the fixes, and update origin." + DONE
    )


# ---------------------------------------------------------------- S3 / S10 / S11 trunk moved


def s3_setup(root, env, arm, n, k=1):
    setup_stack(root, env, arm, n, k=k)
    upstream_commit(root, env, TRUNK_MOVED[0])


def s3_prompt(n, k=1):
    return ctx(n, k) + (
        "Someone merged new work into main on origin. Bring the whole stack up to date with origin's "
        "main (b1 directly on top of it) and update origin." + DONE
    )


def s10_setup(root, env, arm, n):
    s3_setup(root, env, arm, n)
    (root / "work" / "f5.txt").write_text("b5 wip\n")


def s10_git(n):
    return ["git fetch -q", "git rebase -q --autostash --update-refs origin/main", push_all(n)]


def s10_prompt(n):
    return ctx(n) + (
        "You have uncommitted edits in f5.txt on b5 that are not ready to commit. Someone merged new "
        "work into main on origin. Bring the whole stack up to date with origin's main (b1 directly on "
        "top of it) and update origin. Keep your edits to f5.txt exactly as they are, uncommitted."
        + DONE
    )


# ---------------------------------------------------------------- S4 / S5 conflict


def s4_setup(root, env, arm, n):
    setup_stack(root, env, arm, n, conflict_b=3)
    upstream_commit(root, env, {"conf.txt": "from-main\n"})


def s4_arc(n):
    return ["arc sync -q || true", write("conf.txt", RESOLVED), "git add conf.txt"] + [
        "arc rebase --continue -q",
        "arc push -q",
    ]


def s4_git(n):
    return [
        "git fetch -q",
        "git rebase -q --update-refs origin/main || true",
        write("conf.txt", RESOLVED),
        "git add conf.txt",
        "git rebase --continue",
        push_all(n),
    ]


def s4_prompt(n):
    return ctx(n) + (
        "Someone merged a change into main on origin. Bring the whole stack up to date with origin's "
        "main (b1 directly on top of it) and update origin. If conf.txt conflicts, resolve it so the "
        "file contains exactly two lines: 'from-b3' then 'from-main'." + DONE
    )


def s4_expected(n):
    edits = {3: [{"f3.txt": "b3 v1\n", "conf.txt": RESOLVED}]}
    return expect(n, conflict_b=3, trunk_extra=[{"conf.txt": "from-main\n"}], edits=edits)


def s5_setup(root, env, arm, n):
    s4_setup(root, env, arm, n)
    return snapshot_refs(root, env)


def s5_prompt(n):
    return ctx(n) + (
        "Try to bring the stack up to date with origin's main. If that hits any conflict, do NOT resolve "
        "it: back out completely so every local branch and everything on origin is exactly as it was "
        "before you started, with a clean working tree and nothing in progress." + DONE
    )


# ---------------------------------------------------------------- S6 / S12 / S13 merged upstream


def s6_setup(root, env, arm, n, k=1):
    setup_stack(root, env, arm, n, k=k)
    squash_merge_on_origin(root, env, "b1")


def s6_git(n):
    return [
        "git fetch -q --prune",
        f"git rebase -q --update-refs --onto origin/main b1 b{n}",
        "git branch -q -D b1",
        push_all(n, lo=2),
    ]


def s6_prompt(n, k=1):
    return ctx(n, k) + (
        "b1's pull request was just squash-merged into main on origin (the merge also deleted b1 on "
        "origin). Remove b1 locally, put the rest of the stack (b2 and up) directly on top of origin's "
        "new main without re-applying b1's change, and update origin." + DONE
    )


def s12_setup(root, env, arm, n):
    setup_stack(root, env, arm, n)
    squash_merge_on_origin(root, env, "b1")
    squash_merge_on_origin(root, env, "b2")


def s12_git(n):
    return [
        "git fetch -q --prune",
        f"git rebase -q --update-refs --onto origin/main b2 b{n}",
        "git branch -q -D b1 b2",
        push_all(n, lo=3),
    ]


def s12_prompt(n):
    return ctx(n) + (
        "While you were away, b1's and then b2's pull requests were both squash-merged into main on "
        "origin, and both branches were deleted on origin. Remove b1 and b2 locally, put b3 and up "
        "directly on top of origin's main without re-applying their changes, and update origin."
        + DONE
    )


def s13_setup(root, env, arm, n):
    setup_stack(root, env, arm, n)
    merge_commit_on_origin(root, env, "b1")


def s13_git(n):
    return [
        "git fetch -q --prune",
        "git rebase -q --update-refs origin/main",
        "git branch -q -D b1",
        push_all(n, lo=2),
    ]


def s13_prompt(n):
    return ctx(n) + (
        "b1's pull request was just merged into main on origin with a merge commit (the merge also "
        "deleted b1 on origin). Remove b1 locally, put the rest of the stack (b2 and up) directly on "
        "top of origin's new main, and update origin." + DONE
    )


# ---------------------------------------------------------------- S7 drop middle


def s7_arc(n):
    return [
        "arc drop b3 --force -q",
        "arc push -q",
        "git branch -q -D b3",
        "git push -q origin --delete b3",
    ]


def s7_git(n):
    return [
        f"git rebase -q --update-refs --onto b2 b3 b{n}",
        "git branch -q -D b3",
        f"git push -q --force-with-lease origin {names(n, lo=4)} :b3",
    ]


def s7_prompt(n, k=1):
    return ctx(n, k) + (
        "The idea in b3 was abandoned. Remove b3 from the stack entirely (its change must not appear in "
        "any branch), so b4 sits directly on b2. Delete b3 locally and on origin, and update origin."
        + DONE
    )


# ---------------------------------------------------------------- S9 review fix as a new commit


def s9_arc(n):
    return [
        "git checkout -q b2",
        write("f2_fix.txt", "review fix\n"),
        "git add f2_fix.txt",
        "git commit -q -m 'fix: review'",
        "arc rebase --upstack -q",
        "arc push -q",
    ]


def s9_git(n):
    return [
        "git checkout -q b2",
        write("f2_fix.txt", "review fix\n"),
        "git add f2_fix.txt",
        "git commit -q -m 'fix: review'",
        f"git rebase -q --update-refs b2 b{n}",
        push_all(n, lo=2),
    ]


def s9_prompt(n):
    return ctx(n) + (
        "A reviewer asked for a change on b2. Add a new commit on b2 that creates f2_fix.txt containing "
        "exactly the line 'review fix' (b2 then has two commits). Make sure every branch above b2 "
        "includes it, and update origin." + DONE
    )


# ---------------------------------------------------------------- S14 teammate pushed to b2


def s14_setup(root, env, arm, n):
    setup_stack(root, env, arm, n)
    push_to_branch(root, env, "b2", {"t2.txt": "teammate\n"}, "feat: teammate's change")
    upstream_commit(root, env, TRUNK_MOVED[0])


def s14_git(n):
    return [
        "git fetch -q",
        "git checkout -q b2",
        "git merge -q --ff-only origin/b2",
        f"git rebase -q --update-refs b2 b{n}",
        f"git rebase -q --update-refs origin/main b{n}",
        push_all(n),
    ]


def s14_prompt(n):
    return ctx(n) + (
        "A teammate pushed an extra commit to b2 on origin (it adds t2.txt). Separately, someone merged "
        "new work into main on origin. Bring the stack up to date so that b2 includes your teammate's "
        "commit and b1 sits directly on origin's main, then update origin without losing your "
        "teammate's work." + DONE
    )


# ---------------------------------------------------------------- S15 conflict during an edit

S15_B2 = "from-b2\n"
S15_RESOLVED = "from-b2\nfrom-b3\n"


def s15_setup(root, env, arm, n):
    setup_stack(root, env, arm, n, conflict_b=3)


def s15_arc(n):
    return [
        "git checkout -q b2",
        write("conf.txt", S15_B2),
        "git add conf.txt",
        "arc edit -q || true",
        write("conf.txt", S15_RESOLVED),
        "git add conf.txt",
        "arc edit --continue -q",
    ]


def s15_git(n):
    return [
        "git checkout -q b2",
        write("conf.txt", S15_B2),
        "git add conf.txt",
        "git commit -q --amend --no-edit",
        f"git rebase -q --update-refs --onto b2 b2@{{1}} b{n} || true",
        write("conf.txt", S15_RESOLVED),
        "git add conf.txt",
        "git rebase --continue",
        push_all(n, lo=2),
    ]


def s15_prompt(n):
    return ctx(n) + (
        "b3's commit changes conf.txt. A reviewer asked that b2's commit also set conf.txt to exactly "
        "the line 'from-b2'. Fold this into b2's existing commit (b2 stays one commit), carry the change "
        "up the stack, and update origin. When b3 conflicts on conf.txt, resolve it so conf.txt contains "
        "exactly two lines: 'from-b2' then 'from-b3'." + DONE
    )


def s15_expected(n):
    edits = {
        2: [{"f2.txt": "b2 v1\n", "conf.txt": S15_B2}],
        3: [{"f3.txt": "b3 v1\n", "conf.txt": S15_RESOLVED}],
    }
    return expect(n, conflict_b=3, edits=edits)


# ---------------------------------------------------------------- S16 insert a branch mid-stack


def s16_git(n):
    return [
        "git checkout -q -b bX b2",
        write("fx.txt", "bx v1\n"),
        "git add fx.txt",
        "git commit -q -m 'feat: bX'",
        f"git rebase -q --update-refs --onto bX b2 b{n}",
        f"git push -q --force-with-lease origin bX {names(n, lo=3)}",
    ]


def s16_prompt(n):
    return ctx(n) + (
        "A reviewer asked you to split out a preparatory change. Create a new branch bX between b2 and "
        "b3, with one commit that adds fx.txt containing exactly the line 'bx v1'. b3 must then sit "
        "directly on bX. Push bX and update origin." + DONE
    )


def s16_expected(n):
    s = expect(n)
    s.branches.insert(2, ("bX", [{"fx.txt": "bx v1\n"}]))
    return s


SCENARIOS = {
    s.id: s
    for s in [
        Scenario(
            "S1",
            "Build a stack and push it",
            s1_setup,
            lambda n: expect(n),
            s1_arc,
            s1_git,
            s1_prompt,
        ),
        Scenario(
            "S2",
            "Amend a mid-stack branch",
            _plain,
            lambda n: expect(n, edits={2: [{"f2.txt": "b2 v2\n"}]}),
            s2_arc,
            s2_git,
            s2_prompt,
        ),
        Scenario(
            "S3",
            "Trunk moved: sync",
            s3_setup,
            lambda n: expect(n, trunk_extra=TRUNK_MOVED),
            SYNC_ARC,
            SYNC_GIT,
            s3_prompt,
        ),
        Scenario(
            "S4", "Sync with a conflict: resolve", s4_setup, s4_expected, s4_arc, s4_git, s4_prompt
        ),
        Scenario(
            "S5",
            "Sync with a conflict: abort",
            s5_setup,
            lambda n: None,
            lambda n: ["arc sync -q || true", "arc rebase --abort -q"],
            lambda n: [
                "git fetch -q",
                "git rebase -q --update-refs origin/main || true",
                "git rebase --abort",
            ],
            s5_prompt,
        ),
        Scenario(
            "S6",
            "Bottom branch squash-merged",
            s6_setup,
            lambda n: expect(n, merged=(1,)),
            SYNC_ARC,
            s6_git,
            s6_prompt,
        ),
        Scenario(
            "S7",
            "Drop a middle branch",
            _plain,
            lambda n: expect(n, drop=(3,)),
            s7_arc,
            s7_git,
            s7_prompt,
        ),
        Scenario(
            "S8",
            "Amend two non-adjacent branches",
            _plain,
            lambda n: expect(n, edits={2: [{"f2.txt": "b2 v2\n"}], 4: [{"f4.txt": "b4 v2\n"}]}),
            s8_arc,
            s8_git,
            s8_prompt,
        ),
        Scenario(
            "S9",
            "Review fix as a new commit",
            _plain,
            lambda n: expect(n, edits={2: branch_commits(2) + [{"f2_fix.txt": "review fix\n"}]}),
            s9_arc,
            s9_git,
            s9_prompt,
        ),
        Scenario(
            "S10",
            "Sync with uncommitted changes",
            s10_setup,
            lambda n: expect(n, trunk_extra=TRUNK_MOVED, wip={"f5.txt": "b5 wip\n"}),
            lambda n: ["git stash -q", "arc sync -q", "arc push -q", "git stash pop -q"],
            s10_git,
            s10_prompt,
        ),
        Scenario(
            "S11a",
            "Trunk moved, 3 commits per branch",
            lambda r, e, a, n: s3_setup(r, e, a, n, k=3),
            lambda n: expect(n, k=3, trunk_extra=TRUNK_MOVED),
            SYNC_ARC,
            SYNC_GIT,
            lambda n: s3_prompt(n, 3),
        ),
        Scenario(
            "S11b",
            "Squash-merged bottom, 3 commits per branch",
            lambda r, e, a, n: s6_setup(r, e, a, n, k=3),
            lambda n: expect(n, k=3, merged=(1,)),
            SYNC_ARC,
            s6_git,
            lambda n: s6_prompt(n, 3),
        ),
        Scenario(
            "S11c",
            "Drop a middle branch, 3 commits per branch",
            lambda r, e, a, n: setup_stack(r, e, a, n, k=3) and None,
            lambda n: expect(n, k=3, drop=(3,)),
            s7_arc,
            s7_git,
            lambda n: s7_prompt(n, 3),
        ),
        Scenario(
            "S12",
            "Two bottom branches squash-merged",
            s12_setup,
            lambda n: expect(n, merged=(1, 2)),
            SYNC_ARC,
            s12_git,
            s12_prompt,
        ),
        Scenario(
            "S13",
            "Bottom branch merged with a merge commit",
            s13_setup,
            lambda n: expect(n, merged=(1,)),
            SYNC_ARC,
            s13_git,
            s13_prompt,
        ),
        Scenario(
            "S14",
            "Teammate pushed to a stack branch",
            s14_setup,
            lambda n: expect(
                n,
                trunk_extra=TRUNK_MOVED,
                edits={2: branch_commits(2) + [{"t2.txt": "teammate\n"}]},
            ),
            SYNC_ARC,
            s14_git,
            s14_prompt,
        ),
        Scenario(
            "S15",
            "Conflict during a mid-stack amend",
            s15_setup,
            s15_expected,
            s15_arc,
            s15_git,
            s15_prompt,
        ),
        Scenario(
            "S16", "Insert a branch mid-stack", _plain, s16_expected, None, s16_git, s16_prompt
        ),
    ]
}
