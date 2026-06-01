from __future__ import annotations
import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)


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
    return "main"


def branch_exists(name: str) -> bool:
    return bool(_run(["git", "branch", "--list", name]).stdout.strip())


def branch_exists_remote(name: str) -> bool:
    """Check if branch exists on origin."""
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
    return _run(["git", "merge-base", "--is-ancestor", ancestor, descendant], check=False).returncode == 0


def fetch(remote: str = "origin") -> None:
    _run(["git", "fetch", remote])


def rebase(onto: str) -> subprocess.CompletedProcess:
    return _run(["git", "rebase", onto], check=False)


def rebase_onto(new_base: str, old_base: str, branch: str) -> subprocess.CompletedProcess:
    return _run(["git", "rebase", "--onto", new_base, old_base, branch], check=False)


def rebase_continue() -> subprocess.CompletedProcess:
    return _run(["git", "rebase", "--continue"], check=False)


def rebase_abort() -> None:
    _run(["git", "rebase", "--abort"], check=False)


def force_push(branches: list[str], remote: str = "origin") -> None:
    _run(["git", "push", "--force-with-lease", "--atomic", remote] + branches)


def delete_branch(name: str) -> None:
    _run(["git", "branch", "-d", name])


def get_commit_subject(ref: str = "HEAD") -> str:
    return _run(["git", "log", "-1", "--format=%s", ref]).stdout.strip()


def get_commit_body(ref: str = "HEAD") -> str:
    return _run(["git", "log", "-1", "--format=%b", ref]).stdout.strip()


def get_commit_message(ref: str = "HEAD") -> str:
    return _run(["git", "log", "-1", "--format=%B", ref]).stdout.strip()


def amend_message(new_message: str) -> None:
    _run(["git", "commit", "--amend", "-m", new_message])


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
