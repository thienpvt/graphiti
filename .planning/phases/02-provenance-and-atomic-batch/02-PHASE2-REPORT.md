# Phase 2 Report — Provenance and Atomic Batch

**Date:** 2026-07-17
**Executor branch:** `worktree-agent-a24661030d63d622b`
**Base:** `03bdd7f`
**Neo4j:** local test container on `bolt://localhost:17687` (credentials supplied through the command environment; not recorded)
**Required test group:** `oracle-catalog-tool-test`

## Overall: PASS

All required Phase 2 gates passed. The 34-test live suite ran with `CATALOG_INT_REQUIRED=1` and zero skips. No image was pushed, no workload was deployed, no production canary or full ingest ran, and no existing data was cleared or deleted.

## Commands Run

Commands below are exact except secrets are replaced by `<redacted>` and the worktree path is abbreviated as `<repo_root>`.

### Neo4j readiness

```bash
docker inspect --format 'running={{.State.Running}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' graphiti-catalog-neo4j-test

NEO4J_URI=bolt://localhost:17687 \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=<redacted> \
uv run python <async-driver-connectivity-check>
```

Observed: exit 0. Container state was `running=true health=none`. Neo4j driver connectivity succeeded against `Neo4j/5.26.0`, Bolt protocol `5.8`.

### Focused catalog units

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
uv run pytest \
  tests/test_catalog_identity.py \
  tests/test_catalog_models.py \
  tests/test_catalog_store_unit.py \
  tests/test_catalog_service.py \
  -q --tb=short
```

Observed: exit 0 — `260 passed in 1.88s`.

### Required live Neo4j integration

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
NEO4J_URI=bolt://localhost:17687 \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=<redacted> \
CATALOG_INT_REQUIRED=1 \
uv run pytest tests/test_catalog_neo4j_int.py -q --tb=short --timeout=120
```

Observed: exit 0 — `34 passed in 23.14s`; zero skipped. Required mode was active.

### Combined catalog suite

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
NEO4J_URI=bolt://localhost:17687 \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=<redacted> \
CATALOG_INT_REQUIRED=1 \
uv run pytest \
  tests/test_catalog_identity.py \
  tests/test_catalog_models.py \
  tests/test_catalog_store_unit.py \
  tests/test_catalog_service.py \
  tests/test_catalog_neo4j_int.py \
  -q --tb=line --timeout=120
```

Observed: exit 0 — `294 passed in 24.18s`.

### Catalog-scoped Ruff and Pyright

```bash
cd mcp_server
uv run ruff format --check \
  src/services/catalog_identity.py src/services/catalog_service.py \
  src/services/catalog_store.py src/config/schema.py \
  src/models/catalog_common.py src/models/catalog_edges.py \
  src/models/catalog_entities.py src/models/catalog_provenance.py \
  src/models/catalog_batch.py src/models/catalog_responses.py \
  src/graphiti_mcp_server.py tests/test_catalog_identity.py \
  tests/test_catalog_models.py tests/test_catalog_service.py \
  tests/test_catalog_store_unit.py tests/test_catalog_neo4j_int.py

uv run ruff check \
  src/services/catalog_identity.py src/services/catalog_service.py \
  src/services/catalog_store.py src/config/schema.py \
  src/models/catalog_common.py src/models/catalog_edges.py \
  src/models/catalog_entities.py src/models/catalog_provenance.py \
  src/models/catalog_batch.py src/models/catalog_responses.py \
  src/graphiti_mcp_server.py tests/test_catalog_identity.py \
  tests/test_catalog_models.py tests/test_catalog_service.py \
  tests/test_catalog_store_unit.py tests/test_catalog_neo4j_int.py

PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
uv run pyright \
  src/services/catalog_identity.py src/services/catalog_service.py \
  src/services/catalog_store.py src/config/schema.py \
  src/models/catalog_common.py src/models/catalog_edges.py \
  src/models/catalog_entities.py src/models/catalog_provenance.py \
  src/models/catalog_batch.py src/models/catalog_responses.py \
  src/graphiti_mcp_server.py tests/test_catalog_identity.py \
  tests/test_catalog_models.py tests/test_catalog_service.py \
  tests/test_catalog_store_unit.py tests/test_catalog_neo4j_int.py
```

Observed:

- Ruff format: exit 0 — `16 files already formatted`.
- Ruff check: exit 0 — `All checks passed!`.
- Pyright: exit 0 — `0 errors, 0 warnings, 0 informations` (the CLI also printed a non-failing newer-version notice).

The first Ruff check found one `SIM103` in the newly added registration assertion. It was fixed minimally by using `LEGACY_TOOL_NAMES.issubset(names)`, committed, then all scoped quality gates were rerun green.

### MCP schema listing and registration

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
uv run pytest tests/test_catalog_service.py \
  -k 'registers_exactly_seven or registration or mcp_tool' -q
```

Observed: exit 0 — `8 passed, 91 deselected in 1.06s`.

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
uv run python <list-mcp-tools-and-nested-request-schemas>
```

Observed: exit 0.

```text
TOOL_COUNT 21
CATALOG_COUNT 7
LEGACY_COUNT 14
MISSING []
```

### Existing MCP regressions

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
uv run pytest \
  tests/test_update_entity.py tests/test_factories.py \
  tests/test_configuration.py tests/test_core_parity.py \
  -q --tb=short
```

Observed: exit 0 — `86 passed in 1.34s`.

### No-LLM, no-queue, and registration spies

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
uv run pytest tests/test_catalog_service.py \
  -k 'no_queue_or_llm or no_queue_or_llm_calls or no_llm or registration or mcp_tool' \
  -q --tb=short
```

Observed: exit 0 — `10 passed, 89 deselected in 0.97s`.

### Named live interoperability, community, and teardown gates

```bash
cd mcp_server
PYTHONPATH="<repo_root>;<repo_root>/mcp_server/src" \
NEO4J_URI=bolt://localhost:17687 \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=<redacted> \
CATALOG_INT_REQUIRED=1 \
uv run pytest tests/test_catalog_neo4j_int.py \
  -k 'search_nodes_and_memory_facts_interop or explicit_community_build_accepts_batch_entities or batch_no_llm_queue_or_implicit_community_calls or teardown_scoped_and_fixture_never_calls_clear_graph' \
  -vv --tb=short --timeout=120
```

Observed: exit 0 — `4 passed, 30 deselected in 3.24s`. The four selected test node IDs all passed:

- `test_search_nodes_and_memory_facts_interop`
- `test_batch_no_llm_queue_or_implicit_community_calls`
- `test_explicit_community_build_accepts_batch_entities`
- `test_teardown_scoped_and_fixture_never_calls_clear_graph`

### Read-only forbidden-group snapshot

```bash
cd mcp_server
NEO4J_URI=bolt://localhost:17687 \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=<redacted> \
uv run python <read-only-oracle-catalog-v2-count-query>
```

Observed: exit 0.

```text
FORBIDDEN_GROUP oracle-catalog-v2
READ_ONLY_SNAPSHOT {'nodes': 0, 'relationships': 0, 'max_updated_at': None, 'max_created_at': None}
```

The query was read-only. The isolated live suite targets only `oracle-catalog-tool-test`; it also statically asserts the forbidden group constant, scoped element-ID teardown, and absence of `clear_graph` calls.

### Local standalone image build

```bash
docker build -f mcp_server/docker/Dockerfile.standalone -t graphiti-mcp:phase2-local .
```

Observed: exit 0. Build completed locally without push or deploy. Resulting image metadata:

```text
id=sha256:975bf905f82454359c80f156a583c23b7d1d73c72456b07b9e93346c3dab9c7d
size=126540417
```

## Seven Tool Schemas

FastMCP exposes each catalog tool with one required outer `request` object. The observed nested request schemas were:

| Order | Tool | Required nested fields | Nested request properties |
|---:|---|---|---|
| 1 | `upsert_typed_entities` | `group_id`, `batch_id`, `entities` | `group_id`, `batch_id`, `entities`, `dry_run`, `atomic` |
| 2 | `upsert_typed_edges` | `group_id`, `batch_id`, `edges` | `group_id`, `batch_id`, `edges`, `dry_run`, `atomic`, `strict_endpoints` |
| 3 | `resolve_typed_entities` | `group_id` | `group_id`, `entities`, `graph_keys` |
| 4 | `verify_catalog_batch` | `group_id` | `group_id`, `batch_id`, `entities`, `edges`, `require_provenance` |
| 5 | `upsert_provenance` | `group_id`, `batch_id`, `sources` | `group_id`, `batch_id`, `sources`, `entity_targets`, `edge_targets`, `dry_run`, `atomic` |
| 6 | `get_catalog_ingest_status` | `group_id`, `batch_id` | `group_id`, `batch_id` |
| 7 | `upsert_catalog_batch` | `group_id`, `batch_id` | `group_id`, `batch_id`, `entities`, `edges`, `provenance`, `request_sha256`, `catalog_sha256`, `dry_run`, `atomic` |

Registration preserved all 14 legacy tools: `add_memory`, `search_nodes`, `search_memory_facts`, `add_triplet`, `get_entity_edge`, `get_episodes`, `get_episode_entities`, `update_entity`, `build_communities`, `summarize_saga`, `delete_episode`, `delete_entity_edge`, `clear_graph`, and `get_status`.

## Observed Results

| Gate | Result | Evidence |
|---|---|---|
| Catalog units | PASS | 260 passed |
| Required live Neo4j | PASS | 34 passed, zero skipped, Neo4j 5.26.0 |
| Combined catalog suite | PASS | 294 passed |
| Ruff format/check | PASS | 16 formatted; all lint checks passed |
| Scoped Pyright | PASS | 0 errors, 0 warnings, 0 informations |
| Seven catalog schemas | PASS | 7/7; 21 total tools; 14 legacy retained |
| Existing MCP regressions | PASS | 86 passed |
| Search interoperability | PASS | Named live node/fact search test passed |
| Explicit community build | PASS | Named live explicit-maintenance test passed |
| No LLM/queue/implicit community | PASS | Unit spies and named live test passed |
| Isolation / forbidden group | PASS | Dedicated group only; read-only forbidden-group snapshot remained empty |
| Local image build | PASS | Standalone image built locally; no push/deploy |

## Isolation

- All integration writes used the sanitized fixture and `group_id=oracle-catalog-tool-test`.
- The integration fixture tears down exact created element IDs. It does not clear a group.
- `oracle-catalog-v2` was never a write target. Its observed read-only snapshot was empty.
- `CatalogIngestBatch` remains a non-`Entity` node and was excluded from entity search/community inputs by observed live coverage.
- The only fixture authority used for ACCEPT_TAB was `mcp_server/tests/fixtures/accept_tab_sanitized.json`; untracked `mcp_server/sample_catalog.json` was not used or changed.

## No-LLM, No-Queue, Community Neutrality

Catalog entity/edge/batch paths use the configured embedder for search vectors, but the observed spy gates recorded no LLM extraction and no queue calls. Provenance and status paths do not embed. Normal deterministic upserts did not invoke community building. The separate explicit community-maintenance test succeeded against batch-created entities.

## Graphiti and Neo4j Limitations

- This implementation and evidence are Neo4j-only; no FalkorDB or other-backend portability claim is made.
- Deterministic source records use installed Graphiti `Episodic` nodes.
- Entity provenance uses deterministic `MENTIONS` relationships.
- Neo4j cannot connect a relationship directly to another relationship without introducing a new schema object. Fact provenance therefore appends source episode UUIDs to `RELATES_TO.episodes`, the closest installed Graphiti-compatible representation.
- Batch status uses only `CatalogIngestBatch`, not `Entity`, so Graphiti entity search and community clustering exclude it.
- Community summaries are maintenance output. Catalog upserts do not create them automatically.

## Prohibitions Held

- No deployment, Kubernetes apply, restart of a live workload, registry push, or image publication.
- No production or `oracle-catalog-v2` canary execution.
- No full catalog ingest.
- No graph clear or existing-data deletion.
- No LLM, queue, or semantic `add_memory` behavior changes.
- No manifest edits.
- No credentials written to README, report, tests, commits, or command-result evidence.
- No skipped live test counted as PASS.

## Image Build

The standalone MCP Dockerfile built successfully as `graphiti-mcp:phase2-local`. The image stayed local. No push, deploy, Kubernetes action, or live server launch followed.

## Canary Recommendation Only

After separate operator approval, use a fresh non-production group and a sanitized minimal request to validate the immutable namespace, schema listing, dry-run result, commit, identical retry, status lookup, verification, search, and explicit community maintenance. Capture a before/after group snapshot and stop on any structured error. Do not reuse `oracle-catalog-v2`, do not run a full ingest, and do not change the UUID namespace during rollback.

This is recommendation text only. No canary was executed in this plan.

## Final Verdict

All required observed checks are green, including the unskipped 34-test live Neo4j suite, seven-tool schema listing, legacy compatibility, search, explicit community maintenance, no-LLM/no-queue isolation, forbidden-group protection, and local standalone image build.

**Overall: PASS**
