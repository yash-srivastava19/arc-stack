"""Tests for arc edit command."""
import json
from pathlib import Path

import pytest


def test_edit_state_roundtrip(tmp_path):
    from arc.commands.edit import (
        _EditState, _save_edit_state, _load_edit_state, _clear_edit_state,
        _edit_state_path,
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
    from arc.commands.edit import _detect_mode
    from unittest.mock import patch
    with patch("arc.commands.edit.git.get_staged_files", return_value=[]):
        assert _detect_mode(message="fix typo", interactive=False) == "message"


def test_detect_mode_staged_when_files_staged():
    from arc.commands.edit import _detect_mode
    from unittest.mock import patch
    with patch("arc.commands.edit.git.get_staged_files", return_value=["auth.py"]):
        assert _detect_mode(message=None, interactive=False) == "staged"


def test_detect_mode_staged_overrides_message_when_files_staged():
    from arc.commands.edit import _detect_mode
    from unittest.mock import patch
    with patch("arc.commands.edit.git.get_staged_files", return_value=["auth.py"]):
        assert _detect_mode(message="new message", interactive=False) == "staged"


def test_detect_mode_interactive():
    from arc.commands.edit import _detect_mode
    from unittest.mock import patch
    with patch("arc.commands.edit.git.get_staged_files", return_value=[]):
        assert _detect_mode(message=None, interactive=True) == "interactive"


@pytest.mark.git
def test_get_amendment_summary_shape(git_repo):
    import subprocess as sp
    import os
    from arc.commands.edit import _get_amendment_summary
    old_sha = sp.run(["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True).stdout.strip()
    (git_repo / "x.py").write_text("a = 1\nb = 2\n")
    sp.run(["git", "add", "x.py"], cwd=git_repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "add x"], cwd=git_repo, check=True, capture_output=True)
    new_sha = sp.run(["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True).stdout.strip()
    orig = os.getcwd()
    try:
        os.chdir(git_repo)
        summary = _get_amendment_summary(old_sha, new_sha)
    finally:
        os.chdir(orig)
    assert "x.py" in summary["files_changed"]
    assert summary["insertions"] == 2
    assert isinstance(summary["deletions"], int)
