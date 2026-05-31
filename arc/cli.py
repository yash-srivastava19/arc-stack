from __future__ import annotations
import json as _json
import sys
import click
from rich.console import Console
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
