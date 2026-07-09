from unittest.mock import patch

from arc import tip


def _state(branches):
    return {"version": 1, "base": "main", "prefix": None, "branches": branches, "metadata": {}}


def test_sync_tip_branch_noop_when_missing():
    data = _state([{"name": "feat/a", "pr_number": None, "revision": 0}])
    with (
        patch("arc.tip.git.branch_exists", return_value=False) as mock_exists,
        patch("arc.tip.git.force_update_branch") as mock_force,
    ):
        tip.sync_tip_branch(data)
    mock_exists.assert_called_once_with(tip.TIP_BRANCH)
    mock_force.assert_not_called()


def test_sync_tip_branch_moves_to_top_when_present():
    data = _state(
        [
            {"name": "feat/a", "pr_number": None, "revision": 0},
            {"name": "feat/b", "pr_number": None, "revision": 0},
        ]
    )
    with (
        patch("arc.tip.git.branch_exists", return_value=True),
        patch("arc.tip.git.get_sha", return_value="abc123") as mock_sha,
        patch("arc.tip.git.force_update_branch") as mock_force,
    ):
        tip.sync_tip_branch(data)
    mock_sha.assert_called_once_with("feat/b")
    mock_force.assert_called_once_with(tip.TIP_BRANCH, "abc123")


def test_sync_tip_branch_noop_when_stack_empty():
    data = _state([])
    with (
        patch("arc.tip.git.branch_exists", return_value=True),
        patch("arc.tip.git.force_update_branch") as mock_force,
    ):
        tip.sync_tip_branch(data)
    mock_force.assert_not_called()
