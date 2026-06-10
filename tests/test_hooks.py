"""Unit tests for the generic lifecycle hook runner. No arc.* coupling."""

import json
from pathlib import Path

import pytest

from arc.hooks import EVENTS, HookContext, HookType, hook_type, run_hook

pytestmark = pytest.mark.unit


def _ctx(tmp_path, event="pre-submit", **extra):
    return HookContext(
        event=event,
        branch="feat/auth",
        base="main",
        root=tmp_path,
        version="0.5.0",
        extra=extra,
        stack=[{"name": "feat/auth", "pr_number": 42, "revision": 3}],
    )


def test_events_table_complete():
    assert EVENTS == (
        "pre-submit",
        "post-submit",
        "pre-land",
        "post-land",
        "pre-sync",
        "post-sync",
        "pre-push",
        "post-push",
    )


def test_pre_events_are_gates_post_events_notify():
    for event in EVENTS:
        expected = HookType.GATE if event.startswith("pre-") else HookType.NOTIFY
        assert hook_type(event) is expected


def test_as_env_scalars(tmp_path):
    env = _ctx(tmp_path).as_env()
    assert env["ARC_EVENT"] == "pre-submit"
    assert env["ARC_BRANCH"] == "feat/auth"
    assert env["ARC_BASE"] == "main"
    assert env["ARC_ROOT"] == str(tmp_path)
    assert env["ARC_VERSION"] == "0.5.0"


def test_as_env_extras_uppercased_and_coerced(tmp_path):
    env = _ctx(tmp_path, pr_number=42, draft=True, pr_url=None).as_env()
    assert env["ARC_PR_NUMBER"] == "42"
    assert env["ARC_DRAFT"] == "true"  # bools lowercase, shell-friendly
    assert "ARC_PR_URL" not in env  # None values omitted


def test_as_json_round_trips(tmp_path):
    payload = json.loads(_ctx(tmp_path, pr_number=42).as_json())
    assert payload == {
        "event": "pre-submit",
        "branch": "feat/auth",
        "base": "main",
        "version": "0.5.0",
        "extra": {"pr_number": 42},
        "stack": [{"name": "feat/auth", "pr_number": 42, "revision": 3}],
    }


def _write_hook(hooks_dir: Path, event: str, script: str, executable: bool = True) -> Path:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir / event
    path.write_text(f"#!/bin/sh\n{script}\n")
    if executable:
        path.chmod(0o755)
    return path


def test_missing_hook_is_silent_noop(tmp_path):
    res = run_hook("pre-submit", _ctx(tmp_path), tmp_path / "hooks")
    assert res.ok and not res.ran


def test_non_executable_hook_is_silent_noop(tmp_path):
    hooks_dir = tmp_path / "hooks"
    _write_hook(hooks_dir, "pre-submit", "exit 1", executable=False)
    res = run_hook("pre-submit", _ctx(tmp_path), hooks_dir)
    assert res.ok and not res.ran


def test_gate_pass(tmp_path):
    hooks_dir = tmp_path / "hooks"
    _write_hook(hooks_dir, "pre-submit", "echo checked; exit 0")
    res = run_hook("pre-submit", _ctx(tmp_path), hooks_dir)
    assert res.ok and res.ran and res.exit_code == 0
    assert "checked" in res.stdout


def test_gate_failure_not_ok(tmp_path):
    hooks_dir = tmp_path / "hooks"
    _write_hook(hooks_dir, "pre-submit", "echo broken >&2; exit 3")
    res = run_hook("pre-submit", _ctx(tmp_path), hooks_dir)
    assert not res.ok and res.ran and res.exit_code == 3
    assert "broken" in res.stderr


def test_notify_failure_still_ok(tmp_path):
    hooks_dir = tmp_path / "hooks"
    _write_hook(hooks_dir, "post-submit", "exit 1")
    res = run_hook("post-submit", _ctx(tmp_path), hooks_dir)
    assert res.ok and res.ran and res.exit_code == 1


def test_hook_receives_env_vars(tmp_path):
    hooks_dir = tmp_path / "hooks"
    capture = tmp_path / "captured-env"
    _write_hook(
        hooks_dir,
        "pre-push",
        f'echo "$ARC_EVENT|$ARC_BRANCH|$ARC_BASE|$ARC_VERSION" > {capture}',
    )
    run_hook("pre-push", _ctx(tmp_path, event="pre-push"), hooks_dir)
    assert capture.read_text().strip() == "pre-push|feat/auth|main|0.5.0"


def test_hook_receives_json_on_stdin(tmp_path):
    hooks_dir = tmp_path / "hooks"
    capture = tmp_path / "captured-stdin"
    _write_hook(hooks_dir, "pre-submit", f"cat > {capture}")
    run_hook("pre-submit", _ctx(tmp_path, pr_number=42), hooks_dir)
    payload = json.loads(capture.read_text())
    assert payload["event"] == "pre-submit"
    assert payload["extra"] == {"pr_number": 42}
    assert payload["stack"][0]["name"] == "feat/auth"


def test_hook_runs_with_repo_root_cwd(tmp_path):
    hooks_dir = tmp_path / "hooks"
    capture = tmp_path / "captured-cwd"
    _write_hook(hooks_dir, "pre-submit", f"pwd > {capture}")
    run_hook("pre-submit", _ctx(tmp_path), hooks_dir)
    assert capture.read_text().strip() == str(tmp_path)


def test_hooks_module_imports_stdlib_only():
    """Dependency rule: arc/hooks.py must be extractable (roadmap 8b)."""
    import ast

    import arc.hooks as hooks_module

    source = Path(hooks_module.__file__).read_text()
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            assert not name.startswith("arc"), f"arc.hooks imports {name!r} — must be stdlib-only"
