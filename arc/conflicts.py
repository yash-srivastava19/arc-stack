from __future__ import annotations

from pathlib import Path

from arc.git import changed_files_between
from arc.state import StackState


def predict_conflicts(data: StackState, root: Path) -> list[dict]:
    """Predict which adjacent branch pairs may conflict during sync (file-overlap heuristic)."""
    branches = [b["name"] for b in data["branches"]]
    if len(branches) < 2:
        return []
    base = data["base"]
    parents = [base] + branches[:-1]
    results = []
    for i in range(1, len(branches)):
        branch = branches[i]
        parent = parents[i]
        grandparent = parents[i - 1]
        parent_files = set(changed_files_between(root, grandparent, parent))
        branch_files = set(changed_files_between(root, parent, branch))
        shared = parent_files & branch_files
        if shared:
            results.append({"branch": branch, "parent": parent, "shared_files": sorted(shared)})
    return results
