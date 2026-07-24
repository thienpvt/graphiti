# Project Research Summary

**Project:** Deterministic Catalog Ingestion for Graphiti MCP — v1.2 FE/BO Catalog Pilot and Object Context
**Domain:** Additive MCP catalog-v2 pilot (offline sample conversion + one exact read-only context tool)
**Researched:** 2026-07-24
**Confidence:** HIGH

## Executive Summary

v1.2 is thin additive pilot on shipped v1.1 catalog-v2 substrate. Goal: prove deterministic FE connected sample and BO structural sample from frozen `catalog/catalog.json` authority (2 docs, 1,261 tables, 10,649 columns, 434 FE-only relationships, 0 BO relationships), ingest via existing prepare/token-commit path into isolated test group, and expose one new read-only MCP tool `get_catalog_object_context` returning typed focal object, bounded one-hop neighbors, evidence excerpts, confidence, and source locators. No LLM, no Docling, no full catalog ingest, no invented BO edges, no FE/BO maps, no multi-hop/path/impact, no images in object context, zero new dependencies, no v1.1 final canary Gates 0-10 replay.

Recommended approach: offline scripts own authority load/sample/convert into new `catalog/pilot-v12-requests/` artifacts; runtime reuses prepare (immutable control-plane plan, no domain writes, no embeddings) and commit (embed stored payload then one domain transaction); surgical CatalogService/Store/MCP registration for bounded neighbor read. Acceptance is delta-only on source-bound image plus pilot receipts.

Key risks: FE/BO identity collision if database token omitted; bare FK qualification; invented BO relations; frozen v1.1 canary contamination; unbounded one-hop fan-out; prepare/commit boundary misuse; readiness overclaim. Mitigate with plane-qualified keys, fail-closed endpoint resolve, dedicated pilot artifact dir, neighbor default 50 / hard 200, evidence via existing page caps, group_id on every match, and explicit pilot-not-production scope.

## Key Findings

### Recommended Stack

Add **zero** new runtime or dev dependencies. Reuse Python 3.10+, uv lockfiles, FastMCP, Pydantic `CatalogStrictModel`, neo4j 5.26+, existing CatalogService/Store/identity, stdlib JSON/hash/BFS selection, offline builder patterns from `scripts/build_catalog_canary_requests.py`, secret scanner, Dockerfile.standalone. Do not add networkx, jsonschema, orjson, Docling, LLM paths, or Phase-6 canary harness as v1.2 gate.

**Core technologies:**
- Python / uv / existing lockfiles — runtime truth; no lock churn
- Pydantic CatalogStrictModel — validate converted payloads + tool I/O
- neo4j async driver + fixed Cypher — prepare/commit + one-hop neighbor MATCH
- FastMCP additive `@mcp.tool` — register `get_catalog_object_context` only
- Stdlib json/hashlib/uuid/collections — offline convert + deterministic sample
- Native Ollama embedder (shipped) — commit path only; object context never embeds

Detail: `.planning/research/STACK.md`

### Expected Features

**Must have (table stakes):**
- Authority gate on `catalog/catalog.json` inventory + SHA-256
- Deterministic connected FE sample (SVFE_SHB + authoritative FKs)
- Deterministic rich BO sample (MAIN1 structure only; zero BO relations)
- FE/BO isolation (separate manifests, prepares, commits)
- Prepare validates full request; persists immutable canonical control-plane plan; **no domain writes; no embeddings**
- Token-only commit; embeds stored payload before domain transaction; atomic rollback
- Exact focal-object read; bounded one-hop neighbors; stable order + truncation metadata
- Evidence excerpts + source locators + confidence; no-write read posture
- Batch caps 500 / 2,000 / 5,000; zero new deps; frozen v1.1 canary dirs untouched
- New pilot artifact directory per run/version

**Should have (differentiators):**
- Relationship-connected FE canary (not isolated writes)
- Rich BO without invented edges
- Typed context envelope + canonical response digest
- Explicit truncation metadata; negative-delta / zero-write acceptance proof
- Source-scoped run ledger cross-linking digests

**Defer / excluded:**
- Full catalog ingest; production promotion; FE/BO maps; inferred BO FKs
- Multi-hop, path, impact, NL orchestration, Docling/LLM
- Object-context **images** (not in v1.2 product scope)
- Repeat v1.1 canary Gates 0-10

**Object-context bounds (architecture authority):**
- `neighbor_limit` default **50**, hard max **200** (1-hop only)
- Evidence via existing evidence page cap (`max_page_size` / `HARD_MAX_PAGE_SIZE` 500); compact excerpts only
- No image fields in tool contract

Detail: `.planning/research/FEATURES.md` (image claims superseded by this summary + ARCHITECTURE)

### Architecture Approach

Thin additive slice: offline converter/sampler then existing prepare/commit into isolated group then one new read path (UUID probe + bounded RELATES_TO + evidence page). Server never loads 18MB authority on request path. Historical `catalog/canary-v2-requests*` frozen; pilot writes only `catalog/pilot-v12-requests/`.

**Major components:**
1. `scripts/build_catalog_pilot_requests.py` (+ optional pure convert module) — validate, sample FE/BO, map v2 keys, hash, emit pilot artifacts
2. Existing prepare/commit/identity/manifest/evidence — unchanged ingest substrate
3. `get_catalog_object_context` (MCP + CatalogService + one store neighbor helper) — read-only compact DTO
4. `scripts/run_catalog_pilot_acceptance.py` — delta smoke; not Phase-6 canary
5. Source-bound image smoke — prove new tool registration + pilot path; no full canary replay

**Prepare/commit contract (shipped v1.1, do not misstate):**
- Prepare: validate; persist immutable canonical **control-plane** plan; no domain graph writes; no embeddings
- Commit: token only; embed from stored payload; single domain transaction; fail then full rollback

Detail: `.planning/research/ARCHITECTURE.md`

### Critical Pitfalls

1. **FE/BO identity collision / bare FK ends** — include database token in every preimage; require fully qualified endpoints; fail closed on ambiguity
2. **Invented BO relationships** — zero BO relations is source fact; structural sample only
3. **Frozen v1.1 canary contamination** — new `pilot-v12-requests/` only; hash-guard historical dirs
4. **Unbounded one-hop / group_id omit / read mutates** — LIMIT+ORDER; group on every MATCH; `_read_gate` only; no embedder
5. **Prepare/commit authority leak + readiness overclaim** — token binds digest/group/sample/namespace/limits/expiry; prepare may persist control-plane plan but not domain; do not claim production readiness or rerun v1.1 canary
6. **Dirty tree / secret-in-image** — touch only explicit v1.2 paths; narrow COPY; scan image

Detail: `.planning/research/PITFALLS.md` (correct prepare language: control-plane plan may persist; domain must not)

## Implications for Roadmap

Suggested phase structure (gateable; context path parallel converter path then join):

### Phase 1: Object-context models and caps
**Rationale:** No runtime deps; defines contract before store/service
**Delivers:** `catalog_object_context` request/response (`extra=forbid`); neighbor default 50 / hard 200; evidence page bounds; capabilities stub; reject bad group_id/limits
**Addresses:** Exact focal contract, bound validation, zero image fields
**Avoids:** Invented product bounds; image scope creep

### Phase 2: Store bounded neighbor read
**Rationale:** Single new Cypher primitive; unit-testable with fake driver
**Delivers:** Parameterized 1-hop RELATES_TO; group_id required; stable ORDER; LIMIT; allowlisted projection
**Addresses:** Bounded one-hop context
**Avoids:** Unbounded MATCH; label injection; dynamic properties

### Phase 3: Service get_catalog_object_context + unit tests
**Rationale:** Compose resolve + neighbors + evidence; prove no write/embed
**Delivers:** found/missing/integrity paths; truncation flags; confidence + locators + excerpts
**Addresses:** Typed envelope; no-write posture; evidence fidelity
**Avoids:** Read-time repair; search_nodes misuse; image binding

### Phase 4: MCP tool registration
**Rationale:** Thin adapter after service green
**Delivers:** Tool visible; read-only init pattern (mirror get_catalog_evidence)
**Addresses:** Additive MCP surface; existing tools unchanged
**Avoids:** Bootstrap write side effects on read init

### Phase 5: Converter/sampler pure functions + unit tests
**Rationale:** Parallel with 1-4; offline only
**Delivers:** FE connected + BO structural mapping; plane keys PREFIX::{FE|BO}::DB.SCHEMA; explicit evidence_links; stable hashes; tiny fixture tests
**Addresses:** Deterministic samples; FE/BO isolation; authority inventory checks
**Avoids:** BO invented FKs; nondeterministic selection; v1 keys without plane

### Phase 6: Build pilot artifacts from real catalog.json
**Rationale:** Needs pure convert; pins reviewable digests
**Delivers:** catalog/pilot-v12-requests/{manifest,fe,bo}; authority sha pin; refuse overwrite on drift
**Addresses:** New pilot dir; frozen canary dirs untouched
**Avoids:** Writing canary-v2-requests*; full 1261 dump

### Phase 7: Integration prepare/commit + object_context_int
**Rationale:** Join paths; live Neo4j isolated group only
**Delivers:** Token commit FE/BO; context on FE table/column + BO table; group isolation fixtures
**Addresses:** Atomic commit; exact context; caps
**Avoids:** Protected groups; partial writes; late cap checks

### Phase 8: Delta acceptance runner
**Rationale:** One-command offline to runtime proof without Phase-6 canary
**Delivers:** Receipts, declared-delta, zero-write read proof, replay idempotency
**Addresses:** Deterministic acceptance artifacts; negative-delta
**Avoids:** Full v1.1 canary replay; readiness overclaim

### Phase 9: Source-bound image + runtime smoke
**Rationale:** Last; proves packaging of new tool only
**Delivers:** Image digest + source revision; secret/catalog scan; tool list + pilot smoke
**Addresses:** Source-bound image acceptance
**Avoids:** Mutable tag as identity; secret/catalog in layers; Gates 0-10

### Phase Ordering Rationale

- Models then store then service then MCP matches existing catalog tool layering
- Converter/artifacts parallel until integration join
- Acceptance after green int; image last
- Avoids frozen-artifact and canary-replay pitfalls by construction
- Prepare/commit unchanged code path exercised, not reimplemented

### Research Flags

Phases needing deeper research during planning:
- **Phase 5-6:** Exact FE seed/component table ids; BO column-rich table id; fixed DB token string; one-batch vs split FK batch under caps
- **Phase 7:** Pilot group id (oracle-catalog-tool-test vs oracle-catalog-v12-pilot-test)

Phases with standard patterns (skip research-phase):
- **Phase 1-4:** Mirror existing catalog evidence/resolve adapter + Pydantic forbid patterns
- **Phase 8-9:** Thin runner + existing image/secret scan scripts

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Repo lockfiles + zero-dep verdict; all concerns covered |
| Features | HIGH | Scope clear; image fields in FEATURES.md superseded by product correction |
| Architecture | HIGH | Live modules + catalog facts inspected; bounds explicit |
| Pitfalls | HIGH | Repo constraints + v1.1 freeze policy; prepare wording corrected here |

**Overall confidence:** HIGH

### Gaps to Address

- Exact FE connected table set and BO structural table id — choose in plan-phase with reorder-stable fixtures
- Fixed database segment constant for v2 key body (e.g. ORCL) — lock in converter + manifest
- Neighbor/evidence config constants vs CatalogConfig fields — prefer constants if config churn unwanted
- FEATURES.md still lists image limits — treat SUMMARY + ARCHITECTURE as contract authority for v1.2 object context
- Some PITFALLS prepare read-only lines overstate — prepare may write control-plane plan; must not domain-write or embed

## Sources

### Primary (HIGH confidence)

- `.planning/research/STACK.md` — zero-dep stack, conversion/selection/image mechanisms
- `.planning/research/FEATURES.md` — table stakes / anti-features (images stripped for v1.2 context)
- `.planning/research/ARCHITECTURE.md` — component map, bounds 50/200, build order, pilot dir
- `.planning/research/PITFALLS.md` — critical failure modes and phase gates
- `.planning/PROJECT.md` — v1.2 goal, constraints, out-of-scope
- Shipped v1.1 catalog-v2: prepare control-plane plan + token commit embed-then-tx; UUIDv5; evidence; Neo4j 5.26+
- Repo: mcp_server catalog service/store/identity, graphiti_mcp_server.py, models/catalog_*
- Repo: scripts/build_catalog_canary_requests.py, authority hashing, image secret scanner
- Authority facts: catalog/catalog.json — 2 documents, 1,261 tables, 10,649 columns, 434 FE relationships, 0 BO relationships, schemas SVFE_SHB + MAIN1

### Secondary (MEDIUM confidence)

- Exact FE/BO sample member ids — product choice deferred to plan phase
- Config flag names for neighbor caps — may stay module constants

### Tertiary (LOW confidence)

- None material for roadmap structure

---
*Research completed: 2026-07-24*
*Ready for roadmap: yes*
