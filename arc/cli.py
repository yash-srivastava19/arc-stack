from __future__ import annotations
import json as _json
import subprocess as _subprocess
import sys
import click
from rich.console import Console
from rich.tree import Tree
from arc import git, github, state as st, ops

err = Console(stderr=True)
out = Console()

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option("0.1.0", prog_name="arc")
@click.option("--no-color", is_flag=True, envvar="NO_COLOR", is_eager=True,
              help="Disable color output.")
@click.pass_context
def cli(ctx, no_color):
    """arc — stacked pull request manager."""
    ctx.ensure_object(dict)
    if no_color:
        import os
        os.environ["NO_COLOR"] = "1"


def _check_setup() -> bool:
    """Returns True if environment is ready. Prints errors and returns False if not."""
    ok = True
    if not git.is_installed():
        err.print("git is not installed. Install git and retry.")
        ok = False
    if not github.is_installed():
        err.print("gh is not installed. Install from https://cli.github.com and retry.")
        ok = False
    elif not github.is_authenticated():
        err.print("gh is not authenticated. Run 'gh auth login' then retry.")
        ok = False
    return ok


def _load_state_or_exit(root):
    try:
        return st.load(root)
    except FileNotFoundError as e:
        err.print(str(e))
        sys.exit(2)


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
        err.print("Commit your changes, then run 'arc new <branch>' to add another or 'arc status' to view your stack.")


@cli.command("add")
@click.argument("branch")
@click.option("-q", "--quiet", is_flag=True)
def add_cmd(branch, quiet):
    """Adopt an existing branch into the stack."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    name = st.apply_prefix(data, branch)
    if not git.branch_exists(name):
        err.print(f"Branch {name!r} does not exist locally. Create it first.")
        sys.exit(1)
    if st.get_branch(data, name):
        err.print(f"Branch {name!r} is already in the stack.")
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
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    current = git.current_branch()
    names = st.branch_names(data)

    commit_counts = {n: git.commit_count(data["base"], n) for n in names}
    needs_rebase_flags = {
        n: not git.is_ancestor(ops.parent_branch(data, n), n)
        for n in names
    }
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


@cli.command("sync")
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def sync_cmd(dry_run, quiet, output_json):
    """Fetch and cascade-rebase the stack."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    if not st.branch_names(data):
        err.print("Stack is empty. Run 'arc new <branch>' to add a branch.")
        return

    if not quiet:
        err.print("Fetching...", end=" ")
    if not dry_run:
        git.fetch()
    if not quiet:
        err.print("done.")

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
            sys.exit(3)

    if not dry_run and not quiet:
        err.print("Stack synced. Run 'arc push' to push to remote.")


@cli.command("push")
@click.option("-n", "--dry-run", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("--json", "output_json", is_flag=True)
def push_cmd(dry_run, quiet, output_json):
    """Force-push all stack branches to remote."""
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    names = st.branch_names(data)
    if not names:
        err.print("Stack is empty.")
        return
    if dry_run:
        for name in names:
            sha = git.get_sha(name)
            err.print(f"\\[dry-run] push {name} ({sha[:8]})")
        return
    git.force_push(names)
    for name in names:
        current_rev = st.get_branch(data, name)["revision"]
        data = st.update_branch(data, name, revision=current_rev + 1)
    st.save(root, data)
    if not quiet:
        err.print(f"Pushed {len(names)} branches. Run 'arc submit' to create pull requests.")


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
    root = git.find_repo_root()
    data = _load_state_or_exit(root)
    branches = data["branches"]
    if not branches:
        err.print("Stack is empty.")
        return

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
            updated.append({"branch": name, "pr_number": pr_number,
                            "pr_url": existing.get("url"), "revision": b["revision"]})

    if not dry_run:
        st.save(root, data)

    if output_json and not dry_run:
        out.print_json(_json.dumps({"created": created, "updated": updated}))
    elif not quiet and not dry_run:
        err.print("PRs ready. View your stack with 'arc status'.")
