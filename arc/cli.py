from __future__ import annotations

import json as _json
import os
import random
import subprocess as _subprocess
import sys
import tempfile

import click
from rich.console import Console
from rich.tree import Tree

from arc import conflicts as _conflicts
from arc import git, github, ops
from arc import graph as _graph
from arc import state as st

err = Console(stderr=True)
out = Console()

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option("0.1.0", prog_name="arc")
@click.option(
    "--no-color", is_flag=True, envvar="NO_COLOR", is_eager=True, help="Disable color output."
)
@click.pass_context
def cli(ctx, no_color):
    """arc — stacked pull request manager."""
    ctx.ensure_object(dict)
    if no_color:
        import os

        os.environ["NO_COLOR"] = "1"


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
) -> None:
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


@cli.command()
@click.option("-q", "--quiet", is_flag=True)
def setup(quiet):
    """Check environment and configure git for arc."""
    if not _check_setup():
        sys.exit(6)
    git.set_config("rerere.enabled", "true", global_=True)
    if not quiet:
        err.print("git rerere enabled.")
        err.print("Ready. cd into a repo and run 'arc init' to create a stack.")


@cli.command("doctor")
def doctor_cmd() -> None:
    """Check environment and report what's wrong."""
    import importlib.metadata

    ok = True

    def check(label: str, passed: bool, fix: str) -> None:
        nonlocal ok
        if passed:
            err.print(f"✓ {label}", style="green")
        else:
            err.print(f"✗ {label}", style="red")
            err.print(f"  fix: {fix}", style="dim")
            ok = False

    check("git installed", git.is_installed(), "install git from https://git-scm.com")

    gh_ok = github.is_installed()
    check("gh installed", gh_ok, "install from https://cli.github.com")
    if gh_ok:
        check("gh authenticated", github.is_authenticated(), "run gh auth login")

    try:
        current = importlib.metadata.version("arc-prs")
    except importlib.metadata.PackageNotFoundError:
        current = "unknown"
    err.print(f"✓ arc version {current}", style="green")

    root = None
    try:
        root = git.find_repo_root()
    except RuntimeError:
        pass

    if root:
        state_path = root / ".arc" / "state.json"
        if state_path.exists():
            try:
                data = st.load(root)
                n = len(data.get("branches", []))
                err.print(f"✓ stack initialized ({n} branches)", style="green")
            except Exception as e:
                err.print(f"✗ .arc/state.json is corrupt: {e}", style="red")
                ok = False
        else:
            err.print("  stack not initialized in this repo (run arc init)", style="dim")

    if not ok:
        sys.exit(1)


@cli.command("init")
@click.option("--base", default=None, help="Trunk branch (default: repo default).")
@click.option("--prefix", default=None, help="Branch prefix applied on 'arc new'.")
@click.option("-q", "--quiet", is_flag=True)
def init_cmd(base, prefix, quiet):
    """Initialize a stack in the current repo."""
    if not _check_setup():
        sys.exit(6)
    root = git.find_repo_root()
    resolved_base = base or git.default_branch()
    data = st.init_state(base=resolved_base, prefix=prefix)
    st.save(root, data)
    _update_gitignore(root, ".arc/state.json")
    if not quiet:
        err.print(f"Stack initialized (base: {resolved_base}).")
        err.print("Run 'arc new <branch>' to create your first branch.")


@cli.command("new")
@click.argument("branch")
@click.option("-q", "--quiet", is_flag=True)
def new_cmd(branch, quiet):
    """Create a new branch and add it to the stack."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    name = st.apply_prefix(data, branch)
    data = st.add_branch(data, name)
    git.create_branch(name, "HEAD")
    st.save(root, data)
    if not quiet:
        err.print(f"Branch {name} created.")
        err.print(
            "Commit your changes, then run 'arc new <branch>' to add another or 'arc status' to view your stack."
        )


@cli.command("restack")
@click.argument("branch", required=False)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def restack_cmd(branch: str | None, dry_run: bool, quiet: bool) -> None:
    """Restack a single branch onto its stack parent without full sync."""
    if not _check_setup():
        sys.exit(6)
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
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
    result = git.rebase(parent)
    if result.returncode != 0:
        err.print(f"Rebase of {target} onto {parent} failed.")
        err.print("hint: resolve conflicts then run arc rebase --continue", style="dim")
        sys.exit(3)
    if not quiet:
        err.print(f"✓ {target} rebased onto {parent}.")
        err.print("hint: run arc push to update remote", style="dim")


@cli.command("add")
@click.argument("branch")
@click.option("-q", "--quiet", is_flag=True)
def add_cmd(branch, quiet):
    """Adopt an existing branch into the stack."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    name = st.apply_prefix(data, branch)
    if not git.branch_exists(name):
        err.print(f"Branch {name!r} does not exist locally.")
        err.print(f"hint: git checkout -b {name}", style="dim")
        sys.exit(1)
    if st.get_branch(data, name):
        err.print(f"Branch {name!r} is already in the stack.")
        err.print("hint: run arc status to see the current stack", style="dim")
        sys.exit(1)
    data = st.add_branch(data, name)
    st.save(root, data)
    if not quiet:
        err.print(f"Branch {name} added to stack.")


@cli.command("status")
@click.option("--json", "output_json", is_flag=True)
@click.option("--plain", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def status_cmd(output_json, plain, quiet):
    """Show the current stack."""
    if not output_json and not _is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
    current = git.current_branch()
    names = st.branch_names(data)

    commit_counts = {n: git.commit_count(data["base"], n) for n in names}
    needs_rebase_flags = {n: not git.is_ancestor(ops.parent_branch(data, n), n) for n in names}
    pr_info = {}
    for b in data["branches"]:
        if b["pr_number"]:
            info = github.get_pr(b["name"])
            if info:
                pr_info[b["name"]] = {
                    "pr_url": info.get("url"),
                    "pr_state": info.get("state"),
                    "is_merged": info.get("state") == "MERGED",
                }

    status = ops.stack_status(data, current, commit_counts, pr_info, needs_rebase_flags)

    if plain:
        out.print("\n".join(names))
        return

    if output_json:
        out.print_json(_json.dumps(status))
        return

    _render_status_tree(status)
    if not quiet:
        hint = ops.next_step_hint(status)
        if hint:
            err.print(f"\n→ {hint}")
    _maybe_print_periodic_hint(root)


def _render_status_tree(status: dict) -> None:
    tree = Tree(f"arc  (base: {status['base']})")
    node = tree
    for b in status["branches"]:
        pr_str = f"PR #{b['pr_number']}" if b["pr_number"] else "no PR"
        rev_str = f"  (rev {b['revision']})" if b["revision"] > 0 else ""
        rebase_str = "  ← needs rebase" if b["needs_rebase"] else ""
        current_str = " *" if b["is_current"] else ""
        label = f"{b['name']}{current_str}  {pr_str}  {b['commits']} commits{rev_str}{rebase_str}"
        node = node.add(label)
    out.print(tree)


def detect_merged_branches(data: dict) -> set[str]:
    """Find branches in state that are actually merged (PR was merged on GitHub)."""
    merged = set()
    for branch in data["branches"]:
        pr_number = branch.get("pr_number")
        if pr_number and github.pr_is_merged(pr_number):
            merged.add(branch["name"])
    return merged


def retarget_dependent_prs(data: dict, merged_branches: set[str], quiet: bool = False) -> dict:
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


@cli.command("sync")
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def sync_cmd(dry_run, quiet, output_json):
    """Fetch and cascade-rebase the stack."""
    if not output_json and not _is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
    if not st.branch_names(data):
        err.print("Stack is empty.")
        err.print("hint: run arc new <branch> to create your first branch", style="dim")
        return

    try:
        if not quiet:
            err.print("Fetching...", end=" ")
        if not dry_run:
            git.fetch()
        if not quiet:
            err.print("done.")

        # Squash-merge recovery: detect and remove branches already squash-merged into base
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
                    git.delete_branch(name)
        if squash_merged and not dry_run:
            data["branches"] = [b for b in data["branches"] if b["name"] not in squash_merged]
            st.save(root, data)

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
        pre_shas = {}
        if not dry_run:
            pre_shas = {b["name"]: git.get_sha(b["name"]) for b in data["branches"]}

        for step in plan:
            branch, onto = step["branch"], step["onto"]
            if dry_run:
                err.print(f"\\[dry-run] rebase {branch} onto {onto}")
                continue
            if not quiet:
                err.print(f"Rebasing {branch} onto {onto}...")
            git.checkout(branch)
            result = git.rebase(onto)
            if result.returncode != 0:
                git.rebase_abort()
                for name, sha in pre_shas.items():
                    try:
                        git.checkout(name)
                        git._run(["git", "reset", "--hard", sha])
                    except Exception:
                        pass
                files = git.conflicted_files()
                err.print(f"Conflict in {branch}. Resolve: {', '.join(files) or 'see git status'}")
                err.print("Then run 'arc rebase --continue' or 'arc rebase --abort'.")
                _maybe_print_error_hint(root)
                sys.exit(3)

        if not dry_run:
            # Auto-retarget PRs whose base was merged
            merged_branches = detect_merged_branches(data)
            if merged_branches:
                data = retarget_dependent_prs(data, merged_branches, quiet)
                st.save(root, data)

        if not dry_run and not quiet:
            err.print("Stack synced. Run 'arc push' to push to remote.")
        if not dry_run:
            _maybe_print_periodic_hint(root)
    except SystemExit:
        raise
    except Exception:
        _maybe_print_error_hint(root)
        raise


@cli.command("push")
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def push_cmd(dry_run, quiet, output_json):
    """Force-push all stack branches to remote."""
    if not output_json and not _is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    try:
        if dry_run:
            for name in names:
                sha = git.get_sha(name)
                err.print(f"\\[dry-run] push {name} ({sha[:8]})")
            return
        git.force_push(names)
        for name in names:
            branch_entry = st.get_branch(data, name)
            assert branch_entry is not None
            current_rev = branch_entry["revision"]
            data = st.update_branch(data, name, revision=current_rev + 1)
        st.save(root, data)
        if not quiet:
            err.print(f"Pushed {len(names)} branches. Run 'arc submit' to create pull requests.")
        _maybe_print_periodic_hint(root)
    except SystemExit:
        raise
    except Exception:
        _maybe_print_error_hint(root)
        raise


def _run_hooks(root, hooks: list[str]) -> None:
    for cmd in hooks:
        result = _subprocess.run(cmd, shell=True, cwd=root)
        if result.returncode != 0:
            err.print(f"Pre-submit hook failed: {cmd!r} (exit {result.returncode}).")
            err.print("Fix the failure or use --skip-hooks.")
            sys.exit(7)


@cli.command("submit")
@click.option("--draft", is_flag=True, default=True)
@click.option("--open", "mark_open", is_flag=True, default=False)
@click.option("--skip-hooks", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def submit_cmd(draft, mark_open, skip_hooks, dry_run, quiet, output_json):
    """Create or update pull requests for the stack."""
    if not output_json and not _is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
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
            if not existing:
                pr = github.create_pr(name, base, title, body, draft=use_draft)
                data = st.update_branch(data, name, pr_number=pr["number"])
                created.append({"branch": name, "pr_number": pr["number"], "pr_url": pr["url"]})
            else:
                pr_number = b["pr_number"] or existing["number"]
                github.update_pr_body(pr_number, body)
                if mark_open:
                    github.mark_pr_ready(pr_number)
                updated.append(
                    {
                        "branch": name,
                        "pr_number": pr_number,
                        "pr_url": existing.get("url"),
                        "revision": b["revision"],
                    }
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
            _maybe_print_periodic_hint(root)
    except SystemExit:
        raise
    except Exception:
        _maybe_print_error_hint(root)
        raise


# ---------------------------------------------------------------------------
# Task 13: arc land
# ---------------------------------------------------------------------------


@cli.command("land")
@click.argument("branch", required=False)
@click.option("-f", "--force", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("--keep-branch", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def land_cmd(branch, force, dry_run, keep_branch, quiet, output_json):
    """Land a merged PR and restack branches above it."""
    if not output_json and not _is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
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

    if not force and sys.stdin.isatty():
        click.confirm(f"Delete local branch {target!r}?", abort=True)

    try:
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
                _maybe_print_error_hint(root)
                sys.exit(3)

        if not keep_branch:
            git.checkout(parent)
            git.delete_branch(target)

        data = st.remove_branch(data, target)
        st.save(root, data)

        if not quiet:
            n_above = len(above)
            err.print(f"{target} landed. {n_above} branch{'es' if n_above != 1 else ''} restacked.")
            err.print("Run 'arc status' to see your updated stack.")
    except SystemExit:
        raise
    except Exception:
        _maybe_print_error_hint(root)
        raise


# ---------------------------------------------------------------------------
# Task 14: arc amend + arc drop
# ---------------------------------------------------------------------------


@cli.command("amend")
@click.option("-q", "--quiet", is_flag=True)
def amend_cmd(quiet):
    """Update commit message with PR link and stack position."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    current = git.current_branch()
    b = st.get_branch(data, current)
    if not b:
        err.print(f"{current!r} is not in the stack.")
        sys.exit(5)
    names = st.branch_names(data)
    position = f"{names.index(current) + 1}/{len(names)}"
    existing_msg = git.get_commit_message()
    pr_info = github.get_pr(current) if b["pr_number"] else None
    pr_url = pr_info.get("url", "") if pr_info else ""
    footer = f"\nArc-PR: {pr_url}\nArc-Stack-Position: {position}"
    import re

    if "Arc-PR:" not in existing_msg:
        git.amend_message(existing_msg + footer)
    else:
        new_msg = re.sub(r"\nArc-PR:.*(\nArc-Stack-Position:.*)?", footer, existing_msg)
        git.amend_message(new_msg)
    if not quiet:
        err.print("Commit message updated.")


@cli.command("drop")
@click.argument("branch")
@click.option("-f", "--force", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def drop_cmd(branch, force, dry_run, quiet, output_json):
    """Remove a branch from the stack and restack above it."""
    if not output_json and not _is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
    name = st.apply_prefix(data, branch)
    if not st.get_branch(data, name):
        err.print(f"{name!r} is not in the stack.")
        sys.exit(5)
    if not force and not dry_run:
        if not sys.stdin.isatty():
            err.print(f"Use --force to drop {name!r} non-interactively.")
            sys.exit(5)
        click.confirm(f"Remove {name!r} from stack?", default=False, abort=True)
    parent = ops.parent_branch(data, name)
    above = ops.upstack_branches(data, name)
    if dry_run:
        err.print(f"\\[dry-run] remove {name} from stack")
        for ab in above:
            err.print(f"\\[dry-run] rebase {ab} onto {parent}")
        return
    try:
        for ab in above:
            git.checkout(ab)
            result = git.rebase(parent)
            if result.returncode != 0:
                git.rebase_abort()
                err.print(f"Conflict rebasing {ab}. Resolve and run 'arc rebase --continue'.")
                _maybe_print_error_hint(root)
                sys.exit(3)
        data = st.remove_branch(data, name)
        st.save(root, data)
        if not quiet:
            err.print(f"{name} removed from stack.")
    except SystemExit:
        raise
    except Exception:
        _maybe_print_error_hint(root)
        raise


# ---------------------------------------------------------------------------
# Task 15: arc rebase
# ---------------------------------------------------------------------------


@cli.command("rebase")
@click.option("--upstack", is_flag=True)
@click.option("--downstack", is_flag=True)
@click.option("--continue", "do_continue", is_flag=True)
@click.option("--abort", "do_abort", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def rebase_cmd(upstack, downstack, do_continue, do_abort, dry_run, quiet):
    """Cascade-rebase the stack or part of it."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)

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

    try:
        for step in plan:
            branch, onto = step["branch"], step["onto"]
            if dry_run:
                err.print(f"\\[dry-run] rebase {branch} onto {onto}")
                continue
            if not quiet:
                err.print(f"Rebasing {branch} onto {onto}...")
            git.checkout(branch)
            result = git.rebase(onto)
            if result.returncode != 0:
                git.rebase_abort()
                files = git.conflicted_files()
                err.print(f"Conflict in {branch}: {', '.join(files) or 'see git status'}")
                err.print("Resolve conflicts, then run 'arc rebase --continue'.")
                _maybe_print_error_hint(root)
                sys.exit(3)

        if not dry_run and not quiet:
            err.print("Rebase complete.")
    except SystemExit:
        raise
    except Exception:
        _maybe_print_error_hint(root)
        raise


# ---------------------------------------------------------------------------
# Task 16: Navigation commands
# ---------------------------------------------------------------------------


@cli.command("checkout")
@click.argument("target")
def checkout_cmd(target):
    """Check out a branch by name or index (1-based)."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    if target.isdigit():
        name = ops.branch_at_index(data, int(target))
        if not name:
            err.print(f"No branch at index {target}.")
            sys.exit(5)
    else:
        name = st.apply_prefix(data, target)
        if not st.get_branch(data, name):
            err.print(f"{name!r} is not in the stack.")
            sys.exit(5)
    git.checkout(name)
    err.print(f"Switched to {name}.")


def _navigate(n: int, direction: int) -> None:
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    names = st.branch_names(data)
    current = git.current_branch()
    if current not in names:
        err.print(f"{current!r} is not in the stack.")
        sys.exit(5)
    idx = names.index(current) + direction * n
    idx = max(0, min(idx, len(names) - 1))
    git.checkout(names[idx])
    err.print(f"Switched to {names[idx]}.")


@cli.command("up")
@click.argument("n", default=1, type=int)
def up_cmd(n):
    """Move up n branches toward the top."""
    _navigate(n, 1)


@cli.command("down")
@click.argument("n", default=1, type=int)
def down_cmd(n):
    """Move down n branches toward the trunk."""
    _navigate(n, -1)


@cli.command("top")
def top_cmd():
    """Jump to the topmost branch."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    git.checkout(names[-1])
    err.print(f"Switched to {names[-1]}.")


@cli.command("bottom")
def bottom_cmd():
    """Jump to the bottommost branch."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    git.checkout(names[0])
    err.print(f"Switched to {names[0]}.")


# ---------------------------------------------------------------------------
# Task 11: arc stack analyze
# ---------------------------------------------------------------------------


@cli.group("stack")
def stack_group() -> None:
    """Stack analysis and intelligence commands."""


@stack_group.command("analyze")
@click.option("--json", "output_json", is_flag=True)
def stack_analyze_cmd(output_json: bool) -> None:
    """Show critical path, safe-to-land branches, and blockers."""
    if not _check_setup():
        sys.exit(6)
    root = git.find_repo_root()
    data = _load_state_or_exit(root, output_json=output_json)
    if not data.get("branches"):
        err.print("Stack is empty.")
        err.print("hint: run arc new <branch> to create your first branch", style="dim")
        sys.exit(1)
    statuses: dict[str, dict] = {}
    for b in data["branches"]:
        if b.get("pr_number"):
            statuses[b["name"]] = github.get_pr_status(b["pr_number"])
        else:
            statuses[b["name"]] = {
                "approved": False,
                "ci_passing": None,
                "draft": True,
                "in_merge_queue": False,
            }
    analysis = _graph.analyze_stack(data, statuses)
    if output_json:
        import json as _j

        out.print_json(
            _j.dumps(
                {
                    "critical_path": analysis.critical_path,
                    "safe_to_land": analysis.safe_to_land,
                    "blocked": analysis.blocked,
                    "in_merge_queue": analysis.in_merge_queue,
                }
            )
        )
        return
    out.print(f"\nStack: {data['base']} → {' → '.join(analysis.critical_path)}\n")
    for b in data["branches"]:
        name = b["name"]
        pr = f"PR #{b['pr_number']}" if b.get("pr_number") else "no PR"
        if name in analysis.safe_to_land:
            icon, msg = "✅", "ready to land"
        elif name in analysis.in_merge_queue:
            icon, msg = "🔀", "in merge queue"
        elif name in analysis.blocked:
            icon, msg = "⏳", f"blocked: {analysis.blocked[name]}"
        else:
            icon, msg = "○", "no PR yet" if not b.get("pr_number") else "pending"
        out.print(f"  {icon} {name} ({pr}) — {msg}")
    if analysis.safe_to_land:
        out.print(f"\nSAFE TO LAND NOW: {', '.join(analysis.safe_to_land)}")
    if analysis.blocked:
        out.print(f"CRITICAL PATH: {' → '.join(analysis.critical_path)}")


# ---------------------------------------------------------------------------
# Task 3: arc report
# ---------------------------------------------------------------------------


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


@cli.command("report")
@click.option("--bug", is_flag=True)
@click.option("--feedback", is_flag=True)
@click.option("--message", type=str, default=None)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def report_cmd(bug, feedback, message, dry_run, quiet):
    """Report a bug or share feedback."""
    from arc import report as report_module

    git.find_repo_root()

    # Determine issue type
    issue_type = "bug" if bug else ("feedback" if feedback else "bug")

    # Non-TTY requires --message
    if not sys.stdin.isatty() and not message:
        err.print("Non-interactive mode requires --message flag.")
        err.print('Usage: arc report --bug --message "description"')
        sys.exit(5)

    # Get user text (either from --message or editor)
    if message:
        user_text = message
    else:
        # TTY: open editor
        template = report_module.collect_env_context() + "\n---\n\nDescribe the issue here..."
        user_text = _open_editor(template)
        if not user_text or not user_text.strip():
            err.print("Aborted: no issue description provided.")
            sys.exit(1)

    # Format issue body
    body = report_module.format_issue_body(user_text, error_message=None)

    # Dry-run: print and exit
    if dry_run:
        out.print(body)
        return

    # Create issue
    title = f"[{issue_type}] User report"
    result = github.create_issue(title, body)

    if result:
        if not quiet:
            err.print(f"Issue #{result['number']} created: {result['html_url']}")
        out.print(result["html_url"])
    else:
        err.print("Failed to create issue.")
        sys.exit(4)
