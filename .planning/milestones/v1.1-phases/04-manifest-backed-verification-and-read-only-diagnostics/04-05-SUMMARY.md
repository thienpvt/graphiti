---
phase: 04-manifest-backed-verification-and-read-only-diagnostics
plan: 05
subsystem: catalog-diagnostics
tags: [tdd, rese-01, rese-02, rese-03, evid-12, iden-08, read-only, phase4]

requires:
  - phase: 04-02
    provides: reads_enabled + HARD_MAX_PAGE_SIZE + _read_gate
  - phase: 04-03
    provides: page_members pagination helper
  - phase: 04-04
    provides: edge verify MATCH RETURN content_sha256 patterns
provides:
  - resolve_typed_edges service/store/model surface (RESE-01..03)
  - get_catalog_evidence compact paginated read (EVID-12)
  - match_edges_for_resolve + match_evidence_links_for_target (_read_many only)
  - GREEN edge + evidence + store unit suites
affects:
  - 04-06

tech-stack:
  added: []
  patterns:
    - "resolve_typed_edges mirrors resolve_typed_entities: _read_gate → MATCH → group by key → anomalies"
    - "Edge anomalies without repair: missing/duplicate_edge_key/edge_type_mismatch/endpoint_mismatch/endpoint_pair_violation/uuid_mismatch/missing_embedding/missing_content_hash"
    - "Q2: resolve Cypher always RETURNs e.content_sha256; null live hash is observation anomaly"
    - "Evidence list MATCH by group_id+target_kind+target_uuid ORDER BY uuid; page_members offset/limit"
    - "Compact default omits excerpt; include_excerpts length-bounded by MAX_EVIDENCE_LENGTH"

key-files:
  created: []
  modified:
    - mcp_server/src/models/catalog_entities.py
    - mcp_server/src/models/catalog_responses.py
    - mcp_server/src/services/catalog_store.py
    - mcp_server/src/services/catalog_service.py
    - mcp_server/tests/test_catalog_resolve_edges.py
    - mcp_server/tests/test_catalog_evidence_read.py
    - mcp_server/tests/test_catalog_store_unit.py

key-decisions:
  - "Reuse verify keys Cypher shape for resolve; dedicated match_edges_for_resolve always RETURNs content_sha256"
  - "endpoint_pair_violation from live endpoint labels vs EDGE_ENDPOINT_MAP; report only, no rewrite"
  - "Null content_sha256 → missing_content_hash anomaly (not schema omission)"
  - "Evidence target UUID derived server-side from graph_key/edge_key + namespace; never client UUID authority"
  - "No MCP registration (deferred to 04-06); manifest_verification remains false"

patterns-established:
  - "match_edges_for_resolve / match_evidence_links_for_target via _read_many only"
  - "_analyze_resolve_edge_item anomaly taxonomy parallel to entity resolve"
  - "get_catalog_evidence: gate → derive target uuid → MATCH → page_members → compact project"

requirements-completed:
  - RESE-01
  - RESE-02
  - RESE-03
  - EVID-12
  - IDEN-08

coverage:
  - id: D1
    description: resolve_typed_edges returns uuid, endpoints+graph keys, type, content_sha256, embedding presence
    requirement: RESE-01
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_resolve_edges.py::test_resolve_typed_edges_fields"
        status: pass
    human_judgment: false
  - id: D2
    description: Edge anomaly taxonomy without repair (missing/duplicate/type/endpoint/pair/uuid)
    requirement: RESE-02
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_resolve_edges.py::test_anomalies"
        status: pass
    human_judgment: false
  - id: D3
    description: resolve works writes-off; no embedder/write tx; group-scoped MATCH
    requirement: RESE-03
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_resolve_edges.py::test_writes_off"
        status: pass
    human_judgment: false
  - id: D4
    description: get_catalog_evidence bounded pagination with hard max fail-closed
    requirement: EVID-12
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_read.py::test_evidence_page_bounded"
        status: pass
    human_judgment: false
  - id: D5
    description: Compact default omits full excerpts; optional excerpts length-bounded
    requirement: EVID-12
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_read.py::test_compact_default"
        status: pass
    human_judgment: false
  - id: D6
    description: Full system-scoped graph_key on evidence target identity
    requirement: IDEN-08
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_evidence_read.py::test_full_graph_key_on_target"
        status: pass
    human_judgment: false
  - id: D7
    description: Store resolve/evidence Cypher group-scoped, RETURNs content_sha256, no write verbs
    requirement: RESE-01
    verification:
      - kind: unit
        ref: "mcp_server/tests/test_catalog_store_unit.py::test_build_match_edges_for_resolve_cypher_returns_content_sha256_and_is_read_only"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-19
status: complete
---

# Phase 04 Plan 05: Edge Resolve + Evidence Read Summary

**Read-only resolve_typed_edges and get_catalog_evidence with group isolation, anomaly taxonomy without repair, content_sha256 RETURN, and bounded compact evidence pagination.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-18T19:08:02Z
- **Completed:** 2026-07-18T19:14:05Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- `ResolveTypedEdgesRequest` / `ResolveEdgeResult` / `ResolveTypedEdgesResponse` models
- `GetCatalogEvidenceRequest` / `CompactEvidenceLink` / `GetCatalogEvidenceResponse` models
- Store `match_edges_for_resolve` always RETURNs `e.content_sha256` (Q2); `_read_many` only
- Store `match_evidence_links_for_target` fixed-label MATCH + ORDER BY uuid
- Service `resolve_typed_edges`: anomaly tags, no repair/embed/write, works writes-off
- Service `get_catalog_evidence`: hard max 500 fail-closed, compact default, optional bounded excerpts
- Full graph keys on source/target/entity identities (IDEN-08)
- 24 GREEN tests (8 resolve + 10 evidence + 6 store)
- No MCP registration; `manifest_verification` remains false

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | resolve_typed_edges models store service | `1bb96d4` | catalog_entities/responses/store/service, resolve+store tests |
| 2 | get_catalog_evidence GREEN suite | `c739071` | test_catalog_evidence_read.py |

## Files Created/Modified

| File | Purpose |
|------|---------|
| `mcp_server/src/models/catalog_entities.py` | ResolveTypedEdgesRequest, GetCatalogEvidenceRequest |
| `mcp_server/src/models/catalog_responses.py` | ResolveEdgeResult, evidence response models |
| `mcp_server/src/services/catalog_store.py` | match_edges_for_resolve, match_evidence_links_for_target |
| `mcp_server/src/services/catalog_service.py` | resolve_typed_edges, get_catalog_evidence |
| `mcp_server/tests/test_catalog_resolve_edges.py` | RESE-01..03 GREEN |
| `mcp_server/tests/test_catalog_evidence_read.py` | EVID-12/IDEN-08 GREEN |
| `mcp_server/tests/test_catalog_store_unit.py` | Cypher safety + read-only proofs |

## Decisions Made

- Reuse verify keys Cypher shape for resolve; dedicated match always RETURNs content_sha256
- endpoint_pair_violation from live endpoint labels vs EDGE_ENDPOINT_MAP; report only
- Null content_sha256 → missing_content_hash anomaly
- Evidence target UUID server-derived from graph_key/edge_key + namespace
- MCP registration deferred to plan 06

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Scoped Pyright on resolve-edge tests**
- **Found during:** Wave 5 gate after GREEN
- **Issue:** `_row` endpoint params typed `str` but anomaly fixtures pass `None`; `execute_write` assigned on store though attr unknown
- **Fix:** `source_uuid`/`target_uuid: str | None`; spy real `upsert_edge_item` only (no invented write attr)
- **Files modified:** `mcp_server/tests/test_catalog_resolve_edges.py`
- **Verification:** scoped pyright 0; 90 tests; ruff clean

## Verification Results

- `pytest tests/test_catalog_resolve_edges.py tests/test_catalog_evidence_read.py tests/test_catalog_store_unit.py` → **90 passed**
- `ruff check` on modified files → **All checks passed**
- `pyright` on sources + `test_catalog_resolve_edges.py` → **0 errors**

## Known Stubs

None that block plan goals. MCP tool registration intentionally deferred to 04-06. `manifest_verification` remains false.

## Threat Flags

None new. Mitigations T-04-ISO/READ/INFO/BOUND/INJ covered by unit suite (group_id MATCH, _read_many only, compact default, hard max, fixed labels).

## TDD Gate Compliance

- RED existed as Wave 0 `pytest.fail` scaffolds in plan 04-01
- GREEN: Task 1 `1bb96d4` (resolve + models + store); Task 2 `c739071` (evidence suite)
- Fix: scoped Pyright on resolve-edge tests (new commit, no amend)

## Self-Check: PASSED

- FOUND: `mcp_server/src/services/catalog_service.py` (`resolve_typed_edges`, `get_catalog_evidence`)
- FOUND: `mcp_server/src/services/catalog_store.py` (`match_edges_for_resolve`, `match_evidence_links_for_target`)
- FOUND: `mcp_server/src/models/catalog_entities.py` (`ResolveTypedEdgesRequest`, `GetCatalogEvidenceRequest`)
- FOUND: `mcp_server/src/models/catalog_responses.py` (`ResolveTypedEdgesResponse`, `GetCatalogEvidenceResponse`)
- FOUND: `mcp_server/tests/test_catalog_resolve_edges.py`
- FOUND: `mcp_server/tests/test_catalog_evidence_read.py`
- FOUND commit: `1bb96d4`
- FOUND commit: `c739071`
