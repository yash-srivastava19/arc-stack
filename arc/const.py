"""Named constants for external protocol values."""

# GitHub PR states (returned by gh pr view --json state)
PR_OPEN = "OPEN"
PR_CLOSED = "CLOSED"
PR_MERGED = "MERGED"

# GitHub review outcomes
REVIEW_APPROVED = "APPROVED"

# CI check conclusions
CI_SUCCESS = "SUCCESS"
CI_FAILURE = "FAILURE"
CI_ERROR = "ERROR"

# Fallback trunk name used when no remote/reflog info is available
DEFAULT_BASE = "main"
