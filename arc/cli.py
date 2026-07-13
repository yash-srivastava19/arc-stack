from __future__ import annotations

import click

from arc import __version__
from arc.commands import ALL_COMMANDS
from arc.commands._shared import err, out  # noqa: F401  (re-export: tests patch arc.cli.err.print)
from arc.exceptions import ArcError

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class ArcGroup(click.Group):
    """Catches ArcError at the CLI boundary so failures print a clean message
    instead of a raw Python traceback (e.g. a `gh` call failing because a
    branch was never pushed)."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except ArcError as e:
            err.print(str(e))
            ctx.exit(1)


@click.group(context_settings=CONTEXT_SETTINGS, cls=ArcGroup)
@click.version_option(version=__version__, prog_name="arc")
@click.option(
    "--no-color", is_flag=True, envvar="NO_COLOR", is_eager=True, help="Disable color output."
)
@click.option(
    "--no-input",
    is_flag=True,
    envvar="ARC_NO_INPUT",
    default=False,
    help="Never prompt; fail fast instead of waiting for confirmation.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print git and gh commands as they run.",
)
@click.pass_context
def cli(ctx, no_color, no_input, verbose):
    """arc — stacked pull request manager."""
    ctx.ensure_object(dict)
    ctx.obj["no_input"] = no_input
    ctx.obj["verbose"] = verbose
    if verbose:
        from arc import git as _git
        from arc import github as _gh

        _git._VERBOSE = True
        _gh._VERBOSE = True
    if no_color:
        import os

        os.environ["NO_COLOR"] = "1"


for _cmd in ALL_COMMANDS:
    cli.add_command(_cmd)
