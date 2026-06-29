import subprocess
from unittest.mock import MagicMock, Mock, patch

from arc import git, github
from arc.commands.sync import detect_merged_branches, retarget_dependent_prs


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
        m.assert_called_once_with(
            ["git", "branch", "-r", "--list", "origin/test-branch"], check=False
        )


def test_branch_exists_remote_returns_false():
    """Branch does not exist on remote."""
    with patch("arc.git._run", return_value=mock_result("", returncode=0)) as m:
        assert git.branch_exists_remote("test-branch") is False
        # Verify the correct git command was constructed
        m.assert_called_once_with(
            ["git", "branch", "-r", "--list", "origin/test-branch"], check=False
        )


def test_update_pr_base_changes_base_branch():
    """Update PR base branch via gh CLI."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="")

        github.update_pr_base(10, "main")

        # Verify the exact command and all arguments
        mock_run.assert_called_once_with(
            ["gh", "pr", "edit", "10", "--base", "main"], capture_output=True, text=True, timeout=10
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


def test_detect_merged_branches_finds_merged_prs():
    """Find branches whose PR was actually merged on GitHub."""
    state = {
        "base": "main",
        "branches": [
            {"name": "feature-1", "pr_number": 1, "revision": 1},
            {"name": "feature-2", "pr_number": 2, "revision": 1},
        ],
    }

    with patch("arc.github.pr_is_merged") as mock_merged:
        # feature-1's PR merged, feature-2's PR still open
        mock_merged.side_effect = [True, False]

        merged = detect_merged_branches(state)

        assert merged == {"feature-1"}


def test_detect_merged_branches_ignores_unpushed():
    """Branches without a PR number (e.g. created but not submitted) are never merged."""
    state = {
        "base": "main",
        "branches": [
            {"name": "feature-1", "pr_number": None, "revision": 0},
            {"name": "feature-2", "pr_number": 2, "revision": 1},
        ],
    }

    with patch("arc.github.pr_is_merged") as mock_merged:
        mock_merged.return_value = False

        merged = detect_merged_branches(state)

        # feature-1 has no PR, so pr_is_merged is not consulted for it
        assert merged == set()
        mock_merged.assert_called_once_with(2)


def test_retarget_dependent_prs_updates_base():
    """Retarget PRs whose base was merged."""
    state = {
        "base": "main",
        "branches": [
            {"name": "feature-1", "pr_number": 1, "revision": 1},
            {"name": "feature-2", "pr_number": 2, "revision": 1},
            {"name": "feature-3", "pr_number": 3, "revision": 1},
        ],
    }

    with patch("arc.github.update_pr_base") as mock_update:
        mock_update.return_value = True

        retarget_dependent_prs(state, {"feature-1"}, quiet=True)

        # Only PR #2 should be retargeted (feature-2's base was feature-1)
        mock_update.assert_called_once_with(2, "main")


def test_retarget_dependent_prs_prunes_merged_from_state():
    """Merged branches are removed from the returned state to avoid re-detection."""
    state = {
        "base": "main",
        "branches": [
            {"name": "feature-1", "pr_number": 1, "revision": 1},
            {"name": "feature-2", "pr_number": 2, "revision": 1},
        ],
    }

    with patch("arc.github.update_pr_base", return_value=True):
        new_state = retarget_dependent_prs(state, {"feature-1"}, quiet=True)

    names = [b["name"] for b in new_state["branches"]]
    assert names == ["feature-2"]


def test_retarget_dependent_prs_prints_status():
    """Print status message for each retargeted PR."""
    state = {
        "base": "main",
        "branches": [
            {"name": "feature-1", "pr_number": 1, "revision": 1},
            {"name": "feature-2", "pr_number": 2, "revision": 1},
        ],
    }

    with patch("arc.github.update_pr_base") as mock_update:
        mock_update.return_value = True

        with patch("arc.cli.err.print") as mock_print:
            retarget_dependent_prs(state, {"feature-1"}, quiet=False)

            # Verify status message was printed
            mock_print.assert_called_once()
            call_args = mock_print.call_args[0][0]
            assert "Retargeted PR #2 to main" in call_args


def test_sync_prunes_merged_branch_from_stack(arc_root, monkeypatch):
    """arc sync removes merged branches from stack state automatically."""
    from arc import git as _git
    from arc.state import load as _load
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [
                {"name": "release/v030", "pr_number": 25, "revision": 1},
                {"name": "feat/next", "pr_number": 27, "revision": 1},
            ],
        },
    )
    monkeypatch.setattr(_git, "fetch", lambda remote="origin": None)
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/next")
    monkeypatch.setattr(_git, "is_ancestor", lambda a, b: True)
    monkeypatch.setattr(_git, "rebase_fork_point", lambda onto: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(_git, "checkout", lambda b: None)
    monkeypatch.setattr(_git, "is_squash_merged", lambda root, branch, base: False)
    monkeypatch.setattr(_git, "branch_exists", lambda b: True)
    monkeypatch.setattr(_git, "get_sha", lambda ref: "abc123")
    monkeypatch.setattr(_git, "commit_count", lambda base, branch: 1)
    from arc import conflicts as _c

    monkeypatch.setattr(_c, "predict_conflicts", lambda d, r: [])
    # release/v030 PR is merged; feat/next is open
    import arc.github as _gh

    monkeypatch.setattr(_gh, "pr_is_merged", lambda n: n == 25)
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["sync", "-q"])
    assert result.exit_code == 0
    data = _load(arc_root)
    names = [b["name"] for b in data["branches"]]
    assert "release/v030" not in names
    assert "feat/next" in names
