from __future__ import annotations

from dataclasses import dataclass

from arc.state import StackState


@dataclass
class StackAnalysis:
    safe_to_land: list[str]
    blocked: dict[str, str]
    critical_path: list[str]
    in_merge_queue: list[str]


def analyze_stack(data: StackState, statuses: dict[str, dict]) -> StackAnalysis:
    branches = [b["name"] for b in data["branches"]]
    safe_to_land: list[str] = []
    blocked: dict[str, str] = {}
    in_merge_queue: list[str] = []
    parent_ready: dict[str, bool] = {}

    for i, name in enumerate(branches):
        parent = data["base"] if i == 0 else branches[i - 1]
        s = statuses.get(name, {})
        if s.get("in_merge_queue"):
            in_merge_queue.append(name)
        parent_ok = True if i == 0 else parent_ready.get(parent, False)
        if not parent_ok:
            blocked[name] = f"waiting on {parent}"
            parent_ready[name] = False
        elif s.get("draft"):
            blocked[name] = "PR is still a draft"
            parent_ready[name] = False
        elif not s.get("approved"):
            blocked[name] = "not yet approved"
            parent_ready[name] = False
        elif s.get("ci_passing") is False:
            blocked[name] = "CI is failing"
            parent_ready[name] = False
        else:
            safe_to_land.append(name)
            parent_ready[name] = True

    return StackAnalysis(
        safe_to_land=safe_to_land,
        blocked=blocked,
        critical_path=list(branches),
        in_merge_queue=in_merge_queue,
    )
