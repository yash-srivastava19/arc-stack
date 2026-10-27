import json
import os
import subprocess as sp

import pytest
from click.testing import CliRunner

from arc import ops
from arc import state as st
from arc.cli import cli

_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(cwd, *args):
    return sp.run(
        ["git", *args], cwd=cwd, env=_ENV, capture_output=True, text=True, check=True
    ).stdout.strip()


def _no_gh(monkeypatch):
    monkeypatch.setattr("arc.github.is_installed", lambda: False)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: False)


@pytest.mark.git
def test_init_works_without_the_github_cli(git_repo, monkeypatch):
    _no_gh(monkeypatch)
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(cli, ["init", "--base", "main", "-q"])

    assert result.exit_code == 0, result.output
    assert (git_repo / ".arc" / "state.json").exists()


@pytest.mark.git
def test_restack_works_without_the_github_cli(arc_stack, monkeypatch):
    _git(arc_stack, "checkout", "-q", "-b", "feat/a")
    (arc_stack / "a.txt").write_text("a")
    _git(arc_stack, "add", "a.txt")
    _git(arc_stack, "commit", "-q", "-m", "a")
    st.save(arc_stack, st.add_branch(st.init_state(base="main"), "feat/a"))
    _no_gh(monkeypatch)
    monkeypatch.chdir(arc_stack)

    result = CliRunner().invoke(cli, ["restack", "feat/a"])

    assert result.exit_code == 0, result.output


@pytest.mark.git
def test_add_drops_merged_branches_before_adopting(arc_stack, monkeypatch):
    for name in ("feat/merged", "feat/next"):
        _git(arc_stack, "checkout", "-q", "-b", name, "main")
    data = st.add_branch(st.init_state(base="main"), "feat/merged")
    data["branches"][0]["pr_number"] = 7
    st.save(arc_stack, data)
    monkeypatch.setattr("arc.github.pr_is_merged", lambda n: n == 7)
    monkeypatch.chdir(arc_stack)

    result = CliRunner().invoke(cli, ["add", "feat/next", "-q"])

    assert result.exit_code == 0, result.output
    state = json.loads((arc_stack / ".arc" / "state.json").read_text())
    assert [b["name"] for b in state["branches"]] == ["feat/next"]


def test_status_does_not_ask_to_rebase_a_merged_branch():
    data = st.add_branch(st.init_state(base="main"), "feat/merged")

    status = ops.stack_status(
        data,
        current_branch="main",
        commit_counts={"feat/merged": 1},
        pr_info={"feat/merged": {"is_merged": True}},
        needs_rebase_flags={"feat/merged": True},
    )

    assert status["branches"][0]["needs_rebase"] is False
    assert "rebase" not in ops.next_step_hint(status)


def _git_without_ahead_behind(monkeypatch):
    """git before 2.41 rejects the %(ahead-behind:...) atom."""
    import arc.git as git_mod

    real = git_mod._run

    def run(args, cwd=None, check=True):
        if args[:2] == ["git", "for-each-ref"] and "ahead-behind" in " ".join(args):
            return sp.CompletedProcess(args, 128, "", "fatal: unknown field name")
        return real(args, cwd=cwd, check=check)

    monkeypatch.setattr(git_mod, "_run", run)


@pytest.mark.git
@pytest.mark.parametrize("old_git", [False, True])
def test_status_reports_commit_counts_and_stale_branches(stacked_repo, monkeypatch, old_git):
    if old_git:
        _git_without_ahead_behind(monkeypatch)
    _git(stacked_repo, "checkout", "-q", "feat/auth")
    (stacked_repo / "auth2.py").write_text("more")
    _git(stacked_repo, "add", "auth2.py")
    _git(stacked_repo, "commit", "-q", "-m", "more auth")
    monkeypatch.chdir(stacked_repo)

    result = CliRunner().invoke(cli, ["status", "--json"])

    assert result.exit_code == 0, result.output
    branches = {b["name"]: b for b in json.loads(result.output)["branches"]}
    assert {n: b["commits"] for n, b in branches.items()} == {
        "feat/auth": 2,
        "feat/api": 2,
        "feat/tests": 3,
    }
    assert {n: b["needs_rebase"] for n, b in branches.items()} == {
        "feat/auth": False,
        "feat/api": True,
        "feat/tests": False,
    }
