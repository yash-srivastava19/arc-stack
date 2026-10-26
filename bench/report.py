"""Aggregate results/*.jsonl into markdown tables."""

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

R = Path(__file__).resolve().parent / "results"


def load(name):
    p = R / name
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def wilson(k, n, z=1.96):
    if n == 0:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def scripted_table(rows):
    out = [
        "| Scenario | n | Arm | Cmds | Git procs | Median ms | p95 ms | Oracle | Failed checks |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        for arm in ("arc", "arcfix", "git"):
            if arm not in r:
                continue
            a = r[arm]
            label = {"arc": "arc (documented)", "arcfix": "arc + workaround", "git": "expert git"}[
                arm
            ]
            out.append(
                f"| {r['scenario']} | {r['n']} | {label} | {a['cmds']} | {a['git_procs']} | {a['median_ms']} | {a['p95_ms']} | "
                f"{'PASS' if a['oracle_pass'] else '**FAIL**'} | {', '.join(a['failed'])} |"
            )
    return "\n".join(out)


def agent_table(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r["scenario"], r["arm"], r["model"])].append(r)
    out = [
        "| Scenario | Model | Arm | Trials | Harness err | Success [95% CI] | Tool calls med (IQR) | Cost $ med | Wall s med | False-done | Destructive/trial | Top failed checks |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (s, arm, m), rs in sorted(g.items()):
        valid = [r for r in rs if not r.get("harness_error") or r.get("capped")]
        k = sum(r["success"] for r in valid)
        n = len(valid)
        lo, hi = wilson(k, n)
        calls = sorted(r["tool_calls"] for r in valid) or [0]
        q = lambda p: calls[int(p * (len(calls) - 1))]
        costs = [r["cost_usd"] or 0 for r in valid] or [0]
        walls = [r["wall_s"] for r in valid] or [0]
        fails = defaultdict(int)
        for r in valid:
            for f in r["failed"]:
                fails[f] += 1
        top = ", ".join(f"{f}×{c}" for f, c in sorted(fails.items(), key=lambda x: -x[1])[:3])
        out.append(
            f"| {s} | {m} | {arm} | {n} | {len(rs) - n} | {k}/{n} ({lo:.0%}–{hi:.0%}) | {statistics.median(calls):.0f} ({q(0.25)}–{q(0.75)}) | "
            f"{statistics.median(costs):.2f} | {statistics.median(walls):.0f} | {sum(r['false_done'] for r in valid)} | "
            f"{statistics.mean([r['destructive'] for r in valid]) if valid else 0:.1f} | {top} |"
        )
    return "\n".join(out)


def agent_pooled(rows):
    g = defaultdict(list)
    for r in rows:
        if not r.get("harness_error") or r.get("capped"):
            g[(r["model"], r["arm"])].append(r)
    out = [
        "| Model | Arm | Trials | Success [95% CI] | Median tool calls | Total cost $ | False-done | Destructive cmds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for (m, arm), rs in sorted(g.items()):
        k, n = sum(r["success"] for r in rs), len(rs)
        lo, hi = wilson(k, n)
        out.append(
            f"| {m} | {arm} | {n} | {k}/{n} = {k / n:.0%} ({lo:.0%}–{hi:.0%}) | {statistics.median(r['tool_calls'] for r in rs):.0f} | "
            f"{sum(r['cost_usd'] or 0 for r in rs):.2f} | {sum(r['false_done'] for r in rs)} | {sum(r['destructive'] for r in rs)} |"
        )
    return "\n".join(out)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "scripted"):
        print("## Scripted n=5\n\n" + scripted_table(load("scripted.jsonl")) + "\n")
        print("## Scripted depth sweep\n\n" + scripted_table(load("scripted_depth.jsonl")) + "\n")
    if what in ("all", "agent"):
        rows = load("agent_valid.jsonl")
        print("## Agent pooled\n\n" + agent_pooled(rows) + "\n")
        print("## Agent per scenario\n\n" + agent_table(rows) + "\n")
