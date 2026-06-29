"""Cross-command CLI plumbing shared by all arc command modules.

Import contract: command modules use `from arc.commands import _shared` and
call `_shared.helper()` so tests can patch the single canonical target
(arc.commands._shared.*). Exception: the `err`/`out` Console singletons may
be imported directly (`from arc.commands._shared import err, out`) — patching
an attribute on the shared instance works regardless of import path.
"""

from __future__ import annotations

import os
import random
import subprocess as _subprocess
import sys
import tempfile
from typing import NoReturn

from rich.console import Console

from arc import git, github
from arc import state as st

err = Console(stderr=True)
out = Console()


def _maybe_print_periodic_hint(root) -> None:
    """Randomly print non-blocking feedback hint on success."""
    try:
        config = st.load_config(root)
    except Exception:
        config = {}
    feedback_config = config.get("feedback", {})

    if not feedback_config.get("enabled", True):
        return
    if not feedback_config.get("prompt_periodic", True):
        return

    rate = feedback_config.get("prompt_periodic_rate", 5)

    if random.randint(1, rate) == 1:
        err.print("→ Feedback welcome? arc report --feedback", style="dim")

    # version hint (independent of feedback rate)
    try:
        root = git.find_repo_root()
        from arc.update import version_hint as _vhint

        hint = _vhint(root)
        if hint:
            err.print(f"→ {hint}", style="dim")
    except Exception:
        pass


def _maybe_print_error_hint(root) -> None:
    """Print non-blocking hint about arc report --bug after error."""
    try:
        config = st.load_config(root)
    except Exception:
        config = {}
    feedback_config = config.get("feedback", {})

    if not feedback_config.get("enabled", True):
        return
    if not feedback_config.get("prompt_after_error", True):
        return

    err.print("→ Report this: arc report --bug", style="dim")


def _check_setup() -> bool:
    """Returns True if environment is ready. Prints errors and returns False if not."""
    ok = True
    if not git.is_installed():
        err.print("git is not installed.")
        err.print("hint: install git from https://git-scm.com", style="dim")
        ok = False
    if not github.is_installed():
        err.print("gh is not installed.")
        err.print("hint: install from https://cli.github.com", style="dim")
        ok = False
    elif not github.is_authenticated():
        err.print("gh is not authenticated.")
        err.print("hint: run gh auth login", style="dim")
        ok = False
    return ok


def _is_tty() -> bool:
    """Return True if stdout is a TTY. Extracted for testability."""
    return sys.stdout.isatty()


def _exit_json_error(
    message: str, exit_code: int, hint: str = "", output_json: bool = False
) -> NoReturn:
    if output_json:
        import json as _j

        out.print_json(
            _j.dumps({"ok": False, "error": message, "exit_code": exit_code, "hint": hint})
        )
    else:
        err.print(message)
        if hint:
            err.print(f"hint: {hint}", style="dim")
    sys.exit(exit_code)


def _load_state_or_exit(root, output_json: bool = False):
    try:
        return st.load(root)
    except FileNotFoundError:
        _exit_json_error(
            "arc is not initialized in this repo.",
            exit_code=2,
            hint="run arc init --base main",
            output_json=output_json,
        )
    except Exception as e:
        _exit_json_error(str(e), exit_code=2, output_json=output_json)


def _update_gitignore(root, entry: str) -> None:
    gitignore = root / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if entry not in existing:
        with open(gitignore, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"{entry}\n")


def _open_editor(template: str) -> str:
    """Open $EDITOR with template, return edited text."""
    editor = os.environ.get("EDITOR", "vi")

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as f:
        f.write(template)
        f.flush()
        temp_path = f.name

    try:
        _subprocess.run([editor, temp_path], check=False)
        with open(temp_path) as f:
            return f.read()
    finally:
        os.unlink(temp_path)


def filter_merged_before_push(
    names: list[str],
    data: dict,
    root,
    *,
    quiet: bool = False,
    output_json: bool = False,
) -> list[str]:
    """Return only the branches in *names* that are safe to push.

    Skips branches that are already merged into the stack base.  Two checks
    run in order (cheapest first):
      1. Local git-cherry squash-merge detection (no network).
      2. GitHub PR state via `gh pr view` (network, only when pr_number exists).

    Warns about each skipped branch so the user knows why it was dropped.
    The caller is responsible for deciding whether to update arc state.
    """
    from pathlib import Path as _Path

    base = data.get("base", "main")
    safe: list[str] = []
    for name in names:
        # ── 1. local squash-merge check (fast, no network) ───────────────────
        if git.is_squash_merged(_Path(root) if not hasattr(root, "is_dir") else root, name, base):
            if not quiet and not output_json:
                err.print(
                    f"↓ {name!r} is already merged into {base!r} — skipping push",
                    style="yellow",
                )
            continue
        # ── 2. GitHub PR state check (slow, requires network) ─────────────────
        branch_entry = st.get_branch(data, name)
        pr_number = branch_entry.get("pr_number") if branch_entry else None
        if pr_number and github.pr_is_merged(pr_number):
            if not quiet and not output_json:
                err.print(
                    f"↓ {name!r} (PR #{pr_number}) is already merged — skipping push",
                    style="yellow",
                )
            continue
        safe.append(name)
    return safe


def run_lifecycle_hook(
    root,
    data: dict,
    event: str,
    *,
    branch: str = "",
    extra: dict | None = None,
    skip: bool = False,
    output_json: bool = False,
    quiet: bool = False,
) -> None:
    """Fire a file-based lifecycle hook from .arc/hooks/<event>.

    Gate (pre-*) failure exits with code 7 (same as legacy config hooks).
    Notify (post-*) failure prints a dim warning and continues. Missing or
    non-executable hook is a silent no-op (arc doctor surfaces the
    non-executable case).
    """
    if skip:
        return
    from arc import __version__, hooks

    hooks_dir = root / ".arc" / "hooks"
    path = hooks_dir / event
    if not path.is_file() or not os.access(path, os.X_OK):
        return
    if not quiet:
        err.print(f"→ running {event} hook", style="dim")
    ctx = hooks.HookContext(
        event=event,
        branch=branch,
        base=data.get("base", ""),
        root=root,
        version=__version__,
        extra=extra or {},
        stack=data.get("branches", []),
    )
    result = hooks.run_hook(event, ctx, hooks_dir)
    if result.stdout.strip() and not quiet:
        err.print(result.stdout.rstrip(), style="dim")
    if not result.ok:
        if result.stderr.strip():
            err.print(result.stderr.rstrip())
        _exit_json_error(
            f"{event} hook failed (exit {result.exit_code})",
            exit_code=7,
            hint="fix the hook or re-run with --skip-hooks",
            output_json=output_json,
        )
    elif result.exit_code != 0 and not quiet:
        err.print(f"→ {event} hook exited {result.exit_code} (ignored)", style="dim")
        if result.stderr.strip():
            err.print(result.stderr.rstrip(), style="dim")
