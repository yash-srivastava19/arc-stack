from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Input, RichLog, Static
from textual.worker import Worker, WorkerState

from arc import git, github
from arc import state as st
from arc.exceptions import NotInitializedError

# ── Palette (green-terminal aesthetic) ──────────────────────────────────────

_BG = "#0c0e0b"
_FG = "#c9d1b8"
_DIM = "#5f6b52"
_MUTED = "#7c8a68"
_BRIGHT = "#e7ecd8"
_GREEN = "#8fb573"
_RED = "#e0796f"
_YELLOW = "#e0a93b"
_BLUE = "#7aa8d8"
_BORDER = "#1e211a"
_SEL_BG = "#14170f"
_TRACK = "#2a2e26"


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class BranchStatus:
    """Status of a single branch in the stack."""

    name: str
    pr_number: int | None
    pr_url: str | None
    ci_passing: bool | None  # None = pending/unknown
    approved: bool
    draft: bool
    commits: int
    revision: int
    blocker_reason: str | None
    base: str  # parent branch name

    @property
    def status_icon(self) -> str:
        if self.pr_number is None:
            return "○"
        if self.ci_passing is False:
            return "✗"
        if self.approved:
            return "✓"
        if self.ci_passing is None:
            return "⚙"
        return "○"

    @property
    def status_color(self) -> str:
        if self.pr_number is None:
            return _DIM
        if self.ci_passing is False:
            return _RED
        if self.approved:
            return _GREEN
        if self.ci_passing is None:
            return _YELLOW
        return _FG

    @property
    def row_accent(self) -> str:
        """Left-border color for the branch row."""
        if self.ci_passing is False:
            return _RED
        if self.approved:
            return _GREEN
        if self.pr_number and self.ci_passing is None:
            return _YELLOW
        if self.pr_number:
            return _BLUE
        return _BORDER


@dataclass
class StackView:
    """Model for the entire stack view."""

    base: str
    branches: list[BranchStatus]
    current_git_branch: str = ""
    current_index: int = 0
    error: str = ""

    @property
    def current_branch(self) -> BranchStatus | None:
        if 0 <= self.current_index < len(self.branches):
            return self.branches[self.current_index]
        return None

    def move_selection(self, delta: int) -> None:
        new_index = self.current_index + delta
        if 0 <= new_index < len(self.branches):
            self.current_index = new_index

    def index_of(self, branch_name: str) -> int | None:
        for i, b in enumerate(self.branches):
            if b.name == branch_name:
                return i
        return None


# ── State loader ─────────────────────────────────────────────────────────────


def load_stack_view(root: Path) -> StackView:
    """Load stack state and GitHub PR status into a StackView.

    Reads .arc/state.json, counts commits per branch via git, and fetches
    PR status from GitHub for branches that have a PR.
    """
    try:
        current_git_branch = git.current_branch()
    except Exception:
        current_git_branch = ""

    data = st.load(root)
    branch_list = data.get("branches", [])
    base = data.get("base", "main")
    branches: list[BranchStatus] = []

    for i, branch_dict in enumerate(branch_list):
        name = branch_dict["name"]
        pr_number = branch_dict.get("pr_number")
        parent = branch_list[i - 1]["name"] if i > 0 else base

        try:
            commits = git.commit_count(parent, name)
        except Exception:
            commits = 0

        blocker_reason = None
        ci_passing = None
        approved = False
        is_draft = False
        pr_url = None

        if pr_number:
            pr_status = github.get_pr_status(pr_number)
            ci_passing = pr_status.get("ci_passing")
            approved = pr_status.get("approved", False)
            is_draft = pr_status.get("draft", False)
            pr_url = pr_status.get("url")

            if ci_passing is False:
                blocker_reason = "CI failing"
            elif is_draft:
                blocker_reason = "draft"
            elif not approved:
                blocker_reason = "awaiting review"
        else:
            is_draft = True

        branches.append(
            BranchStatus(
                name=name,
                pr_number=pr_number,
                pr_url=pr_url,
                ci_passing=ci_passing,
                approved=approved,
                draft=is_draft,
                commits=commits,
                revision=branch_dict.get("revision", 0),
                blocker_reason=blocker_reason,
                base=parent,
            )
        )

    stack = StackView(base=base, branches=branches, current_git_branch=current_git_branch)
    idx = stack.index_of(current_git_branch)
    if idx is not None:
        stack.current_index = idx

    return stack


# ── Widgets ──────────────────────────────────────────────────────────────────


class TitleBarWidget(Static):
    """Single-line title bar: repo info on left, clock on right."""

    def __init__(self, base: str = "…", current_branch: str = "", **kwargs):
        super().__init__(**kwargs)
        self.base = base
        self.current_branch = current_branch
        self._clock = ""

    def on_mount(self) -> None:
        self.set_interval(1, self._tick)
        self._tick()

    def _tick(self) -> None:
        self._clock = datetime.now().strftime("%H:%M:%S")
        self.refresh()

    def render(self) -> str:
        branch_info = f" · on {self.current_branch}" if self.current_branch else ""
        left = f"[{_GREEN}]arc[/{_GREEN}] [{_DIM}]— {self.base}{branch_info}[/{_DIM}]"
        right = f"[{_DIM}]{self._clock}[/{_DIM}]"
        return f"{left}  {right}"


class SummaryWidget(Static):
    """Stack summary: $ arc status + branch/PR counts."""

    def __init__(self, stack_view: StackView, loading: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view
        self.loading = loading

    def render(self) -> str:
        if self.loading:
            return f"[{_MUTED}]$ arc status[/{_MUTED}]\n[{_DIM}]loading…[/{_DIM}]"

        if self.stack_view.error:
            return f"[{_MUTED}]$ arc status[/{_MUTED}]\n[{_RED}]{self.stack_view.error}[/{_RED}]"

        n = len(self.stack_view.branches)
        prs = sum(1 for b in self.stack_view.branches if b.pr_number)
        approved = sum(1 for b in self.stack_view.branches if b.approved)

        parts = [
            f"[{_BRIGHT}]{self.stack_view.base}[/{_BRIGHT}]",
            f"[{_DIM}]{n} branch{'es' if n != 1 else ''}[/{_DIM}]",
        ]
        if prs:
            parts.append(f"[{_BLUE}]{prs} PR{'s' if prs != 1 else ''}[/{_BLUE}]")
        if approved:
            parts.append(f"[{_GREEN}]{approved} approved[/{_GREEN}]")
        if not self.stack_view.branches:
            parts.append(f"[{_DIM}]run arc new <branch> to add branches[/{_DIM}]")

        header = f"[{_MUTED}]$ arc status[/{_MUTED}]"
        summary = "  ".join(parts)
        return f"{header}\n{summary}"


class ActionsBarWidget(Static):
    """Keyboard shortcuts bar."""

    def render(self) -> str:
        def key(k: str, label: str) -> str:
            return f"[{_GREEN}][{k}][/{_GREEN}][{_MUTED}] {label}[/{_MUTED}]"

        keys = "  ".join(
            [
                key("s", "sync"),
                key("p", "push"),
                key("l", "land"),
                key("r", "restack"),
                key("o", "open PR"),
                key("R", "refresh"),
                key("q", "quit"),
            ]
        )
        return keys


class BranchTreeWidget(Static):
    """Stack tree: one row per branch with left-accent border and status info."""

    def __init__(self, stack_view: StackView, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view

    def render(self) -> str:
        if not self.stack_view.branches:
            return f"[{_DIM}]stack is empty[/{_DIM}]"

        base = self.stack_view.base
        n = len(self.stack_view.branches)
        lines = [f"[bold {_DIM}]{base}[/bold {_DIM}]"]

        for i, branch in enumerate(self.stack_view.branches):
            is_selected = i == self.stack_view.current_index
            is_head = branch.name == self.stack_view.current_git_branch

            connector = "└─" if i == n - 1 else "├─"
            accent = branch.row_accent

            # left accent bar (simulated with colored pipe)
            bar = f"[{accent}]┃[/{accent}]"

            # cursor
            cursor = f"[bold {_GREEN}]▶[/bold {_GREEN}] " if is_selected else "  "

            # name
            name = (
                f"[bold {_BRIGHT}]{branch.name}[/bold {_BRIGHT}]"
                if is_head
                else f"[{_FG}]{branch.name}[/{_FG}]"
            )

            # PR label
            if branch.pr_number:
                pr_label = f"[{_BLUE}]#{branch.pr_number}[/{_BLUE}]"
            else:
                pr_label = f"[{_DIM}]--[/{_DIM}]"

            # CI icon
            icon = f"[{branch.status_color}]{branch.status_icon}[/{branch.status_color}]"

            # commits + rev
            meta = f"[{_DIM}]{branch.commits}c  (rev {branch.revision})[/{_DIM}]"

            # HEAD marker
            head_marker = f"  [{_BRIGHT}]◀ HEAD[/{_BRIGHT}]" if is_head else ""

            # blocker
            blocker = (
                f"  [{_YELLOW}]{branch.blocker_reason}[/{_YELLOW}]"
                if branch.blocker_reason and is_selected
                else ""
            )

            lines.append(
                f"{cursor}[{_DIM}]{connector}[/{_DIM}] {bar} {name}  {pr_label}  {icon}  {meta}{head_marker}{blocker}"
            )

        # warn if current branch is not in the stack
        cgb = self.stack_view.current_git_branch
        if cgb and self.stack_view.index_of(cgb) is None and cgb != base:
            lines.append(
                f"\n[{_YELLOW}]⚠ current branch [{_BRIGHT}]{cgb}[/{_BRIGHT}] not in stack[/{_YELLOW}]"
                f"\n[{_DIM}]→ run arc add {cgb}[/{_DIM}]"
            )

        return "\n".join(lines)


class DetailWidget(Static):
    """Inline detail panel for the selected branch (like `arc show`)."""

    def __init__(self, stack_view: StackView, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view

    def render(self) -> str:
        current = self.stack_view.current_branch
        if not current:
            return ""

        lines: list[str] = []
        lines.append(f"[{_MUTED}]$ arc show {current.name}[/{_MUTED}]")
        lines.append(f"[{_DIM}]branch [/{_DIM}][{_BRIGHT}]{current.name}[/{_BRIGHT}]")
        lines.append(f"[{_DIM}]base   [/{_DIM}][{_FG}]{current.base}[/{_FG}]")
        commit_word = "commit" if current.commits == 1 else "commits"
        lines.append(
            f"[{_DIM}]commits[/{_DIM}] [{_FG}]{current.commits} {commit_word}[/{_FG}]  [{_DIM}]rev {current.revision}[/{_DIM}]"
        )

        if current.pr_number:
            pr_str = f"[{_BLUE}]#{current.pr_number}[/{_BLUE}]"
            if current.pr_url:
                pr_str += f"  [{_DIM}]{current.pr_url}[/{_DIM}]"
            lines.append(f"[{_DIM}]pr     [/{_DIM}]{pr_str}")

            if current.ci_passing is True:
                ci_str = f"[{_GREEN}]✓ passing[/{_GREEN}]"
            elif current.ci_passing is False:
                ci_str = f"[{_RED}]✗ failing[/{_RED}]"
            else:
                ci_str = f"[{_YELLOW}]⚙ running[/{_YELLOW}]"
            lines.append(f"[{_DIM}]checks [/{_DIM}]{ci_str}")

            if current.approved:
                review = f"[{_GREEN}]✓ approved[/{_GREEN}]"
            elif current.draft:
                review = f"[{_DIM}]draft[/{_DIM}]"
            else:
                review = f"[{_YELLOW}]○ awaiting review[/{_YELLOW}]"
            lines.append(f"[{_DIM}]review [/{_DIM}]{review}")
        else:
            lines.append(
                f"[{_DIM}]pr     [/{_DIM}][{_DIM}]none — run arc push && arc submit[/{_DIM}]"
            )

        return "\n".join(lines)


# ── App ───────────────────────────────────────────────────────────────────────


class DashboardApp(App):
    """Interactive dashboard for arc stacked PRs."""

    CSS = f"""
Screen {{
    background: {_BG};
    color: {_FG};
}}

#title_bar {{
    height: 1;
    background: {_BG};
    color: {_DIM};
    padding: 0 1;
    border-bottom: tall {_BORDER};
}}

#scroll_area {{
    height: 1fr;
    background: {_BG};
    scrollbar-color: {_TRACK} {_BG};
    scrollbar-size: 1 1;
    padding: 1 2;
}}

SummaryWidget {{
    margin-bottom: 1;
    padding: 0;
}}

#actions_bar {{
    height: 1;
    margin-bottom: 1;
    color: {_MUTED};
    padding: 0;
}}

#branch_tree {{
    padding: 0;
    margin-bottom: 1;
}}

#detail {{
    padding: 1;
    margin-bottom: 1;
    border: tall {_BORDER};
}}

#detail.hidden {{
    display: none;
}}

#cmd_input {{
    height: 3;
    background: {_BG};
    border: tall {_BORDER};
    color: {_BRIGHT};
    padding: 0 1;
}}

#cmd_input:focus {{
    border: tall {_GREEN};
}}

#output_log {{
    height: 8;
    background: {_BG};
    border: tall {_BORDER};
    scrollbar-color: {_TRACK} {_BG};
    scrollbar-size: 1 1;
    padding: 0 1;
}}
"""

    BINDINGS = [
        Binding("up,k", "move_up", "Up", show=False),
        Binding("down,j", "move_down", "Down", show=False),
        Binding("enter", "toggle_detail", "Detail", show=False),
        Binding("s", "cmd_sync", "sync", show=False),
        Binding("p", "cmd_push", "push", show=False),
        Binding("l", "cmd_land", "land", show=False),
        Binding("r", "cmd_restack", "restack", show=False),
        Binding("o", "open_pr", "open PR", show=False),
        Binding("R", "refresh", "refresh", show=False),
        Binding("q", "quit", "quit", show=False),
    ]

    TITLE = "arc dashboard"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.stack_view: StackView | None = None
        self._loading = True
        self._detail_open = False

    def compose(self) -> ComposeResult:
        empty = StackView(base="…", branches=[])
        yield TitleBarWidget(id="title_bar")
        with ScrollableContainer(id="scroll_area"):
            with Vertical():
                yield SummaryWidget(empty, loading=True, id="summary")
                yield ActionsBarWidget(id="actions_bar")
                yield BranchTreeWidget(empty, id="branch_tree")
                yield DetailWidget(empty, id="detail", classes="hidden")
        yield Input(placeholder="arc› ", id="cmd_input")
        yield RichLog(id="output_log", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._load_state_async()
        self.start_polling()
        self._emit(f"[{_MUTED}]arc dashboard — use ↑↓ to navigate, enter to expand[/{_MUTED}]")

    @work(thread=True, exit_on_error=False, exclusive=True)
    def _load_state_worker(self) -> StackView | None:
        try:
            return load_stack_view(self.root)
        except NotInitializedError:
            v = StackView(base="main", branches=[])
            v.error = "not initialized — run arc init"
            return v
        except Exception as e:
            v = StackView(base="main", branches=[])
            v.error = str(e)
            return v

    def _on_load_complete(self, stack: StackView | None) -> None:
        self._loading = False
        if stack is not None:
            self.stack_view = stack
        self._refresh_all()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name == "_load_state_worker" and event.state == WorkerState.SUCCESS:
            self._on_load_complete(event.worker.result)

    def _load_state_async(self) -> None:
        self._loading = True
        self._load_state_worker()

    @work(exclusive=True)
    async def start_polling(self) -> None:
        while True:
            await asyncio.sleep(30)
            self._load_state_async()

    # ── Navigation ─────────────────────────────────────────────────────────

    def action_move_up(self) -> None:
        if self.stack_view:
            self.stack_view.move_selection(-1)
            if self._detail_open:
                self._refresh_detail()
            self._refresh_tree()

    def action_move_down(self) -> None:
        if self.stack_view:
            self.stack_view.move_selection(1)
            if self._detail_open:
                self._refresh_detail()
            self._refresh_tree()

    def action_toggle_detail(self) -> None:
        self._detail_open = not self._detail_open
        detail = self.query_one("#detail", DetailWidget)
        if self._detail_open:
            detail.remove_class("hidden")
        else:
            detail.add_class("hidden")
        self._refresh_detail()

    # ── Arc commands ────────────────────────────────────────────────────────

    def action_cmd_sync(self) -> None:
        self._run_arc("sync")

    def action_cmd_push(self) -> None:
        self._run_arc("push")

    def action_cmd_land(self) -> None:
        if self.stack_view and self.stack_view.current_branch:
            self._run_arc("land", self.stack_view.current_branch.name)
        else:
            self._emit(f"[{_RED}]no branch selected[/{_RED}]")

    def action_cmd_restack(self) -> None:
        if self.stack_view and self.stack_view.current_branch:
            self._run_arc("restack", self.stack_view.current_branch.name)
        else:
            self._emit(f"[{_RED}]no branch selected[/{_RED}]")

    def action_open_pr(self) -> None:
        if not self.stack_view or not self.stack_view.current_branch:
            self._emit(f"[{_YELLOW}]no branch selected[/{_YELLOW}]")
            return
        current = self.stack_view.current_branch
        if current.pr_url:
            self._open_url_worker(current.pr_url)
            self._emit(f"[{_MUTED}]opening PR #{current.pr_number}…[/{_MUTED}]")
        elif current.pr_number:
            self._open_pr_worker(current.pr_number)
            self._emit(f"[{_MUTED}]opening PR #{current.pr_number}…[/{_MUTED}]")
        else:
            self._emit(f"[{_YELLOW}]no PR yet — run arc push && arc submit[/{_YELLOW}]")

    def action_refresh(self) -> None:
        self._emit(f"[{_MUTED}]refreshing…[/{_MUTED}]")
        self._load_state_async()

    async def action_quit(self) -> None:
        self.exit()

    # ── Input command handling ───────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.clear()
        if not cmd:
            return
        self._emit(f"[{_MUTED}]arc› {cmd}[/{_MUTED}]")
        parts = cmd.split()
        verb = parts[0] if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if verb in ("sync", "s"):
            self._run_arc("sync")
        elif verb in ("push", "p"):
            self._run_arc("push")
        elif verb in ("land", "l"):
            branch = arg or (
                self.stack_view.current_branch.name
                if self.stack_view and self.stack_view.current_branch
                else ""
            )
            if branch:
                self._run_arc("land", branch)
            else:
                self._emit(f"[{_YELLOW}]usage: land <branch>[/{_YELLOW}]")
        elif verb in ("restack", "r"):
            branch = arg or (
                self.stack_view.current_branch.name
                if self.stack_view and self.stack_view.current_branch
                else ""
            )
            if branch:
                self._run_arc("restack", branch)
            else:
                self._emit(f"[{_YELLOW}]usage: restack <branch>[/{_YELLOW}]")
        elif verb in ("refresh", "R"):
            self.action_refresh()
        elif verb in ("quit", "q"):
            self.exit()
        else:
            self._emit(
                f"[{_RED}]unknown: {cmd}[/{_RED}]  [{_DIM}]try: sync push land restack quit[/{_DIM}]"
            )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _run_arc(self, cmd: str, branch: str = "") -> None:
        self._emit(f"[{_MUTED}]$ arc {cmd}{' ' + branch if branch else ''}[/{_MUTED}]")
        self._run_arc_worker(cmd, branch)

    @work(thread=True, exit_on_error=False)
    def _run_arc_worker(self, cmd: str, branch: str) -> None:
        try:
            args = ["arc", cmd] + ([branch] if branch and cmd in ("land", "restack") else [])
            result = subprocess.run(
                args,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                out = (result.stdout or "").strip()
                self.call_from_thread(self._on_arc_success, cmd, out)
            else:
                err = (result.stderr or result.stdout or "unknown error").strip()[:200]
                self.call_from_thread(self._on_arc_failure, cmd, err)
        except Exception as e:
            self.call_from_thread(self._on_arc_failure, cmd, str(e)[:120])

    def _on_arc_success(self, cmd: str, output: str) -> None:
        self._emit(f"[{_GREEN}]✓ {cmd} succeeded[/{_GREEN}]")
        if output:
            for line in output.splitlines()[:8]:
                self._emit(f"[{_DIM}]  {line}[/{_DIM}]")
        self._load_state_async()

    def _on_arc_failure(self, cmd: str, error: str) -> None:
        self._emit(f"[{_RED}]✗ {cmd} failed[/{_RED}]")
        for line in error.splitlines()[:5]:
            self._emit(f"[{_RED}]  {line}[/{_RED}]")

    @work(thread=True)
    def _open_url_worker(self, url: str) -> None:
        try:
            subprocess.run(["xdg-open", url], timeout=5)
        except Exception:
            try:
                subprocess.run(["open", url], timeout=5)
            except Exception:
                pass

    @work(thread=True)
    def _open_pr_worker(self, pr_number: int) -> None:
        try:
            subprocess.run(["gh", "pr", "view", str(pr_number), "--web"], cwd=self.root, timeout=5)
        except Exception:
            pass

    def _emit(self, markup: str) -> None:
        try:
            self.query_one("#output_log", RichLog).write(markup)
        except Exception:
            pass

    def _refresh_tree(self) -> None:
        try:
            view = self.stack_view or StackView(base="main", branches=[])
            tree = self.query_one("#branch_tree", BranchTreeWidget)
            tree.stack_view = view
            tree.refresh()
        except Exception:
            pass

    def _refresh_detail(self) -> None:
        try:
            view = self.stack_view or StackView(base="main", branches=[])
            detail = self.query_one("#detail", DetailWidget)
            detail.stack_view = view
            detail.refresh()
        except Exception:
            pass

    def _refresh_all(self) -> None:
        try:
            view = self.stack_view or StackView(base="main", branches=[])

            title = self.query_one("#title_bar", TitleBarWidget)
            title.base = view.base
            title.current_branch = view.current_git_branch
            title.refresh()

            summary = self.query_one("#summary", SummaryWidget)
            summary.stack_view = view
            summary.loading = self._loading
            summary.refresh()

            tree = self.query_one("#branch_tree", BranchTreeWidget)
            tree.stack_view = view
            tree.refresh()

            detail = self.query_one("#detail", DetailWidget)
            detail.stack_view = view
            detail.refresh()
        except Exception:
            pass


def run_dashboard(root: Path) -> None:
    app = DashboardApp(root)
    app.run()
