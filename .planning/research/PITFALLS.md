# Pitfalls Research

**Domain:** Deterministic catalog-ingestion MCP tools on Graphiti/Neo4j
**Researched:** 2026-07-16
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Caller- or uuid4-based identity authority

**What goes wrong:**
Entities/edges get random UUIDs (Graphiti `Node.uuid` / `Edge.uuid` default `uuid4`) or trust client-supplied UUIDs. Retries create second nodes/edges. Re-ingest of the same catalog key no longer hits the same Neo4j object. Identity becomes non-idempotent under concurrent or restarted clients.

**Why it happens:**
Installed Graphiti models mint UUIDs at construction (`graphiti_core/nodes.py`, `edges.py`). MCP `add_triplet` does `uuid=source_node_uuid or str(uuid4())`. Semantic tools treat UUID as optional reuse hint, not server-owned deterministic identity. Catalog work needs UUIDv5 over fixed namespace + `group_id|type|key`.

**How to avoid:**
- Server-only UUIDv5: entity = `uuid5(ns, f"{group_id}|{entity_type}|{graph_key}")`; edge = `uuid5(ns, f"{group_id}|{edge_type}|{edge_key}")`; source/batch similarly.
- Reject caller UUID as identity authority; if accepted for diagnostics, compare to server UUID and return `deterministic_uuid_conflict`.
- Pin immutable `GRAPHITI_CATALOG_UUID_NAMESPACE`; never auto-generate per process.
- Do not call `EntityNode()` / `EntityEdge()` without overriding uuid.

**Warning signs:**
- Double ingest yields two UUIDs for one `graph_key`.
- Retry after timeout “creates” instead of “updates”.
- Unit tests that assert uuid4 randomness, or omit namespace config tests.
- Different pods with different namespaces rewrite the whole graph identity set.

**Test evidence:**
- Same `(group_id, type, key)` → identical UUID across process restarts.
- Two concurrent upserts → one node count for that UUID.
- Wrong/mismatched caller UUID → structured `deterministic_uuid_conflict`.
- Namespace change documented as full re-key event (not silent).

**Phase to address:**
Phase 1 — foundation for `upsert_typed_entities` / `upsert_typed_edges` / `resolve_typed_entities`.

---

### Pitfall 2: Non-canonical payload hashing and content-hash drift

**What goes wrong:**
SHA-256 of non-canonical JSON (key order, whitespace, float formatting, null omission, Unicode normalization) differs across clients. False `content_hash_mismatch`, false “changed” updates, or silent acceptance of divergent payloads with same hash if hash algorithm is wrong (MD5, truncated digest, uppercase hex).

**Why it happens:**
Catalog clients serialize differently. Python `json.dumps` defaults are not stable without `sort_keys`, separators, and explicit float/None policy. Project forbids MD5 and requires exactly 64 lowercase hex SHA-256.

**How to avoid:**
- One server-side canonicalize function: sorted keys, UTF-8, no insignificant whitespace, stable nulls, reject NaN/Infinity before hash.
- Always recompute server hash; client hash is audit only → mismatch = `content_hash_mismatch`.
- Persist `content_hash` on node/edge for change detection; compare before SET.
- Never MD5; never store non-64-char digests.

**Warning signs:**
- Same logical payload hashes differ between unit fixtures and MCP client.
- “No-op” upserts flip `updated_at` every time.
- Hash fields appear mixed case or length ≠ 64.

**Test evidence:**
- Fixtures with reordered keys produce identical hash.
- NaN/Infinity rejected before write.
- Mutating one field changes hash and triggers update path only.

**Phase to address:**
Phase 1 — request models + upsert write path.

---

### Pitfall 3: Graphiti `SET n = $entity_data` property clobber and protected-field overwrite

**What goes wrong:**
Stock Neo4j entity save uses `MERGE … SET n = $entity_data` (`node_db_queries.get_entity_node_save_query`, `Neo4jEntityNodeOperations.save`). Full map replace drops properties absent from the payload, rewrites `created_at`, and flattens `attributes` onto the node. Attribute keys can collide with `uuid`, `name`, `group_id`, `name_embedding`, `summary`, `labels`, `created_at`. Upsert “update” becomes destructive reset.

**Why it happens:**
Graphiti designed episode/entity saves for full replacement of known fields. Catalog upserts need preserve-on-update semantics (`created_at` immutable, add `updated_at`, keep endpoint UUIDs, preserve exact `name_raw`/`name_canonical`).

**How to avoid:**
- Do not reuse stock `EntityNode.save` for catalog domain if it cannot preserve fields.
- Catalog Cypher: `ON CREATE SET` vs `ON MATCH SET` with explicit property list; never unvalidated attribute map as full node replace.
- Protected property denylist on request models: `uuid`, `group_id`, `name_embedding`, `labels`, `created_at`, `updated_at`, `content_hash`, identity keys.
- On match: keep original `created_at`; set `updated_at`; only overwrite allowlisted mutable fields when content_hash differs.

**Warning signs:**
- Second upsert nulls previously set catalog columns.
- `created_at` moves forward on retry.
- Attributes appear both nested and top-level inconsistently on read-back.
- `entity_node_from_record` loses fields because they were never written or were stripped as “core” keys only partially.

**Test evidence:**
- Create then update unrelated field → `created_at` unchanged, `updated_at` advanced, other fields intact.
- Attribute named like protected key rejected at validation (`validation_error`).
- Read-back equality of full property set after no-op upsert (same content_hash).

**Phase to address:**
Phase 1 — Neo4j persistence for typed entities/edges.

---

### Pitfall 4: Label accretion, type conflict, and generic Entity pollution

**What goes wrong:**
Save path does `SET n:{labels}` and merges labels without removing wrong types (`list(set(node.labels + ['Entity']))`). A node can accumulate `Table`+`View` or remain bare `Entity` if type omitted. `add_triplet` resolves missing endpoints via extraction/create path and can invent generic nodes. Search and `resolve_typed_entities` then see duplicates, mistypes, or untyped “ghost” endpoints.

**Why it happens:**
Semantic Graphiti merges labels. MCP triplet tool documents optional UUID reuse but creates new `EntityNode` by name when missing. Catalog requires exact one type label from allowlist plus `Entity` (for search compatibility) and forbids implicit endpoint creation.

**How to avoid:**
- Allowlist entity types only; graph-key prefix must match type (`TABLE::` ↔ `Table`, etc.) → else `graph_key_prefix_mismatch` / `entity_type_conflict`.
- Upsert sets exactly `{Entity, <Type>}`; on type conflict with existing different type → fail, do not multi-label.
- `upsert_typed_edges` requires pre-existing typed endpoints; missing → `missing_endpoint`; wrong type → `endpoint_type_mismatch`; bare Entity-only → `generic_endpoint_conflict`.
- Never call `add_triplet` / `add_memory` / queue for catalog tools.

**Warning signs:**
- `labels(n)` grows across retries.
- Edge upsert succeeds when source key never inserted.
- `resolve_typed_entities` reports generic or duplicate hits for one graph_key.
- Search returns catalog rows without expected type filter.

**Test evidence:**
- Upsert Table then same UUID as View → `entity_type_conflict`, no dual labels.
- Edge without endpoints fails; no new Entity created (node count unchanged).
- Generic Entity with same name/key flagged by resolve tool.
- `search_nodes` with type filter still finds correctly labeled catalog entities.

**Phase to address:**
Phase 1 — typed upsert + resolve; regression gate vs `add_triplet` behavior.

---

### Pitfall 5: Cypher label/property injection via dynamic identifiers

**What goes wrong:**
Interpolating client labels or property names into Cypher (`SET n:{labels}`, `SET n:$(node.labels)`, filter `n:Person|Organization`) enables injection if validation is skipped. Existing mitigations (`SAFE_CYPHER_IDENTIFIER_PATTERN`, `validate_node_labels`, tests in `test_node_label_security.py` / `test_search_security.py`) only help if catalog tools reuse them and never build queries from raw strings.

**Why it happens:**
Neo4j labels/relationship types cannot be parameters. Graphiti already interpolates after validation. New catalog code may “temporarily” format f-strings from request fields or allow arbitrary attribute keys as property names.

**How to avoid:**
- Fixed server allowlists for labels, edge types, and property names; map enum → literal in code.
- Re-validate at query-builder boundary even if Pydantic already ran (`model_construct` bypass exists in tests for a reason).
- Parameterize all values (`$uuid`, `$group_id`, maps of known keys only).
- No arbitrary Cypher tool surface.

**Warning signs:**
- Query strings contain raw `request.label` or `request.properties.keys()`.
- Security tests not run in MCP/catalog CI.
- Property names from PDF/DDL flow straight into SET clauses.

**Test evidence:**
- Malicious label/property strings → `validation_error` / `NodeLabelValidationError`, zero DB writes.
- Allowlisted labels produce expected query shape only.
- Keep core `test_node_label_security` + catalog-specific injection cases green.

**Phase to address:**
Phase 1 — models + query builders (must stay green in Phase 2).

---

### Pitfall 6: Missing uniqueness constraints and concurrent double-create

**What goes wrong:**
Installed Neo4j bootstrap creates indexes on `Entity.uuid` / `group_id` / `name`, **not** uniqueness constraints (`graph_queries.get_range_indices`). Concurrent `MERGE` on uuid is usually safe for single-key merge, but concurrent writers using different merge keys (name, graph_key property without constraint), application-level check-then-set, or multi-statement non-transactional writes can still duplicate logical catalog objects. No unique `(group_id, graph_key)` constraint means two UUIDs for one key if identity code diverges.

**Why it happens:**
Graphiti’s semantic model expects uuid primary identity and LLM dedupe, not catalog natural keys. Indexes are non-unique. Application “SELECT then INSERT” without serializable/tx boundaries races.

**How to avoid:**
- Always MERGE on server UUIDv5 (deterministic) inside one write transaction.
- Optional/additional unique constraint on catalog natural key only if property is always present and indexed carefully—do not assume stock Graphiti constraints.
- Never check existence in one session and write in another without MERGE.
- Serialize per `(group_id, batch_id)` or rely on single atomic tx for batch.

**Warning signs:**
- Integration stress with parallel upserts yields count > 1 for one graph_key.
- “resolve” reports duplicates after load tests.
- Code path uses `CREATE` instead of `MERGE`.

**Test evidence:**
- asyncio/parallel double upsert → single node, single edge.
- `resolve_typed_entities` / `verify_catalog_batch` zero duplicates after concurrent runs.
- Failure mid-batch leaves zero partial domain rows (see Pitfall 7).

**Phase to address:**
Phase 1 for single-entity/edge; Phase 2 stress for `upsert_catalog_batch`.

---

### Pitfall 7: Non-atomic multi-statement writes and embedding-after-write

**What goes wrong:**
Writes via `execute_query` auto-commit each statement. Embedding call after partial node write, or status write inside the same failing domain tx, yields half graphs: entities without edges, edges without embeddings, batch status “committed” while domain rolled back (or opposite). PROJECT.md requires embeddings **before** opening Neo4j write tx; batch tools return only after commit/rollback.

**Why it happens:**
Neo4jDriver has real `transaction()` commit/rollback (`neo4j_driver.py`), but most Graphiti saves ignore it. MCP `add_memory` queues async work and returns success on enqueue—explicitly wrong pattern for catalog. Embedding APIs fail independently of Neo4j.

**How to avoid:**
- Precompute all embeddings; on embed failure → `embedding_failed`, no domain write.
- One `async with driver.transaction()` for all domain MERGEs in a request/batch.
- Persist `CatalogIngestBatch` failure status in a **separate** safe transaction after rollback so status never blocks domain atomicity incorrectly—or write status last only on success; failed-status path must not require domain commit.
- Never use `QueueService` for catalog tools.

**Warning signs:**
- Nodes without `name_embedding` after “success”.
- Edge count < entity expectation after error response.
- Tool returns before Neo4j commit.
- Logs show embed HTTP after MERGE.

**Test evidence:**
- Mock embedder raise → zero nodes/edges, `embedding_failed`.
- Fault injection after entity MERGE before edge MERGE → full rollback.
- Success path: embeddings present; verify tool passes.
- MCP client awaits final structured result only after durability.

**Phase to address:**
Phase 1 for entity/edge tools; Phase 2 for batch/status orchestration.

---

### Pitfall 8: group_id isolation failure and cross-tenant bleed

**What goes wrong:**
Reads/writes omit `group_id` predicate. UUID uniqueness is global in practice (uuid index) but natural keys and searches are group-scoped. Wrong default group (empty string vs Falkor `_`) or client-omitted group writes into shared partition. Tests accidentally use live `oracle-catalog-v2` and mutate production-like data.

**Why it happens:**
Graphiti partitions by `group_id` but many getters accept uuid alone (`get_by_uuid`). Fulltext queries embed group filters only when callers pass them. MCP tools have “effective group” defaults.

**How to avoid:**
- Require explicit `group_id` on every catalog tool; validate charset (`validate_group_id`).
- Every MATCH/MERGE includes `group_id` equality on nodes and edges.
- UUID identity string includes `group_id` so groups cannot collide.
- Tests only `oracle-catalog-tool-test`; never `clear_graph` on shared DBs; never touch `oracle-catalog-v2`.

**Warning signs:**
- Search without group returns other tenants’ tables.
- Same graph_key in two groups yields same UUID (identity formula bug).
- Integration tests leave data outside tool-test group.

**Test evidence:**
- Upsert in group A invisible to resolve/search in group B.
- Invalid group_id rejected.
- UUID differs across groups for same type+key.

**Phase to address:**
Phase 1 — all tools; continuous regression.

---

### Pitfall 9: Embedding dimension truncation / missing vectors / search interoperability

**What goes wrong:**
OpenAI/Voyage embedders slice to `embedding_dim` without pad/check (`embedder/openai.py`). Null embeddings skip vector index usefulness. Catalog entities missing `name_embedding` fail hybrid search while fulltext may still hit. Dim mismatch across re-embed breaks cosine. `db.create.setNodeVectorProperty` path differs from map SET—order matters in stock queries.

**Why it happens:**
Graphiti optimistically truncates. Catalog tools must force embed-before-write but may forget fact embeddings on edges or use wrong text (`name` vs `name_canonical` vs graph_key).

**How to avoid:**
- Embed stable searchable text (define one: prefer `name_canonical` or documented field); same string forever for idempotent vectors (note: model upgrades still change vectors—document).
- Assert embedding length == configured dim; fail `embedding_failed` if not.
- Write embeddings inside same domain tx after values known.
- `verify_catalog_batch` / resolve flags unembedded entities.
- Regression: `search_nodes` / `search_memory_facts` still function; catalog nodes appear when labeled Entity.

**Warning signs:**
- resolve reports unembedded after success.
- Vector search empty, BM25 hits only.
- Silent dim slice in logs.

**Test evidence:**
- Stored vector length equals config.
- verify fails if embedding property null.
- search_nodes returns upserted entity by name in tool-test group.

**Phase to address:**
Phase 1 — upsert + verify; search regression gate before Phase 2.

---

### Pitfall 10: Edge identity and endpoint coupling errors

**What goes wrong:**
Edge UUID not deterministic; or deterministic but endpoints recreated with new UUIDs so MERGE attaches to wrong nodes. Stock `add_triplet` regenerates edge UUID when existing edge has different source/target (`graphiti.py`), masking conflicts. Catalog edges must fail on identity conflict, not silently mint new UUIDs. Direction and type (`ForeignKeyTo` vs `Contains`) encoded only in free-text `name`/`fact` if custom type property omitted—search may treat all as `RELATES_TO`.

**Why it happens:**
Graphiti edges are `RELATES_TO` with semantic `name`/`fact`. Catalog allowlisted edge types need durable type property or relationship type strategy without breaking search. Implicit endpoint creation expands graph.

**How to avoid:**
- Edge UUIDv5 from `group_id|edge_type|edge_key`; store `edge_type`, `edge_key`, endpoint UUIDs, content_hash.
- Require endpoints exist and match declared types before MERGE.
- On UUID exists with different endpoints/type → `edge_identity_conflict`.
- Do not clone `add_triplet` UUID regeneration behavior.
- Decide RELATES_TO + `edge_type` property vs typed rels; keep search compatibility explicit.

**Warning signs:**
- Retry creates second edge UUID for same edge_key.
- Edge points at generic Entity.
- verify endpoint UUID ≠ UUIDv5(entity key).

**Test evidence:**
- Idempotent edge upsert same UUID.
- Endpoint swap attempt → conflict error, original edge intact.
- Missing endpoint → no edge row.

**Phase to address:**
Phase 1 — `upsert_typed_edges` + verify.

---

### Pitfall 11: Provenance via `add_episode` / LLM extraction / wrong episodic schema

**What goes wrong:**
Phase 2 provenance implemented by `add_memory`/`add_episode` triggers extraction, async queue, unwanted entities/edges, non-deterministic episode UUIDs. Or invents new labels not in installed schema. MENTIONS links missing; status nodes labeled `Entity` pollute search and communities.

**Why it happens:**
Episodic path is the documented “memory” API. Installed provenance is Episodic + MENTIONS + entity_edges fields—not catalog Source nodes alone. PROJECT.md: if direct episode-entity linking unsupported, document closest representation—do not invent silently.

**How to avoid:**
- `upsert_provenance` writes only allowlisted Source / episodic structures without LLM.
- No queue; synchronous commit.
- `CatalogIngestBatch` label **not** `Entity`; excluded from entity fulltext/vector search and community rebuild inputs.
- `build_communities` compatibility tested but not invoked on upsert path.
- Provenance target missing → `provenance_target_missing`.

**Warning signs:**
- Provenance upsert creates Preference/Procedure entities.
- Batch status appears in `search_nodes`.
- Episode content contains full PDF text logged or embedded unintentionally.

**Test evidence:**
- Provenance upsert: no LLM mock calls; queue empty.
- search_nodes does not return CatalogIngestBatch.
- Targets missing → structured error; no partial mentions if atomic.

**Phase to address:**
Phase 2 — blocked until Phase 1 gate passes.

---

### Pitfall 12: Batch status, retry idempotency, and conflict semantics

**What goes wrong:**
Retries of `upsert_catalog_batch` create duplicate work, flip status incorrectly, or mark success after partial failure. Concurrent batches with same `batch_id` interleave. Failed batch leaves domain dirty while status says failed (or success). `get_catalog_ingest_status` reads stale in-memory state instead of Neo4j.

**Why it happens:**
Status is new Phase 2 concept; easy to keep in process memory (like QueueService). Batch identity UUIDv5(`group_id|Batch|batch_id`) must be MERGE’d carefully relative to domain tx.

**How to avoid:**
- Persist status nodes in Neo4j only; restart-safe.
- Define state machine: pending → committed | failed; retries of committed no-op if same content_hash; conflicting payload → `batch_conflict`.
- Domain tx atomic; status update rules documented (success after domain commit; failure status after rollback).
- Enforce batch limits (500/2000/5000) before any side effect.

**Warning signs:**
- Two status nodes per batch_id.
- Status success with missing edges.
- In-memory dict for status.

**Test evidence:**
- Retry identical batch → committed once, domain counts stable.
- Retry altered payload → `batch_conflict`.
- Crash between domain commit and status (simulate) documented recovery.

**Phase to address:**
Phase 2 — `upsert_catalog_batch` / `get_catalog_ingest_status`.

---

### Pitfall 13: MCP/Pydantic validation gaps (limits, numbers, prefixes)

**What goes wrong:**
Oversized batches OOM Neo4j/MCP. Non-finite floats poison properties. Wrong graph_key prefix accepted. Confidence outside [0,1]. Empty strings for required keys. Extra fields silently ignored or passed to Neo4j. Feature flag off but tools still registered as writable.

**Why it happens:**
MCP tools historically accept loose strings. Catalog PROJECT.md demands strict allowlists, limits, hash format, prefix, finite numbers, protected properties.

**How to avoid:**
- Pydantic models with strict enums, max lengths, collection caps, field validators.
- Tool entry: validate entire request before embed/tx; item-level structured errors with codes from PROJECT.md list.
- `feature_disabled` when catalog upsert config off.
- `invalid_uuid_namespace` when namespace missing/not UUID.

**Warning signs:**
- Tools accept 50k edges.
- NaN stored (Neo4j may reject or corrupt).
- Schema registration missing new tools in MCP list test.

**Test evidence:**
- Parametrized invalid payloads → correct error codes, no writes.
- MCP tool listing includes catalog tools with schemas.
- Limit boundary 500/501 entities.

**Phase to address:**
Phase 1 models + tool registration; Phase 2 extends models for batch/provenance.

---

### Pitfall 14: Regression into semantic ingestion paths

**What goes wrong:**
Catalog feature “reuses” `add_memory`, episode bulk, or triplet helpers “for speed,” reintroducing LLM cost, async success lies, generic endpoints, and non-idempotent UUIDs. Or catalog writes break existing MCP tests / search / communities.

**Why it happens:**
Pressure to ship; large `graphiti_mcp_server.py` monolith encourages copy-paste of existing tools.

**How to avoid:**
- Separate service module; no calls into queue or `add_episode`.
- Phase 1 gate: unit + Neo4j integration + format + typecheck + MCP schema + existing MCP tests + generic-duplicate checks.
- Document semantic vs deterministic guidance for operators.

**Warning signs:**
- Import of `QueueService` from catalog module.
- Tests skipped “need OpenAI”.
- Existing `test_mcp_integration` failures ignored.

**Test evidence:**
- Catalog tests run with embedder mock only (no LLM).
- Full MCP regression suite green.
- Canary group only.

**Phase to address:**
Phase 1 gate (blocker for Phase 2); continuous in Phase 2.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse `EntityNode.save` / `SET n = $map` | Fast wiring to Graphiti | Clobbers properties; weak ON CREATE/MATCH control | Never for catalog domain writes |
| Reuse `add_triplet` for edges | Existing API | Generic endpoints; uuid4; silent UUID regen | Never |
| In-memory batch status | Less Cypher | Lost on restart; lies after crash | Never (QueueService lesson) |
| Skip unique natural-key constraint, rely only on UUIDv5 | Less schema migration | Duplicates if identity bug | Acceptable if UUIDv5+MERGE+tests ironclad |
| Truncate embeddings like OpenAI client | Matches core | Silent search quality loss | Never without length assert |
| Phase 2 before Phase 1 Neo4j green | Schedule optimism | Provenance on broken primitives | Never per PROJECT.md gate |
| Dynamic Cypher from DDL property names | Flexible attributes | Injection + schema chaos | Never — allowlist/map only |
| Shared test group with prod catalog | Real data | Destroys/mutates baseline | Never — `oracle-catalog-tool-test` only |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Neo4j 5.26+ | Assume UNIQUE on uuid | Only non-unique indexes today; MERGE on UUIDv5; add constraints only with migration plan |
| Neo4j transactions | `execute_query` per row | `driver.transaction()` for multi-write atomicity |
| Graphiti labels | Multi-label merge forever | Exact Entity+Type; conflict on mismatch |
| Graphiti search | Status/provenance as Entity | Non-Entity labels for internal nodes; Entity only for searchable catalog types |
| MCP queue | Treat queued success as durable | Catalog tools synchronous; never queue |
| Embedder providers | Different dims / truncation | Config dim assert; pre-tx embed |
| group_id fulltext | Unvalidated group in query string | `validate_group_id` + params/builders |
| Existing MCP tools | Change `add_memory` semantics | Additive tools only; preserve queue behavior |
| UUID namespace env | Auto-gen if missing | Fail closed `invalid_uuid_namespace` |
| Communities | Rebuild on each upsert | Community-neutral upserts; optional compatibility test only |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-row round-trips outside UNWIND | Multi-minute ingest | Batched UNWIND inside one tx (within limits) | Hundreds of entities |
| Embed per entity sequential | Slow batches | `create_batch` before tx | >50 entities |
| Oversized batches (ignore 500/2k/5k) | Timeouts, memory spikes | Hard validation limits | ~10k+ rows unconstrained |
| Full property rewrite every no-op | Write amplification, index churn | content_hash short-circuit | Continuous sync jobs |
| Holding tx open during HTTP embed | Neo4j tx timeouts | Embed first, then short tx | Slow embedder + large batch |
| Unbounded concurrent MCP upserts | Lock contention, pool exhaustion | Semaphore / client-side concurrency caps | Parallel CI + multi-agent |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Interpolating client labels/properties | Cypher injection, graph wipe | Allowlists + `SAFE_CYPHER_IDENTIFIER_PATTERN` + security tests |
| Logging full catalog / source_refs | Secret/PII leakage in logs | Log batch_id and counts only |
| Catalog tools on open NodePort without auth | Unauthorized graph mutation | Network policy; auth at ingress (existing MCP risk) |
| Accepting caller UUID as authority | Identity spoof / overwrite cross-key | Server UUIDv5 only |
| Writing status/searchable Entity for internal control | Data exfil via search tools | Non-Entity internal labels |
| Disabling validation “for bulk speed” | Injection + corruption at 14k scale | Never; limits instead |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Async-style “accepted” responses | Agents retry blindly, duplicate work | Synchronous commit/rollback result |
| Opaque string errors | Cannot automate remediate | Structured codes (`missing_endpoint`, …) |
| Silent generic endpoint creation | Graph fills with junk entities | Hard fail `generic_endpoint_conflict` |
| No resolve/verify tools | Blind re-ingest | Ship resolve + verify in Phase 1 |
| Namespace rotation without docs | Entire identity map “breaks” | Document immutability; explicit migration |
| Mixing semantic add_memory with catalog keys | Non-deterministic overwrites | Operator docs: two ingestion modes |

## "Looks Done But Isn't" Checklist

- [ ] **Idempotent UUID:** Same key → same UUIDv5 across restarts; namespace pinned — verify unit matrix
- [ ] **content_hash:** Canonical SHA-256 64 lowercase; no-op upsert preserves `created_at` — verify integration
- [ ] **Protected properties:** Cannot overwrite uuid/group_id/embeddings/created_at via attributes — verify validation tests
- [ ] **Typed labels:** Exactly Entity+allowlisted type; no label accretion — verify labels(n) after 2 upserts
- [ ] **No generic endpoints:** Edge upsert never CREATE node — verify node count
- [ ] **Atomic tx:** Mid-failure rollback — verify fault injection
- [ ] **Embed before tx:** Failure leaves graph clean — verify mock embedder errors
- [ ] **Embeddings present:** verify/resolve flag unembedded — verify search_nodes hit
- [ ] **group_id isolation:** Cross-group invisible — verify dual-group test
- [ ] **Injection:** Malicious labels/props rejected — verify security tests
- [ ] **MCP schema:** Tools registered, feature flag, limits — verify tool list + boundary tests
- [ ] **Regression:** Existing MCP tests + no queue/LLM on catalog path — verify gate report
- [ ] **Phase 2 status:** CatalogIngestBatch not in entity search — verify search negative test
- [ ] **Provenance:** No add_episode/LLM — verify call spies
- [ ] **Batch retry:** Same batch_id idempotent; conflict on payload change — verify Phase 2
- [ ] **No live group mutation:** Only `oracle-catalog-tool-test` — verify test config constants

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong UUID namespace deployed | HIGH | Stop writers; re-ingest to new group or full rebuild under new namespace; never mix namespaces in one group |
| Generic endpoint pollution | MEDIUM | resolve_typed_entities report; manual/admin delete only with explicit ops (out of scope for tools); re-upsert typed |
| Partial batch without atomicity | HIGH | Identify group; delete only tool-test data if safe; fix tx; re-run verify; re-ingest |
| content_hash algorithm change | HIGH | Version hash property or full rewrite; dual-read period |
| Label type conflicts | MEDIUM | Fail closed; human chooses winning type; single-type repair upsert |
| Missing embeddings | LOW | Re-upsert same payload (idempotent) after embedder fix |
| Batch status desync | MEDIUM | Trust domain verify over status; repair status node from verify result |
| Injection bug shipped | HIGH | Rotate credentials if logs suspect; patch validators; audit recent writes by group |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Caller/uuid4 identity | Phase 1 | Deterministic UUID unit tests + dual-process equality |
| Non-canonical hashing | Phase 1 | Canonicalization vectors + no-op upsert integration |
| SET map clobber / protected fields | Phase 1 | Create/update property preservation Neo4j test |
| Label accretion / generic endpoints | Phase 1 | labels(n) + edge-without-endpoint count tests |
| Cypher injection | Phase 1 | Security unit tests on catalog builders |
| Concurrent double-create | Phase 1 (entity/edge), Phase 2 (batch stress) | Parallel upsert integration |
| Non-atomic writes / embed ordering | Phase 1 tools; Phase 2 batch | Fault-injection rollback + embed-fail clean graph |
| group_id bleed | Phase 1 | Dual-group isolation test |
| Embedding/search gaps | Phase 1 gate | verify unembedded + search_nodes regression |
| Edge identity/endpoints | Phase 1 | Idempotent edge + conflict cases |
| Provenance/LLM/schema | Phase 2 | No LLM/queue spies; schema assertions |
| Batch status/retry | Phase 2 | Retry/conflict/status restart tests |
| Pydantic/MCP validation | Phase 1 (+2 models) | Invalid matrix + tool schema list |
| Semantic path regression | Phase 1 gate (blocker) | MCP suite + Phase 1 report |

### Suggested phase ownership (roadmap)

1. **Phase 1 — Typed primitives:** config/namespace, models, UUIDv5+SHA-256, entity/edge upsert, resolve, verify, Neo4j atomic writes, embed-before-tx, security, search regression, generic-duplicate detection.
2. **Phase 2 — Provenance & batch:** provenance without LLM, CatalogIngestBatch status, atomic `upsert_catalog_batch`, status API, retry/conflict, stress concurrency — only after Phase 1 report green.

## Sources

- Project requirements: `C:/Users/thien/PyCharmMiscProject/graphiti/.planning/PROJECT.md` (identity, phases, error codes, limits)
- Codebase concerns: `C:/Users/thien/PyCharmMiscProject/graphiti/.planning/codebase/CONCERNS.md` (queue durability, embedding truncation, label injection, MCP monolith)
- Graphiti entity save / clobber: `graphiti_core/models/nodes/node_db_queries.py` (`SET n = $entity_data`), `graphiti_core/driver/neo4j/operations/entity_node_ops.py`
- Record attribute flattening: `graphiti_core/driver/record_parsers.py` (`entity_node_from_record`)
- Default uuid4 identity: `graphiti_core/nodes.py`, `graphiti_core/edges.py`
- Triplet generic endpoints + UUID regen: `graphiti_core/graphiti.py` (`add_triplet`), `mcp_server/src/graphiti_mcp_server.py` (triplet + `add_memory` queue)
- Neo4j real transactions: `graphiti_core/driver/neo4j_driver.py` (`transaction`)
- Indexes not uniqueness constraints: `graphiti_core/graph_queries.py` (`get_range_indices`)
- Label/group security tests: `tests/test_node_label_security.py`, `tests/utils/search/test_search_security.py`, `graphiti_core/helpers.py` (`SAFE_CYPHER_IDENTIFIER_PATTERN`)
- Embedding truncation: `graphiti_core/embedder/openai.py`
- Sample catalog shape: `mcp_server/sample_catalog.json`
- Testing layout: `.planning/codebase/TESTING.md`

---
*Pitfalls research for: Deterministic catalog-ingestion MCP tools (Graphiti/Neo4j)*
*Researched: 2026-07-16*
