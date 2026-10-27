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
    own_files = [set(changed_files_between(root, p, b)) for p, b in zip(parents, branches)]
    results = []
    for i in range(1, len(branches)):
        shared = own_files[i - 1] & own_files[i]
        if shared:
            results.append(
                {"branch": branches[i], "parent": parents[i], "shared_files": sorted(shared)}
            )
    return results
