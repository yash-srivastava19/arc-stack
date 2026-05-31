from unittest.mock import patch
from click.testing import CliRunner
from arc.cli import cli


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "arc" in result.output.lower()


def test_setup_success():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True), \
         patch("arc.git.set_config"):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 0
    assert "Ready" in result.output


def test_setup_quiet_suppresses_hints():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True), \
         patch("arc.git.set_config"):
        result = runner.invoke(cli, ["setup", "-q"])
    assert result.exit_code == 0


def test_setup_fails_when_git_not_installed():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=False), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=True):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "git" in result.output


def test_setup_fails_when_gh_not_installed():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=False):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "gh" in result.output


def test_setup_fails_when_not_authenticated():
    runner = CliRunner()
    with patch("arc.git.is_installed", return_value=True), \
         patch("arc.github.is_installed", return_value=True), \
         patch("arc.github.is_authenticated", return_value=False):
        result = runner.invoke(cli, ["setup"])
    assert result.exit_code == 6
    assert "gh auth login" in result.output
