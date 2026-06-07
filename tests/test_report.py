import platform
import sys

from arc import report


def test_collect_env_context_includes_arc_version():
    ctx = report.collect_env_context()
    assert "arc version:" in ctx
    assert "0.4.0" in ctx


def test_collect_env_context_includes_python_version():
    ctx = report.collect_env_context()
    assert "Python version:" in ctx
    assert str(sys.version_info.major) in ctx


def test_collect_env_context_includes_os():
    ctx = report.collect_env_context()
    assert "OS:" in ctx
    assert platform.system() in ctx or "Linux" in ctx or "Darwin" in ctx


def test_collect_env_context_no_pii():
    ctx = report.collect_env_context()
    # Ensure no usernames, paths, or secrets
    assert not any(c in ctx for c in ["@", "$", "/home", "/Users"])


def test_format_issue_body_without_error():
    body = report.format_issue_body(
        user_text="This is feedback",
        error_message=None,
        command_name=None,
    )
    assert "[Environment]" in body
    assert "This is feedback" in body
    assert "[Context]" not in body


def test_format_issue_body_with_error():
    body = report.format_issue_body(
        user_text="sync fails on squash-merge",
        error_message="Conflict in feat/api",
        command_name="sync",
    )
    assert "[Environment]" in body
    assert "[Context]" in body
    assert "Command: sync" in body
    assert "Conflict in feat/api" in body
    assert "sync fails on squash-merge" in body


def test_format_issue_body_has_separator():
    body = report.format_issue_body("test", None, None)
    assert "---" in body
