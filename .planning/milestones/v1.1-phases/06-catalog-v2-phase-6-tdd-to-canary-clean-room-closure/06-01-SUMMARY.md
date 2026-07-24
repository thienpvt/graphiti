---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 01
subsystem: source-binding
tags: [git-plumbing, sha256, archive, tdd]
requires:
  - phase: 05-verification-security-compatibility-and-migration-docs
    provides: Phase 5 pre-canary readiness and immutable H1-H7 evidence
provides:
  - Exact raw-Git source-tree materialization without checkout or git-archive bytes
  - Canonical path/blob-digest source-context hash reproducing the baseline golden
  - Fail-closed archive membership, mode, path, and drift verification
  - RED-first focused contract suite
  - Phase 6 Wave 1 P6-AUTH-01 proof: no deployment, Kubernetes, canary, or historical-group action occurred
  - No runtime/image/namespace/canary side effects; canary_executed=false
  - Protected config remained untouched, unstaged, and uncommitted
  - Disposable test workspaces were confined to CLAUDE_JOB_DIR/tmp/phase6-archive-*
affects: [06-02, 06-03, source-bound-image]
tech-stack:
  added: []
  patterns: [raw git ls-tree and cat-file authority, path-blob digest aggregation]
key-files:
  created:
    - scripts/catalog_raw_git_archive.py
    - mcp_server/tests/test_catalog_raw_git_archive.py
  modified:
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-VALIDATION.md
key-decisions:
  - "Git object bytes are source authority; checkout and git-archive EOL behavior is excluded."
  - "Canonical context hash preserves ls-tree order and excludes mode/object ID from the aggregate."
patterns-established:
  - "Exact materialization: git ls-tree -rz --full-tree followed by git cat-file blob with shell=False."
  - "Archive verification reports H8-compatible count and context-hash fields."
requirements-completed: [P6-AUTH-01, P6-BASE-01, P6-CONT-01, P6-TDD-01, P6-TDD-02, P6-TDD-03, P6-BIND-02, P6-BIND-03, P6-BIND-04, P6-PRES-01, P6-PRES-02]
coverage:
  - id: D1
    description: Exact raw-Git materializer and archive verifier
    requirement: P6-BIND-02
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_raw_git_archive.py
        status: pass
    human_judgment: false
  - id: D2
    description: Baseline canonical source-context golden
    requirement: P6-BASE-01
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_raw_git_archive.py#test_baseline_source_context_golden
        status: pass
    human_judgment: false
  - id: D3
    description: Fail-closed tree/path/mode/drift contracts
    requirement: P6-BIND-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_raw_git_archive.py
        status: pass
    human_judgment: false
duration: 31min
completed: 2026-07-22
status: complete
---

# Phase 6 Plan 01: Raw-Git Exact Archive Summary

**Raw Git plumbing now materializes byte-exact source trees and reproduces the fixed `dcf730…` baseline context hash.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-07-22T12:00:00Z
- **Completed:** 2026-07-22T12:31:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added an importable RED scaffold and eight failing acceptance tests before implementation.
- Implemented exact `ls-tree`/`cat-file` materialization, safe path validation, deterministic context hashing, and H8-compatible verification counts.
- Reproduced baseline `dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f` over 731 committed files.
- Preserved `mcp_server/config/config-docker-neo4j.yaml` unstaged; no Docker, runtime, namespace, canary, deployment, Kubernetes, or historical-group action occurred.

## Task Commits

1. **Task 1: RED raw-Git archive acceptance suite** — `a6448ae`
2. **Task 2: GREEN plumbing materializer + baseline golden** — `f306c6f`

## Files Created/Modified

- `scripts/catalog_raw_git_archive.py` — Exact Git-object materializer, verifier, and context digest.
- `mcp_server/tests/test_catalog_raw_git_archive.py` — Eight RED/GREEN archive contract tests.
- `06-VALIDATION.md` — Wave 1 results marked GREEN.

## Decisions Made

- Used raw object IDs from `git ls-tree` for every `git cat-file blob` read; never revision/path checkout bytes.
- Stored symlink target blobs as exact link text, preserving authority without unsafe host symlink creation.
- On Windows, verified mode authority through Git metadata while avoiding unsupported POSIX executable-bit filesystem claims.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added repository root to the focused test import path**
- **Found during:** Task 1 RED execution
- **Issue:** `uv --project mcp_server` did not expose the repository `scripts` namespace, causing collection exit 2.
- **Fix:** Added the repository root to `sys.path` before importing the new helper.
- **Verification:** Eight tests collected and failed with pytest exit exactly 1.
- **Committed in:** `a6448ae`

**2. [Rule 1 - Bug] Made mode verification platform-correct**
- **Found during:** Task 2 GREEN execution
- **Issue:** Windows reports permission bits differently from POSIX, causing false archive mismatches.
- **Fix:** Retained Git mode authority; compare executable bits only where the filesystem supports them.
- **Verification:** Eight focused tests and 30 adjacent gate-runner tests pass.
- **Committed in:** `f306c6f`

**Total deviations:** 2 auto-fixed (1 blocking issue, 1 correctness bug)
**Impact on plan:** Required for valid RED and cross-platform correctness; no scope expansion.

## Issues Encountered

- Initial RED run produced collection exit 2; corrected before accepting RED.
- Initial GREEN run exposed Windows mode semantics; fixed without weakening Git mode validation.

## User Setup Required

None.

## Next Phase Readiness

- Plan 06-02 can implement terminal/auth/replay contracts on top of a proven raw-Git authority helper.
- Image/runtime/canary work remains gated behind Plans 06-03–06-05.

## Self-Check: PASSED

- Created files exist.
- RED and GREEN commits exist.
- Focused tests: 8 passed.
- Adjacent tests: 38 passed.
- Ruff/format/compile checks pass.
- Baseline context golden exact.
- Protected config remains unstaged.

---
*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Completed: 2026-07-22*
