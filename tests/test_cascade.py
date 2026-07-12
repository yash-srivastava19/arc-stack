import json
from unittest.mock import MagicMock, patch

from arc import cascade


def mock_result(returncode=0, stderr=""):
    r = MagicMock()
    r.returncode = returncode
    r.stderr = stderr
    return r


def _plan(*pairs):
    return [{"branch": b, "onto": o} for b, o in pairs]


def test_run_cascade_empty_plan_is_done():
    result = cascade.run_cascade([], "/tmp/root", command="sync")
    assert result == {"ok": True, "state": "done", "command": "sync"}


def test_run_cascade_full_success(tmp_path):
    plan = _plan(("feat/a", "main"), ("feat/b", "feat/a"))
    with (
        patch("arc.cascade.git.get_sha", return_value="sha0"),
        patch("arc.cascade.git.checkout"),
        patch("arc.cascade.git.rebase_fork_point", return_value=mock_result(0)),
    ):
        result = cascade.run_cascade(plan, tmp_path, command="sync", quiet=True)
    assert result == {"ok": True, "state": "done", "command": "sync"}
    assert not (tmp_path / ".arc" / "rebase-in-progress.json").exists()


def test_run_cascade_real_conflict_saves_state_and_pauses(tmp_path):
    plan = _plan(("feat/a", "main"), ("feat/b", "feat/a"))

    def fake_rebase(onto):
        return mock_result(0) if onto == "main" else mock_result(1)

    with (
        patch("arc.cascade.git.get_sha", return_value="sha0"),
        patch("arc.cascade.git.checkout"),
        patch("arc.cascade.git.rebase_fork_point", side_effect=fake_rebase),
        patch("arc.cascade.git.is_mid_rebase", return_value=True),
        patch("arc.cascade.git.conflicted_files", return_value=["api.py"]),
    ):
        result = cascade.run_cascade(plan, tmp_path, command="rebase", quiet=True)

    assert result == {
        "ok": False,
        "state": "paused",
        "command": "rebase",
        "conflict_branch": "feat/b",
        "conflicted_files": ["api.py"],
        "exit_code": 3,
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    assert state_path.exists()
    saved = json.loads(state_path.read_text())
    assert saved["command"] == "rebase"
    assert saved["plan"] == plan
    assert saved["completed"] == ["feat/a"]
    assert saved["pre_shas"] == {"feat/a": "sha0", "feat/b": "sha0"}


def test_run_cascade_precondition_failure_rolls_back_no_state(tmp_path):
    plan = _plan(("feat/a", "main"))
    with (
        patch("arc.cascade.git.get_sha", return_value="sha0"),
        patch("arc.cascade.git.checkout") as mock_checkout,
        patch("arc.cascade.git.rebase_fork_point", return_value=mock_result(128, "dirty tree")),
        patch("arc.cascade.git.is_mid_rebase", return_value=False),
        patch("arc.cascade.git._run") as mock_run,
    ):
        result = cascade.run_cascade(plan, tmp_path, command="sync", quiet=True)

    assert result == {
        "ok": False,
        "state": "error",
        "branch": "feat/a",
        "message": "dirty tree",
        "exit_code": 3,
    }
    assert not (tmp_path / ".arc" / "rebase-in-progress.json").exists()
    # rollback checks out feat/a and resets it — confirms _rollback ran
    mock_checkout.assert_any_call("feat/a")
    mock_run.assert_any_call(["git", "reset", "--hard", "sha0"])


def test_load_state_raises_on_corrupt_json(tmp_path):
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not valid json")

    try:
        cascade.load_state(tmp_path)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "arc rebase --abort" in str(exc)


def test_continue_cascade_no_state_is_error():
    with patch("arc.cascade.git.is_mid_rebase", return_value=False):
        result = cascade.continue_cascade("/tmp/root")
    assert result == {
        "ok": False,
        "state": "error",
        "branch": "",
        "message": "No paused rebase to continue.",
        "exit_code": 3,
    }


def test_continue_cascade_falls_back_to_bare_rebase_when_no_cascade_state(tmp_path):
    with (
        patch("arc.cascade.git.is_mid_rebase", return_value=True),
        patch("arc.cascade.git.rebase_continue", return_value=mock_result(0)),
    ):
        result = cascade.continue_cascade(tmp_path)
    assert result == {"ok": True, "state": "done", "command": "rebase"}


def test_continue_cascade_bare_fallback_still_conflicted(tmp_path):
    with (
        patch("arc.cascade.git.is_mid_rebase", return_value=True),
        patch("arc.cascade.git.rebase_continue", return_value=mock_result(1)),
        patch("arc.cascade.git.current_branch", return_value="feat/x"),
        patch("arc.cascade.git.conflicted_files", return_value=["a.py"]),
    ):
        result = cascade.continue_cascade(tmp_path)
    assert result == {
        "ok": False,
        "state": "paused",
        "command": "rebase",
        "conflict_branch": "feat/x",
        "conflicted_files": ["a.py"],
        "exit_code": 3,
    }


def test_continue_cascade_resolves_and_finishes_remaining(tmp_path):
    plan = _plan(("feat/a", "main"), ("feat/b", "feat/a"), ("feat/c", "feat/b"))
    state = {
        "command": "sync",
        "plan": plan,
        "completed": ["feat/a"],
        "pre_shas": {"feat/a": "s1", "feat/b": "s2", "feat/c": "s3"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state))

    with (
        patch("arc.cascade.git.is_mid_rebase", return_value=True),
        patch("arc.cascade.git.rebase_continue", return_value=mock_result(0)),
        patch("arc.cascade.git.checkout"),
        patch("arc.cascade.git.rebase_fork_point", return_value=mock_result(0)),
    ):
        result = cascade.continue_cascade(tmp_path, quiet=True)

    assert result == {"ok": True, "state": "done", "command": "sync"}
    assert not state_path.exists()


def test_continue_cascade_hits_new_conflict_on_next_branch(tmp_path):
    plan = _plan(("feat/a", "main"), ("feat/b", "feat/a"), ("feat/c", "feat/b"))
    state = {
        "command": "rebase",
        "plan": plan,
        "completed": ["feat/a"],
        "pre_shas": {"feat/a": "s1", "feat/b": "s2", "feat/c": "s3"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state))

    def fake_rebase(onto):
        # feat/b (onto feat/a) succeeds, feat/c (onto feat/b) conflicts
        return mock_result(0) if onto == "feat/a" else mock_result(1)

    with (
        patch("arc.cascade.git.is_mid_rebase", side_effect=[True, True]),
        patch("arc.cascade.git.rebase_continue", return_value=mock_result(0)),
        patch("arc.cascade.git.checkout"),
        patch("arc.cascade.git.rebase_fork_point", side_effect=fake_rebase),
        patch("arc.cascade.git.conflicted_files", return_value=["shared.py"]),
    ):
        result = cascade.continue_cascade(tmp_path, quiet=True)

    assert result == {
        "ok": False,
        "state": "paused",
        "command": "rebase",
        "conflict_branch": "feat/c",
        "conflicted_files": ["shared.py"],
        "exit_code": 3,
    }
    saved = json.loads(state_path.read_text())
    assert saved["completed"] == ["feat/a", "feat/b"]


def test_continue_cascade_still_conflicted_reports_paused(tmp_path):
    plan = _plan(("feat/a", "main"), ("feat/b", "feat/a"))
    state = {
        "command": "sync",
        "plan": plan,
        "completed": [],
        "pre_shas": {"feat/a": "s1", "feat/b": "s2"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state))

    with (
        patch("arc.cascade.git.is_mid_rebase", return_value=True),
        patch("arc.cascade.git.rebase_continue", return_value=mock_result(1)),
        patch("arc.cascade.git.conflicted_files", return_value=["api.py"]),
    ):
        result = cascade.continue_cascade(tmp_path, quiet=True)

    assert result == {
        "ok": False,
        "state": "paused",
        "command": "sync",
        "conflict_branch": "feat/a",
        "conflicted_files": ["api.py"],
        "exit_code": 3,
    }
    # State on disk is untouched — still shows feat/a as the unfinished branch.
    saved = json.loads(state_path.read_text())
    assert saved["completed"] == []


def test_abort_cascade_no_state_and_no_rebase_reports_nothing_aborted():
    with patch("arc.cascade.git.is_mid_rebase", return_value=False):
        result = cascade.abort_cascade("/tmp/root")
    assert result == {"aborted": False, "state": None}


def test_abort_cascade_falls_back_to_bare_git_abort_when_no_cascade_state(tmp_path):
    with (
        patch("arc.cascade.git.is_mid_rebase", return_value=True),
        patch("arc.cascade.git.rebase_abort") as mock_abort,
    ):
        result = cascade.abort_cascade(tmp_path)
    assert result == {"aborted": True, "state": None}
    mock_abort.assert_called_once()


def test_abort_cascade_rolls_back_every_branch_and_clears_state(tmp_path):
    state = {
        "command": "rebase",
        "plan": _plan(("feat/a", "main"), ("feat/b", "feat/a")),
        "completed": ["feat/a"],
        "pre_shas": {"feat/a": "s1", "feat/b": "s2"},
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    state_path = tmp_path / ".arc" / "rebase-in-progress.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state))

    with (
        patch("arc.cascade.git.rebase_abort") as mock_abort,
        patch("arc.cascade.git.checkout") as mock_checkout,
        patch("arc.cascade.git._run") as mock_run,
    ):
        result = cascade.abort_cascade(tmp_path)

    assert result == {"aborted": True, "state": state}
    assert not state_path.exists()
    mock_abort.assert_called_once()
    mock_checkout.assert_any_call("feat/a")
    mock_checkout.assert_any_call("feat/b")
    mock_run.assert_any_call(["git", "reset", "--hard", "s1"])
    mock_run.assert_any_call(["git", "reset", "--hard", "s2"])


def test_run_cascade_uses_rebase_onto_when_old_base_present(tmp_path):
    plan = [{"branch": "feat/api", "onto": "main", "old_base": "feat/auth"}]
    with (
        patch("arc.cascade.git.get_sha", return_value="sha0"),
        patch("arc.cascade.git.checkout"),
        patch("arc.cascade.git.rebase_onto", return_value=mock_result(0)) as mock_onto,
        patch("arc.cascade.git.rebase_fork_point") as mock_fp,
    ):
        result = cascade.run_cascade(plan, tmp_path, command="rebase", quiet=True)
    assert result == {"ok": True, "state": "done", "command": "rebase"}
    mock_onto.assert_called_once_with("main", "feat/auth", "feat/api")
    mock_fp.assert_not_called()


def test_run_cascade_uses_fork_point_when_old_base_absent(tmp_path):
    plan = [{"branch": "feat/api", "onto": "main"}]
    with (
        patch("arc.cascade.git.get_sha", return_value="sha0"),
        patch("arc.cascade.git.checkout"),
        patch("arc.cascade.git.rebase_onto") as mock_onto,
        patch("arc.cascade.git.rebase_fork_point", return_value=mock_result(0)) as mock_fp,
    ):
        result = cascade.run_cascade(plan, tmp_path, command="rebase", quiet=True)
    assert result == {"ok": True, "state": "done", "command": "rebase"}
    mock_fp.assert_called_once_with("main")
    mock_onto.assert_not_called()
