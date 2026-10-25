import subprocess as sp

import pytest
from click.testing import CliRunner

from arc.cli import cli


def _git(root, *args):
    return sp.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.mark.git
@pytest.mark.parametrize("dropped", ["feat/auth", "feat/api"])
def test_drop_removes_dropped_branch_commits_from_upstack(stacked_repo, monkeypatch, dropped):
    monkeypatch.chdir(stacked_repo)

    result = CliRunner().invoke(cli, ["drop", dropped, "-f"])

    assert result.exit_code == 0, result.output
    dropped_file = {"feat/auth": "auth.py", "feat/api": "api.py"}[dropped]
    for branch in ("feat/tests",) + (("feat/api",) if dropped == "feat/auth" else ()):
        assert dropped_file not in _git(stacked_repo, "ls-tree", "--name-only", branch).split()
    parent = "main" if dropped == "feat/auth" else "feat/auth"
    child = "feat/api" if dropped == "feat/auth" else "feat/tests"
    assert _git(stacked_repo, "rev-list", "--count", f"{parent}..{child}").strip() == "1"
