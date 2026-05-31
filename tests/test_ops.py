from arc import ops, state as st


def _make_state(branches=None, base="main", prefix=None):
    s = st.init_state(base=base, prefix=prefix)
    for name in (branches or []):
        s = st.add_branch(s, name)
    return s


def test_parent_branch_returns_base_for_first():
    s = _make_state(["feat/auth", "feat/api"])
    assert ops.parent_branch(s, "feat/auth") == "main"


def test_parent_branch_returns_previous_for_rest():
    s = _make_state(["feat/auth", "feat/api"])
    assert ops.parent_branch(s, "feat/api") == "feat/auth"


def test_parent_branch_raises_for_unknown():
    s = _make_state(["feat/auth"])
    import pytest
    with pytest.raises(ValueError, match="not in stack"):
        ops.parent_branch(s, "feat/unknown")


def test_upstack_branches():
    s = _make_state(["feat/auth", "feat/api", "feat/ui"])
    assert ops.upstack_branches(s, "feat/auth") == ["feat/api", "feat/ui"]


def test_upstack_branches_empty_for_top():
    s = _make_state(["feat/auth", "feat/api"])
    assert ops.upstack_branches(s, "feat/api") == []


def test_downstack_branches():
    s = _make_state(["feat/auth", "feat/api", "feat/ui"])
    assert ops.downstack_branches(s, "feat/api") == ["feat/auth", "feat/api"]


def test_rebase_plan_empty_stack():
    s = _make_state()
    assert ops.rebase_plan(s) == []


def test_rebase_plan_single_branch():
    s = _make_state(["feat/auth"])
    plan = ops.rebase_plan(s)
    assert plan == [{"branch": "feat/auth", "onto": "main"}]


def test_rebase_plan_multi_branch():
    s = _make_state(["feat/auth", "feat/api", "feat/ui"])
    plan = ops.rebase_plan(s)
    assert plan == [
        {"branch": "feat/auth", "onto": "main"},
        {"branch": "feat/api", "onto": "feat/auth"},
        {"branch": "feat/ui", "onto": "feat/api"},
    ]


def test_rebase_plan_skips_merged():
    s = _make_state(["feat/auth", "feat/api", "feat/ui"])
    plan = ops.rebase_plan(s, merged={"feat/auth"})
    assert plan == [
        {"branch": "feat/api", "onto": "main"},
        {"branch": "feat/ui", "onto": "feat/api"},
    ]


def test_stack_status_structure():
    s = _make_state(["feat/auth", "feat/api"])
    s = st.update_branch(s, "feat/auth", pr_number=42, revision=2)
    status = ops.stack_status(
        state=s,
        current_branch="feat/api",
        commit_counts={"feat/auth": 2, "feat/api": 3},
        pr_info={"feat/auth": {"pr_url": "https://gh/42", "pr_state": "OPEN", "is_merged": False}},
        needs_rebase_flags={"feat/auth": False, "feat/api": True},
    )
    assert status["base"] == "main"
    assert status["current_branch"] == "feat/api"
    assert len(status["branches"]) == 2
    b0 = status["branches"][0]
    assert b0["name"] == "feat/auth"
    assert b0["index"] == 1
    assert b0["pr_number"] == 42
    assert b0["revision"] == 2
    assert b0["needs_rebase"] is False
    assert b0["is_current"] is False
    b1 = status["branches"][1]
    assert b1["needs_rebase"] is True
    assert b1["is_current"] is True
    assert b1["pr_number"] is None
    assert b1["pr_url"] is None


def test_build_pr_body_with_body():
    entries = [
        {"name": "feat/auth", "pr_number": 42, "is_current": True},
        {"name": "feat/api", "pr_number": None, "is_current": False},
    ]
    body = ops.build_pr_body(commit_body="Some details.", stack_entries=entries, base="main")
    assert "Some details." in body
    assert "Stack (base: main):" in body
    assert "1. feat/auth - PR #42 [this PR]" in body
    assert "2. feat/api - no PR" in body


def test_build_pr_body_empty_commit_body():
    entries = [{"name": "feat/auth", "pr_number": None, "is_current": True}]
    body = ops.build_pr_body(commit_body="", stack_entries=entries, base="main")
    assert body.startswith("---")


def test_build_pr_title_single_commit():
    assert ops.build_pr_title("Add auth middleware", "feat/auth") == "Add auth middleware"


def test_build_pr_title_humanizes_branch_when_no_subject():
    assert ops.build_pr_title("", "feat/auth-middleware") == "Feat auth middleware"


def test_next_step_hint_needs_rebase():
    status = {
        "branches": [
            {"name": "feat/api", "needs_rebase": True, "pr_number": None, "revision": 0}
        ]
    }
    hint = ops.next_step_hint(status)
    assert "arc sync" in hint


def test_next_step_hint_unpushed():
    status = {
        "branches": [
            {"name": "feat/auth", "needs_rebase": False, "pr_number": None, "revision": 0}
        ]
    }
    hint = ops.next_step_hint(status)
    assert "arc push" in hint


def test_next_step_hint_no_prs():
    status = {
        "branches": [
            {"name": "feat/auth", "needs_rebase": False, "pr_number": None, "revision": 1}
        ]
    }
    hint = ops.next_step_hint(status)
    assert "arc submit" in hint


def test_next_step_hint_all_good():
    status = {
        "branches": [
            {"name": "feat/auth", "needs_rebase": False, "pr_number": 42, "revision": 1}
        ]
    }
    hint = ops.next_step_hint(status)
    assert hint == ""


def test_branch_at_index():
    s = _make_state(["feat/auth", "feat/api"])
    assert ops.branch_at_index(s, 1) == "feat/auth"
    assert ops.branch_at_index(s, 2) == "feat/api"
    assert ops.branch_at_index(s, 99) is None


def test_validate_stack_valid():
    s = _make_state(["feat/auth"])
    assert ops.validate_stack(s) == []


def test_validate_stack_no_base():
    s = {"version": 1, "base": "", "branches": [], "metadata": {}}
    errors = ops.validate_stack(s)
    assert any("base" in e for e in errors)
