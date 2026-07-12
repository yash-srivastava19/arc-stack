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
    from arc import __version__

    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    # Guard against the hardcoded-literal regression (shipped 0.4.0 reporting "0.3.2")
    assert "0.3.2" not in result.output


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
        patch("arc.commands.stack.tip.sync_tip_branch"),
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


def test_new_rejects_reserved_tip_name(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["new", "arc-tip"])
    assert result.exit_code == 1
    assert "reserved" in result.output.lower()


def test_add_rejects_reserved_tip_name(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.branch_exists", return_value=True),
    ):
        result = runner.invoke(cli, ["add", "arc-tip"])
    assert result.exit_code == 1
    assert "reserved" in result.output.lower()


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
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)  # force human-readable output
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
        patch("arc.commands._shared._is_tty", return_value=True),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "arc sync" in result.output


def test_status_hints_sync_when_remote_ahead(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.remote_ahead_count", return_value=2),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.commands._shared._is_tty", return_value=True),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "arc sync" in result.output
    assert "ahead by 2" in result.output


def test_status_hints_rebase_when_only_local_drift(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=False),
        patch("arc.git.remote_ahead_count", return_value=0),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.commands._shared._is_tty", return_value=True),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "arc rebase" in result.output


def test_status_no_sync_rebase_hint_when_clean(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.remote_ahead_count", return_value=0),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.commands._shared._is_tty", return_value=True),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "arc sync" not in result.output
    assert "arc rebase" not in result.output


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

    def fake_rebase_fp(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch"),
        patch("arc.git.rebase_fork_point", side_effect=fake_rebase_fp),
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
        patch("arc.git.rebase_fork_point", return_value=conflict_result),
        patch("arc.git.checkout"),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.conflicted_files", return_value=["src/auth.py"]),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 3
    assert "Conflict in" in result.output
    assert "arc rebase --continue" in result.output
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    assert state_path.exists()


# ---------------------------------------------------------------------------
# Task 11: arc push
# ---------------------------------------------------------------------------


def test_push_force_pushes_all_branches(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.force_push") as mock_push,
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
        result = runner.invoke(cli, ["push"])
    assert result.exit_code == 0
    mock_push.assert_called_once_with(["feat/auth", "feat/api"])


def test_push_skips_merged_branches(tmp_path):
    """arc push silently skips branches whose PR is already merged."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    # feat/auth (pr_number=42) is merged; feat/api (no PR) is not squash-merged
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.force_push") as mock_push,
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=True),
    ):
        result = runner.invoke(cli, ["push"])
    assert result.exit_code == 0
    # Only feat/api should be pushed (feat/auth's PR is merged; feat/api has no pr_number)
    mock_push.assert_called_once_with(["feat/api"])
    assert "already merged" in result.output


def test_push_skips_squash_merged_branches(tmp_path):
    """arc push skips branches detected as squash-merged into base via git cherry."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()

    def _is_squash_merged(_root, branch, _base):
        return branch == "feat/auth"

    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.force_push") as mock_push,
        patch("arc.git.is_squash_merged", side_effect=_is_squash_merged),
    ):
        result = runner.invoke(cli, ["push"])
    assert result.exit_code == 0
    mock_push.assert_called_once_with(["feat/api"])


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
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.force_push"),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
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


def test_submit_retargets_stale_pr_base(tmp_path):
    """arc submit updates PR base when the stack position changed since the last submit."""
    _write_state_with_branches(tmp_path)
    retargeted = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_commit_subject", return_value="feat"),
        patch("arc.git.get_commit_body", return_value=""),
        patch("arc.git.commit_count", return_value=1),
        patch(
            "arc.github.get_pr",
            # PR base is currently "old-base" but arc computes it should be "main"
            return_value={
                "number": 42,
                "url": "https://gh/42",
                "state": "OPEN",
                "baseRefName": "old-base",
            },
        ),
        patch("arc.github.update_pr_body"),
        patch(
            "arc.github.update_pr_base",
            side_effect=lambda n, b: retargeted.append((n, b)) or True,
        ),
    ):
        result = runner.invoke(cli, ["submit"])
    assert result.exit_code == 0, result.output
    assert (42, "main") in retargeted, "PR should be retargeted to 'main' (the computed base)"


def test_submit_no_retarget_when_base_unchanged(tmp_path):
    """arc submit does not call update_pr_base when the PR base already matches."""
    # Single-branch stack: computed base is "main", PR already targets "main"
    _write_state(tmp_path, branches=[{"name": "feat/auth", "pr_number": 42, "revision": 1}])
    retargeted = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_commit_subject", return_value="feat"),
        patch("arc.git.get_commit_body", return_value=""),
        patch("arc.git.commit_count", return_value=1),
        patch(
            "arc.github.get_pr",
            return_value={
                "number": 42,
                "url": "https://gh/42",
                "state": "OPEN",
                "baseRefName": "main",  # already correct
            },
        ),
        patch("arc.github.update_pr_body"),
        patch(
            "arc.github.update_pr_base",
            side_effect=lambda n, b: retargeted.append((n, b)) or True,
        ),
    ):
        result = runner.invoke(cli, ["submit"])
    assert result.exit_code == 0, result.output
    assert retargeted == [], "no retarget call when base is already correct"


def test_status_warns_when_edit_in_progress(tmp_path):
    """arc status prints a warning when .arc/edit-in-progress.json exists."""
    _write_state_with_branches(tmp_path)
    (tmp_path / ".arc" / "edit-in-progress.json").write_text('{"target": "feat/auth"}')
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=1),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["status"])
    assert "edit" in result.output.lower()
    assert "continue" in result.output.lower() or "abort" in result.output.lower()


def test_status_no_warning_without_edit_state(tmp_path):
    """arc status does not print edit warning when no edit is in progress."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=1),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["status"])
    assert "edit-in-progress" not in result.output
    assert "arc edit --continue" not in result.output


def test_status_warns_on_paused_cascade(tmp_path, monkeypatch):
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    _write_state_with_branches(tmp_path)
    (tmp_path / ".arc" / "rebase-in-progress.json").write_text("{}")
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=2),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.remote_ahead_count", return_value=0),
        patch("arc.github.get_pr", return_value=None),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "rebase" in result.output.lower()
    assert "arc rebase --continue" in result.output


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


def _write_state_with_pr_above(tmp_path):
    """Stack where both feat/auth AND feat/api have PRs — for retarget tests."""
    return _write_state(
        tmp_path,
        prefix="feat",
        branches=[
            {"name": "feat/auth", "pr_number": 42, "revision": 1},
            {"name": "feat/api", "pr_number": 43, "revision": 1},
        ],
    )


def test_land_retargets_above_prs_to_parent(tmp_path):
    """arc land retargets above-branch PRs to parent before deleting branch."""
    _write_state_with_pr_above(tmp_path)
    retarget_calls = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value="squash123"),
        patch("arc.git.get_sha", return_value="old_sha"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_onto", return_value=MagicMock(returncode=0)),
        patch("arc.git.delete_branch"),
        patch("arc.git.is_ancestor", return_value=False),
        patch("arc.github.get_pr_state", return_value="OPEN") as mock_state,
        patch(
            "arc.github.update_pr_base",
            side_effect=lambda n, b: retarget_calls.append((n, b)) or True,
        ),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0, result.output
    # feat/api (PR #43) should be retargeted to "main" (the parent of feat/auth)
    assert (43, "main") in retarget_calls
    mock_state.assert_called_once_with(43)


def test_land_reopens_and_retargets_auto_closed_prs(tmp_path):
    """arc land reopens GitHub-auto-closed child PRs then retargets them."""
    _write_state_with_pr_above(tmp_path)
    reopen_calls = []
    retarget_calls = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value="squash123"),
        patch("arc.git.get_sha", return_value="old_sha"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_onto", return_value=MagicMock(returncode=0)),
        patch("arc.git.delete_branch"),
        patch("arc.git.is_ancestor", return_value=False),
        # GitHub auto-closed PR #43 because its base branch was deleted
        patch("arc.github.get_pr_state", return_value="CLOSED"),
        patch("arc.github.reopen_pr", side_effect=lambda n: reopen_calls.append(n) or True),
        patch(
            "arc.github.update_pr_base",
            side_effect=lambda n, b: retarget_calls.append((n, b)) or True,
        ),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0, result.output
    assert 43 in reopen_calls, "should reopen the auto-closed PR"
    assert (43, "main") in retarget_calls, "should retarget to parent after reopen"


def test_land_auto_promotes_next_pr_to_ready(tmp_path):
    """arc land marks the new bottom-of-stack PR as ready after landing."""
    _write_state_with_pr_above(tmp_path)
    promoted = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value=None),
        patch("arc.git.get_sha", return_value="sha"),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.git.delete_branch"),
        patch("arc.github.get_pr_state", return_value="OPEN"),
        patch("arc.github.update_pr_base", return_value=True),
        patch("arc.github.mark_pr_ready", side_effect=lambda n: promoted.append(n)),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0, result.output
    assert 43 in promoted, "feat/api's PR #43 should be promoted to ready"


def test_land_no_auto_promote_when_disabled_in_config(tmp_path):
    """auto_promote_on_land: false in config suppresses the mark-ready call."""
    _write_state_with_pr_above(tmp_path)
    (tmp_path / ".arc" / "config.json").write_text(_json.dumps({"auto_promote_on_land": False}))
    promoted = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value=None),
        patch("arc.git.get_sha", return_value="sha"),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.git.delete_branch"),
        patch("arc.github.get_pr_state", return_value="OPEN"),
        patch("arc.github.update_pr_base", return_value=True),
        patch("arc.github.mark_pr_ready", side_effect=lambda n: promoted.append(n)),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0, result.output
    assert promoted == [], "mark_pr_ready should not be called when auto_promote_on_land is false"


def test_land_no_auto_promote_when_no_above_branches(tmp_path):
    """arc land does not call mark_pr_ready when there are no branches above."""
    _write_state(
        tmp_path,
        branches=[{"name": "feat/auth", "pr_number": 42, "revision": 1}],
    )
    promoted = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value=None),
        patch("arc.git.get_sha", return_value="sha"),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.checkout"),
        patch("arc.git.delete_branch"),
        patch("arc.github.mark_pr_ready", side_effect=lambda n: promoted.append(n)),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0, result.output
    assert promoted == [], "no mark_pr_ready when stack has no branches above"


def test_land_exits_3_on_conflict_and_saves_state(tmp_path):
    _write_state_with_branches(tmp_path)
    conflict_result = MagicMock(returncode=1)

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value=None),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_fork_point", return_value=conflict_result),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.conflicted_files", return_value=["api.py"]),
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 3
    assert "arc rebase --continue" in result.output
    assert "arc land" in result.output
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    assert state_path.exists()


def test_sync_uses_fork_point_rebase(tmp_path):
    """arc sync uses git rebase --fork-point so amended parent commits don't replay."""
    _write_state(
        tmp_path,
        branches=[{"name": "feat/a", "pr_number": None, "revision": 0}],
    )
    fork_point_calls = []
    plain_rebase_calls = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.fetch"),
        patch("arc.git.refresh_index"),
        patch("arc.git.branch_exists", return_value=True),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.checkout"),
        patch(
            "arc.git.rebase_fork_point",
            side_effect=lambda _: fork_point_calls.append(True) or MagicMock(returncode=0),
        ),
        patch(
            "arc.git.rebase",
            side_effect=lambda _: plain_rebase_calls.append(True) or MagicMock(returncode=0),
        ),
        patch("arc.commands.sync.tip.sync_tip_branch"),
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 0, result.output
    assert fork_point_calls, "sync must call rebase_fork_point"
    assert not plain_rebase_calls, "sync must not fall back to plain rebase"


def test_sync_refresh_index_called_before_rebase(tmp_path):
    """arc sync calls git.refresh_index before rebasing to clear phantom mtime diffs."""
    _write_state(
        tmp_path,
        branches=[{"name": "feat/a", "pr_number": None, "revision": 0}],
    )
    call_order = []
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.fetch", side_effect=lambda: call_order.append("fetch")),
        patch("arc.git.refresh_index", side_effect=lambda: call_order.append("refresh")),
        patch("arc.git.branch_exists", return_value=True),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.checkout"),
        patch(
            "arc.git.rebase_fork_point",
            side_effect=lambda _: call_order.append("rebase") or MagicMock(returncode=0),
        ),
        patch("arc.commands.sync.tip.sync_tip_branch"),
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 0, result.output
    assert call_order.index("refresh") < call_order.index("rebase"), (
        "refresh_index must run before rebase"
    )


def test_sync_pre_rebase_failure_shows_clear_error(tmp_path):
    """arc sync shows 'Could not start rebase' (not 'Conflict') for pre-condition failures."""
    _write_state(
        tmp_path,
        branches=[{"name": "feat/a", "pr_number": None, "revision": 0}],
    )
    failed_result = MagicMock(
        returncode=128, stderr="error: cannot rebase: You have unstaged changes."
    )
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.fetch"),
        patch("arc.git.refresh_index"),
        patch("arc.git.branch_exists", return_value=True),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_fork_point", return_value=failed_result),
        # Not mid-rebase: rebase never started
        patch("arc.git.is_mid_rebase", return_value=False),
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 3
    assert "conflict" not in result.output.lower(), (
        "should not say 'conflict' for a pre-rebase failure"
    )
    assert "could not start rebase" in result.output.lower()


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
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", side_effect=fake_rebase),
    ):
        result = runner.invoke(cli, ["drop", "feat/auth", "-f"])
    assert result.exit_code == 0
    data = _json.loads((tmp_path / ".arc" / "state.json").read_text())
    assert all(b["name"] != "feat/auth" for b in data["branches"])
    assert "main" in rebase_calls  # feat/api rebased onto main


def test_drop_exits_3_on_conflict_and_saves_state(tmp_path):
    _write_state_with_branches(tmp_path)
    conflict_result = MagicMock(returncode=1)

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", return_value=conflict_result),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.conflicted_files", return_value=["api.py"]),
    ):
        result = runner.invoke(cli, ["drop", "feat/auth", "-f"])
    assert result.exit_code == 3
    assert "arc rebase --continue" in result.output
    assert "arc drop" in result.output
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    assert state_path.exists()


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
        patch("arc.git.rebase_fork_point") as mock_rebase,
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

    def fake_rebase_fp(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", side_effect=fake_rebase_fp),
    ):
        result = runner.invoke(cli, ["rebase"])
    assert result.exit_code == 0
    assert rebase_calls == ["main", "feat/auth"]


def test_rebase_upstack(tmp_path):
    _write_state_with_branches(tmp_path)
    rebase_calls = []

    def fake_rebase_fp(onto):
        rebase_calls.append(onto)
        r = MagicMock()
        r.returncode = 0
        return r

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", side_effect=fake_rebase_fp),
    ):
        result = runner.invoke(cli, ["rebase", "--upstack"])
    assert result.exit_code == 0
    assert "main" in rebase_calls


def test_rebase_exits_3_on_conflict_and_saves_state(tmp_path):
    _write_state_with_branches(tmp_path)
    conflict_result = MagicMock(returncode=1)

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", return_value=conflict_result),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.conflicted_files", return_value=["api.py"]),
    ):
        result = runner.invoke(cli, ["rebase"])
    assert result.exit_code == 3
    assert "Conflict in" in result.output
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    assert state_path.exists()


def test_rebase_continue_no_paused_state(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=False),
    ):
        result = runner.invoke(cli, ["rebase", "--continue"])
    assert result.exit_code == 3
    assert "no paused rebase" in result.output.lower()


def test_rebase_continue_completes_a_bare_restack_rebase(tmp_path):
    """arc restack leaves a bare (non-cascade) rebase paused on conflict;
    arc rebase --continue must still be able to finish it (regression test —
    this used to be a dead end after cascade.py redefined --continue to be
    cascade-state-driven)."""
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.rebase_continue", return_value=MagicMock(returncode=0)),
        patch("arc.commands.sync.tip.sync_tip_branch"),
    ):
        result = runner.invoke(cli, ["rebase", "--continue"])
    assert result.exit_code == 0
    assert "Rebase complete" in result.output


def test_rebase_continue_resumes_and_finishes(tmp_path):
    _write_state_with_branches(tmp_path)
    state = {
        "command": "rebase",
        "plan": [
            {"branch": "feat/auth", "onto": "main"},
            {"branch": "feat/api", "onto": "feat/auth"},
        ],
        "completed": [],
        "pre_shas": {"feat/auth": "s1", "feat/api": "s2"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(_json.dumps(state))

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.rebase_continue", return_value=MagicMock(returncode=0)),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.commands.sync.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["rebase", "--continue"])
    assert result.exit_code == 0
    assert "Rebase complete" in result.output
    assert not state_path.exists()
    mock_sync.assert_called_once()


def test_rebase_continue_sync_initiated_prunes_merged_branches(tmp_path):
    _write_state_with_branches(tmp_path)
    state = {
        "command": "sync",
        "plan": [{"branch": "feat/auth", "onto": "main"}],
        "completed": [],
        "pre_shas": {"feat/auth": "s1"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(_json.dumps(state))

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.rebase_continue", return_value=MagicMock(returncode=0)),
        patch("arc.github.pr_is_merged", return_value=False),
        patch("arc.commands.sync.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["rebase", "--continue"])
    assert result.exit_code == 0
    assert "Stack synced" in result.output
    mock_sync.assert_called_once()


def test_rebase_continue_sync_initiated_fires_post_sync_hook(tmp_path):
    _write_state_with_branches(tmp_path)
    state = {
        "command": "sync",
        "plan": [{"branch": "feat/auth", "onto": "main"}],
        "completed": [],
        "pre_shas": {"feat/auth": "s1"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(_json.dumps(state))

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=True),
        patch("arc.git.rebase_continue", return_value=MagicMock(returncode=0)),
        patch("arc.github.pr_is_merged", return_value=False),
        patch("arc.commands.sync.tip.sync_tip_branch"),
        patch("arc.commands.sync._shared.run_lifecycle_hook") as mock_hook,
        patch("arc.commands.sync._shared._maybe_print_periodic_hint") as mock_hint,
    ):
        result = runner.invoke(cli, ["rebase", "--continue"])
    assert result.exit_code == 0
    mock_hook.assert_called_once()
    assert mock_hook.call_args.args[2] == "post-sync"
    mock_hint.assert_called_once_with(tmp_path)


def test_rebase_abort_no_paused_state(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=False),
    ):
        result = runner.invoke(cli, ["rebase", "--abort"])
    assert result.exit_code == 0
    assert "no paused rebase" in result.output.lower()


def test_rebase_abort_restores_all_branches(tmp_path):
    _write_state_with_branches(tmp_path)
    state = {
        "command": "rebase",
        "plan": [
            {"branch": "feat/auth", "onto": "main"},
            {"branch": "feat/api", "onto": "feat/auth"},
        ],
        "completed": ["feat/auth"],
        "pre_shas": {"feat/auth": "s1", "feat/api": "s2"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(_json.dumps(state))

    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.rebase_abort") as mock_abort,
        patch("arc.git.checkout") as mock_checkout,
        patch("arc.git._run") as mock_run,
    ):
        result = runner.invoke(cli, ["rebase", "--abort"])
    assert result.exit_code == 0
    assert not state_path.exists()
    mock_abort.assert_called_once()
    mock_checkout.assert_any_call("feat/auth")
    mock_checkout.assert_any_call("feat/api")
    mock_run.assert_any_call(["git", "reset", "--hard", "s1"])
    mock_run.assert_any_call(["git", "reset", "--hard", "s2"])


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


def test_tip_creates_and_checks_out_arc_tip(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_sha", return_value="abc12345"),
        patch("arc.git.checkout_branch_at") as mock_checkout_at,
    ):
        result = runner.invoke(cli, ["tip"])
    assert result.exit_code == 0
    mock_checkout_at.assert_called_once_with("arc-tip", "abc12345")
    assert "arc-tip" in result.output


def test_tip_empty_stack(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["tip"])
    assert result.exit_code == 0
    assert "empty" in result.output.lower()


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
        patch("arc.commands._shared.random.randint", return_value=1),
        patch("arc.commands._shared._is_tty", return_value=True),
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
        patch("arc.commands._shared.random.randint", return_value=2),
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
        patch("arc.commands._shared.random.randint", return_value=1),
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
        patch("arc.commands._shared.random.randint", return_value=1),
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
        patch("arc.commands._shared._is_tty", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["status"])
    data = json.loads(result.output)
    assert "branches" in data


def test_status_no_init_gives_helpful_message(tmp_path, monkeypatch):
    """Running arc status without arc init should suggest arc init, not crash."""
    monkeypatch.setattr(
        "arc.commands._shared._is_tty", lambda: True
    )  # force human-readable error output
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


def test_doctor_warns_on_paused_cascade_mid_rebase(tmp_path):
    (tmp_path / ".arc").mkdir()
    (tmp_path / ".arc" / "state.json").write_text(
        _json.dumps({"version": 1, "base": "main", "prefix": None, "branches": [], "metadata": {}})
    )
    (tmp_path / ".arc" / "rebase-in-progress.json").write_text("{}")
    runner = CliRunner()
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=True),
    ):
        result = runner.invoke(cli, ["doctor"])
    assert "paused mid-cascade" in result.output.lower()


def test_doctor_warns_on_stale_cascade_state(tmp_path):
    (tmp_path / ".arc").mkdir()
    (tmp_path / ".arc" / "state.json").write_text(
        _json.dumps({"version": 1, "base": "main", "prefix": None, "branches": [], "metadata": {}})
    )
    (tmp_path / ".arc" / "rebase-in-progress.json").write_text("{}")
    runner = CliRunner(env={"COLUMNS": "200"})
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.is_mid_rebase", return_value=False),
    ):
        result = runner.invoke(cli, ["doctor"])
    assert "stale" in result.output.lower()
    assert "arc rebase --abort" in result.output


# ---------------------------------------------------------------------------
# arc restack
# ---------------------------------------------------------------------------


def test_restack_rebases_branch_onto_parent(arc_root, monkeypatch):
    from arc import git as _git
    from arc import github as _gh
    from arc import tip as _tip
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_authenticated", lambda: True)
    rebase_calls = []
    monkeypatch.setattr(
        _git,
        "rebase_fork_point",
        lambda onto: rebase_calls.append(onto) or type("R", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(_git, "checkout", lambda b: None)
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/b")
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    monkeypatch.setattr(_tip, "sync_tip_branch", lambda data: None)
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
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
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
    from arc import tip as _tip
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
    monkeypatch.setattr(_git, "rebase_fork_point", lambda onto: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(_git, "checkout", lambda b: None)
    monkeypatch.setattr(_git, "branch_exists", lambda b: True)
    monkeypatch.setattr(_git, "delete_branch", lambda b, force=False: None)
    monkeypatch.setattr(_c, "predict_conflicts", lambda d, r: [])
    monkeypatch.setattr(_git, "get_sha", lambda ref: "abc")
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    monkeypatch.setattr(_tip, "sync_tip_branch", lambda data: None)
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
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["stack", "analyze"])
    assert result.exit_code == 0
    assert "feat/a" in result.output
    assert "feat/b" in result.output


def test_stack_snapshot_json_shape(arc_root, monkeypatch):
    """arc stack snapshot --json returns base, current_branch, branches with pr_health, and analysis."""
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
    monkeypatch.setattr(_gh, "get_pr", lambda _: None)
    monkeypatch.setattr("arc.git.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: True)
    monkeypatch.setattr("arc.git.current_branch", lambda: "feat/a")
    monkeypatch.setattr("arc.git.commit_count", lambda base, branch: 1)
    monkeypatch.setattr("arc.git.is_ancestor", lambda a, b: True)

    result = CliRunner().invoke(cli, ["stack", "snapshot", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)

    assert payload["base"] == "main"
    assert "current_branch" in payload
    assert len(payload["branches"]) == 2

    branch_a = next(b for b in payload["branches"] if b["name"] == "feat/a")
    assert branch_a["pr_health"]["approved"] is True
    assert branch_a["pr_health"]["ci_passing"] is True

    branch_b = next(b for b in payload["branches"] if b["name"] == "feat/b")
    assert branch_b["pr_health"]["approved"] is False

    assert "critical_path" in payload["analysis"]
    assert "safe_to_land" in payload["analysis"]
    assert "blocked" in payload["analysis"]
    assert "feat/a" in payload["analysis"]["safe_to_land"]


def test_stack_snapshot_empty_stack_exits(arc_root, monkeypatch):
    """arc stack snapshot on an empty stack exits with code 1."""
    monkeypatch.chdir(arc_root)
    monkeypatch.setattr("arc.git.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_installed", lambda: True)
    monkeypatch.setattr("arc.github.is_authenticated", lambda: True)

    result = CliRunner().invoke(cli, ["stack", "snapshot", "--json"])
    assert result.exit_code != 0


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
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
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


# ---------------------------------------------------------------------------
# v0.3.1: --no-input global flag
# ---------------------------------------------------------------------------


def test_no_input_flag_exits_instead_of_prompting(arc_root, monkeypatch):
    """arc --no-input land exits 1 instead of prompting when --force not passed."""
    from arc import git as _git
    from arc import github as _gh
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_authenticated", lambda: True)
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [{"name": "feat/a", "pr_number": 10, "revision": 1}],
        },
    )
    monkeypatch.setattr(_git, "current_branch", lambda: "feat/a")
    monkeypatch.setattr(_gh, "pr_is_merged", lambda n: True)
    monkeypatch.setattr(_gh, "get_merge_commit_sha", lambda n: None)
    monkeypatch.setattr(_git, "get_sha", lambda ref: "abc1234")
    monkeypatch.setattr(_git, "is_ancestor", lambda a, d: True)

    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["--no-input", "land"])
    assert result.exit_code == 1
    assert "force" in result.output.lower() or "confirm" in result.output.lower()


def test_no_input_flag_drop_exits_instead_of_prompting(arc_root, monkeypatch):
    """arc --no-input drop exits 1 instead of prompting when --force not passed."""
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [{"name": "feat/a", "pr_number": None, "revision": 0}],
        },
    )

    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["--no-input", "drop", "feat/a"])
    assert result.exit_code == 1
    assert "force" in result.output.lower() or "confirm" in result.output.lower()


# ---------------------------------------------------------------------------
# v0.3.1: --verbose global flag
# ---------------------------------------------------------------------------


def test_verbose_flag_prints_git_commands(arc_root, monkeypatch):
    """arc --verbose status --plain exits 0 without crash."""
    from arc import git as _git
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr(_git, "current_branch", lambda: "main")
    # Ensure _VERBOSE is restored after this test (the CLI sets it as a module
    # side-effect, which would otherwise leak into subsequent tests).
    monkeypatch.setattr(_git, "_VERBOSE", False)
    _save(
        arc_root,
        {
            "version": 1,
            "base": "main",
            "prefix": None,
            "metadata": {},
            "branches": [],
        },
    )

    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["--verbose", "status", "--plain"])
    # verbose output goes to stderr — just verify exit 0 and no crash
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# v0.3.1: arc status merged-PR hint
# ---------------------------------------------------------------------------


def test_status_shows_merged_branch_hint(tmp_path, monkeypatch):
    """arc status shows a hint when a branch is merged."""
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
    _write_state(
        tmp_path,
        branches=[
            {"name": "feat/auth", "pr_number": 42, "revision": 1},
        ],
    )
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.commit_count", return_value=1),
        patch("arc.git.is_ancestor", return_value=True),
        patch(
            "arc.github.get_pr",
            return_value={"url": "https://github.com/o/r/pull/42", "state": "MERGED"},
        ),
    ):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "merged" in result.output.lower()
    assert "arc sync" in result.output


# ---------------------------------------------------------------------------
# v0.3.2: arc status stale PR base warning
# ---------------------------------------------------------------------------


def test_status_warns_on_stale_pr_base(arc_root, monkeypatch):
    """arc status warns when a branch's PR targets a stale base."""
    from arc import github as _gh
    from arc.state import save as _save

    monkeypatch.chdir(arc_root)
    monkeypatch.setattr("arc.commands._shared._is_tty", lambda: True)
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
    # feat/b should target feat/a but GitHub shows it targeting an old branch
    monkeypatch.setattr(
        _gh,
        "get_pr",
        lambda b: (
            {
                "number": 10,
                "baseRefName": "main",
                "state": "OPEN",
                "isDraft": False,
                "url": "https://github.com/x/y/pull/10",
                "mergedAt": None,
            }
            if b == "feat/a"
            else {
                "number": 11,
                "baseRefName": "feat/v031-commands",  # stale!
                "state": "OPEN",
                "isDraft": False,
                "url": "https://github.com/x/y/pull/11",
                "mergedAt": None,
            }
        ),
    )
    monkeypatch.setattr(_gh, "is_installed", lambda: True)
    monkeypatch.setattr(_gh, "is_authenticated", lambda: True)
    from arc import git as _git

    monkeypatch.setattr(_git, "current_branch", lambda: "feat/a")
    monkeypatch.setattr(_git, "commit_count", lambda base, branch: 1)
    monkeypatch.setattr(_git, "is_ancestor", lambda a, b: True)
    from click.testing import CliRunner

    from arc.cli import cli

    result = CliRunner().invoke(cli, ["status"])
    assert "stale" in result.output.lower() or "retarget" in result.output.lower()
    assert "feat/b" in result.output


def test_cli_command_inventory_unchanged():
    """The public CLI surface must not change during the v0.5.0 refactor."""
    expected = {
        "setup",
        "doctor",
        "completions",
        "upgrade",
        "schema",
        "config",
        "init",
        "new",
        "restack",
        "add",
        "status",
        "sync",
        "push",
        "submit",
        "land",
        "amend",
        "drop",
        "rebase",
        "checkout",
        "up",
        "down",
        "top",
        "bottom",
        "tip",
        "stack",
        "report",
        "dashboard",
    }
    assert set(cli.commands.keys()) == expected
    assert set(cli.commands["config"].commands.keys()) == {"get", "set", "list"}
    assert set(cli.commands["stack"].commands.keys()) == {"analyze", "snapshot"}


def test_new_calls_sync_tip_branch(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.create_branch"),
        patch("arc.commands.stack.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["new", "feat/x"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_add_calls_sync_tip_branch(tmp_path):
    _write_state(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.branch_exists", return_value=True),
        patch("arc.commands.stack.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["add", "feat/x"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_drop_calls_sync_tip_branch(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.commands.stack.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["drop", "feat/auth", "-f"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_sync_calls_sync_tip_branch(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.fetch"),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.github.get_pr", return_value=None),
        patch("arc.commands.sync.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_rebase_calls_sync_tip_branch(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/auth"),
        patch("arc.git.checkout"),
        patch("arc.git.get_sha", return_value="abc"),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.commands.sync.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["rebase"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_restack_calls_sync_tip_branch(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.commands._shared._check_setup", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.git.checkout"),
        patch("arc.commands.sync.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["restack", "feat/api"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_restack_hints_arc_edit_when_more_branches_above(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.commands._shared._check_setup", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.git.checkout"),
    ):
        result = runner.invoke(cli, ["restack", "feat/auth"])
    assert result.exit_code == 0
    assert "arc edit" in result.output


def test_restack_no_hint_when_at_stack_tip(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.commands._shared._check_setup", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.rebase_fork_point", return_value=MagicMock(returncode=0)),
        patch("arc.git.checkout"),
    ):
        result = runner.invoke(cli, ["restack", "feat/api"])
    assert result.exit_code == 0
    assert "arc edit" not in result.output


def test_land_calls_sync_tip_branch(tmp_path):
    _write_state_with_branches(tmp_path)
    runner = CliRunner()
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value="squash123"),
        patch("arc.git.get_sha", return_value="old_sha"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_onto", return_value=MagicMock(returncode=0)),
        patch("arc.git.delete_branch"),
        patch("arc.git.is_ancestor", return_value=False),
        patch("arc.commands.submit.tip.sync_tip_branch") as mock_sync,
    ):
        result = runner.invoke(cli, ["land", "feat/auth", "-f"])
    assert result.exit_code == 0
    mock_sync.assert_called_once()
