"""Maintains a local `arc-tip` branch that always tracks the stack's top branch.

Opt-in: arc-tip is only created by `arc tip`. Other stack-mutating commands
call sync_tip_branch, which is a no-op until arc-tip exists locally.
"""

from __future__ import annotations

from arc import git
from arc import state as st
from arc.state import StackState

TIP_BRANCH = "arc-tip"


def sync_tip_branch(data: StackState) -> None:
    """If arc-tip exists locally, fast-forward it to the current top-of-stack SHA.

    No-op if arc-tip doesn't exist yet, the stack is empty, or arc-tip is the
    currently checked-out branch (force-moving it would fail and this function
    must never disturb the user's current branch)."""
    if not git.branch_exists(TIP_BRANCH):
        return
    if git.current_branch() == TIP_BRANCH:
        return
    names = st.branch_names(data)
    if not names:
        return
    git.force_update_branch(TIP_BRANCH, git.get_sha(names[-1]))
