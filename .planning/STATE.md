---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Catalog-v2 Pre-Canary Hardening
current_phase: 03B
current_phase_name: Atomic Catalog, Exact Evidence, Durable Manifest Writes
status: pending discussion/planning
stopped_at: Phase 3B context gathered
last_updated: "2026-07-18T09:13:25.888Z"
last_activity: 2026-07-18
last_activity_desc: Phase 3A verified 6/6; ready_for_phase_3b=true
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 25
  completed_plans: 25
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-18)

**Core value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.
**Current focus:** Phase 03B — Atomic Catalog, Exact Evidence, Durable Manifest Writes (pending discussion/planning)

## Current Position

Phase: 03B (Atomic Catalog, Exact Evidence, Durable Manifest Writes) — PENDING DISCUSSION/PLANNING
Plan: not planned
Status: Phase 3A verified; Phase 3B awaiting discussion/planning
Last activity: 2026-07-18 — Phase 3A verified 6/6; ready_for_phase_3b=true

Progress: Phase 0+1+2+3A complete at local gate (25 v1.1 plans: 2+12+5+6); Phase 3B pending discussion/planning

## Performance Metrics

**Velocity:**

- Total plans completed: 39 (14 in v1.0, 25 in v1.1 Phases 0–3A)
- Average duration: tracked in plan summaries

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| v1.0 Phase 1. Typed Catalog Primitives | 8 | 8 | see summaries |
| v1.0 Phase 2. Provenance and Atomic Batch | 6 | 6 | see summaries |
| Phase 0 | 2 | 2 | see summaries |
| Phase 1 | 12 | 12 | see summaries |
| Phase 2 | 5 | 5 | see summaries |
| Phase 3A | 6 | 6 | see summaries |

**Prior milestone:**

- v1.0 Phase 1: 5/5 truths, 55/55 requirements
- v1.0 Phase 2: 5/5 truths, 31/31 requirements
- v1.0 audit: 6/6 flows, 86/86 requirements

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Planning artifacts remapped from offset Phases 3–7 to canonical Phase 0 / 1 / 2 / 3A / 3B / 4 / 5; 138 requirement IDs preserved uniquely
- No canary execution, `oracle-catalog-v2` query/mutation, automatic v1 migration, or deployment this milestone
- [Phase 1]: Plan 01-11 tracked stdlib gate runner is sole local_gate_pass authority; LF-normalized content digests
- [Phase 1]: ready_for_phase_2 stays false until four independent audits green
- [Phase 1]: CR-01/CR-02/WR-01/WR-02 closed with no-silent-drop key equality
- [Phase 1]: WR-R01/WR-R02 accepted residuals (edge lock parity; status default polish) — not hard blockers
- [Phase 1]: Plan 01-12 final readiness after goal PASSED, security SECURED, Nyquist COMPLIANT, code CLEAR_WITH_RESIDUALS
- [Session]: full-v1.1 autonomous request superseded the earlier stop-after-Phase-1 limit
- [Phase 2]: Plan 02-05 tracked stdlib gate runner is sole local_gate_pass / ready_for_phase_3a authority
- [Phase 2]: raw 02-EDGE-PROBE.json byte-stable; resolution is separate 68/68 map
- [Phase 2]: server-owned 16-type endpoint map, explicit evidence-link contract, authoritative batch hash, and mutation-free capabilities verified
- [Phase 2]: ready_for_phase_3a true only with local_gate_pass + safety (no canary, no oracle-catalog-v2, no prepare write path)
- [Phase 3A]: 6/6 plans complete; prepare/discard/token control plane verified; ready_for_phase_3b=true

### Pending Todos

Phase 3A fully verified 6/6; ready_for_phase_3b=true. Next: Phase 3B discussion/planning (domain+evidence+manifest co-commit); local Ollama E2E before cleanup; milestone audit/completion; explicit cleanup confirmation.

### Blockers/Concerns

- Never mutate `oracle-catalog-v2` without separate approval
- Preserve unrelated working-tree dirt: `.planning/config.json`, docker/k8s configs, `.codegraph/`, `catalog/`, `mcp_server/sample_catalog.json`
- Do not push, merge, deploy, or tag without separate approval
- Neo4j single-transaction and manifest property-size limits must be validated in Phase 3B planning

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260718-ca6 | Document Phase 1 residual WR-R01/WR-R02 as accepted residuals | 2026-07-18 | e31bb04 | [260718-ca6-document-phase-1-residual-findings](./quick/260718-ca6-document-phase-1-residual-findings/) |
| 260718-c2u | LF-stable Phase 1 gate digests + Scope Stop bind | 2026-07-18 | 4c9fff3 | [260718-c2u-remediate-phase-1-nyquist-digest-bind](./quick/260718-c2u-remediate-phase-1-nyquist-digest-bind/) |
| 260718-bnv | Remediate Phase 1 Nyquist non-compliance: rebind gate ledger to primary HEAD | 2026-07-18 | 63f7fe8 | [260718-bnv-remediate-phase-1-nyquist-non-compliance](./quick/260718-bnv-remediate-phase-1-nyquist-non-compliance/) |
| 260717-wvz | Reconcile ROADMAP.md and REQUIREMENTS.md to the canonical pre-canary roadmap; preserve 138/138 unique mappings | 2026-07-17 | 37ff944 | [260717-wvz-reconcile-planning-roadmap-md-and-planni](./quick/260717-wvz-reconcile-planning-roadmap-md-and-planni/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Future | Oracle extraction / SQL-PLSQL parsing | Deferred | v1.1 requirements |
| Future | Relationship inference / path-impact / object context | Deferred | v1.1 requirements |
| Future | Catalog delta/retirement / business transactions | Deferred | v1.1 requirements |
| Ops | Production canary / live-group migration | Separate approval | v1.0 close / v1.1 scope |
| Backend | FalkorDB/other catalog portability | Deferred | v1.0 / v1.1 |
| Residual | WR-R01 edge MERGE lock-authoritative identity arbitration | Accepted residual → Phase 3B/5 | Phase 1 01-12 |
| Residual | WR-R02 `_write_status_from_row` fail-closed unknown status | Accepted residual → later polish | Phase 1 01-12 |

## Session Continuity

Last session: 2026-07-18T09:13:25.881Z
Stopped at: Phase 3B context gathered
Resume file: .planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md
Next: Phase 3B discussion, research, and planning
