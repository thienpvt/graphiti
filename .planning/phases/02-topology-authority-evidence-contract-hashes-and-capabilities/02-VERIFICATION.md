---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
verified: 2026-07-18T18:30:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
requirements_score: 34/34
review_status: clean
nyquist_compliant: true
threats_open: 0
api_coverage: 22/22
gate:
  local_gate_pass: true
  ready_for_phase_3a: true
  evaluated_head: d26fe809a4370fc96e126021b44dfddfdd1d567b
  current_head: 0e98a34c5b19ceb7932c43d9b333ec775c62c3a1
  focused_pytest: 927
  topology_evidence_hash_capabilities: 396
  runner_self_tests: 15
  scoped_ruff: pass
  scoped_pyright: pass
  canary_executed: false
  oracle_catalog_v2_queried: false
  availability_probed: false
  no_new_store_or_control_plane_write_path: true
  raw_edge_probe_count: 68
  resolution_count: 68
process_residuals:
  - id: PR-02-02-RED-COMMIT
    severity: non_blocking
    statement: "Plan 02-02 lacks a separately named test(02-02) RED commit; TDD gate documented collection-failure RED narrative then GREEN at c3f8d6f/f3d395f"
    disposition: accepted
---

# Phase 2: Topology Authority, Evidence Contract, Hashes, and Capabilities — Verification Report

**Phase Goal:** Server owns edge topology and freezes the evidence contract before prepare hashing; operators discover capabilities without mutation

**Verified:** 2026-07-18T18:30:00Z  
**Status:** passed  
**Re-verification:** No — initial verification  
**HEAD:** `0e98a34` (ledger-compatible docs-only child of evaluated `d26fe80`)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every approved catalog edge type enforces a finite server-owned `(source_entity_type, target_entity_type)` map; disallowed pairs fail before side effects; unapproved `LikelyReferencesTo`, `MapsTo`, and `SynchronizesTo` remain deferred | ✓ VERIFIED | `EDGE_ENDPOINT_MAP` keys == `CATALOG_EDGE_TYPES` (16); deferred types absent; `validate_edge_endpoint_pair` wired in model + service preflight before resolve/embed/tx; `test_catalog_topology.py` matrix + named spot tests pass |
| 2 | Explicit `CatalogEvidenceLink` schema stable before persistence: one source, one typed target, allowlisted kind, bounds, deterministic identity/hash; no Cartesian multi-source shape | ✓ VERIFIED | `CatalogEvidenceLink` XOR entity/edge target; 6 kinds; finite confidence + SHA-256 format; `NestedProvenancePayload` rejects `entity_targets`/`edge_targets` without conversion; identity helpers + coalesce; Cartesian unit tests pass |
| 3 | Combined batches require lowercase 64-hex `catalog_sha256`; server-computed `request_sha256` covers identity schema, group, batch, catalog hash, and all canonical entity/edge/source/evidence content under one versioned recipe | ✓ VERIFIED | Required `catalog_sha256` Field + format validator; `batch_request_canonical_payload` includes full domain under `CANONICALIZATION_VERSION`, excludes `dry_run`/caller `request_sha256`; `test_catalog_hash.py` mutation/exclusion/coalesce coverage |
| 4 | `upsert_catalog_batch` results (including dry-run) return `identity_schema_version`, server `request_sha256`, `catalog_sha256`, and `batch_uuid` with zero dry-run writes | ✓ VERIFIED | `CatalogBatchWriteResponse` fields present; `test_dry_run_echoes_authoritative_hash_fields_zero_write` pass; service uses `batch_request_sha256` and echoes hashes on gate failure |
| 5 | `get_catalog_capabilities` works after server init even when writes disabled and returns versions, gates, non-reversible namespace fingerprint, registries, endpoint map, limits, and feature flags without secrets | ✓ VERIFIED | MCP tool registered; pure `build_catalog_capabilities`; fingerprint domain-separated; raw namespace never returned; features truthful (`prepare_commit=false`); disabled-writes + redaction tests pass; `get_status` still `status`/`message` |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `mcp_server/src/models/catalog_topology.py` | Server map + validators | ✓ VERIFIED | 16 types, 279 finite pairs, export helper |
| `mcp_server/src/models/catalog_evidence.py` | CatalogEvidenceLink contract | ✓ VERIFIED | XOR target, kinds, bounds |
| `mcp_server/src/models/catalog_batch.py` | Required catalog_sha256 + non-Cartesian provenance | ✓ VERIFIED | NestedProvenancePayload reject legacy |
| `mcp_server/src/models/catalog_edges.py` | Model topology check | ✓ VERIFIED | calls `validate_edge_endpoint_pair` |
| `mcp_server/src/services/catalog_identity.py` | Versioned request hash recipe + evidence identity | ✓ VERIFIED | `batch_request_sha256`, coalesce |
| `mcp_server/src/services/catalog_service.py` | Preflight + dry-run hash echo + evidence counters | ✓ VERIFIED | topology before resolve; `_batch_provenance_item_count` |
| `mcp_server/src/services/catalog_capabilities.py` | Mutation-free capabilities builder | ✓ VERIFIED | pure builder; fingerprint |
| `mcp_server/src/graphiti_mcp_server.py` | MCP registration | ✓ VERIFIED | `get_catalog_capabilities` tool |
| `mcp_server/tests/test_catalog_topology.py` | TEST-02 matrix | ✓ VERIFIED | map completeness + deferred + model reject |
| `mcp_server/tests/test_catalog_evidence.py` | EVID contract tests | ✓ VERIFIED | Cartesian reject + hash stability |
| `mcp_server/tests/test_catalog_hash.py` | TEST-04 hash tests | ✓ VERIFIED | dry-run zero-write + mismatch |
| `mcp_server/tests/test_catalog_capabilities.py` | CAPA tests | ✓ VERIFIED | redaction + disabled writes |
| `mcp_server/tests/catalog_phase2_gate_runner.py` + `run_phase2_gate.py` | Fail-closed gate | ✓ VERIFIED | ledger producer |
| `02-GATE-RESULTS.json` | Local gate ledger | ✓ VERIFIED | `ready_for_phase_3a=true` |
| `02-EDGE-PROBE.json` / `02-EDGE-PROBE-RESOLUTION.json` | 68/68 probe map | ✓ VERIFIED | raw 68, resolution 68 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `EDGE_ENDPOINT_MAP` | `validate_edge_endpoint_pair` | single authority lookup | ✓ WIRED | topology module |
| `CatalogEdgeItem` / `CatalogService` | `validate_edge_endpoint_pair` | model + service preflight | ✓ WIRED | before resolve/embed/tx |
| `endpoint_map_export` | capabilities response | `build_catalog_capabilities` | ✓ WIRED | `endpoint_map=` export |
| `batch_request_canonical_payload` | `batch_request_sha256` | pure digest | ✓ WIRED | identity service |
| `upsert_catalog_batch` service | hash + response echo | dry-run and commit paths | ✓ WIRED | HASH-05 fields |
| MCP `get_catalog_capabilities` | `build_catalog_capabilities` | tool handler | ✓ WIRED | graphiti_mcp_server.py |
| NestedProvenancePayload | CatalogEvidenceLink | evidence_links only | ✓ WIRED | Cartesian rejected mode=before |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| capabilities response | `endpoint_map` | `EDGE_ENDPOINT_MAP` via export | Yes — live map | ✓ FLOWING |
| capabilities response | `namespace_fingerprint` | one-way SHA-256 of configured UUID | Yes — derived, not raw | ✓ FLOWING |
| batch response hashes | `request_sha256` | `batch_request_sha256(request)` | Yes — full-domain recipe | ✓ FLOWING |
| batch request | `catalog_sha256` | required client field, validated | Yes — required lowercase hex | ✓ FLOWING |
| evidence links | exclusive target | Pydantic model validation | Yes — XOR enforced | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Map keys == edge types | `pytest ...::test_edge_endpoint_map_keys_equal_catalog_edge_types` | pass | ✓ PASS |
| Deferred types absent | `pytest ...::test_deferred_edge_types_not_registered` | pass | ✓ PASS |
| Cartesian rejected | `pytest ...::test_batch_rejects_cartesian_entity_targets` | pass | ✓ PASS |
| Dry-run hash echo zero write | `pytest ...::test_dry_run_echoes_authoritative_hash_fields_zero_write` | pass | ✓ PASS |
| Caps disabled writes | `pytest ...::test_build_capabilities_disabled_writes_missing_namespace` | pass | ✓ PASS |
| Namespace redaction | `pytest ...::test_build_capabilities_redacts_namespace_and_secrets` | pass | ✓ PASS |
| Collect TEHC suite | `--collect-only` topology+evidence+hash+capabilities | 396 tests | ✓ PASS |

Full suite not re-run this verification; gate ledger at evaluated HEAD records 927/396/15 green with ruff/pyright pass. Spot-checks confirm contracts still hold at current HEAD (docs-only delta after `d26fe80`).

### Probe / Gate Execution

| Probe / Check | Result | Status |
|---------------|--------|--------|
| `02-GATE-RESULTS.json` `local_gate_pass` | true | ✓ PASS |
| `ready_for_phase_3a` | true | ✓ PASS |
| `nyquist_compliant` | true | ✓ PASS |
| focused_pytest | 927 passed | ✓ PASS (ledger) |
| topology_evidence_hash_capabilities | 396 passed | ✓ PASS (ledger) |
| runner_self_tests | 15 passed | ✓ PASS (ledger) |
| scoped_ruff / scoped_pyright | exit 0 | ✓ PASS (ledger) |
| edge_probe raw/resolution | 68/68 | ✓ PASS |
| safety_no_probe | pass | ✓ PASS |
| no_new_store_write_path | pass | ✓ PASS |
| canary / oracle-catalog-v2 / availability probe | all false | ✓ PASS |
| catalog_neo4j_int | skip (policy) | ✓ SKIP |

Verifier did **not** run Neo4j, canary, live-group, deploy, or `oracle-catalog-v2` actions.

### Requirements Coverage (34/34 Phase 2)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| EDGE-01 | ✓ SATISFIED | Immutable server `EDGE_ENDPOINT_MAP`; no client map field |
| EDGE-02 | ✓ SATISFIED | 16 documented edge types present as keys |
| EDGE-03 | ✓ SATISFIED | ForeignKeyTo Column-Column + Table-Table; dual pairs tested |
| EDGE-04 | ✓ SATISFIED | Calls/ReadsFrom/WritesTo finite products from code-unit sources |
| EDGE-05 | ✓ SATISFIED | TriggerOn/SynonymFor/DocumentedBy/UsesSequence constraints |
| EDGE-06 | ✓ SATISFIED | JoinsWith + finite DependsOn/ReferencesByCode/DerivedFrom |
| EDGE-07 | ✓ SATISFIED | EnforcedBy pairs + existing evidence rule surface |
| EDGE-08 | ✓ SATISFIED | Fail with `edge_endpoint_pair_not_allowed` before side effects |
| EDGE-09 | ✓ SATISFIED | Shared authority on edge + batch; deferred types unregistered |
| HASH-01 | ✓ SATISFIED | Required lowercase 64-hex `catalog_sha256` |
| HASH-02 | ✓ SATISFIED | Full-domain request hash includes schema/group/batch/catalog + entities/edges/sources/evidence |
| HASH-03 | ✓ SATISFIED | Excludes dry_run, caller request_sha256, timestamps, retries, plan tokens |
| HASH-04 | ✓ SATISFIED | Mutation tests: domain field / catalog_sha256 change digest; order-stable |
| HASH-05 | ✓ SATISFIED | Batch response echoes identity_schema_version, request_sha256, catalog_sha256, batch_uuid |
| HASH-06 | ✓ SATISFIED | Caller hash audit-only; mismatch → `content_hash_mismatch` |
| HASH-07 | ✓ SATISFIED | Single `CANONICALIZATION_VERSION` recipe |
| CAPA-01 | ✓ SATISFIED | Tool works with writes disabled / incomplete identity prereqs |
| CAPA-02 | ✓ SATISFIED | package_version, backend, connectivity |
| CAPA-03 | ✓ SATISFIED | gates + boolean configured + non-reversible fingerprint; no raw namespace |
| CAPA-04 | ✓ SATISFIED | identity/canonicalization/catalog schema versions |
| CAPA-05 | ✓ SATISFIED | entity/edge registries + endpoint map export |
| CAPA-06 | ✓ SATISFIED | configured + hard limits including page size placeholders |
| CAPA-07 | ✓ SATISFIED | embeddings/neo4j readiness unknown without mutation |
| CAPA-08 | ✓ SATISFIED | features: prepare/commit false; explicit evidence true; manifest false |
| CAPA-09 | ✓ SATISFIED | `get_status` preserves status/message |
| EVID-01 | ✓ SATISFIED | CatalogEvidenceLink full field set |
| EVID-02 | ✓ SATISFIED | Exclusive complete entity XOR edge target |
| EVID-03 | ✓ SATISFIED | Six-kind allowlist |
| EVID-04 | ✓ SATISFIED | Length/depth/finite bounds |
| EVID-05 | ✓ SATISFIED | Deterministic UUID + content hash helpers |
| EVID-06 | ✓ SATISFIED | Explicit links only; no Cartesian expansion |
| EVID-14 | ✓ SATISFIED | Legacy multi-target shape rejected, no auto-conversion |
| TEST-02 | ✓ SATISFIED | Exhaustive allow/reject topology matrix |
| TEST-04 | ✓ SATISFIED | Hash mutation/exclusion/dry-run zero-write tests |

Phase 3B EVID-07..11 intentionally out of scope.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | No TBD/FIXME/XXX debt markers in Phase 2 product paths under review | — | — |
| `graphiti_mcp_server.py` | IN-01: `get_catalog_capabilities` not in SAFE-08 rewrite set | ℹ️ Info | No request model; non-blocking (02-REVIEW) |
| `catalog_identity.py` / service | IN-02: evidence UUID helper unused on write path | ℹ️ Info | Phase 3B persistence (02-REVIEW) |

### Safety / Scope Stop

- `canary_executed=false`
- `oracle_catalog_v2_queried=false`
- `availability_probed=false`
- `no_new_store_or_control_plane_write_path=true`
- No `prepare*` / `control_plane*` product modules added
- Review: `status: clean` (critical 0, warning 0) after WR-R01/WR-R02
- Security: `threats_open: 0`
- Nyquist: `nyquist_compliant: true` (VALIDATION audit 34/34)
- API coverage: 22/22 INTEGRATE (COVERAGE.md), no OPT-OUT

### Process Residual (non-blocking)

**PR-02-02-RED-COMMIT:** Plan 02-02 SUMMARY records RED as collection failure before GREEN commits `c3f8d6f` / `f3d395f`, without a separately named `test(02-02) RED` commit hash (unlike 02-01’s `bb5d3c4`/`5ae6f72`). Accepted process residual; does not block goal truths or requirements.

### Human Verification Required

None. All five roadmap truths automated; gate safety structural; no UI/live-DB requirement in Phase 2 contract.

### Gaps Summary

No blocking gaps. Phase 2 goal achieved. `ready_for_phase_3a=true` remains valid under ledger policy (docs-only commits after evaluated HEAD `d26fe80`).

---

_Verified: 2026-07-18T18:30:00Z_  
_Verifier: Claude (gsd-verifier)_  
_Method: goal-backward against code + gate ledger + named spot-tests; SUMMARY claims not trusted as sole evidence_
