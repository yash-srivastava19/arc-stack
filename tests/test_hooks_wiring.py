"""Integration tests: file-based lifecycle hooks wired into arc commands."""

import json as _json

import pytest
from click.testing import CliRunner

from arc.cli import cli
from arc.commands import _shared

pytestmark = pytest.mark.unit


def _write_state(tmp_path, branches=None):
    (tmp_path / ".arc").mkdir(exist_ok=True)
    data = {
        "version": 1,
        "base": "main",
        "prefix": None,
        "branches": branches
        if branches is not None
        else [
            {"name": "feat/a", "pr_number": 41, "revision": 1},
            {"name": "feat/b", "pr_number": 42, "revision": 1},
        ],
        "metadata": {},
    }
    (tmp_path / ".arc" / "state.json").write_text(_json.dumps(data))
    return data


def _write_hook(tmp_path, event, script, executable=True):
    hooks_dir = tmp_path / ".arc" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir / event
    path.write_text(f"#!/bin/sh\n{script}\n")
    if executable:
        path.chmod(0o755)
    return path


def test_run_lifecycle_hook_noop_without_hook_file(tmp_path):
    data = _write_state(tmp_path)
    _shared.run_lifecycle_hook(tmp_path, data, "pre-push", branch="feat/a")


def test_run_lifecycle_hook_gate_failure_exits_7(tmp_path):
    data = _write_state(tmp_path)
    _write_hook(tmp_path, "pre-push", "exit 1")
    with pytest.raises(SystemExit) as exc:
        _shared.run_lifecycle_hook(tmp_path, data, "pre-push", branch="feat/a")
    assert exc.value.code == 7


def test_run_lifecycle_hook_notify_failure_continues(tmp_path):
    data = _write_state(tmp_path)
    _write_hook(tmp_path, "post-push", "exit 1")
    _shared.run_lifecycle_hook(tmp_path, data, "post-push", branch="feat/a")


def test_run_lifecycle_hook_skip_bypasses_gate(tmp_path):
    data = _write_state(tmp_path)
    _write_hook(tmp_path, "pre-push", "exit 1")
    _shared.run_lifecycle_hook(tmp_path, data, "pre-push", branch="feat/a", skip=True)


def test_run_lifecycle_hook_passes_context(tmp_path):
    data = _write_state(tmp_path)
    capture = tmp_path / "captured"
    _write_hook(tmp_path, "pre-push", f'echo "$ARC_EVENT|$ARC_BRANCH|$ARC_PR_NUMBER" > "{capture}"')
    _shared.run_lifecycle_hook(tmp_path, data, "pre-push", branch="feat/a", extra={"pr_number": 41})
    assert capture.read_text().strip() == "pre-push|feat/a|41"


def test_push_pre_push_gate_aborts_before_push(tmp_path):
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "pre-push", "exit 1")
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.get_sha", return_value="abc1234567890"),
        patch("arc.git.force_push") as mock_push,
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["push"])
    assert result.exit_code == 7
    mock_push.assert_not_called()


def test_push_skip_hooks_bypasses_gate(tmp_path):
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "pre-push", "exit 1")
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.get_sha", return_value="abc1234567890"),
        patch("arc.git.force_push") as mock_push,
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["push", "--skip-hooks"])
    assert result.exit_code == 0
    mock_push.assert_called_once()


def test_push_post_push_failure_does_not_fail_command(tmp_path):
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "post-push", "exit 1")
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.get_sha", return_value="abc1234567890"),
        patch("arc.git.force_push"),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["push"])
    assert result.exit_code == 0


def test_sync_dry_run_does_not_fire_hooks(tmp_path):
    """Dry-run never fires hooks — consistent with push/submit/land."""
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "pre-sync", "exit 1")
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.branch_exists", return_value=True),
        patch("arc.git.is_squash_merged", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["sync", "--dry-run"])
    assert result.exit_code == 0


def test_sync_pre_sync_gate_aborts_before_fetch(tmp_path):
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "pre-sync", "exit 1")
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.fetch") as mock_fetch,
    ):
        result = CliRunner().invoke(cli, ["sync"])
    assert result.exit_code == 7
    mock_fetch.assert_not_called()


def test_sync_post_sync_fires_after_rebase_chain(tmp_path):
    from unittest.mock import MagicMock, patch

    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": None, "revision": 1}])
    capture = tmp_path / "captured"
    _write_hook(tmp_path, "post-sync", f'echo "$ARC_EVENT" > "{capture}"')
    rebase_ok = MagicMock(returncode=0)
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.fetch"),
        patch("arc.git.branch_exists", return_value=True),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.git.get_sha", return_value="abc1234567890"),
        patch("arc.git.checkout"),
        patch("arc.git.rebase_fork_point", return_value=rebase_ok),
        patch("arc.commands.sync.tip.sync_tip_branch"),
    ):
        result = CliRunner().invoke(cli, ["sync"])
    assert result.exit_code == 0
    assert capture.read_text().strip() == "post-sync"


def _patched_submit_env(tmp_path, existing_pr=None):
    from unittest.mock import patch

    return (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.get_commit_subject", return_value="subject"),
        patch("arc.git.get_commit_body", return_value="body"),
        patch("arc.git.commit_count", return_value=1),
        patch("arc.github.get_pr", return_value=existing_pr),
        patch(
            "arc.github.create_pr",
            return_value={"number": 99, "url": "https://github.com/x/y/pull/99"},
        ),
        patch(
            "arc.github.get_pr_status",
            return_value={"approved": False, "in_merge_queue": False},
        ),
    )


def test_submit_pre_submit_file_hook_gate_aborts(tmp_path):
    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": None, "revision": 0}])
    _write_hook(tmp_path, "pre-submit", "exit 1")
    p = _patched_submit_env(tmp_path)
    with p[0], p[1], p[2], p[3], p[4], p[5] as mock_create, p[6]:
        result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code == 7
    mock_create.assert_not_called()


def test_submit_post_submit_receives_pr_context(tmp_path):
    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": None, "revision": 0}])
    capture = tmp_path / "captured"
    _write_hook(tmp_path, "post-submit", f'echo "$ARC_PR_NUMBER|$ARC_PR_URL" > "{capture}"')
    p = _patched_submit_env(tmp_path)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code == 0
    assert capture.read_text().strip() == "99|https://github.com/x/y/pull/99"


def test_submit_post_submit_fires_on_update_path(tmp_path):
    """post-submit must also fire when the PR already exists (update, not create)."""
    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": 55, "revision": 2}])
    capture = tmp_path / "captured"
    _write_hook(tmp_path, "post-submit", f'echo "$ARC_PR_NUMBER|$ARC_PR_URL" > "{capture}"')
    existing = {"number": 55, "url": "https://github.com/x/y/pull/55", "state": "OPEN"}
    p = _patched_submit_env(tmp_path, existing_pr=existing)
    from unittest.mock import patch

    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], patch("arc.github.update_pr_body"):
        result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code == 0
    assert capture.read_text().strip() == "55|https://github.com/x/y/pull/55"


def test_gate_failure_json_payload_shape(tmp_path):
    """--json gate failure emits the structured error envelope on stdout."""
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "pre-push", "exit 1")
    with (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.current_branch", return_value="feat/a"),
        patch("arc.git.get_sha", return_value="abc1234567890"),
        patch("arc.git.force_push"),
        patch("arc.git.is_squash_merged", return_value=False),
        patch("arc.github.pr_is_merged", return_value=False),
    ):
        result = CliRunner().invoke(cli, ["push", "--json"])
    assert result.exit_code == 7
    payload = _json.loads(result.output[result.output.index("{") :])
    assert payload["ok"] is False
    assert payload["exit_code"] == 7
    assert "pre-push hook failed" in payload["error"]
    assert "--skip-hooks" in payload["hint"]


def test_submit_legacy_config_hooks_still_work(tmp_path):
    """Backward compat: hooks.pre-submit shell commands in .arc/config.json."""
    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": None, "revision": 0}])
    (tmp_path / ".arc" / "config.json").write_text(
        _json.dumps({"hooks": {"pre-submit": ["exit 1"]}})
    )
    p = _patched_submit_env(tmp_path)
    with p[0], p[1], p[2], p[3], p[4], p[5] as mock_create, p[6]:
        result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code == 7
    mock_create.assert_not_called()


def _patched_land_env(tmp_path):
    from unittest.mock import patch

    return (
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.github.pr_is_merged", return_value=True),
        patch("arc.github.get_merge_commit_sha", return_value=None),
        patch("arc.git.is_ancestor", return_value=True),
        patch("arc.git.get_sha", return_value="abc1234567890"),
        patch("arc.git.checkout"),
        patch("arc.git.delete_branch"),
    )


def test_land_pre_land_gate_aborts_before_branch_delete(tmp_path):
    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": 41, "revision": 1}])
    _write_hook(tmp_path, "pre-land", "exit 1")
    p = _patched_land_env(tmp_path)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as mock_delete:
        result = CliRunner().invoke(cli, ["land", "feat/a", "--force"])
    assert result.exit_code == 7
    mock_delete.assert_not_called()


def test_land_post_land_fires_with_pr_number(tmp_path):
    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": 41, "revision": 1}])
    capture = tmp_path / "captured"
    _write_hook(tmp_path, "post-land", f'echo "$ARC_PR_NUMBER" > "{capture}"')
    p = _patched_land_env(tmp_path)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        result = CliRunner().invoke(cli, ["land", "feat/a", "--force"])
    assert result.exit_code == 0
    assert capture.read_text().strip() == "41"


def test_submit_gate_failure_midstack_persists_created_prs(tmp_path):
    """If pre-submit passes for branch 1 (PR created) then fails for branch 2,
    branch 1's pr_number must be persisted to state.json."""
    import json as _json_inner

    _write_state(
        tmp_path,
        branches=[
            {"name": "feat/a", "pr_number": None, "revision": 0},
            {"name": "feat/b", "pr_number": None, "revision": 0},
        ],
    )
    # Hook exits 0 for feat/a, 1 for any other branch
    _write_hook(tmp_path, "pre-submit", '[ "$ARC_BRANCH" = "feat/a" ] && exit 0; exit 1')
    p = _patched_submit_env(tmp_path)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code == 7
    saved = _json_inner.loads((tmp_path / ".arc" / "state.json").read_text())
    branches_by_name = {b["name"]: b for b in saved["branches"]}
    assert branches_by_name["feat/a"]["pr_number"] == 99
    assert branches_by_name["feat/b"]["pr_number"] is None


def test_submit_update_path_heals_missing_pr_number(tmp_path):
    """Re-running submit when GitHub has a PR but state.json doesn't must persist it."""
    import json as _json_inner
    from unittest.mock import patch

    _write_state(tmp_path, branches=[{"name": "feat/a", "pr_number": None, "revision": 0}])
    existing = {"number": 55, "url": "https://github.com/x/y/pull/55", "state": "OPEN"}
    p = _patched_submit_env(tmp_path, existing_pr=existing)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], patch("arc.github.update_pr_body"):
        result = CliRunner().invoke(cli, ["submit"])
    assert result.exit_code == 0
    saved = _json_inner.loads((tmp_path / ".arc" / "state.json").read_text())
    branch = next(b for b in saved["branches"] if b["name"] == "feat/a")
    assert branch["pr_number"] == 55


def test_init_scaffolds_hooks_dir(tmp_path):
    import os
    from unittest.mock import patch

    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
        patch("arc.git.default_branch", return_value="main"),
    ):
        result = CliRunner().invoke(cli, ["init"])
    assert result.exit_code == 0
    hooks_dir = tmp_path / ".arc" / "hooks"
    assert (hooks_dir / "README.md").exists()
    assert (hooks_dir / "pre-submit.sample").exists()
    assert (hooks_dir / "post-land.sample").exists()
    assert not os.access(hooks_dir / "pre-submit.sample", os.X_OK)


def test_doctor_warns_on_non_executable_hook(tmp_path):
    from unittest.mock import patch

    _write_state(tmp_path)
    _write_hook(tmp_path, "pre-submit", "exit 0", executable=False)
    with (
        patch("arc.git.is_installed", return_value=True),
        patch("arc.github.is_installed", return_value=True),
        patch("arc.github.is_authenticated", return_value=True),
        patch("arc.git.find_repo_root", return_value=tmp_path),
    ):
        result = CliRunner().invoke(cli, ["doctor"])
    assert "pre-submit" in result.output
    assert "chmod +x" in result.output
