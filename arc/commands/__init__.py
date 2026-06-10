"""arc CLI commands, grouped by responsibility.

Modules define plain click commands; arc.cli registers them via ALL_COMMANDS.
Rule: command modules import sibling helpers as `from arc.commands import _shared`
and call `_shared.helper()` — never `from ._shared import helper` — so tests can
patch one canonical target (arc.commands._shared.*).
Exception: the err/out Console singletons may be imported directly; they are shared instances.
"""

ALL_COMMANDS: list = []
