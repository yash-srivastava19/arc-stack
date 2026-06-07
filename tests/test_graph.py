from arc.graph import analyze_stack


def make_statuses(branches, approved, ci_ok):
    return {
        b: {
            "approved": b in approved,
            "ci_passing": True if b in ci_ok else None,
            "draft": False,
            "in_merge_queue": False,
        }
        for b in branches
    }


def test_analyze_stack_marks_ready_branch():
    data = {"base": "main", "branches": [{"name": "feat/a", "pr_number": 1, "revision": 1}]}
    analysis = analyze_stack(data, make_statuses(["feat/a"], ["feat/a"], ["feat/a"]))
    assert "feat/a" in analysis.safe_to_land


def test_analyze_stack_marks_blocked_branch():
    data = {
        "base": "main",
        "branches": [
            {"name": "feat/a", "pr_number": 1, "revision": 1},
            {"name": "feat/b", "pr_number": 2, "revision": 1},
        ],
    }
    analysis = analyze_stack(
        data, make_statuses(["feat/a", "feat/b"], ["feat/b"], ["feat/a", "feat/b"])
    )
    assert "feat/b" in analysis.blocked
    assert "feat/a" in analysis.blocked["feat/b"]


def test_analyze_stack_critical_path_is_full_chain():
    data = {
        "base": "main",
        "branches": [
            {"name": "feat/a", "pr_number": 1, "revision": 1},
            {"name": "feat/b", "pr_number": 2, "revision": 1},
            {"name": "feat/c", "pr_number": 3, "revision": 1},
        ],
    }
    analysis = analyze_stack(
        data,
        make_statuses(
            ["feat/a", "feat/b", "feat/c"],
            ["feat/a", "feat/b", "feat/c"],
            ["feat/a", "feat/b", "feat/c"],
        ),
    )
    assert analysis.critical_path == ["feat/a", "feat/b", "feat/c"]
