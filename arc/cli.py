from __future__ import annotations
import json as _json
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
