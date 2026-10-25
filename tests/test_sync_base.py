import json
import os
import subprocess as sp

import pytest
from click.testing import CliRunner

from arc import state as st
from arc.cli import cli

_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(cwd, *args):
    return sp.run(
        ["git", *args], cwd=cwd, env=_ENV, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(cwd, name, content):
    (cwd / name).write_text(content)
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", f"add {name}")


@pytest.fixture
def pushed_stack(arc_stack):
    """feat/a -> feat/b on main, both pushed, feat/b checked out."""
    root = arc_stack
    for name in ("feat/a", "feat/b"):
        _git(root, "checkout", "-q", "-b", name)
        _commit(root, f"{name[-1]}.txt", name)
    _git(root, "push", "-q", "-u", "origin", "feat/a", "feat/b")
    data = st.init_state(base="main")
    for name in ("feat/a", "feat/b"):
        data = st.add_branch(data, name)
    st.save(root, data)
    other = root.parent / "other"
    _git(root.parent, "clone", "-q", str(root.parent / "remote.git"), str(other))
    _git(other, "config", "user.email", "o@arc.dev")
    _git(other, "config", "user.name", "Other")
    _git(other, "checkout", "-q", "-B", "main", "origin/main")
    return root, other


def _sync(root, monkeypatch):
    monkeypatch.chdir(root)
    return CliRunner().invoke(cli, ["sync"])


@pytest.mark.git
def test_sync_restacks_onto_trunk_that_moved_on_origin(pushed_stack, monkeypatch):
    root, other = pushed_stack
    _commit(other, "upstream.txt", "new work on main")
    _git(other, "push", "-q", "origin", "main")

    result = _sync(root, monkeypatch)

    assert result.exit_code == 0, result.output
    upstream = _git(root, "rev-parse", "origin/main")
    assert _git(root, "rev-parse", "main") == upstream
    assert _git(root, "merge-base", "feat/a", upstream) == upstream
    assert "upstream.txt" in _git(root, "ls-tree", "--name-only", "feat/b").split()


@pytest.mark.git
def test_sync_drops_bottom_branch_squash_merged_on_origin(pushed_stack, monkeypatch):
    root, other = pushed_stack
    _git(other, "merge", "-q", "--squash", "origin/feat/a")
    _git(other, "commit", "-q", "-m", "feat/a (#1)")
    _git(other, "push", "-q", "origin", "main", ":feat/a")

    result = _sync(root, monkeypatch)

    assert result.exit_code == 0, result.output
    names = [b["name"] for b in json.loads((root / ".arc" / "state.json").read_text())["branches"]]
    assert names == ["feat/b"]
    upstream = _git(root, "rev-parse", "origin/main")
    assert _git(root, "rev-parse", "feat/b~1") == upstream


@pytest.mark.git
def test_sync_leaves_trunk_alone_when_it_has_unpushed_commits(pushed_stack, monkeypatch):
    root, other = pushed_stack
    _commit(other, "upstream.txt", "new work on main")
    _git(other, "push", "-q", "origin", "main")
    _git(root, "checkout", "-q", "main")
    _commit(root, "local.txt", "local only")
    local_main = _git(root, "rev-parse", "main")
    _git(root, "checkout", "-q", "feat/b")

    result = _sync(root, monkeypatch)

    assert result.exit_code == 0, result.output
    assert _git(root, "rev-parse", "main") == local_main
