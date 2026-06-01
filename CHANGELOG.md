# Changelog

All notable changes to arc (stacked pull requests) are documented in this file.

## [0.2.0] - 2026-06-01

### Added
- **Arc Report Feature** — users and agents can report bugs/feedback via `arc report --bug/--feedback`
  - Non-blocking passive hints after errors and periodically on success
  - Agent-friendly `--message` flag for non-interactive reporting
  - Issue creation with prefilled environment context (arc/Python/OS versions)
  - VCR-based E2E testing with automatic PII masking
  - Configuration via `~/.arc/config.toml` for disabling hints

- **Arc Sync Auto-Retarget Feature** — dependent PRs automatically retarget when base branches merge
  - Detect merged branches via GitHub PR status (not just remote branch absence)
  - Retarget dependent PRs to stack root automatically
  - Prune merged branches from local state to avoid re-detection
  - Integrates seamlessly into `arc sync` workflow
  - MVP limitation: non-contiguous merges retarget to root instead of nearest ancestor (documented for future optimization)

### Changed
- Improved stack management reliability with proper state handling
- Enhanced test coverage with 141 total tests (zero regressions)

### Technical Details
- Added `collect_env_context()` and `format_issue_body()` for issue creation
- Added `create_issue()` to GitHub module for issue submission
- Added `branch_exists_remote()` to git module for branch status checking
- Added `update_pr_base()` to GitHub module for PR retargeting
- Integrated passive prompting into all arc commands
- VCR cassette recording with automatic sensitive data masking

## [0.1.0] - 2026-05-31

### Added
- Initial release of arc
- Core stacked PR management: `arc new`, `arc push`, `arc submit`, `arc land`, `arc rebase`, `arc drop`
- Stack status display with `arc status`
- Git integration for branch management
- GitHub integration for PR creation and management
- Comprehensive test suite
- Documentation and CLI guide (arc.md skill)
