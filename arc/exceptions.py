from __future__ import annotations


class ArcError(Exception):
    """Base exception for all arc errors. Commands catch this at the CLI boundary."""


class NotInitializedError(ArcError):
    """arc state not found — arc init has not been run in this repo."""


class ConfigError(ArcError):
    """config.json is malformed or missing a required key."""


class BranchConflictError(ArcError):
    """A rebase conflict was encountered during restack."""


class GitError(ArcError):
    """A git subprocess call returned non-zero."""


class GitHubError(ArcError):
    """A gh CLI call or GitHub API response indicated failure."""


class HookFailedError(ArcError):
    """A lifecycle gate hook (pre-*) returned non-zero."""

    def __init__(self, event: str, exit_code: int) -> None:
        self.event = event
        self.exit_code = exit_code
        super().__init__(f"{event} hook failed (exit {exit_code})")


class StateVersionError(ArcError):
    """state.json contains an unrecognised version number."""
