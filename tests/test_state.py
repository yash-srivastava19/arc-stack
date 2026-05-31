import json
import pytest
from pathlib import Path
from arc import state


def test_find_repo_root_finds_git(tmp_path):
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "src" / "deep"
    subdir.mkdir(parents=True)
    assert state.find_repo_root(subdir) == tmp_path


def test_find_repo_root_raises_outside_repo(tmp_path):
    with pytest.raises(RuntimeError, match="Not in a git repository"):
        state.find_repo_root(tmp_path)


def test_init_state_defaults():
    s = state.init_state(base="main")
    assert s["version"] == 1
    assert s["base"] == "main"
    assert s["prefix"] is None
    assert s["branches"] == []
    assert s["metadata"] == {}


def test_init_state_with_prefix():
    s = state.init_state(base="main", prefix="feat")
    assert s["prefix"] == "feat"


def test_save_and_load_roundtrip(repo_root):
    s = state.init_state(base="main", prefix="feat")
    state.save(repo_root, s)
    loaded = state.load(repo_root)
    assert loaded == s


def test_load_raises_when_missing(repo_root):
    with pytest.raises(FileNotFoundError, match="arc init"):
        state.load(repo_root)


def test_load_rejects_unknown_version(repo_root):
    path = repo_root / ".arc" / "state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"version": 999, "base": "main", "branches": [], "metadata": {}}))
    with pytest.raises(ValueError, match="Unknown state version"):
        state.load(repo_root)


def test_apply_prefix_adds_prefix():
    s = state.init_state(base="main", prefix="feat")
    assert state.apply_prefix(s, "auth") == "feat/auth"


def test_apply_prefix_skips_if_already_prefixed():
    s = state.init_state(base="main", prefix="feat")
    assert state.apply_prefix(s, "feat/auth") == "feat/auth"


def test_apply_prefix_skips_if_no_prefix():
    s = state.init_state(base="main")
    assert state.apply_prefix(s, "auth") == "auth"


def test_add_branch_appends():
    s = state.init_state(base="main")
    s2 = state.add_branch(s, "feat/auth")
    assert len(s2["branches"]) == 1
    assert s2["branches"][0] == {"name": "feat/auth", "pr_number": None, "revision": 0}
    assert s["branches"] == []  # original unchanged (pure)


def test_remove_branch():
    s = state.init_state(base="main")
    s = state.add_branch(s, "feat/auth")
    s = state.add_branch(s, "feat/api")
    s2 = state.remove_branch(s, "feat/auth")
    assert state.branch_names(s2) == ["feat/api"]


def test_update_branch():
    s = state.init_state(base="main")
    s = state.add_branch(s, "feat/auth")
    s2 = state.update_branch(s, "feat/auth", pr_number=42, revision=1)
    assert s2["branches"][0]["pr_number"] == 42
    assert s2["branches"][0]["revision"] == 1


def test_get_branch_returns_none_when_missing():
    s = state.init_state(base="main")
    assert state.get_branch(s, "feat/auth") is None


def test_branch_names():
    s = state.init_state(base="main")
    s = state.add_branch(s, "feat/auth")
    s = state.add_branch(s, "feat/api")
    assert state.branch_names(s) == ["feat/auth", "feat/api"]


def test_load_config_returns_empty_when_absent(repo_root):
    assert state.load_config(repo_root) == {}


def test_load_config_reads_file(repo_root):
    cfg = {"hooks": {"pre-submit": ["npm test"]}}
    path = repo_root / ".arc" / "config.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(cfg))
    assert state.load_config(repo_root) == cfg
