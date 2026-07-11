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


def test_force_update_branch():
    with patch("arc.git._run", return_value=mock_result()) as m:
        git.force_update_branch("arc-tip", "abc123")
    m.assert_called_once_with(["git", "branch", "-f", "arc-tip", "abc123"])


def test_checkout_branch_at():
    with patch("arc.git._run", return_value=mock_result()) as m:
        git.checkout_branch_at("arc-tip", "abc123")
    m.assert_called_once_with(["git", "checkout", "-B", "arc-tip", "abc123"])


def test_remote_ahead_count_positive():
    with patch("arc.git._run", return_value=mock_result("3\n")) as m:
        assert git.remote_ahead_count("main") == 3
    m.assert_called_once_with(["git", "rev-list", "--count", "main..origin/main"], check=False)


def test_remote_ahead_count_zero_when_up_to_date():
    with patch("arc.git._run", return_value=mock_result("0\n")):
        assert git.remote_ahead_count("main") == 0


def test_remote_ahead_count_zero_when_no_remote_ref():
    with patch("arc.git._run", return_value=mock_result(returncode=1)):
        assert git.remote_ahead_count("main") == 0


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


@pytest.mark.git
def test_get_staged_files_empty(git_repo):
    import os

    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        assert git.get_staged_files() == []
    finally:
        os.chdir(orig)


@pytest.mark.git
def test_get_staged_files_with_staged(git_repo):
    import os
    import subprocess

    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        (git_repo / "new.py").write_text("x = 1")
        subprocess.run(["git", "add", "new.py"], cwd=git_repo, check=True, capture_output=True)
        assert "new.py" in git.get_staged_files()
    finally:
        os.chdir(orig)


@pytest.mark.git
def test_amend_staged_no_edit(git_repo):
    import os
    import subprocess

    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        old_sha = git.get_sha("HEAD")
        (git_repo / "new.py").write_text("x = 1")
        subprocess.run(["git", "add", "new.py"], cwd=git_repo, check=True, capture_output=True)
        git.amend_staged()
        new_sha = git.get_sha("HEAD")
        assert new_sha != old_sha
    finally:
        os.chdir(orig)


@pytest.mark.git
def test_diff_stat_returns_correct_counts(git_repo):
    import os
    import subprocess

    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        old_sha = git.get_sha("HEAD")
        (git_repo / "a.py").write_text("line1\nline2\n")
        subprocess.run(["git", "add", "a.py"], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add a"], cwd=git_repo, check=True, capture_output=True
        )
        new_sha = git.get_sha("HEAD")
        stat = git.diff_stat(old_sha, new_sha)
        assert "a.py" in stat["files_changed"]
        assert stat["insertions"] == 2
        assert stat["deletions"] == 0
    finally:
        os.chdir(orig)


@pytest.mark.git
def test_is_mid_rebase_false_when_clean(git_repo):
    assert git.is_mid_rebase(git_repo) is False


@pytest.mark.git
def test_reset_branch_to_other_branch(git_repo):
    import os
    import subprocess

    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        old_sha = git.get_sha("HEAD")
        (git_repo / "b.py").write_text("y = 2")
        subprocess.run(["git", "add", "b.py"], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add b"], cwd=git_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "tmp-branch"], cwd=git_repo, check=True, capture_output=True
        )
        git.reset_branch_to("main", old_sha)
        subprocess.run(["git", "checkout", "main"], cwd=git_repo, check=True, capture_output=True)
        assert git.get_sha("HEAD") == old_sha
    finally:
        os.chdir(orig)


@pytest.mark.git
def test_checkout_branch_at_works_when_already_on_that_branch(git_repo):
    import os

    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        first_sha = git.get_sha("main")
        git.checkout_branch_at("arc-tip", first_sha)
        assert git.current_branch() == "arc-tip"

        # Make a new commit on main so there's a different SHA to move to.
        (git_repo / "new.txt").write_text("x")
        import subprocess

        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], check=True, capture_output=True)
        second_sha = git.get_sha("main")

        # This is the exact call that crashed before the fix: force-moving
        # arc-tip while it's the currently checked-out branch.
        git.checkout_branch_at("arc-tip", second_sha)
        assert git.current_branch() == "arc-tip"
        assert git.get_sha("arc-tip") == second_sha
    finally:
        os.chdir(orig)
