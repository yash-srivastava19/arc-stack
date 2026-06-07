"""Pure functions for collecting environment context and formatting issue bodies."""

import platform
import sys
from importlib.metadata import version


def collect_env_context() -> str:
    """Collect environment info for issue reports (non-PII).

    Returns a formatted string with arc version, Python version, and OS.
    """
    arc_ver = version("arc-prs")
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_info = f"{platform.system()} {platform.release()}"

    return f"[Environment]\narc version: {arc_ver}\nPython version: {py_ver}\nOS: {os_info}\n"


def format_issue_body(
    user_text: str,
    error_message: str | None = None,
    command_name: str | None = None,
) -> str:
    """Format issue body with environment context and user text.

    Args:
        user_text: The user's description of the issue
        error_message: Optional error message to include in context
        command_name: Optional name of the command that triggered this

    Returns:
        Formatted issue body ready for GitHub
    """
    ctx = collect_env_context()

    if error_message or command_name:
        ctx += "[Context]\n"
        if command_name:
            ctx += f"Command: {command_name}\n"
        if error_message:
            ctx += f"Error: {error_message}\n"

    body = ctx + "\n---\n\n" + user_text
    return body
