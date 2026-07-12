"""Environment and meta commands: setup, doctor, completions, upgrade, report, dashboard."""

from __future__ import annotations

import os
import sys

import click

from arc import __version__, git, github
from arc.commands import _shared
from arc.commands._shared import err, out


def _install_completions() -> str | None:
    """Write the completion hook to the user's shell rc file.

    Returns a human-readable description of what was done, or None if the
    shell is unsupported or the hook was already present.
    """
    from pathlib import Path

    shell = os.path.basename(os.environ.get("SHELL", ""))
    home = Path.home()

    if shell == "zsh":
        rc = home / ".zshrc"
        line = 'eval "$(arc completions zsh)"'
    elif shell == "bash":
        rc = home / ".bashrc"
        line = 'eval "$(arc completions bash)"'
    elif shell == "fish":
        rc = home / ".config" / "fish" / "config.fish"
        line = "arc completions fish | source"
    else:
        return None

    rc.parent.mkdir(parents=True, exist_ok=True)
    existing = rc.read_text() if rc.exists() else ""
    if "arc completions" in existing:
        return f"completions already in {rc}"

    with rc.open("a") as f:
        f.write(f"\n# arc shell completions\n{line}\n")
    return f"completions added to {rc}"


@click.command("setup")
@click.option("-q", "--quiet", is_flag=True)
def setup(quiet):
    """Check environment and configure git for arc."""
    if not _shared._check_setup():
        sys.exit(6)
    git.set_config("rerere.enabled", "true", global_=True)
    completion_result = _install_completions()
    if not quiet:
        err.print("git rerere enabled.")
        if completion_result:
            err.print(completion_result)
        err.print("Ready. cd into a repo and run 'arc init' to create a stack.")


@click.command("doctor")
def doctor_cmd() -> None:
    """Check environment and report what's wrong."""
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

    err.print(f"✓ arc version {__version__}", style="green")

    root = None
    try:
        root = git.find_repo_root()
    except RuntimeError:
        pass

    if root:
        from arc import state as st

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

        edit_state_path = root / ".arc" / "edit-in-progress.json"
        if edit_state_path.exists():
            if git.is_mid_rebase(root):
                err.print(
                    "⚠  arc edit is paused mid-rebase — run 'arc edit --continue' or 'arc edit --abort'",
                    style="yellow",
                )
            else:
                err.print(
                    "⚠  stale edit-in-progress.json found (no active rebase) — run 'arc edit --abort' to clean up",
                    style="yellow",
                )

        cascade_state_path = root / ".arc" / "rebase-in-progress.json"
        if cascade_state_path.exists():
            if git.is_mid_rebase(root):
                err.print(
                    "⚠  a rebase is paused mid-cascade — run 'arc rebase --continue' or 'arc rebase --abort'",
                    style="yellow",
                )
            else:
                err.print(
                    "⚠  stale rebase-in-progress.json found (no active rebase) — run 'arc rebase --abort' to clean up",
                    style="yellow",
                )

        hooks_dir = root / ".arc" / "hooks"
        if hooks_dir.is_dir():
            from arc.hooks import EVENTS

            for event in EVENTS:
                hook_path = hooks_dir / event
                if hook_path.is_file() and not os.access(hook_path, os.X_OK):
                    err.print(f"✗ .arc/hooks/{event} exists but is not executable", style="red")
                    err.print(f"  fix: chmod +x .arc/hooks/{event}", style="dim")
                    ok = False
            known = set(EVENTS) | {"README.md"}
            for entry in sorted(hooks_dir.iterdir()):
                if (
                    entry.is_file()
                    and entry.name not in known
                    and not entry.name.endswith(".sample")
                ):
                    err.print(
                        f"  .arc/hooks/{entry.name} is not a known hook event (ignored)",
                        style="dim",
                    )

    if not ok:
        sys.exit(1)


@click.command("completions")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completions_cmd(shell: str) -> None:
    """Print shell completion script.

    Usage:
      bash: eval "$(arc completions bash)"
      zsh:  eval "$(arc completions zsh)"
      fish: arc completions fish | source
    """
    import subprocess as _sub

    env = {**os.environ, "_ARC_COMPLETE": f"{shell}_source"}
    result = _sub.run(["arc"], env=env, capture_output=True, text=True)
    print(result.stdout, end="")


@click.command("upgrade")
def upgrade_cmd() -> None:
    """Upgrade arc to the latest version."""
    import subprocess as _sub

    # prefer uv tool upgrade, fall back to pip
    if _sub.run(["uv", "--version"], capture_output=True).returncode == 0:
        result = _sub.run(["uv", "tool", "upgrade", "arc-prs"], capture_output=True, text=True)
    else:
        result = _sub.run(["pip", "install", "-U", "arc-prs"], capture_output=True, text=True)
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        if output:
            err.print(output)
        err.print(
            "hint:  install with `uv tool install arc-prs` or `pip install arc-prs`",
            style="dim",
        )
        sys.exit(1)
    err.print("arc upgraded successfully.")


@click.command("report")
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
        user_text = _shared._open_editor(template)
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


@click.command("dashboard")
@click.option(
    "--theme",
    default=None,
    metavar="NAME",
    help="Color theme override (arc, dracula, nord, gruvbox, catppuccin, tokyo-night).",
)
@click.pass_context
def dashboard_cmd(ctx, theme: str | None) -> None:
    """Launch interactive dashboard for stacked PRs."""
    import arc.git as git
    from arc.dashboard import run_dashboard

    root = git.find_repo_root()
    run_dashboard(root, theme_name=theme)
