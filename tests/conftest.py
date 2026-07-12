import os
import re
import subprocess as _sp

import pytest
import vcr as vcrlib


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch):
    """Strip GIT_* env vars inherited from the pre-commit hook.

    When pytest runs inside a git pre-commit hook, git sets GIT_DIR,
    GIT_WORK_TREE, and GIT_INDEX_FILE. Every subprocess.run call inherits
    these, causing git commands to operate on the hook's repo instead of
    whatever repo the test is targeting. Clearing them restores normal
    git behaviour (discovery from cwd) for all tests.
    """
    for key in list(os.environ.keys()):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)


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


@pytest.fixture
def vcr_config():
    return {
        "filter_headers": [
            "authorization",
            "x-github-token",
            "x-oauth-token",
            "cookie",
        ],
        "filter_post_data_parameters": ["token", "access_token"],
        "decode_compressed_response": True,
    }


def mask_cassette_pii(cassette_path):
    """Mask PII and sensitive data from recorded cassette before committing."""
    with open(cassette_path) as f:
        content = f.read()

    # Mask email addresses (example@domain.com)
    masked = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "<EMAIL>", content)

    # Mask home directory paths (/home/username/...)
    masked = re.sub(r"/home/[a-z0-9_/-]+", "<HOME_PATH>", masked)

    # Mask GitHub personal access tokens (ghp_... format, 20+ chars)
    masked = re.sub(r"ghp_[a-zA-Z0-9]{20,}", "<GH_TOKEN>", masked)

    # Mask OAuth tokens (gho_... or ghu_... format, 20+ chars)
    masked = re.sub(r"gh[ou]_[a-zA-Z0-9]{20,}", "<GH_OAUTH_TOKEN>", masked)

    # Mask generic tokens in JSON values ("token": "...") and headers
    masked = re.sub(r'("token":\s*")[^"]*"', r'\1<TOKEN>"', masked)
    masked = re.sub(r'("access_token":\s*")[^"]*"', r'\1<TOKEN>"', masked)

    # Mask user login names that appear in GitHub responses
    # Pattern: "login": "username" - mask common bot/user names to generic form
    masked = re.sub(r'("login":\s*")[a-zA-Z0-9._-]+"', r'\1<USERNAME>"', masked)

    # Mask user IDs (numeric user ids in "id": 123456 with optional trailing chars)
    masked = re.sub(r'("id":\s*)\d{6,}(?=[,\n}\s]|$)', r"\1<USER_ID>", masked)

    # Mask repository node IDs (long base64-like strings in "node_id")
    masked = re.sub(r'("node_id":\s*")[A-Za-z0-9+/=]+"', r'\1<NODE_ID>"', masked)

    # Mask OAuth authorization codes
    masked = re.sub(r'("code":\s*")[a-zA-Z0-9]*"', r'\1<AUTH_CODE>"', masked)

    with open(cassette_path, "w") as f:
        f.write(masked)


@pytest.fixture
def record_cassette(vcr_config):
    """Record/replay GitHub API interactions with PII masking."""
    cassette_dir = "tests/cassettes"
    os.makedirs(cassette_dir, exist_ok=True)
    cassette_path = os.path.join(cassette_dir, "create_issue.yaml")
    with vcrlib.VCR(**vcr_config).use_cassette(cassette_path, record_mode="once") as cassette:
        yield cassette
    if os.path.exists(cassette_path):
        mask_cassette_pii(cassette_path)


@pytest.fixture
def git_repo(tmp_path):
    """A real local git repo with a bare remote. Suitable for testing arc git operations."""
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"

    _sp.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    _sp.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    _sp.run(
        ["git", "config", "user.email", "test@arc.dev"], cwd=work, check=True, capture_output=True
    )
    _sp.run(["git", "config", "user.name", "Arc Test"], cwd=work, check=True, capture_output=True)
    # git 2.28+ already defaults to 'main' on empty clones; ignore the error
    # when the branch already exists.
    _sp.run(["git", "checkout", "-b", "main"], cwd=work, capture_output=True)

    (work / "README.md").write_text("init")
    _sp.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    _sp.run(["git", "commit", "-m", "init"], cwd=work, check=True, capture_output=True)
    _sp.run(["git", "push", "-u", "origin", "main"], cwd=work, check=True, capture_output=True)

    return work


@pytest.fixture
def arc_stack(git_repo):
    """A git_repo with arc initialized (real .arc/state.json)."""
    from arc import state as st

    root = git_repo
    (root / ".arc").mkdir(exist_ok=True)
    data = {
        "version": 1,
        "base": "main",
        "prefix": None,
        "branches": [],
        "metadata": {},
    }
    st.save(root, data)
    return root


@pytest.fixture
def stacked_repo(arc_stack):
    """A real arc stack with 3 branches: feat/auth → feat/api → feat/tests.
    Checked out on feat/auth. Each branch has one unique file."""
    import subprocess as sp

    root = arc_stack
    from arc import state as st

    for branch, filename, content in [
        ("feat/auth", "auth.py", "def auth(): pass\n"),
        ("feat/api", "api.py", "def api(): pass\n"),
        ("feat/tests", "tests.py", "def test_api(): pass\n"),
    ]:
        sp.run(["git", "checkout", "-b", branch], cwd=root, check=True, capture_output=True)
        (root / filename).write_text(content)
        sp.run(["git", "add", filename], cwd=root, check=True, capture_output=True)
        sp.run(
            ["git", "commit", "-m", f"add {filename}"], cwd=root, check=True, capture_output=True
        )

    sp.run(["git", "checkout", "feat/auth"], cwd=root, check=True, capture_output=True)

    data = st.init_state(base="main")
    for b in ("feat/auth", "feat/api", "feat/tests"):
        data = st.add_branch(data, b)
    st.save(root, data)
    return root
