"""Stack navigation: checkout, up, down, top, bottom."""

from __future__ import annotations

import sys

import click

from arc import git, ops, tip
from arc import state as st
from arc.commands import _shared
from arc.commands._shared import err


@click.command("checkout")
@click.argument("target")
def checkout_cmd(target):
    """Check out a branch by name or index (1-based)."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    if target.isdigit():
        name = ops.branch_at_index(data, int(target))
        if not name:
            err.print(f"No branch at index {target}.")
            sys.exit(5)
    else:
        name = st.apply_prefix(data, target)
        if not st.get_branch(data, name):
            err.print(f"{name!r} is not in the stack.")
            sys.exit(5)
    git.checkout(name)
    err.print(f"Switched to {name}.")


def _navigate(n: int, direction: int) -> None:
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    names = st.branch_names(data)
    current = git.current_branch()
    if current not in names:
        err.print(f"{current!r} is not in the stack.")
        sys.exit(5)
    idx = names.index(current) + direction * n
    idx = max(0, min(idx, len(names) - 1))
    git.checkout(names[idx])
    err.print(f"Switched to {names[idx]}.")


@click.command("up")
@click.argument("n", default=1, type=int)
def up_cmd(n):
    """Move up n branches toward the top."""
    _navigate(n, 1)


@click.command("down")
@click.argument("n", default=1, type=int)
def down_cmd(n):
    """Move down n branches toward the trunk."""
    _navigate(n, -1)


@click.command("top")
def top_cmd():
    """Jump to the topmost branch."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    git.checkout(names[-1])
    err.print(f"Switched to {names[-1]}.")


@click.command("tip")
def tip_cmd():
    """Create or update the local arc-tip branch to point at the stack's top, and check it out."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    top = names[-1]
    sha = git.get_sha(top)
    git.checkout_branch_at(tip.TIP_BRANCH, sha)
    err.print(f"{tip.TIP_BRANCH} → {top} ({sha[:8]})")


@click.command("bottom")
def bottom_cmd():
    """Jump to the bottommost branch."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    git.checkout(names[0])
    err.print(f"Switched to {names[0]}.")
