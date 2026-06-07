import json as _json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from arc.cli import cli


def _write_state(tmp_path, base="main", prefix=None, branches=None):
    """Helper: write a stack state.json to tmp_path."""
    (tmp_path / ".arc").mkdir(exist_ok=True)
    data = {
        "version": 1,
        "base": base,
        "prefix": prefix,
        "branches": branches or [],
        "metadata": {},
    }
    (tmp_path / ".arc" / "state.json").write_text(_json.dumps(data))
    return tmp_path


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.output


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "arc" in result.output.lower()


def test_setup_success():
    runner = CliRunner()
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
        patch("arc.git.set_config"),
    ):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 0
    assert "Ready" in result.output


def test_setup_quiet_suppresses_hints():
    runner = CliRunner()
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
        patch("arc.git.set_config"),
    ):
        result = runner.invoke(cli, ["setup", "-q"])
    assert result.exit_code == 0


def test_setup_fails_when_git_not_installed():
    runner = CliRunner()
    with (
        patch("arc.git.is_installed", return_value=False),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
    ):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "git" in result.output


def test_setup_fails_when_gh_not_installed():
    runner = CliRunner()
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=False),
    ):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "gh" in result.output


def test_setup_fails_when_not_authenticated():
    runner = CliRunner()
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=False),
    ):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "gh auth login" in result.output


# ---------------------------------------------------------------------------
# Task 7: arc init
# ---------------------------------------------------------------------------


def test_init_creates_state(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.default_branch", return_value="main"),
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
    ):
        result = runner.invoke(cli, ["init", "--base", "main"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["base"] == "main"
    assert data["branches"] == []


def test_init_detects_default_branch(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.default_branch", return_value="develop"),
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
    ):
        result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["base"] == "develop"


def test_init_adds_state_json_to_gitignore(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.default_branch", return_value="main"),
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
    ):
        runner.invoke(cli, ["init", "--base", "main"])
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".arc/state.json" in gitignore.read_text()


def test_init_with_prefix(tmp_path):
    (tmp_path / ".git").mkdir()
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.default_branch", return_value="main"),
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
    ):
        runner.invoke(cli, ["init", "--base", "main", "--prefix", "feat"])
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["prefix"] == "feat"


# ---------------------------------------------------------------------------
# Task 8: arc new + arc add
# ---------------------------------------------------------------------------


def test_new_creates_branch(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.create_branch") as mock_create,
    ):
        result = runner.invoke(cli, ["new", "feat/auth"])
    assert result.exit_code == 0
    mock_create.assert_called_once_with("feat/auth", "HEAD")
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["name"] == "feat/auth"


def test_new_applies_prefix(tmp_path):
    _write_state(tmp_path, prefix="feat")
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.create_branch") as mock_create,
    ):
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
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.branch_exists", return_value=True),
    ):
        result = runner.invoke(cli, ["add", "feat/auth"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["name"] == "feat/auth"


def test_add_fails_if_branch_missing(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.branch_exists", return_value=False),
    ):
        result = runner.invoke(cli, ["add", "feat/auth"])
    assert result.exit_code == 1


def test_add_fails_if_already_in_stack(tmp_path):
    _write_state(tmp_path, branches=[{"name": "feat/auth", "pr_number": None, "revision": 0}])
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.branch_exists", return_value=True),
    ):
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
            {"name": "feat/api", "pr_number": None, "revision": 0},
        ],
    )


def test_status_plain(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["status", "--plain"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert lines == ["feat/auth", "feat/api"]


def test_status_json(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["status", "--json"])
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert data["base"] == "main"
    assert len(data["branches"]) == 2
    assert data["branches"][0]["name"] == "feat/auth"
    assert data["branches"][0]["pr_number"] == 42
    assert "needs_rebase" in data["branches"][0]
    assert data["branches"][0]["revision"] == 1


def test_status_human_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)  # force human-readable output
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "feat/auth" in result.output


def test_status_shows_hint_when_needs_rebase(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=False),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.cli._is_tty", return_value=True),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "arc sync" in result.output


# ---------------------------------------------------------------------------
# Task 10: arc sync
# ---------------------------------------------------------------------------


def test_sync_dry_run_prints_plan(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch"),
        patch("arc.git.rebase") as mock_rebase,
        patch("arc.github.get_pr", return_value=None),
    ):
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
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch"),
        patch("arc.git.rebase", side_effect=fake_rebase),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 0
    assert rebase_calls == ["main", "feat/auth"]


def test_sync_exits_3_on_conflict(tmp_path):
    _write_state_with_branches(tmp_path)
    conflict_result = MagicMock()
    conflict_result.returncode = 1

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch"),
        patch("arc.git.rebase", return_value=conflict_result),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_abort"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.conflicted_files", return_value=["src/auth.py"]),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 3


# ---------------------------------------------------------------------------
# Task 11: arc push
# ---------------------------------------------------------------------------


def test_push_force_pushes_all_branches(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.force_push") as mock_push,
    ):
        result = runner.invoke(cli, ["push"])
    assert result.exit_code == 0
    mock_push.assert_called_once_with(["feat/auth", "feat/api"])


def test_push_dry_run(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.force_push") as mock_push,
        patch("arc.git.get_sha", return_value="abc123"),
    ):
        result = runner.invoke(cli, ["push", "-n"])
    assert result.exit_code == 0
    mock_push.assert_not_called()
    assert "[dry-run]" in result.output


def test_push_increments_revision(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), patch("arc.git.force_push"):
        runner.invoke(cli, ["push"])
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["revision"] == 2  # was 1
    assert data["branches"][1]["revision"] == 1  # was 0


# ---------------------------------------------------------------------------
# Task 12: arc submit
# ---------------------------------------------------------------------------


def _write_state_no_prs(tmp_path):
    return _write_state(
        tmp_path,
        prefix="feat",
        branches=[
            {"name": "feat/auth", "pr_number": None, "revision": 1},
            {"name": "feat/api", "pr_number": None, "revision": 1},
        ],
    )


def test_submit_creates_prs(tmp_path):
    _write_state_no_prs(tmp_path)
    created = []

    def fake_create(branch, base, title, body, draft):
        n = len(created) + 50
        created.append(branch)
        return {"number": n, "url": f"https://gh/{n}"}

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_commit_subject", return_value="Add feature"),
        patch("arc.git.get_commit_body", return_value=""),
        patch("arc.git.commit_count", return_value=1),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.github.create_pr", side_effect=fake_create),
    ):
        result = runner.invoke(cli, ["submit", "--draft"])
    assert result.exit_code == 0
    assert created == ["feat/auth", "feat/api"]
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert data["branches"][0]["pr_number"] == 50


def test_submit_updates_existing_prs(tmp_path):
    _write_state_with_branches(tmp_path)
    updated = []

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_commit_subject", return_value="feat"),
        patch("arc.git.get_commit_body", return_value=""),
        patch("arc.git.commit_count", return_value=1),
        patch(
            "arc.github.get_pr",
            return_value={"number": 42, "url": "https://gh/42", "state": "OPEN"},
        ),
        patch("arc.github.update_pr_body", side_effect=lambda n, b: updated.append(n)),
    ):
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
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_commit_subject", return_value="feat"),
        patch("arc.git.get_commit_body", return_value=""),
        patch("arc.git.commit_count", return_value=1),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.github.create_pr", return_value={"number": 1, "url": "https://gh/1"}),
    ):
        result = runner.invoke(cli, ["submit", "--skip-hooks"])
    assert result.exit_code == 0


def test_submit_dry_run(tmp_path):
    _write_state_no_prs(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.github.create_pr") as mock_create,
    ):
        result = runner.invoke(cli, ["submit", "-n"])
    assert result.exit_code == 0
    mock_create.assert_not_called()
    assert "[dry-run]" in result.output


# ---------------------------------------------------------------------------
# Task 13: arc land
# ---------------------------------------------------------------------------


def test_land_fails_if_pr_not_merged(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 1
    assert "not merged" in result.output.lower()


def test_land_removes_branch_and_restacks(tmp_path):
    _write_state_with_branches(tmp_path)

    rebase_calls = []

    def fake_rebase_onto(new_base, old_base, branch):
        rebase_calls.append((new_base, old_base, branch))
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value="squash123"),
        patch("arc.git.get_sha", return_value="old_sha"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_onto", side_effect=fake_rebase_onto),
        patch("arc.git.delete_branch"),
        patch("arc.git.is_ancestor", return_value=False),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0
    assert ("main", "feat/auth", "feat/api") in rebase_calls
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert all(b["name"] != "feat/auth" for b in data["branches"])


def test_land_fails_if_no_pr(tmp_path):
    _write_state_with_branches(tmp_path)
    # feat/api has no PR
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["land", "feat/api", "-f"])
    assert result.exit_code == 1


def test_land_dry_run(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value=None),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.is_ancestor", return_value=True),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-n", "-f"])
    assert result.exit_code == 0
    assert "[dry-run]" in result.output


# ---------------------------------------------------------------------------
# Task 14: arc amend + arc drop
# ---------------------------------------------------------------------------


def test_amend_appends_pr_footer(tmp_path):
    _write_state_with_branches(tmp_path)
    amended = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.get_commit_message", return_value="Add auth"),
        patch("arc.git.amend_message", side_effect=amended.append),
        patch("arc.github.get_pr", return_value={"url": "https://gh/42"}),
    ):
        result = runner.invoke(cli, ["amend"])
    assert result.exit_code == 0
    assert amended
    assert "Arc-PR: https://gh/42" in amended[0]
    assert "Arc-Stack-Position: 1/2" in amended[0]


def test_amend_fails_if_not_in_stack(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="not-in-stack"),
    ):
        result = runner.invoke(cli, ["amend"])
    assert result.exit_code == 5


def test_drop_removes_branch_and_restacks(tmp_path):
    _write_state_with_branches(tmp_path)
    rebase_calls = []

    def fake_rebase(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout"),
        patch("arc.git.rebase", side_effect=fake_rebase),
    ):
        result = runner.invoke(cli, ["drop", "feat/auth", "-f"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert all(b["name"] != "feat/auth" for b in data["branches"])
    assert "main" in rebase_calls  # feat/api rebased onto main


def test_drop_requires_force_non_interactive(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["drop", "feat/auth"])
    assert result.exit_code == 5


def test_drop_dry_run(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.rebase") as mock_rebase,
    ):
        result = runner.invoke(cli, ["drop", "feat/auth", "-n"])
    assert result.exit_code == 0
    mock_rebase.assert_not_called()
    assert "[dry-run]" in result.output


# ---------------------------------------------------------------------------
# Task 15: arc rebase
# ---------------------------------------------------------------------------


def test_rebase_entire_stack(tmp_path):
    _write_state_with_branches(tmp_path)
    rebase_calls = []

    def fake_rebase(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase", side_effect=fake_rebase),
    ):
        result = runner.invoke(cli, ["rebase"])
    assert result.exit_code == 0
    assert rebase_calls == ["main", "feat/auth"]


def test_rebase_upstack(tmp_path):
    _write_state_with_branches(tmp_path)
    rebase_calls = []

    def fake_rebase(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase", side_effect=fake_rebase),
    ):
        result = runner.invoke(cli, ["rebase", "--upstack"])
    assert result.exit_code == 0
    assert "main" in rebase_calls


def test_rebase_continue(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.rebase_continue", return_value=MagicMock(returncode=0)),
    ):
        result = runner.invoke(cli, ["rebase", "--continue"])
    assert result.exit_code == 0


def test_rebase_abort(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), patch("arc.git.rebase_abort"):
        result = runner.invoke(cli, ["rebase", "--abort"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Task 16: Navigation commands
# ---------------------------------------------------------------------------


def test_checkout_by_name(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout") as mock_co,
    ):
        result = runner.invoke(cli, ["checkout", "feat/api"])
    assert result.exit_code == 0
    mock_co.assert_called_once_with("feat/api")


def test_checkout_by_index(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout") as mock_co,
    ):
        result = runner.invoke(cli, ["checkout", "2"])
    assert result.exit_code == 0
    mock_co.assert_called_once_with("feat/api")


def test_checkout_invalid_index(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["checkout", "99"])
    assert result.exit_code == 5


def test_up_moves_toward_top(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout") as mock_co,
    ):
        result = runner.invoke(cli, ["up"])
    assert result.exit_code == 0
    mock_co.assert_called_once_with("feat/api")


def test_down_moves_toward_trunk(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/api"),
        patch("arc.git.checkout") as mock_co,
    ):
        result = runner.invoke(cli, ["down"])
    assert result.exit_code == 0
    mock_co.assert_called_once_with("feat/auth")


def test_top_jumps_to_last(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout") as mock_co,
    ):
        result = runner.invoke(cli, ["top"])
    assert result.exit_code == 0
    mock_co.assert_called_once_with("feat/api")


def test_bottom_jumps_to_first(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout") as mock_co,
    ):
        result = runner.invoke(cli, ["bottom"])
    assert result.exit_code == 0
    mock_co.assert_called_once_with("feat/auth")


# ---------------------------------------------------------------------------
# Task 3: arc report
# ---------------------------------------------------------------------------


def test_report_bug_non_tty_requires_message():
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value="/tmp"):
        result = runner.invoke(cli, ["report", "--bug"])
    assert result.exit_code == 5
    assert "message" in result.output.lower()


def test_report_bug_with_message_non_tty():
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value="/tmp"),
        patch("arc.github.create_issue", return_value={"number": 42, "html_url": "https://gh/42"}),
    ):
        result = runner.invoke(cli, ["report", "--bug", "--message", "test bug"])
    assert result.exit_code == 0
    assert "42" in result.output


def test_report_feedback_with_message():
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value="/tmp"),
        patch("arc.github.create_issue", return_value={"number": 43, "html_url": "https://gh/43"}),
    ):
        result = runner.invoke(cli, ["report", "--feedback", "--message", "feature request"])
    assert result.exit_code == 0


def test_report_dry_run_prints_issue():
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value="/tmp"):
        result = runner.invoke(cli, ["report", "--bug", "--message", "test", "--dry-run"])
    assert result.exit_code == 0
    assert "[Environment]" in result.output or "test" in result.output


# ---------------------------------------------------------------------------
# Task 4: Passive error hints
# ---------------------------------------------------------------------------


def test_error_hint_printed_after_sync_exception(tmp_path):
    """Hint is printed after unexpected sync failure."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch", side_effect=RuntimeError("network error")),
    ):
        result = runner.invoke(cli, ["sync"])
    assert "arc report --bug" in result.output


def test_error_hint_respects_enabled_false(tmp_path):
    """Hint is suppressed when feedback.enabled=false in config."""
    _write_state_with_branches(tmp_path)
    import json as _json_mod

    cfg = {"feedback": {"enabled": False}}
    (tmp_path / ".arc" / "config.json").write_text(_json_mod.dumps(cfg))
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch", side_effect=RuntimeError("network error")),
    ):
        result = runner.invoke(cli, ["sync"])
    assert "arc report --bug" not in result.output


def test_error_hint_respects_prompt_after_error_false(tmp_path):
    """Hint is suppressed when feedback.prompt_after_error=false in config."""
    _write_state_with_branches(tmp_path)
    import json as _json_mod

    cfg = {"feedback": {"prompt_after_error": False}}
    (tmp_path / ".arc" / "config.json").write_text(_json_mod.dumps(cfg))
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch", side_effect=RuntimeError("network error")),
    ):
        result = runner.invoke(cli, ["sync"])
    assert "arc report --bug" not in result.output


# ---------------------------------------------------------------------------
# Task 5: Periodic hints
# ---------------------------------------------------------------------------


def test_periodic_hint_printed_when_random_hits(tmp_path):
    """Periodic feedback hint is printed when random returns 1."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.cli.random.randint", return_value=1),
        patch("arc.cli._is_tty", return_value=True),
    ):
        result = runner.invoke(cli, ["status"])
    assert "arc report --feedback" in result.output


def test_periodic_hint_not_printed_when_random_misses(tmp_path):
    """Periodic feedback hint is not printed when random doesn't return 1."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.cli.random.randint", return_value=2),
    ):
        result = runner.invoke(cli, ["status"])
    assert "arc report --feedback" not in result.output


def test_periodic_hint_disabled_by_config(tmp_path):
    """Periodic hint is suppressed when feedback.prompt_periodic=false."""
    _write_state_with_branches(tmp_path)
    import json as _json_mod

    cfg = {"feedback": {"prompt_periodic": False}}
    (tmp_path / ".arc" / "config.json").write_text(_json_mod.dumps(cfg))
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.cli.random.randint", return_value=1),
    ):
        result = runner.invoke(cli, ["status"])
    assert "arc report --feedback" not in result.output


def test_periodic_hint_disabled_when_feedback_disabled(tmp_path):
    """Periodic hint is suppressed when feedback.enabled=false."""
    _write_state_with_branches(tmp_path)
    import json as _json_mod

    cfg = {"feedback": {"enabled": False}}
    (tmp_path / ".arc" / "config.json").write_text(_json_mod.dumps(cfg))
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.cli.random.randint", return_value=1),
    ):
        result = runner.invoke(cli, ["status"])
    assert "arc report --feedback" not in result.output


# ---------------------------------------------------------------------------
# Task 3 (v0.3.0): Auto TTY detection, first-run experience, JSON errors
# ---------------------------------------------------------------------------


def test_status_auto_json_when_piped(arc_root, monkeypatch):
    """When stdout is not a TTY, status should emit JSON without --json flag."""
    import json
    from unittest.mock import patch

    from arc.state import save as _save

    _save(arc_root, {"version": 1, "base": "main", "prefix": None, "branches": [], "metadata": {}})
    monkeypatch.chdir(arc_root)
    from click.testing import CliRunner

    from arc.cli import cli

    # _is_tty returns False (not a TTY) so auto-JSON should kick in
    with (
        patch("arc.git.find_repo_root", return_value=arc_root),
        patch("arc.git.current_branch", return_value="main"),
        patch("arc.cli._is_tty", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["status"])
    data = json.loads(result.output)
    assert "branches" in data


def test_status_no_init_gives_helpful_message(tmp_path, monkeypatch):
    """Running arc status without arc init should suggest arc init, not crash."""
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)  # force human-readable error output
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 2
    assert "arc init" in result.output


def test_status_json_error_on_no_init(tmp_path, monkeypatch):
    """When --json is passed and command fails, error should be valid JSON."""
    import json

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["status", "--json"])
    assert result.exit_code == 2
    data = json.loads(result.output)
    assert data["ok"] is False
    assert "error" in data
    assert "hint" in data


# ---------------------------------------------------------------------------
# Task 5 (v0.3.0): arc doctor
# ---------------------------------------------------------------------------


def test_doctor_passes_in_clean_environment(monkeypatch):
    """arc doctor exits 0 when git and gh are present and authenticated."""
    from click.testing import CliRunner

    from arc import git, github
    from arc.cli import cli

    monkeypatch.setattr(git, "is_installed", lambda: True)
    monkeypatch.setattr(github, "is_installed", lambda: True)
    monkeypatch.setattr(github, "is_authenticated", lambda: True)
    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "git" in result.output
    assert "gh" in result.output


def test_doctor_fails_when_gh_not_authenticated(monkeypatch):
    """arc doctor exits 1 when gh is not authenticated."""
    from click.testing import CliRunner

    from arc import git, github
    from arc.cli import cli

    monkeypatch.setattr(git, "is_installed", lambda: True)
    monkeypatch.setattr(github, "is_installed", lambda: True)
    monkeypatch.setattr(github, "is_authenticated", lambda: False)
    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 1
    assert "gh auth login" in result.output


# ---------------------------------------------------------------------------
# arc restack
# ---------------------------------------------------------------------------


def test_restack_rebases_branch_onto_parent(arc_root, monkeypatch):
    from arc import git as _git
    from arc import github as _gh
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_authenticated", lambda: True)
    rebase_calls = []
    monkeypatch.setattr(
        _git, "rebase", lambda onto: rebase_calls.append(onto) or type("R", (), {"returncode": 0})()
    )
    monkeypatch.setattr(_git, "checkout", lambda b: None)
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/b")
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [
                {"name": "feat/a", "pr_number": None, "revision": 0},
                {"name": "feat/b", "pr_number": None, "revision": 0},
            ],
        },
    )
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["restack", "feat/b"])
    assert result.exit_code == 0
    assert "feat/a" in rebase_calls


# ---------------------------------------------------------------------------
# Task 9: conflict prediction in arc sync
# ---------------------------------------------------------------------------


def test_sync_warns_on_predicted_conflicts(arc_root, monkeypatch):
    from arc import conflicts as _c
    from arc import git as _git
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [
                {"name": "feat/a", "pr_number": None, "revision": 0},
                {"name": "feat/b", "pr_number": None, "revision": 0},
            ],
        },
    )
    monkeypatch.setattr(_git, "fetch", lambda remote="origin": None)
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/a")
    monkeypatch.setattr(_git, "branch_exists", lambda b: False)
    monkeypatch.setattr(_git, "is_squash_merged", lambda root, branch, base: False)
    monkeypatch.setattr(
        _c,
        "predict_conflicts",
        lambda data, root: [{"branch": "feat/b", "parent": "feat/a", "shared_files": ["api.py"]}],
    )
    monkeypatch.setattr(_git, "rebase", lambda onto: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(_git, "checkout", lambda b: None)
    monkeypatch.setattr(_git, "is_ancestor", lambda a, b: True)
    monkeypatch.setattr(_git, "get_sha", lambda ref: "abc")
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["sync"])
    assert "conflict" in result.output.lower()
    assert "feat/b" in result.output
    assert "api.py" in result.output


# ---------------------------------------------------------------------------
# Task 10: squash-merge recovery in arc sync
# ---------------------------------------------------------------------------


def test_sync_detects_squash_merged_branch(arc_root, monkeypatch):
    from arc import conflicts as _c
    from arc import git as _git
    from arc.state import load as _load
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [
                {"name": "feat/a", "pr_number": 10, "revision": 1},
                {"name": "feat/b", "pr_number": 11, "revision": 1},
            ],
        },
    )
    monkeypatch.setattr(_git, "fetch", lambda remote="origin": None)
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/b")
    monkeypatch.setattr(_git, "is_squash_merged", lambda root, branch, base: branch == "feat/a")
    monkeypatch.setattr(_git, "is_ancestor", lambda a, b: True)
    monkeypatch.setattr(_git, "rebase", lambda onto: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(_git, "checkout", lambda b: None)
    monkeypatch.setattr(_git, "branch_exists", lambda b: True)
    monkeypatch.setattr(_git, "delete_branch", lambda b: None)
    monkeypatch.setattr(_c, "predict_conflicts", lambda d, r: [])
    monkeypatch.setattr(_git, "get_sha", lambda ref: "abc")
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["sync", "-q"])
    assert result.exit_code == 0
    data = _load(arc_root)
    branch_names = [b["name"] for b in data["branches"]]
    assert "feat/a" not in branch_names
    assert "feat/b" in branch_names


# ---------------------------------------------------------------------------
# Task 11: arc stack analyze + async hints in arc submit
# ---------------------------------------------------------------------------


def test_stack_analyze_shows_safe_to_land(arc_root, monkeypatch):
    from arc import github as _gh
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [
                {"name": "feat/a", "pr_number": 10, "revision": 1},
                {"name": "feat/b", "pr_number": 11, "revision": 1},
            ],
        },
    )
    monkeypatch.setattr(
        _gh,
        "get_pr_status",
        lambda n: (
            {"approved": True, "ci_passing": True, "draft": False, "in_merge_queue": False}
            if n == 10
            else {"approved": False, "ci_passing": True, "draft": False, "in_merge_queue": False}
        ),
    )
    monkeypatch.setattr("arc.git.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: True)
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["stack", "analyze"])
    assert result.exit_code == 0
    assert "feat/a" in result.output
    assert "feat/b" in result.output


def test_submit_prints_async_hint_when_parent_in_merge_queue(arc_root, monkeypatch):
    from arc import git as _git
    from arc import github as _gh
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_authenticated", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [
                {"name": "feat/a", "pr_number": 10, "revision": 1},
                {"name": "feat/b", "pr_number": None, "revision": 0},
            ],
        },
    )
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/b")
    monkeypatch.setattr(_git, "get_commit_subject", lambda ref="HEAD": "add feature b")
    monkeypatch.setattr(_git, "get_commit_body", lambda ref="HEAD": "")
    monkeypatch.setattr(_git, "force_push", lambda branches, remote="origin": None)
    monkeypatch.setattr(_git, "branch_exists_remote", lambda b: True)
    monkeypatch.setattr(_git, "commit_count", lambda base, branch: 1)
    monkeypatch.setattr(_gh, "get_pr", lambda b: None)
    monkeypatch.setattr(
        _gh,
        "create_pr",
        lambda branch, base, title, body, draft=True: {
            "number": 11,
            "url": "https://github.com/x/y/pull/11",
        },
    )
    monkeypatch.setattr(
        _gh,
        "get_pr_status",
        lambda n: {"approved": True, "ci_passing": True, "draft": False, "in_merge_queue": True},
    )
    monkeypatch.setattr("arc.cli._is_tty", lambda: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["submit", "--open"])
    assert "safe to build on" in result.output.lower() or "merge queue" in result.output.lower()


# ---------------------------------------------------------------------------
# arc completions
# ---------------------------------------------------------------------------


def test_completions_prints_script(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type("R", (), {"stdout": "complete -F _arc arc\n", "returncode": 0})(),
    )
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["completions", "bash"])
    assert result.exit_code == 0
    assert len(result.output) > 0


# ---------------------------------------------------------------------------
# arc schema
# ---------------------------------------------------------------------------


def test_schema_returns_valid_json(monkeypatch):
    import json

    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["schema", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["type"] == "object"
    assert "branches" in data["properties"]


# ---------------------------------------------------------------------------
# arc config
# ---------------------------------------------------------------------------


def test_config_list_empty(arc_root, monkeypatch):
    monkeypatch.chdir(arc_root)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["config", "list"])
    assert result.exit_code == 0


def test_config_set_and_get(arc_root, monkeypatch):
    monkeypatch.chdir(arc_root)
    from click.testing import CliRunner

    from arc.cli import cli

    CliRunner().invoke(cli, ["config", "set", "feedback.enabled", "false"])
    result = CliRunner().invoke(cli, ["config", "get", "feedback.enabled"])
    assert result.exit_code == 0
    assert "False" in result.output
