"""Shared harness code: isolated environment, deterministic fixtures, and the oracle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BENCH = Path(__file__).resolve().parent
# Trials live outside the repo so nested git repos never land in the working tree.
TRIALS = Path(os.environ.get("BENCH_TRIALS", tempfile.gettempdir())) / "arc-bench-trials"
DATE = "2026-01-01T00:00:00Z"
# The arc under test. Point BENCH_VENV at another venv to benchmark a different arc version.
VENV = Path(os.environ.get("BENCH_VENV", BENCH / ".venv"))


def make_env(arm: str, extra: dict | None = None) -> dict:
    """Environment for one arm. `arc` puts bench/.venv/bin on PATH; `git` does not."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") and k not in ("VIRTUAL_ENV", "PYTHONPATH")
    }
    path = [str(BENCH / "bin")]
    if arm == "arc":
        path.append(str(VENV / "bin"))
    path += ["/usr/local/bin", "/usr/bin", "/bin"]
    env.update(
        PATH=":".join(path),
        GIT_CONFIG_GLOBAL=str(BENCH / "gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_DATE=DATE,
        GIT_COMMITTER_DATE=DATE,
        GIT_EDITOR="true",
        GIT_TERMINAL_PROMPT="0",
        NO_COLOR="1",
        LC_ALL="C.UTF-8",
    )
    if extra:
        env.update(extra)
    return env


def sh(args, cwd, env, check=True, inp=None) -> subprocess.CompletedProcess:
    r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, input=inp)
    if check and r.returncode != 0:
        raise RuntimeError(f"{args} failed in {cwd}:\n{r.stdout}\n{r.stderr}")
    return r


def git(cwd, env, *args, check=True) -> str:
    return sh(["git", *args], cwd, env, check=check).stdout.strip()


# ---------------------------------------------------------------- declarative specs


@dataclass
class Spec:
    """A stack described as data: trunk commits plus ordered branches of commits.

    A commit is {path: content}. Content None deletes the file.
    """

    trunk: list[dict]
    branches: list[tuple[str, list[dict]]]
    gone: list[str] = field(default_factory=list)  # branches that must not exist
    wip: dict = field(default_factory=dict)  # uncommitted edits that must survive


def base_trunk() -> list[dict]:
    return [{"README.md": "# bench\n", "main.txt": "m0\n", "conf.txt": "base\n"}]


def branch_commits(i: int, k: int = 1, conflict: bool = False) -> list[dict]:
    """Commits for branch b<i>. The first adds f<i>.txt, later ones add f<i>_<j>.txt."""
    first = {f"f{i}.txt": f"b{i} v1\n"}
    if conflict:
        first["conf.txt"] = f"from-b{i}\n"
    return [first] + [{f"f{i}_{j}.txt": f"b{i} part {j}\n"} for j in range(2, k + 1)]


def stack(n: int, conflict_b: int | None = None, k: int = 1) -> list:
    return [(f"b{i}", branch_commits(i, k, conflict_b == i)) for i in range(1, n + 1)]


def apply_commit(cwd: Path, env, files: dict, msg: str) -> None:
    for p, content in files.items():
        f = cwd / p
        if content is None:
            if f.exists():
                git(cwd, env, "rm", "-q", p)
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        git(cwd, env, "add", p)
    git(cwd, env, "commit", "-q", "-m", msg)


def build_repo(root: Path, spec: Spec, env, push=True) -> Path:
    """origin.git (bare) plus work/ with trunk `main` and the stack, pushed."""
    git(root, env, "init", "-q", "--bare", "origin.git")
    work = root / "work"
    git(root, env, "init", "-q", "work")
    git(work, env, "remote", "add", "origin", "../origin.git")
    for k, c in enumerate(spec.trunk):
        apply_commit(work, env, c, f"chore: trunk {k}")
    git(work, env, "push", "-q", "-u", "origin", "main")
    for name, commits in spec.branches:
        git(work, env, "checkout", "-q", "-b", name)
        for k, c in enumerate(commits):
            apply_commit(work, env, c, f"feat: {name} part {k}")
    if push and spec.branches:
        git(work, env, "push", "-q", "-u", "origin", *[b for b, _ in spec.branches])
    return work


def teammate(root: Path, env) -> Path:
    """A second clone of origin, standing in for another developer or GitHub's merge button."""
    other = root / "_other"
    if not other.exists():
        git(root, env, "clone", "-q", "origin.git", "_other")
    git(other, env, "fetch", "-q", "--prune", "origin")
    git(other, env, "checkout", "-q", "-B", "main", "origin/main")
    return other


def upstream_commit(root: Path, env, files: dict, msg="chore: upstream change") -> None:
    """Another developer pushes a commit to origin/main."""
    other = teammate(root, env)
    apply_commit(other, env, files, msg)
    git(other, env, "push", "-q", "origin", "main")


def squash_merge_on_origin(root: Path, env, branch: str) -> None:
    """GitHub squash merge of `branch` into main, with delete-branch-on-merge."""
    other = teammate(root, env)
    git(other, env, "merge", "-q", "--squash", f"origin/{branch}")
    git(other, env, "commit", "-q", "-m", f"{branch} (#1)")
    git(other, env, "push", "-q", "origin", "main", f":{branch}")


def merge_commit_on_origin(root: Path, env, branch: str) -> None:
    """GitHub "Create a merge commit" of `branch` into main, with delete-branch-on-merge."""
    other = teammate(root, env)
    git(other, env, "merge", "-q", "--no-ff", "-m", f"Merge {branch} (#1)", f"origin/{branch}")
    git(other, env, "push", "-q", "origin", "main", f":{branch}")


def push_to_branch(root: Path, env, branch: str, files: dict, msg: str) -> None:
    """A teammate pushes a commit on top of origin/<branch>."""
    other = teammate(root, env)
    git(other, env, "checkout", "-q", "-B", branch, f"origin/{branch}")
    apply_commit(other, env, files, msg)
    git(other, env, "push", "-q", "origin", branch)


def arc_adopt(work: Path, env, branches: list[str]) -> None:
    sh(["arc", "--no-input", "init", "--base", "main", "-q"], work, env)
    for b in branches:
        sh(["arc", "--no-input", "add", b, "-q"], work, env)


# ---------------------------------------------------------------- expected state


@dataclass
class Expect:
    trunk_tree: str
    branches: list[tuple[str, str, str, int]]  # (name, tree, cumulative patch-id, commits)
    gone: list[str]
    wip: dict


def _patch_id(cwd, env, a, b) -> str:
    diff = sh(["git", "diff", "--binary", a, b], cwd, env).stdout
    if not diff:
        return "EMPTY"
    out = sh(["git", "patch-id", "--stable"], cwd, env, inp=diff).stdout.split()
    return out[0] if out else "EMPTY"


def expected_from_spec(spec: Spec) -> Expect:
    env = make_env("git")
    TRIALS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TRIALS) as td:
        work = build_repo(Path(td), spec, env, push=False)
        trunk_tree = git(work, env, "rev-parse", "main^{tree}")
        rows, prev = [], "main"
        for name, commits in spec.branches:
            tree = git(work, env, "rev-parse", f"{name}^{{tree}}")
            rows.append((name, tree, _patch_id(work, env, prev, name), len(commits)))
            prev = name
        return Expect(trunk_tree, rows, spec.gone, spec.wip)


# ---------------------------------------------------------------- oracle


def snapshot_refs(root: Path, env) -> dict:
    loc = git(root / "work", env, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")
    rem = git(
        root / "origin.git", env, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads"
    )
    return {
        # Local trunk is excluded: refreshing main from origin is not part of a stack rollback.
        "local": {
            r: s for r, s in (ln.split() for ln in loc.splitlines()) if r != "refs/heads/main"
        },
        "origin": dict(ln.split() for ln in rem.splitlines()) if rem else {},
    }


def oracle(root: Path, exp: Expect | None, pre_refs: dict | None = None, arm: str = "git") -> dict:
    """Judge the end state from git alone, plus arc's stack file for the arc arm.

    Returns {check: (ok, detail)}.
    """
    env = make_env("git")
    work, origin = root / "work", root / "origin.git"
    res: dict[str, tuple[bool, str]] = {}

    def rev(repo, ref):
        r = sh(["git", "rev-parse", "-q", "--verify", ref], repo, env, check=False)
        return r.stdout.strip() if r.returncode == 0 else None

    wip = exp.wip if exp else {}
    gd = Path(git(work, env, "rev-parse", "--absolute-git-dir"))
    inprog = [
        p
        for p in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD")
        if (gd / p).exists()
    ]
    dirty = [
        ln
        for ln in sh(["git", "status", "--porcelain", "--untracked-files=no"], work, env).stdout.splitlines()
        if ln[3:] not in wip
    ]
    detached = sh(["git", "symbolic-ref", "-q", "HEAD"], work, env, check=False).returncode != 0
    res["O5_clean"] = (
        not inprog and not dirty and not detached,
        f"inprog={inprog} dirty={dirty!r} detached={detached}",
    )
    lost = [p for p, c in wip.items() if not (work / p).exists() or (work / p).read_text() != c]
    res["O9_wip_kept"] = (not lost, "; ".join(lost))

    if pre_refs is not None:  # O8: abort scenario, everything back exactly
        now = snapshot_refs(root, env)
        res["O8_rollback"] = (
            now == pre_refs,
            "" if now == pre_refs else f"pre={pre_refs} now={now}",
        )
        return res

    assert exp is not None
    trunk = rev(origin, "refs/heads/main")
    res["O0_trunk"] = (rev(origin, "main^{tree}") == exp.trunk_tree, "origin/main tree")
    prev, o1, o2, o3, o4 = trunk, [], [], [], []
    for name, tree, pid, ncommits in exp.branches:
        tip = rev(work, f"refs/heads/{name}")
        if tip is None:
            o1.append(f"{name}: missing")
            prev = None
            continue
        if rev(work, f"{name}^{{tree}}") != tree:
            o1.append(f"{name}: tree")
        if prev is None or git(work, env, "merge-base", tip, prev, check=False) != prev:
            o2.append(f"{name}: not on parent")
        else:
            cnt = int(git(work, env, "rev-list", "--count", f"{prev}..{tip}"))
            if cnt != ncommits:
                o3.append(f"{name}: {cnt} commits, want {ncommits}")
            elif _patch_id(work, env, prev, tip) != pid:
                o3.append(f"{name}: patch")
        if rev(origin, f"refs/heads/{name}") != tip:
            o4.append(f"{name}: origin != local")
        prev = tip
    res["O1_trees"] = (not o1, "; ".join(o1))
    res["O2_chain"] = (not o2, "; ".join(o2))
    res["O3_commits"] = (not o3, "; ".join(o3))
    res["O4_pushed"] = (not o4, "; ".join(o4))
    o6 = [g for g in exp.gone if rev(work, f"refs/heads/{g}") or rev(origin, f"refs/heads/{g}")]
    res["O6_gone"] = (not o6, "; ".join(o6))
    if arm == "arc":
        state = json.loads((work / ".arc" / "state.json").read_text())
        have = [b["name"] for b in state["branches"]]
        want = [name for name, *_ in exp.branches]
        res["O10_arc_state"] = (have == want, "" if have == want else f"{have} != {want}")
    return res


def passed(res: dict) -> bool:
    return all(ok for ok, _ in res.values())


def failed_checks(res: dict) -> list[str]:
    return [k for k, (ok, _) in res.items() if not ok]


def new_trial_dir(tag: str) -> Path:
    TRIALS.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{tag}-", dir=TRIALS))


def rm(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)
