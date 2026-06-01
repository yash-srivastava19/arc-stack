# Arc Roadmap — Features & Ideas to Explore

This document tracks features, improvements, and ideas for future releases of arc. We append to this as we discover needs and opportunities.

**Guidelines:**
- Features listed here align with [clig.dev](https://clig.dev/) best practices
- Prioritized by user impact, not implementation complexity
- Move to implementation plan (`docs/superpowers/plans/`) once designed
- Completed features move to `CHANGELOG.md`

---

## v0.3.0 — Intelligence & Visibility

### Core Features (High Priority)

#### 1. **Conflict Prediction** (Feature 3)
**Problem:** Users discover merge conflicts only *after* merging, blocking upstack PRs.

**Solution:** `arc sync` predicts conflicts before they happen.

```bash
$ arc sync
Checking for conflicts...
⚠️  feature-2 will conflict with feature-1
   Both files edit src/api.py:45-67
   Suggest reorder: land feature-1 first, then rebase feature-2
```

**CLI Alignment (clig.dev):**
- ✅ Human-first: warns before problems
- ✅ Conversational: suggests actions
- ✅ Robust: prevents silent failures

**Implementation notes:**
- Simulate merge (git merge-base, check diff hunks)
- Run before rebase, report problems
- Suggest: land order, cherry-pick, manual resolution

---

#### 2. **Stack Intelligence** (Feature 5)
**Problem:** Complex stacks (5+ branches) are hard to understand. Users don't know merge order, what's blocking, what's safe to land.

**Solution:** `arc stack analyze` shows critical path, bottlenecks, safe merge order.

```bash
$ arc stack analyze
Stack: api-redesign (7 branches)
├── feature-1 (auth-service) ✅ APPROVED, ready to land
├── feature-2 (api-routes) ⚠️  needs feature-1
├── feature-3 (tests) ✅ APPROVED, blocked by feature-2
├── feature-4 (docs) ✅ APPROVED, independent!

CRITICAL PATH: feature-1 → feature-2 → feature-3
BOTTLENECK: feature-2 (blocks 4 others)
Safe merge order: feature-1, feature-4, feature-2, feature-3...
```

**CLI Alignment (clig.dev):**
- ✅ Appropriate density: shows what matters, hides noise
- ✅ Discoverable: users learn stack structure
- ✅ Conversational: provides actionable suggestions

**Implementation notes:**
- Read PR status (approved, failing, waiting)
- Build dependency graph
- Identify critical path (longest chain)
- Suggest topological sort for merging

---

#### 3. **Edit + Auto-Restack** (Feature 8)
**Problem:** Modifying a commit requires manually rebasing upstack. Error-prone, tedious.

**Solution:** `arc edit` modifies a commit and auto-restacks dependents.

```bash
$ arc edit feature-1
[Opens editor]
[User changes commit message/content]
[Arc auto-restacks feature-2, feature-3, feature-4]
✅ feature-1 updated
✅ feature-2 rebased
✅ feature-3 rebased
✅ feature-4 rebased
```

**CLI Alignment (clig.dev):**
- ✅ Simple, composable: one command does the work
- ✅ Robust: handles cascading changes gracefully

**Implementation notes:**
- Interactive rebase to the commit
- After user saves, detect new SHA
- Rebase all dependent branches
- Handle conflicts with user guidance

---

### Secondary Features (Medium Priority)

#### 4. **Branch Restack Command**
`arc restack <branch>` — reorganize a branch without full sync.

#### 5. **Stack Log Viewer**
`arc log --stack` — visual tree of branches and commits.

#### 6. **Partial Stack Submit**
`arc submit --downstack` — submit only current + ancestors, skip upstack.

#### 7. **Squash-Merge Recovery**
Auto-detect when a branch was squash-merged on GitHub, handle gracefully.

---

## v0.4.0 — Collaboration & Workflow

### Team Features

#### 8. **Approval Tracking in CLI**
`arc status --approvals` — show which reviewers approved which PRs.

```bash
$ arc status --approvals
feature-1 ✅ approved by alice, bob
feature-2 ⏳ waiting on alice
feature-3 ✅ approved by bob
```

#### 9. **Team Stack View** (optional web dashboard)
Read-only web view: see all active stacks, bottlenecks, who's blocked.

#### 10. **Merge Queue Integration**
Orchestrate parallel testing: test multiple PRs together before merge.

---

## v0.5.0+ — Advanced

### Future Explorations

- Multi-platform support (GitLab, Gitea, Bitbucket)
- Fork mode workflows (read-only repos)
- Offline stash mode (queue PRs for submit when online)
- Integration hooks (link to issues, run custom commands)
- AI-powered suggestions (conflict resolution, test failures)
- Configuration profiles (different workflows for different teams)

---

## Design Principles (from clig.dev)

All features should follow these principles:

1. **Human-first** — Help users understand what's happening
2. **Composable** — Work with standard Unix tools (`| grep`, `> file`, etc.)
3. **Consistent** — Follow existing arc patterns and conventions
4. **Discoverable** — Users should learn by trying, not memorizing
5. **Robust** — Never surprise users with silent failures
6. **Empathetic** — Guide users through problems with helpful suggestions

**Output Formats:**
- Default: human-readable (pretty-printed, colors, hints)
- `--json`: machine-readable (for scripting, tools)
- `--plain`: script-friendly tables (for `awk`, `grep`)

---

## How to Use This Document

1. **When discovering a new need:** Add it here with problem/solution
2. **When ready to build:** Extract to `docs/superpowers/plans/`
3. **When completing:** Move details to `CHANGELOG.md`, remove from roadmap
4. **Review regularly:** Prioritize based on user impact, not complexity

---

**Last updated:** 2026-06-01
**Features completed:** v0.2.0 (arc report, sync auto-retarget)
