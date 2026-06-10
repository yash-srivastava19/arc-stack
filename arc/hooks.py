"""Generic lifecycle hook runner.

Hooks are plain executables in a hooks directory, named by event
(git's model). Context flows as env vars (scalars) and JSON on stdin
(full structure). Exit codes are the protocol: pre-* events are gates
(non-zero aborts), post-* events are notifications (exit code ignored).

Dependency rule: this module imports stdlib only — never arc.* — so it
can be extracted as a standalone package (roadmap item 8b).

Hooks run unbounded (no timeout), like git's — a pre-submit hook may
legitimately run a full test suite. Callers should announce the hook
before invoking so users know what is running.
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
    if event not in EVENTS:
        raise ValueError(f"unknown hook event {event!r}; expected one of {EVENTS}")
    if event != ctx.event:
        raise ValueError(f"event {event!r} does not match ctx.event {ctx.event!r}")
    path = hooks_dir / event
    if not path.is_file() or not os.access(path, os.X_OK):
        return HookResult(ok=True, ran=False)
    env = {**os.environ, **ctx.as_env()}
    try:
        proc = subprocess.run(
            [str(path)],
            input=ctx.as_json(),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=ctx.root,
        )
    except OSError as exc:
        # Malformed hooks (missing/CRLF shebang, noexec mount) must fail the
        # gate, not crash the host command with a traceback.
        return HookResult(
            ok=hook_type(event) is HookType.NOTIFY,
            stderr=f"failed to execute hook: {exc}",
            exit_code=126,
            ran=True,
        )
    ok = proc.returncode == 0 or hook_type(event) is HookType.NOTIFY
    return HookResult(
        ok=ok,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        ran=True,
    )
