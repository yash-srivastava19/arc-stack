from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from arc import state as st
from arc import github


@dataclass
class BranchStatus:
    """Status of a single branch in the stack."""
    name: str
    pr_number: Optional[int]
    ci_passing: Optional[bool]  # None = pending/unknown
    approved: bool
    draft: bool
    commits: int
    revision: int
    blocker_reason: Optional[str]  # e.g., "waiting on feat/auth to land"

    @property
    def status_icon(self) -> str:
        """Return icon for branch status."""
        if self.blocker_reason:
            return "⏳"  # blocked/waiting
        if self.ci_passing is False:
            return "✗"  # failing
        if self.ci_passing is None:
            return "⚙️"  # running/pending
        if self.approved:
            return "✅"  # ready to land
        return "○"  # no PR or not ready


@dataclass
class StackView:
    """Model for the entire stack view."""
    base: str  # "main"
    branches: list[BranchStatus]
    current_index: int = 0  # selected branch

    @property
    def current_branch(self) -> Optional[BranchStatus]:
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


from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Static
from textual.binding import Binding
from textual import work
import asyncio
import subprocess


class StackTreeWidget(Static):
    """Left panel: Stack tree with status icons."""

    def __init__(self, stack_view: StackView):
        super().__init__()
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

    def __init__(self, stack_view: StackView):
        super().__init__()
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

    def __init__(self, stack_view: StackView):
        super().__init__()
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
        self.stack_view: Optional[StackView] = None
        self.status_message = ""

    def compose(self) -> ComposeResult:
        """Create three-panel layout."""
        yield Horizontal(
            StackTreeWidget(self.stack_view or StackView(base="main", branches=[])),
            BranchDetailsWidget(self.stack_view or StackView(base="main", branches=[])),
            ActionsWidget(self.stack_view or StackView(base="main", branches=[])),
            id="main_container",
        )
        yield Static(self.status_message, id="footer")

    def on_mount(self) -> None:
        """Initialize and load stack state."""
        self.load_state()
        self.start_polling()

    def load_state(self) -> None:
        """Load current stack state from disk."""
        try:
            self.stack_view = load_stack_view(self.root)
            self.refresh_panels()
        except Exception as e:
            self.status_message = f"Error loading state: {e}"

    @work(exclusive=True)
    async def start_polling(self) -> None:
        """Background polling every 10 seconds."""
        while True:
            await asyncio.sleep(10)
            self.load_state()

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
        """Open current branch's PR in browser."""
        if self.stack_view and self.stack_view.current_branch:
            current = self.stack_view.current_branch
            if current.pr_number:
                try:
                    subprocess.run(["gh", "pr", "view", str(current.pr_number), "--web"], cwd=self.root)
                    self.status_message = f"Opened PR #{current.pr_number} in browser"
                except Exception:
                    self.status_message = "Cannot open PR (gh CLI not found)"
                self.set_timer(3.0, self._clear_status_message)
                self.set_timer(3.0, self._clear_status_message)
        self.refresh_panels()

    def _clear_status_message(self) -> None:
        """Clear status message after timer fires."""
        self.status_message = ""
        self.refresh_panels()

    def action_refresh(self) -> None:
        """Force refresh now."""
        self.load_state()
        self.status_message = "Refreshed"

    def action_quit(self) -> None:
        """Quit dashboard."""
        self.exit()

    def run_arc_command(self, cmd: str) -> None:
        """Run arc command on current branch."""
        if not self.stack_view or not self.stack_view.current_branch:
            self.status_message = "No branch selected"
            return

        branch = self.stack_view.current_branch.name
        self.status_message = f"Running arc {cmd}..."
        self.refresh_panels()

        try:
            result = subprocess.run(
                ["arc", cmd, branch],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                self.status_message = f"✓ {cmd.capitalize()} succeeded"
                self.load_state()
            else:
                error = result.stderr[:100] if result.stderr else "unknown error"
                self.status_message = f"✗ {cmd.capitalize()} failed: {error}"
        except Exception as e:
            self.status_message = f"✗ Error: {str(e)[:80]}"

        self.refresh_panels()

    def refresh_panels(self) -> None:
        """Refresh all panel widgets."""
        try:
            container = self.query_one("#main_container", Horizontal)
            container.remove_children()
            container.mount(
                StackTreeWidget(self.stack_view or StackView(base="main", branches=[])),
                BranchDetailsWidget(self.stack_view or StackView(base="main", branches=[])),
                ActionsWidget(self.stack_view or StackView(base="main", branches=[])),
            )
            self.query_one("#footer", Static).update(self.status_message)
        except Exception:
            pass  # widget tree may not be ready yet


def run_dashboard(root: Path) -> None:
    """Entry point: run the dashboard."""
    app = DashboardApp(root)
    app.run()
