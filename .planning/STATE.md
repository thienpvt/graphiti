---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Catalog-v2 Pre-Canary Hardening
status: executing
stopped_at: Completed 06-03-PLAN.md
last_updated: "2026-07-22T19:20:00Z"
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 49
  completed_plans: 47
  percent: 92
current_phase: 06
current_phase_name: Catalog-v2 TDD-to-Canary Clean-Room Closure
last_activity: 2026-07-22
last_activity_desc: Phase 6 Plan 06-03 complete; candidate d54abe9 exact archive and frozen matrix green; 3/5 executed; next Plan 06-04
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** A catalog item can be retried safely and commits as exactly one deterministic, correctly typed, searchable Neo4j object without LLM-derived or implicit graph mutations.
**Current focus:** Phase 06 — catalog-v2-phase-6-tdd-to-canary-clean-room-closure

## Current Position

Phase 5 complete (historical). Phase 6 execution is active; Plans 06-01 through 06-03 complete.

### Phase 6 (3/5 complete → execute 06-04)

- Authority: `e52c1b5:spec/new-phase.md`
- Requirements ingested: **64/64** P6-* IDs
- Plans on disk: **5** sequential waves (`06-01`…`06-05`) — **3/5 executed**
- Plan 06-01: raw-Git exact archive RED/GREEN complete; baseline `dcf730…` golden exact
- Plan 06-02: post-ID terminal/auth/replay/final-launcher RED/GREEN complete; 57 harness + 309 catalog tests passed
- Plan 06-03: candidate `d54abe9` bound to 756 exact blobs; context `46a870f81158…`; frozen matrix green
- Next: Plan 06-04 build/inspect one filtered archive-derived source-bound image; no runtime
- `canary_ids_allocated=false`; no source-bound image yet; no clean-room runtime; `canary_executed=false`; no canary approval
- Dirty overlay `mcp_server/config/config-docker-neo4j.yaml` remains unstaged

### Phase 5 (preserved historical facts)

- Phase 5 plans: 7/7 complete across 6 waves
- Final marker-bound proof: verified
- Evaluated implementation HEAD: `27c4e2e4e5000d84d18cde24a99b010831771fe7`
- Final ledger SHA-256: `012a5a2129719755babed6cc0850b1ede25f54125f6c6e560c555db79b1041d5`
- Proof marker SHA-256: `ead31643f5ac571e17b02ad5960ab8b4b240b5dfc1ca17f75a5300b4119e1677`
- Canonical final checks: 20/20 pass
- Focused Phase 5 suite: 380 passed
- Live Neo4j TEST-11: 62 passed using only `oracle-catalog-tool-test`
- Local Ollama E2E: 5 passed; no cleanup
- Deep review: clean
- Nyquist: 37/37 edge probes resolved
- Security: verified; `threats_open=0`; no accepted risks
- Goal verification: 5/5 must-haves; 17/17 requirements; no gaps
- `phase_5_complete=true`; `ready_to_regenerate_canary=true`
- `canary_executed=false`; current `oracle-catalog-v2` queried/mutated=false; `clear_graph_called=false`
- Historical `a67789a` retained as separate `test_policy` / `local_neo4j_no_corresponding_data` axis

## Performance Metrics

| Phase | Plans | Status |
|-------|------:|--------|
| v1.0 Phase 1 | 8/8 | Complete |
| v1.0 Phase 2 | 6/6 | Complete |
| Phase 0 | 2/2 | Complete |
| Phase 1 | 12/12 | Complete |
| Phase 2 | 5/5 | Complete |
| Phase 3A | 6/6 | Complete |
| Phase 3B | 6/6 | Complete |
| Phase 4 | 6/6 | Complete; ready_for_phase_5=true; manifest_verification=true |
| Phase 5 | 7/7 | Complete; final proof verified; ready_to_regenerate_canary=true |
| Phase 6 | 3/5 | In progress; exact candidate bind/frozen matrix complete; next 06-04 |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 06 P01 | 31min | 2 tasks | 3 files |
| Phase 06 P02 | 56min | 2 tasks | 15 task-owned files |
| Phase 06 P03 | 96min | 2 tasks | 6 planning/source files |

## Accumulated Context

### Decisions

- Active v1.1 spine Phase 0 / 1 / 2 / 3A / 3B / 4 / 5 is complete.
- Phase 6 authorized by `e52c1b5`; 64 P6-* requirements ingested; five-wave plans written (06-01 archive TDD → 06-02 classification/auth/replay TDD → 06-03 bind/matrix → 06-04 image → 06-05 R0–R3/freeze/handoff).
- Phase 6 Plans 06-01/02/03 complete (3/5); candidate `d54abe9` exact archive and frozen matrix green; next Plan 06-04; no image/runtime/IDs/canary.
- [Phase 06]: Image authority is fixed to BIND commit `d54abe9d3d224367cb3a4eb989683a2860a9add2`, tree `4f87cf0c5ece8351ea83307c5078044e613139b3`, context `46a870f81158e1862cfcfb7662b4776c40733a344881ccf6192b643fe61222e8`.
- No automatic catalog-v1 migration, deployment, push, merge, tag, graph clear, or existing-data deletion.
- Development/live tests use only `oracle-catalog-tool-test`.
- Never query or mutate `oracle-catalog-v2`.
- Phase 3B uses two-axis safety: permanent historical audit for `a67789a`; independent current safety. Historical event class `test_policy`, scope `local_neo4j_no_corresponding_data`.
- `features.manifests=true`; `manifest_verification=true`.
- `canary_executed=false` remains hard truth until Phase 6 top-level handoff.
- Post-ID canary classes only: PASSED | FAILED_BEFORE_COMMIT | FAILED_AFTER_COMMIT (never post-ID BLOCKED).
- P6-CAN-04/05: one primary token-only commit; committed harness replay gate (no second commit).
- P6-PROV-03: contract-safe auth sentinel path; no CatalogErrorCode expansion (P6-HARN-19).
- [Phase 06]: Git object bytes are source authority; checkout and git-archive EOL behavior is excluded.
- [Phase 06]: Canonical context hash preserves ls-tree order and excludes mode/object ID from the aggregate.

### Pending Todos

1. Execute Plan 06-04: one filtered archive-derived image bound to candidate `d54abe9`; inspect labels/layers; no runtime/canary.
2. Do not allocate canary IDs or start runtime until Plans 06-04 then 06-05 execute in order.
3. Require explicit confirmation before any cleanup/deletion.

### Blockers/Concerns

- Preserve unrelated working-tree changes: `.planning/config.json`, prior phase artifacts, Docker/Kubernetes configs, `.codegraph/`, `catalog/`, `mcp_server/sample_catalog.json`.
- Unrelated `mcp_server/config/config-docker-neo4j.yaml` defaults `qwen3-embedding:0.6b` to 1536 dimensions although official maximum is 1024; intentionally untouched (P6-PRES-01).
- Never weaken a real product, transaction, validation, security, test, or hard gate.
- No remote-state mutation without separate approval.
- Phase 6 plan artifacts may remain uncommitted by standing order until orchestrator commits.

## Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260719-tur | Halt local Compose activation after safety violation; canary not run | 2026-07-19 | uncommitted | `.planning/quick/260719-tur-activate-local-compose-catalog-runtime-a/` |
| 260719-udj | Implement truthful mutation-free Catalog-v2 runtime readiness | 2026-07-19 | uncommitted | `.planning/quick/260719-udj-implement-truthful-mutation-free-catalog/` |
| 260718-ca6 | Document Phase 1 residual WR-R01/WR-R02 as accepted residuals | 2026-07-18 | e31bb04 | `.planning/quick/260718-ca6-document-phase-1-residual-findings/` |
| 260718-c2u | LF-stable Phase 1 gate digests + Scope Stop bind | 2026-07-18 | 4c9fff3 | `.planning/quick/260718-c2u-remediate-phase-1-nyquist-digest-bind/` |
| 260718-bnv | Remediate Phase 1 Nyquist non-compliance | 2026-07-18 | 63f7fe8 | `.planning/quick/260718-bnv-remediate-phase-1-nyquist-non-compliance/` |
| 260717-wvz | Reconcile roadmap and requirements to canonical pre-canary roadmap | 2026-07-17 | 37ff944 | `.planning/quick/260717-wvz-reconcile-planning-roadmap-md-and-planni/` |

## Deferred Items

| Category | Item | Status |
|----------|------|--------|
| Canary | Phase 6 production/regenerated canary | Separate approval |
| Migration | Automatic catalog-v1 → catalog-v2 migration | Out of scope |
| Backend | FalkorDB/Kuzu/Neptune catalog portability | Deferred |
| Product | Oracle extraction, parser, path/impact, delta/retirement | Deferred |

## Session Continuity

**Last session:** 2026-07-22T19:20:00Z
**Resume file:** .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-04-PLAN.md

Stopped at: Completed 06-03-PLAN.md
Next: execute Plan 06-04 image build/inspection only; still no runtime/IDs/canary.
