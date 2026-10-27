"""The oracle must PASS the expert git script and FAIL every deliberately broken end state."""

from run_scripted import run_once
from scenarios import SCENARIOS

N = 5
BROKEN = [
    # (name, scenario, lines appended to / replacing the expert git script)
    ("dropped commit", "S2", "+", ["git reset -q --hard b4", "git push -q -f origin b5"]),
    (
        "extra empty commit",
        "S6",
        "+",
        ["git checkout -q b3", "git commit -q --allow-empty -m dup", "git push -q -f origin b3"],
    ),
    ("stale parent", "S3", "+", ["git branch -f b3 b3@{1}", "git push -q -f origin b3"]),
    ("unpushed branch", "S2", "+", ["git push -q -f origin b2@{1}:refs/heads/b2"]),
    (
        "rebase left in progress",
        "S4",
        "=",
        ["git fetch -q", "git rebase -q --update-refs origin/main || true"],
    ),
    (
        "wrong conflict resolution",
        "S4",
        "=",
        [
            "git fetch -q",
            "git rebase -q --update-refs origin/main || true",
            "printf 'from-main\\nfrom-b3\\n' > conf.txt",
            "git add conf.txt",
            "git rebase --continue",
            "git push -q -f origin b1 b2 b3 b4 b5",
        ],
    ),
    ("partial rollback", "S5", "+", ["git branch -f b2 b1"]),
    ("deleted branch left on origin", "S7", "+", ["git push -q origin b2:refs/heads/b3"]),
    ("teammate commit overwritten", "S14", "+", ["git push -q -f origin b2~1:refs/heads/b2"]),
    ("uncommitted work lost", "S10", "+", ["git checkout -q -- f5.txt"]),
]
# Broken end states for the arc arm: the stack file disagrees with git.
BROKEN_ARC = [
    ("stale branch left in .arc", "S6", "+", ["git branch -q b1 main", "arc add b1 -q"]),
]


def main():
    ok_all = True
    for sid in SCENARIOS:
        r = run_once(SCENARIOS[sid], "git", N)
        print(f"control  {sid}: oracle_pass={r['oracle_pass']}")
        ok_all &= r["oracle_pass"]
    for arm, cases in (("git", BROKEN), ("arc", BROKEN_ARC)):
        for name, sid, mode, extra in cases:
            sc = SCENARIOS[sid]
            lines = (getattr(sc, arm)(N) + extra) if mode == "+" else extra
            r = run_once(sc, arm, N, lines=lines)
            caught = not r["oracle_pass"]
            ok_all &= caught
            print(f"broken   {name:30s} ({sid}, {arm}): caught={caught} by {r['failed']}")
    print("ORACLE SELFTEST", "PASS" if ok_all else "FAIL")


if __name__ == "__main__":
    main()
