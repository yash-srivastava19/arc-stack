"""Commit amendment with automatic upstack restack: arc edit."""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

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
    original_sha: str    # branch tip before amendment
    amended_sha: str     # branch tip after amendment
    to_restack: list[str]
    restacked: list[str]
    original_shas: dict[str, str]  # every branch -> sha before any change (for --abort)
    started_at: str      # ISO 8601


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

from arc import git


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
        files_changed=stat["files_changed"],   # type: ignore[arg-type]
        insertions=stat["insertions"],          # type: ignore[arg-type]
        deletions=stat["deletions"],            # type: ignore[arg-type]
    )
