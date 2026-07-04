from __future__ import annotations

import json
import subprocess

from arc.const import CI_ERROR, CI_FAILURE, CI_SUCCESS, PR_MERGED, REVIEW_APPROVED
from arc.exceptions import GitHubError

_VERBOSE = False  # module-level flag set by cli


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    if _VERBOSE:
        import sys as _sys

        print(f"  gh {' '.join(str(a) for a in args[1:])}", file=_sys.stderr)
    try:
        return subprocess.run(args, capture_output=True, text=True, check=check)
    except subprocess.CalledProcessError as e:
        raise GitHubError(e.stderr.strip() or f"gh {args[1]} exited {e.returncode}") from e


def is_installed() -> bool:
    return _run(["gh", "--version"], check=False).returncode == 0


def is_authenticated() -> bool:
    return _run(["gh", "auth", "status"], check=False).returncode == 0


def create_pr(branch: str, base: str, title: str, body: str, draft: bool = True) -> dict:
    args = [
        "gh",
        "pr",
        "create",
        "--base",
        base,
        "--head",
        branch,
        "--title",
        title,
        "--body",
        body,
    ]
    if draft:
        args.append("--draft")
    result = _run(args)
    url = result.stdout.strip()
    number = int(url.rstrip("/").split("/")[-1])
    return {"number": number, "url": url}


def get_pr(branch: str) -> dict | None:
    result = _run(
        ["gh", "pr", "view", branch, "--json", "number,url,state,baseRefName,mergedAt,isDraft"],
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def update_pr_body(number: int, body: str) -> None:
    _run(["gh", "pr", "edit", str(number), "--body", body])


def update_pr_base(pr_number: int, new_base: str) -> bool:
    result = _run(["gh", "pr", "edit", str(pr_number), "--base", new_base], check=False)
    return result.returncode == 0


def mark_pr_ready(number: int) -> None:
    result = _run(
        ["gh", "pr", "view", str(number), "--json", "isDraft"],
        check=False,
    )
    if result.returncode == 0:
        pr = json.loads(result.stdout)
        if not pr.get("isDraft", True):
            return
    _run(["gh", "pr", "ready", str(number)], check=False)


def pr_is_merged(number: int) -> bool:
    result = _run(["gh", "pr", "view", str(number), "--json", "state"], check=False)
    if result.returncode != 0:
        return False
    return json.loads(result.stdout).get("state") == PR_MERGED


def get_pr_state(number: int) -> str | None:
    """Return PR state: 'OPEN', 'CLOSED', or 'MERGED'. None if not found."""
    result = _run(["gh", "pr", "view", str(number), "--json", "state"], check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout).get("state")


def reopen_pr(number: int) -> bool:
    """Reopen a closed PR. Returns True on success."""
    result = _run(["gh", "pr", "reopen", str(number)], check=False)
    return result.returncode == 0


def get_merge_commit_sha(number: int) -> str | None:
    result = _run(["gh", "pr", "view", str(number), "--json", "mergeCommit"], check=False)
    if result.returncode != 0:
        return None
    commit = json.loads(result.stdout).get("mergeCommit")
    return commit.get("oid") if commit else None


def get_pr_status(pr_number: int) -> dict:
    result = _run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "isDraft,reviewDecision,statusCheckRollup,mergeQueueEntry",
        ],
        check=False,
    )
    if result.returncode != 0:
        return {"approved": False, "ci_passing": None, "draft": False, "in_merge_queue": False}
    data = json.loads(result.stdout)
    checks = data.get("statusCheckRollup") or []
    if not checks:
        ci_passing = None
    elif all(c.get("conclusion") == CI_SUCCESS for c in checks):
        ci_passing = True
    elif any(c.get("conclusion") in (CI_FAILURE, CI_ERROR) for c in checks):
        ci_passing = False
    else:
        ci_passing = None
    return {
        "approved": data.get("reviewDecision") == REVIEW_APPROVED,
        "ci_passing": ci_passing,
        "draft": data.get("isDraft", False),
        "in_merge_queue": bool(data.get("mergeQueueEntry")),
    }


def create_issue(title: str, body: str) -> dict | None:
    try:
        result = _run(["gh", "issue", "create", "--title", title, "--body", body], check=False)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    try:
        return {"number": int(url.split("/")[-1]), "html_url": url}
    except (ValueError, IndexError):
        return None
