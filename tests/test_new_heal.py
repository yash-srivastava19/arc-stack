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


@pytest.mark.git
def test_new_on_a_merged_stack_top_starts_from_base(arc_stack, monkeypatch):
    root = arc_stack
    _git(root, "checkout", "-q", "-b", "feat/a")
    (root / "a.txt").write_text("a")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-q", "-m", "add a")
    data = st.add_branch(st.init_state(base="main"), "feat/a")
    data["branches"][0]["pr_number"] = 1
    st.save(root, data)
    monkeypatch.setattr("arc.github.pr_is_merged", lambda n: True)
    monkeypatch.setattr("arc.github.get_merge_commit_sha", lambda n: None)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(cli, ["new", "feat/b", "-q"])

    assert result.exit_code == 0, result.output
    names = [b["name"] for b in json.loads((root / ".arc" / "state.json").read_text())["branches"]]
    assert names == ["feat/b"]
    assert _git(root, "rev-parse", "feat/b") == _git(root, "rev-parse", "main")
