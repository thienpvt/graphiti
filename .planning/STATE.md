---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Catalog-v2 Pre-Canary Hardening
current_phase: 1
current_phase_name: Strict Contracts and Catalog-v2 Identity
status: Phase 1 gap closure — 01-10 complete; readiness false; next 01-11
stopped_at: Completed 01-10-PLAN.md
last_updated: "2026-07-18T01:04:12.232Z"
last_activity: 2026-07-18
last_activity_desc: "Completed 01-10 lock-authoritative entity conflicts and offline catalog-v2 fixtures"
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 13
  completed_plans: 12
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-18)

**Core value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.
**Current focus:** Phase 1 — Strict Contracts and Catalog-v2 Identity (gap closure)

## Current Position

Phase: 1 of 7 (Strict Contracts and Catalog-v2 Identity) — IN PROGRESS
Plan: 10 of 11 complete (next 01-11)
Status: Phase 1 gap closure in progress; ready_for_phase_2=false
Last activity: 2026-07-18 — Completed 01-10 lock-authoritative entity conflicts and offline catalog-v2 fixtures

Progress: [█████████░] 92%

## Performance Metrics

**Velocity:**

- Total plans completed: 22 (14 in v1.0, 8 in v1.1 Phase 0+1)
- Average duration: tracked in plan summaries
- Total execution time: tracked in plan summaries

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| v1.0 Phase 1. Typed Catalog Primitives | 8 | 8 | see summaries |
| v1.0 Phase 2. Provenance and Atomic Batch | 6 | 6 | see summaries |
| Phase 0–5 (v1.1, 7 work units) | 7 | TBD | - |
| Phase 0 | 2 | 2 | see summaries |
| Phase 1 | 8 | 8 | see summaries |

**Prior milestone:**

- v1.0 Phase 1: 5/5 truths, 55/55 requirements
- v1.0 Phase 2: 5/5 truths, 31/31 requirements
- v1.0 audit: 6/6 flows, 86/86 requirements

**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 4min | 2 tasks | 6 files |
| Phase 01 P02 | 25min | 2 tasks | 7 files |
| Phase 01 P03 | 3min | 2 tasks | 3 files |
| Phase 01 P04 | 40min | 2 tasks + hard-gate | 5 files |
| Phase 01 P05 | 15min | 2 tasks | 4 files |
| Phase 01 P06 | 40min | 2 tasks | 13 files |
| Phase 01 P08 | 23min | 3 tasks | 8 files |
| Phase 01-strict-contracts-and-catalog-v2-identity P09 | 6min | 3 tasks | 9 files |
| Phase 01 P10 | 14min | 2 tasks | 8 files |

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
- [Phase 1]: Shared CatalogStrictModel base; required catalog-v2/system_key shells; Literal True write flags
- [Phase 1]: Response models remain non-strict BaseModel; status request omits version/system_key
- [Phase 1]: REFACTOR no-op for 01-01; no dual-version compatibility helpers
- [Phase 1]: Pure catalog_graph_key fullmatch registry; shell system_key authority; no v1 rewrite
- [Phase 1]: Procedure/Function require nonempty #OVERLOAD; package optional; SourceArtifact distinct from provenance source_key
- [Phase 1]: REFACTOR no-op for 01-02; no dual-version rewrite helpers
- [Phase 1]: catalog-v2 UUID materials via IDENTITY_SCHEMA_VERSION; signatures stable
- [Phase 1]: Pure EvidenceLink/Manifest/PreparedPlan helpers only; no persistence
- [Phase 1]: REFACTOR no-op for 01-03; no dual-version identity shim
- [Phase 1]: Converter pure in catalog_common; CatalogSafeFastMCP wires SAFE-08 structured ToolError for seven catalog tools only
- [Phase 1]: Fresh ToolError(JSON) outside except; legacy/non-validation ToolErrors unchanged
- [Phase 1]: CONT-07 proven via FastMCP call_tool + typed request annotations on all seven catalog tools
- [Phase 1]: REFACTOR no-op for 01-04; no dual-version helpers
- [Phase 1]: 01-PHASE1-GATE was green after 01-05; Plan 01-06 invalidated it to ready_for_phase_2=false pending 01-07/01-08 gap closure
- [Phase 1]: catalog_neo4j_int=skip without live probe; Phase 0 canary-script fails remain baseline noise
- [Phase 1]: Missing system_key remains Pydantic missing/validation_error; only explicit invalid_system_key errors receive that structured code
- [Phase 1]: CatalogSourceRef models are dumped to plain JSON dictionaries before canonical hashing and store serialization
- [Phase 1]: Strict scalar aliases reject coercion before Literal handling; nested graph-key scope errors retain exact request-relative locations
- [Phase 1]: IDEN-08 unique completion belongs to Phase 4; Phase 1 graph-key echo tests are partial foundation evidence only
- [Phase 1]: IDEN-13 unique completion belongs to Phase 5; Phase 1 v1-material inequality and historical-golden guards are partial foundation evidence only
- [Phase 1]: Final evidence gate is green; stop before Phase 2 for independent orchestrator re-audit
- [Phase ?]: Plan 01-09: CR-02 reference_time model validation preserves exact ISO source string; WR-01 exact graph-key field locations via validate_entity_graph_key_at
- [Phase ?]: Plan 01-09: readiness remains false; CR-01/WR-02 delegated to 01-10; 01-11 alone may reconsider local readiness
- [Phase ?]: Entity MERGE self-lock + under-lock immutable/type CASE is mutation authority
- [Phase ?]: Combined batch catches EntityInvariantRace as typed conflict after domain rollback
- [Phase ?]: Pure offline catalog-v2 FE fixtures; live race defined but unexecuted

### Pending Todos

Next: Plan 01-11 readiness reconsideration only after mandatory checks. ready_for_phase_2=false. Do not transition or execute Phase 2 in this session.

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

Last session: 2026-07-18T01:04:12.225Z
Stopped at: Completed 01-10-PLAN.md
Resume file: None
Next: Independent Phase 1 re-audit; stop before Phase 2 execution
