---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 03
subsystem: source-binding
tags: [raw-git, archive, frozen-matrix, fix-forward]
requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: Plans 06-01/02 raw-Git and terminal/auth/replay contracts
provides:
  - Exact raw-Git binding for candidate d54abe9d3d224367cb3a4eb989683a2860a9add2
  - Complete frozen matrix from candidate archive bytes
  - READY_FOR_IMAGE_BINDING authority for Plan 06-04
  - Full P6-HARN-01..19 offline/deferred evidence map
  - No image, runtime, identity, MCP transport, provider, or canary activity
affects: [06-04, 06-05, image-binding, clean-room-runtime]
tech-stack:
  added: []
  patterns: [raw-Git authority, archive-local disposable Git metadata, fix-forward freeze]
key-files:
  created:
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-BIND-RECEIPT.json
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-MATRIX-RECEIPT.json
  modified:
    - scripts/catalog_raw_git_archive.py
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-VALIDATION.md
key-decisions:
  - "Candidate identity remains d54abe9; later planning commits never redefine image authority."
  - "Git-aware archive tests use disposable archive-local Git metadata; source bytes remain exact raw-Git blobs."
  - "Windows executable mode authority is git ls-tree; filesystem mode comparison runs only where reliable."
requirements-completed: [P6-BASE-03, P6-TDD-04, P6-BIND-01, P6-BIND-02, P6-BIND-03, P6-BIND-04, P6-BIND-05, P6-BIND-06, P6-PRES-01, P6-PRES-02, P6-CONT-01]
requirements-offline-green-runtime-pending: [P6-HARN-01, P6-HARN-02, P6-HARN-03, P6-HARN-04, P6-HARN-05, P6-HARN-06, P6-HARN-07, P6-HARN-08, P6-HARN-09, P6-HARN-10, P6-HARN-11, P6-HARN-12, P6-HARN-13, P6-HARN-14, P6-HARN-15, P6-HARN-16, P6-HARN-17, P6-HARN-18, P6-HARN-19]
coverage:
  - id: D1
    description: Candidate raw-Git/archive equality
    requirement: P6-BIND-05
    verification:
      - kind: receipt
        ref: 06-BIND-RECEIPT.json
        status: pass
    human_judgment: false
  - id: D2
    description: Complete frozen matrix from candidate archive
    requirement: P6-TDD-04
    verification:
      - kind: receipt
        ref: 06-MATRIX-RECEIPT.json
        status: pass
    human_judgment: false
  - id: D3
    description: Failed-candidate preservation and fix-forward correction
    requirement: P6-BIND-06
    verification:
      - kind: git
        ref: 723fc4d..d54abe9
        status: pass
    human_judgment: false
duration: 96min
completed: 2026-07-22
status: complete
---

# Phase 6 Plan 03: Exact Bind and Frozen Matrix Summary

**Candidate `d54abe9` binds to 756 exact raw-Git blobs; complete archive matrix green.**

## Accomplishments

- Preserved failed candidate `723fc4d`; fixed Windows mode verification forward in `d54abe9`.
- Bound candidate commit/tree/context with zero missing, extra, or mismatched members.
- Frozen suites: **134 focused**, **80 Phase 5**, **475 warning-strict union**, **1556 complete catalog**, **84 direct**, **8 archive**.
- Ruff, format, Pyright, compilation, 22-field manifest, baseline golden, BASE-03, CatalogErrorCode checks passed.
- Image/runtime/MCP/provider/identity/canary counts remain zero. Protected config remains unstaged.

## Candidate Authority

- **Commit:** `d54abe9d3d224367cb3a4eb989683a2860a9add2`
- **Parent:** `723fc4d7a46e848e42d76dc237df0a7608097add`
- **Tree:** `4f87cf0c5ece8351ea83307c5078044e613139b3`
- **Files:** 756
- **Context:** `46a870f81158e1862cfcfb7662b4776c40733a344881ccf6192b643fe61222e8`

## Deviation

Initial frozen runs lacked Git metadata. Git-aware tests failed with `fatal: not a git repository`; candidate Git environment then leaked into synthetic repositories. Resolution: separate pristine BIND and matrix trees; disposable archive-local Git metadata for matrix tests. Source unchanged. Full rerun green.

## Next

Plan 06-04: build exactly one filtered archive-derived image bound to `06-BIND-RECEIPT.json` `commit`. No runtime or canary.

## Self-Check: PASSED

- BIND/MATRIX candidate aligned; candidate excludes both receipts.
- HARN checklist complete; offline rows green; runtime rows explicitly deferred.
- No source changes after final freeze.
- No image, runtime, IDs, or canary.

---
*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Completed: 2026-07-22*
