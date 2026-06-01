from unittest.mock import patch, MagicMock, Mock
from arc import git, github


def mock_result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = stderr
    return r


def test_branch_exists_remote_returns_true():
    """Branch exists on remote."""
    with patch("arc.git._run", return_value=mock_result("origin/test-branch\n")) as m:
        assert git.branch_exists_remote("test-branch") is True
        # Verify the correct git command was constructed
        m.assert_called_once_with(["git", "branch", "-r", "--list", "origin/test-branch"], check=False)


def test_branch_exists_remote_returns_false():
    """Branch does not exist on remote."""
    with patch("arc.git._run", return_value=mock_result("", returncode=0)) as m:
        assert git.branch_exists_remote("test-branch") is False
        # Verify the correct git command was constructed
        m.assert_called_once_with(["git", "branch", "-r", "--list", "origin/test-branch"], check=False)


def test_update_pr_base_changes_base_branch():
    """Update PR base branch via gh CLI."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="")

        result = github.update_pr_base(10, "main")

        # Verify gh pr edit was called
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args
        assert "pr" in args
        assert "edit" in args
        assert "10" in args
        assert "--base" in args
        assert "main" in args


def test_update_pr_base_returns_true_on_success():
    """Returns True if gh command succeeds."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)
        assert github.update_pr_base(10, "main") is True


def test_update_pr_base_returns_false_on_failure():
    """Returns False if gh command fails."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=1)
        assert github.update_pr_base(10, "main") is False
