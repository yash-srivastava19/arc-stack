from unittest.mock import MagicMock, patch

import pytest

from arc import git


def mock_result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = stderr
    return r


def test_is_installed_true():
    with patch("arc.git._run", return_value=mock_result("git version 2.0\n")):
        assert git.is_installed() is True


def test_is_installed_false():
    with patch("arc.git._run", return_value=mock_result(returncode=1)):
        assert git.is_installed() is False


def test_current_branch():
    with patch("arc.git._run", return_value=mock_result("feat/auth\n")) as m:
        assert git.current_branch() == "feat/auth"
    m.assert_called_once_with(["git", "rev-parse", "--abbrev-ref", "HEAD"])


def test_branch_exists_true():
    with patch("arc.git._run", return_value=mock_result("feat/auth\n")):
        assert git.branch_exists("feat/auth") is True


def test_branch_exists_false():
    with patch("arc.git._run", return_value=mock_result("")):
        assert git.branch_exists("feat/auth") is False


def test_get_sha():
    with patch("arc.git._run", return_value=mock_result("abc123\n")):
        assert git.get_sha("HEAD") == "abc123"


def test_commit_count():
    with patch("arc.git._run", return_value=mock_result("3\n")):
        assert git.commit_count("main", "feat/auth") == 3


def test_is_ancestor_true():
    with patch("arc.git._run", return_value=mock_result(returncode=0)):
        assert git.is_ancestor("main", "feat/auth") is True


def test_is_ancestor_false():
    with patch("arc.git._run", return_value=mock_result(returncode=1)):
        assert git.is_ancestor("main", "feat/auth") is False


def test_get_commit_subject():
    with patch("arc.git._run", return_value=mock_result("Add auth middleware\n")):
        assert git.get_commit_subject() == "Add auth middleware"


def test_get_commit_body():
    with patch("arc.git._run", return_value=mock_result("Some details\n")):
        assert git.get_commit_body() == "Some details"


def test_get_commit_message():
    with patch("arc.git._run", return_value=mock_result("Subject\n\nBody\n")):
        assert git.get_commit_message() == "Subject\n\nBody"


def test_conflicted_files():
    output = "UU src/auth.py\nUU src/api.py\n"
    with patch("arc.git._run", return_value=mock_result(output)):
        files = git.conflicted_files()
    assert files == ["src/auth.py", "src/api.py"]


def test_conflicted_files_empty():
    with patch("arc.git._run", return_value=mock_result("")):
        assert git.conflicted_files() == []


def test_find_repo_root(tmp_path):
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "deep"
    subdir.mkdir()
    result = git.find_repo_root(subdir)
    assert result == tmp_path


def test_find_repo_root_raises(tmp_path):
    with pytest.raises(RuntimeError, match="Not in a git repository"):
        git.find_repo_root(tmp_path)


@pytest.mark.git
def test_git_repo_fixture_has_real_git(git_repo):
    import subprocess

    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "init" in result.stdout


@pytest.mark.git
def test_changed_files_between_returns_modified_files(git_repo):
    import subprocess

    subprocess.run(
        ["git", "checkout", "-b", "feat/a"], cwd=git_repo, check=True, capture_output=True
    )
    (git_repo / "api.py").write_text("def hello(): pass")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add api"], cwd=git_repo, check=True, capture_output=True
    )
    from arc.git import changed_files_between

    assert "api.py" in changed_files_between(git_repo, "main", "feat/a")


@pytest.mark.git
def test_is_squash_merged_true_when_changes_in_base(git_repo):
    import subprocess

    subprocess.run(
        ["git", "checkout", "-b", "feat/a"], cwd=git_repo, check=True, capture_output=True
    )
    (git_repo / "api.py").write_text("squashed")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add api"], cwd=git_repo, check=True, capture_output=True
    )
    subprocess.run(["git", "checkout", "main"], cwd=git_repo, check=True, capture_output=True)
    (git_repo / "api.py").write_text("squashed")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "squash feat/a"], cwd=git_repo, check=True, capture_output=True
    )
    from arc.git import is_squash_merged

    assert is_squash_merged(git_repo, "feat/a", "main") is True


@pytest.mark.git
def test_is_squash_merged_false_when_unique_commits(git_repo):
    import subprocess

    subprocess.run(
        ["git", "checkout", "-b", "feat/a"], cwd=git_repo, check=True, capture_output=True
    )
    (git_repo / "api.py").write_text("unique")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add api"], cwd=git_repo, check=True, capture_output=True
    )
    from arc.git import is_squash_merged

    assert is_squash_merged(git_repo, "feat/a", "main") is False
