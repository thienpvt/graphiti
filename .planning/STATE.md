---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Catalog-v2 Pre-Canary Hardening
status: roadmap_ready
last_updated: "2026-07-17T16:00:00.000Z"
last_activity: 2026-07-17
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-17)

**Core value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.
**Current focus:** Phase 3 — Strict Contracts and Catalog-v2 Identity

## Current Position

Phase: 3 of 7 (Strict Contracts and Catalog-v2 Identity) — v1.1 active phases are 3–7
Plan: —
Status: Ready to plan Phase 3
Last activity: 2026-07-17 — v1.1 roadmap created (138/138 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 14 (v1.0)
- Average duration: tracked in plan summaries
- Total execution time: tracked in plan summaries

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Typed Catalog Primitives | 8 | 8 | see summaries |
| 2. Provenance and Atomic Batch | 6 | 6 | see summaries |
| 3–7 (v1.1) | 0 | TBD | - |

**Prior milestone:**

- Phase 1: 5/5 truths, 55/55 requirements
- Phase 2: 5/5 truths, 31/31 requirements
- v1.0 audit: 6/6 flows, 86/86 requirements

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v1.1 continues phase numbering at 3 after shipped v1.0 Phases 1–2
- Five-phase v1.1 spine: contracts/identity → maps/hashes/capabilities → prepare/commit/evidence → manifests/diagnostics → verify/docs
- No store/control-plane writes before strict model/identity/map/hash unit gates
- No commit before prepare/discard zero-domain-write proof
- No manifest-backed verify before atomic commit+manifest+concurrency
- Prepare stores the full immutable payload, resolved membership, and required embeddings; commit makes no external calls and uses one success tx for domain+evidence+manifest+terminals
- Stop and report if Neo4j cannot store prepared payloads or co-commit success unit
- Catalog-v2 intentionally breaks v1 request identity/provenance/hash contracts; preserve tool names
- Cherry-picked pre-hardening canary artifacts record an ACCEPT_TAB dry-run/commit in `oracle-catalog-v2`; treat them as offline historical evidence only
- No canary execution, `oracle-catalog-v2` query/mutation, automatic v1 migration, or deployment this milestone
- Approved edge vocabulary remains the existing 16 types; `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` are deferred
- Phase 5 and Phase 6 require phase-specific research during planning

### Pending Todos

None. Next: `/gsd-plan-phase 3` (or discuss Phase 3 if discuss mode requires it).

### Blockers/Concerns

- Never mutate `oracle-catalog-v2` without separate approval
- Preserve unrelated working-tree dirt: `.planning/config.json`, docker/k8s configs, `.codegraph/`, `catalog/`, `mcp_server/sample_catalog.json`
- Do not push, merge, deploy, or tag without separate approval
- Neo4j property-size / single-tx limits for prepared payloads and manifests must be validated in Phase 5–6 planning

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
Stopped at: v1.1 ROADMAP.md + STATE.md + REQUIREMENTS traceability written
Resume file: None
Next: present roadmap for approval; plan Phase 3 after approval
