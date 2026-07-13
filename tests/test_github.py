import json
from unittest.mock import MagicMock, patch

import pytest

from arc import github
from arc.exceptions import GitHubError


def mock_result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = stderr
    return r


def test_is_installed_true():
    with patch("arc.github._run", return_value=mock_result("gh version 2.0\n")):
        assert github.is_installed() is True


def test_is_installed_false():
    with patch("arc.github._run", return_value=mock_result(returncode=1)):
        assert github.is_installed() is False


def test_is_authenticated_true():
    with patch("arc.github._run", return_value=mock_result(returncode=0)):
        assert github.is_authenticated() is True


def test_is_authenticated_false():
    with patch("arc.github._run", return_value=mock_result(returncode=1)):
        assert github.is_authenticated() is False


def test_get_pr_returns_none_when_missing():
    stderr = 'no pull requests found for branch "feat/auth"'
    with patch("arc.github._run", return_value=mock_result(returncode=1, stderr=stderr)):
        assert github.get_pr("feat/auth") is None


def test_get_pr_raises_on_unexpected_failure():
    """A transient/auth gh failure must not be silently treated as 'no PR' —
    that ambiguity previously let `arc submit` attempt to create a duplicate
    PR for a branch that already had one, if `gh pr view` failed for any
    reason other than the branch genuinely having no PR."""
    with patch(
        "arc.github._run",
        return_value=mock_result(returncode=1, stderr="error: authentication required (401)"),
    ):
        with pytest.raises(GitHubError):
            github.get_pr("feat/auth")


def test_get_pr_returns_data():
    payload = {
        "number": 42,
        "url": "https://gh/42",
        "state": "OPEN",
        "baseRefName": "main",
        "mergedAt": None,
    }
    with patch("arc.github._run", return_value=mock_result(json.dumps(payload))):
        result = github.get_pr("feat/auth")
    assert result["number"] == 42
    assert result["state"] == "OPEN"


def test_pr_is_merged_true():
    payload = {"state": "MERGED"}
    with patch("arc.github._run", return_value=mock_result(json.dumps(payload))):
        assert github.pr_is_merged(42) is True


def test_pr_is_merged_false():
    payload = {"state": "OPEN"}
    with patch("arc.github._run", return_value=mock_result(json.dumps(payload))):
        assert github.pr_is_merged(42) is False


def test_pr_is_merged_returns_false_on_api_error():
    with patch("arc.github._run", return_value=mock_result(returncode=1)):
        assert github.pr_is_merged(42) is False


def test_get_merge_commit_sha_returns_none_when_not_merged():
    payload = {"mergeCommit": None}
    with patch("arc.github._run", return_value=mock_result(json.dumps(payload))):
        assert github.get_merge_commit_sha(42) is None


def test_get_merge_commit_sha_returns_sha():
    payload = {"mergeCommit": {"oid": "abc123"}}
    with patch("arc.github._run", return_value=mock_result(json.dumps(payload))):
        assert github.get_merge_commit_sha(42) == "abc123"


def test_update_pr_body_calls_gh():
    with patch("arc.github._run") as mock_run:
        mock_run.return_value = mock_result()
        github.update_pr_body(42, "new body")
    mock_run.assert_called_once_with(["gh", "pr", "edit", "42", "--body", "new body"])


def test_mark_pr_ready_calls_gh():
    """Old test: ensure gh pr ready is called when PR is in draft."""
    with patch("arc.github._run") as mock_run:
        # First call: PR is in draft (isDraft=True)
        # Second call: mark as ready succeeds
        mock_run.side_effect = [mock_result(json.dumps({"isDraft": True})), mock_result()]
        github.mark_pr_ready(42)

    # Verify gh pr ready was called (second call)
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[1][0] == (["gh", "pr", "ready", "42"],)


def test_mark_pr_ready_skips_when_already_ready():
    """PR is already ready (isDraft=False), should skip gh pr ready call."""
    with patch("arc.github._run") as mock_run:
        # First call: check PR status returns isDraft=False
        mock_run.return_value = mock_result(json.dumps({"isDraft": False}))
        github.mark_pr_ready(42)

    # Should have called _run once (to check isDraft), not twice
    mock_run.assert_called_once_with(["gh", "pr", "view", "42", "--json", "isDraft"], check=False)


def test_mark_pr_ready_calls_when_in_draft():
    """PR is in draft (isDraft=True), should call gh pr ready."""
    with patch("arc.github._run") as mock_run:
        # First call: check PR status returns isDraft=True
        # Second call: mark as ready returns success
        mock_run.side_effect = [mock_result(json.dumps({"isDraft": True})), mock_result()]
        github.mark_pr_ready(42)

    # Should have called _run twice: once to check, once to mark ready
    assert mock_run.call_count == 2
    calls = mock_run.call_args_list
    assert calls[0][0] == (["gh", "pr", "view", "42", "--json", "isDraft"],)
    assert calls[1][0] == (["gh", "pr", "ready", "42"],)
    assert calls[1][1] == {"check": False}


def test_create_issue_calls_gh_api():
    """Test that create_issue calls gh api and returns parsed result."""
    with patch("arc.github._run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/<OWNER>/<REPO>/issues/42\n"
        )
        result = github.create_issue(title="Bug Report", body="Description here")

        assert result is not None
        assert result["number"] == 42
        assert "github.com" in result["html_url"]
        assert "<OWNER>" in result["html_url"]  # Matches mock output


def test_create_issue_targets_arc_repo_not_cwd_repo():
    """create_issue must always target arc's own repo, regardless of which
    repo the user is currently running `arc` in (--repo must be explicit,
    otherwise gh infers the repo from the cwd's git remote)."""
    with patch("arc.github._run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/owner/repo/issues/42\n"
        )
        github.create_issue(title="Bug Report", body="Description here")

        args = mock_run.call_args[0][0]
        assert "--repo" in args
        assert args[args.index("--repo") + 1] == github.ARC_REPO


def test_create_issue_returns_none_on_failure():
    """Test that create_issue returns None on API error."""
    with patch("arc.github._run") as mock_run:
        mock_run.side_effect = Exception("API error")
        result = github.create_issue(title="Bug", body="Description")
        assert result is None


def test_create_issue_returns_none_on_nonzero_exit():
    """Test that create_issue returns None if gh command fails."""
    with patch("arc.github._run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = github.create_issue(title="Bug", body="Description")
        assert result is None


def test_get_pr_status_parses_approved_and_ci(monkeypatch):
    import json as _json
    import subprocess

    payload = {
        "isDraft": False,
        "reviewDecision": "APPROVED",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "mergeQueueEntry": {"position": 1},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type(
            "R", (), {"returncode": 0, "stdout": _json.dumps(payload), "stderr": ""}
        )(),
    )
    from arc.github import get_pr_status

    s = get_pr_status(42)
    assert s["approved"] is True
    assert s["ci_passing"] is True
    assert s["in_merge_queue"] is True


def test_get_pr_status_safe_defaults_on_failure(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
    )
    from arc.github import get_pr_status

    s = get_pr_status(42)
    assert s == {"approved": False, "ci_passing": None, "draft": False, "in_merge_queue": False}


# VCR Cassette PII Masking Tests


def test_mask_cassette_pii_emails(tmp_path):
    """Test that email addresses are masked."""
    from tests.conftest import mask_cassette_pii

    cassette = tmp_path / "test.yaml"
    cassette.write_text("user: alice@example.com, contact: bob.smith@test.org")

    mask_cassette_pii(str(cassette))
    content = cassette.read_text()

    assert "<EMAIL>" in content
    assert "alice@example.com" not in content
    assert "bob.smith@test.org" not in content


def test_mask_cassette_pii_tokens(tmp_path):
    """Test that GitHub tokens are masked."""
    from tests.conftest import mask_cassette_pii

    cassette = tmp_path / "test.yaml"
    cassette.write_text("token: ghp_abc123def456ghi789jkl012mno3456")

    mask_cassette_pii(str(cassette))
    content = cassette.read_text()

    assert "<GH_TOKEN>" in content
    assert "ghp_abc123def456ghi789jkl012mno3456" not in content


def test_mask_cassette_pii_login(tmp_path):
    """Test that login names are masked."""
    from tests.conftest import mask_cassette_pii

    cassette = tmp_path / "test.yaml"
    cassette.write_text('"login": "yash-srivastava19"')

    mask_cassette_pii(str(cassette))
    content = cassette.read_text()

    assert "<USERNAME>" in content
    assert "yash-srivastava19" not in content


def test_mask_cassette_pii_user_ids(tmp_path):
    """Test that user IDs are masked."""
    from tests.conftest import mask_cassette_pii

    cassette = tmp_path / "test.yaml"
    cassette.write_text('"id": 123456789')

    mask_cassette_pii(str(cassette))
    content = cassette.read_text()

    assert "<USER_ID>" in content
    assert "123456789" not in content


def test_mask_cassette_pii_home_paths(tmp_path):
    """Test that home directory paths are masked."""
    from tests.conftest import mask_cassette_pii

    cassette = tmp_path / "test.yaml"
    cassette.write_text("path: /home/yashs/Desktop/repo")

    mask_cassette_pii(str(cassette))
    content = cassette.read_text()

    assert "<HOME_PATH>" in content
    assert "/home/yashs/Desktop/repo" not in content
