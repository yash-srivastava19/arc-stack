import pytest
from pathlib import Path


@pytest.fixture
def repo_root(tmp_path):
    """A temporary directory with a .git folder (simulates a git repo)."""
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def arc_root(repo_root):
    """A temporary repo with .arc/ already initialized."""
    (repo_root / ".arc").mkdir()
    return repo_root
