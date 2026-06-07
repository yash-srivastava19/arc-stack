from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static
from textual.worker import Worker, WorkerState

from arc import github
from arc import state as st


@dataclass
class BranchStatus:
    """Status of a single branch in the stack."""

    name: str
    pr_number: int | None
    ci_passing: bool | None  # None = pending/unknown
    approved: bool
    draft: bool
    commits: int
    revision: int
    blocker_reason: str | None  # e.g., "waiting on feat/auth to land"

    @property
    def status_icon(self) -> str:
        """Return icon for branch status."""
        if self.pr_number is None:
            return "○"  # no PR
        if self.ci_passing is False:
            return "✗"  # failing (takes priority over blocked)
        if self.blocker_reason:
            return "⏳"  # blocked/waiting
        if self.ci_passing is None:
            return "⚙️"  # running/pending
        if self.approved:
            return "✅"  # ready to land
        return "○"  # not ready


@dataclass
class StackView:
    """Model for the entire stack view."""

    base: str  # "main"
    branches: list[BranchStatus]
    current_index: int = 0  # selected branch

    @property
    def current_branch(self) -> BranchStatus | None:
        """Get currently selected branch."""
        if 0 <= self.current_index < len(self.branches):
            return self.branches[self.current_index]
        return None

    def move_selection(self, delta: int) -> None:
        """Move selection up (-1) or down (+1)."""
        new_index = self.current_index + delta
        if 0 <= new_index < len(self.branches):
            self.current_index = new_index


def load_stack_view(root: Path) -> StackView:
    """Load stack state and GitHub PR status into a StackView model.

    Reads .arc/state.json and fetches PR status for each branch.
    """
    data = st.load(root)
    branches = []

    for branch_dict in data.get("branches", []):
        name = branch_dict["name"]
        pr_number = branch_dict.get("pr_number")

        # Fetch GitHub status if PR exists
        blocker_reason = None
        ci_passing = None
        approved = False
        draft = False
        if pr_number:
            pr_status = github.get_pr_status(pr_number)
            ci_passing = pr_status.get("ci_passing")
            approved = pr_status.get("approved", False)
            draft = pr_status.get("draft", False)

            # Compute blocker reason: CI failure takes priority
            if ci_passing is False:
                blocker_reason = "CI is failing"
            elif not approved and not draft:
                blocker_reason = "not yet approved"
        else:
            draft = True  # no PR = draft

        branch = BranchStatus(
            name=name,
            pr_number=pr_number,
            ci_passing=ci_passing,
            approved=approved,
            draft=draft,
            commits=branch_dict.get("commits", 0),
            revision=branch_dict.get("revision", 0),
            blocker_reason=blocker_reason,
        )
        branches.append(branch)

    return StackView(base=data.get("base", "main"), branches=branches)


class StackTreeWidget(Static):
    """Left panel: Stack tree with status icons."""

    def __init__(self, stack_view: StackView, id: str | None = None):
        super().__init__(id=id)
        self.stack_view = stack_view

    def render(self) -> str:
        if not self.stack_view.branches:
            return "No branches in stack"

        lines = ["[bold cyan]STACK[/bold cyan]"]
        for i, branch in enumerate(self.stack_view.branches):
            icon = branch.status_icon
            name = branch.name
            is_selected = "▶ " if i == self.stack_view.current_index else "  "
            lines.append(f"{is_selected}{icon} {name}")

        return "\n".join(lines)


class BranchDetailsWidget(Static):
    """Center panel: Full details for selected branch."""

    def __init__(self, stack_view: StackView, id: str | None = None):
        super().__init__(id=id)
        self.stack_view = stack_view

    def render(self) -> str:
        current = self.stack_view.current_branch
        if not current:
            return "No branch selected"

        lines = [f"[bold yellow]{current.name}[/bold yellow]"]
        if current.pr_number:
            lines.append(f"PR #{current.pr_number}")
        lines.append(f"{current.commits} commits · revision {current.revision}")
        # TODO(v0.5): show latest commit message here; state.json doesn't store it yet

        if current.ci_passing is True:
            lines.append("[green]✓ CI passing[/green]")
        elif current.ci_passing is False:
            lines.append("[red]✗ CI failing[/red]")
        elif current.ci_passing is None:
            lines.append("[yellow]⚙ CI running[/yellow]")

        if current.approved:
            lines.append("[green]✓ Approved[/green]")
        else:
            lines.append("[yellow]○ Awaiting approval[/yellow]")

        if current.blocker_reason:
            lines.append(f"[red]⏳ Blocked: {current.blocker_reason}[/red]")

        if current.pr_number:
            lines.append("[blue]→ Press 'o' to open PR[/blue]")

        return "\n".join(lines)


class ActionsWidget(Static):
    """Right panel: Keyboard shortcuts and status."""

    def __init__(self, stack_view: StackView, id: str | None = None):
        super().__init__(id=id)
        self.stack_view = stack_view

    def render(self) -> str:
        return (
            "[bold cyan]ACTIONS[/bold cyan]\n\n"
            "[yellow]s[/yellow] sync\n"
            "[yellow]p[/yellow] push\n"
            "[yellow]l[/yellow] land\n"
            "[yellow]r[/yellow] restack\n"
            "[yellow]o[/yellow] open PR\n"
            "[yellow]R[/yellow] refresh\n"
            "[yellow]q[/yellow] quit\n\n"
            "[green]● live[/green]"
        )


class DashboardApp(App):
    """Main Textual application for arc dashboard."""

    BINDINGS = [
        Binding("up", "move_up", "Up"),
        Binding("down", "move_down", "Down"),
        Binding("s", "sync", "Sync"),
        Binding("p", "push", "Push"),
        Binding("l", "land", "Land"),
        Binding("r", "restack", "Restack"),
        Binding("o", "open_pr", "Open PR"),
        Binding("shift+r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    TITLE = "arc dashboard"

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.stack_view: StackView | None = None
        self.status_message = ""

    def compose(self) -> ComposeResult:
        """Create three-panel layout."""
        empty = StackView(base="main", branches=[])
        yield Horizontal(
            StackTreeWidget(self.stack_view or empty, id="panel_tree"),
            BranchDetailsWidget(self.stack_view or empty, id="panel_details"),
            ActionsWidget(self.stack_view or empty, id="panel_actions"),
            id="main_container",
        )
        yield Static(self.status_message, id="footer")

    def on_mount(self) -> None:
        """Initialize and load stack state."""
        self._load_state_async()
        self.start_polling()

    def load_state(self) -> None:
        """Load current stack state from disk (synchronous, for backward compat)."""
        try:
            self.stack_view = load_stack_view(self.root)
            self.refresh_panels()
        except Exception as e:
            self.status_message = f"Error loading state: {e}"

    @work(thread=True, exit_on_error=False, exclusive=True)
    def _load_state_worker(self) -> StackView | None:
        """Load state in worker thread (may take time for GitHub API)."""
        try:
            return load_stack_view(self.root)
        except Exception:
            return None

    def _on_load_complete(self, stack: StackView | None) -> None:
        """Callback when load finishes (runs on main thread)."""
        if stack:
            self.stack_view = stack
        else:
            self.status_message = "Error loading stack — check git repo and .arc/state.json"
            self.set_timer(3.0, self._clear_status_message)
        self.refresh_panels()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes to collect _load_state_worker results."""
        if event.worker.name == "_load_state_worker" and event.state == WorkerState.SUCCESS:
            self._on_load_complete(event.worker.result)

    def _load_state_async(self) -> None:
        """Non-blocking load: dispatches to worker thread, updates UI via callback."""
        self._load_state_worker()

    @work(exclusive=True)
    async def start_polling(self) -> None:
        """Background polling every 10 seconds."""
        while True:
            await asyncio.sleep(10)
            self._load_state_async()

    def action_move_up(self) -> None:
        """Move selection up."""
        if self.stack_view:
            self.stack_view.move_selection(-1)
            self.refresh_panels()

    def action_move_down(self) -> None:
        """Move selection down."""
        if self.stack_view:
            self.stack_view.move_selection(1)
            self.refresh_panels()

    def action_sync(self) -> None:
        """Run arc sync on current branch."""
        self.run_arc_command("sync")

    def action_push(self) -> None:
        """Run arc push on current branch."""
        self.run_arc_command("push")

    def action_land(self) -> None:
        """Run arc land on current branch."""
        self.run_arc_command("land")

    def action_restack(self) -> None:
        """Run arc restack on current branch."""
        self.run_arc_command("restack")

    def action_open_pr(self) -> None:
        """Open PR in browser (non-blocking)."""
        if not self.stack_view or not self.stack_view.current_branch:
            self.status_message = "No branch selected"
            return

        current = self.stack_view.current_branch
        if current.pr_number:
            self._open_pr_worker(current.pr_number)
            self.status_message = f"Opening PR #{current.pr_number}..."
        else:
            self.status_message = "No PR for this branch — run 'arc push' first"
            self.set_timer(3.0, self._clear_status_message)
        self.refresh_panels()

    @work(thread=True)
    def _open_pr_worker(self, pr_number: int) -> None:
        """Open PR in browser (worker thread)."""
        try:
            subprocess.run(["gh", "pr", "view", str(pr_number), "--web"], cwd=self.root, timeout=5)
        except Exception:
            pass  # User error or gh not installed — ignore silently

    def _clear_status_message(self) -> None:
        """Clear status message after timer fires."""
        self.status_message = ""
        self.refresh_panels()

    def action_refresh(self) -> None:
        """Force refresh now."""
        self.status_message = "Refreshing..."
        self.refresh_panels()
        self._load_state_async()
        self.set_timer(2.0, self._clear_status_message)

    async def action_quit(self) -> None:
        """Quit dashboard."""
        self.exit()

    def run_arc_command(self, cmd: str) -> None:
        """Run arc command on current branch (non-blocking)."""
        if not self.stack_view or not self.stack_view.current_branch:
            self.status_message = "No branch selected"
            self.refresh_panels()
            return

        branch = self.stack_view.current_branch.name
        self.status_message = f"Running arc {cmd}..."
        self.refresh_panels()
        self._run_arc_command_worker(cmd, branch)

    @work(thread=True, exit_on_error=False)
    def _run_arc_command_worker(self, cmd: str, branch: str) -> None:
        """Worker thread: run arc command without blocking the event loop."""
        try:
            if cmd in ("land", "restack"):
                args = ["arc", cmd, branch]
            else:  # sync, push — operate on current branch; no branch arg
                args = ["arc", cmd]
            result = subprocess.run(
                args,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                self.call_from_thread(self._on_command_success, cmd)
            else:
                error = result.stderr[:100] if result.stderr else "unknown error"
                self.call_from_thread(self._on_command_failure, cmd, error)
        except Exception as e:
            self.call_from_thread(self._on_command_failure, cmd, str(e)[:80])

    def _on_command_success(self, cmd: str) -> None:
        """Handle successful arc command (called on main thread)."""
        self.status_message = f"✓ {cmd.capitalize()} succeeded"
        self._load_state_async()

    def _on_command_failure(self, cmd: str, error: str) -> None:
        """Handle failed arc command (called on main thread)."""
        self.status_message = f"✗ {cmd.capitalize()} failed: {error}"
        self.refresh_panels()

    def refresh_panels(self) -> None:
        """Refresh all panel widgets by updating their data and repainting."""
        try:
            empty = StackView(base="main", branches=[])
            current_view = self.stack_view or empty

            tree_widget = self.query_one("#panel_tree", StackTreeWidget)
            tree_widget.stack_view = current_view
            tree_widget.refresh()

            details_widget = self.query_one("#panel_details", BranchDetailsWidget)
            details_widget.stack_view = current_view
            details_widget.refresh()

            actions_widget = self.query_one("#panel_actions", ActionsWidget)
            actions_widget.stack_view = current_view
            actions_widget.refresh()

            self.query_one("#footer", Static).update(self.status_message)
        except Exception:
            pass  # widget tree may not be ready yet


def run_dashboard(root: Path) -> None:
    """Entry point: run the dashboard."""
    app = DashboardApp(root)
    app.run()
