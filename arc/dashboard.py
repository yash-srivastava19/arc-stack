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
from textual.worker import Worker

from arc import git, github
from arc import state as st
from arc.exceptions import NotInitializedError

# ── Theme ─────────────────────────────────────────────────────────────────────


@dataclass
class DashboardTheme:
    """Color palette for the dashboard.

    Select a theme with:  arc config set dashboard.theme <name>
    Available names: arc, dracula, nord, gruvbox, catppuccin, tokyo-night
    """

    name: str
    bg: str
    fg: str
    dim: str
    muted: str
    bright: str
    green: str
    red: str
    yellow: str
    blue: str
    border: str
    sel_bg: str
    track: str


THEMES: dict[str, DashboardTheme] = {
    "arc": DashboardTheme(
        name="arc",
        bg="#0c0e0b",
        fg="#c9d1b8",
        dim="#5f6b52",
        muted="#7c8a68",
        bright="#e7ecd8",
        green="#8fb573",
        red="#e0796f",
        yellow="#e0a93b",
        blue="#7aa8d8",
        border="#1e211a",
        sel_bg="#14170f",
        track="#2a2e26",
    ),
    "dracula": DashboardTheme(
        name="dracula",
        bg="#282a36",
        fg="#f8f8f2",
        dim="#6272a4",
        muted="#6272a4",
        bright="#ffffff",
        green="#50fa7b",
        red="#ff5555",
        yellow="#f1fa8c",
        blue="#8be9fd",
        border="#44475a",
        sel_bg="#44475a",
        track="#383a4a",
    ),
    "nord": DashboardTheme(
        name="nord",
        bg="#2e3440",
        fg="#d8dee9",
        dim="#4c566a",
        muted="#616e88",
        bright="#eceff4",
        green="#a3be8c",
        red="#bf616a",
        yellow="#ebcb8b",
        blue="#81a1c1",
        border="#3b4252",
        sel_bg="#3b4252",
        track="#434c5e",
    ),
    "gruvbox": DashboardTheme(
        name="gruvbox",
        bg="#282828",
        fg="#ebdbb2",
        dim="#665c54",
        muted="#7c6f64",
        bright="#fbf1c7",
        green="#b8bb26",
        red="#fb4934",
        yellow="#fabd2f",
        blue="#83a598",
        border="#3c3836",
        sel_bg="#3c3836",
        track="#504945",
    ),
    "catppuccin": DashboardTheme(
        name="catppuccin",
        bg="#1e1e2e",
        fg="#cdd6f4",
        dim="#585b70",
        muted="#6c7086",
        bright="#ffffff",
        green="#a6e3a1",
        red="#f38ba8",
        yellow="#f9e2af",
        blue="#89b4fa",
        border="#313244",
        sel_bg="#313244",
        track="#45475a",
    ),
    "tokyo-night": DashboardTheme(
        name="tokyo-night",
        bg="#1a1b26",
        fg="#a9b1d6",
        dim="#414868",
        muted="#565f89",
        bright="#c0caf5",
        green="#9ece6a",
        red="#f7768e",
        yellow="#e0af68",
        blue="#7aa2f7",
        border="#292e42",
        sel_bg="#292e42",
        track="#32344a",
    ),
}

DEFAULT_THEME = "arc"

# Active theme — set by DashboardApp.__init__ before compose() fires.
# All widget render() methods read from _T so they automatically pick up
# whatever theme was loaded for this session.
_T: DashboardTheme = THEMES[DEFAULT_THEME]


def load_theme(root: Path) -> DashboardTheme:
    """Load theme from arc config (dashboard.theme), falling back to 'arc'."""
    try:
        cfg = st.load_config(root)
        name = cfg.get("dashboard", {}).get("theme", DEFAULT_THEME)
        return THEMES.get(name, THEMES[DEFAULT_THEME])
    except Exception:
        return THEMES[DEFAULT_THEME]


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

    def status_color(self, t: DashboardTheme | None = None) -> str:
        theme = t or _T
        if self.pr_number is None:
            return theme.dim
        if self.ci_passing is False:
            return theme.red
        if self.approved:
            return theme.green
        if self.ci_passing is None:
            return theme.yellow
        return theme.fg

    def row_accent(self, t: DashboardTheme | None = None) -> str:
        theme = t or _T
        if self.ci_passing is False:
            return theme.red
        if self.approved:
            return theme.green
        if self.pr_number and self.ci_passing is None:
            return theme.yellow
        if self.pr_number:
            return theme.blue
        return theme.border


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


def load_local_stack_view(root: Path) -> StackView:
    """Load stack state from local sources only (no network).

    Reads .arc/state.json and git commit counts. Fast — called first so
    the UI can render the branch tree while PR status fetches in the background.
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

        branches.append(
            BranchStatus(
                name=name,
                pr_number=pr_number,
                pr_url=None,
                ci_passing=None,
                approved=False,
                draft=pr_number is None,
                commits=commits,
                revision=branch_dict.get("revision", 0),
                blocker_reason=None,
                base=parent,
            )
        )

    stack = StackView(base=base, branches=branches, current_git_branch=current_git_branch)
    idx = stack.index_of(current_git_branch)
    if idx is not None:
        stack.current_index = idx

    return stack


def _apply_pr_status(branch: BranchStatus, pr_status: dict) -> None:
    """Update a BranchStatus in-place with data from github.get_pr_status()."""
    branch.ci_passing = pr_status.get("ci_passing")
    branch.approved = pr_status.get("approved", False)
    branch.draft = pr_status.get("draft", False)
    branch.pr_url = pr_status.get("url")

    if branch.ci_passing is False:
        branch.blocker_reason = "CI failing"
    elif branch.draft:
        branch.blocker_reason = "draft"
    elif not branch.approved:
        branch.blocker_reason = "awaiting review"
    else:
        branch.blocker_reason = None


def load_stack_view(root: Path) -> StackView:
    """Load full stack view including GitHub PR status (blocking). Used in tests."""
    stack = load_local_stack_view(root)
    for branch in stack.branches:
        if branch.pr_number:
            try:
                pr_status = github.get_pr_status(branch.pr_number)
                _apply_pr_status(branch, pr_status)
            except Exception:
                pass
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
        t = _T
        branch_info = f" · on {self.current_branch}" if self.current_branch else ""
        left = f"[{t.green}]arc[/{t.green}] [{t.dim}]— {self.base}{branch_info}[/{t.dim}]"
        right = f"[{t.dim}]{self._clock}[/{t.dim}]"
        return f"{left}  {right}"


class SummaryWidget(Static):
    """Stack summary: $ arc status + branch/PR counts."""

    def __init__(self, stack_view: StackView, loading: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view
        self.loading = loading

    def render(self) -> str:
        t = _T
        if self.loading:
            return f"[{t.muted}]$ arc status[/{t.muted}]\n[{t.dim}]loading…[/{t.dim}]"

        if self.stack_view.error:
            return (
                f"[{t.muted}]$ arc status[/{t.muted}]\n[{t.red}]{self.stack_view.error}[/{t.red}]"
            )

        n = len(self.stack_view.branches)
        prs = sum(1 for b in self.stack_view.branches if b.pr_number)
        approved = sum(1 for b in self.stack_view.branches if b.approved)

        parts = [
            f"[{t.bright}]{self.stack_view.base}[/{t.bright}]",
            f"[{t.dim}]{n} branch{'es' if n != 1 else ''}[/{t.dim}]",
        ]
        if prs:
            parts.append(f"[{t.blue}]{prs} PR{'s' if prs != 1 else ''}[/{t.blue}]")
        if approved:
            parts.append(f"[{t.green}]{approved} approved[/{t.green}]")
        if not self.stack_view.branches:
            parts.append(f"[{t.dim}]run arc new <branch> to add branches[/{t.dim}]")

        header = f"[{t.muted}]$ arc status[/{t.muted}]"
        summary = "  ".join(parts)
        return f"{header}\n{summary}"


class ActionsBarWidget(Static):
    """Keyboard shortcuts bar."""

    def render(self) -> str:
        t = _T

        def key(k: str, label: str) -> str:
            # Use \[ to escape brackets so Rich doesn't interpret [s] as strikethrough etc.
            return f"[{t.green}]\\[{k}][/{t.green}][{t.muted}] {label}[/{t.muted}]"

        return "  ".join(
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


class BranchTreeWidget(Static):
    """Stack tree: one row per branch with left-accent border and status info."""

    def __init__(self, stack_view: StackView, loading: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view
        self.loading = loading

    def render(self) -> str:
        t = _T
        if self.loading:
            return f"[{t.dim}]loading…[/{t.dim}]"
        if not self.stack_view.branches:
            return f"[{t.dim}]stack is empty[/{t.dim}]"

        base = self.stack_view.base
        n = len(self.stack_view.branches)
        lines = [f"[bold {t.dim}]{base}[/bold {t.dim}]"]

        for i, branch in enumerate(self.stack_view.branches):
            is_selected = i == self.stack_view.current_index
            is_head = branch.name == self.stack_view.current_git_branch

            connector = "└─" if i == n - 1 else "├─"
            accent = branch.row_accent(t)
            sc = branch.status_color(t)

            bar = f"[{accent}]┃[/{accent}]"
            cursor = f"[bold {t.green}]▶[/bold {t.green}] " if is_selected else "  "
            name = (
                f"[bold {t.bright}]{branch.name}[/bold {t.bright}]"
                if is_head
                else f"[{t.fg}]{branch.name}[/{t.fg}]"
            )
            pr_label = (
                f"[{t.blue}]#{branch.pr_number}[/{t.blue}]"
                if branch.pr_number
                else f"[{t.dim}]--[/{t.dim}]"
            )
            icon = f"[{sc}]{branch.status_icon}[/{sc}]"
            meta = f"[{t.dim}]{branch.commits}c  (rev {branch.revision})[/{t.dim}]"
            head_marker = f"  [{t.bright}]◀ HEAD[/{t.bright}]" if is_head else ""
            blocker = (
                f"  [{t.yellow}]{branch.blocker_reason}[/{t.yellow}]"
                if branch.blocker_reason and is_selected
                else ""
            )

            lines.append(
                f"{cursor}[{t.dim}]{connector}[/{t.dim}] {bar} {name}  {pr_label}  {icon}  {meta}{head_marker}{blocker}"
            )

        cgb = self.stack_view.current_git_branch
        if cgb and self.stack_view.index_of(cgb) is None and cgb != base:
            lines.append(
                f"\n[{t.yellow}]⚠ current branch [{t.bright}]{cgb}[/{t.bright}] not in stack[/{t.yellow}]"
                f"\n[{t.dim}]→ run arc add {cgb}[/{t.dim}]"
            )

        return "\n".join(lines)


class DetailWidget(Static):
    """Inline detail panel for the selected branch (like `arc show`)."""

    def __init__(self, stack_view: StackView, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view

    def render(self) -> str:
        t = _T
        current = self.stack_view.current_branch
        if not current:
            return ""

        lines: list[str] = []
        lines.append(f"[{t.muted}]$ arc show {current.name}[/{t.muted}]")
        lines.append(f"[{t.dim}]branch [/{t.dim}][{t.bright}]{current.name}[/{t.bright}]")
        lines.append(f"[{t.dim}]base   [/{t.dim}][{t.fg}]{current.base}[/{t.fg}]")
        commit_word = "commit" if current.commits == 1 else "commits"
        lines.append(
            f"[{t.dim}]commits[/{t.dim}] [{t.fg}]{current.commits} {commit_word}[/{t.fg}]  [{t.dim}]rev {current.revision}[/{t.dim}]"
        )

        if current.pr_number:
            pr_str = f"[{t.blue}]#{current.pr_number}[/{t.blue}]"
            if current.pr_url:
                pr_str += f"  [{t.dim}]{current.pr_url}[/{t.dim}]"
            lines.append(f"[{t.dim}]pr     [/{t.dim}]{pr_str}")

            if current.ci_passing is True:
                ci_str = f"[{t.green}]✓ passing[/{t.green}]"
            elif current.ci_passing is False:
                ci_str = f"[{t.red}]✗ failing[/{t.red}]"
            else:
                ci_str = f"[{t.yellow}]⚙ running[/{t.yellow}]"
            lines.append(f"[{t.dim}]checks [/{t.dim}]{ci_str}")

            if current.approved:
                review = f"[{t.green}]✓ approved[/{t.green}]"
            elif current.draft:
                review = f"[{t.dim}]draft[/{t.dim}]"
            else:
                review = f"[{t.yellow}]○ awaiting review[/{t.yellow}]"
            lines.append(f"[{t.dim}]review [/{t.dim}]{review}")
        else:
            lines.append(
                f"[{t.dim}]pr     [/{t.dim}][{t.dim}]none — run arc push && arc submit[/{t.dim}]"
            )

        return "\n".join(lines)


# ── App ───────────────────────────────────────────────────────────────────────


def _build_css(t: DashboardTheme) -> str:
    return f"""
Screen {{
    background: {t.bg};
    color: {t.fg};
}}

#title_bar {{
    height: 1;
    background: {t.bg};
    color: {t.dim};
    padding: 0 1;
    border-bottom: tall {t.border};
}}

#scroll_area {{
    height: 1fr;
    background: {t.bg};
    scrollbar-color: {t.track} {t.bg};
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
    color: {t.muted};
    padding: 0;
}}

#branch_tree {{
    padding: 0;
    margin-bottom: 1;
}}

#detail {{
    padding: 1;
    margin-bottom: 1;
    border: tall {t.border};
}}

#detail.hidden {{
    display: none;
}}

#cmd_input {{
    height: 3;
    background: {t.bg};
    border: tall {t.border};
    color: {t.bright};
    padding: 0 1;
}}

#cmd_input:focus {{
    border: tall {t.green};
}}

#output_log {{
    height: 8;
    background: {t.bg};
    border: tall {t.border};
    scrollbar-color: {t.track} {t.bg};
    scrollbar-size: 1 1;
    padding: 0 1;
}}
"""


class DashboardApp(App):
    """Interactive dashboard for arc stacked PRs."""

    CSS = _build_css(THEMES[DEFAULT_THEME])  # overwritten in __init__ with the active theme

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
    ]

    TITLE = "arc dashboard"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, root: Path, theme: DashboardTheme | None = None):
        # Set the module-level active theme BEFORE super().__init__ so all
        # widget render() calls see the right palette from the start.
        # Also update the class-level CSS so Textual picks up the theme colors.
        global _T
        _T = theme or THEMES[DEFAULT_THEME]
        DashboardApp.CSS = _build_css(_T)
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
                yield BranchTreeWidget(empty, loading=True, id="branch_tree")
                yield DetailWidget(empty, id="detail", classes="hidden")
        yield Input(placeholder="arc› ", id="cmd_input")
        yield RichLog(id="output_log", highlight=True, markup=True)

    def on_mount(self) -> None:
        # Start unfocused so browse-mode keys (q, j/k, s, p…) work immediately.
        # The user focuses the input explicitly by clicking it or pressing Tab.
        self.query_one("#cmd_input", Input).blur()
        self.set_focus(None)
        self._load_state_async()
        self.start_polling()
        self._emit(f"[{_T.muted}]arc dashboard — use ↑↓ to navigate, enter to expand[/{_T.muted}]")

    @work(thread=True, exit_on_error=False, exclusive=True)
    def _load_state_worker(self) -> None:
        """Two-phase load: local state first (fast), then GitHub per-branch (slow)."""
        try:
            # Phase 1 — instant: read state.json + git commit counts, no network
            stack = load_local_stack_view(self.root)
            self.call_from_thread(self._on_local_load, stack)

            # Phase 2 — slow: fetch GitHub PR status one branch at a time
            for branch in stack.branches:
                if branch.pr_number:
                    try:
                        pr_status = github.get_pr_status(branch.pr_number)
                        _apply_pr_status(branch, pr_status)
                    except Exception:
                        pass
                    self.call_from_thread(self._refresh_content)

            self.call_from_thread(self._on_load_done)
        except NotInitializedError:
            v = StackView(base="main", branches=[])
            v.error = "not initialized — run arc init"
            self.call_from_thread(self._on_local_load, v)
            self.call_from_thread(self._on_load_done)
        except Exception as e:
            v = StackView(base="main", branches=[])
            v.error = str(e)
            self.call_from_thread(self._on_local_load, v)
            self.call_from_thread(self._on_load_done)

    def _on_local_load(self, stack: StackView) -> None:
        """Called from thread after fast local load — show branch tree immediately."""
        self.stack_view = stack
        self._refresh_all()

    def _on_load_done(self) -> None:
        """Called from thread when all (including GitHub) fetches are complete."""
        self._loading = False
        self._refresh_all()

    def _refresh_content(self) -> None:
        """Lightweight refresh called after each per-branch PR status fetch."""
        self._refresh_tree()
        self._refresh_detail()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        pass  # all updates driven by call_from_thread inside the worker

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
            self._emit(f"[{_T.red}]no branch selected[/{_T.red}]")

    def action_cmd_restack(self) -> None:
        if self.stack_view and self.stack_view.current_branch:
            self._run_arc("restack", self.stack_view.current_branch.name)
        else:
            self._emit(f"[{_T.red}]no branch selected[/{_T.red}]")

    def action_open_pr(self) -> None:
        if not self.stack_view or not self.stack_view.current_branch:
            self._emit(f"[{_T.yellow}]no branch selected[/{_T.yellow}]")
            return
        current = self.stack_view.current_branch
        if current.pr_url:
            self._open_url_worker(current.pr_url)
            self._emit(f"[{_T.muted}]opening PR #{current.pr_number}…[/{_T.muted}]")
        elif current.pr_number:
            self._open_pr_worker(current.pr_number)
            self._emit(f"[{_T.muted}]opening PR #{current.pr_number}…[/{_T.muted}]")
        else:
            self._emit(f"[{_T.yellow}]no PR yet — run arc push && arc submit[/{_T.yellow}]")

    def action_refresh(self) -> None:
        self._emit(f"[{_T.muted}]refreshing…[/{_T.muted}]")
        self._load_state_async()

    def on_key(self, event) -> None:  # type: ignore[override]
        # Handle q and Escape directly so they fire even when no widget is focused.
        # We skip q when the Input is focused (user might be typing a command).
        input_focused = isinstance(self.focused, Input)
        if event.key == "q" and not input_focused:
            event.stop()
            self.exit()
        elif event.key == "escape" and input_focused:
            event.stop()
            self.query_one("#cmd_input", Input).blur()
            self.set_focus(None)

    # ── Input command handling ───────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.clear()
        if not cmd:
            return
        self._emit(f"[{_T.muted}]arc› {cmd}[/{_T.muted}]")
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
                self._emit(f"[{_T.yellow}]usage: land <branch>[/{_T.yellow}]")
        elif verb in ("restack", "r"):
            branch = arg or (
                self.stack_view.current_branch.name
                if self.stack_view and self.stack_view.current_branch
                else ""
            )
            if branch:
                self._run_arc("restack", branch)
            else:
                self._emit(f"[{_T.yellow}]usage: restack <branch>[/{_T.yellow}]")
        elif verb in ("refresh", "R"):
            self.action_refresh()
        elif verb in ("quit", "q"):
            self.exit()
        else:
            self._emit(
                f"[{_T.red}]unknown: {cmd}[/{_T.red}]  [{_T.dim}]try: sync push land restack quit[/{_T.dim}]"
            )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _run_arc(self, cmd: str, branch: str = "") -> None:
        self._emit(f"[{_T.muted}]$ arc {cmd}{' ' + branch if branch else ''}[/{_T.muted}]")
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
        self._emit(f"[{_T.green}]✓ {cmd} succeeded[/{_T.green}]")
        if output:
            for line in output.splitlines()[:8]:
                self._emit(f"[{_T.dim}]  {line}[/{_T.dim}]")
        self._load_state_async()

    def _on_arc_failure(self, cmd: str, error: str) -> None:
        self._emit(f"[{_T.red}]✗ {cmd} failed[/{_T.red}]")
        for line in error.splitlines()[:5]:
            self._emit(f"[{_T.red}]  {line}[/{_T.red}]")

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
            tree.loading = self._loading
            tree.refresh()

            detail = self.query_one("#detail", DetailWidget)
            detail.stack_view = view
            detail.refresh()
        except Exception:
            pass


def run_dashboard(root: Path) -> None:
    theme = load_theme(root)
    app = DashboardApp(root, theme=theme)
    app.run()
