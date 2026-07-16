# Project Research Summary

**Project:** Deterministic Catalog Ingestion for Graphiti MCP
**Domain:** Deterministic Neo4j catalog-upsert MCP tools (Graphiti MCP extension)
**Researched:** 2026-07-16
**Confidence:** HIGH

## Executive Summary

This milestone adds synchronous, typed, deterministic, idempotent Neo4j upsert tools to the existing Graphiti MCP server for structured database catalogs (PDF, DDL, Oracle dictionary, SQL-parser output). Experts build this as server-owned identity and Cypher beside-not through-semantic memory: fixed allowlists, UUIDv5 over an immutable deployment namespace, SHA-256 content audit, embed-before-write, real Neo4j transactions, and no LLM, no ingestion queue, no caller UUID authority. Existing add_memory and add_triplet paths remain for narrative memory; they are unsafe for roughly 14k entities and 30k-plus edges because they are async or non-deterministic and can invent generic endpoints.

Recommended approach: implement entirely inside mcp_server/ against installed Graphiti 0.29.2 (PyPI lock) plus Neo4j 5.26+ / driver 5.28.1, reusing FastMCP, GraphitiService client, embedder factory, and Entity/RELATES_TO/Episodic shapes-but do not use stock EntityNode.save, add_triplet, add_episode, or bulk helpers as the write path. Research consensus is a dedicated CatalogNeo4jStore with fixed Cypher, ON CREATE/MATCH property control, and Neo4j-only write gating. Ship Phase 1 primitives first (upsert_typed_entities, upsert_typed_edges, resolve_typed_entities, verify_catalog_batch plus config/models/identity). Phase 2 is blocked until the full Phase 1 gate passes and a Phase 1 report is written. Phase 2 then adds provenance, CatalogIngestBatch status, and atomic upsert_catalog_batch.

Key risks: (1) uuid4 or caller identity yields non-idempotent retries; (2) Graphiti SET n = $entity_data clobbers created_at and audit fields; (3) generic endpoint pollution via triplet-like paths; (4) embed-inside-tx or auto-commit multi-statement partial graphs; (5) Phase 2 provenance inventing schema or re-entering add_episode. Mitigate with server UUIDv5 plus canonical SHA-256, dedicated store, typed-endpoint enforcement, embed-before-tx plus one domain transaction, non-Entity status labels, and a hard Phase 1 gate. Out of scope remains absolute: no K8s deploy, no live-group mutation (oracle-catalog-v2), no full catalog ingest, no clear_graph or deletes, no multi-backend claims, no new runtime packages.

## Key Findings

### Recommended Stack

Use the already-installed MCP stack only. No new runtime packages for Phase 1-2. Milestone write path is Neo4j-only; FalkorDB and other backends return disabled/error and stay untouched.

**Core technologies:**
- Python >=3.10 / uv lockfile - monorepo async runtime; mcp_server/uv.lock is source of truth
- mcp (FastMCP) 1.27.2 - register tools with @mcp.tool() only; no second app/router
- graphiti-core 0.29.2 (PyPI wheel in lock) - models, embedder, search, Neo4j driver; prefer MCP package code against public 0.29.2 APIs
- neo4j driver 5.28.1 + Neo4j server 5.26+ - real Neo4jDriver.transaction(); vector property procs
- Pydantic 2.11.x + pydantic-settings - allowlisted request/config; extend GraphitiConfig for catalog namespace/limits
- Configured EmbedderClient (OpenAI embedder default) - embeddings only; zero LLMClient calls
- stdlib uuid.uuid5 + hashlib.sha256 - identity and audit; MD5 forbidden

**Critical version / provenance notes:**
- Lock resolves graphiti-core from PyPI 0.29.2, not path-editable monorepo graphiti_core/ (local tree also reports 0.29.2). Prefer implementing in mcp_server/; core changes only if an API gap is proven (open decision).
- MCP embedder dimensions default 1536 in Neo4j YAML; do not assume bare env EMBEDDING_DIM 1024.
- MEDIUM residual: whether stock EntityNode.save preserves every catalog property-research recommends not relying on it; default is dedicated Cypher.

### Expected Features

**Must have (table stakes / Phase 1):**
- Catalog config: immutable GRAPHITI_CATALOG_UUID_NAMESPACE, batch limits (500 / 2,000 / 5,000), feature gate
- Strict allowlisted entity/edge models (prefixes, protected props, hash, finite numbers, confidence)
- upsert_typed_entities - sync UUIDv5 + SHA-256 + embed-before-tx + typed Neo4j MERGE
- upsert_typed_edges - typed endpoints required; no implicit create
- resolve_typed_entities - read-only missing/generic/duplicate/mistyped/uuid-mismatch/unembedded
- verify_catalog_batch - read-only identity/type/endpoint/embedding audit
- Sync commit/rollback semantics; no queue/LLM; server UUIDv5 only; group_id isolation; structured error codes
- Preserve created_at; add updated_at; exact name_raw/name_canonical; Entity+type labels for search interop
- Phase 1 gate report before any Phase 2 work
- Tests only on oracle-catalog-tool-test

**Should have (differentiators / Phase 2 after gate):**
- upsert_provenance on installed Episodic + MENTIONS (plus edge episodes as supported)-no add_episode/LLM/queue
- CatalogIngestBatch (non-Entity) + get_catalog_ingest_status
- upsert_catalog_batch - full validate, same-request endpoint resolution, pre-tx embeds, one atomic domain tx, failed-status outside domain tx, retry idempotency, batch_conflict
- Operator docs: semantic-vs-deterministic, namespace immutability, ACCEPT_TAB, rollout/rollback (docs only)

**Defer (v2+ / out of scope this milestone):**
- Full production catalog ingest / canary against live groups
- Kubernetes deployment automation
- Multi-backend catalog persistence claims
- Auto community rebuild on upsert; any add_memory queue redesign; graph cleanup tools

**Anti-features (do not build):** LLM catalog path, async catalog writes, caller UUID identity, auto namespace, implicit endpoints, arbitrary Cypher/labels/properties, MD5, payload logging, invented provenance schema, live-group mutation, clear_graph.

### Architecture Approach

Seven additive MCP tools beside existing semantic tools. Flow: thin @mcp.tool -> CatalogService (validate, UUIDv5, hash, embed-before-tx, feature gate) -> CatalogNeo4jStore (fixed Cypher + driver.transaction()). Reuse live GraphitiService.client for driver/embedder; never QueueService/LLM. Domain entities remain :Entity:<Type> with embeddings for hybrid search; internal status is :CatalogIngestBatch only.

**Major components:**
1. CatalogConfig - immutable UUID namespace, limits, enabled flag (extend schema.py)
2. Catalog models - allowlisted request/response + error codes (separate from semantic entity_types.py)
3. catalog_identity - UUIDv5 + canonical SHA-256
4. CatalogService - orchestration and embed-then-tx ordering
5. CatalogNeo4jStore - dedicated Neo4j persistence (required; not stock model save)
6. Phase 1 tools - entity/edge upsert + resolve + verify
7. Phase 2 tools - provenance, batch status, atomic batch

**Identity formulas (server-only):**
- Entity: uuid5(ns, f"{group_id}|{entity_type}|{graph_key}")
- Edge: uuid5(ns, f"{group_id}|{edge_type}|{edge_key}")
- Source: uuid5(ns, f"{group_id}|Source|{source_key}")
- Batch: uuid5(ns, f"{group_id}|Batch|{batch_id}")

**Edge storage (reconciled):** keep Graphiti search shape ()-[:RELATES_TO {uuid, name, ...}]->() with allowlisted type in name / edge_type property-not free-form relationship types from clients.

### Critical Pitfalls

1. **Caller/uuid4 identity authority** - Always server UUIDv5; reject mismatched caller UUID with deterministic_uuid_conflict; pin namespace.
2. **SET n = $entity_data clobber** - Dedicated ON CREATE/MATCH Cypher; protect created_at/embeddings/identity keys; content_hash short-circuit no-ops.
3. **Generic endpoints / label accretion** - Exact {Entity, Type}; type conflict fails closed; edges never CREATE nodes.
4. **Non-atomic writes / embed-after-write** - All embeddings before open tx; one domain tx; status writes outside domain tx on failure path.
5. **Cypher injection via labels/properties** - Fixed allowlists only; re-validate at query builder; parameterize values.
6. **Phase 2 provenance via add_episode/LLM or Entity-labeled status** - Installed episodic schema only; document gaps; CatalogIngestBatch never :Entity.
7. **group_id bleed / live graph mutation** - Require group_id on every op; tests only oracle-catalog-tool-test; never touch oracle-catalog-v2 or deploy.

## Implications for Roadmap

Based on research, suggested phase structure is exactly two gated implementation phases (no deploy/ingest phase in this milestone).

### Phase 1: Typed Catalog Primitives (Foundation)
**Rationale:** Provenance and batch orchestration depend on trusted identity, typed endpoints, atomic single-tool writes, and verify/resolve. PROJECT.md and all four research files hard-block Phase 2 until the Phase 1 gate is green.
**Delivers:**
- CatalogConfig + feature flag + immutable namespace validation
- Allowlisted Pydantic models + structured error codes
- UUIDv5 + canonical SHA-256 helpers
- CatalogNeo4jStore entity/edge MERGE + read paths (Neo4j-gated)
- upsert_typed_entities, upsert_typed_edges, resolve_typed_entities, verify_catalog_batch
- MCP registration; unit + Neo4j integration tests; format/typecheck; existing MCP regression; generic-duplicate checks
- Short Phase 1 gate report
- Minimal operator docs for Phase 1 tools and namespace immutability
**Addresses:** FEATURES table stakes / P1 matrix; STACK milestone API checklist rows for four Phase 1 tools
**Avoids:** Pitfalls 1-10, 13-14 (identity, hash, clobber, labels, injection, concurrency basics, atomicity, group_id, embeddings/search, edge endpoints, validation, semantic-path regression)
**Gate (exact):** focused unit tests; Neo4j integration on oracle-catalog-tool-test only; formatting; changed-code typecheck; MCP tool listing/schema; relevant existing MCP tests; generic-duplicate checks; Phase 1 report. Phase 2 must not start until all pass.

### Phase 2: Provenance and Atomic Batch Orchestration
**Rationale:** Only after primitives are integration-proven. Batch composes entity/edge/provenance under one domain transaction; status and provenance have distinct failure modes (LLM temptation, search pollution, status/domain desync).
**Delivers:**
- upsert_provenance using installed Episodic + MENTIONS (plus closest compatible episode-edge linking; document if incomplete)
- CatalogIngestBatch + get_catalog_ingest_status (Neo4j-persisted, non-Entity)
- upsert_catalog_batch (validate all -> same-request endpoint map -> embed all -> one domain tx -> status after success / failed-status after rollback; retry idempotency; batch_conflict)
- Full docs: atomicity, limits, ACCEPT_TAB, semantic-vs-deterministic, rollout/rollback guidance (no automation)
- Expanded search_nodes / search_memory_facts / safe build_communities interop on test group only
**Uses:** Neo4jDriver.transaction, EmbedderClient pre-tx, Episodic/MENTIONS save patterns, CatalogConfig limits
**Implements:** Architecture Phase 2 store/status/batch components
**Avoids:** Pitfalls 11-12 (provenance/LLM/schema; batch status/retry); continues 5, 7, 8, 14

### Explicit non-phases (do not schedule as delivery)
- Production full-catalog load, K8s deploy, live-group canary mutation, multi-backend portability, community auto-update, graph deletion utilities

### Phase Ordering Rationale

- Config/models/identity before any Cypher - undefined namespace or allowlists make every UUID and query unsafe
- Entities before standalone edges - edges require pre-existing typed endpoints
- Resolve + verify with upserts in Phase 1 - production-safe operators need preflight/postflight before orchestration
- Dedicated store from day one - stock Graphiti save paths fail property-preservation and multi-statement atomicity (STACK + ARCHITECTURE + PITFALLS agree; conservative choice: dedicated store required, not optional)
- Phase 1 gate before provenance/batch - Phase 2 multiplies bugs in primitives across 14k-scale chunks
- Status outside domain tx - failed-status persistence must not violate domain atomicity
- No deploy/live mutation phases - operational constraint of the milestone

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (persistence slice):** Confirm final Cypher for ON CREATE/MATCH property lists, vector property write order, and protected-field denylist vs entity_node_from_record read-back - patterns known, property map must be specified carefully
- **Phase 1 (edge type durability):** Document search filter contract (EntityEdge.name / edge_types) vs extra edge_type property; keep RELATES_TO
- **Phase 2 (provenance linking):** Installed Graphiti 0.29.2 episode-to-entity-edge linkage completeness is an open decision-if direct linking unsupported, document closest compatible representation; do not invent labels
- **Phase 2 (batch status state machine):** Exact recovery when domain commits but status write fails (trust verify over status)

Phases with standard patterns (skip broad research-phase; plan from this SUMMARY + code):
- **Phase 1 config/Pydantic/MCP registration** - established MCP server patterns
- **Phase 1 UUIDv5/SHA-256 unit logic** - stdlib, fully specified
- **Phase 1 tool surface wiring** - thin FastMCP adapters

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Lockfile + source versions; MEDIUM only on reusing stock save vs dedicated Cypher (resolved conservatively: dedicated store) |
| Features | HIGH | Directly from PROJECT.md Active/Out-of-Scope; no invented features |
| Architecture | HIGH | Repo-sourced component map; dedicated store required across ARCHITECTURE/PITFALLS |
| Pitfalls | HIGH | Code-evidenced (uuid4 defaults, SET map clobber, triplet generics, queue non-durability, index vs uniqueness) |

**Overall confidence:** HIGH

### Gaps to Address

- **Graphiti 0.29.2 lock vs monorepo path:** Prefer MCP-only implementation against PyPI 0.29.2 APIs. If core must change, make explicit version/path decision before coding.
- **Stock save sufficiency:** Treat as insufficient for catalog domain writes unless Phase 1 proves otherwise; plan dedicated Cypher first (conservative reconciliation of STACK prefer-save-if-complete vs ARCHITECTURE/PITFALLS dedicated-required).
- **Provenance schema fidelity on 0.29.2:** Open-plan Phase 2 research spike on Episodic/MENTIONS/entity_edges/episodes list write/read before implementing upsert_provenance.
- **Natural-key uniqueness constraints:** Neo4j Community may lack multi-property node keys; enforce via UUIDv5 MERGE + application conflict detection; optional constraints only with migration plan.
- **Embed text field:** Pin one stable embed source (name_canonical vs name) in Phase 1 plan for idempotent vectors; model upgrades still change vectors-document.
- **Unrelated worktree dirt:** Preserve mcp_server/k8s/graphiti-neo4j.yaml, .codegraph/, mcp_server/sample_catalog.json unless explicitly approved-exclude from feature commits.

## Sources

### Primary (HIGH confidence)
- .planning/PROJECT.md - requirements, allowlists, phase gate, error codes, out of scope
- mcp_server/pyproject.toml, mcp_server/uv.lock - mcp 1.27.2, graphiti-core 0.29.2, neo4j 5.28.1, pydantic 2.11.7
- mcp_server/src/graphiti_mcp_server.py - FastMCP tools, GraphitiService, queue/triplet behavior
- mcp_server/src/config/schema.py, config/config-docker-neo4j.yaml - config + Neo4j defaults
- graphiti_core/driver/neo4j_driver.py - transaction(), execute_query
- graphiti_core/models/nodes/node_db_queries.py, models/edges/edge_db_queries.py - MERGE / SET shapes
- graphiti_core/nodes.py, edges.py, graphiti.py - models, uuid4 defaults, add_triplet/add_episode
- graphiti_core/graph_queries.py - indexes (not uniqueness constraints)
- graphiti_core/helpers.py - label/group validation
- .planning/research/STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

### Secondary (MEDIUM confidence)
- .planning/codebase/* - monorepo architecture/concerns maps
- mcp_server/sample_catalog.json - fixture shape (not full ingest scope)
- Embedding dim / truncation behavior in OpenAI embedder client

### Tertiary (LOW confidence)
- Optional Neo4j composite uniqueness for (group_id, graph_key) - edition-dependent; plan app-level first
- Exact 0.29.2 episode-edge provenance completeness - validate in Phase 2 planning

---
*Research completed: 2026-07-16*
*Ready for roadmap: yes*
