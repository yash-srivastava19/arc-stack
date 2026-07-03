from __future__ import annotations

from arc import state as st
from arc.state import StackState


def parent_branch(data: StackState, name: str) -> str:
    names = st.branch_names(data)
    if name not in names:
        raise ValueError(f"{name!r} not in stack")
    idx = names.index(name)
    return data["base"] if idx == 0 else names[idx - 1]


def upstack_branches(data: StackState, name: str) -> list[str]:
    names = st.branch_names(data)
    if name not in names:
        return []
    return names[names.index(name) + 1 :]


def downstack_branches(data: StackState, name: str) -> list[str]:
    names = st.branch_names(data)
    if name not in names:
        return []
    return names[: names.index(name) + 1]


def rebase_plan(data: StackState, merged: set[str] | None = None) -> list[dict]:
    merged = merged or set()
    plan = []
    prev = data["base"]
    for b in data["branches"]:
        name = b["name"]
        if name in merged:
            continue
        plan.append({"branch": name, "onto": prev})
        prev = name
    return plan


def stack_status(
    state: StackState,
    current_branch: str,
    commit_counts: dict[str, int],
    pr_info: dict[str, dict],
    needs_rebase_flags: dict[str, bool],
) -> dict:
    branches = []
    for i, b in enumerate(state["branches"]):
        name = b["name"]
        info = pr_info.get(name, {})
        branches.append(
            {
                "name": name,
                "index": i + 1,
                "pr_number": b.get("pr_number"),
                "pr_url": info.get("pr_url"),
                "pr_state": info.get("pr_state"),
                "commits": commit_counts.get(name, 0),
                "revision": b.get("revision", 0),
                "needs_rebase": needs_rebase_flags.get(name, False),
                "is_current": name == current_branch,
                "is_merged": info.get("is_merged", False),
            }
        )
    return {
        "base": state["base"],
        "prefix": state.get("prefix"),
        "current_branch": current_branch,
        "branches": branches,
    }


def build_pr_body(commit_body: str, stack_entries: list[dict], base: str) -> str:
    lines = []
    if commit_body:
        lines.append(commit_body)
        lines.append("")
    lines.append("---")
    lines.append(f"Stack (base: {base}):")
    for i, entry in enumerate(stack_entries):
        pr_ref = f"PR #{entry['pr_number']}" if entry["pr_number"] else "no PR"
        marker = " [this PR]" if entry["is_current"] else ""
        lines.append(f"  {i + 1}. {entry['name']} - {pr_ref}{marker}")
    return "\n".join(lines)


def build_pr_title(commit_subject: str, branch_name: str) -> str:
    if commit_subject:
        return commit_subject
    slug = branch_name.replace("/", " ").replace("-", " ").replace("_", " ")
    return slug.capitalize()


def next_step_hint(status: dict) -> str:
    branches = status.get("branches", [])
    if any(b["needs_rebase"] for b in branches):
        names = [b["name"] for b in branches if b["needs_rebase"]]
        return f"Run 'arc sync' to rebase {names[0]}."
    if any(b["revision"] == 0 for b in branches):
        return "Run 'arc push' to push unpushed branches."
    if any(b["pr_number"] is None for b in branches):
        return "Run 'arc submit' to create pull requests."
    return ""


def branch_at_index(data: StackState, idx: int) -> str | None:
    names = st.branch_names(data)
    if 1 <= idx <= len(names):
        return names[idx - 1]
    return None


def validate_stack(data: StackState) -> list[str]:
    errors = []
    if not data.get("base"):
        errors.append("Stack has no base branch configured.")
    if not isinstance(data.get("branches"), list):
        errors.append("Stack branches must be a list.")
    return errors
