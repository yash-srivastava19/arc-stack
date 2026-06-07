from pathlib import Path
from unittest.mock import patch


def test_predict_conflicts_finds_shared_files(tmp_path):
    from arc.conflicts import predict_conflicts

    data = {
        "base": "main",
        "branches": [
            {"name": "feat/a", "pr_number": None, "revision": 0},
            {"name": "feat/b", "pr_number": None, "revision": 0},
        ],
    }

    def fake_files(root: Path, from_ref: str, to_ref: str) -> list[str]:
        if to_ref == "feat/a":
            return ["api.py", "README.md"]
        if to_ref == "feat/b":
            return ["api.py", "tests.py"]
        return []

    with patch("arc.conflicts.changed_files_between", fake_files):
        result = predict_conflicts(data, tmp_path)
    assert len(result) == 1
    assert result[0]["branch"] == "feat/b"
    assert "api.py" in result[0]["shared_files"]


def test_predict_conflicts_empty_when_no_overlap(tmp_path):
    from arc.conflicts import predict_conflicts

    data = {
        "base": "main",
        "branches": [
            {"name": "feat/a", "pr_number": None, "revision": 0},
            {"name": "feat/b", "pr_number": None, "revision": 0},
        ],
    }

    def fake_files(root: Path, from_ref: str, to_ref: str) -> list[str]:
        if to_ref == "feat/a":
            return ["api.py"]
        if to_ref == "feat/b":
            return ["tests.py"]
        return []

    with patch("arc.conflicts.changed_files_between", fake_files):
        result = predict_conflicts(data, tmp_path)
    assert result == []


def test_predict_conflicts_skips_single_branch(tmp_path):
    from arc.conflicts import predict_conflicts

    data = {"base": "main", "branches": [{"name": "feat/a", "pr_number": None, "revision": 0}]}
    with patch("arc.conflicts.changed_files_between", return_value=["api.py"]):
        result = predict_conflicts(data, tmp_path)
    assert result == []
