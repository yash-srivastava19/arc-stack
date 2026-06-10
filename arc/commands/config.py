from __future__ import annotations

import sys

import click

from arc import git
from arc import state as st
from arc.commands import _shared
from arc.commands._shared import err, out

_JSON_SCHEMAS: dict[str, dict] = {
    "status": {
        "type": "object",
        "properties": {
            "base": {"type": "string"},
            "prefix": {"type": ["string", "null"]},
            "current_branch": {"type": "string"},
            "branches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "index": {"type": "integer"},
                        "pr_number": {"type": ["integer", "null"]},
                        "pr_url": {"type": ["string", "null"]},
                        "pr_state": {"type": ["string", "null"]},
                        "commits": {"type": "integer"},
                        "revision": {"type": "integer"},
                        "needs_rebase": {"type": "boolean"},
                        "is_current": {"type": "boolean"},
                        "is_merged": {"type": "boolean"},
                    },
                },
            },
        },
    },
    "submit": {
        "type": "object",
        "properties": {
            "created": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "branch": {"type": "string"},
                        "pr_number": {"type": "integer"},
                        "pr_url": {"type": "string"},
                    },
                },
            },
            "updated": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "branch": {"type": "string"},
                        "pr_number": {"type": "integer"},
                        "pr_url": {"type": "string"},
                        "revision": {"type": "integer"},
                    },
                },
            },
        },
    },
    "analyze": {
        "type": "object",
        "properties": {
            "critical_path": {"type": "array", "items": {"type": "string"}},
            "safe_to_land": {"type": "array", "items": {"type": "string"}},
            "blocked": {"type": "object", "additionalProperties": {"type": "string"}},
            "in_merge_queue": {"type": "array", "items": {"type": "string"}},
        },
    },
}


@click.command("schema")
@click.argument("command", type=click.Choice(list(_JSON_SCHEMAS)))
def schema_cmd(command: str) -> None:
    """Print JSON Schema for a command's --json output."""
    import json as _j

    out.print_json(_j.dumps(_JSON_SCHEMAS[command], indent=2))


@click.group("config")
def config_group() -> None:
    """Read and write arc configuration."""


@config_group.command("get")
@click.argument("key")
def config_get_cmd(key: str) -> None:
    """Get a config value (e.g. arc config get feedback.enabled)."""
    root = git.find_repo_root()
    cfg = st.load_config(root)
    val = cfg
    for part in key.split("."):
        if not isinstance(val, dict) or part not in val:
            err.print(f"Key {key!r} not found.")
            sys.exit(1)
        val = val[part]
    out.print(str(val))


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set_cmd(key: str, value: str) -> None:
    """Set a config value (e.g. arc config set feedback.enabled false)."""
    import json as _j

    root = git.find_repo_root()
    cfg = st.load_config(root)
    parts = key.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    # coerce common types
    coerced: object = value
    if value.lower() == "true":
        coerced = True
    elif value.lower() == "false":
        coerced = False
    elif value.isdigit():
        coerced = int(value)
    node[parts[-1]] = coerced
    config_path = root / ".arc" / "config.json"
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(_j.dumps(cfg, indent=2))
    if not _shared._is_tty():
        return
    err.print(f"Set {key} = {coerced}")


@config_group.command("list")
def config_list_cmd() -> None:
    """List all config values."""
    root = git.find_repo_root()
    cfg = st.load_config(root)

    def _flat(d: dict, prefix: str = "") -> list[str]:
        lines = []
        for k, v in d.items():
            full = f"{prefix}{k}" if prefix else k
            if isinstance(v, dict):
                lines.extend(_flat(v, f"{full}."))
            else:
                lines.append(f"{full} = {v}")
        return lines

    for line in _flat(cfg):
        out.print(line)
