"""Scripted layer: run each scenario's arc and git sequences, judge them, and time them.

Arms run interleaved (arc, git, arc, git, ...) so machine drift affects both equally.
Each timed run uses a fresh fixture; fixture setup is not timed.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import subprocess
import time
from pathlib import Path

from lib import (
    BENCH,
    VENV,
    expected_from_spec,
    failed_checks,
    make_env,
    new_trial_dir,
    oracle,
    passed,
    rm,
)
from scenarios import SCENARIOS

TOOL = re.compile(r"^(?:\w+=\S+\s+)*(git|arc|gh)\b")


def user_commands(lines):
    """Commands a developer types: lines that start with git, arc, or gh."""
    return sum(1 for ln in lines if TOOL.match(ln))


def run_once(sc, arm, n, trace=False, lines=None):
    root = new_trial_dir(f"{sc.id}-{arm}-n{n}")
    lines = lines or getattr(sc, arm)(n)
    pre = sc.setup(root, make_env(arm), arm, n)
    env = make_env(arm, {"BENCH_GH_LOG": str(root / "gh.log")})
    if trace:
        env["GIT_TRACE2_EVENT"] = str(root / "trace2.jsonl")
    t0 = time.perf_counter()
    p = subprocess.run(
        ["bash", "-ec", "\n".join(lines)],
        cwd=root / "work",
        env=env,
        capture_output=True,
        text=True,
    )
    secs = time.perf_counter() - t0
    out = {"rc": p.returncode, "secs": secs, "stderr": p.stderr[-2000:]}
    if trace:
        tr = root / "trace2.jsonl"
        events = [json.loads(ln) for ln in tr.read_text().splitlines()] if tr.exists() else []
        out["git_procs"] = sum(1 for e in events if e.get("event") == "start")
    spec = sc.expected(n)
    res = oracle(root, expected_from_spec(spec) if spec else None, pre, arm)
    out["oracle_pass"] = passed(res)
    out["failed"] = failed_checks(res)
    out["detail"] = {k: d for k, (ok, d) in res.items() if not ok}
    rm(root)
    return out


def versions():
    run = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout.strip()  # noqa: E731
    return {
        "arc": run(str(VENV / "bin" / "arc"), "--version"),
        "git": run("git", "--version"),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--n", default="5", help="stack depths, comma separated")
    ap.add_argument("--runs", type=int, default=15, help="timed runs per arm")
    ap.add_argument("--out", default=str(BENCH / "results" / "scripted.jsonl"))
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    meta = versions()
    with open(a.out, "a") as fh:
        for n in [int(x) for x in a.n.split(",")]:
            for sid in a.scenarios.split(","):
                sc = SCENARIOS[sid]
                arms = ["arc", "git"] if sc.arc else ["git"]
                row: dict = {"scenario": sid, "title": sc.title, "n": n, "runs": a.runs, "versions": meta}
                if not sc.arc:
                    row["arc"] = {"unsupported": True}
                first = {arm: run_once(sc, arm, n, trace=True) for arm in arms}
                times: dict = {arm: [] for arm in arms}
                fails = {arm: 0 for arm in arms}
                for _ in range(a.runs):
                    for arm in arms:
                        r = run_once(sc, arm, n)
                        times[arm].append(r["secs"] * 1000)
                        fails[arm] += not r["oracle_pass"]
                for arm in arms:
                    f, t = first[arm], sorted(times[arm])
                    row[arm] = {
                        "cmds": user_commands(getattr(sc, arm)(n)),
                        "git_procs": f["git_procs"],
                        "oracle_pass": f["oracle_pass"] and fails[arm] == 0,
                        "failed": f["failed"],
                        "detail": f["detail"],
                        "stderr": "" if f["oracle_pass"] else f["stderr"],
                        "timed_fail": fails[arm],
                        "median_ms": round(statistics.median(t), 1) if t else None,
                        "min_ms": round(t[0], 1) if t else None,
                        "max_ms": round(t[-1], 1) if t else None,
                    }
                fh.write(json.dumps(row) + "\n")
                fh.flush()

                def show(arm):
                    r = row[arm]
                    if r.get("unsupported"):
                        return f"{arm}: unsupported"
                    ok = "PASS" if r["oracle_pass"] else f"FAIL {r['failed']}"
                    return f"{arm}: {ok} cmds={r['cmds']} procs={r['git_procs']} med={r['median_ms']}ms"

                print(f"{sid} n={n} | {show('arc')} | {show('git')}", flush=True)


if __name__ == "__main__":
    main()
