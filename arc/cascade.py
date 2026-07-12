"""Executes a rebase plan across the stack, pausing on real conflicts and
resuming remaining branches — shared by `arc sync` and `arc rebase`.

No click, no sys.exit — callers translate CascadeResult into user-facing
messages and exit codes.
"""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from arc import git
from arc.commands._shared import err
from arc.ops import RebasePlanStep


class CascadeState(TypedDict):
    command: Literal["sync", "rebase"]
    plan: list[RebasePlanStep]
    completed: list[str]
    pre_shas: dict[str, str]
    started_at: str


class CascadeDone(TypedDict):
    ok: Literal[True]
    state: Literal["done"]
    command: Literal["sync", "rebase"]


class CascadePaused(TypedDict):
    ok: Literal[False]
    state: Literal["paused"]
    command: Literal["sync", "rebase"]
    conflict_branch: str
    conflicted_files: list[str]
    exit_code: Literal[3]


class CascadeError(TypedDict):
    ok: Literal[False]
    state: Literal["error"]
    branch: str
    message: str
    exit_code: Literal[3]


CascadeResult = CascadeDone | CascadePaused | CascadeError


class AbortResult(TypedDict):
    aborted: bool
    state: CascadeState | None


_STATE_FILENAME = "rebase-in-progress.json"


def _state_path(root: Path) -> Path:
    return Path(root) / ".arc" / _STATE_FILENAME


def _save_state(root: Path, state: CascadeState) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(state, indent=2))


def load_state(root: Path) -> CascadeState | None:
    path = _state_path(root)
    if not path.exists():
        return None
    try:
        return _json.loads(path.read_text())
    except _json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Corrupt cascade state file at {path}. "
            "Run `arc rebase --abort` or delete the file manually to recover."
        ) from exc


def _clear_state(root: Path) -> None:
    path = _state_path(root)
    if path.exists():
        path.unlink()


def _rollback(pre_shas: dict[str, str]) -> None:
    """Best-effort reset of every branch in pre_shas to its pre-cascade SHA."""
    for name, sha in pre_shas.items():
        try:
            git.checkout(name)
            git._run(["git", "reset", "--hard", sha])
        except Exception:
            pass


def _run_from(
    steps: list[RebasePlanStep],
    root: Path,
    command: Literal["sync", "rebase"],
    full_plan: list[RebasePlanStep],
    pre_shas: dict[str, str],
    completed: list[str],
    quiet: bool,
) -> CascadeResult:
    """Run `steps` (the remaining portion of `full_plan`) in order, extending
    `completed` as branches finish. Shared by run_cascade and continue_cascade."""
    for step in steps:
        branch, onto = step["branch"], step["onto"]
        if not quiet:
            err.print(f"Rebasing {branch} onto {onto}...")
        git.checkout(branch)
        old_base = step.get("old_base")
        result = (
            git.rebase_onto(onto, old_base, branch) if old_base else git.rebase_fork_point(onto)
        )
        if result.returncode != 0:
            if not git.is_mid_rebase(root):
                _rollback(pre_shas)
                _clear_state(root)
                return {
                    "ok": False,
                    "state": "error",
                    "branch": branch,
                    "message": result.stderr.strip() or "see git status",
                    "exit_code": 3,
                }
            _save_state(
                root,
                {
                    "command": command,
                    "plan": full_plan,
                    "completed": completed,
                    "pre_shas": pre_shas,
                    "started_at": datetime.now(UTC).isoformat(),
                },
            )
            return {
                "ok": False,
                "state": "paused",
                "command": command,
                "conflict_branch": branch,
                "conflicted_files": git.conflicted_files(),
                "exit_code": 3,
            }
        completed.append(branch)

    _clear_state(root)
    return {"ok": True, "state": "done", "command": command}


def run_cascade(
    plan: list[RebasePlanStep],
    root: Path,
    command: Literal["sync", "rebase"],
    quiet: bool = False,
) -> CascadeResult:
    """Run `plan` in order: checkout each branch, rebase onto its parent.

    On a real conflict, saves state so continue_cascade/abort_cascade can
    resume or roll back, and returns a paused result. On a pre-condition
    failure (rebase never started — dirty tree, locked index, etc.), rolls
    back immediately since there's nothing to resume.
    """
    if not plan:
        return {"ok": True, "state": "done", "command": command}
    pre_shas = {step["branch"]: git.get_sha(step["branch"]) for step in plan}
    return _run_from(plan, root, command, plan, pre_shas, [], quiet)


def continue_cascade(root: Path, quiet: bool = False) -> CascadeResult:
    """Resume a paused cascade after the user resolves conflicts."""
    state = load_state(root)
    if state is None:
        if git.is_mid_rebase(root):
            # A bare (non-cascade) rebase is in progress — from `arc restack`,
            # `arc drop`, or `arc land`, none of which write cascade state.
            # Fall back to a plain continue so `arc rebase --continue` still
            # works as a generic recovery command for any paused rebase.
            result = git.rebase_continue()
            if result.returncode != 0:
                return {
                    "ok": False,
                    "state": "paused",
                    "command": "rebase",
                    "conflict_branch": git.current_branch(),
                    "conflicted_files": git.conflicted_files(),
                    "exit_code": 3,
                }
            return {"ok": True, "state": "done", "command": "rebase"}
        return {
            "ok": False,
            "state": "error",
            "branch": "",
            "message": "No paused rebase to continue.",
            "exit_code": 3,
        }

    command = state["command"]
    plan = state["plan"]
    completed = list(state["completed"])
    pre_shas = state["pre_shas"]
    conflict_branch = plan[len(completed)]["branch"]

    if git.is_mid_rebase(root):
        result = git.rebase_continue()
        if result.returncode != 0:
            # Still conflicted — state on disk already reflects this branch
            # as unfinished; nothing to update.
            return {
                "ok": False,
                "state": "paused",
                "command": command,
                "conflict_branch": conflict_branch,
                "conflicted_files": git.conflicted_files(),
                "exit_code": 3,
            }
    # else: user resolved and ran `git rebase --continue` manually already.
    completed.append(conflict_branch)

    remaining = plan[len(completed) :]
    return _run_from(remaining, root, command, plan, pre_shas, completed, quiet)


def abort_cascade(root: Path) -> AbortResult:
    """Abort the in-progress git rebase (if any) and roll every plan branch
    back to its pre-cascade SHA.

    Returns {"aborted": True, "state": <state>} for a cascade abort,
    {"aborted": True, "state": None} for a bare (non-cascade) rebase abort
    — e.g. from `arc restack`/`arc drop`/`arc land`, none of which write
    cascade state — and {"aborted": False, "state": None} if there was
    nothing to abort at all.
    """
    state = load_state(root)
    if state is None:
        if git.is_mid_rebase(root):
            git.rebase_abort()
            return {"aborted": True, "state": None}
        return {"aborted": False, "state": None}
    git.rebase_abort()
    _rollback(state["pre_shas"])
    _clear_state(root)
    return {"aborted": True, "state": state}
