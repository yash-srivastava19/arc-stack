"""Print the markdown tables used on the docs Benchmarks page from bench/results/.

python3 report.py               # scripted results for the current arc
python3 report.py --history     # pass/fail per arc version from results/correctness-*.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verdict(arm: dict) -> str:
    if arm.get("unsupported"):
        return "no command"
    return "pass" if arm["oracle_pass"] else "**fail**"


def timing(arm: dict) -> str:
    if arm.get("unsupported") or arm["median_ms"] is None:
        return "–"
    return f"{arm['median_ms']:.0f} ({arm['min_ms']:.0f}–{arm['max_ms']:.0f})"


def commands(arm: dict) -> str:
    return "–" if arm.get("unsupported") else str(arm["cmds"])


def processes(arm: dict) -> str:
    return "–" if arm.get("unsupported") else str(arm["git_procs"])


def scenario_table(rows: list[dict]) -> str:
    out = [
        "| Scenario | Correct: arc | Correct: git | Commands: arc | Commands: git "
        "| Time ms: arc | Time ms: git | git processes: arc | git processes: git |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        a, g = r["arc"], r["git"]
        out.append(
            f"| {r['scenario']} {r['title']} | {verdict(a)} | {verdict(g)} | {commands(a)} | "
            f"{commands(g)} | {timing(a)} | {timing(g)} | {processes(a)} | {processes(g)} |"
        )
    return "\n".join(out)


def depth_table(rows: list[dict]) -> str:
    out = [
        "| Scenario | Branches | Time ms: arc | Time ms: git | git processes: arc | git processes: git |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (int(r["scenario"][1:].rstrip("abc")), r["n"])):
        a, g = r["arc"], r["git"]
        out.append(
            f"| {r['scenario']} | {r['n']} | {timing(a)} | {timing(g)} | {processes(a)} | {processes(g)} |"
        )
    return "\n".join(out)


def history_table() -> str:
    runs = {
        p.stem.removeprefix("correctness-"): {r["scenario"]: r for r in load(p)}
        for p in sorted(RESULTS.glob("correctness-*.jsonl"))
    }
    versions = list(runs)
    scenarios = list(next(iter(runs.values())))
    out = [
        "| Scenario | " + " | ".join(f"arc {v}" for v in versions) + " |",
        "|---|" + "---|" * len(versions),
    ]
    for sid in scenarios:
        title = runs[versions[0]][sid]["title"]
        cells = [verdict(runs[v][sid]["arc"]) if sid in runs[v] else "–" for v in versions]
        out.append(f"| {sid} {title} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def scenario_sections(n: int = 5) -> str:
    """One section per scenario: the situation in words, then each arm's exact commands."""
    from scenarios import DONE, SCENARIOS

    out = []
    for sc in SCENARIOS.values():
        situation = sc.prompt(n).removesuffix(DONE)
        for preamble_end in ("except stack branches. ", "stands in for GitHub. "):
            situation = situation.split(preamble_end)[-1]
        out += [f"### {sc.id}: {sc.title}", "", situation, ""]
        for arm in ("arc", "git"):
            lines = getattr(sc, arm)
            out += [f"**{arm}**", ""]
            out += (
                ["```bash", *lines(n), "```", ""]
                if lines
                else ["arc has no command for this. Use the git sequence.", ""]
            )
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--scenarios", action="store_true")
    ap.add_argument("--version", help="arc version whose results to print, such as 0.8.4")
    a = ap.parse_args()
    if a.history:
        print(history_table())
        return
    if a.scenarios:
        print(scenario_sections())
        return
    main_rows = load(RESULTS / f"scripted-{a.version}.jsonl")
    v = main_rows[0]["versions"]
    print(
        f"{v['arc']}, {v['git']}, Python {v['python']}. Timed runs per arm: {main_rows[0]['runs']}.\n"
    )
    print(scenario_table(main_rows))
    depth = RESULTS / f"scripted-{a.version}-depth.jsonl"
    if depth.exists():
        print()
        print(depth_table(load(depth)))


if __name__ == "__main__":
    main()
