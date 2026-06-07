import pytest
from pathlib import Path
from dataclasses import dataclass
from arc.dashboard import BranchStatus, StackView, load_stack_view
from unittest.mock import patch, MagicMock


class TestBranchStatus:
    """Tests for BranchStatus dataclass."""

    def test_status_icon_approved(self):
        """Approved branch shows ✅."""
        branch = BranchStatus(
            name="feat/auth",
            pr_number=1,
            ci_passing=True,
            approved=True,
            draft=False,
            commits=1,
            revision=1,
            blocker_reason=None
        )
        assert branch.status_icon == "✅"

    def test_status_icon_blocked(self):
        """Blocked branch shows ⏳."""
        branch = BranchStatus(
            name="feat/api",
            pr_number=2,
            ci_passing=True,
            approved=False,
            draft=False,
            commits=1,
            revision=1,
            blocker_reason="not yet approved"
        )
        assert branch.status_icon == "⏳"

    def test_status_icon_ci_running(self):
        """CI running shows ⚙️."""
        branch = BranchStatus(
            name="feat/ui",
            pr_number=3,
            ci_passing=None,
            approved=False,
            draft=False,
            commits=1,
            revision=1,
            blocker_reason=None
        )
        assert branch.status_icon == "⚙️"

    def test_status_icon_ci_failing(self):
        """CI failing shows ✗."""
        branch = BranchStatus(
            name="feat/test",
            pr_number=4,
            ci_passing=False,
            approved=False,
            draft=False,
            commits=1,
            revision=1,
            blocker_reason="CI is failing"
        )
        assert branch.status_icon == "✗"

    def test_status_icon_no_pr(self):
        """No PR shows ○."""
        branch = BranchStatus(
            name="feat/draft",
            pr_number=None,
            ci_passing=None,
            approved=False,
            draft=True,
            commits=2,
            revision=1,
            blocker_reason=None
        )
        assert branch.status_icon == "○"


class TestStackView:
    """Tests for StackView dataclass."""

    def test_current_branch_valid_index(self):
        """current_branch returns branch at current_index."""
        b1 = BranchStatus("feat/a", 1, True, True, False, 1, 1, None)
        b2 = BranchStatus("feat/b", 2, True, False, False, 1, 1, "not yet approved")
        stack = StackView(base="main", branches=[b1, b2], current_index=0)
        assert stack.current_branch == b1

    def test_current_branch_out_of_bounds(self):
        """current_branch returns None when index out of bounds."""
        b1 = BranchStatus("feat/a", 1, True, True, False, 1, 1, None)
        stack = StackView(base="main", branches=[b1], current_index=5)
        assert stack.current_branch is None

    def test_move_selection_down(self):
        """move_selection(1) moves cursor down."""
        b1 = BranchStatus("feat/a", 1, True, True, False, 1, 1, None)
        b2 = BranchStatus("feat/b", 2, True, False, False, 1, 1, "not yet approved")
        stack = StackView(base="main", branches=[b1, b2], current_index=0)
        stack.move_selection(1)
        assert stack.current_index == 1

    def test_move_selection_up(self):
        """move_selection(-1) moves cursor up."""
        b1 = BranchStatus("feat/a", 1, True, True, False, 1, 1, None)
        b2 = BranchStatus("feat/b", 2, True, False, False, 1, 1, "not yet approved")
        stack = StackView(base="main", branches=[b1, b2], current_index=1)
        stack.move_selection(-1)
        assert stack.current_index == 0

    def test_move_selection_respects_bounds(self):
        """move_selection respects bounds and doesn't move out of range."""
        b1 = BranchStatus("feat/a", 1, True, True, False, 1, 1, None)
        stack = StackView(base="main", branches=[b1], current_index=0)
        stack.move_selection(-5)
        assert stack.current_index == 0
        stack.move_selection(5)
        assert stack.current_index == 0


class TestLoadStackView:
    """Tests for load_stack_view function."""

    @patch('arc.dashboard.st.load')
    @patch('arc.dashboard.github.get_pr_status')
    def test_load_stack_view_with_pr(self, mock_get_pr, mock_load):
        """load_stack_view loads branches and PR status."""
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/auth", "pr_number": 1, "commits": 2, "revision": 1}
            ]
        }
        mock_get_pr.return_value = {
            "ci_passing": True,
            "approved": True,
            "draft": False
        }

        stack = load_stack_view(Path("."))

        assert stack.base == "main"
        assert len(stack.branches) == 1
        assert stack.branches[0].name == "feat/auth"
        assert stack.branches[0].pr_number == 1
        assert stack.branches[0].ci_passing is True
        assert stack.branches[0].approved is True

    @patch('arc.dashboard.st.load')
    def test_load_stack_view_no_pr(self, mock_load):
        """load_stack_view marks branches without PR as draft."""
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/draft", "pr_number": None, "commits": 1, "revision": 1}
            ]
        }

        stack = load_stack_view(Path("."))

        assert stack.branches[0].draft is True
        assert stack.branches[0].pr_number is None

    @patch('arc.dashboard.st.load')
    @patch('arc.dashboard.github.get_pr_status')
    def test_blocker_reason_ci_failing(self, mock_get_pr, mock_load):
        """load_stack_view sets blocker when CI is failing."""
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/broken", "pr_number": 1, "commits": 1, "revision": 1}
            ]
        }
        mock_get_pr.return_value = {
            "ci_passing": False,
            "approved": False,
            "draft": False
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].blocker_reason == "CI is failing"

    @patch('arc.dashboard.st.load')
    @patch('arc.dashboard.github.get_pr_status')
    def test_blocker_reason_not_approved(self, mock_get_pr, mock_load):
        """load_stack_view sets blocker when not approved."""
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/pending", "pr_number": 1, "commits": 1, "revision": 1}
            ]
        }
        mock_get_pr.return_value = {
            "ci_passing": True,
            "approved": False,
            "draft": False
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].blocker_reason == "not yet approved"
