# Roadmap: Deterministic Catalog Ingestion for Graphiti MCP

## Overview

v1.1 hardens the shipped deterministic catalog MCP surface before any regenerated canary. v1.0 shipped typed catalog primitives and provenance/atomic batch (Phases 1–2). Active pre-canary work uses the canonical spine Phase 0 / 1 / 2 / 3A / 3B / 4 / 5 from `graphiti_mcp_pre_canary_roadmap_en.md`: baseline and compatibility policy; fail-closed catalog-v2 contracts and identity; topology authority, evidence contract, hashes, and capabilities; immutable prepare/commit control plane; atomic catalog + exact evidence + durable manifest co-commit; manifest-backed verification and read-only diagnostics; then final security, compatibility, observability, migration docs, and readiness report. Phase 6 canary is a separate out-of-scope task. A cherry-picked pre-hardening canary workflow records an ACCEPT_TAB dry-run and commit in `oracle-catalog-v2`; v1.1 treats those repository artifacts as historical evidence only and never queries, mutates, retries, or reuses that live group/hash. No canary execution, automatic v1→v2 migration, deployment, or multi-backend claims.

## Shipped Milestones

- [x] **v1.0 — Deterministic Catalog Ingestion** — Shipped 2026-07-17

| Phase | Plans | Result |
|---|---:|---|
| v1.0 Phase 1. Typed Catalog Primitives | 8/8 | Verified: 5/5 truths, 55/55 requirements |
| v1.0 Phase 2. Provenance and Atomic Batch | 6/6 | Verified: 5/5 truths, 31/31 requirements |
| **v1.0 total** | **14/14** | **86/86 requirements; 6/6 integration flows** |

Archives: [v1.0 roadmap](milestones/v1.0-ROADMAP.md) · [v1.0 requirements](milestones/v1.0-REQUIREMENTS.md) · [v1.0 audit](milestones/v1.0-MILESTONE-AUDIT.md) · [phase artifacts](milestones/v1.0-phases/)

## Phases

**Phase Numbering:**

- Active v1.1 spine: Phase 0, 1, 2, 3A, 3B, 4, 5 (seven work units)
- Phase 6 canary is separate / out of scope and carries no requirement IDs
- Shipped history is labeled `v1.0 Phase 1` / `v1.0 Phase 2` to avoid collision with active Phase 1

- [x] **v1.0 Phase 1: Typed Catalog Primitives** - Config, identity, entity/edge upsert, resolve, verify (shipped)
- [x] **v1.0 Phase 2: Provenance and Atomic Batch** - Provenance, batch status, atomic batch, docs (shipped)
- [ ] **Phase 0: Baseline, Inventory, and Compatibility Policy** - Live baseline, isolation policy, worktree/remote safety
- [ ] **Phase 1: Strict Contracts and Catalog-v2 Identity** - Recursive forbid contracts, FE/BO/COMMON grammar, fail-closed identity
- [x] **Phase 2: Topology Authority, Evidence Contract, Hashes, Capabilities** - Endpoint map, exact evidence schema, authoritative hashes, capabilities; local gate ready_for_phase_3a=true
- [x] **Phase 3A: Immutable Prepare/Commit Control Plane** - Prepare/discard/token, immutable payload, zero domain write on prepare; local gate ready_for_phase_3b=true
- [x] **Phase 3B: Atomic Catalog, Exact Evidence, Durable Manifest Writes** - Domain+evidence+manifest co-commit, rollback, search interop
- [x] **Phase 4: Manifest-Backed Verification and Read-Only Diagnostics** - Manifest reads, verify, edge resolve, split gates (completed 2026-07-18)
- [ ] **Phase 5: Verification, Security, Compatibility, and Migration Docs** - Exhaustive tests, isolation, docs, final report without canary
- Phase 6 canary: separate approval only — not in this milestone requirement set

## Hard Gates

1. **No store/control-plane write implementation** until Phase 1–2 unit gates pass for strict models, identity grammar, endpoint map, evidence contract, and hash coverage.
2. **No commit implementation** until Phase 3A prepare/discard prove zero domain/Entity/Episodic/evidence/status mutation and token/control-plane proofs pass.
3. **No manifest-backed verification** until Phase 3B atomic commit co-writes domain + evidence + manifest + terminal batch/plan state and concurrency tests pass.
4. **Final readiness (Phase 5)** only after available unit/service/store/MCP/concurrency/live Neo4j/Ruff/Pyright checks report truthfully and isolation proves no v1.1 `oracle-catalog-v2` query/mutation or canary execution; pre-hardening repository evidence is historical only.
5. **Stop and report** (do not weaken the contract) if Neo4j cannot safely store immutable prepared payloads (3A) or co-commit domain + evidence + manifest + terminal states in one transaction (3B).

## Phase Details

### Phase 0: Baseline, Inventory, and Compatibility Policy

**Goal**: Maintainers observe a recorded live-grounded baseline and explicit isolation/compatibility policy before contract or identity code changes
**Depends on**: v1.0 complete
**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04, SAFE-01, SAFE-02, SAFE-12, SAFE-13
**Success Criteria** (what must be TRUE):

  1. Maintainer can review a recorded live-grounded baseline of all 14 legacy MCP tools, all 7 catalog tools, and the cherry-picked canary builder/runner/fixtures/receipts/checkpoint/tests; historical ACCEPT_TAB commit evidence is inventoried offline
  2. Pre-existing catalog/canary/Ruff/Pyright failures remain distinguishable from v1.1 regressions; unavailable checks report as skipped
  3. Compatibility policy and catalog-v1 deprecation boundary are recorded before contract changes
  4. New tests and development writes use only `oracle-catalog-tool-test`; `oracle-catalog-v2` is never queried or mutated; no canary runs
  5. Dirty-worktree unrelated files and remote state remain untouched (no push/merge/deploy/tag)

**Plans**: 2/2 plans executed

Plans:
**Wave 1**

- [x] 00-01-PLAN.md — Wave 1: live inventory, offline ACCEPT_TAB evidence, truthful pass/fail/skip check ledger

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 00-02-PLAN.md — Wave 2 (depends on 01): compatibility freeze, isolation/remote safety policy, Phase 0 gate report

### Phase 1: Strict Contracts and Catalog-v2 Identity

**Goal**: Agents observe fail-closed catalog-v2 request contracts and collision-free FE/BO/COMMON identities before any new store or control-plane write path ships
**Depends on**: Phase 0 baseline complete
**Requirements**: CONT-01, CONT-02, CONT-03, CONT-04, CONT-05, CONT-06, CONT-07, CONT-08, IDEN-01, IDEN-02, IDEN-03, IDEN-04, IDEN-05, IDEN-06, IDEN-07, IDEN-09, IDEN-10, IDEN-11, IDEN-12, SAFE-05, SAFE-08, TEST-01, TEST-03
**Success Criteria** (what must be TRUE):

  1. Every deterministic catalog request rejects unknown or misspelled nested fields, forbids `strict_endpoints=false` and `atomic=false`, preserves hash-bearing source bytes, and validates completely before any side effect
  2. Catalog-v2 domain requests require `identity_schema_version='catalog-v2'` and a bounded canonical `system_key`; invalid keys fail with `invalid_system_key` / `unsupported_identity_schema` before DB reads, embeddings, schema init, transactions, or status writes
  3. FE and BO objects with identical Oracle names receive different graph keys and server-derived UUIDs in one `group_id`; Procedure/Function overloads do not collapse; catalog-v1 keys/hashes are never silently accepted or rewritten
  4. Caller UUIDs never control identity; structured errors expose safe diagnostics only
  5. Unit coverage for recursive forbid, immutable flags, full entity grammar, FE/BO/overload separation, and UUID material versioning passes before Phase 2 write-adjacent work

**Plans**: 12/12 plans executed

Plans:

- [x] 01-01-PLAN.md — Strict CatalogStrictModel shells, Literal flags, version/system_key, CONT-08 codes, models suite
- [x] 01-02-PLAN.md — Graph-key grammar registry (18 types), FE/BO scope, overload, v1 reject, IDEN-08 echo
- [x] 01-03-PLAN.md — Versioned UUIDv5 materials + pure future-kind helpers; identity goldens; service graph_key echo
- [x] 01-04-PLAN.md — Structured safe errors + mandatory FastMCP typed CONT-07 production boundary + spies
- [x] 01-05-PLAN.md — Truthful 01-PHASE1-GATE.md hard gate, VALIDATION refresh, edge-probe 53/53 assert
- [x] 01-06-PLAN.md — Strict contract gap closure
- [x] 01-07-PLAN.md — Catalog logging scrub + nine edge probes
- [x] 01-08-PLAN.md — Requirement remap + historical fail-closed gate
- [x] 01-09-PLAN.md — CR-02/WR-01 provenance timestamp + graph-key locations
- [x] 01-10-PLAN.md — CR-01/WR-02 locked entity conflicts + offline fixtures
- [x] 01-11-PLAN.md — Tracked local gate runner, evidence ledger, audit handoff
- [x] 01-12-PLAN.md — Final readiness after four independent audits green

**Gate**: Final readiness earned (`ready_for_phase_2=true`). Local matrix green; independent audits: goal PASSED 23/23, security SECURED 47/47, Nyquist COMPLIANT, code CLEAR_WITH_RESIDUALS (WR-R01/WR-R02 accepted). Session stop-after-phase-1: Phase 2 not started.

### Phase 2: Topology Authority, Evidence Contract, Hashes, and Capabilities

**Goal**: Server owns edge topology and freezes the evidence contract before prepare hashing; operators discover capabilities without mutation
**Depends on**: Phase 1 unit gates green
**Requirements**: EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-08, EDGE-09, HASH-01, HASH-02, HASH-03, HASH-04, HASH-05, HASH-06, HASH-07, CAPA-01, CAPA-02, CAPA-03, CAPA-04, CAPA-05, CAPA-06, CAPA-07, CAPA-08, CAPA-09, EVID-01, EVID-02, EVID-03, EVID-04, EVID-05, EVID-06, EVID-14, TEST-02, TEST-04
**Success Criteria** (what must be TRUE):

  1. Every approved catalog edge type enforces a finite server-owned `(source_entity_type, target_entity_type)` map; disallowed pairs fail before side effects; unapproved `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` remain deferred
  2. Explicit `CatalogEvidenceLink` schema is stable before persistence: one source, one typed target, allowlisted kind, bounds, deterministic identity/hash; no Cartesian multi-source shape
  3. Combined batches require lowercase 64-hex `catalog_sha256`; server-computed `request_sha256` covers identity schema, group, batch, catalog hash, and all canonical entity/edge/source/evidence content under one versioned recipe
  4. `upsert_catalog_batch` results (including dry-run) return `identity_schema_version`, server `request_sha256`, `catalog_sha256`, and `batch_uuid` with zero dry-run writes
  5. `get_catalog_capabilities` works after server init even when writes are disabled and returns versions, gates, non-reversible namespace fingerprint, registries, endpoint map, limits, and feature flags without secrets

**Plans**: 5/5 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Wave 1: Server-owned EDGE_ENDPOINT_MAP + model/service preflight + exhaustive TEST-02 matrix
- [x] 02-02-PLAN.md — Wave 1: CatalogEvidenceLink contract + pure identity + catalog-v2 Cartesian rejection (no service edits)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Wave 2 (after 01+02): Required catalog_sha256 + versioned request hash recipe + evidence_links service counters + dry-run hash echo

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — Wave 3 (after 03): Read-only get_catalog_capabilities + imports version constants + get_status compat

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-05-PLAN.md — Wave 4: Phase 2 fail-closed gate runner, 02-EDGE-PROBE-RESOLUTION.json 68/68, ready_for_phase_3a ledger

**Gate**: Local Phase 2 gate green (`ready_for_phase_3a=true` via `02-GATE-RESULTS.json`); Phase 3A prepare/control-plane write implementation unblocked for planning/execution under separate plans

### Phase 3A: Immutable Prepare/Commit Control Plane

**Goal**: Eliminate payload mutation between validation and commit; prepare stores restart-safe immutable control-plane state with zero domain graph write
**Depends on**: Phase 2 map/hash/evidence-contract unit gates green
**Requirements**: PLAN-01, PLAN-02, PLAN-03, PLAN-04, PLAN-05, PLAN-06, PLAN-07, PLAN-08, PLAN-09, PLAN-10, PLAN-11, PLAN-12, PLAN-17, PLAN-18, PLAN-19, PLAN-20, SAFE-11, TEST-05
**Success Criteria** (what must be TRUE):

  1. `prepare_catalog_batch` validates the full catalog-v2 batch, projects outcomes, computes required embeddings, and persists bounded non-Entity immutable payload/identity/membership/embedding state with zero domain/evidence/manifest/status mutation
  2. Prepare returns a one-time-visible opaque `plan_token` plus plan UUID, hashes, counts, projections, and `expires_at`; only a secure token digest is stored and compared timing-safe; TTL, payload-byte, and active-plan ceilings are enforced
  3. `commit_prepared_catalog_batch` accepts only `plan_token` (and optional expected hash), revalidates the frozen artifact, and performs no external embedding/LLM/queue/network call
  4. Token is bound to one immutable group/batch/schema/hash/payload; expired/discarded/consumed plans cannot revive; discard terminates only unconsumed plans without deleting domain data
  5. Dry-run remains zero-write; existing `upsert_catalog_batch` remains available

**Plans**: 6/6 plans executed

- [x] 03A-01-PLAN.md
- [x] 03A-02-PLAN.md
- [x] 03A-03-PLAN.md
- [x] 03A-04-PLAN.md
- [x] 03A-05-PLAN.md
- [x] 03A-06-PLAN.md

**Research**: required during planning (payload chunking, property limits, token CAS)
**Stop condition**: If Neo4j cannot store immutable prepared payloads, stop and report — do not weaken the contract
**Gate**: Phase 3A verified 6/6; prepare/discard zero-domain-write and token/control-plane tests passed; `ready_for_phase_3b=true`; Phase 3B domain co-commit unblocked for discussion/planning

### Phase 3B: Atomic Catalog, Exact Evidence, and Durable Manifest Writes

**Goal**: Commit or roll back catalog data, exact evidence, and batch membership together with no partial domain success
**Depends on**: Phase 3A prepare/discard and token gates green
**Requirements**: PLAN-13, PLAN-14, PLAN-15, PLAN-16, EVID-07, EVID-08, EVID-09, EVID-10, EVID-11, MANI-01, MANI-02, MANI-03, MANI-04, MANI-06, MANI-07, TEST-06, TEST-07
**Success Criteria** (what must be TRUE):

  1. Successful commit writes all domain data, exact evidence, durable manifest, terminal batch status, and terminal prepared-plan state in one Neo4j transaction where supported
  2. Any failure rolls back completely; stranded `COMMITTING` has deterministic recovery; identical replay and concurrent same-token commits yield one logical committed batch without duplicate domain/evidence/manifest/status
  3. Explicit `CatalogEvidenceLink` records replace Cartesian multi-source target arrays; missing/mismatched targets fail atomically; identical links coalesce; immutable link conflicts return `provenance_link_conflict`; control records never carry Entity labels
  4. Manifest membership is exact for created, updated, and unchanged objects and is never inferred from `entity.batch_id` / `edge.batch_id`
  5. Search interoperability for catalog entities/edges remains; fault injection between persistence steps leaves neither a partial graph nor a partial manifest

**Plans:** 6/6 plans executed

Plans:
**Wave 1**

- [x] 03B-01-PLAN.md — Wave 0 RED Nyquist scaffolds + fail-closed gate runner skeleton

**Wave 2**

- [x] 03B-02-PLAN.md — Pure manifest canonicalize/chunk + additive commit response fields

**Wave 3** *(blocked on Wave 2)*

- [x] 03B-03-PLAN.md — Evidence + manifest store Cypher, constraints, terminal agree, plan lock

**Wave 4** *(blocked on Wave 2+3)*

- [x] 03B-04-PLAN.md — Shared atomic writer; upsert+commit co-commit; fault injection

**Wave 5** *(blocked on Wave 4)*

- [x] 03B-05-PLAN.md — Stranded COMMITTING recovery, stable replay, concurrency arbitration

**Wave 6** *(blocked on Wave 3–5)*

- [x] 03B-06-PLAN.md — Live Neo4j proof, 24/24 edge map, gate ledger, capabilities.manifests flip

**Research:** complete (`03B-RESEARCH.md`) — single-tx ceilings, chunk policy, recovery algorithms
**Stop condition:** If Neo4j cannot co-commit domain+evidence+manifest+terminal states in one transaction, stop and report — do not weaken the contract
**Gate:** Passed at product HEAD `1f9a7d7`: final live gate ready/complete true; current safety green; historical `a67789a` test-policy event retained; goal 5/5, requirements 17/17, Nyquist 17/17, security 16/16, deep review clean. Phase 4 unblocked.

### Phase 4: Manifest-Backed Verification and Read-Only Diagnostics

**Goal**: Operators can inspect committed membership, evidence, and edges and verify batches from durable manifests while catalog mutation is disabled
**Depends on**: Phase 3B atomic commit + manifest + concurrency gates green
**Requirements**: IDEN-08, MANI-05, VERI-01, VERI-02, VERI-03, VERI-04, VERI-05, VERI-06, RESE-01, RESE-02, RESE-03, GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, GATE-06, EVID-12, EVID-13, TEST-08, TEST-09
**Success Criteria** (what must be TRUE):

  1. `get_catalog_batch_manifest` returns group, batch, hashes, identity schema version, exact counts, and paginated compact item identities for committed membership including unchanged shared entities
  2. Batch-only `verify_catalog_batch` uses the committed manifest as membership authority, reports missing members and extra duplicates, checks exact types/UUIDs/endpoints/embeddings/evidence/manifest consistency, and fails with `manifest_mismatch` when no valid manifest exists
  3. `resolve_typed_edges` and `get_catalog_evidence` return group-isolated read-only diagnostics without embedding or writes
  4. Separate read/write feature gates keep capabilities and catalog diagnostics usable when writes are disabled; read paths never initialize/repair schema or open write transactions
  5. Explicit-key verification remains available; gate/registration tests prove read tools work while writes are off

**Plans**: 6/6 plans complete

**Wave 1**

- [x] 04-01-PLAN.md — Wave 0 behavioral tests and fail-closed Phase 4 gate scaffold

**Wave 2** *(blocked on Wave 1)*

- [x] 04-02-PLAN.md — Split read/write gates, missing-status truth, bounded page limits, capability foundations

**Wave 3** *(blocked on Wave 2)*

- [x] 04-03-PLAN.md — Durable manifest reassembly, integrity checks, and canonical paginated membership read

**Wave 4** *(blocked on Wave 3)*

- [x] 04-04-PLAN.md — Manifest-authoritative batch verification, exact drift, evidence identities, explicit-key compatibility

**Wave 5** *(blocked on Wave 4)*

- [x] 04-05-PLAN.md — Read-only typed-edge resolution and bounded evidence diagnostics

**Wave 6** *(blocked on Wave 5)*

- [x] 04-06-PLAN.md — Additive 28-tool registration, final capability flip, and fail-closed Phase 4 gate

**Research**: complete (`04-RESEARCH.md`) — manifest reassembly, pagination, verification authority, split gates
**Planning gate**: passed after one revision; 21/21 requirements, D-01–D-31, 42/42 edge probes, 31/31 decision coverage
**Gate**: Passed — goal 5/5 truths; requirements_verified 21/21; Nyquist 21/21 req + 42/42 edge probes; security closed 11/11; review clean; `manifest_verification=true`; `ready_for_phase_5=true`; `canary_executed=false`; historical `a67789a` two-axis retained; Phase 5 unblocked
**Stop condition**: Any invalid/missing manifest, cross-group read, read-side mutation, expected-from-observed verification, or legacy-tool regression blocks Phase 5

### Phase 5: Verification, Security, Compatibility, and Migration Docs

**Goal**: Maintainers can prove catalog-v2 pre-canary readiness with truthful checks, isolation, security, compatibility, and migration guidance without executing a canary
**Depends on**: Phase 4 complete
**Requirements**: IDEN-13, SAFE-03, SAFE-04, SAFE-06, SAFE-07, SAFE-09, SAFE-10, TEST-10, TEST-11, TEST-12, DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05, DOCS-06, REPT-01
**Success Criteria** (what must be TRUE):

  1. Deterministic catalog paths never invoke prohibited Graphiti tools, LLM extraction, async queue ingestion, implicit endpoints, or communities; conflicts fail closed; logs stay free of payloads, source text, credentials, auth headers, raw tokens, and unsafe exceptions
  2. All 14 legacy MCP tools retain names and public contracts; seven catalog tool names remain registered; every read/write stays `group_id`-isolated on Neo4j 5.26+ only
  3. Live Neo4j tests on `oracle-catalog-tool-test` prove atomic rollback, search interop, exact evidence/manifest behavior, control labels excluded from entity search, and zero writes outside the test group
  4. Operator and migration docs cover tool inventory, catalog-v2 grammar/map/hash/capabilities/prepare/evidence/manifest/gates/errors/config, obsolete pre-hardening identities/hashes, no automatic migration, and offline canary-artifact regeneration without running the canary
  5. Final structured report sets `canary_executed=false` and sets `ready_to_regenerate_canary=true` only after every stated available gate reports pass/fail/skip truthfully

**Plans**: TBD

## Progress

**Execution Order:**
v1.0 Phase 1 → v1.0 Phase 2 (shipped) → Phase 0 → 1 → 2 → 3A → 3B → 4 → 5. Phase 6 canary is separate.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| v1.0 Phase 1. Typed Catalog Primitives | 8/8 | Complete | 2026-07-17 |
| v1.0 Phase 2. Provenance and Atomic Batch | 6/6 | Complete | 2026-07-17 |
| Phase 0. Baseline, Inventory, and Compatibility Policy | 2/2 | Complete | 2026-07-17 |
| Phase 1. Strict Contracts and Catalog-v2 Identity | 12/12 | Complete; ready_for_phase_2=true | 2026-07-18 |
| Phase 2. Topology Authority, Evidence Contract, Hashes, Capabilities | 5/5 | Complete; ready_for_phase_3a=true | 2026-07-18 |
| Phase 3A. Immutable Prepare/Commit Control Plane | 6/6 | Complete; ready_for_phase_3b=true | 2026-07-18 |
| Phase 3B. Atomic Catalog, Exact Evidence, Durable Manifest Writes | 6/6 | Complete; ready_for_phase_4=true | 2026-07-18 |
| Phase 4. Manifest-Backed Verification and Read-Only Diagnostics | 6/6 | Complete; ready_for_phase_5=true; manifest_verification=true | 2026-07-18 |
| Phase 5. Verification, Security, Compatibility, and Migration Docs | 0/TBD | Not started; Phase 4 dependency satisfied | - |

## Coverage

| Phase | Requirement count | Categories |
|-------|------------------:|------------|
| Phase 0 | 8 | BASE, SAFE (isolation/worktree/remote/canary-ban) |
| Phase 1 | 23 | CONT, IDEN foundation, SAFE-05/08, TEST-01/03 |
| Phase 2 | 34 | EDGE, HASH, CAPA, EVID contract (01–06, 14), TEST-02/04 |
| Phase 3A | 18 | PLAN control plane (01–12, 17–20), SAFE-11, TEST-05 |
| Phase 3B | 17 | PLAN domain-tx (13–16), EVID persist (07–11), MANI write, TEST-06/07 |
| Phase 4 | 21 | IDEN-08, MANI-05, VERI, RESE, GATE, EVID-12/13, TEST-08/09 |
| Phase 5 | 17 | IDEN-13, SAFE (security/compat), TEST-10/11/12, DOCS, REPT |
| **v1.1 total** | **138** | All v1.1 |

- v1.1 requirements: 138
- Mapped: 138/138
- Orphans: 0
- Duplicates: 0

## Explicit Non-Goals (v1.1)

- Real canary execution or production/`oracle-catalog-v2` writes (Phase 6 separate)
- Automatic catalog-v1 → catalog-v2 identity migration
- Oracle/SQL/PL/SQL parsing, relationship inference, object-context/path/impact tools
- Catalog delta/retirement, business-transaction entities
- FalkorDB/Kuzu/Neptune catalog portability claims
- Deployment, push/merge/tag, graph clear/delete, full 14k ingest
- Multi-backend catalog claims beyond Neo4j 5.26+

---
*Roadmap created: 2026-07-17 for milestone v1.1*
*Reconciled: 2026-07-17 to graphiti_mcp_pre_canary_roadmap_en.md (Phase 0/1/2/3A/3B/4/5)*
