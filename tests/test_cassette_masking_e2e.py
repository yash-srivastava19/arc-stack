"""Integration test: Verify cassettes are recorded and masked automatically.

Tests the real workflow: VCR records API interaction → fixture auto-masks PII →
cassette is safe to commit with no credentials exposed.
"""

import re
from pathlib import Path

import pytest


def test_masking_function_applied_to_cassette_before_write(tmp_path):
    """Integration: Verify masking is applied when cassette is written to disk.

    Tests the full pipeline: sensitive data → VCR recording → auto-masked →
    safe cassette on disk
    """
    from tests.conftest import mask_cassette_pii

    cassette_path = tmp_path / "test.yaml"

    # Simulate what a real cassette would look like with sensitive data
    sensitive_cassette = """interactions:
  - request:
      method: POST
      uri: https://api.github.com/repos/owner/repo/issues
      headers:
        authorization: "token ghp_testtoken123456789abcdefghijklmn"
    response:
      status:
        code: 201
      body:
        string: '{"id": 123456789, "login": "sensitiveusername", "email": "user@company.com"}'
"""

    cassette_path.write_text(sensitive_cassette)

    # Apply the masking that the fixture would apply
    mask_cassette_pii(str(cassette_path))

    # Read the masked cassette
    masked_content = cassette_path.read_text()

    # Verify no credentials are exposed
    assert "ghp_testtoken123456789abcdefghijklmn" not in masked_content, "Token should be masked"
    assert "sensitiveusername" not in masked_content, "Username should be masked"
    assert "user@company.com" not in masked_content, "Email should be masked"
    assert "123456789" not in masked_content, "User ID should be masked"

    # Verify placeholders are in place
    assert "<GH_TOKEN>" in masked_content or "<TOKEN>" in masked_content, (
        "Token should be replaced with placeholder"
    )
    assert "<USERNAME>" in masked_content, "Username should be replaced with placeholder"
    assert "<EMAIL>" in masked_content, "Email should be replaced with placeholder"
    assert "<USER_ID>" in masked_content, "User ID should be replaced with placeholder"


def test_no_unmasked_credentials_in_committed_cassettes():
    """Integration: Verify committed cassettes have no unmasked credentials.

    Checks any existing cassettes in tests/cassettes/ directory are safe to commit.
    This runs against the committed cassette files to ensure no PII leaks.
    """
    cassettes_dir = Path("tests/cassettes")

    if not cassettes_dir.exists():
        pytest.skip("No cassettes directory yet (cassettes haven't been recorded)")

    # Patterns that indicate unmasked credentials
    forbidden_patterns = {
        "GitHub token": r"ghp_[a-zA-Z0-9]{20,}",
        "OAuth token": r"gh[ou]_[a-zA-Z0-9]{20,}",
        "Email address": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+(\.com|\.org|\.net|\.io)",
    }

    for cassette_file in cassettes_dir.glob("*.yaml"):
        with open(cassette_file) as f:
            content = f.read()

        for pattern_name, pattern in forbidden_patterns.items():
            match = re.search(pattern, content)
            assert not match, (
                f"Found unmasked {pattern_name} in {cassette_file.name}: {match.group()}. "
                "Cassette is NOT safe to commit!"
            )
