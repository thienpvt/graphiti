# Stack Research

**Domain:** v1.2 FE/BO Catalog Pilot and Object Context (deterministic MCP catalog layer)
**Researched:** 2026-07-24
**Confidence:** HIGH
**Milestone:** v1.2 — subsequent to shipped v1.1 catalog-v2 pre-canary hardening

## Verdict

**Add zero new runtime or dev dependencies.** v1.2 is conversion + selection + one compact read tool + targeted image acceptance on the already-shipped catalog-v2 stack.

Reuse:

- Pydantic strict models (`CatalogStrictModel`, `extra='forbid'`)
- Existing catalog MCP tools (prepare/commit/resolve/evidence/manifest)
- Offline builder patterns in `scripts/build_catalog_canary_requests.py`
- Stdlib JSON/hash/path/graph selection
- Existing source-bound Docker/image/canary scripts

Do **not** reopen v1.1 final canary Gates 0–10. Do **not** add parsers, schema-frameworks, graph libraries, streaming JSON libs, or LLM/Docling paths.

## Recommended Stack

### Core Technologies (unchanged — reuse)

| Technology | Version (repo-grounded) | Purpose | Why for v1.2 |
|------------|-------------------------|---------|--------------|
| Python | `>=3.10,<4` (`mcp_server/pyproject.toml`) | Runtime | Keep 3.10 min; no 3.11-only APIs |
| `uv` + `mcp_server/uv.lock` | lockfile-driven | Install truth | Zero new deps → no lock churn |
| `mcp` (FastMCP) | `>=1.27.2,<2` | Tool registration | One additive `@mcp.tool()` for object context |
| `graphiti-core` | path/editable monorepo source | Embedder + search interop | Catalog writes stay off LLM/queue/`EntityNode.save` |
| `neo4j` driver | `>=5.26.0` (via graphiti-core) | Async Bolt + real txs | Prepare/commit + one hop neighbor MATCH |
| Neo4j server | 5.26+ (compose baseline) | Graph storage | Parameterized Cypher only; fixed labels |
| Pydantic | installed 2.x (`CatalogStrictModel`) | Strict request/response contracts | Validate converted payloads + new tool I/O |
| `pydantic-settings` | installed | CatalogConfig gates | No new config system |
| Native Ollama embedder | already wired v1.1 | Name/fact embeddings before write tx | Unchanged; no new embedder package |
| `pyyaml` | `>=6.0.3` | YAML config | Existing catalog-local compose override |

### Supporting Libraries (already present — reuse, do not re-declare)

| Library / module | Where | Purpose in v1.2 | When |
|------------------|-------|-----------------|------|
| stdlib `json` | scripts + models | Load `catalog/catalog.json`; canonical dumps | Always. `object_pairs_hook` duplicate-key reject already in builder |
| stdlib `hashlib` | `catalog_identity`, `catalog_authority_hashing` | SHA-256 authority + content hashes | Catalog bytes + request payloads |
| stdlib `uuid` | `services/catalog_identity.py` | Server UUIDv5 only | Never caller UUID authority |
| stdlib `hmac` + `secrets` | identity / prepare | Plan tokens | Unchanged prepare/commit |
| stdlib `pathlib`, `argparse`, `tempfile`, `dataclasses` | scripts | Offline converter CLI | New/extended builder script |
| stdlib `collections` (`Counter`, `defaultdict`, `deque`) | scripts | Deterministic FE component selection | BFS/degree — **not** networkx |
| stdlib `re`, `unicodedata` | hashing + keys | BOM/control reject; key grammar | Authority + graph_key |
| stdlib `ast` + existing scanner | `scripts/catalog_image_secret_scanner.py` | Image secret scan | Targeted image acceptance |
| `models.catalog_*` | `mcp_server/src/models/` | Entity/edge/evidence/batch/prepare contracts | Validate converted slice before prepare |
| `services.catalog_service` / `catalog_store` | `mcp_server/src/services/` | Prepare/commit/resolve/evidence + new neighbor read | Object-context tool |
| `scripts/build_catalog_canary_requests.py` | scripts | Table→entity/edge conversion, FK join, strict validate | **Extend or extract**; do not rewrite |
| `scripts/catalog_authority_hashing.py` | scripts | raw/lf SHA-256, git/archive authority | Pin `catalog.json` digest in slice manifest |
| `scripts/run_catalog_canary_batch.py` + launcher | scripts | Source-bound run surface | Thin v1.2 acceptance driver only |
| `scripts/catalog_image_secret_scanner.py` | scripts | `scan_complete_image` | Image receipt without new scanner |
| pytest / pytest-asyncio / ruff / pyright | dev group | Unit + live tests | Same markers; isolated test group only |

### Development Tools (unchanged)

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest + pytest-asyncio | Converter unit tests; object-context service/store tests | Deterministic fixtures over faker |
| pytest-timeout | Live Neo4j hang protection | Keep |
| ruff / pyright | Format + basic typecheck | line-length 100, single quotes |
| Docker + `Dockerfile.standalone` | Source-bound image build | `mcp_server/docker/build-standalone.sh` pattern |
| compose override | `docker-compose-neo4j.catalog-local.override.yml` | Local Neo4j + catalog config; not K8s deploy |

## Installation

```bash
# No new packages. From repo root / mcp_server as today:
uv sync --extra dev          # root library if needed
cd mcp_server && uv sync     # MCP runtime + dev group

# Do NOT:
# uv add orjson ijson jsonschema networkx pandas msgspec docling
```

## Exact Mechanisms for v1.2 Scope

### 1. Strict JSON validation / conversion (offline)

**Authority:** untracked ~19 MB `catalog/catalog.json` (`schema_version: "1.0"`, 2 documents, 1261 tables, 10649 columns, 434 relationships). Normalized JSON is sole authority — no Docling, no LLM reparse.

**Use (installed / stdlib):**

| Concern | Mechanism | Existing anchor |
|---------|-----------|-----------------|
| Load | `json.loads(..., object_pairs_hook=_reject_duplicate_keys)` | `build_catalog_canary_requests.strict_json_bytes` / `strict_load` |
| BOM / controls | reject UTF-8 BOM + binary Cc | `strict_json_bytes`, `catalog_authority_hashing.canonical_text_bytes_lf` |
| Authority pin | `sha256_raw_bytes` + optional `lf_sha256` of catalog file | `catalog_authority_hashing.authority_digest` |
| Shape check | Lightweight required-key / type asserts **or** thin Pydantic view models only for the **selected slice**, not a second full-catalog schema stack | Prefer asserts + reuse `CatalogEntityItem` / `CatalogEdgeItem` / `UpsertCatalogBatchRequest` on **output** |
| Output validate | `validate_request` + model field allowlists; hardened path uses `identity_schema_version=catalog-v2`, `system_key` ∈ {`FE`,`BO`,`COMMON`} | `validate_request`, `build_hardened_payload_from_fixture`, `CatalogStrictModel` |
| Content hashes | `services.catalog_identity.canonical_sha256` / `_with_content_hashes` | Already used by builder |
| Table expand | `merge_table_objects`, `build_table_request`, `make_entity` / `make_edge` | Already maps columns/constraints/indexes → Contains / PrimaryKeyOf / DocumentedBy |
| FK edges | `build_fk_request` pattern: qualify bare `from_table`/`to_table` names against selected table ids via `endswith('.' + name)` | **Required** — catalog relationships store bare names (`T_ACQ_FEE_RULES`), tables store `SVFE_SHB.T_...` |
| Atomic write | `_atomic_write_missing` / `_atomic_replace_set` | Commit request artifacts deterministically |

**Do not** introduce `jsonschema`, `orjson`, `ijson`, `msgspec`, or a second ontology layer. 19 MB fits stdlib `json.load` once per conversion run. `jsonschema` appears only as a **transitive** lock entry — not a direct dep and not an API to adopt.

**Conversion output:** hardened catalog-v2 batch payloads (prepare-ready), not live Neo4j writes from the converter process.

### 2. Deterministic representative selection

**Observed structure (repo inspection):**

| Slice | Schema / doc | Tables | Relationships in JSON |
|-------|--------------|--------|------------------------|
| FE | `SVFE_SHB` / `SVFE Database Dictionary…pdf` | 637 | 434 (`DOCUMENTED_FOREIGN_KEY` 429, `DOCUMENTED_RELATIONSHIP` 5); bare table names |
| BO | `MAIN1` / `Data dictionary SVBO…pdf` | 624 | **0** relationship records |

**Use stdlib only:**

1. Index tables by `id` and by `(schema, name_canonical)`.
2. Qualify each relationship endpoint: unique match under selected system schema; fail closed on 0 or >1 matches.
3. Build undirected adjacency for FE from qualified FK endpoints.
4. Pick FE connected sample with **frozen tie-break rules** (sort keys, not hash randomization), e.g.:
   - Prefer component containing known good anchor tables if still desired (`ACCEPT_TAB` lineage) **or** largest component by (edge_count, table_count, min(table_id));
   - Then bound to batch limits (`DEFAULT_MAX_ENTITIES_PER_BATCH=500`, edges 2000, evidence 5000) by deterministic BFS/priority from a frozen seed table id.
5. Pick BO **structurally rich** table(s) by frozen score, e.g. `(n_columns, n_indexes, n_primary_keys, n_constraints, table_id)` — BO has no FK records; richness is columnar/index structure only.
6. Emit a committed selection manifest: `catalog_sha256`, selected table ids, relationship ids, counts, system_key per batch, seed/tie-break version string.

**Do not** add `networkx`, `pandas`, or ML clustering. Selection is offline script logic with golden expected ids/counts in tests.

### 3. Compact object-context retrieval (runtime)

**Gap:** existing reads are split:

- `resolve_typed_entities` / `resolve_typed_edges` — identity/status, not full typed detail + neighbors
- `get_catalog_evidence` — paginated compact evidence for one target
- `get_catalog_batch_manifest` — batch membership

**Add one** read-only MCP tool (name TBD in plan phase), same stack:

| Layer | Stack choice |
|-------|----------------|
| Transport | `@mcp.tool()` on `CatalogSafeFastMCP` in `graphiti_mcp_server.py` |
| Request/response | New `CatalogStrictModel` types in `models/catalog_*.py` + compact DTOs in `catalog_responses.py` |
| Service | `CatalogService` method: gate → group_id scope → load focal entity → bound neighbors → evidence excerpts → locators |
| Store | New **parameterized** Cypher on `CatalogNeo4jStore`: one-hop `RELATES_TO` by `group_id` + focal `uuid`/`graph_key`; fixed allowlisted return properties; `LIMIT` bound |
| Safety | No client labels/property names in Cypher; no write path; no embeddings call on read |

**Response shape (stack constraint, not product copy):** typed focal object fields already stored on Entity, immediate neighbor edges/nodes (bounded), evidence excerpts (`CompactEvidenceLink`-class projection), source locators (page / document_id from evidence or attributes). Hard caps on neighbor count and excerpt length (`MAX_EVIDENCE_LENGTH` already 8192; use tighter tool default).

**Do not** add Neo4j GDS, APOC requirement, Elasticsearch, or a general graph-query API. **Do not** implement multi-hop path/impact tools (out of scope).

### 4. Targeted image acceptance

**Reuse v1.1 image machinery; narrow the gate:**

| Piece | Reuse | v1.2 change |
|-------|-------|-------------|
| Build | `mcp_server/docker/Dockerfile.standalone` + `build-standalone.sh` / CI `publish-mcp-image.yml` pattern | Build new source-bound image from v1.2 runtime sources |
| Secret scan | `scripts/catalog_image_secret_scanner.py` (`scan_complete_image`) | Same |
| Authority digests | `catalog_authority_hashing` + runner `SOURCE_AUTHORITY_PATHS` / execution map | Extend path list if new converter modules are authority-bound |
| Runtime smoke | compose catalog-local override + `/health` + tool list | Prove new object-context tool registered; prepare/commit path still importable |
| Ingest proof | Existing prepare + token-only commit against **new isolated test group** | FE+BO slice only; not full catalog |
| Final canary | `run_catalog_phase6_final_canary.py` Gates 0–10 | **Do not re-run** as v1.2 acceptance |

**Do not** add BuildKit frontend frameworks, Syft/Grype as hard deps, or K8s deploy. Production digest promotion stays separate approval.

## Alternatives Considered

| Recommended | Alternative | When alternative might win |
|-------------|-------------|----------------------------|
| stdlib `json` one-shot load | `ijson` streaming | Only if catalog grows multi-GB and conversion must run in tiny RAM — not true at 19 MB |
| Pydantic validate **outputs** | Draft a full JSON Schema + `jsonschema` | External non-Python consumers need a portable schema doc — still generate from Pydantic, do not add runtime dep |
| Stdlib adjacency/BFS | `networkx` | Complex graph analytics / multi-criteria Steiner subgraph — YAGNI for representative slice |
| One MCP object-context tool | Agent chains resolve+evidence+search | Higher token cost, non-atomic bounds; milestone asks one compact tool |
| Extend builder script | New package/poetry project for ETL | Splits identity/hash authority; increases drift risk |
| Thin v1.2 acceptance driver | Full Phase-6 final canary replay | Cannot reproduce v1.1 image digest; policy forbids repeat |

## What NOT to Use

| Avoid | Why | Use instead |
|-------|-----|-------------|
| Any new PyPI dependency | YAGNI; lock churn; review surface | Stdlib + installed Pydantic/neo4j/mcp |
| `orjson` / `ujson` / `msgspec` | Speed irrelevant at 19 MB; hash authority must match stdlib canonicalization already used in identity | `json` + existing `canonical_sha256` |
| `ijson` | Unnecessary streaming complexity | `json.load` |
| `jsonschema` as direct API | Duplicates Pydantic contracts; transitive-only today | `CatalogStrictModel` + builder `validate_request` |
| `networkx` / `rustworkx` | Selection is tiny deterministic BFS | `defaultdict` + `deque` |
| `pandas` / `polars` | Tabular convenience hides deterministic ordering bugs | Plain lists + `sort` key tuples |
| Docling / PDF parsers | JSON is normalized authority; reparse non-deterministic | Read `catalog/catalog.json` only |
| LLM extraction / `add_memory` for pilot slice | Breaks deterministic identity and sync commit | `prepare_catalog_batch` + `commit_prepared_catalog_batch` |
| `add_triplet` for catalog FKs | Generic endpoints / non-catalog edge identity | Typed catalog edges (`ForeignKeyTo`, etc.) |
| Caller-supplied UUIDs as identity | Forbidden by project constraints | Server UUIDv5 via `catalog_identity` |
| MD5 / non-SHA-256 content hashes | Forbidden | SHA-256 lowercase hex |
| FalkorDB/Kuzu/Neptune work in v1.2 | Neo4j-first; no portability claim | Neo4j only |
| APOC / GDS / arbitrary Cypher tool | Injection + ops dependency | Fixed allowlisted store queries |
| Full Phase-6 final canary harness as v1.2 gate | Explicitly out of scope; planning-only commits after v1.1 canary | Delta acceptance: image build + smoke + slice ingest + object-context asserts |
| K8s deploy / live `oracle-catalog-v2` writes | Operations constraint | Isolated test group only (new group id; never mutate live) |
| Full 1261-table ingest | Out of scope | Bounded FE connected + BO rich sample within batch limits |
| BO inferred FKs / FE↔BO maps | No BO relationship records; inference is later milestone | BO structural entities/edges only (Contains, PK, indexes, DocumentedBy) |
| New embedder provider packages | Ollama path already proven | Existing config |
| `tenacity` around catalog writes | Masks tx failures | Fail closed; rollback |

## Stack Patterns by Variant

**If conversion stays offline-only (default):**

- Keep converter under `scripts/` importing `mcp_server/src` models/identity (same path bootstrap as `build_catalog_canary_requests.py`).
- Runtime image gains **only** the object-context tool + store/service code — not the 19 MB JSON.

**If selection must be re-run in CI:**

- Commit selection manifest + request payloads as golden artifacts; CI verifies converter replay hash-equals golden.
- Do not fetch PDFs or regenerate JSON.

**If object-context needs attributes not currently returned by resolve:**

- Extend store MATCH RETURN list with allowlisted property keys already written at upsert time.
- Do not open a generic property projection API.

**If image acceptance cannot use prior canary freeze receipts:**

- Bind new freeze to v1.2 source digests + new image id (`sha256:…`).
- Smoke: health, tool ledger includes new tool, one dry-run prepare of fixture slice optional; skip Gate 0–10 ACCEPT_TAB final canary script.

## Integration Points (implementation map)

| Feature | Primary touch points | Avoid touching |
|---------|----------------------|----------------|
| JSON → catalog-v2 requests | `scripts/build_catalog_canary_requests.py` (extract shared pure fns) or sibling `scripts/build_catalog_fe_bo_pilot_requests.py`; `models.catalog_*`; `services.catalog_identity` | `graphiti_core` extraction prompts; Docling |
| Selection manifest | New small pure module under `scripts/` + tests in `mcp_server/tests/test_catalog_*.py` | Live Neo4j |
| Ingest pilot | Existing `prepare_catalog_batch` / `commit_prepared_catalog_batch`; runner patterns from `run_catalog_canary_batch.py` | `clear_graph`; live groups |
| Object context tool | `graphiti_mcp_server.py`, `catalog_service.py`, `catalog_store.py`, `catalog_entities.py` / `catalog_responses.py` | Semantic `search_nodes` rewrite |
| Image | `Dockerfile.standalone`, secret scanner, thin acceptance script | `run_catalog_phase6_final_canary.py` full path |

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Python 3.10+ | All mcp_server code | No `enum.StrEnum`; polyfill remains |
| Pydantic 2.x strict models | FastMCP tool args | Nested `extra='forbid'` must stay per-model |
| neo4j driver 5.26+ | Neo4j 5.26+ | Composite UNIQUE already used for catalog identity |
| `mcp` 1.27.x | existing `CatalogSafeFastMCP` | Additive tool only |
| Ollama embedder config | prepare/commit embeddings-before-tx | Unchanged contract |
| `catalog/catalog.json` `schema_version=1.0` | Converter tie-break version N | Pin file SHA-256 in manifest; bump converter version if mapping rules change |

## Confidence Assessment

| Area | Level | Notes |
|------|-------|-------|
| Zero new deps | HIGH | All four v1.2 concerns covered by installed stack + stdlib |
| Conversion reuse of builder | HIGH | `build_table_request` / `build_fk_request` / `validate_request` already encode mapping |
| FE relationship qualification | HIGH | Verified bare names vs `SCHEMA.TABLE` ids; builder already uses `endswith` join |
| BO has no FK records | HIGH | Counter over full relationship list = 0 for MAIN1 |
| Object-context needs new tool/query | HIGH | Resolve/evidence insufficient alone for "details + neighbors + locators" |
| Skip full final canary | HIGH | PROJECT.md decision + milestone_context |
| Exact FE seed table set | MEDIUM | Product choice of seed/component left to plan phase; stack does not depend on it |

## Sources

- Repo: `mcp_server/pyproject.toml`, `mcp_server/src/models/catalog_*.py`, `mcp_server/src/services/catalog_{service,store,identity}.py`, `mcp_server/src/graphiti_mcp_server.py`
- Repo: `scripts/build_catalog_canary_requests.py`, `scripts/catalog_authority_hashing.py`, `scripts/catalog_image_secret_scanner.py`, `scripts/run_catalog_phase6_final_canary.py`, `scripts/run_catalog_canary_batch.py`
- Repo: `mcp_server/docker/Dockerfile.standalone`, `docker-compose-neo4j.catalog-local.override.yml`, `.github/workflows/publish-mcp-image.yml`
- Repo inspection: `catalog/catalog.json` structure/counts/schemas/relationship naming (local file read; not dumped)
- Repo: `.planning/PROJECT.md` v1.2 scope, constraints, out-of-scope list
- Prior research: v1.1 STACK research (2026-07-17) — zero-dep verdict carried forward; milestone focus updated

---
*Stack research for: v1.2 FE/BO Catalog Pilot and Object Context*
*Researched: 2026-07-24*
*New dependencies: none*
