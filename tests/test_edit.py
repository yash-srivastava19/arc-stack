"""Tests for arc edit command."""

import json
import os as _os

import pytest


def test_edit_state_roundtrip(tmp_path):
    from arc.commands.edit import (
        _clear_edit_state,
        _edit_state_path,
        _EditState,
        _load_edit_state,
        _save_edit_state,
    )

    (tmp_path / ".arc").mkdir()
    state: _EditState = {
        "branch": "feat/auth",
        "mode": "staged",
        "original_sha": "abc1234",
        "amended_sha": "def5678",
        "to_restack": ["feat/api", "feat/tests"],
        "restacked": [],
        "original_shas": {"feat/auth": "abc1234", "feat/api": "ghi0001", "feat/tests": "jkl0002"},
        "started_at": "2026-06-17T10:00:00Z",
    }
    _save_edit_state(tmp_path, state)
    assert _edit_state_path(tmp_path).exists()
    loaded = _load_edit_state(tmp_path)
    assert loaded == state
    _clear_edit_state(tmp_path)
    assert _load_edit_state(tmp_path) is None


def test_load_edit_state_returns_none_when_absent(tmp_path):
    from arc.commands.edit import _load_edit_state

    (tmp_path / ".arc").mkdir()
    assert _load_edit_state(tmp_path) is None


def test_detect_mode_message_when_flag_and_clean_index():
    from unittest.mock import patch

    from arc.commands.edit import _detect_mode

    with patch("arc.commands.edit.git.get_staged_files", return_value=[]):
        assert _detect_mode(message="fix typo", interactive=False) == "message"


def test_detect_mode_staged_when_files_staged():
    from unittest.mock import patch

    from arc.commands.edit import _detect_mode

    with patch("arc.commands.edit.git.get_staged_files", return_value=["auth.py"]):
        assert _detect_mode(message=None, interactive=False) == "staged"


def test_detect_mode_staged_overrides_message_when_files_staged():
    from unittest.mock import patch

    from arc.commands.edit import _detect_mode

    with patch("arc.commands.edit.git.get_staged_files", return_value=["auth.py"]):
        assert _detect_mode(message="new message", interactive=False) == "staged"


def test_detect_mode_interactive():
    from unittest.mock import patch

    from arc.commands.edit import _detect_mode

    with patch("arc.commands.edit.git.get_staged_files", return_value=[]):
        assert _detect_mode(message=None, interactive=True) == "interactive"


@pytest.mark.git
def test_get_amendment_summary_shape(git_repo):
    import os
    import subprocess as sp

    from arc.commands.edit import _get_amendment_summary

    old_sha = sp.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True
    ).stdout.strip()
    (git_repo / "x.py").write_text("a = 1\nb = 2\n")
    sp.run(["git", "add", "x.py"], cwd=git_repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "add x"], cwd=git_repo, check=True, capture_output=True)
    new_sha = sp.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True
    ).stdout.strip()
    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        summary = _get_amendment_summary(old_sha, new_sha)
    finally:
        os.chdir(orig)
    assert "x.py" in summary["files_changed"]
    assert summary["insertions"] == 2
    assert isinstance(summary["deletions"], int)


def _run_edit(args, cwd=None):
    """Invoke edit_cmd via CliRunner, changing cwd if specified."""
    from click.testing import CliRunner

    from arc.commands.edit import edit_cmd

    runner = CliRunner()
    orig = _os.getcwd()
    if cwd:
        _os.chdir(cwd)
    try:
        result = runner.invoke(edit_cmd, args, catch_exceptions=False)
    finally:
        _os.chdir(orig)
    return result


@pytest.mark.git
def test_edit_fails_with_nothing_to_amend(arc_stack):
    from unittest.mock import patch

    with patch("arc.commands.edit.git.get_staged_files", return_value=[]):
        with patch("arc.commands.edit.git.find_repo_root", return_value=arc_stack):
            with patch("arc.commands.edit.git.is_mid_rebase", return_value=False):
                with patch("arc.commands.edit.git.current_branch", return_value="main"):
                    result = _run_edit(["--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["ok"] is False
    assert "nothing to amend" in data["error"]


@pytest.mark.git
def test_edit_fails_when_interactive_and_message(arc_stack):
    from unittest.mock import patch

    with patch("arc.commands.edit.git.find_repo_root", return_value=arc_stack):
        with patch("arc.commands.edit.git.is_mid_rebase", return_value=False):
            result = _run_edit(["--interactive", "--message", "fix", "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert "mutually exclusive" in data["error"]


@pytest.mark.git
def test_edit_fails_when_mid_rebase(arc_stack):
    from unittest.mock import patch

    with patch("arc.commands.edit.git.find_repo_root", return_value=arc_stack):
        with patch("arc.commands.edit.git.is_mid_rebase", return_value=True):
            result = _run_edit(["--message", "fix", "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert "mid-rebase" in data["error"]


@pytest.mark.git
def test_edit_continue_fails_when_no_state(arc_stack):
    from unittest.mock import patch

    with patch("arc.commands.edit.git.find_repo_root", return_value=arc_stack):
        result = _run_edit(["--continue", "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert "no edit in progress" in data["error"]


@pytest.mark.git
def test_edit_message_only_no_upstack(arc_stack):
    """arc edit --message on a branch with no upstack branches."""
    import subprocess as sp

    root = arc_stack

    sp.run(["git", "checkout", "-b", "feat/auth"], cwd=root, check=True, capture_output=True)
    (root / "auth.py").write_text("def auth(): pass\n")
    sp.run(["git", "add", "auth.py"], cwd=root, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "original message"], cwd=root, check=True, capture_output=True)
    old_sha = sp.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()

    from arc import state as st

    data = st.init_state(base="main")
    data = st.add_branch(data, "feat/auth")
    st.save(root, data)

    orig = _os.getcwd()
    _os.chdir(root)
    result = _run_edit(["--message", "new message", "--no-push", "--json"])
    _os.chdir(orig)

    assert result.exit_code == 0, result.output
    data_out = json.loads(result.output)
    assert data_out["ok"] is True
    assert data_out["state"] == "done"
    assert data_out["mode"] == "message"
    assert data_out["old_sha"] == old_sha
    assert data_out["new_sha"] != old_sha
    assert data_out["restacked"] == []
    assert data_out["pushed"] == []  # --no-push


@pytest.mark.git
def test_edit_staged_content_no_upstack(arc_stack):
    """arc edit with staged changes on a branch with no upstack."""
    import subprocess as sp

    root = arc_stack

    sp.run(["git", "checkout", "-b", "feat/solo"], cwd=root, check=True, capture_output=True)
    (root / "solo.py").write_text("x = 1\n")
    sp.run(["git", "add", "solo.py"], cwd=root, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "add solo"], cwd=root, check=True, capture_output=True)

    from arc import state as st

    data = st.init_state(base="main")
    data = st.add_branch(data, "feat/solo")
    st.save(root, data)

    # Stage an additional change
    (root / "solo.py").write_text("x = 1\ny = 2\n")
    sp.run(["git", "add", "solo.py"], cwd=root, check=True, capture_output=True)

    orig = _os.getcwd()
    _os.chdir(root)
    result = _run_edit(["--no-push", "--json"])
    _os.chdir(orig)

    assert result.exit_code == 0, result.output
    data_out = json.loads(result.output)
    assert data_out["ok"] is True
    assert data_out["state"] == "done"
    assert data_out["mode"] == "staged"
    assert "solo.py" in data_out["amendment_summary"]["files_changed"]
    assert data_out["amendment_summary"]["insertions"] == 1


@pytest.mark.git
def test_edit_restacks_upstack_branches(stacked_repo):
    """arc edit on feat/auth restacks feat/api and feat/tests."""
    import subprocess as sp

    root = stacked_repo

    old_auth_sha = sp.run(
        ["git", "rev-parse", "feat/auth"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    old_api_sha = sp.run(
        ["git", "rev-parse", "feat/api"], cwd=root, capture_output=True, text=True
    ).stdout.strip()

    orig = _os.getcwd()
    _os.chdir(root)
    result = _run_edit(["feat/auth", "--message", "amended auth", "--no-push", "--json"])
    _os.chdir(orig)

    assert result.exit_code == 0, result.output
    data_out = json.loads(result.output)
    assert data_out["state"] == "done"
    assert data_out["old_sha"] == old_auth_sha
    assert data_out["restacked"] == ["feat/api", "feat/tests"]

    # feat/api must have a new SHA (was rebased onto new feat/auth)
    new_api_sha = sp.run(
        ["git", "rev-parse", "feat/api"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    assert new_api_sha != old_api_sha


@pytest.mark.git
def test_edit_dry_run_shows_upstack(stacked_repo):
    import subprocess as sp

    root = stacked_repo

    # Stage something so mode=staged is detected
    sp.run(["git", "checkout", "feat/auth"], cwd=root, check=True, capture_output=True)
    (root / "auth.py").write_text("def auth(): return True\n")
    sp.run(["git", "add", "auth.py"], cwd=root, check=True, capture_output=True)

    orig = _os.getcwd()
    _os.chdir(root)
    result = _run_edit(["feat/auth", "--dry-run", "--json"])
    _os.chdir(orig)

    assert result.exit_code == 0, result.output
    data_out = json.loads(result.output)
    assert data_out["state"] == "dry_run"
    assert "feat/api" in data_out["upstack"]
    assert "feat/tests" in data_out["upstack"]
    assert isinstance(data_out["predicted_conflicts"], list)
