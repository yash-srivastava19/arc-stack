# Changelog

All notable changes to arc are documented here.

---

## [0.3.1] — 2026-06-07

### Added
- `arc completions bash|zsh|fish` — generate shell completion scripts
- `arc upgrade` — upgrade arc via uv/pip with one command; background version hint when newer version available
- `arc config get/set/list` — read and write config values without editing TOML
- `arc schema status|submit|analyze` — print JSON Schema for command `--json` output
- `--no-input` global flag (`ARC_NO_INPUT`) — fail fast instead of prompting; safe for agents and CI
- `--verbose / -v` global flag — print git and gh commands to stderr as they run
- `arc status` shows a dim hint when any branch has a merged PR (prompts `arc sync`)
- `arc sync` auto-prunes merged branches from stack state — stale branches no longer linger after merge

### Fixed
- `arc sync` no longer crashes when deleting squash-merged local branches (used `-D` force delete)

---

## [0.3.0] — 2026-06-07

### Added
- **Conflict Prediction** — `arc sync` warns before rebasing when adjacent branches modify the same files
- **Stack Intelligence** (`arc stack analyze`) — shows critical path, safe-to-land branches, and blockers with live GitHub PR status
- **Squash-Merge Recovery** — `arc sync` detects squash-merged branches and removes them from the stack automatically
- **`arc restack [<branch>]`** — restack a single branch onto its parent without full sync
- **Async-First Hints** — `arc submit` hints when a parent branch is approved and in merge queue
- **`arc doctor`** — self-diagnostic: checks git, gh, auth, and stack state
- **JSON error output** — `--json` commands emit `{"ok": false, "error": "...", "hint": "..."}` on failure
- **Auto-TTY detection** — JSON output automatic when stdout is piped (no `--json` flag needed)
- **Structured error messages** — all errors include a `hint:` line with the exact fix

### Improved
- First-run experience: missing `arc init` now suggests the fix instead of a cryptic error
- CI: ruff + mypy lint job, 80% coverage gate, real git integration test fixtures

---

## [0.2.1] — 2026-06-02

### Fixed
- **`arc submit --open` blocker:** `mark_pr_ready` now idempotent, handles already-ready PRs without crashing
  - Root cause: PR created as ready when `--open` used; subsequent runs tried to mark ready again
  - Solution: Check PR draft status before calling `gh pr ready`
  - Impact: Users can now reliably use `arc submit --open --skip-hooks` on repeated runs

### Improved
- **VCR cassette security:** Expanded PII masking for recorded API interactions
  - Now masks: GitHub tokens (ghp_, gho_, ghu_), login names, user IDs, node IDs, OAuth codes
  - Prevents accidental credential exposure when committing test cassettes
  - Infrastructure ready for E2E test cassette recording

### Tests
- Added 5 unit tests for masking patterns
- Added 2 integration tests for full cassette recording workflow
- All 163 tests passing

---

## [0.2.0] — 2026-05-31

### Added
- **`arc report` command** — Report bugs and feedback directly from CLI
  - `arc report --bug [--message TEXT]` — File bug reports with environment context
  - `arc report --feedback [--message TEXT]` — Share feature ideas
  - Interactive (TTY) and non-interactive (agent) modes
  - Automatic environment context collection (arc version, Python, OS)

- **Auto-retarget on PR merge** — Stacks automatically rebase when parent PRs merge
  - `arc sync` detects merged PRs and retargets dependent branches
  - Eliminates manual retarget step
  - Keeps distributed teams unblocked

### Improved
- Simplified CI: Single Python version (3.11) instead of 3.12, 3.13
- Release workflow: GitHub auto-generates release notes instead of manual changelog

### Tests
- Added E2E tests for `arc report` command
- VCR cassette recording infrastructure ready

---

## [0.1.0] — 2026-05-15

### Added
- Core `arc` CLI for stacked PR management
- Commands: `new`, `push`, `submit`, `sync`, `land`, `drop`, `status`, `checkout`, navigation (`up`, `down`, `top`, `bottom`)
- Stack state management in `.arc/state.json`
- Configuration in `.arc/config.json`
- GitHub PR creation and management
- Error hints and periodic feedback (1-in-5 random tips)
- Pre-submit hooks support

### Features
- Linear stack of branches (one-to-one with PRs)
- Auto-retarget on merge (v0.2.0+)
- Cascade rebase on parent changes
- Dry-run support for safe preview
- JSON output for scripting

---

## Versioning

Arc follows semantic versioning:
- **Patch (0.2.x):** Bug fixes, test improvements
- **Minor (0.x.0):** New features, improvements
- **Major (x.0.0):** Breaking changes (rare)
