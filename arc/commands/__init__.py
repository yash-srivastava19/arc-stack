"""arc CLI commands, grouped by responsibility.

Modules define plain click commands; arc.cli registers them via ALL_COMMANDS.
Rule: command modules import sibling helpers as `from arc.commands import _shared`
and call `_shared.helper()` — never `from ._shared import helper` — so tests can
patch one canonical target (arc.commands._shared.*).
Exception: the err/out Console singletons may be imported directly; they are shared instances.
"""

from arc.commands.config import config_group, schema_cmd
from arc.commands.diagnostics import (
    completions_cmd,
    dashboard_cmd,
    doctor_cmd,
    report_cmd,
    setup,
    upgrade_cmd,
)
from arc.commands.nav import bottom_cmd, checkout_cmd, down_cmd, top_cmd, up_cmd
from arc.commands.stack import (
    add_cmd,
    amend_cmd,
    drop_cmd,
    init_cmd,
    new_cmd,
    stack_group,
    status_cmd,
)
from arc.commands.submit import land_cmd, submit_cmd
from arc.commands.sync import push_cmd, rebase_cmd, restack_cmd, sync_cmd

ALL_COMMANDS: list = [
    setup,
    doctor_cmd,
    completions_cmd,
    upgrade_cmd,
    report_cmd,
    dashboard_cmd,
    checkout_cmd,
    up_cmd,
    down_cmd,
    top_cmd,
    bottom_cmd,
    config_group,
    schema_cmd,
    init_cmd,
    new_cmd,
    add_cmd,
    status_cmd,
    amend_cmd,
    drop_cmd,
    stack_group,
    submit_cmd,
    land_cmd,
    sync_cmd,
    push_cmd,
    restack_cmd,
    rebase_cmd,
]
