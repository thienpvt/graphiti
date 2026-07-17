---
phase: 02-provenance-and-atomic-batch
plan: 04
subsystem: api
tags: [atomic-batch, neo4j, uuidv5, provenance, mcp, tdd]

requires:
  - phase: 02-provenance-and-atomic-batch
    provides: deterministic source/batch identities, provenance writers, terminal batch status store
  - phase: 01-typed-catalog-primitives
    provides: typed entity/edge preparation, conflict checks, embeddings, transaction writers
provides:
  - upsert_catalog_batch preflight with deterministic coalescing and endpoint union
  - embed-before-transaction atomic entity/edge/provenance/status commit
  - rollback followed by isolated best-effort failed-status persistence
  - upsert_catalog_batch MCP tool registration
  - dry-run, batch-conflict, unchanged, ordering, rollback, and registration tests
affects:
  - 02-05 live Neo4j batch integration
  - 02-06 operator documentation and final verification

tech-stack:
  added: []
  patterns:
    - Full nested preflight before embedding or writes
    - Same-request entity endpoint union before MATCH-only persisted resolution
    - One domain transaction for entities, edges, provenance, committed status
    - Separate best-effort failed-status transaction after rollback

key-files:
  created: []
  modified:
    - mcp_server/src/services/catalog_service.py
    - mcp_server/src/graphiti_mcp_server.py
    - mcp_server/tests/test_catalog_service.py

key-decisions:
  - "Caller request_sha256 is the external batch-idempotency token when supplied; otherwise the server canonical hash is used"
  - "Edge writes precede append-only provenance attachment inside the same transaction"
  - "Failed status stores only the exception type as bounded error_summary, never exception text or payload"

patterns-established:
  - "Batch order: gate → batch status read → complete preflight → embed all changed objects → schema ensure → one domain transaction"
  - "Batch retry: committed+same hash returns unchanged; committed+different hash returns batch_conflict"
  - "Failure isolation: domain rollback completes before the second terminal-status transaction opens"

requirements-completed: [BATC-03, BATC-04, BATC-05, BATC-06, BATC-07, BATC-08, BATC-09, BATC-10]

coverage:
  - id: D1
    description: Committed batch hash comparison returns unchanged or batch_conflict without mutation
    requirement: BATC-03
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_committed_different_hash_returns_batch_conflict_before_embed
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_committed_same_hash_returns_unchanged_short_circuit
        status: pass
    human_judgment: false
  - id: D2
    description: Same-request endpoint union and complete conflict collection happen before embedding
    requirement: BATC-04
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_dry_run_endpoint_union_no_writes_or_status
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_collects_all_known_conflicts_before_embed
        status: pass
    human_judgment: false
  - id: D3
    description: Changed entity and edge embeddings finish before the single domain transaction
    requirement: BATC-06
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_embedding_completes_before_single_domain_transaction
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_embedding_failure_opens_no_transaction_or_status
        status: pass
    human_judgment: false
  - id: D4
    description: Entities, edges, provenance, and committed status write in one transaction without wiping episodes
    requirement: BATC-07
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_writes_edges_before_provenance_append_in_same_transaction
        status: pass
      - kind: other
        ref: MCP FastMCP list_tools runtime observation for upsert_catalog_batch
        status: pass
    human_judgment: false
  - id: D5
    description: Domain failure rolls back before isolated best-effort failed-status persistence
    requirement: BATC-08
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_domain_failure_rolls_back_then_writes_failed_status_separately
        status: pass
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_failed_status_write_failure_preserves_original_error
        status: pass
    human_judgment: false
  - id: D6
    description: Dry-run fully preflights with no schema, domain, or status write
    requirement: BATC-10
    verification:
      - kind: unit
        ref: mcp_server/tests/test_catalog_service.py#test_batch_dry_run_endpoint_union_no_writes_or_status
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-17
status: complete
---

# Phase 02 Plan 04: Atomic Catalog Batch Orchestration Summary

**Deterministic nested catalog batches now preflight completely, embed before one Neo4j domain transaction, commit provenance plus terminal status atomically, and isolate failed-status persistence after rollback**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-17T00:52:59Z
- **Completed:** 2026-07-17T01:12:54Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added full batch preflight: configured limits, deterministic coalescing, persisted status/hash checks, entity/edge conflicts, same-request endpoint union, dry-run projections
- Added embed-first one-transaction writes for changed entities, changed edges, provenance sources/links, and committed `CatalogIngestBatch` status
- Added rollback-safe failure handling: separate best-effort failed-status transaction with sanitized exception-type summary
- Registered additive `upsert_catalog_batch` FastMCP tool; logs only batch ID and counts
- Preserved `RELATES_TO.episodes` by writing edges before append-only provenance attachment

## Task Commits

1. **Task 1 RED: Batch preflight tests** - `6ca7d39` (test)
2. **Task 1 GREEN: Batch preflight implementation** - `780312d` (feat)
3. **Task 2 RED: Atomic write tests** - `bef2f33` (test)
4. **Task 2 GREEN: Atomic write implementation and MCP tool** - `7b11ae8` (feat)

## Files Created/Modified

- `mcp_server/src/services/catalog_service.py` - batch canonical hash, gates, preflight, embeddings, atomic domain/status orchestration
- `mcp_server/src/graphiti_mcp_server.py` - `upsert_catalog_batch` request/response imports and MCP registration
- `mcp_server/tests/test_catalog_service.py` - preflight, endpoint union, idempotency, dry-run, ordering, rollback, status, tool tests

## Decisions Made

- Treat supplied `request_sha256` as caller's external idempotency token; derive canonical server hash when absent
- Recheck same-request endpoints after entity writes in the domain transaction; persisted endpoints remain MATCH-only
- Store only `type(exc).__name__` in failed status, keeping error summaries bounded and payload/credential-free

## Deviations from Plan

None - plan executed exactly as written. No `catalog_store.py` change was required; Plan 02-02 already removed edge-update episode wiping and supplied every needed primitive.

## Issues Encountered

- Runtime verifier command output was intercepted by the harness on the first in-memory surface attempt. Tool registration was then observed through FastMCP `list_tools`; behavior remained covered by scoped runtime-safe mocks and tests.
- Context7 CLI unavailable; no version-sensitive API change was needed beyond existing FastMCP patterns.

## Verification

- `pytest tests/test_catalog_service.py -k batch -q`: 24 passed
- `pytest tests/test_catalog_store_unit.py tests/test_catalog_service.py -q`: 153 passed
- Scoped Ruff format check: 5 files formatted
- Scoped Ruff check: passed
- Scoped Pyright: 0 errors, 0 warnings
- Runtime MCP surface: `upsert_catalog_batch` listed with nested request schema and `atomic: const true`
- Runtime malformed-input probe: `atomic=false` rejected with Pydantic `literal_error`

## Runtime Verification

**Verdict:** PASS

- FastMCP tool registry exposed `upsert_catalog_batch` with entity, edge, provenance, hash, dry-run, and atomic fields
- Probe confirmed non-atomic requests fail at the public model boundary
- No live database, deployment, graph clearing, deletion, `oracle-catalog-v2`, LLM, queue, or community build was used

## TDD Gate Compliance

- RED: `6ca7d39`, `bef2f33`
- GREEN: `780312d`, `7b11ae8`
- No refactor commit required

## Known Stubs

None. No placeholder batch branch remains.

## Threat Flags

No unplanned threat surface. The new MCP write tool is explicitly covered by plan threats T-02-30 through T-02-34: one transaction, MATCH-only endpoints, hash conflict gate, sanitized status, configured limits.

## User Setup Required

None - no external service configuration added.

## Next Phase Readiness

- Atomic orchestration ready for Plan 02-05 live Neo4j test-group verification
- Integration work must remain constrained to `oracle-catalog-tool-test`; production/live groups remain forbidden

## Self-Check: PASSED

- FOUND: all three modified implementation/test files
- FOUND: `02-04-SUMMARY.md`
- FOUND: commits `6ca7d39`, `780312d`, `bef2f33`, `7b11ae8`

---
*Phase: 02-provenance-and-atomic-batch*
*Completed: 2026-07-17*
