# Catalog V2 Migration Notes

## Status

Catalog-v1 identity keys and content hashes are **obsolete**.

There is **no automatic migration**, rekey, rewrite, graph rewrite, or in-place conversion from catalog-v1 identities to catalog-v2.

- No graph re-key of existing nodes/edges.
- No bulk rewrite of historical canary or production objects under a new identity schema.
- Callers must rebuild request payloads under catalog-v2 contracts offline.

## Identity rules

- Catalog-v1 keys/hashes must not be treated as valid catalog-v2 identity authority.
- Old `ACCEPT_TAB` SHA values must **never** be reused for catalog-v2 acceptance or identity derivation.
- Historical ACCEPT_TAB / 10-16-1 / 38-85 golden hashes are **not authority**.
- Server-derived UUIDv5 identity under the configured namespace remains the only identity authority for catalog-v2 writes.
- Backend scope for this path: **Neo4j 5.26+ only**. No non-Neo4j portability claim is made here.

## Historical canary materials

- Historical path `catalog/canary-v2-requests/` is **read-only** and **non-authority**.
- Historical canary files must not be used as source-of-truth for live identity, acceptance hashes, or write payloads.
- Hardened offline canary request path (authority for offline regen only):

  `catalog/canary-v2-requests-hardened/`

## Offline regeneration

Regenerate hardened canary request payloads **offline** using the **builder only**. No network, DB, MCP, LLM, or embedder is involved.

Builder script: `scripts/build_catalog_canary_requests.py`

From repository root (hardened mode):

```bash
uv run python scripts/build_catalog_canary_requests.py \
  --mode hardened \
  --fixture mcp_server/tests/fixtures/accept_tab_sanitized.json \
  --output-dir catalog/canary-v2-requests-hardened
```

### Builder constraints

- **Builder only** — no MCP server, no Neo4j/DB, no network, no LLM/embedder calls.
- Offline pure model validation + file write under the output directory.
- After write, builder **reopens** emitted JSON and runs `validate_hardened_request`.
- Default `--mode` is `hardened`. Historical mode remains available only for explicit archival regeneration under `catalog/canary-v2-requests/` and is **not** hardened authority.
- Syntax check only when needed: `uv run python scripts/build_catalog_canary_requests.py --help` or the offline unit tests. Do not treat help as a regeneration run requirement for Phase 5.

### Required hardened payload fields

Hardened offline payloads must satisfy catalog-v2 prepare-shaped contracts, including:

- `identity_schema_version`: exactly `catalog-v2`
- `system_key`: `FE` for the sanitized fixture path
- `group_id`: exactly `oracle-catalog-tool-test`
- remaining prepare domain fields validated by `PrepareCatalogBatchRequest` / `validate_hardened_request`

### Offline validation and tests

- Reopen emitted request JSON and call `validate_hardened_request` (builder does this after write).
- Offline pure tests: `mcp_server/tests/test_catalog_canary_scripts.py`
- Do not rehydrate obsolete catalog-v1 keys/hashes into the regenerated payload set.
- Do not reuse old `ACCEPT_TAB` SHA values.

## Pre-canary readiness (mutation-free)

Before any canary retry, call `get_catalog_capabilities` for truthful runtime readiness:

- `connectivity` — already-initialized raw Neo4j driver `verify_connectivity`; never bootstraps
- `neo4j_indexes` — all 14 Catalog-v2 uniqueness constraints present via `SHOW CONSTRAINTS` (legacy field name; no product Catalog-v2 indexes)
- `embeddings.ready` — Ollama: `GET /api/tags` + configured model present; never embed generation

Probes are mutation-free (no CREATE/DROP/ensure/write/LLM). This readiness work **stops before canary** — no Phase 6 / live canary execution is authorized here.

`get_catalog_capabilities` response shape is **unchanged** by schema bootstrap work. Bootstrap is a separate operator path and must not be invoked by capabilities probes.

## Schema bootstrap (operator-only, Neo4j 5.26+)

Dedicated operator entry: `scripts/bootstrap_catalog_v2_schema.py`.

### Contract

- Uses the **official raw Neo4j async driver** (`neo4j.AsyncGraphDatabase`) only.
- **Never** constructs Graphiti `Neo4jDriver`.
- Exactly **three** `CatalogNeo4jStore` ensure calls, in this order:
  1. `ensure_uuid_uniqueness_constraints`
  2. `ensure_plan_schema`
  3. `ensure_evidence_manifest_schema`
- Then **exactly one** `inspect_catalog_v2_schema_readiness` (canonical matcher).
- Requires exact **14/14** uniqueness constraints present with exact shape.
- Canonical matcher accepts Neo4j `RELATIONSHIP_UNIQUENESS` / `NODE_UNIQUENESS` / `UNIQUENESS`.
- All statements are store-owned `CREATE CONSTRAINT … IF NOT EXISTS` only.
- **No** retry, repair, DROP, rollback, or data rewrite on failure.
- Fail closed on partial readiness or ensure error.

### Statement review (offline)

Review store-owned statement properties on `CatalogNeo4jStore`:
`uuid_constraint_statements`, `plan_schema_statements`, and
`evidence_manifest_schema_statements`. Bootstrap CLI supports only `-h` / `--help`.

### Live bootstrap (operator-approved only; not part of offline remediation)

From repository root, supply Neo4j connection values through `NEO4J_*`, then run with reviewed
generated catalog-local config:

```bash
CONFIG_PATH=mcp_server/config/config-docker-neo4j.catalog-local.yaml uv run --project mcp_server --frozen python scripts/bootstrap_catalog_v2_schema.py
```

```powershell
$env:CONFIG_PATH='mcp_server/config/config-docker-neo4j.catalog-local.yaml'; uv run --project mcp_server --frozen python scripts/bootstrap_catalog_v2_schema.py
```

Do **not** run live bootstrap from canary execution, offline remediation, Phase 5 gates, or
capabilities probes.

## Future live path

When a live write path is **separately approved** (after Phase 5 / canary readiness gates):

1. Preferred large-payload path: `prepare_catalog_batch`
2. Token-only: `commit_prepared_catalog_batch`

Direct upserts (`upsert_catalog_batch`, `upsert_typed_entities`, `upsert_typed_edges`, `upsert_provenance`) are **not** hardened canary authority and are not the preferred large-payload path.

No other live commit sequence is authorized by this note.

## Phase 5 ban

Phase 5 **never**:

- Executes canary against live MCP
- Invokes `scripts/run_catalog_canary_batch.py` (including dry-run)
- Queries or mutates `oracle-catalog-v2`
- Requires live prepare/commit as a Phase 5 step
- Treats historical goldens as current identity authority

Offline builder regeneration and pure tests are documentation/support only; they are not live canary execution.

## Separate residual axis

Keep the historical and current safety axes **separate**. Do not conflate them.

1. **Historical axis** — commit `a67789a04ca0cc2f2a56d7498c65be3460215f77` `test_policy` / `local_neo4j_no_corresponding_data` residual findings. Preserve historical truth; do not rewrite. Not resolved by this migration note.
2. **Current axis** — catalog-v2 identity, hardened offline artifacts, and the active ban on querying/mutating `oracle-catalog-v2` plus Phase 5 canary non-execution.

Old ACCEPT_TAB / 10-16-1 / 38-85 hashes remain historical non-authority under both axes.

## Explicit non-goals / bans

- No secrets in docs or logs
- No deployment actions
- No graph clear / delete / existing-data destruction
- No live-group writes from this note
- No non-Neo4j backend claims
- No automatic migration / rekey / rewrite tooling implied by this document
- No graph re-key of existing catalog objects
