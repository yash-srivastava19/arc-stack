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
    """Mask PII and sensitive data from recorded cassette before committing."""
    with open(cassette_path, "r") as f:
        content = f.read()

    # Mask email addresses (example@domain.com)
    masked = re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "<EMAIL>", content
    )

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
    masked = re.sub(r'("id":\s*)\d{6,}(?=[,\n}\s]|$)', r'\1<USER_ID>', masked)

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
    with vcrlib.VCR(**vcr_config).use_cassette(
        cassette_path, record_mode="once"
    ) as cassette:
        yield cassette
    if os.path.exists(cassette_path):
        mask_cassette_pii(cassette_path)
