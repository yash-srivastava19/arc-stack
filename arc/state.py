from __future__ import annotations
import json
from pathlib import Path

STATE_VERSION = 1


def find_repo_root(start: Path | None = None) -> Path:
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Not in a git repository. Run 'git init' first.")


def _state_path(root: Path) -> Path:
    return root / ".arc" / "state.json"


def _config_path(root: Path) -> Path:
    return root / ".arc" / "config.json"


def load(root: Path) -> dict:
    path = _state_path(root)
    if not path.exists():
        raise FileNotFoundError("No stack found. Run 'arc init' to create one.")
    data = json.loads(path.read_text())
    if data.get("version") != STATE_VERSION:
        raise ValueError(f"Unknown state version {data.get('version')}. Upgrade arc.")
    return data


def save(root: Path, data: dict) -> None:
    path = _state_path(root)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_config(root: Path) -> dict:
    path = _config_path(root)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def init_state(base: str, prefix: str | None = None) -> dict:
    return {
        "version": STATE_VERSION,
        "base": base,
        "prefix": prefix,
        "branches": [],
        "metadata": {},
    }


def apply_prefix(data: dict, name: str) -> str:
    prefix = data.get("prefix")
    if prefix and not name.startswith(prefix + "/"):
        return f"{prefix}/{name}"
    return name


def add_branch(data: dict, name: str) -> dict:
    entry = {"name": name, "pr_number": None, "revision": 0}
    return {**data, "branches": data["branches"] + [entry]}


def remove_branch(data: dict, name: str) -> dict:
    return {**data, "branches": [b for b in data["branches"] if b["name"] != name]}


def update_branch(data: dict, name: str, **kwargs) -> dict:
    branches = [
        {**b, **kwargs} if b["name"] == name else b
        for b in data["branches"]
    ]
    return {**data, "branches": branches}


def get_branch(data: dict, name: str) -> dict | None:
    return next((b for b in data["branches"] if b["name"] == name), None)


def branch_names(data: dict) -> list[str]:
    return [b["name"] for b in data["branches"]]
