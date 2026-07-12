from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, RichLog, Static
from textual.worker import Worker

from arc import git, github
from arc import state as st
from arc.exceptions import NotInitializedError

# ── Theme ─────────────────────────────────────────────────────────────────────


@dataclass
class DashboardTheme:
    """Color palette for the dashboard.

    Select via CLI:  arc dashboard --theme dracula
    Set as default:  arc config set dashboard.theme dracula
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
_T: DashboardTheme = THEMES[DEFAULT_THEME]


def load_theme(root: Path, override: str | None = None) -> DashboardTheme:
    """Load theme from CLI override, then config, then fall back to 'arc'."""
    if override:
        return THEMES.get(override, THEMES[DEFAULT_THEME])
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

    @property
    def branches_needing_rebase(self) -> int:
        return sum(1 for b in self.branches if b.commits == 0 and b.pr_number)

    @property
    def open_prs(self) -> int:
        return sum(1 for b in self.branches if b.pr_number and not b.draft)

    @property
    def ready_to_land(self) -> BranchStatus | None:
        # Bottom-most approved branch with no blockers
        for b in self.branches:
            if b.approved and not b.blocker_reason:
                return b
        return None


# ── State loader ─────────────────────────────────────────────────────────────


def load_local_stack_view(root: Path) -> StackView:
    """Load stack state from local sources only (no network). Fast."""
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
    """$ arc status summary line."""

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
        prs = self.stack_view.open_prs
        approved = sum(1 for b in self.stack_view.branches if b.approved)
        needs_rebase = self.stack_view.branches_needing_rebase
        ready = self.stack_view.ready_to_land

        parts = [
            f"[{t.bright}]{self.stack_view.base}[/{t.bright}]",
            f"[{t.dim}]{n} branch{'es' if n != 1 else ''}[/{t.dim}]",
        ]
        if prs:
            parts.append(f"[{t.blue}]{prs} open PR{'s' if prs != 1 else ''}[/{t.blue}]")
        if approved:
            parts.append(f"[{t.green}]{approved} approved[/{t.green}]")
        if needs_rebase:
            parts.append(f"[{t.yellow}]{needs_rebase} need rebase[/{t.yellow}]")
        if ready:
            parts.append(f"[{t.green}]{ready.name} ready to land[/{t.green}]")
        if not self.stack_view.branches:
            parts.append(f"[{t.dim}]run arc new <branch> to start[/{t.dim}]")

        header = f"[{t.muted}]$ arc status[/{t.muted}]"
        return f"{header}\n{'  '.join(parts)}"


class ActionsBarWidget(Static):
    """Top-level keyboard shortcuts bar (above the tree)."""

    def render(self) -> str:
        t = _T

        def key(k: str, label: str) -> str:
            return f"[{t.green}]\\[{k}][/{t.green}][{t.muted}] {label}[/{t.muted}]"

        return "  ".join(
            [
                key("s", "sync"),
                key("p", "push"),
                key("l", "land"),
                key("c", "checkout"),
                key("n", "new"),
                key("a", "analyze"),
                key("R", "refresh"),
                key("q", "quit"),
            ]
        )


class BranchTreeWidget(Static):
    """Indented stack tree — each branch indented under its parent."""

    def __init__(self, stack_view: StackView, loading: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view
        self.loading = loading

    def render(self) -> str:
        t = _T
        if self.loading:
            return f"[{t.dim}]loading…[/{t.dim}]"
        if not self.stack_view.branches:
            return f"[{t.dim}]stack is empty — run arc new <branch>[/{t.dim}]"

        base = self.stack_view.base
        n = len(self.stack_view.branches)
        lines = [f"[bold {t.dim}]{base}[/bold {t.dim}]"]

        for i, branch in enumerate(self.stack_view.branches):
            is_selected = i == self.stack_view.current_index
            is_head = branch.name == self.stack_view.current_git_branch

            # Indentation: each level adds 3 spaces
            indent = "   " * i
            connector = "└──" if i == n - 1 else "├──"
            accent = branch.row_accent(t)
            sc = branch.status_color(t)

            bar = f"[{accent}]┃[/{accent}]"
            cursor = f"[bold {t.green}]▶[/bold {t.green}]" if is_selected else " "

            name_style = f"bold {t.bright}" if is_head else t.fg
            name = f"[{name_style}]{branch.name}[/{name_style}]"

            pr_label = (
                f"[{t.blue}]#{branch.pr_number}[/{t.blue}]"
                if branch.pr_number
                else f"[{t.dim}]no PR[/{t.dim}]"
            )
            # show draft/open status when there's a PR
            if branch.pr_number and branch.draft:
                pr_label += f" [{t.dim}]draft[/{t.dim}]"
            elif branch.pr_number and not branch.draft and not branch.approved:
                pr_label += f" [{t.dim}]open[/{t.dim}]"

            icon = f"[{sc}]{branch.status_icon}[/{sc}]"
            meta = f"[{t.dim}]{branch.commits}c  (rev {branch.revision})[/{t.dim}]"
            head_marker = f"[{t.bright}]◀ HEAD[/{t.bright}]" if is_head else ""
            blocker = (
                f"[{t.yellow}]{branch.blocker_reason}[/{t.yellow}]" if branch.blocker_reason else ""
            )

            parts = [p for p in [name, pr_label, icon, meta, head_marker, blocker] if p]
            row = f"{indent}[{t.dim}]{connector}[/{t.dim}] {bar} {cursor} {'  '.join(parts)}"
            lines.append(row)

        # Warn when on a branch not in the stack
        cgb = self.stack_view.current_git_branch
        if cgb and self.stack_view.index_of(cgb) is None and cgb != base:
            lines.append(
                f"\n[{t.yellow}]⚠  [{t.bright}]{cgb}[/{t.bright}] is not in the stack[/{t.yellow}]"
                f"\n[{t.dim}]   run arc add {cgb} to include it[/{t.dim}]"
            )

        # Rebase hint
        needs_rebase = self.stack_view.branches_needing_rebase
        if needs_rebase:
            lines.append(
                f"\n[{t.dim}]→ Run 'arc sync' to rebase {needs_rebase} "
                f"branch{'es' if needs_rebase != 1 else ''}.[/{t.dim}]"
            )

        return "\n".join(lines)


class DetailWidget(Static):
    """Branch detail panel — $ arc show <branch>."""

    def __init__(self, stack_view: StackView, **kwargs):
        super().__init__(**kwargs)
        self.stack_view = stack_view

    def render(self) -> str:
        t = _T
        current = self.stack_view.current_branch
        if not current:
            return f"[{t.dim}]select a branch to see details[/{t.dim}]"

        lines: list[str] = []
        lines.append(f"[{t.muted}]$ arc show {current.name}[/{t.muted}]")
        lines.append(f"[{t.dim}]branch [/{t.dim}][{t.bright}]{current.name}[/{t.bright}]")
        lines.append(f"[{t.dim}]base   [/{t.dim}][{t.fg}]{current.base}[/{t.fg}]")
        commit_word = "commit" if current.commits == 1 else "commits"
        lines.append(
            f"[{t.dim}]commits[/{t.dim}] [{t.fg}]{current.commits} {commit_word}[/{t.fg}]"
            f"  [{t.dim}]rev {current.revision}[/{t.dim}]"
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


class StatusBarWidget(Static):
    """Bottom status bar with key hints."""

    def render(self) -> str:
        t = _T

        def key(k: str, label: str) -> str:
            return f"[bold {t.green}]{k}[/bold {t.green}][{t.dim}] {label}[/{t.dim}]"

        parts = [
            key("j/k", "nav"),
            key("enter", "select"),
            key("c", "checkout"),
            key("s", "sync"),
            key("p", "push"),
            key("l", "land"),
            key("n", "new"),
            key("a", "analyze"),
            key("?", "help"),
            key("q", "quit"),
        ]
        right = f"[{t.dim}]arc {_arc_version()}  ·  {_T.name}[/{t.dim}]"
        return "  ".join(parts) + f"  {right}"


def _arc_version() -> str:
    try:
        from arc import __version__

        return __version__
    except Exception:
        return "?"


class HelpScreen(ModalScreen):
    """? key — keybinding reference overlay."""

    BINDINGS = [("escape,q,?", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        t = _T

        def row(k: str, desc: str) -> str:
            return f"  [{t.green}]{k:<14}[/{t.green}][{t.fg}]{desc}[/{t.fg}]"

        lines = [
            f"[bold {t.bright}]arc dashboard — keyboard reference[/bold {t.bright}]",
            "",
            f"[{t.muted}]Navigation[/{t.muted}]",
            row("j / k / ↑ / ↓", "move selection up/down"),
            row("enter", "show/hide branch detail"),
            "",
            f"[{t.muted}]Stack operations[/{t.muted}]",
            row("s", "arc sync (rebase stack)"),
            row("p", "arc push (update PRs)"),
            row("l", "arc land (merge selected)"),
            row("r", "arc restack (rebase selected)"),
            row("n", "arc new <name> (new branch)"),
            row("a", "arc stack analyze"),
            row("c", "git checkout selected branch"),
            row("o", "open PR in browser"),
            row("R", "refresh dashboard"),
            "",
            f"[{t.muted}]Input[/{t.muted}]",
            row("Tab / click", "focus arc› command input"),
            row("Escape", "unfocus input / close help"),
            row("q", "quit"),
            "",
            f"[{t.dim}]Themes: arc, dracula, nord, gruvbox, catppuccin, tokyo-night[/{t.dim}]",
            f"[{t.dim}]arc dashboard --theme <name>   or   arc config set dashboard.theme <name>[/{t.dim}]",
            "",
            f"[{t.dim}]Press Escape, q, or ? to close[/{t.dim}]",
        ]
        yield Static("\n".join(lines), id="help_content")

    CSS = """
HelpScreen {
    align: center middle;
}
#help_content {
    padding: 2 4;
    width: 64;
    border: tall #1e211a;
}
"""


# ── App CSS builder ──────────────────────────────────────────────────────────


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

#main_area {{
    height: 1fr;
}}

#left_col {{
    width: 60%;
    background: {t.bg};
    border-right: tall {t.border};
}}

#summary {{
    height: auto;
    padding: 1 2 0 2;
}}

#actions_bar {{
    height: 1;
    padding: 0 2;
    margin-top: 1;
    color: {t.muted};
}}

#tree_scroll {{
    height: 1fr;
    background: {t.bg};
    scrollbar-color: {t.track} {t.bg};
    scrollbar-size: 1 1;
    padding: 1 2;
}}

#right_col {{
    width: 40%;
    background: {t.bg};
}}

#detail {{
    height: 1fr;
    padding: 1 2;
    border-bottom: tall {t.border};
}}

#output_log {{
    height: 1fr;
    background: {t.bg};
    scrollbar-color: {t.track} {t.bg};
    scrollbar-size: 1 1;
    padding: 0 1;
}}

#cmd_input {{
    height: 3;
    background: {t.bg};
    border-top: tall {t.border};
    border-bottom: tall {t.border};
    color: {t.bright};
    padding: 0 1;
}}

#cmd_input:focus {{
    border-top: tall {t.green};
    border-bottom: tall {t.green};
}}

#status_bar {{
    height: 1;
    background: {t.bg};
    color: {t.dim};
    padding: 0 1;
    border-top: tall {t.border};
}}

HelpScreen #help_content {{
    background: {t.bg};
    border: tall {t.border};
    color: {t.fg};
}}
"""


# ── App ───────────────────────────────────────────────────────────────────────


class DashboardApp(App):
    """Interactive dashboard for arc stacked PRs."""

    CSS = _build_css(THEMES[DEFAULT_THEME])

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
        Binding("n", "cmd_new", "new branch", show=False),
        Binding("a", "cmd_analyze", "analyze", show=False),
        Binding("c", "cmd_checkout", "checkout", show=False),
    ]

    TITLE = "arc dashboard"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, root: Path, theme: DashboardTheme | None = None):
        global _T
        _T = theme or THEMES[DEFAULT_THEME]
        DashboardApp.CSS = _build_css(_T)
        super().__init__()
        self.root = root
        self.stack_view: StackView | None = None
        self._loading = True

    def compose(self) -> ComposeResult:
        empty = StackView(base="…", branches=[])
        yield TitleBarWidget(id="title_bar")
        with Horizontal(id="main_area"):
            with Vertical(id="left_col"):
                yield SummaryWidget(empty, loading=True, id="summary")
                yield ActionsBarWidget(id="actions_bar")
                with ScrollableContainer(id="tree_scroll"):
                    yield BranchTreeWidget(empty, loading=True, id="branch_tree")
            with Vertical(id="right_col"):
                yield DetailWidget(empty, id="detail")
                yield RichLog(id="output_log", highlight=True, markup=True)
        yield Input(placeholder="arc› ", id="cmd_input")
        yield StatusBarWidget(id="status_bar")

    def on_mount(self) -> None:
        self.query_one("#cmd_input", Input).blur()
        self.set_focus(None)
        self._load_state_async()
        self.start_polling()
        self._emit(
            f"[{_T.muted}]arc dashboard ready — use ↑↓/j/k to navigate, ? for help[/{_T.muted}]"
        )

    # ── Loading ─────────────────────────────────────────────────────────────

    @work(thread=True, exit_on_error=False, exclusive=True)
    def _load_state_worker(self) -> None:
        """Two-phase: local state first (instant), then GitHub PR status (per-branch)."""
        try:
            stack = load_local_stack_view(self.root)
            self.call_from_thread(self._on_local_load, stack)

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
        self.stack_view = stack
        self._refresh_all()

    def _on_load_done(self) -> None:
        self._loading = False
        self._refresh_all()

    def _refresh_content(self) -> None:
        self._refresh_tree()
        self._refresh_detail()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        pass

    def _load_state_async(self) -> None:
        self._loading = True
        self._load_state_worker()

    @work(exclusive=True)
    async def start_polling(self) -> None:
        while True:
            await asyncio.sleep(30)
            self._load_state_async()

    # ── Navigation ──────────────────────────────────────────────────────────

    def action_move_up(self) -> None:
        if self.stack_view:
            self.stack_view.move_selection(-1)
            self._refresh_tree()
            self._refresh_detail()

    def action_move_down(self) -> None:
        if self.stack_view:
            self.stack_view.move_selection(1)
            self._refresh_tree()
            self._refresh_detail()

    def action_toggle_detail(self) -> None:
        # In the two-column layout the detail panel is always visible;
        # Enter now scrolls the tree to the selected row instead.
        self._refresh_detail()

    # ── Stack commands ───────────────────────────────────────────────────────

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

    def action_cmd_new(self) -> None:
        """Focus the input pre-filled with 'new ' so user can type the branch name."""
        inp = self.query_one("#cmd_input", Input)
        inp.value = "new "
        inp.focus()
        inp.cursor_position = len(inp.value)

    def action_cmd_analyze(self) -> None:
        self._run_arc_raw(["arc", "stack", "analyze"])

    def action_cmd_checkout(self) -> None:
        if not self.stack_view or not self.stack_view.current_branch:
            self._emit(f"[{_T.yellow}]no branch selected[/{_T.yellow}]")
            return
        branch = self.stack_view.current_branch.name
        self._emit(f"[{_T.muted}]$ git checkout {branch}[/{_T.muted}]")
        self._checkout_worker(branch)

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

    # ── Keys ─────────────────────────────────────────────────────────────────

    def on_key(self, event) -> None:  # type: ignore[override]
        input_focused = isinstance(self.focused, Input)
        if event.key == "q" and not input_focused:
            event.stop()
            self.exit()
        elif event.key == "question_mark" and not input_focused:
            event.stop()
            self.push_screen(HelpScreen())
        elif event.key == "escape" and input_focused:
            event.stop()
            self.query_one("#cmd_input", Input).blur()
            self.set_focus(None)

    # ── Input handler ────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.clear()
        event.input.blur()
        self.set_focus(None)
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
        elif verb in ("new", "n"):
            if arg:
                self._run_arc("new", arg)
            else:
                self._emit(f"[{_T.yellow}]usage: new <branch-name>[/{_T.yellow}]")
        elif verb in ("analyze", "a"):
            self._run_arc_raw(["arc", "stack", "analyze"])
        elif verb in ("checkout", "c"):
            branch = arg or (
                self.stack_view.current_branch.name
                if self.stack_view and self.stack_view.current_branch
                else ""
            )
            if branch:
                self._emit(f"[{_T.muted}]$ git checkout {branch}[/{_T.muted}]")
                self._checkout_worker(branch)
            else:
                self._emit(f"[{_T.yellow}]usage: checkout <branch>[/{_T.yellow}]")
        elif verb in ("refresh", "R"):
            self.action_refresh()
        elif verb in ("quit", "q"):
            self.exit()
        elif verb in ("help", "?"):
            self.push_screen(HelpScreen())
        else:
            self._emit(
                f"[{_T.red}]unknown: {cmd}[/{_T.red}]  [{_T.dim}]press ? for help[/{_T.dim}]"
            )

    # ── Workers ──────────────────────────────────────────────────────────────

    def _run_arc(self, cmd: str, branch: str = "") -> None:
        self._emit(f"[{_T.muted}]$ arc {cmd}{' ' + branch if branch else ''}[/{_T.muted}]")
        self._run_arc_worker(cmd, branch)

    def _run_arc_raw(self, args: list[str]) -> None:
        self._emit(f"[{_T.muted}]$ {' '.join(args)}[/{_T.muted}]")
        self._run_raw_worker(args)

    @work(thread=True, exit_on_error=False)
    def _run_arc_worker(self, cmd: str, branch: str) -> None:
        try:
            args = ["arc", cmd] + ([branch] if branch and cmd in ("land", "restack", "new") else [])
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                out = (result.stdout or "").strip()
                self.call_from_thread(self._on_arc_success, cmd, out)
            else:
                err = (result.stderr or result.stdout or "unknown error").strip()[:300]
                self.call_from_thread(self._on_arc_failure, cmd, err)
        except Exception as e:
            self.call_from_thread(self._on_arc_failure, cmd, str(e)[:150])

    @work(thread=True, exit_on_error=False)
    def _run_raw_worker(self, args: list[str]) -> None:
        try:
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, timeout=60)
            out = (result.stdout or result.stderr or "").strip()
            color = _T.green if result.returncode == 0 else _T.red
            for line in out.splitlines()[:20]:
                self.call_from_thread(self._emit, f"[{color}]{line}[/{color}]")
            if result.returncode == 0:
                self.call_from_thread(self._load_state_async)
        except Exception as e:
            self.call_from_thread(self._emit, f"[{_T.red}]{e}[/{_T.red}]")

    @work(thread=True, exit_on_error=False)
    def _checkout_worker(self, branch: str) -> None:
        try:
            result = subprocess.run(
                ["git", "checkout", branch],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self.call_from_thread(
                    self._emit, f"[{_T.green}]✓ checked out {branch}[/{_T.green}]"
                )
                self.call_from_thread(self._load_state_async)
            else:
                err = (result.stderr or "").strip()
                self.call_from_thread(self._emit, f"[{_T.red}]✗ {err}[/{_T.red}]")
        except Exception as e:
            self.call_from_thread(self._emit, f"[{_T.red}]{e}[/{_T.red}]")

    def _on_arc_success(self, cmd: str, output: str) -> None:
        self._emit(f"[{_T.green}]✓ {cmd} succeeded[/{_T.green}]")
        if output:
            for line in output.splitlines()[:10]:
                self._emit(f"[{_T.dim}]  {line}[/{_T.dim}]")
        self._load_state_async()

    def _on_arc_failure(self, cmd: str, error: str) -> None:
        self._emit(f"[{_T.red}]✗ {cmd} failed[/{_T.red}]")
        for line in error.splitlines()[:6]:
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

    # ── Refresh helpers ──────────────────────────────────────────────────────

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


def run_dashboard(root: Path, theme_name: str | None = None) -> None:
    theme = load_theme(root, override=theme_name)
    app = DashboardApp(root, theme=theme)
    app.run()
