from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from arc.exceptions import NotInitializedError, StateVersionError

STATE_VERSION = 1


class BranchEntry(TypedDict):
    name: str
    pr_number: int | None
    revision: int


class StackState(TypedDict):
    version: int
    base: str
    prefix: str | None
    branches: list[BranchEntry]
    metadata: dict[str, Any]


def _state_path(root: Path):
    return root / ".arc" / "state.json"


def _config_path(root: Path):
    return root / ".arc" / "config.json"


def load(root: Path) -> StackState:
    path = _state_path(root)
    if not path.exists():
        raise NotInitializedError("No stack found. Run 'arc init' to create one.")
    data: StackState = json.loads(path.read_text())
    if data.get("version") != STATE_VERSION:
        raise StateVersionError(f"Unknown state version {data.get('version')}. Upgrade arc.")
    return data


def save(root: Path, data):
    path = _state_path(root)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_config(root: Path):
    path = _config_path(root)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def init_state(base: str, prefix: str | None = None):
    return {
        "version": STATE_VERSION,
        "base": base,
        "prefix": prefix,
        "branches": [],
        "metadata": {},
    }


def apply_prefix(data, name: str):
    prefix = data.get("prefix")
    if prefix and not name.startswith(prefix + "/"):
        return f"{prefix}/{name}"
    return name


def add_branch(data, name: str):
    entry = {"name": name, "pr_number": None, "revision": 0}
    return {**data, "branches": data["branches"] + [entry]}


def remove_branch(data, name: str):
    return {**data, "branches": [b for b in data["branches"] if b["name"] != name]}


def update_branch(data, name: str, **kwargs):
    branches = [{**b, **kwargs} if b["name"] == name else b for b in data["branches"]]
    return {**data, "branches": branches}


def get_branch(data, name: str):
    return next((b for b in data["branches"] if b["name"] == name), None)


def branch_names(data):
    return [b["name"] for b in data["branches"]]
