# Submitting

Push branches to remote and open pull requests.

---

## Push

```bash
arc push
```

Force-pushes all stack branches to remote in order (bottom to top). Increments each branch's revision counter. arc skips branches with no commits beyond their base.

```bash
arc push -n    # dry run: show what would be pushed without pushing
arc push -q    # quiet: suppress output
```

arc pushes atomically in stack order so reviewers never see a partially-updated stack.

---

## Submit

```bash
arc submit
```

For each branch in the stack:
- If no PR exists: creates a draft PR targeting the branch below it (or `main` for the bottommost)
- If a PR exists: updates the PR description and base if the stack shape changed

All PRs get a stack map in the description footer:

```
---
Stack (base: main):
  1. feat/auth - PR #42 [this PR]
  2. feat/api  - PR #43
  3. feat/ui   - PR #44
```

### Flags

| Flag | Effect |
|------|--------|
| `--draft` | Force all PRs to draft mode |
| `--open` | Mark all draft PRs as ready for review |
| `--skip-hooks` | Skip `pre-submit` hooks |
| `-n` | Dry run |
| `-q` | Quiet |

### Typical workflow

```bash
arc push
arc submit --draft      # open PRs for initial review setup

# after feedback, iterate:
arc push && arc submit  # refresh PR descriptions and bases
```

When all branches are ready:

```bash
arc submit --open
```

---

## PR titles and bodies

`arc submit` uses the first line of each branch's HEAD commit as the PR title. The body is populated with the commit message (everything after the first line), then the stack map footer is appended.

To update a PR title or body manually, edit it on GitHub — `arc submit` will not overwrite manual edits to the title or body content (it only updates the stack map footer).

---

## Hooks

`arc submit` fires `pre-submit` and `post-submit` hooks. Configure a pre-submit gate in `.arc/config.json`:

```json
{
  "hooks": {
    "pre-submit": ["npm run lint", "npm test"]
  }
}
```

Or as an executable file in `.arc/hooks/pre-submit`. See [Hooks](hooks.md) for details.
