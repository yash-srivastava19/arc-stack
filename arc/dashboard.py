from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


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
