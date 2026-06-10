"""PR lifecycle: submit (create/update PRs), land (merge + restack)."""

from __future__ import annotations

import json as _json
import subprocess as _subprocess
import sys

import click

from arc import git, github, ops
from arc import state as st
from arc.commands import _shared
from arc.commands._shared import err, out


def _run_hooks(root, hooks: list[str]) -> None:
    for cmd in hooks:
        result = _subprocess.run(cmd, shell=True, cwd=root)
        if result.returncode != 0:
            err.print(f"Pre-submit hook failed: {cmd!r} (exit {result.returncode}).")
            err.print("Fix the failure or use --skip-hooks.")
            sys.exit(7)


@click.command("submit")
@click.option("--draft", is_flag=True, default=True)
@click.option("--open", "mark_open", is_flag=True, default=False)
@click.option("--skip-hooks", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def submit_cmd(draft, mark_open, skip_hooks, dry_run, quiet, output_json):
    """Create or update pull requests for the stack."""
    if not output_json and not _shared._is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
    branches = data["branches"]
    if not branches:
        err.print("Stack is empty.")
        return

    try:
        cfg = st.load_config(root)
        hooks = cfg.get("hooks", {}).get("pre-submit", [])
        if hooks and not skip_hooks and not dry_run:
            _run_hooks(root, hooks)
        elif hooks and skip_hooks and not quiet:
            err.print("Warning: pre-submit hooks skipped.")

        use_draft = draft and not mark_open
        created, updated = [], []

        for i, b in enumerate(branches):
            name = b["name"]
            base = data["base"] if i == 0 else branches[i - 1]["name"]

            if dry_run:
                existing = github.get_pr(name)
                action = "create" if not existing else "update"
                err.print(f"\\[dry-run] {action} PR for {name} (base: {base})")
                continue

            _shared.run_lifecycle_hook(
                root,
                data,
                "pre-submit",
                branch=name,
                extra={"pr_number": b["pr_number"], "draft": use_draft},
                skip=skip_hooks,
                output_json=output_json,
                quiet=quiet,
            )

            subject = git.get_commit_subject(name)
            body_text = git.get_commit_body(name)
            count = git.commit_count(base, name)
            title = ops.build_pr_title(subject if count == 1 else "", name)
            entries = [
                {"name": x["name"], "pr_number": x["pr_number"], "is_current": x["name"] == name}
                for x in branches
            ]
            body = ops.build_pr_body(body_text, entries, data["base"])

            existing = github.get_pr(name)
            entry = None
            if not existing:
                pr = github.create_pr(name, base, title, body, draft=use_draft)
                data = st.update_branch(data, name, pr_number=pr["number"])
                entry = {"branch": name, "pr_number": pr["number"], "pr_url": pr["url"]}
                created.append(entry)
            else:
                pr_number = b["pr_number"] or existing["number"]
                github.update_pr_body(pr_number, body)
                if mark_open:
                    github.mark_pr_ready(pr_number)
                entry = {
                    "branch": name,
                    "pr_number": pr_number,
                    "pr_url": existing.get("url"),
                    "revision": b["revision"],
                }
                updated.append(entry)

            if entry:
                _shared.run_lifecycle_hook(
                    root,
                    data,
                    "post-submit",
                    branch=name,
                    extra={"pr_number": entry["pr_number"], "pr_url": entry["pr_url"]},
                    skip=skip_hooks,
                    output_json=output_json,
                    quiet=quiet,
                )

        if not dry_run:
            st.save(root, data)

        if output_json and not dry_run:
            out.print_json(_json.dumps({"created": created, "updated": updated}))
        elif not quiet and not dry_run:
            err.print("PRs ready. View your stack with 'arc status'.")

        if not quiet and not dry_run:
            for b in data["branches"]:
                if b.get("pr_number"):
                    s = github.get_pr_status(b["pr_number"])
                    if s.get("in_merge_queue") and s.get("approved"):
                        err.print(
                            f"→ {b['name']} is approved and in merge queue — safe to build on.",
                            style="dim",
                        )

        if not dry_run:
            _shared._maybe_print_periodic_hint(root)
    except SystemExit:
        raise
    except Exception:
        _shared._maybe_print_error_hint(root)
        raise


@click.command("land")
@click.argument("branch", required=False)
@click.option("-f", "--force", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("--keep-branch", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
@click.option("--skip-hooks", is_flag=True)
@click.pass_context
def land_cmd(ctx, branch, force, dry_run, keep_branch, quiet, output_json, skip_hooks):
    """Land a merged PR and restack branches above it."""
    if not output_json and not _shared._is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        sys.exit(1)

    target = branch or names[0]
    if target not in names:
        err.print(f"Branch {target!r} is not in the stack.")
        sys.exit(5)

    b = st.get_branch(data, target)
    assert b is not None
    if not b["pr_number"]:
        err.print(f"Branch {target!r} has no PR. Run 'arc submit' first.")
        sys.exit(1)

    if not github.pr_is_merged(b["pr_number"]):
        err.print(f"PR #{b['pr_number']} ({target}) is not merged yet.")
        sys.exit(1)

    parent = ops.parent_branch(data, target)
    above = ops.upstack_branches(data, target)
    merge_sha = github.get_merge_commit_sha(b["pr_number"])
    squash_merged = bool(merge_sha) and not git.is_ancestor(git.get_sha(target), parent)

    if dry_run:
        strategy = "squash-merge" if squash_merged else "regular merge"
        err.print(f"\\[dry-run] land {target} ({strategy})")
        for ab in above:
            err.print(f"\\[dry-run] rebase {ab} onto {parent}")
        return

    if not force and not dry_run:
        if ctx.obj.get("no_input"):
            err.print("Requires confirmation. Pass --force to proceed without prompting.")
            sys.exit(1)
        if sys.stdin.isatty():
            click.confirm(f"Delete local branch {target!r}?", abort=True)

    try:
        _shared.run_lifecycle_hook(
            root,
            data,
            "pre-land",
            branch=target,
            extra={"pr_number": b["pr_number"]},
            skip=skip_hooks,
            output_json=output_json,
            quiet=quiet,
        )
        pre_shas = {n: git.get_sha(n) for n in above}
        for ab in above:
            git.checkout(ab)
            if squash_merged:
                result = git.rebase_onto(parent, target, ab)
            else:
                result = git.rebase(parent)
            if result.returncode != 0:
                for n, sha in pre_shas.items():
                    try:
                        git.checkout(n)
                        git._run(["git", "reset", "--hard", sha])
                    except Exception:
                        pass
                err.print(f"Conflict rebasing {ab}. Resolve and run 'arc rebase --continue'.")
                _shared._maybe_print_error_hint(root)
                sys.exit(3)

        if not keep_branch:
            git.checkout(parent)
            git.delete_branch(target)

        data = st.remove_branch(data, target)
        st.save(root, data)

        _shared.run_lifecycle_hook(
            root,
            data,
            "post-land",
            branch=target,
            extra={"pr_number": b["pr_number"]},
            skip=skip_hooks,
            output_json=output_json,
            quiet=quiet,
        )

        if not quiet:
            n_above = len(above)
            err.print(f"{target} landed. {n_above} branch{'es' if n_above != 1 else ''} restacked.")
            err.print("Run 'arc status' to see your updated stack.")
    except SystemExit:
        raise
    except Exception:
        _shared._maybe_print_error_hint(root)
        raise
