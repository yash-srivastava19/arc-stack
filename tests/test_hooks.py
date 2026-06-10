"""Unit tests for the generic lifecycle hook runner. No arc.* coupling."""

import json
from pathlib import Path

import pytest

from arc.hooks import EVENTS, HookContext, HookResult, HookType, hook_type, run_hook

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
