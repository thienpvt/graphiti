# Phase 3B: Atomic Catalog, Exact Evidence, and Durable Manifest Writes - Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 16
**Analogs found:** 16 / 16

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp_server/src/services/catalog_manifest.py` | utility (pure) | transform | `mcp_server/src/services/catalog_prepared_artifact.py` | exact |
| `mcp_server/src/services/catalog_identity.py` | utility | transform | same file (`catalog_prepared_plan_chunk_uuid`) | exact |
| `mcp_server/src/services/catalog_store.py` | store | CRUD + request-response (tx) | same file (plan chunks + provenance + batch status) | exact |
| `mcp_server/src/services/catalog_service.py` | service | request-response + batch | same file (`upsert_catalog_batch` write body + `commit_prepared_*`) | exact |
| `mcp_server/src/models/catalog_responses.py` | model | request-response | `CommitPreparedCatalogBatchResponse` | exact |
| `mcp_server/src/models/catalog_common.py` | config | — | same file (chunk/hard ceilings) | role-match |
| `mcp_server/src/services/catalog_capabilities.py` | utility | transform | same file (`features` dict) | exact |
| `mcp_server/src/graphiti_mcp_server.py` | route | request-response | existing commit tool wiring | role-match |
| `mcp_server/tests/test_catalog_manifest.py` | test | transform | `tests/test_catalog_prepared_artifact.py` | exact |
| `mcp_server/tests/test_catalog_evidence_store.py` | test | CRUD | `tests/test_catalog_store_unit.py` + `test_catalog_evidence.py` | role-match |
| `mcp_server/tests/test_catalog_atomic_writer.py` | test | batch | `tests/test_catalog_service.py` (upsert path) | role-match |
| `mcp_server/tests/test_catalog_commit_recovery.py` | test | request-response | `tests/test_catalog_prepare_service.py` | role-match |
| `mcp_server/tests/test_catalog_concurrency.py` | test | event-driven | prepare CAS tests / service unit | partial |
| `mcp_server/tests/test_catalog_commit_neo4j_int.py` | test | CRUD (live) | `tests/test_catalog_prepare_neo4j_int.py` | exact |
| `mcp_server/tests/test_catalog_phase3b_gate_runner.py` | test | batch | `tests/test_catalog_phase3a_gate_runner.py` + `catalog_phase3a_gate_runner.py` | exact |
| `mcp_server/tests/test_catalog_capabilities.py` | test | transform | same file (extend features) | exact |

## Pattern Assignments

### `mcp_server/src/services/catalog_manifest.py` — NEW pure utility

**Analog:** `mcp_server/src/services/catalog_prepared_artifact.py`

- Canonical JSON: `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`, UTF-8.
- Reject self-hash fields and non-finite values.
- Reuse `chunk_artifact_bytes` / `reassemble_artifact_bytes`; each chunk retains index, offset, byte length, SHA-256, base64 payload.
- Add `build_manifest_body_from_membership`, `serialize_manifest_body`, `manifest_sha256`.
- Sort membership by graph key, edge key, source key, evidence link key.
- Version: `catalog-manifest-v1`.
- Use Phase 3A chunk limits: default 128 KiB, hard 256 KiB, max 128 chunks.

### `mcp_server/src/services/catalog_identity.py` — MODIFY

**Analogs:** `catalog_manifest_uuid`, `catalog_prepared_plan_chunk_uuid`, evidence helpers.

Add `catalog_manifest_chunk_uuid(namespace, group_id, batch_id, chunk_index)` using explicit material `group_id|catalog-v2|ManifestChunk|batch_id|index`. Reuse `catalog_evidence_link_uuid`, `evidence_link_key`, `evidence_canonical_payload`, `coalesce_byte_identical_evidence_links`, and canonical SHA-256; do not invent alternate evidence identity.

### `mcp_server/src/services/catalog_store.py` — MODIFY

**Analogs inside same file:**

| Need | Analog |
|------|--------|
| Evidence/manifest constraints | prepared plan + batch constraints |
| Plan terminal state | `_PLAN_CAS_LEGAL`, `cas_plan_state` |
| Create-once root/chunks | `create_prepared_plan_with_chunks` |
| Target/plan write lock | `lock_provenance_targets` property-touch lock |
| Graphiti links | `upsert_mentions_link`, `append_edge_episode` |
| Batch terminal | `claim_batch_status`, `upsert_batch_status` |
| Schema ensure | identity/plan schema locks + verification |

Evidence:
- Label `CatalogEvidenceLink` only; never `Entity`/`Episodic`.
- Unique `(uuid, group_id)` and `(group_id, link_key)`.
- Fixed allowlist: uuid/group/batch/link/content/source/target/evidence metadata/timestamps only; no embeddings.
- Create once; divergent content hash maps to `provenance_link_conflict`.

Manifest:
- Labels `CatalogBatchManifest`, `CatalogBatchManifestChunk` only.
- Root stores scope, versions, hashes, counts, manifest digest, payload bytes, chunk count.
- Create once; divergent same identity fails as manifest/batch conflict.
- Ordered deterministic chunks; uniqueness races fail closed.

Recovery:
- Lock prepared plan in success transaction via group-scoped fixed query and property touch.
- Internal terminal-agreement read checks plan COMMITTED + batch committed + manifest binding/digest.
- Partial terminal evidence fails closed; no repair/reset.

### `mcp_server/src/services/catalog_service.py` — MODIFY

**Analog A:** `upsert_catalog_batch` existing one-transaction body.

**Analog B:** `_record_failed_status` separate post-rollback transaction.

**Analog C:** `commit_prepared_catalog_batch` digest/load/reassemble/bind/CAS seam ending at COMMITTING.

Extract one `_write_catalog_batch_atomic(tx, projection)`:
1. Lock plan if prepared path; claim/recheck batch.
2. Return stable receipt if terminal agreement holds.
3. Write entities.
4. Write edges.
5. Write sources and explicit Graphiti compatibility links.
6. Write exact evidence records.
7. Write manifest root/chunks.
8. Write batch committed status.
9. CAS plan COMMITTING→COMMITTED if prepared path.

Prepared commit projection comes only from frozen artifact, including frozen embeddings. Direct upsert projection comes from existing preflight + embed-before-transaction. Both call the same writer; dry run remains zero-write. Any raised exception relies on `Neo4jDriver.transaction()` rollback. Failure status, when recorded, occurs only after rollback.

### `mcp_server/src/models/catalog_responses.py` — MODIFY

Extend `CommitPreparedCatalogBatchResponse` additively with bounded committed fields such as `batch_uuid`, `manifest_sha256`, aggregate created/updated/unchanged counts. Never return token, payload, membership arrays, excerpts, or embeddings.

### `mcp_server/src/models/catalog_common.py` — OPTIONAL MODIFY

Reuse Phase 3A hard chunk/payload ceilings for manifest unless live proof requires tighter limits. Do not increase domain batch maxima.

### `mcp_server/src/services/catalog_capabilities.py` — MODIFY

After Phase 3B persistence/live gate (outcome blocked by historical hard gate):
- `prepare_commit=True` remains.
- `explicit_evidence_links=True` remains.
- `manifests=False` while historical `oracle-catalog-v2` read-only probes block the phase (intent was True after clean proof; SUMMARY is authoritative).
- `manifest_verification=False` until Phase 4 (not opened).

Builder remains mutation-free. See `03B-06-SUMMARY.md` status: blocked.

### `mcp_server/src/graphiti_mcp_server.py` — TOUCH ONLY IF NEEDED

No new tool names. Preserve token-only commit request and thin safe wrapper. Response schema changes are additive only.

## Test Patterns

| New test | Analog | Pattern |
|----------|--------|---------|
| `test_catalog_manifest.py` | `test_catalog_prepared_artifact.py` | canonical bytes/chunks/hash/order/tamper/bounds |
| `test_catalog_evidence_store.py` | `test_catalog_store_unit.py`, evidence tests | create-once/conflict/target/label/coalesce |
| `test_catalog_atomic_writer.py` | `test_catalog_service.py` | shared writer and every fault boundary |
| `test_catalog_commit_recovery.py` | `test_catalog_prepare_service.py` | COMMITTING resume, terminal agreement, no revival |
| `test_catalog_concurrency.py` | prepare CAS tests | same-token and same-batch arbitration |
| `test_catalog_commit_neo4j_int.py` | `test_catalog_prepare_neo4j_int.py` | live atomicity/rollback/replay/search/control/isolation |
| Phase 3B gate runner | Phase 3A gate runner | HEAD/content/spec/live fail-closed ledger |
| capabilities extension | existing file | manifests false (blocked), verification false |

Fault injection monkeypatches each store boundary and proves no partial Entity/edge/evidence/manifest/committed status/plan COMMITTED survives.

## Shared Patterns

- **Transaction authority:** `graphiti_core/driver/neo4j_driver.py` commits on clean exit, rolls back on any `BaseException`.
- **Fixed Cypher:** labels/types/property names server-owned; all parameters bound; every read/write group-scoped.
- **Create-once conflicts:** deterministic identity + content hash + uniqueness; no silent rewrite.
- **Cross-process locks:** Neo4j write locks/CAS, never process-local lock alone.
- **Plan state:** COMMITTING→COMMITTED only inside success transaction; never COMMITTING→PREPARED.
- **Logging:** plan UUID/batch ID/counts/error codes only.
- **Capabilities:** flip only after required live gate proof.

## Safe Integration Seams

1. After current commit claim/revalidation: build frozen projection, ensure schema outside success transaction, invoke shared writer, return COMMITTED receipt.
2. Replace direct upsert inline write loop with same writer; preserve current dry-run and embedding order.
3. Extend store schema ensure with verified evidence/manifest constraints before writes.
4. Keep Phase 4 public read tools out of 3B; internal recovery reads only.

## Forbidden

- Split successful commit across Neo4j transactions.
- Reset COMMITTING to PREPARED.
- Infer membership from `batch_id` or live query counts.
- Label evidence/manifest as Entity or attach searchable embeddings.
- Recreate Cartesian provenance.
- External I/O during prepared commit.
- Canary, `oracle-catalog-v2`, deployment, push/merge/tag, `clear_graph`, deletion.
- New dependencies or multi-backend claims.

## Metadata

**Analog search scope:** catalog services/models/tests + Neo4j driver  
**Files classified:** 16  
**Exact/role analogs:** 16  
**Hard stop:** live single-transaction co-commit and rollback proof must pass or Phase 3B stops.
