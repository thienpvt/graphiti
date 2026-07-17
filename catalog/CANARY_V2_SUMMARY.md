# Deterministic catalog canary v2

## Scope

- Target group: `oracle-catalog-v2`
- Catalog SHA-256: `3882cb4bc50064215ead782b0fa0dfbf0098cb344b50184e6c207145377e832f`
- Planned unique entities: 38
- Planned unique edges: 85
- Selected documented foreign keys: 3
- Quarantined relationships: 8
- Communities: disabled
- Standard/LLM ingestion: not used

## Immutable artifact workflow

- Builder: `scripts/build_catalog_canary_requests.py`
- Runner: `scripts/run_catalog_canary_batch.py`
- Offline tests: `mcp_server/tests/test_catalog_canary_scripts.py`
- Archived job scripts: `tests/script/`
- Manual nested catalog tool calls: 0 after workflow implementation
- ACCEPT_TAB golden server request SHA-256: `a84e8a7ad71c3d5c9ebd3655a3a049e883b9bf97cc7c5c9ece640c77e1b2539a`
- ACCEPT_TAB artifact SHA-256: `a89e3427a3b1ceec10f36d361fcdbe9e7e30243db4ff51ca59848dfb33968a33`

## Execution status

1. ACCEPT_TAB dry-run passed from immutable artifact: 10 entities, 16 edges, 1 provenance source, zero failures.
2. ACCEPT_TAB commit completed on server with exact approved request hash: 10 entities, 16 edges, 1 provenance source.
3. Read-only batch verification passed: all entities/edges/provenance found, embeddings present, no anomalies.
4. Commit runner stopped at search retrieval gate because deployed MCP serialization rejected Neo4j `DateTime` values. Domain commit remained valid and atomic.
5. `mcp_server/src/utils/formatting.py` now normalizes nested driver date values. Regression tests live in `mcp_server/tests/test_formatting.py`.
6. Remaining batches are intentionally paused until fixed MCP image is deployed. No automatic retry occurred.

## Safety state

- Previous failed `content_hash_mismatch` evidence preserved in checkpoint.
- Immutable retry attempts appended; prior checkpoint fields unchanged.
- `oracle-catalog-v1` untouched.
- Eight quarantined relationships untouched.
- No prohibited maintenance or standard-ingestion calls.
- `safe_for_full_ingest`: false until serialization fix is deployed and all six artifacts pass dry-run, commit, verification, search, and idempotency gates.
