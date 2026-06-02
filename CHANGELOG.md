# Changelog

All notable changes to arc are documented here.

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
