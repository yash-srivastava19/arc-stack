"""Layer 2: headless agent trials. Same model, same task text; arms differ only in tooling."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import (
    BENCH,
    expected_from_spec,
    failed_checks,
    make_env,
    new_trial_dir,
    oracle,
    passed,
    rm,
)
from scenarios import SCENARIOS

CLAUDE = shutil.which("claude") or "claude"
ARC_DOC = (BENCH.parent / "skills" / "arc.md").read_text()
MAX_CALLS = 40
TIMEOUT_S = 900
HOME = Path.home()


def jail(root: Path) -> list[str]:
    """bwrap: whole filesystem read-only except the trial dir and claude's own state (auth)."""
    return [
        "bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--ro-bind", str(BENCH), str(BENCH), "--bind", str(root), str(root),
        "--bind", str(HOME / ".claude"), str(HOME / ".claude"),
        "--bind", str(HOME / ".claude.json"), str(HOME / ".claude.json"),
        "--die-with-parent", "--chdir", str(root),
    ]

BASE_SYS = (
    "You are a software engineer working in a non-interactive Linux shell. There is no GitHub or "
    "network access: 'origin' is a local bare repository. No editor is available (GIT_EDITOR=true). "
    "Do the task completely and verify the result yourself before finishing. Do not ask questions."
)
ARMS = {
    "arc": BASE_SYS
    + "\n\nThe stacked-branch CLI `arc` is installed and this repository's stack is already "
    "initialized with arc (base: main). Prefer arc for stack operations.\n\n# arc documentation\n\n"
    + ARC_DOC,
    "arc_nodoc": BASE_SYS
    + "\n\nThe stacked-branch CLI `arc` is installed and this repository's stack is already "
    "initialized with arc (base: main). Prefer arc for stack operations. Use `arc --help` to learn it.",
    "git": BASE_SYS + "\n\nUse git (version 2.55) for everything.",
}

TOOL_RE = re.compile(r"(?:^|[;&|(]\s*|\s)(arc|git|gh)\s")
DESTRUCTIVE = re.compile(
    r"reset\s+--hard|push\s+[^;&|]*(?<!-with-lease)(?:\s-f\b|\s--force\b(?!-with-lease))|branch\s+-D\b|checkout\s+--\s|clean\s+-f|rm\s+-rf"
)


def run_trial(sid: str, arm: str, model: str, n: int, budget: float, idx: int) -> dict:
    sc = SCENARIOS[sid]
    env_arm = "git" if arm == "git" else "arc"
    root = new_trial_dir(f"agent-{sid}-{arm}-{model}-{idx}")
    env = make_env(env_arm)
    pre = sc.setup(root, env, env_arm, n)
    spec = sc.expected(n)
    exp = expected_from_spec(spec) if spec else None

    run_env = make_env(env_arm, {"BENCH_GH_LOG": str(root / "gh.log")})
    cmd = jail(root) + [
        CLAUDE,
        "-p",
        "--model",
        model,
        "--output-format",
        "stream-json",
        "--verbose",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--system-prompt",
        ARMS[arm],
        "--tools",
        "Bash",
        "--allowedTools",
        "Bash",
        "--permission-mode",
        "dontAsk",
        "--max-budget-usd",
        str(budget),
        sc.prompt(n),
    ]
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        cmd, cwd=root, env=run_env, stdout=subprocess.PIPE, stderr=open(root / "claude.stderr", "w"), text=True
    )
    killer = threading.Timer(TIMEOUT_S, proc.kill)
    killer.start()
    commands, result, capped = [], None, False
    transcript = []
    for line in proc.stdout:
        transcript.append(line)
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for blk in ev.get("message", {}).get("content", []):
                if blk.get("type") == "tool_use":
                    commands.append(blk.get("input", {}).get("command", ""))
                    if len(commands) > MAX_CALLS:
                        capped = True
                        proc.kill()
        elif ev.get("type") == "result":
            result = ev
    proc.wait()
    killer.cancel()
    wall = time.perf_counter() - t0

    res = oracle(root, exp, pre)
    ok = passed(res)
    text = (result or {}).get("result", "") or ""
    claimed = "DONE" in text
    usage = (result or {}).get("usage", {})
    joined = "\n".join(commands)
    out = {
        "scenario": sid,
        "arm": arm,
        "model": model,
        "n": n,
        "idx": idx,
        "success": ok and not capped,
        "failed": failed_checks(res),
        "detail": {k: d for k, (o, d) in res.items() if not o},
        "tool_calls": len(commands),
        "tool_invocations": {
            t: len(re.findall(rf"(?:^|[;&|(]\s*|\s|\n){t}\s", "\n" + joined))
            for t in ("arc", "git", "gh")
        },
        "status_calls": len(re.findall(r"\barc\s+status\b", joined)),
        "destructive": len(DESTRUCTIVE.findall(joined)),
        "claimed_done": claimed,
        "false_done": claimed and not ok,
        "capped": capped,
        "timed_out": wall >= TIMEOUT_S,
        "cost_usd": (result or {}).get("total_cost_usd"),
        "num_turns": (result or {}).get("num_turns"),
        "tokens_in": (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0),
        "tokens_out": usage.get("output_tokens"),
        "wall_s": round(wall, 1),
        "harness_error": result is None,
        "gh_calls": (root / "gh.log").read_text().splitlines()
        if (root / "gh.log").exists()
        else [],
        "commands": commands,
        "final_text": text[-600:],
    }
    tdir = BENCH / "results" / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / f"{sid}-{arm}-{model}-{idx}.jsonl").write_text("".join(transcript))
    if not os.environ.get("BENCH_KEEP"):
        rm(root)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="S6")
    ap.add_argument("--arms", default="arc,git")
    ap.add_argument("--models", default="sonnet")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default=str(BENCH / "results" / "agent.jsonl"))
    a = ap.parse_args()
    jobs = [
        (s, arm, m, a.n, a.budget, i)
        for i in range(a.start, a.start + a.trials)
        for s in a.scenarios.split(",")
        for m in a.models.split(",")
        for arm in a.arms.split(",")
    ]
    lock = threading.Lock()
    with open(a.out, "a") as fh, ThreadPoolExecutor(a.jobs) as ex:

        def go(j):
            try:
                r = run_trial(*j)
            except Exception as e:  # harness failure, not a tool failure
                r = {
                    "scenario": j[0],
                    "arm": j[1],
                    "model": j[2],
                    "idx": j[5],
                    "harness_error": True,
                    "error": repr(e),
                }
            with lock:
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                print(
                    f"{r['scenario']} {r['arm']:9s} {r['model']:6s} #{r['idx']}: success={r.get('success')} "
                    f"calls={r.get('tool_calls')} cost={r.get('cost_usd')} failed={r.get('failed')} "
                    f"herr={r.get('harness_error')}",
                    flush=True,
                )

        list(ex.map(go, jobs))


if __name__ == "__main__":
    main()
