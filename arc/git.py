from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TypedDict

from arc.exceptions import GitError


class DiffStat(TypedDict):
    files_changed: list[str]
    insertions: int
    deletions: int


_VERBOSE = False  # module-level flag set by cli


def _run(
    args: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    if _VERBOSE:
        import sys as _sys

        print(f"  git {' '.join(str(a) for a in args[1:])}", file=_sys.stderr)
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)
    except subprocess.CalledProcessError as e:
        raise GitError(e.stderr.strip() or f"git {args[1]} exited {e.returncode}") from e


def find_repo_root(start: Path | None = None) -> Path:
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Not in a git repository.")


def is_installed() -> bool:
    return _run(["git", "--version"], check=False).returncode == 0


def current_branch() -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def default_branch(remote: str = "origin") -> str:
    result = _run(["git", "remote", "show", remote], check=False)
    for line in result.stdout.splitlines():
        if "HEAD branch" in line:
            return line.split(":", 1)[1].strip()
    # No remote (or remote unreachable) — probe common trunk names locally.
    for candidate in ("main", "master", "trunk", "develop"):
        if _run(["git", "branch", "--list", candidate], check=False).stdout.strip():
            return candidate
    # Last resort: current branch (user is likely on trunk during init).
    symbolic = _run(["git", "symbolic-ref", "--short", "HEAD"], check=False)
    return symbolic.stdout.strip() or "main"


def branch_exists(name: str) -> bool:
    return bool(_run(["git", "branch", "--list", name]).stdout.strip())


def branch_exists_remote(name: str) -> bool:
    result = _run(["git", "branch", "-r", "--list", f"origin/{name}"], check=False)
    return bool(result.stdout.strip())


def create_branch(name: str, from_ref: str = "HEAD") -> None:
    _run(["git", "checkout", "-b", name, from_ref])


def checkout(name: str) -> None:
    _run(["git", "checkout", name])


def get_sha(ref: str) -> str:
    return _run(["git", "rev-parse", ref]).stdout.strip()


def commit_count(base: str, branch: str) -> int:
    return int(_run(["git", "rev-list", "--count", f"{base}..{branch}"]).stdout.strip())


def is_ancestor(ancestor: str, descendant: str) -> bool:
    return (
        _run(["git", "merge-base", "--is-ancestor", ancestor, descendant], check=False).returncode
        == 0
    )


def fetch(remote: str = "origin") -> None:
    _run(["git", "fetch", remote])


def rebase(onto: str) -> subprocess.CompletedProcess:
    return _run(["git", "rebase", onto], check=False)


def rebase_onto(new_base: str, old_base: str, branch: str) -> subprocess.CompletedProcess:
    return _run(["git", "rebase", "--onto", new_base, old_base, branch], check=False)


def rebase_fork_point(onto: str) -> subprocess.CompletedProcess:
    """Rebase using --fork-point so amended parent commits don't replay into children.

    When a parent branch is amended externally (git commit --amend), plain
    `git rebase <parent>` replays the old amended content as new commits → conflict.
    --fork-point finds the last commit that was in <onto>'s reflog and is also
    an ancestor of HEAD, then rebases from that point — skipping the old content.
    Falls back to merge-base if no fork point is found (git handles this internally).
    """
    return _run(["git", "rebase", "--fork-point", onto], check=False)


def refresh_index() -> None:
    """Clear phantom mtime differences so rebase/status aren't confused by unchanged files."""
    _run(["git", "update-index", "--refresh"], check=False)


def rebase_continue() -> subprocess.CompletedProcess:
    return _run(["git", "rebase", "--continue"], check=False)


def rebase_abort() -> None:
    _run(["git", "rebase", "--abort"], check=False)


def force_push(branches: list[str], remote: str = "origin") -> None:
    _run(["git", "push", "--force-with-lease", "--atomic", remote] + branches)


def delete_branch(name: str, force: bool = False) -> None:
    flag = "-D" if force else "-d"
    _run(["git", "branch", flag, name], check=False)


def force_update_branch(name: str, sha: str) -> None:
    """Create or move local branch `name` to point at `sha`, without checking it out."""
    _run(["git", "branch", "-f", name, sha])


def get_commit_subject(ref: str = "HEAD") -> str:
    return _run(["git", "log", "-1", "--format=%s", ref]).stdout.strip()


def get_commit_body(ref: str = "HEAD") -> str:
    return _run(["git", "log", "-1", "--format=%b", ref]).stdout.strip()


def get_commit_message(ref: str = "HEAD") -> str:
    return _run(["git", "log", "-1", "--format=%B", ref]).stdout.strip()


def amend_message(new_message: str) -> None:
    _run(["git", "commit", "--amend", "-m", new_message])


def get_staged_files() -> list[str]:
    """Return files currently in the git index (staged for commit)."""
    result = _run(["git", "diff", "--cached", "--name-only"], check=False)
    return [f for f in result.stdout.splitlines() if f]


def amend_staged() -> None:
    """Amend HEAD commit with currently staged changes, keeping the existing message."""
    _run(["git", "commit", "--amend", "--no-edit"])


def diff_stat(old_ref: str, new_ref: str) -> DiffStat:
    """Return diff stats between two commits: files_changed list, insertions, deletions."""
    files_result = _run(["git", "diff", "--name-only", old_ref, new_ref], check=False)
    files = [f for f in files_result.stdout.splitlines() if f]

    stat_result = _run(["git", "diff", "--shortstat", old_ref, new_ref], check=False)
    insertions, deletions = 0, 0
    for part in stat_result.stdout.split(","):
        part = part.strip()
        if "insertion" in part:
            insertions = int(part.split()[0])
        elif "deletion" in part:
            deletions = int(part.split()[0])

    return {"files_changed": files, "insertions": insertions, "deletions": deletions}


def is_mid_rebase(root: Path | None = None) -> bool:
    """Return True if git is currently in the middle of a rebase operation."""
    if root is None:
        root = find_repo_root()
    git_path = root / ".git"
    if git_path.is_file():
        # worktree: .git is a file like "gitdir: /path/to/.git/worktrees/name"
        line = git_path.read_text().strip()
        git_dir = Path(line.split("gitdir:", 1)[1].strip())
    else:
        git_dir = git_path
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def reset_branch_to(branch: str, sha: str) -> None:
    """Move a branch pointer to sha. Uses reset --hard if branch is currently checked out."""
    if current_branch() == branch:
        _run(["git", "reset", "--hard", sha])
    else:
        _run(["git", "branch", "-f", branch, sha])


def set_config(key: str, value: str, global_: bool = False) -> None:
    args = ["git", "config"]
    if global_:
        args.append("--global")
    _run(args + [key, value])


def conflicted_files() -> list[str]:
    result = _run(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
    files = []
    for line in result.stdout.splitlines():
        if line:
            # Handle case where line might have status prefix (e.g., "UU filename")
            parts = line.split(None, 1)
            # If there are two parts, the second is the filename; otherwise the whole line is the filename
            filename = parts[1] if len(parts) > 1 else parts[0]
            files.append(filename)
    return files


def changed_files_between(root: Path, from_ref: str, to_ref: str) -> list[str]:
    result = _run(["git", "diff", "--name-only", f"{from_ref}..{to_ref}"], cwd=root, check=False)
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


def is_squash_merged(root: Path, branch: str, base: str) -> bool:
    result = _run(["git", "cherry", "-v", base, branch], cwd=root, check=False)
    if result.returncode != 0:
        return False
    return not any(line.startswith("+") for line in result.stdout.splitlines())
