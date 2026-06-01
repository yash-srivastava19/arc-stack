from unittest.mock import patch, MagicMock, Mock
import subprocess
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

        # Verify the exact command and all arguments
        mock_run.assert_called_once_with(
            ["gh", "pr", "edit", "10", "--base", "main"],
            capture_output=True,
            text=True,
            timeout=10
        )


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


def test_update_pr_base_returns_false_on_exception():
    """Returns False if subprocess raises an exception."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("gh", 10)
        assert github.update_pr_base(10, "main") is False
