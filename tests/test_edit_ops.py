from unittest.mock import patch

from arc.commands._edit_ops import _detect_mode, _get_amendment_summary


def test_detect_mode_interactive():
    assert _detect_mode(message=None, interactive=True) == "interactive"


def test_detect_mode_staged_when_files_staged():
    with patch("arc.git.get_staged_files", return_value=["foo.py"]):
        assert _detect_mode(message="msg", interactive=False) == "staged"


def test_detect_mode_message_when_nothing_staged():
    with patch("arc.git.get_staged_files", return_value=[]):
        assert _detect_mode(message="msg", interactive=False) == "message"


def test_get_amendment_summary():
    mock_stat = {"files_changed": ["a.py", "b.py"], "insertions": 5, "deletions": 2}
    with patch("arc.git.diff_stat", return_value=mock_stat):
        result = _get_amendment_summary("abc123", "def456")
    assert result["files_changed"] == ["a.py", "b.py"]
    assert result["insertions"] == 5
    assert result["deletions"] == 2
