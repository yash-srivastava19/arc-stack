"""Commit amendment with automatic upstack restack: arc edit."""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import Literal, TypedDict

import click

from arc import git
from arc.commands import _shared
from arc.commands._shared import err

# ── Public TypedDicts (JSON API shapes) ──────────────────────────────────────


class AmendmentSummary(TypedDict):
    files_changed: list[str]
    insertions: int
    deletions: int


class PredictedConflict(TypedDict):
    branch: str
    files: list[str]


class EditDoneResult(TypedDict):
    ok: Literal[True]
    state: Literal["done"]
    mode: Literal["message", "staged", "interactive"]
    branch: str
    old_sha: str
    new_sha: str
    amendment_summary: AmendmentSummary
    restacked: list[str]
    pushed: list[str]


class EditPausedResult(TypedDict):
    ok: Literal[False]
    state: Literal["paused"]
    mode: Literal["message", "staged", "interactive"]
    branch: str
    old_sha: str
    new_sha: str
    amendment_summary: AmendmentSummary
    restacked: list[str]
    conflict_branch: str
    conflict_sha: str
    conflicted_files: list[str]
    remaining: list[str]
    exit_code: Literal[3]
    hint: str


class EditDryRunResult(TypedDict):
    ok: Literal[True]
    state: Literal["dry_run"]
    mode: Literal["message", "staged", "interactive"]
    branch: str
    current_sha: str
    would_amend: bool
    upstack: list[str]
    would_push: list[str]
    predicted_conflicts: list[PredictedConflict]


class EditAbortedResult(TypedDict):
    ok: Literal[True]
    state: Literal["aborted"]
    branch: str
    restored_sha: str
    restored_branches: list[str]


# ── In-progress state (internal, not exported) ───────────────────────────────


class _EditState(TypedDict):
    branch: str
    mode: Literal["message", "staged", "interactive"]
    original_sha: str  # branch tip before amendment
    amended_sha: str  # branch tip after amendment
    to_restack: list[str]
    restacked: list[str]
    original_shas: dict[str, str]  # every branch -> sha before any change (for --abort)
    started_at: str  # ISO 8601


_EDIT_STATE_FILENAME = "edit-in-progress.json"


def _edit_state_path(root: Path) -> Path:
    return root / ".arc" / _EDIT_STATE_FILENAME


def _save_edit_state(root: Path, state: _EditState) -> None:
    path = _edit_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(state, indent=2))


def _load_edit_state(root: Path) -> _EditState | None:
    path = _edit_state_path(root)
    if not path.exists():
        return None
    try:
        return _json.loads(path.read_text())
    except _json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Corrupt edit state file at {path}. "
            "Run `arc edit --abort` or delete the file manually to recover."
        ) from exc


def _clear_edit_state(root: Path) -> None:
    path = _edit_state_path(root)
    if path.exists():
        path.unlink()


# ── Pure helper functions ─────────────────────────────────────────────────────


def _detect_mode(
    message: str | None,
    interactive: bool,
) -> Literal["message", "staged", "interactive"]:
    # `message` is not read here: staged content always takes priority over
    # a message-only intent. "message" mode is a guarantee that no file content
    # changed; having staged files overrides that guarantee regardless of --message.
    if interactive:
        return "interactive"
    if git.get_staged_files():
        return "staged"
    return "message"


def _get_amendment_summary(old_sha: str, new_sha: str) -> AmendmentSummary:
    """Return diff stats between old and new commit SHAs."""
    stat = git.diff_stat(old_sha, new_sha)
    return AmendmentSummary(
        files_changed=stat["files_changed"],
        insertions=stat["insertions"],
        deletions=stat["deletions"],
    )


# ── Command ───────────────────────────────────────────────────────────────────


@click.command("edit")
@click.argument("branch", required=False, default=None)
@click.option("--message", "-m", default=None, help="New commit message.")
@click.option("--interactive", is_flag=True, help="Interactive rebase within branch.")
@click.option("--no-push", is_flag=True, help="Skip force-push after restack.")
@click.option("--dry-run", is_flag=True, help="Preview what would happen.")
@click.option("--continue", "do_continue", is_flag=True, help="Resume after conflict.")
@click.option("--abort", "do_abort", is_flag=True, help="Undo edit, restore original state.")
@click.option("--skip-hooks", is_flag=True, help="Skip pre-edit / post-edit hooks.")
@click.option("--json", "output_json", is_flag=True, help="Structured output.")
@click.option("-q", "--quiet", is_flag=True)
def edit_cmd(
    branch,
    message,
    interactive,
    no_push,
    dry_run,
    do_continue,
    do_abort,
    skip_hooks,
    output_json,
    quiet,
):
    """Amend a branch's HEAD commit and restack all upstack branches."""
    if not output_json and not _shared._is_tty():
        output_json = True

    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)

    # ── --abort ───────────────────────────────────────────────────────────────
    if do_abort:
        edit_state = _load_edit_state(root)
        if edit_state is None:
            _shared._exit_json_error(
                "no edit in progress",
                exit_code=1,
                hint="nothing to abort",
                output_json=output_json,
            )
        _do_abort(root, edit_state, output_json=output_json, quiet=quiet)
        return

    # ── --continue ────────────────────────────────────────────────────────────
    if do_continue:
        edit_state = _load_edit_state(root)
        if edit_state is None:
            _shared._exit_json_error(
                "no edit in progress",
                exit_code=1,
                hint="run arc edit to start an edit",
                output_json=output_json,
            )
        _do_continue(root, data, edit_state, no_push=no_push, output_json=output_json, quiet=quiet)
        return

    # ── Pre-flight ────────────────────────────────────────────────────────────
    if git.is_mid_rebase(root):
        _shared._exit_json_error(
            "git is already mid-rebase",
            exit_code=1,
            hint="run git rebase --abort then arc edit --abort",
            output_json=output_json,
        )

    if interactive and message:
        _shared._exit_json_error(
            "--interactive and --message are mutually exclusive",
            exit_code=1,
            output_json=output_json,
        )

    staged = git.get_staged_files()

    if interactive and staged:
        _shared._exit_json_error(
            "--interactive and staged changes are mutually exclusive — unstage first",
            exit_code=1,
            output_json=output_json,
        )

    mode = _detect_mode(message=message, interactive=interactive)

    if mode == "message" and not message:
        _shared._exit_json_error(
            "nothing to amend — no staged changes and no --message",
            exit_code=1,
            hint='stage changes with git add, or pass --message "..."',
            output_json=output_json,
        )

    # Resolve target branch
    target = branch or git.current_branch()
    branch_list = data.get("branches", [])
    names = [b["name"] for b in branch_list]
    if target not in names:
        _shared._exit_json_error(
            f"{target!r} is not in this stack — run arc status",
            exit_code=5,
            output_json=output_json,
        )

    # ── Stub: filled in later PRs ─────────────────────────────────────────────
    err.print(f"arc edit: pre-flight passed for {target!r} (mode={mode})", style="dim")
    sys.exit(0)


def _do_abort(root, state, *, output_json, quiet):
    """Stub — implemented in PR5."""
    _shared._exit_json_error("--abort not yet implemented", exit_code=1, output_json=output_json)


def _do_continue(root, data, state, *, no_push, output_json, quiet):
    """Stub — implemented in PR5."""
    _shared._exit_json_error("--continue not yet implemented", exit_code=1, output_json=output_json)
