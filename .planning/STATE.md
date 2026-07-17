---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Catalog-v2 Pre-Canary Hardening
status: roadmap_ready
last_updated: "2026-07-17T16:50:00.000Z"
last_activity: 2026-07-17
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-17)

**Core value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.
**Current focus:** Phase 0 — Baseline, Inventory, and Compatibility Policy

## Current Position

Phase: 0 of 7 (Baseline, Inventory, and Compatibility Policy) — v1.1 active spine is Phase 0, 1, 2, 3A, 3B, 4, 5
Plan: —
Status: Ready to plan Phase 0
Last activity: 2026-07-17 — completed quick task 260717-wvz: canonical roadmap reconciliation (138/138)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 14 (v1.0)
- Average duration: tracked in plan summaries
- Total execution time: tracked in plan summaries

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| v1.0 Phase 1. Typed Catalog Primitives | 8 | 8 | see summaries |
| v1.0 Phase 2. Provenance and Atomic Batch | 6 | 6 | see summaries |
| Phase 0–5 (v1.1, 7 work units) | 0 | TBD | - |

**Prior milestone:**

- v1.0 Phase 1: 5/5 truths, 55/55 requirements
- v1.0 Phase 2: 5/5 truths, 31/31 requirements
- v1.0 audit: 6/6 flows, 86/86 requirements

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Planning artifacts remapped from offset Phases 3–7 to canonical Phase 0 / 1 / 2 / 3A / 3B / 4 / 5; 138 requirement IDs preserved uniquely
- Evidence contract freezes in Phase 2 before prepare hashing; 3A control plane before 3B domain write
- No store/control-plane writes before strict model/identity/map/hash/evidence-contract unit gates (Phase 1–2)
- No commit before Phase 3A prepare/discard zero-domain-write proof
- No manifest-backed verify before Phase 3B atomic commit+manifest+concurrency
- Prepare stores the full immutable payload, resolved membership, and required embeddings; commit makes no external calls and uses one success tx for domain+evidence+manifest+terminals
- Stop and report if Neo4j cannot store prepared payloads or co-commit success unit
- Catalog-v2 intentionally breaks v1 request identity/provenance/hash contracts; preserve tool names
- Cherry-picked pre-hardening canary artifacts record an ACCEPT_TAB dry-run/commit in `oracle-catalog-v2`; treat them as offline historical evidence only
- No canary execution, `oracle-catalog-v2` query/mutation, automatic v1 migration, or deployment this milestone
- Approved edge vocabulary remains the existing 16 types; `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` are deferred
- Phase 6 canary is separate/out of scope and carries no requirement IDs
- Phase 3A/3B and Phase 4 require phase-specific research during planning

### Pending Todos

None. Next: `/gsd-plan-phase 0` (or discuss Phase 0 if discuss mode requires it). Not "plan Phase 3".

### Blockers/Concerns

- Never mutate `oracle-catalog-v2` without separate approval
- Preserve unrelated working-tree dirt: `.planning/config.json`, docker/k8s configs, `.codegraph/`, `catalog/`, `mcp_server/sample_catalog.json`
- Do not push, merge, deploy, or tag without separate approval
- Neo4j property-size / single-tx limits for prepared payloads and manifests must be validated in Phase 3A/3B planning

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260717-wvz | Reconcile ROADMAP.md and REQUIREMENTS.md to the canonical pre-canary roadmap; preserve 138/138 unique mappings | 2026-07-17 | 37ff944 | [260717-wvz-reconcile-planning-roadmap-md-and-planni](./quick/260717-wvz-reconcile-planning-roadmap-md-and-planni/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Future | Oracle extraction / SQL-PLSQL parsing | Deferred | v1.1 requirements |
| Future | Relationship inference / path-impact / object context | Deferred | v1.1 requirements |
| Future | Catalog delta/retirement / business transactions | Deferred | v1.1 requirements |
| Ops | Production canary / live-group migration | Separate approval | v1.0 close / v1.1 scope |
| Backend | FalkorDB/other catalog portability | Deferred | v1.0 / v1.1 |

## Session Continuity

Last session: 2026-07-17
Stopped at: ROADMAP/REQUIREMENTS/STATE reconciled to canonical Phase 0/1/2/3A/3B/4/5
Resume file: None
Next: present roadmap for approval; plan Phase 0 after approval
