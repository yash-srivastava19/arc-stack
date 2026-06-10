"""Generic lifecycle hook runner.

Hooks are plain executables in a hooks directory, named by event
(git's model). Context flows as env vars (scalars) and JSON on stdin
(full structure). Exit codes are the protocol: pre-* events are gates
(non-zero aborts), post-* events are notifications (exit code ignored).

Dependency rule: this module imports stdlib only — never arc.* — so it
can be extracted as a standalone package (roadmap item 8b).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

EVENTS = (
    "pre-submit",
    "post-submit",
    "pre-land",
    "post-land",
    "pre-sync",
    "post-sync",
    "pre-push",
    "post-push",
)


class HookType(Enum):
    GATE = "gate"  # non-zero exit aborts the host command
    NOTIFY = "notify"  # exit code ignored


def hook_type(event: str) -> HookType:
    return HookType.GATE if event.startswith("pre-") else HookType.NOTIFY


@dataclass
class HookContext:
    event: str
    branch: str
    base: str
    root: Path
    version: str
    extra: dict = field(default_factory=dict)
    stack: list = field(default_factory=list)

    def as_env(self) -> dict[str, str]:
        env = {
            "ARC_EVENT": self.event,
            "ARC_BRANCH": self.branch,
            "ARC_BASE": self.base,
            "ARC_ROOT": str(self.root),
            "ARC_VERSION": self.version,
        }
        for key, value in self.extra.items():
            if value is None:
                continue
            text = str(value).lower() if isinstance(value, bool) else str(value)
            env[f"ARC_{key.upper()}"] = text
        return env

    def as_json(self) -> str:
        return json.dumps(
            {
                "event": self.event,
                "branch": self.branch,
                "base": self.base,
                "version": self.version,
                "extra": self.extra,
                "stack": self.stack,
            }
        )


@dataclass
class HookResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    ran: bool = False


def run_hook(event: str, ctx: HookContext, hooks_dir: Path) -> HookResult:
    path = hooks_dir / event
    if not path.is_file() or not os.access(path, os.X_OK):
        return HookResult(ok=True, ran=False)
    env = {**os.environ, **ctx.as_env()}
    proc = subprocess.run(
        [str(path)],
        input=ctx.as_json(),
        env=env,
        capture_output=True,
        text=True,
        cwd=ctx.root,
    )
    ok = proc.returncode == 0 or hook_type(event) is HookType.NOTIFY
    return HookResult(
        ok=ok,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        ran=True,
    )
