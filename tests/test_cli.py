import json as _json
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from arc.cli import cli


def _write_state(tmp_path, base="main", prefix=None, branches=None):
    """Helper: write a stack state.json to tmp_path."""
    (tmp_path / ".arc").mkdir(exist_ok=True)
    data = {"version": 1, "base": base, "prefix": prefix,
            "branches": branches or [], "metadata": {}}
    (tmp_path / ".arc" / "state.json").write_text(_json.dumps(data))
    return tmp_path


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "arc" in result.output.lower()


def test_setup_success():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True), \
         patch("arc.git.set_config"):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 0
    assert "Ready" in result.output


def test_setup_quiet_suppresses_hints():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True), \
         patch("arc.git.set_config"):
        result = runner.invoke(cli, ["setup", "-q"])
    assert result.exit_code == 0


def test_setup_fails_when_git_not_installed():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=False), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "git" in result.output


def test_setup_fails_when_gh_not_installed():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=False):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "gh" in result.output


def test_setup_fails_when_not_authenticated():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=False):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "gh auth login" in result.output


# ---------------------------------------------------------------------------
# Task 7: arc init
# ---------------------------------------------------------------------------

def test_init_creates_state(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.default_branch", return_value="main"), \
         patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True):
        result = runner.invoke(cli, ["init", "--base", "main"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["base"] == "main"
    assert data["branches"] == []


def test_init_detects_default_branch(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.default_branch", return_value="develop"), \
         patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True):
        result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["base"] == "develop"


def test_init_adds_state_json_to_gitignore(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.default_branch", return_value="main"), \
         patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True):
        runner.invoke(cli, ["init", "--base", "main"])
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".arc/state.json" in gitignore.read_text()


def test_init_with_prefix(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.default_branch", return_value="main"), \
         patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True):
        runner.invoke(cli, ["init", "--base", "main", "--prefix", "feat"])
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["prefix"] == "feat"


# ---------------------------------------------------------------------------
# Task 8: arc new + arc add
# ---------------------------------------------------------------------------

def test_new_creates_branch(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.create_branch") as mock_create:
        result = runner.invoke(cli, ["new", "feat/auth"])
    assert result.exit_code == 0
    mock_create.assert_called_once_with("feat/auth", "HEAD")
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["name"] == "feat/auth"


def test_new_applies_prefix(tmp_path):
    _write_state(tmp_path, prefix="feat")
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.create_branch") as mock_create:
        runner.invoke(cli, ["new", "auth"])
    mock_create.assert_called_once_with("feat/auth", "HEAD")


def test_new_fails_if_not_initialized(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["new", "feat/auth"])
    assert result.exit_code == 2


def test_add_adopts_existing_branch(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.branch_exists", return_value=True):
        result = runner.invoke(cli, ["add", "feat/auth"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["name"] == "feat/auth"


def test_add_fails_if_branch_missing(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.branch_exists", return_value=False):
        result = runner.invoke(cli, ["add", "feat/auth"])
    assert result.exit_code == 1


def test_add_fails_if_already_in_stack(tmp_path):
    _write_state(tmp_path, branches=[{"name": "feat/auth", "pr_number": None, "revision": 0}])
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.branch_exists", return_value=True):
        result = runner.invoke(cli, ["add", "feat/auth"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Task 9: arc status
# ---------------------------------------------------------------------------

def _write_state_with_branches(tmp_path):
    return _write_state(
        tmp_path,
        prefix="feat",
        branches=[
            {"name": "feat/auth", "pr_number": 42, "revision": 1},
            {"name": "feat/api",  "pr_number": None, "revision": 0},
        ]
    )


def test_status_plain(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.current_branch", return_value="feat/auth"), \
         patch("arc.git.commit_count", return_value=2), \
         patch("arc.git.is_ancestor", return_value=True), \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["status", "--plain"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert lines == ["feat/auth", "feat/api"]


def test_status_json(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.current_branch", return_value="feat/auth"), \
         patch("arc.git.commit_count", return_value=2), \
         patch("arc.git.is_ancestor", return_value=True), \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["status", "--json"])
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert data["base"] == "main"
    assert len(data["branches"]) == 2
    assert data["branches"][0]["name"] == "feat/auth"
    assert data["branches"][0]["pr_number"] == 42
    assert "needs_rebase" in data["branches"][0]
    assert data["branches"][0]["revision"] == 1


def test_status_human_exits_0(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.current_branch", return_value="feat/auth"), \
         patch("arc.git.commit_count", return_value=2), \
         patch("arc.git.is_ancestor", return_value=True), \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "feat/auth" in result.output


def test_status_shows_hint_when_needs_rebase(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.current_branch", return_value="feat/auth"), \
         patch("arc.git.commit_count", return_value=2), \
         patch("arc.git.is_ancestor", return_value=False), \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "arc sync" in result.output


# ---------------------------------------------------------------------------
# Task 10: arc sync
# ---------------------------------------------------------------------------

def test_sync_dry_run_prints_plan(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.fetch"), \
         patch("arc.git.rebase") as mock_rebase, \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["sync", "-n"])
    assert result.exit_code == 0
    mock_rebase.assert_not_called()
    assert "[dry-run]" in result.output


def test_sync_cascades_rebase(tmp_path):
    _write_state_with_branches(tmp_path)
    rebase_calls = []

    def fake_rebase(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.fetch"), \
         patch("arc.git.rebase", side_effect=fake_rebase), \
         patch("arc.git.checkout"), \
         patch("arc.git.get_sha", return_value="abc"), \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 0
    assert rebase_calls == ["main", "feat/auth"]


def test_sync_exits_3_on_conflict(tmp_path):
    _write_state_with_branches(tmp_path)
    conflict_result = MagicMock()
    conflict_result.returncode = 1

    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.fetch"), \
         patch("arc.git.rebase", return_value=conflict_result), \
         patch("arc.git.checkout"), \
         patch("arc.git.rebase_abort"), \
         patch("arc.git.get_sha", return_value="abc"), \
         patch("arc.git.conflicted_files", return_value=["src/auth.py"]), \
         patch("arc.github.get_pr", return_value=None):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 3


# ---------------------------------------------------------------------------
# Task 11: arc push
# ---------------------------------------------------------------------------

def test_push_force_pushes_all_branches(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.force_push") as mock_push:
        result = runner.invoke(cli, ["push"])
    assert result.exit_code == 0
    mock_push.assert_called_once_with(["feat/auth", "feat/api"])


def test_push_dry_run(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.force_push") as mock_push, \
         patch("arc.git.get_sha", return_value="abc123"):
        result = runner.invoke(cli, ["push", "-n"])
    assert result.exit_code == 0
    mock_push.assert_not_called()
    assert "[dry-run]" in result.output


def test_push_increments_revision(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.force_push"):
        runner.invoke(cli, ["push"])
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["revision"] == 2  # was 1
    assert data["branches"][1]["revision"] == 1  # was 0


# ---------------------------------------------------------------------------
# Task 12: arc submit
# ---------------------------------------------------------------------------

import subprocess as _subprocess


def _write_state_no_prs(tmp_path):
    return _write_state(
        tmp_path, prefix="feat",
        branches=[
            {"name": "feat/auth", "pr_number": None, "revision": 1},
            {"name": "feat/api",  "pr_number": None, "revision": 1},
        ]
    )


def test_submit_creates_prs(tmp_path):
    _write_state_no_prs(tmp_path)
    created = []

    def fake_create(branch, base, title, body, draft):
        n = len(created) + 50
        created.append(branch)
        return {"number": n, "url": f"https://gh/{n}"}

    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.get_commit_subject", return_value="Add feature"), \
         patch("arc.git.get_commit_body", return_value=""), \
         patch("arc.git.commit_count", return_value=1), \
         patch("arc.github.get_pr", return_value=None), \
         patch("arc.github.create_pr", side_effect=fake_create):
        result = runner.invoke(cli, ["submit", "--draft"])
    assert result.exit_code == 0
    assert created == ["feat/auth", "feat/api"]
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["pr_number"] == 50


def test_submit_updates_existing_prs(tmp_path):
    _write_state_with_branches(tmp_path)
    updated = []

    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.get_commit_subject", return_value="feat"), \
         patch("arc.git.get_commit_body", return_value=""), \
         patch("arc.git.commit_count", return_value=1), \
         patch("arc.github.get_pr", return_value={"number": 42, "url": "https://gh/42", "state": "OPEN"}), \
         patch("arc.github.update_pr_body", side_effect=lambda n, b: updated.append(n)):
        result = runner.invoke(cli, ["submit"])
    assert result.exit_code == 0
    assert 42 in updated


def test_submit_runs_hooks_and_fails(tmp_path):
    _write_state_no_prs(tmp_path)
    cfg = {"hooks": {"pre-submit": ["exit 1"]}}
    (tmp_path / ".arc" / "config.json").write_text(_json.dumps(cfg))
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["submit"])
    assert result.exit_code == 7


def test_submit_skip_hooks(tmp_path):
    _write_state_no_prs(tmp_path)
    cfg = {"hooks": {"pre-submit": ["exit 1"]}}
    (tmp_path / ".arc" / "config.json").write_text(_json.dumps(cfg))
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.git.get_commit_subject", return_value="feat"), \
         patch("arc.git.get_commit_body", return_value=""), \
         patch("arc.git.commit_count", return_value=1), \
         patch("arc.github.get_pr", return_value=None), \
         patch("arc.github.create_pr", return_value={"number": 1, "url": "https://gh/1"}):
        result = runner.invoke(cli, ["submit", "--skip-hooks"])
    assert result.exit_code == 0


def test_submit_dry_run(tmp_path):
    _write_state_no_prs(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch("arc.github.get_pr", return_value=None), \
         patch("arc.github.create_pr") as mock_create:
        result = runner.invoke(cli, ["submit", "-n"])
    assert result.exit_code == 0
    mock_create.assert_not_called()
    assert "[dry-run]" in result.output
