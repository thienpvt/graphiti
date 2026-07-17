# Phase 0 Baseline

**Date:** 2026-07-18  
**Authority:** Live source and tests are the authority for tool/surface inventory. Committed canary artifacts under `catalog/` are offline historical evidence only — not live graph truth, not hardened catalog-v2 golden values.

## 1. Legacy MCP tools (14)

Source: `rg -n "@mcp\.tool" -A2 mcp_server/src/graphiti_mcp_server.py` (live count = 21 total registrations).

| # | Tool name | Anchor |
|---|-----------|--------|
| 1 | `add_memory` | `mcp_server/src/graphiti_mcp_server.py:385` |
| 2 | `search_nodes` | `mcp_server/src/graphiti_mcp_server.py:521` |
| 3 | `search_memory_facts` | `mcp_server/src/graphiti_mcp_server.py:598` |
| 4 | `update_entity` | `mcp_server/src/graphiti_mcp_server.py:678` |
| 5 | `delete_entity_edge` | `mcp_server/src/graphiti_mcp_server.py:795` |
| 6 | `delete_episode` | `mcp_server/src/graphiti_mcp_server.py:821` |
| 7 | `get_entity_edge` | `mcp_server/src/graphiti_mcp_server.py:850` |
| 8 | `get_episodes` | `mcp_server/src/graphiti_mcp_server.py:877` |
| 9 | `summarize_saga` | `mcp_server/src/graphiti_mcp_server.py:947` |
| 10 | `build_communities` | `mcp_server/src/graphiti_mcp_server.py:1000` |
| 11 | `add_triplet` | `mcp_server/src/graphiti_mcp_server.py:1054` |
| 12 | `get_episode_entities` | `mcp_server/src/graphiti_mcp_server.py:1128` |
| 13 | `clear_graph` | `mcp_server/src/graphiti_mcp_server.py:1164` |
| 14 | `get_status` | `mcp_server/src/graphiti_mcp_server.py:1207` |

## 2. Catalog tools (7)

| # | Tool name | Anchor |
|---|-----------|--------|
| 1 | `upsert_typed_entities` | `mcp_server/src/graphiti_mcp_server.py:1240` |
| 2 | `resolve_typed_entities` | `mcp_server/src/graphiti_mcp_server.py:1269` |
| 3 | `verify_catalog_batch` | `mcp_server/src/graphiti_mcp_server.py:1294` |
| 4 | `upsert_typed_edges` | `mcp_server/src/graphiti_mcp_server.py:1319` |
| 5 | `upsert_provenance` | `mcp_server/src/graphiti_mcp_server.py:1349` |
| 6 | `get_catalog_ingest_status` | `mcp_server/src/graphiti_mcp_server.py:1378` |
| 7 | `upsert_catalog_batch` | `mcp_server/src/graphiti_mcp_server.py:1407` |

**Total MCP tool registrations:** 14 legacy + 7 catalog = **21** (`@mcp.tool` count verified).

## 3. Catalog surface map

Existing paths only (no product edits in Phase 0).

| Surface | Path | Role |
|---------|------|------|
| Models — common | `mcp_server/src/models/catalog_common.py` | Shared catalog types |
| Models — entities | `mcp_server/src/models/catalog_entities.py` | Entity request/shape models |
| Models — edges | `mcp_server/src/models/catalog_edges.py` | Edge request/shape models |
| Models — provenance | `mcp_server/src/models/catalog_provenance.py` | Provenance models |
| Models — batch | `mcp_server/src/models/catalog_batch.py` | Atomic batch request models |
| Models — responses | `mcp_server/src/models/catalog_responses.py` | Response DTOs |
| Identity | `mcp_server/src/services/catalog_identity.py` | Deterministic UUIDv5 helpers |
| Service | `mcp_server/src/services/catalog_service.py` | Orchestration |
| Store | `mcp_server/src/services/catalog_store.py` | Neo4j persistence |
| Config | `mcp_server/src/config/schema.py` (`catalog_upsert`) | Catalog upsert settings |
| Tests — models | `mcp_server/tests/test_catalog_models.py` | Unit models |
| Tests — identity | `mcp_server/tests/test_catalog_identity.py` | Unit identity |
| Tests — service | `mcp_server/tests/test_catalog_service.py` | Unit service |
| Tests — store unit | `mcp_server/tests/test_catalog_store_unit.py` | Unit store |
| Tests — neo4j int | `mcp_server/tests/test_catalog_neo4j_int.py` | Integration (tool-test group only) |
| Tests — canary offline | `mcp_server/tests/test_catalog_canary_scripts.py` | Offline canary workflow |
| Fixture | `mcp_server/tests/fixtures/accept_tab_sanitized.json` | Sanitized unit fixture |
| Builder | `scripts/build_catalog_canary_requests.py` | Immutable request builder |
| Runner | `scripts/run_catalog_canary_batch.py` | Live executor — **banned to execute in Phase 0** |
| Checkpoint | `catalog/catalog.json.graphiti-canary-v2-state.json` | Historical attempt state |
| Manifest | `catalog/canary-v2-requests/manifest.json` | Planned totals + digests |
| Receipts | `catalog/canary-v2-requests/accept-tab.*` | Dry-run/commit/payload receipts |
| Summary | `catalog/CANARY_V2_SUMMARY.md` | Human offline narrative |
| Archived scripts | `tests/script/` | Historical builder/runner copies |

## 4. Offline ACCEPT_TAB historical evidence

Paths, digests, and counts only. Full payloads and source text are not embedded.

| Field | Value |
|-------|-------|
| target_group_id | `oracle-catalog-v2` (inventory offline only; never query or mutate) |
| catalog_sha256 | `3882cb4bc50064215ead782b0fa0dfbf0098cb344b50184e6c207145377e832f` |
| ACCEPT_TAB batch_id | `canary-v2::accept-tab` |
| artifact_sha256 | `a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33` |
| server_request_sha256 | `a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a` |
| dry-run counts (checkpoint) | 10 entities / 16 edges / 1 provenance source |
| planned unique totals (manifest) | 38 entities / 85 edges |
| post-commit note | `catalog/CANARY_V2_SUMMARY.md`: domain commit completed; runner stopped at search retrieval gate because deployed MCP serialization rejected Neo4j `DateTime` values; remaining batches paused until fixed image |
| offline sources | `catalog/CANARY_V2_SUMMARY.md`, `catalog/catalog.json.graphiti-canary-v2-state.json`, `catalog/canary-v2-requests/manifest.json`, `catalog/canary-v2-requests/accept-tab.dry-run.response.json`, `catalog/canary-v2-requests/accept-tab.commit.response.json` |
| disposition | Historical only; **invalid as hardened catalog-v2 golden**; never query or mutate the live group |

## 5. Check ledger

Filled by Task 2. Status enum: `pass` | `fail` | `skip`.

| name | command | status | exit_code | first_failure_id | notes |
|------|---------|--------|-----------|------------------|-------|
| | | | | | |

## 6. Safety flags

- `canary_executed=false`
- `oracle_catalog_v2_queried=false`
- `product_code_edited=false`
- `remote_ops=false`
