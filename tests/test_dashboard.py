from pathlib import Path
from unittest.mock import patch

from arc.dashboard import (
    BranchStatus,
    BranchTreeWidget,
    DetailWidget,
    StackView,
    SummaryWidget,
    load_stack_view,
)


def make_branch(
    name="feat/a",
    pr_number=None,
    pr_url=None,
    ci_passing=None,
    approved=False,
    draft=True,
    commits=1,
    revision=1,
    blocker_reason=None,
    base="main",
) -> BranchStatus:
    return BranchStatus(
        name=name,
        pr_number=pr_number,
        pr_url=pr_url,
        ci_passing=ci_passing,
        approved=approved,
        draft=draft,
        commits=commits,
        revision=revision,
        blocker_reason=blocker_reason,
        base=base,
    )


class TestBranchStatus:
    def test_status_icon_approved(self):
        branch = make_branch(pr_number=1, ci_passing=True, approved=True, draft=False)
        assert branch.status_icon == "✓"

    def test_status_icon_ci_running(self):
        branch = make_branch(pr_number=3, ci_passing=None, approved=False, draft=False)
        assert branch.status_icon == "⚙"

    def test_status_icon_ci_failing(self):
        branch = make_branch(pr_number=4, ci_passing=False, approved=False, draft=False)
        assert branch.status_icon == "✗"

    def test_status_icon_no_pr(self):
        branch = make_branch(pr_number=None, draft=True)
        assert branch.status_icon == "○"

    def test_status_color_approved(self):
        branch = make_branch(pr_number=1, ci_passing=True, approved=True, draft=False)
        assert branch.status_color == "#8fb573"

    def test_status_color_ci_failing(self):
        branch = make_branch(pr_number=1, ci_passing=False, draft=False)
        assert branch.status_color == "#e0796f"

    def test_status_color_no_pr(self):
        branch = make_branch(pr_number=None)
        assert branch.status_color == "#5f6b52"


class TestStackView:
    def test_current_branch_valid_index(self):
        b1 = make_branch("feat/a", pr_number=1, ci_passing=True, approved=True)
        b2 = make_branch("feat/b", pr_number=2, base="feat/a")
        stack = StackView(base="main", branches=[b1, b2], current_index=0)
        assert stack.current_branch == b1

    def test_current_branch_out_of_bounds(self):
        b1 = make_branch("feat/a", pr_number=1)
        stack = StackView(base="main", branches=[b1], current_index=5)
        assert stack.current_branch is None

    def test_move_selection_down(self):
        b1 = make_branch("feat/a")
        b2 = make_branch("feat/b", base="feat/a")
        stack = StackView(base="main", branches=[b1, b2], current_index=0)
        stack.move_selection(1)
        assert stack.current_index == 1

    def test_move_selection_up(self):
        b1 = make_branch("feat/a")
        b2 = make_branch("feat/b", base="feat/a")
        stack = StackView(base="main", branches=[b1, b2], current_index=1)
        stack.move_selection(-1)
        assert stack.current_index == 0

    def test_move_selection_respects_bounds(self):
        b1 = make_branch("feat/a")
        stack = StackView(base="main", branches=[b1], current_index=0)
        stack.move_selection(-5)
        assert stack.current_index == 0
        stack.move_selection(5)
        assert stack.current_index == 0

    def test_move_selection_empty_stack(self):
        stack = StackView(base="main", branches=[], current_index=0)
        stack.move_selection(1)
        assert stack.current_index == 0

    def test_index_of_existing_branch(self):
        b1 = make_branch("feat/a")
        b2 = make_branch("feat/b")
        stack = StackView(base="main", branches=[b1, b2])
        assert stack.index_of("feat/a") == 0
        assert stack.index_of("feat/b") == 1

    def test_index_of_missing_branch(self):
        b1 = make_branch("feat/a")
        stack = StackView(base="main", branches=[b1])
        assert stack.index_of("feat/x") is None


class TestLoadStackView:
    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=2)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_load_stack_view_with_pr(self, mock_get_pr, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/auth", "pr_number": 1, "revision": 1}],
        }
        mock_get_pr.return_value = {
            "ci_passing": True,
            "approved": True,
            "draft": False,
            "url": None,
        }

        stack = load_stack_view(Path("."))

        assert stack.base == "main"
        assert len(stack.branches) == 1
        assert stack.branches[0].name == "feat/auth"
        assert stack.branches[0].pr_number == 1
        assert stack.branches[0].ci_passing is True
        assert stack.branches[0].approved is True
        assert stack.branches[0].commits == 2

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=0)
    @patch("arc.dashboard.st.load")
    def test_load_stack_view_no_pr(self, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/draft", "pr_number": None, "revision": 1}],
        }

        stack = load_stack_view(Path("."))

        assert stack.branches[0].draft is True
        assert stack.branches[0].pr_number is None

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_blocker_reason_ci_failing(self, mock_get_pr, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/broken", "pr_number": 1, "revision": 1}],
        }
        mock_get_pr.return_value = {
            "ci_passing": False,
            "approved": False,
            "draft": False,
            "url": None,
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].blocker_reason == "CI failing"

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_blocker_reason_awaiting_review(self, mock_get_pr, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/pending", "pr_number": 1, "revision": 1}],
        }
        mock_get_pr.return_value = {
            "ci_passing": True,
            "approved": False,
            "draft": False,
            "url": None,
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].blocker_reason == "awaiting review"

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    def test_load_stack_view_draft_branch(self, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/wip", "pr_number": None, "revision": 1}],
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].draft is True
        assert stack.branches[0].blocker_reason is None

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_blocker_priority_ci_over_approval(self, mock_get_pr, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/broken", "pr_number": 1, "revision": 1}],
        }
        mock_get_pr.return_value = {
            "ci_passing": False,
            "approved": False,
            "draft": False,
            "url": None,
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].blocker_reason == "CI failing"

    @patch("arc.dashboard.git.current_branch", return_value="feat/api")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_auto_selects_current_git_branch(self, mock_get_pr, mock_load, _cc, _cb):
        """load_stack_view sets current_index to the current git branch."""
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/auth", "pr_number": 1, "revision": 1},
                {"name": "feat/api", "pr_number": 2, "revision": 1},
            ],
        }
        mock_get_pr.return_value = {
            "ci_passing": True,
            "approved": True,
            "draft": False,
            "url": None,
        }

        stack = load_stack_view(Path("."))
        assert stack.current_git_branch == "feat/api"
        assert stack.current_index == 1  # auto-selected feat/api

    @patch("arc.dashboard.git.current_branch", return_value="unrelated/branch")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    def test_current_index_stays_zero_when_branch_not_in_stack(self, mock_load, _cc, _cb):
        """If current git branch is not in the stack, stays at index 0."""
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/auth", "pr_number": None, "revision": 1}],
        }

        stack = load_stack_view(Path("."))
        assert stack.current_index == 0

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    def test_parent_base_set_correctly(self, mock_load, _cc, _cb):
        """First branch uses stack base; subsequent use previous branch as base."""
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/auth", "pr_number": None, "revision": 1},
                {"name": "feat/api", "pr_number": None, "revision": 1},
            ],
        }

        stack = load_stack_view(Path("."))
        assert stack.branches[0].base == "main"
        assert stack.branches[1].base == "feat/auth"


class TestSummaryWidget:
    def test_renders_loading_state(self):
        stack = StackView(base="main", branches=[])
        widget = SummaryWidget(stack, loading=True)
        output = widget.render()
        assert "loading" in output.lower()

    def test_renders_error_state(self):
        stack = StackView(base="main", branches=[])
        stack.error = "Not initialized — run 'arc init'"
        widget = SummaryWidget(stack, loading=False)
        output = widget.render()
        assert "arc init" in output

    def test_renders_branch_count(self):
        b1 = make_branch("feat/a")
        b2 = make_branch("feat/b", base="feat/a")
        stack = StackView(base="main", branches=[b1, b2])
        output = SummaryWidget(stack, loading=False).render()
        assert "2" in output

    def test_renders_pr_count(self):
        b1 = make_branch("feat/a", pr_number=1)
        b2 = make_branch("feat/b", base="feat/a", pr_number=2)
        stack = StackView(base="main", branches=[b1, b2])
        output = SummaryWidget(stack, loading=False).render()
        assert "PR" in output

    def test_renders_base_branch_name(self):
        stack = StackView(base="develop", branches=[])
        output = SummaryWidget(stack, loading=False).render()
        assert "develop" in output


class TestBranchTreeWidget:
    def test_renders_empty_stack_hint(self):
        stack = StackView(base="main", branches=[])
        output = BranchTreeWidget(stack).render()
        assert "empty" in output.lower() or "arc new" in output

    def test_renders_branch_names(self):
        b1 = make_branch("feat/auth", pr_number=1, ci_passing=True, approved=True, draft=False)
        b2 = make_branch("feat/api", base="feat/auth")
        stack = StackView(base="main", branches=[b1, b2])
        output = BranchTreeWidget(stack).render()
        assert "feat/auth" in output
        assert "feat/api" in output

    def test_marks_selected_branch_with_cursor(self):
        b1 = make_branch("feat/a")
        b2 = make_branch("feat/b", base="feat/a")
        stack = StackView(base="main", branches=[b1, b2], current_index=1)
        output = BranchTreeWidget(stack).render()
        assert "▶" in output

    def test_marks_current_git_branch_with_head(self):
        b1 = make_branch("feat/a")
        b2 = make_branch("feat/b", base="feat/a")
        stack = StackView(base="main", branches=[b1, b2], current_git_branch="feat/b")
        output = BranchTreeWidget(stack).render()
        assert "HEAD" in output

    def test_warns_when_current_branch_not_in_stack(self):
        b1 = make_branch("feat/a")
        stack = StackView(base="main", branches=[b1], current_git_branch="hotfix/x")
        output = BranchTreeWidget(stack).render()
        assert "hotfix/x" in output
        assert "arc add" in output

    def test_shows_commit_count(self):
        b1 = make_branch("feat/a", commits=3)
        stack = StackView(base="main", branches=[b1])
        output = BranchTreeWidget(stack).render()
        assert "3c" in output

    def test_shows_base_branch_at_top(self):
        b1 = make_branch("feat/a")
        stack = StackView(base="develop", branches=[b1])
        output = BranchTreeWidget(stack).render()
        assert "develop" in output

    def test_shows_status_icon_in_row(self):
        b1 = make_branch("feat/a", pr_number=1, ci_passing=True, approved=True, draft=False)
        stack = StackView(base="main", branches=[b1])
        output = BranchTreeWidget(stack).render()
        assert "✓" in output


class TestDetailWidget:
    def test_renders_empty_when_no_branch(self):
        stack = StackView(base="main", branches=[])
        output = DetailWidget(stack).render()
        assert output == ""

    def test_renders_branch_name(self):
        b = make_branch("feat/auth")
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "feat/auth" in output

    def test_renders_pr_number(self):
        b = make_branch("feat/auth", pr_number=42, draft=False, base="main")
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "#42" in output

    def test_renders_pr_url(self):
        b = make_branch(
            "feat/auth",
            pr_number=42,
            pr_url="https://github.com/org/repo/pull/42",
            draft=False,
        )
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "github.com" in output

    def test_renders_commit_count(self):
        b = make_branch("feat/auth", commits=5)
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "5" in output

    def test_renders_no_pr_hint(self):
        b = make_branch("feat/auth", pr_number=None)
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "arc push" in output or "none" in output.lower()

    def test_renders_ci_passing(self):
        b = make_branch("feat/auth", pr_number=1, ci_passing=True, draft=False)
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "passing" in output

    def test_renders_ci_failing(self):
        b = make_branch("feat/auth", pr_number=1, ci_passing=False, draft=False)
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "failing" in output

    def test_renders_base_branch(self):
        b = make_branch("feat/api", base="feat/auth")
        stack = StackView(base="main", branches=[b])
        output = DetailWidget(stack).render()
        assert "feat/auth" in output


class TestDashboardIntegration:
    @patch("arc.dashboard.git.current_branch", return_value="feat/ui")
    @patch("arc.dashboard.git.commit_count", return_value=1)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_full_dashboard_workflow(self, mock_get_pr, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [
                {"name": "feat/auth", "pr_number": 1, "revision": 1},
                {"name": "feat/api", "pr_number": 2, "revision": 2},
                {"name": "feat/ui", "pr_number": None, "revision": 1},
            ],
        }
        mock_get_pr.side_effect = [
            {"ci_passing": True, "approved": True, "draft": False, "url": None},
            {"ci_passing": True, "approved": False, "draft": False, "url": None},
        ]

        stack = load_stack_view(Path("."))

        assert len(stack.branches) == 3
        assert stack.base == "main"
        assert stack.current_git_branch == "feat/ui"
        assert stack.current_index == 2  # auto-selected feat/ui

        assert stack.branches[0].name == "feat/auth"
        assert stack.branches[0].status_icon == "✓"
        assert stack.branches[0].blocker_reason is None

        assert stack.branches[1].name == "feat/api"
        assert stack.branches[1].blocker_reason == "awaiting review"

        assert stack.branches[2].name == "feat/ui"
        assert stack.branches[2].draft is True

    def test_navigation_between_branches(self):
        b1 = make_branch("feat/a", pr_number=1, ci_passing=True, approved=True, draft=False)
        b2 = make_branch("feat/b", pr_number=2, base="feat/a")
        b3 = make_branch("feat/c", base="feat/b")

        stack = StackView(base="main", branches=[b1, b2, b3], current_index=0)

        stack.move_selection(1)
        assert stack.current_branch == b2

        stack.move_selection(1)
        assert stack.current_branch == b3

        stack.move_selection(-1)
        assert stack.current_branch == b2

    @patch("arc.dashboard.git.current_branch", return_value="")
    @patch("arc.dashboard.git.commit_count", return_value=2)
    @patch("arc.dashboard.st.load")
    @patch("arc.dashboard.github.get_pr_status")
    def test_widget_rendering_with_data(self, mock_get_pr, mock_load, _cc, _cb):
        mock_load.return_value = {
            "base": "main",
            "branches": [{"name": "feat/auth", "pr_number": 1, "revision": 1}],
        }
        mock_get_pr.return_value = {
            "ci_passing": True,
            "approved": True,
            "draft": False,
            "url": None,
        }

        stack = load_stack_view(Path("."))

        tree_output = BranchTreeWidget(stack).render()
        assert "feat/auth" in tree_output
        assert "✓" in tree_output

        detail_output = DetailWidget(stack).render()
        assert "feat/auth" in detail_output
        assert "#1" in detail_output
        assert "passing" in detail_output
