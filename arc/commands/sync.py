"""Local-remote reconciliation: sync, push, restack, rebase."""

from __future__ import annotations

import sys

import click

from arc import cascade, git, github, ops, tip
from arc import conflicts as _conflicts
from arc import state as st
from arc.commands import _shared
from arc.commands._shared import err
from arc.state import StackState


def detect_merged_branches(data: StackState) -> set[str]:
    """Find branches in state whose PR was merged on GitHub."""
    return {
        b["name"]
        for b in data["branches"]
        if b["pr_number"] is not None and github.pr_is_merged(b["pr_number"])
    }


def retarget_dependent_prs(
    data: StackState, merged_branches: set[str], quiet: bool = False
) -> StackState:
    """Retarget PRs whose base branch was merged, then prune merged branches from state.

    Note: This implementation always retargets to data["base"] (the stack root).
    This works correctly for bottom-up merges but for non-contiguous merges
    (e.g., middle branch merged) it may retarget to root instead of the nearest
    unmerged ancestor. This is acceptable for the MVP; future work can optimize
    to find the nearest unmerged parent.
    """
    for branch in data["branches"]:
        # Use positional parent derivation (matching ops.parent_branch logic)
        parent = ops.parent_branch(data, branch["name"])
        if parent in merged_branches:
            pr_number = branch.get("pr_number")
            if pr_number:
                success = github.update_pr_base(pr_number, data["base"])
                if success and not quiet:
                    err.print(f"Retargeted PR #{pr_number} to {data['base']}")

    # Remove merged branches from state to avoid re-detecting them on the next sync
    for branch_name in merged_branches:
        data = st.remove_branch(data, branch_name)
    return data


def _scan_squash_merged(
    data: StackState, root, dry_run: bool, quiet: bool
) -> tuple[set[str], StackState]:
    """Detect squash-merged branches, remove them locally, and return (removed, updated_data)."""
    squash_merged: set[str] = set()
    for b in data["branches"]:
        name = b["name"]
        if git.branch_exists(name) and git.is_squash_merged(root, name, data["base"]):
            squash_merged.add(name)
            if not quiet:
                err.print(
                    f"↓ {name} detected as squash-merged into {data['base']} — removing from stack."
                )
            if not dry_run:
                if git.current_branch() == name:
                    git.checkout(data["base"])
                git.delete_branch(name, force=True)
    if squash_merged and not dry_run:
        data["branches"] = [b for b in data["branches"] if b["name"] not in squash_merged]
        st.save(root, data)
    return squash_merged, data


def _prune_merged_branches(data: StackState, root, quiet: bool) -> StackState:
    """Retarget PRs above merged branches, prune from state, save, and return updated data."""
    merged_branches = detect_merged_branches(data)
    if not merged_branches:
        return data
    data = retarget_dependent_prs(data, merged_branches, quiet)
    for name in merged_branches:
        if not quiet:
            err.print(f"↓ {name} is merged — removed from stack.")
    data["branches"] = [b for b in data["branches"] if b["name"] not in merged_branches]
    st.save(root, data)
    return data


@click.command("sync")
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
@click.option("--skip-hooks", is_flag=True)
def sync_cmd(dry_run, quiet, output_json, skip_hooks):
    """Fetch and cascade-rebase the stack."""
    output_json = _shared._resolve_output_json(output_json)
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
    if not st.branch_names(data):
        err.print("Stack is empty.")
        err.print("hint: run arc new <branch> to create your first branch", style="dim")
        return

    with _shared.with_error_hint(root):
        _shared.run_lifecycle_hook(
            root,
            data,
            "pre-sync",
            branch=git.current_branch(),
            # sync has no dry-run early return, so dry-run is excluded here
            skip=skip_hooks or dry_run,
            output_json=output_json,
            quiet=quiet,
        )
        if not quiet:
            err.print("Fetching...", end=" ")
        if not dry_run:
            git.fetch()
            # Clear phantom mtime differences (e.g. uv.lock) that would cause
            # git rebase to refuse with "unstaged changes" even when nothing changed.
            git.refresh_index()
        if not quiet:
            err.print("done.")

        _, data = _scan_squash_merged(data, root, dry_run, quiet)

        # Conflict prediction: warn about adjacent branches that modify the same files
        if not dry_run and len(data.get("branches", [])) > 1:
            predicted = _conflicts.predict_conflicts(data, root)
            if predicted:
                err.print("⚠  Conflict prediction:", style="yellow")
                for p in predicted:
                    shared_str = ", ".join(p["shared_files"])
                    err.print(
                        f"   {p['branch']} and {p['parent']} both modify: {shared_str}",
                        style="yellow",
                    )
                err.print("   Proceeding with sync — resolve conflicts if they occur.", style="dim")

        plan = ops.rebase_plan(data)

        if dry_run:
            for step in plan:
                err.print(f"\\[dry-run] rebase {step['branch']} onto {step['onto']}")
        else:
            result = cascade.run_cascade(plan, root, command="sync", quiet=quiet)
            if result["state"] == "paused":
                files = result["conflicted_files"]
                err.print(
                    f"Conflict in {result['conflict_branch']}. "
                    f"Resolve: {', '.join(files) or 'see git status'}"
                )
                err.print("Then run 'arc rebase --continue' or 'arc rebase --abort'.")
                _shared._maybe_print_error_hint(root)
                sys.exit(3)
            if result["state"] == "error":
                err.print(
                    f"Could not start rebase: {result['message']}",
                    style="red",
                )
                err.print("hint: run `git status` to inspect, then retry `arc sync`", style="dim")
                _shared._maybe_print_error_hint(root)
                sys.exit(3)

        if not dry_run:
            data = _prune_merged_branches(data, root, quiet)
            tip.sync_tip_branch(data)

        if not dry_run and not quiet:
            err.print("Stack synced. Run 'arc push' to push to remote.")
        if not dry_run:
            _shared.run_lifecycle_hook(
                root,
                data,
                "post-sync",
                branch=git.current_branch(),
                skip=skip_hooks,
                output_json=output_json,
                quiet=quiet,
            )
            _shared._maybe_print_periodic_hint(root)


@click.command("push")
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
@click.option("--skip-hooks", is_flag=True)
def push_cmd(dry_run, quiet, output_json, skip_hooks):
    """Force-push all stack branches to remote."""
    output_json = _shared._resolve_output_json(output_json)
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    if dry_run:
        for name in names:
            sha = git.get_sha(name)
            err.print(f"\\[dry-run] push {name} ({sha[:8]})")
        return
    with _shared.with_error_hint(root):
        current = git.current_branch()
        _shared.run_lifecycle_hook(
            root,
            data,
            "pre-push",
            branch=current,
            skip=skip_hooks,
            output_json=output_json,
            quiet=quiet,
        )
        to_push = ops.filter_merged_before_push(
            names, data, root, quiet=quiet, output_json=output_json
        )
        if not to_push:
            if not quiet:
                err.print("Nothing to push — all branches already merged.")
            return
        git.force_push(to_push)
        for name in to_push:
            branch_entry = st.get_branch(data, name)
            assert branch_entry is not None
            data = st.update_branch(data, name, revision=branch_entry["revision"] + 1)
        st.save(root, data)
        _shared.run_lifecycle_hook(
            root,
            data,
            "post-push",
            branch=current,
            skip=skip_hooks,
            output_json=output_json,
            quiet=quiet,
        )
        if not quiet:
            skipped = len(names) - len(to_push)
            skip_note = f" ({skipped} already merged, skipped)" if skipped else ""
            err.print(
                f"Pushed {len(to_push)} branch(es).{skip_note} Run 'arc submit' to create pull requests."
            )
        _shared._maybe_print_periodic_hint(root)


@click.command("restack")
@click.argument("branch", required=False)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def restack_cmd(branch: str | None, dry_run: bool, quiet: bool) -> None:
    """Restack a single branch onto its stack parent without full sync."""
    if not _shared._check_setup():
        sys.exit(6)
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    target = branch or git.current_branch()
    names = [b["name"] for b in data["branches"]]
    if target not in names:
        err.print(f"Branch {target!r} is not in the stack.")
        err.print("hint: run arc status to see stack branches", style="dim")
        sys.exit(5)
    parent = ops.parent_branch(data, target)
    if dry_run:
        if not quiet:
            err.print(f"Would rebase {target} onto {parent}.")
        return
    git.checkout(target)
    result = git.rebase_fork_point(parent)
    if result.returncode != 0:
        err.print(f"Rebase of {target} onto {parent} failed.")
        err.print("hint: resolve conflicts then run arc rebase --continue", style="dim")
        sys.exit(3)
    tip.sync_tip_branch(data)
    if not quiet:
        err.print(f"✓ {target} rebased onto {parent}.")
        err.print("hint: run arc push to update remote", style="dim")


@click.command("rebase")
@click.option("--upstack", is_flag=True)
@click.option("--downstack", is_flag=True)
@click.option("--continue", "do_continue", is_flag=True)
@click.option("--abort", "do_abort", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def rebase_cmd(upstack, downstack, do_continue, do_abort, dry_run, quiet):
    """Cascade-rebase the stack or part of it."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)

    if do_continue:
        result = git.rebase_continue()
        if result.returncode != 0:
            err.print("Rebase still has conflicts. Resolve and run 'arc rebase --continue' again.")
            sys.exit(3)
        err.print("Rebase continued.")
        return

    if do_abort:
        git.rebase_abort()
        err.print("Rebase aborted.")
        return

    current = git.current_branch()
    names = st.branch_names(data)

    if upstack:
        targets = [current] + ops.upstack_branches(data, current)
    elif downstack:
        targets = ops.downstack_branches(data, current)
    else:
        targets = names

    plan = [s for s in ops.rebase_plan(data) if s["branch"] in targets]

    with _shared.with_error_hint(root):
        for step in plan:
            branch, onto = step["branch"], step["onto"]
            if dry_run:
                err.print(f"\\[dry-run] rebase {branch} onto {onto}")
                continue
            if not quiet:
                err.print(f"Rebasing {branch} onto {onto}...")
            git.checkout(branch)
            result = git.rebase_fork_point(onto)
            if result.returncode != 0:
                git.rebase_abort()
                files = git.conflicted_files()
                err.print(f"Conflict in {branch}: {', '.join(files) or 'see git status'}")
                err.print("Resolve conflicts, then run 'arc rebase --continue'.")
                _shared._maybe_print_error_hint(root)
                sys.exit(3)

        if not dry_run:
            tip.sync_tip_branch(data)
        if not dry_run and not quiet:
            err.print("Rebase complete.")
