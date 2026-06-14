"""Local stack mutation and inspection: init, new, add, status, amend, drop, stack analyze."""

from __future__ import annotations

import json as _json
import sys

import click
from rich.tree import Tree

from arc import git, github, ops
from arc import graph as _graph
from arc import state as st
from arc.commands import _shared
from arc.commands._shared import err, out

_HOOKS_README = """\
# arc lifecycle hooks

Executables in this directory run at lifecycle events, named by event
(git's model). Activate a sample: rename it (drop `.sample`) and
`chmod +x` it.

| Event | Class | Fires |
|---|---|---|
| pre-submit  | gate   | before each PR create/update |
| post-submit | notify | after each PR URL confirmed |
| pre-land    | gate   | before restack + branch delete |
| post-land   | notify | after branch deleted |
| pre-sync    | gate   | before fetch + rebase chain |
| post-sync   | notify | after all branches rebased |
| pre-push    | gate   | before git push --force-with-lease |
| post-push   | notify | after push confirmed |

Gates (`pre-*`): non-zero exit aborts the command (exit 7).
Notifications (`post-*`): exit code ignored.

Context: env vars (ARC_EVENT, ARC_BRANCH, ARC_BASE, ARC_ROOT, ARC_VERSION,
plus per-event extras like ARC_PR_NUMBER, ARC_PR_URL, ARC_DRAFT) and full
JSON on stdin: {"event", "branch", "base", "version", "extra", "stack"}.

Skip for one run: pass --skip-hooks to submit, land, sync, or push.
"""

_PRE_SUBMIT_SAMPLE = """\
#!/bin/sh
# pre-submit gate — runs before each PR create/update.
# Non-zero exit aborts arc submit. Activate:
#   mv pre-submit.sample pre-submit && chmod +x pre-submit
echo "pre-submit: branch=$ARC_BRANCH base=$ARC_BASE draft=$ARC_DRAFT"
# Example: run your linter
# exec ruff check .
exit 0
"""

_POST_LAND_SAMPLE = """\
#!/bin/sh
# post-land notification — runs after a branch lands and is deleted.
# Exit code is ignored. Activate:
#   mv post-land.sample post-land && chmod +x post-land
echo "post-land: PR #$ARC_PR_NUMBER landed from $ARC_BRANCH"
# Example: notify your team chat here.
exit 0
"""


def _scaffold_hooks_dir(root) -> None:
    hooks_dir = root / ".arc" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("README.md", _HOOKS_README),
        ("pre-submit.sample", _PRE_SUBMIT_SAMPLE),
        ("post-land.sample", _POST_LAND_SAMPLE),
    ):
        path = hooks_dir / name
        if not path.exists():
            path.write_text(content)


@click.command("init")
@click.option("--base", default=None, help="Trunk branch (default: repo default).")
@click.option("--prefix", default=None, help="Branch prefix applied on 'arc new'.")
@click.option("-q", "--quiet", is_flag=True)
def init_cmd(base, prefix, quiet):
    """Initialize a stack in the current repo."""
    if not _shared._check_setup():
        sys.exit(6)
    root = git.find_repo_root()
    resolved_base = base or git.default_branch()
    data = st.init_state(base=resolved_base, prefix=prefix)
    st.save(root, data)
    _scaffold_hooks_dir(root)
    _shared._update_gitignore(root, ".arc/state.json")
    if not quiet:
        err.print(f"Stack initialized (base: {resolved_base}).")
        err.print("Run 'arc new <branch>' to create your first branch.")


@click.command("new")
@click.argument("branch")
@click.option("-q", "--quiet", is_flag=True)
def new_cmd(branch, quiet):
    """Create a new branch and add it to the stack."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
    name = st.apply_prefix(data, branch)
    data = st.add_branch(data, name)
    git.create_branch(name, "HEAD")
    st.save(root, data)
    if not quiet:
        err.print(f"Branch {name} created.")
        err.print(
            "Commit your changes, then run 'arc new <branch>' to add another or 'arc status' to view your stack."
        )


@click.command("add")
@click.argument("branch")
@click.option("-q", "--quiet", is_flag=True)
def add_cmd(branch, quiet):
    """Adopt an existing branch into the stack."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
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


@click.command("status")
@click.option("--json", "output_json", is_flag=True)
@click.option("--plain", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
def status_cmd(output_json, plain, quiet):
    """Show the current stack."""
    if not output_json and not _shared._is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
    current = git.current_branch()
    names = st.branch_names(data)

    try:
        commit_counts = {n: git.commit_count(data["base"], n) for n in names}
    except Exception:
        _shared._exit_json_error(
            f"base branch '{data['base']}' not found — run `arc init --base <branch>` to fix",
            exit_code=1,
            output_json=output_json,
        )
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
    if not output_json and not quiet:
        stale = _stale_pr_bases(data, status)
        if stale:
            for name in stale:
                err.print(
                    f"⚠  {name} — PR base is stale. Run arc sync to retarget.", style="yellow"
                )
    if not quiet:
        merged = [b["name"] for b in status.get("branches", []) if b.get("is_merged")]
        if merged:
            err.print(f"→ {', '.join(merged)} merged — run arc sync to clean up", style="dim")
        hint = ops.next_step_hint(status)
        if hint:
            err.print(f"\n→ {hint}")
    _shared._maybe_print_periodic_hint(root)


def _stale_pr_bases(data: dict, status: dict) -> list[str]:
    """Return branch names whose PR base differs from their expected stack parent."""
    stale = []
    branches = data.get("branches", [])
    for i, b in enumerate(branches):
        if not b.get("pr_number"):
            continue
        expected_base = data["base"] if i == 0 else branches[i - 1]["name"]
        pr = github.get_pr(b["name"])
        if pr and pr.get("baseRefName") and pr["baseRefName"] != expected_base:
            stale.append(b["name"])
    return stale


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


@click.command("amend")
@click.option("-q", "--quiet", is_flag=True)
def amend_cmd(quiet):
    """Update commit message with PR link and stack position."""
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root)
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


@click.command("drop")
@click.argument("branch")
@click.option("-f", "--force", is_flag=True)
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def drop_cmd(ctx, branch, force, dry_run, quiet, output_json):
    """Remove a branch from the stack and restack above it."""
    if not output_json and not _shared._is_tty():
        output_json = True
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
    name = st.apply_prefix(data, branch)
    if not st.get_branch(data, name):
        err.print(f"{name!r} is not in the stack.")
        sys.exit(5)
    if not force and not dry_run:
        if ctx.obj.get("no_input"):
            err.print("Requires confirmation. Pass --force to proceed without prompting.")
            sys.exit(1)
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
                _shared._maybe_print_error_hint(root)
                sys.exit(3)
        data = st.remove_branch(data, name)
        st.save(root, data)
        if not quiet:
            err.print(f"{name} removed from stack.")
    except SystemExit:
        raise
    except Exception:
        _shared._maybe_print_error_hint(root)
        raise


@click.group("stack")
def stack_group() -> None:
    """Stack analysis and intelligence commands."""


@stack_group.command("analyze")
@click.option("--json", "output_json", is_flag=True)
def stack_analyze_cmd(output_json: bool) -> None:
    """Show critical path, safe-to-land branches, and blockers."""
    if not _shared._check_setup():
        sys.exit(6)
    root = git.find_repo_root()
    data = _shared._load_state_or_exit(root, output_json=output_json)
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
