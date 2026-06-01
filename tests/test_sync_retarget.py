from unittest.mock import patch, MagicMock
from arc import git


def mock_result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = stderr
    return r


def test_branch_exists_remote_returns_true():
    """Branch exists on remote."""
    with patch("arc.git._run", return_value=mock_result("origin/test-branch\n")):
        assert git.branch_exists_remote("test-branch") is True


def test_branch_exists_remote_returns_false():
    """Branch does not exist on remote."""
    with patch("arc.git._run", return_value=mock_result("", returncode=0)):
        assert git.branch_exists_remote("test-branch") is False
