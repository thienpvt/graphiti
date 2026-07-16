---
phase: 01-typed-catalog-primitives
verified: 2026-07-16T16:02:51Z
status: gaps_found
score: 3/5 roadmap must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Operator-configured collection limits and strict raw-text validation are enforced"
    status: failed
    reason: "Request schemas hard-cap lists at default values, so configured limits above defaults are unusable. Nested attribute/source_ref raw strings have no length validation."
    artifacts:
      - path: "mcp_server/src/models/catalog_entities.py"
        issue: "max_length=500 ignores configured maximum; nested attributes/source_refs check finite numbers/counts but not nested string length."
      - path: "mcp_server/src/models/catalog_edges.py"
        issue: "max_length=2000 ignores configured maximum; nested attributes check finite numbers/counts but not nested string length."
    missing:
      - "Make request collection validation honor configured maxima, or constrain/document configuration consistently."
      - "Bound nested/raw strings before hashing, embedding, or Neo4j writes."
      - "Add regression tests."
  - truth: "verify_catalog_batch reports edge endpoint mismatches"
    status: failed
    reason: "VerifyEdgeRef carries only edge_type/edge_key. _verify_edges never compares actual relationship endpoints with stored/expected endpoint identity; it incorrectly classifies edge-type mismatch as endpoint_mismatch."
    artifacts:
      - path: "mcp_server/src/models/catalog_entities.py"
        issue: "VerifyEdgeRef has no endpoint expectation fields."
      - path: "mcp_server/src/services/catalog_service.py"
        issue: "_verify_edges ignores returned source/target endpoint fields and appends endpoint_mismatch only when edge type differs."
      - path: "mcp_server/tests/test_catalog_service.py"
        issue: "No test proves endpoint mismatch detection; independent probe returned endpoint_mismatch=[] for mismatched endpoint data."
    missing:
      - "Define endpoint verification semantics and request/store data needed to compare endpoints."
      - "Report actual endpoint mismatches separately from edge-type mismatches."
      - "Add unit and live regression tests."
  - truth: "Phase 1 quality gate and report are green and Phase 2 may start"
    status: failed
    reason: "Independent checks found CONF-04, SAFE-03, and VERI-03 failures absent from the green report. GATE-01/GATE-05 cannot pass while the report says Overall PASS."
    artifacts:
      - path: ".planning/phases/01-typed-catalog-primitives/01-PHASE1-REPORT.md"
        issue: "Overall PASS overstates requirement and focused-test coverage."
    missing:
      - "Fix product gaps, add focused tests, rerun all gates, revise report."
---

# Phase 1: Typed Catalog Primitives Verification Report

**Phase Goal:** Operators can configure and use deterministic typed entity/edge primitives that commit exactly one searchable Neo4j object per identity with no LLM, queue, or implicit endpoint mutation
**Verified:** 2026-07-16T16:02:51Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Roadmap truth | Status | Evidence |
|---|---|---|---|
| 1 | Enable/disable writes; fixed namespace; validated limits; no generated namespace | FAILED | Disabled default, fixed UUID validation, no generation, defaults 500/2000/5000 verified. Configured maxima above defaults fail at fixed Pydantic ceilings; nested raw strings remain unbounded. |
| 2 | Entity/edge writes provide deterministic identity/audit, pre-tx embedding, atomicity, structured errors, no LLM/queue/caller UUID/implicit endpoints | VERIFIED | Product derives UUIDv5/SHA-256, resolves endpoints, embeds before transaction, rechecks invariants, uses group-scoped MERGE plus composite uniqueness. Live retry/conflict/rollback/concurrency/no-LLM/no-queue tests passed. |
| 3 | Resolve/verify are read-only and report all required anomalies | FAILED | Read-only behavior and entity anomalies verified. Edge endpoint mismatch is not implemented: service ignores endpoint fields and treats edge-type mismatch as endpoint mismatch. |
| 4 | Existing search retrieves catalog nodes/facts under the test group with expected filters | VERIFIED | Live Graphiti hybrid search test returned the expected Table and deterministic fact. |
| 5 | Phase 1 quality gate is green; short report explicitly gates Phase 2 | FAILED | Independent rerun passed 180 catalog tests, 86 MCP regressions, Ruff, Pyright, and 18-tool schema listing. Missing product/test coverage above invalidates GATE-01 and report Overall PASS/GATE-05. |

**Score:** 3/5 roadmap truths verified

## Required Artifacts

| Artifact | Status | Details |
|---|---|---|
| `mcp_server/src/config/schema.py` | VERIFIED | `CatalogConfig` substantive, wired into `GraphitiConfig` and service initialization. |
| `mcp_server/src/models/catalog_common.py` | VERIFIED | 15 entity prefixes, 16 edge types, defaults, protected properties, error codes. |
| `mcp_server/src/models/catalog_entities.py` | PARTIAL | Fixed request ceiling; unbounded nested raw strings; `VerifyEdgeRef` lacks endpoint expectations. |
| `mcp_server/src/models/catalog_edges.py` | PARTIAL | Fixed request ceiling; unbounded nested raw strings. |
| `mcp_server/src/models/catalog_responses.py` | VERIFIED | Structured write/resolve/verify responses wired. |
| `mcp_server/src/services/catalog_identity.py` | VERIFIED | Pure UUIDv5/canonical SHA-256 helpers wired. |
| `mcp_server/src/services/catalog_store.py` | VERIFIED | Substantive group-scoped server-owned Cypher, transaction and uniqueness logic. |
| `mcp_server/src/services/catalog_service.py` | PARTIAL | Full orchestration wired; edge endpoint verification incomplete. |
| `mcp_server/src/graphiti_mcp_server.py` | VERIFIED | Four additive tools; all 14 prior tools retained. |
| `mcp_server/tests/test_catalog_*.py` | PARTIAL | 180 pass, including 21 live. Missing the reproduced validation and endpoint-verification failures. |
| `.planning/phases/01-typed-catalog-primitives/01-PHASE1-REPORT.md` | INCORRECT | Detailed report exists and gates Phase 2, but Overall PASS is contradicted by code probes. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Four MCP tools | `CatalogService` | Direct awaited calls | WIRED | Tool listing: 18 total, 4 catalog, 14 existing, none missing. |
| `CatalogService` | identity helpers | UUID/hash preparation | WIRED | Configured namespace plus group/type/key. |
| `CatalogService` | embedder | Await before real write transaction | WIRED | Entity and edge embed phases precede schema/write transaction. |
| `CatalogService` | store/Neo4j | Pre-read, endpoint resolve, in-tx recheck, write | WIRED | Atomic/per-item flows substantive and live-tested. |
| Verify edge rows | endpoint anomaly report | Endpoint comparison | NOT WIRED | Returned source/target data is ignored; edge-type mismatch is mislabeled endpoint mismatch. |
| Catalog writes | Graphiti search | Entity/RELATES_TO properties and vectors | WIRED | Live interoperability passed. |

## Data-Flow Trace

| Artifact | Data | Source | Real flow | Status |
|---|---|---|---|---|
| Entity upsert | UUID, hash, embedding, properties | Validated request, namespace, embedder | Real Neo4j MERGE/vector write | FLOWING |
| Edge upsert | endpoint UUIDs, hash, fact embedding | Existing typed endpoints, request, embedder | Real Neo4j RELATES_TO MERGE | FLOWING |
| Resolve | entity rows/anomalies | Group/key-scoped MATCH | Aggregated correctly | FLOWING |
| Verify edges | relationship endpoints | Group/batch/key-scoped MATCH | Endpoint data discarded | DISCONNECTED |
| Search | names/facts | Existing Graphiti hybrid search | Expected live results | FLOWING |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Catalog behavior plus live Neo4j | `CATALOG_INT_REQUIRED=1 uv run pytest tests/test_catalog_*.py -q --tb=short` | `180 passed in 15.81s`; 21 live | PASS |
| Existing MCP regressions | `uv run pytest tests/test_update_entity.py tests/test_factories.py tests/test_configuration.py tests/test_core_parity.py -q --tb=short` | `86 passed in 1.27s` | PASS |
| Format/lint/type | Catalog-scoped Ruff format/check plus Pyright | 13 formatted; Ruff pass; 0 errors/warnings | PASS |
| MCP schemas | Independent `mcp.list_tools()` assertion | `count=18 catalog=4 existing=14 missing=[]` | PASS |
| Configured entity maximum 501 | Config max 501, construct 501-item request | Pydantic rejects at fixed 500 | FAIL |
| Nested raw-text validation | 1,000,000-character nested attribute in entity/edge | Both accepted | FAIL |
| Edge endpoint mismatch | Verify mocked edge with wrong source/target data | `endpoint_mismatch=[]` | FAIL |

## Probe Execution

No standalone probe scripts declared. Commands above exercised runnable product/test entry points.

## Requirements Coverage

| Requirements | Status | Evidence |
|---|---|---|
| CONF-01..03, CONF-05 | SATISFIED | Disabled default; explicit immutable namespace; Neo4j-only gate. |
| CONF-04 | BLOCKED | Defaults exist; configured maxima above defaults cannot be used. |
| SAFE-01..02, SAFE-04..05 | SATISFIED | Isolation, fixed schemas, structured errors, bounded operational logs. |
| SAFE-03 | BLOCKED | Nested/raw strings remain unbounded. |
| IDEN-01..02, IDEN-05..08 | SATISFIED | Deterministic UUID/hash and conflict/no-op behavior verified. |
| ENTY-01..13 | SATISFIED | Tool, identity, labels, preservation, atomicity, dry-run, concurrency, search verified. |
| RESO-01..04 | SATISFIED | Read-only resolve and required entity anomalies verified. |
| EDGE-01..12 | SATISFIED | Typed endpoint writes, RELATES_TO, preservation, atomicity, concurrency, search verified. |
| VERI-01..02, VERI-04..05 | SATISFIED | Scoped read-only verification, entity anomalies, provenance reporting. |
| VERI-03 | BLOCKED | Edge endpoint mismatch is not actually detected. |
| GATE-01 | BLOCKED | Focused tests miss reproducible requirement failures. |
| GATE-02..04 | SATISFIED | Independent live suite, isolation, tooling, schemas, regressions green. |
| GATE-05 | BLOCKED | Report must not remain Overall PASS. |

**Requirement score:** 50/55 satisfied. Blocked: `CONF-04`, `SAFE-03`, `VERI-03`, `GATE-01`, `GATE-05`. No orphaned Phase 1 IDs.

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `mcp_server/src/models/catalog_entities.py` | 156-158 | Fixed `max_length=500` | BLOCKER | Contradicts operator-configured maximum. |
| `mcp_server/src/models/catalog_edges.py` | 136 | Fixed `max_length=2000` | BLOCKER | Contradicts operator-configured maximum. |
| `mcp_server/src/models/catalog_entities.py` | 85-107 | Recursive validation omits string bounds | BLOCKER | SAFE-03 raw-text gap. |
| `mcp_server/src/models/catalog_edges.py` | 90-101 | Recursive validation omits string bounds | BLOCKER | SAFE-03 raw-text gap. |
| `mcp_server/src/services/catalog_service.py` | 1553-1556 | Edge type mismatch recorded as endpoint mismatch | BLOCKER | VERI-03 false reporting; actual endpoints ignored. |

No unreferenced TBD/FIXME/XXX markers found. Empty-return matches are legitimate no-result read paths.

## Human Verification Required

None. Failures reproduced programmatically. Runtime ordering, rollback, concurrency, isolation, and search invariants have passing tests.

## Gaps Summary

Core write paths are substantive, wired, deterministic, isolated, synchronous, and live-tested. Phase goal still fails: configurable/strict validation is incomplete; edge endpoint verification is absent; report falsely marks the gate green. Phase 2 MUST NOT start. Fix these gaps, add focused/live regressions, rerun all gates, revise `01-PHASE1-REPORT.md`.

---

_Verified: 2026-07-16T16:02:51Z_
_Verifier: Claude (gsd-verifier)_
