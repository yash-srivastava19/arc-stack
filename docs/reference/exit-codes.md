# Exit codes

arc uses structured exit codes so scripts can react to specific conditions without parsing stderr.

| Code | Name | Meaning | What to do |
|------|------|---------|------------|
| `0` | Success | Command completed successfully | |
| `1` | Error | General error | Read stderr for details |
| `2` | Not initialized | No stack found in the current repo | Run `arc init` |
| `3` | Rebase conflict | A branch could not be rebased cleanly | Resolve conflict, then `arc rebase --continue` or `arc rebase --abort` |
| `4` | GitHub API failure | `gh` returned an error | Check `gh auth status`, verify network, retry |
| `5` | Invalid arguments | Bad flag combination or missing required argument | Read stderr for the specific error |
| `6` | Setup check failed | Environment not configured | Run `arc setup` |
| `7` | Pre-hook failed | A `pre-*` hook returned non-zero | Fix the check, or pass `--skip-hooks` |

---

## Using exit codes in scripts

```bash
arc sync
status=$?

case $status in
  0) echo "Sync complete" ;;
  3) echo "Conflict — resolve and run arc rebase --continue" ;;
  4) echo "GitHub API error — check gh auth status" ;;
  *) echo "Unexpected error $status" >&2; exit $status ;;
esac
```

```bash
# Abort the pipeline if arc is not initialized
arc status >/dev/null 2>&1 || { echo "Run arc init first"; exit 1; }
```

---

## Notes

- Exit code `3` (conflict) is not an error — it is the expected outcome when a rebase hits conflicting changes. Scripts should branch on it, not treat it as a failure.
- `arc rebase --continue` and `arc rebase --abort` both exit `0` on success.
- `--dry-run` always exits `0` if the plan was computed successfully, regardless of what the plan contains.
