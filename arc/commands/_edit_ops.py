"""Pure edit-operation helpers: TypedDicts, edit-state CRUD, restack logic.

No click, no sys.exit — all of that lives in edit.py.
Rich is used inline for terminal feedback in _restack_upstack.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Literal, TypedDict

from arc import git, ops
from arc.state import StackState

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


# ── In-progress state (internal) ─────────────────────────────────────────────


class _EditState(TypedDict):
    branch: str
    mode: Literal["message", "staged", "interactive"]
    original_sha: str
    amended_sha: str
    to_restack: list[str]
    restacked: list[str]
    original_shas: dict[str, str]
    started_at: str


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


# ── Pure helpers ──────────────────────────────────────────────────────────────


def _detect_mode(
    message: str | None,
    interactive: bool,
) -> Literal["message", "staged", "interactive"]:
    if interactive:
        return "interactive"
    if git.get_staged_files():
        return "staged"
    return "message"


def _get_amendment_summary(old_sha: str, new_sha: str) -> AmendmentSummary:
    stat = git.diff_stat(old_sha, new_sha)
    return AmendmentSummary(
        files_changed=stat["files_changed"],
        insertions=stat["insertions"],
        deletions=stat["deletions"],
    )


def _do_amend(
    target: str,
    message: str | None,
    mode: Literal["message", "staged", "interactive"],
    quiet: bool,
) -> str:
    """Apply the amendment. Returns the new HEAD SHA. Must be called on target branch."""
    if mode == "interactive":
        import subprocess as _sub

        _sub.run(["git", "rebase", "-i", "HEAD~1"], check=True)
    elif mode == "staged" and message:
        git.amend_message(message)
    elif mode == "staged":
        git.amend_staged()
    else:
        assert message is not None
        git.amend_message(message)
    return git.get_sha("HEAD")


def _restack_upstack(
    branches: list[str],
    original_shas: dict[str, str],
    data: StackState,
    root: Path,
    quiet: bool = False,
    output_json: bool = False,
) -> tuple[list[str], str | None, str | None]:
    """Restack branches onto their updated parents using rebase --onto.

    Returns (restacked, conflict_branch, conflict_sha).
    conflict_branch is None on full success.
    """
    from rich.console import Console as _Console

    _err = _Console(stderr=True)

    restacked: list[str] = []
    for branch in branches:
        parent = ops.parent_branch(data, branch)
        new_base = git.get_sha(parent)
        old_base = original_shas[parent]

        if not quiet and not output_json:
            _err.print(f"→ restacking {branch}...", end=" ")

        result = git.rebase_onto(new_base, old_base, branch)
        if result.returncode != 0:
            conflict_sha = git.get_sha("HEAD") if not git.is_mid_rebase(root) else ""
            if not quiet and not output_json:
                _err.print("CONFLICT", style="red")
            return restacked, branch, conflict_sha

        restacked.append(branch)
        if not quiet and not output_json:
            _err.print("✓", style="green")

    return restacked, None, None
