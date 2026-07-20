---
phase: 05-verification-security-compatibility-and-migration-docs
plan: 05
subsystem: documentation
tags: [catalog-v2, operator-reference, migration, structural-gates, neo4j]
requires:
  - phase: 05-03
    provides: hardened offline canary artifacts and pure prepare/commit sequence
  - phase: 05-04
    provides: exact 14 legacy, 14 catalog, 28-tool union compatibility proof
provides:
  - Complete catalog-v2 operator reference derived from authoritative tool/error registries
  - Offline-only catalog-v1 to catalog-v2 migration and regeneration guidance
  - Fail-closed check-docs and check-migration commands
  - requirements: [DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05, DOCS-06]
affects: [phase-5-gate, phase-5-audit, future-canary-regeneration]
tech-stack:
  added: []
  patterns: [AST-derived documentation sets, exact markdown inventory gates, placeholder-aware secret scan]
key-files:
  created:
    - mcp_server/docs/CATALOG_V2_MIGRATION.md
  modified:
    - mcp_server/README.md
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/catalog_phase5_gate_runner.py
    - mcp_server/tests/test_catalog_phase5_gate_runner.py
key-decisions:
  - "Documentation inventories are compared as exact sets derived statically from authoritative source and the frozen legacy baseline."
  - "Migration guidance permits offline hardened builder use only; Phase 5 never invokes the canary runner or live MCP path."
  - "Examples may contain explicit placeholders/defaults, while real-looking credentials and raw namespace assignments fail the structural gate."
patterns-established:
  - "Operator docs use canonical sections consumed by check-docs."
  - "Migration docs retain separate historical a67789a and current no-v2 safety axes."
requirements-completed: [DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05, DOCS-06]
coverage:
  - id: D1
    description: Exact 14 legacy plus 14 catalog tool inventories and preferred large-payload prepare/commit path
    requirement: DOCS-01
    verification:
      - kind: structural
        ref: "catalog_phase5_gate_runner.py check-docs"
        status: pass
    human_judgment: false
  - id: D2
    description: System-scoped grammar, FE/BO guidance, overloads, registries, and complete endpoint map
    requirement: DOCS-02
    verification:
      - kind: structural
        ref: "catalog_phase5_gate_runner.py check-docs"
        status: pass
    human_judgment: false
  - id: D3
    description: Hashes, capabilities, lifecycle, limits, evidence, manifests, and gates
    requirement: DOCS-03
    verification:
      - kind: structural
        ref: "catalog_phase5_gate_runner.py check-docs"
        status: pass
    human_judgment: false
  - id: D4
    description: Exact CatalogErrorCode inventory and rollout configuration without secrets
    requirement: DOCS-04
    verification:
      - kind: unit
        ref: "test_catalog_phase5_gate_runner.py"
        status: pass
    human_judgment: false
  - id: D5
    description: Obsolete v1 identity, no automatic rewrite, no old ACCEPT_TAB SHA reuse, two-axis safety
    requirement: DOCS-05
    verification:
      - kind: structural
        ref: "catalog_phase5_gate_runner.py check-migration"
        status: pass
    human_judgment: false
  - id: D6
    description: Executable offline hardened builder procedure with explicit live runner ban
    requirement: DOCS-06
    verification:
      - kind: unit
        ref: "test_catalog_canary_scripts.py (23 tests)"
        status: pass
    human_judgment: false
duration: 2h
completed: 2026-07-19
status: complete
---

# Phase 5 Plan 05: Operator and Migration Documentation Summary

**Complete catalog-v2 operator contracts plus an offline-only migration guide, protected by source-derived exact-set gates.**

## Accomplishments

- Documented exactly 14 legacy and 14 catalog tools, the 28-tool union, preferred prepare/token-only-commit flow, catalog-v2 identity grammar, registries, endpoint map, hashes, capabilities, lifecycle, limits, evidence, manifests, gates, errors, and rollout configuration.
- Added an offline hardened regeneration procedure using the sanitized fixture and `--mode hardened`; historical artifacts remain read-only non-authority.
- Kept Phase 5 explicit: no canary runner, live MCP canary, `oracle-catalog-v2` query/mutation, automatic graph re-key, deployment, clear, or delete.
- Added fail-closed `check-docs` and `check-migration` commands; exact tool/error sets derive statically from product source and the frozen legacy baseline.
- Corrected stale public prepare/commit docstrings to describe current immutable prepare and atomic domain/evidence/manifest commit behavior.

## Task Commits

1. **Migration safety note** — `34a4e76` (docs)
2. **Operator reference** — `c405b14` (docs)
3. **Offline regeneration guide** — `bb94215` (docs)
4. **Structural documentation gates** — `908bb7e` (test)
5. **Independent audit corrections and contract alignment** — `fc0d833` (fix)

## Verification

- `check-docs`: **PASS**.
- `check-migration`: **PASS**.
- Focused docs/security/store/service/compatibility/canary suite: **PASS — 354 passed**.
- Additional offline hardened canary suite: included above, **23 passed**.
- Ruff on changed Python: **PASS**.
- Project-scoped Pyright on changed Python: **PASS — 0 errors, 0 warnings, 0 informations**.
- Secret-pattern scan: **PASS — no live-looking credential/private-key matches**.
- `git diff --check` on Plan 05-05 files: **PASS**.

## Safety Evidence

- Structural checks read source/docs only; no product imports, DB connection, network call, canary execution, or secret-value lookup.
- Migration command was syntax-checked with `--help`; builder/runner were not executed during documentation work.
- `oracle-catalog-v2` remains a forbidden target; historical `a67789a` remains a separate immutable audit pointer.
- No dependency, deployment, push, graph clear, existing-data deletion, or worktree cleanup occurred.

## Deviations from Plan

### Auto-fixed issues

1. **Documentation audit found factual drift** — corrected terminal replay/discard semantics, capability read-gate exception, evidence/request hash exclusions, namespace-derived IDs, fact evidence records, and batch UUID wording.
2. **Initial structural headings were too brittle** — aligned canonical headings and made section extraction hierarchy-aware without weakening exact-set checks.
3. **Secret scan rejected placeholders** — retained fail-closed secret detection while permitting only explicit placeholders/default examples.
4. **MCP tool help was stale** — updated prepare/commit docstrings only; no behavior change.

## Known Stubs

None for DOCS-01..06. Phase 5 readiness remains false until 05-06 evidence and post-execution audits complete.

## Next Phase Readiness

- Plan 05-05 complete: **5/7 Phase 5 plans**.
- Plan 05-06 unblocked.
- `canary_executed=false`; Phase 6 remains separate and untouched.

## Self-Check: PASSED

- Both documentation commands pass on current HEAD.
- All six requirements have direct executable evidence.
- Exactly two documentation deliverables exist for this plan: operator reference and migration guide.
