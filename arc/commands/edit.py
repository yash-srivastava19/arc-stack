"""Commit amendment with automatic upstack restack: arc edit."""

from __future__ import annotations

import json as _json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

import click

from arc import git, ops
from arc.commands import _shared
from arc.commands._shared import err, out
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


def _do_amend(
    target: str,
    message: str | None,
    mode: Literal["message", "staged", "interactive"],
    quiet: bool,
) -> str:
    """Apply the amendment. Returns the new HEAD SHA. Must be called while on target branch."""
    if mode == "interactive":
        import subprocess as _sub

        _sub.run(["git", "rebase", "-i", "HEAD~1"], check=True)
    elif mode == "staged" and message:
        git.amend_message(message)
    elif mode == "staged":
        git.amend_staged()
    else:  # mode == "message"
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
    """Restack branches in order onto their updated parents.

    For each branch, computes:
      - new_base: current tip of the parent branch (updated by prior restacks)
      - old_base: original tip of the parent branch (from original_shas)
    Then runs: git rebase --onto new_base old_base branch

    Returns (restacked, conflict_branch, conflict_sha).
    conflict_branch is None on full success.
    """
    restacked: list[str] = []
    for branch in branches:
        parent = ops.parent_branch(data, branch)
        new_base = git.get_sha(parent)
        old_base = original_shas[parent]

        if not quiet and not output_json:
            err.print(f"→ restacking {branch}...", end=" ")

        result = git.rebase_onto(new_base, old_base, branch)
        if result.returncode != 0:
            conflict_sha = git.get_sha("HEAD") if not git.is_mid_rebase(root) else ""
            if not quiet and not output_json:
                err.print("CONFLICT", style="red")
            return restacked, branch, conflict_sha

        restacked.append(branch)
        if not quiet and not output_json:
            err.print("✓", style="green")

    return restacked, None, None


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
    output_json = _shared._resolve_output_json(output_json)

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

    old_sha = git.get_sha(target)
    upstack = ops.upstack_branches(data, target)

    # ── Dry run ───────────────────────────────────────────────────────────────
    if dry_run:
        from arc import conflicts as _conf

        preds = _conf.predict_conflicts(data, root)
        predicted = [
            PredictedConflict(branch=p["branch"], files=p["shared_files"])
            for p in preds
            if p["branch"] in upstack
        ]
        dry_result: EditDryRunResult = {
            "ok": True,
            "state": "dry_run",
            "mode": mode,
            "branch": target,
            "current_sha": old_sha,
            "would_amend": True,
            "upstack": upstack,
            "would_push": ([target] + upstack) if not no_push else [],
            "predicted_conflicts": predicted,
        }
        if output_json:
            out.print_json(_json.dumps(dry_result))
        else:
            err.print(f"would amend {target!r} (mode={mode})")
            for b in upstack:
                err.print(f"  would restack {b}")
        return

    # ── Pre-edit hook ─────────────────────────────────────────────────────────
    _shared.run_lifecycle_hook(
        root,
        data,
        "pre-edit",
        branch=target,
        extra={"mode": mode, "old_sha": old_sha},
        skip=skip_hooks,
        output_json=output_json,
        quiet=quiet,
    )

    # ── Checkout target branch and amend ──────────────────────────────────────
    current = git.current_branch()
    if current != target:
        git.checkout(target)

    if not quiet and not output_json:
        err.print(f"→ amending {target!r}...", end=" ")
    new_sha = _do_amend(target, message, mode, quiet)
    if not quiet and not output_json:
        err.print("✓", style="green")

    summary = _get_amendment_summary(old_sha, new_sha)

    # Build original_shas for --abort recovery
    original_shas: dict[str, str] = {target: old_sha}
    for b in upstack:
        original_shas[b] = git.get_sha(b)

    # ── Restack upstack ───────────────────────────────────────────────────────
    restacked, conflict_branch, conflict_sha = _restack_upstack(
        upstack, original_shas, data, root, quiet=quiet, output_json=output_json
    )

    # ── Handle conflict ───────────────────────────────────────────────────────
    if conflict_branch is not None:
        paused_state: _EditState = {
            "branch": target,
            "mode": mode,
            "original_sha": old_sha,
            "amended_sha": new_sha,
            "to_restack": upstack,
            "restacked": restacked,
            "original_shas": original_shas,
            "started_at": datetime.now(UTC).isoformat(),
        }
        _handle_conflict(
            root,
            paused_state,
            conflict_branch,
            conflict_sha or "",
            summary=summary,
            output_json=output_json,
            quiet=quiet,
        )

    # ── Success ───────────────────────────────────────────────────────────────
    pushed: list[str] = []
    if not no_push:
        to_push = _shared.filter_merged_before_push(
            [target] + restacked, data, root, quiet=quiet, output_json=output_json
        )
        if to_push:
            if not quiet and not output_json:
                err.print(f"→ force-pushing {len(to_push)} branches...", end=" ")
            git.force_push(to_push)
            pushed = to_push
            if not quiet and not output_json:
                err.print("✓", style="green")

    _shared.run_lifecycle_hook(
        root,
        data,
        "post-edit",
        branch=target,
        extra={"mode": mode, "old_sha": old_sha, "new_sha": new_sha},
        skip=skip_hooks,
        output_json=output_json,
        quiet=quiet,
    )

    done: EditDoneResult = {
        "ok": True,
        "state": "done",
        "mode": mode,
        "branch": target,
        "old_sha": old_sha,
        "new_sha": new_sha,
        "amendment_summary": summary,
        "restacked": restacked,
        "pushed": pushed,
    }
    if output_json:
        out.print_json(_json.dumps(done))
    elif not quiet:
        _shared._maybe_print_periodic_hint(root)


def _handle_conflict(
    root: Path,
    state: _EditState,
    conflict_branch: str,
    conflict_sha: str,
    *,
    summary: AmendmentSummary,
    output_json: bool,
    quiet: bool,
) -> None:
    """Save state, emit a paused result, and exit with code 3. Never returns."""
    _save_edit_state(root, state)
    idx = len(state["restacked"])
    remaining = state["to_restack"][idx + 1 :]
    paused: EditPausedResult = {
        "ok": False,
        "state": "paused",
        "mode": state["mode"],
        "branch": state["branch"],
        "old_sha": state["original_sha"],
        "new_sha": state["amended_sha"],
        "amendment_summary": summary,
        "restacked": state["restacked"],
        "conflict_branch": conflict_branch,
        "conflict_sha": conflict_sha,
        "conflicted_files": git.conflicted_files(),
        "remaining": remaining,
        "exit_code": 3,
        "hint": "resolve conflicts then run `arc edit --continue`",
    }
    if output_json:
        out.print_json(_json.dumps(paused))
    else:
        err.print(f"conflict in {conflict_branch!r}", style="red")
        for f in paused["conflicted_files"]:
            err.print(f"  {f}", style="dim")
        err.print("hint: resolve conflicts then run arc edit --continue", style="dim")
    sys.exit(3)


def _do_abort(root: Path, state: _EditState, *, output_json: bool, quiet: bool) -> None:
    """Undo edit — abort any in-progress rebase and restore all branches to original SHAs."""
    if git.is_mid_rebase(root):
        if not quiet and not output_json:
            err.print("→ aborting in-progress rebase...", end=" ")
        git.rebase_abort()
        if not quiet and not output_json:
            err.print("✓", style="green")

    original_shas = state["original_shas"]
    restored: list[str] = []

    # Restore upstack branches first (leaves → root), then the amended branch
    upstack_branches = [b for b in state["to_restack"] if b in original_shas]
    for branch in reversed(upstack_branches):
        sha = original_shas[branch]
        if not quiet and not output_json:
            err.print(f"→ restoring {branch!r} to {sha[:8]}...", end=" ")
        git.reset_branch_to(branch, sha)
        restored.append(branch)
        if not quiet and not output_json:
            err.print("✓", style="green")

    target = state["branch"]
    if not quiet and not output_json:
        err.print(f"→ restoring {target!r} to {state['original_sha'][:8]}...", end=" ")
    git.reset_branch_to(target, state["original_sha"])
    restored.append(target)
    if not quiet and not output_json:
        err.print("✓", style="green")

    # Land on the target branch so the user is in a clean state
    if git.current_branch() != target:
        git.checkout(target)

    _clear_edit_state(root)

    aborted: EditAbortedResult = {
        "ok": True,
        "state": "aborted",
        "branch": target,
        "restored_sha": state["original_sha"],
        "restored_branches": restored,
    }
    if output_json:
        out.print_json(_json.dumps(aborted))
    elif not quiet:
        err.print(f"→ edit aborted — {len(restored)} branch(es) restored", style="dim")


def _do_continue(
    root: Path,
    data: StackState,
    state: _EditState,
    *,
    no_push: bool,
    output_json: bool,
    quiet: bool,
) -> None:
    """Resume a paused arc edit after the user resolves rebase conflicts."""
    restacked = list(state["restacked"])
    to_restack = state["to_restack"]
    original_shas = state["original_shas"]
    summary = _get_amendment_summary(state["original_sha"], state["amended_sha"])

    # Determine the branch that was conflicting
    conflict_branch = to_restack[len(restacked)]

    if git.is_mid_rebase(root):
        # User staged their resolution; finish the current rebase
        if not quiet and not output_json:
            err.print(f"→ continuing rebase on {conflict_branch!r}...", end=" ")
        result = git.rebase_continue()
        if result.returncode != 0:
            # Rebase --continue hit another conflict patch
            conflict_sha = git.get_sha("HEAD") if not git.is_mid_rebase(root) else ""
            if not quiet and not output_json:
                err.print("CONFLICT", style="red")
            updated_state: _EditState = {**state, "restacked": restacked}
            _handle_conflict(
                root,
                updated_state,
                conflict_branch,
                conflict_sha,
                summary=summary,
                output_json=output_json,
                quiet=quiet,
            )
        if not quiet and not output_json:
            err.print("✓", style="green")
    else:
        # User ran git rebase --continue manually; accept current branch state
        if not quiet and not output_json:
            err.print(
                f"→ rebase already finished for {conflict_branch!r} (resolved externally)",
                style="dim",
            )

    restacked.append(conflict_branch)

    # Continue restacking the remaining branches
    remaining = to_restack[len(restacked) :]
    new_restacked, conflict_branch2, conflict_sha2 = _restack_upstack(
        remaining, original_shas, data, root, quiet=quiet, output_json=output_json
    )
    restacked.extend(new_restacked)

    if conflict_branch2 is not None:
        updated_state2: _EditState = {**state, "restacked": restacked}
        _handle_conflict(
            root,
            updated_state2,
            conflict_branch2,
            conflict_sha2 or "",
            summary=summary,
            output_json=output_json,
            quiet=quiet,
        )

    # All restacked — push and emit done
    pushed: list[str] = []
    if not no_push:
        to_push = _shared.filter_merged_before_push(
            [state["branch"]] + restacked, data, root, quiet=quiet, output_json=output_json
        )
        if to_push:
            if not quiet and not output_json:
                err.print(f"→ force-pushing {len(to_push)} branches...", end=" ")
            git.force_push(to_push)
            pushed = to_push
            if not quiet and not output_json:
                err.print("✓", style="green")

    _clear_edit_state(root)

    done: EditDoneResult = {
        "ok": True,
        "state": "done",
        "mode": state["mode"],
        "branch": state["branch"],
        "old_sha": state["original_sha"],
        "new_sha": state["amended_sha"],
        "amendment_summary": summary,
        "restacked": restacked,
        "pushed": pushed,
    }
    if output_json:
        out.print_json(_json.dumps(done))
    elif not quiet:
        _shared._maybe_print_periodic_hint(root)
