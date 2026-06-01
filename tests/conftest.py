import os
import re
import pytest
from pathlib import Path
import vcr as vcrlib


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
    """Mask PII from recorded cassette before committing."""
    with open(cassette_path, "r") as f:
        content = f.read()
    masked = re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "<EMAIL>", content
    )
    masked = re.sub(r"/home/[a-z0-9_/-]+", "<HOME_PATH>", masked)
    with open(cassette_path, "w") as f:
        f.write(masked)


@pytest.fixture
def record_cassette(vcr_config):
    """Record/replay GitHub API interactions with PII masking."""
    cassette_dir = "tests/cassettes"
    os.makedirs(cassette_dir, exist_ok=True)
    cassette_path = os.path.join(cassette_dir, "create_issue.yaml")
    with vcrlib.VCR(**vcr_config).use_cassette(
        cassette_path, record_mode="once"
    ) as cassette:
        yield cassette
    if os.path.exists(cassette_path):
        mask_cassette_pii(cassette_path)
