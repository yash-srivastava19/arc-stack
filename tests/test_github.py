import json
from unittest.mock import patch, MagicMock
from arc import github


def mock_result(stdout="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
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
    with patch("arc.github._run", return_value=mock_result(returncode=1)):
        assert github.get_pr("feat/auth") is None


def test_get_pr_returns_data():
    payload = {"number": 42, "url": "https://gh/42", "state": "OPEN",
               "baseRefName": "main", "mergedAt": None}
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
    with patch("arc.github._run") as mock_run:
        mock_run.return_value = mock_result()
        github.mark_pr_ready(42)
    mock_run.assert_called_once_with(["gh", "pr", "ready", "42"])


def test_create_issue_calls_gh_api():
    """Test that create_issue calls gh api and returns parsed result."""
    with patch("arc.github._run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='https://github.com/<OWNER>/<REPO>/issues/42\n'
        )
        result = github.create_issue(title="Bug Report", body="Description here")

        assert result is not None
        assert result["number"] == 42
        assert "github.com" in result["html_url"]
        assert "<OWNER>" in result["html_url"]  # Matches mock output


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
