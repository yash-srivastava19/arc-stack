"""End-to-end tests for arc report using VCR cassette recording.

The record_cassette fixture wires up VCR to intercept HTTP calls for
replay-based testing. Since arc currently uses the gh CLI subprocess for
GitHub API calls, these tests also mock create_issue to avoid needing
live credentials. When the implementation is switched to direct HTTP,
remove the create_issue mock and the cassette will record/replay the
real API interaction.
"""
import pytest
from click.testing import CliRunner
from arc.cli import cli
from unittest.mock import patch


def test_report_creates_github_issue_e2e(record_cassette, tmp_path):
    """E2E: arc report --bug creates a GitHub issue."""
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch(
             "arc.github.create_issue",
             return_value={"number": 42, "html_url": "https://github.com/owner/repo/issues/42"},
         ):
        result = runner.invoke(cli, ["report", "--bug", "--message", "E2E test issue"])
    assert result.exit_code == 0
    assert "github.com" in result.output or "#" in result.output


def test_report_feedback_creates_issue_e2e(record_cassette, tmp_path):
    """E2E: arc report --feedback creates an issue."""
    runner = CliRunner()
    with patch("arc.git.find_repo_root", return_value=tmp_path), \
         patch(
             "arc.github.create_issue",
             return_value={"number": 43, "html_url": "https://github.com/owner/repo/issues/43"},
         ):
        result = runner.invoke(
            cli, ["report", "--feedback", "--message", "E2E feedback test"]
        )
    assert result.exit_code == 0
    assert "github.com" in result.output or "feedback" in result.output.lower()
