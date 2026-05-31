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
    args = ["gh", "pr", "create", "--base", base, "--head", branch,
            "--title", title, "--body", body]
    if draft:
        args.append("--draft")
    result = _run(args)
    url = result.stdout.strip()
    number = int(url.rstrip("/").split("/")[-1])
    return {"number": number, "url": url}


def get_pr(branch: str) -> dict | None:
    result = _run(
        ["gh", "pr", "view", branch, "--json",
         "number,url,state,baseRefName,mergedAt"],
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def update_pr_body(number: int, body: str) -> None:
    _run(["gh", "pr", "edit", str(number), "--body", body])


def mark_pr_ready(number: int) -> None:
    _run(["gh", "pr", "ready", str(number)])


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
