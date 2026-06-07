from __future__ import annotations

import json
import subprocess


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


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
    """Update a PR's base branch.

    Args:
        pr_number: The PR number to update
        new_base: The new base branch name

    Returns:
        True if the update succeeded, False otherwise
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "edit", str(pr_number), "--base", new_base],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


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
    return json.loads(result.stdout).get("state") == "MERGED"


def get_merge_commit_sha(number: int) -> str | None:
    result = _run(["gh", "pr", "view", str(number), "--json", "mergeCommit"], check=False)
    if result.returncode != 0:
        return None
    commit = json.loads(result.stdout).get("mergeCommit")
    return commit.get("oid") if commit else None


def create_issue(title: str, body: str) -> dict | None:
    """Create a GitHub issue via gh CLI.

    Args:
        title: The issue title
        body: The issue body (markdown)

    Returns:
        dict with "number" and "html_url" keys, or None on failure
    """
    try:
        result = _run(
            ["gh", "issue", "create", "--title", title, "--body", body],
            check=False,
        )

        if result.returncode != 0:
            return None

        # gh outputs the issue URL: https://github.com/owner/repo/issues/42
        url = result.stdout.strip()

        # Extract issue number from URL
        issue_number = int(url.split("/")[-1])

        return {
            "number": issue_number,
            "html_url": url,
        }
    except Exception:
        return None
