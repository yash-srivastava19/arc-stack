from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from arc import state as st
from arc import github


@dataclass
class BranchStatus:
    """Status of a single branch in the stack."""
    name: str
    pr_number: Optional[int]
    ci_passing: Optional[bool]  # None = pending/unknown
    approved: bool
    draft: bool
    commits: int
    revision: int
    blocker_reason: Optional[str]  # e.g., "waiting on feat/auth to land"

    @property
    def status_icon(self) -> str:
        """Return icon for branch status."""
        if self.blocker_reason:
            return "⏳"  # blocked/waiting
        if self.ci_passing is False:
            return "✗"  # failing
        if self.ci_passing is None:
            return "⚙️"  # running/pending
        if self.approved:
            return "✅"  # ready to land
        return "○"  # no PR or not ready


@dataclass
class StackView:
    """Model for the entire stack view."""
    base: str  # "main"
    branches: list[BranchStatus]
    current_index: int = 0  # selected branch

    @property
    def current_branch(self) -> Optional[BranchStatus]:
        """Get currently selected branch."""
        if 0 <= self.current_index < len(self.branches):
            return self.branches[self.current_index]
        return None

    def move_selection(self, delta: int) -> None:
        """Move selection up (-1) or down (+1)."""
        new_index = self.current_index + delta
        if 0 <= new_index < len(self.branches):
            self.current_index = new_index


def load_stack_view(root: Path) -> StackView:
    """Load stack state and GitHub PR status into a StackView model.

    Reads .arc/state.json and fetches PR status for each branch.
    """
    data = st.load(root)
    branches = []

    for branch_dict in data.get("branches", []):
        name = branch_dict["name"]
        pr_number = branch_dict.get("pr_number")

        # Fetch GitHub status if PR exists
        blocker_reason = None
        ci_passing = None
        approved = False
        draft = False
        if pr_number:
            pr_status = github.get_pr_status(pr_number)
            ci_passing = pr_status.get("ci_passing")
            approved = pr_status.get("approved", False)
            draft = pr_status.get("draft", False)

            # Compute blocker reason: CI failure takes priority
            if ci_passing is False:
                blocker_reason = "CI is failing"
            elif not approved and not draft:
                blocker_reason = "not yet approved"
        else:
            draft = True  # no PR = draft

        branch = BranchStatus(
            name=name,
            pr_number=pr_number,
            ci_passing=ci_passing,
            approved=approved,
            draft=draft,
            commits=branch_dict.get("commits", 0),
            revision=branch_dict.get("revision", 0),
            blocker_reason=blocker_reason,
        )
        branches.append(branch)

    return StackView(base=data.get("base", "main"), branches=branches)
