---
phase: quick
plan: 260719-udj
type: execute
wave: 1
depends_on: []
files_modified:
  - mcp_server/src/services/catalog_store.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/src/graphiti_mcp_server.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/README.md
  - mcp_server/docs/CATALOG_V2_MIGRATION.md
autonomous: true
requirements:
  - CAPA-truthful-readiness
must_haves:
  truths:
    - get_catalog_capabilities keeps existing fields and remains one of the exact 28 MCP tools with unchanged contracts for all other tools
    - connectivity ok only after bounded read-only Neo4j probe on already-initialized client; error on probe failure; unknown when service/client uninitialized or backend unsupported
    - embeddings.ready ready only when Ollama GET /api/tags returns 200 AND configured model is present under documented name normalization; missing model is error; non-ollama stays unknown; never embed generation
    - neo4j_indexes ready only when all 14 Catalog-v2 required uniqueness constraints are present via SHOW CONSTRAINTS; field name is legacy — product has no Catalog-v2-specific indexes
    - Capabilities path never calls get_client/initialize/build_indices_and_constraints/ensure_*/embedder.create/LLM/queue/domain writes; Cypher allowlist only RETURN 1 and SHOW CONSTRAINTS
    - Responses and logs redact secrets, raw UUID namespace, passwords, API keys, raw URLs; probe timeout pinned at 2.0s
  artifacts:
    - path: mcp_server/src/services/catalog_store.py
      provides: public read-only inspect over the exact 14 required constraint names
    - path: mcp_server/src/services/catalog_capabilities.py
      provides: async probes for connectivity, schema readiness, ollama model presence
    - path: mcp_server/src/graphiti_mcp_server.py
      provides: service/client matrix via require_initialized_client only
    - path: mcp_server/tests/test_catalog_capabilities.py
      provides: positive/error/unknown/no-mutation/redaction/cypher-allowlist/model-presence coverage
    - path: mcp_server/README.md
      provides: operator docs for truthful readiness and neo4j_indexes semantics
    - path: mcp_server/docs/CATALOG_V2_MIGRATION.md
      provides: pre-canary readiness note; stop before canary
  key_links:
    - from: get_catalog_capabilities
      to: require_initialized_client
      via: never get_client
      pattern: require_initialized_client
    - from: schema probe
      to: CatalogNeo4jStore.inspect_catalog_v2_schema_readiness
      via: SHOW CONSTRAINTS only
      pattern: inspect_catalog_v2_schema_readiness
    - from: ollama readiness
      to: GET /api/tags + model normalize
      via: httpx timeout 2.0s
      pattern: /api/tags
---

<objective>
Implement truthful mutation-free Catalog-v2 runtime readiness reporting in `get_catalog_capabilities` before any canary retry.

Purpose: Replace always-unknown connectivity/embedder/schema readiness with evidence-backed ok/error/unknown states without writes, schema ensure, embedding generation, LLM calls, or bootstrap side effects.

Output: Read-only probes; focused tests with Cypher allowlist + ensure/bootstrap forbids; operator docs; local source-bound Docker image. Stop before canary. No commit/push/deploy/Kubernetes.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@mcp_server/src/services/catalog_capabilities.py
@mcp_server/src/services/catalog_store.py
@mcp_server/src/graphiti_mcp_server.py
@mcp_server/src/models/catalog_responses.py
@mcp_server/src/config/schema.py
@mcp_server/tests/test_catalog_capabilities.py
@mcp_server/README.md
@mcp_server/docs/CATALOG_V2_MIGRATION.md
@mcp_server/docker/Dockerfile.standalone
@graphiti_core/driver/neo4j_driver.py
@graphiti_core/embedder/ollama.py
</context>

<locked_contracts>

## 1. Required Catalog-v2 schema objects (exact names from store create paths)

Product Catalog-v2 create paths issue **CREATE CONSTRAINT IF NOT EXISTS only**. There are **no product-specific Catalog-v2 CREATE INDEX statements** in `catalog_store.py`. Therefore `neo4j_indexes` (legacy field name, unchanged API) means **full required uniqueness-constraint readiness**, not vector/range index readiness.

### Domain identity (5) — `identity_uniqueness_constraint_statements`
1. `catalog_entity_identity_unique` — `(Entity.uuid, Entity.group_id)`
2. `catalog_relates_to_identity_unique` — `(RELATES_TO.uuid, RELATES_TO.group_id)`
3. `catalog_episodic_identity_unique` — `(Episodic.uuid, Episodic.group_id)`
4. `catalog_mentions_identity_unique` — `(MENTIONS.uuid, MENTIONS.group_id)`
5. `catalog_batch_identity_unique` — `(CatalogIngestBatch.uuid, CatalogIngestBatch.group_id)`

### Prepared-plan control plane (4) — `plan_schema_constraint_statements`
6. `catalog_prepared_plan_identity_unique` — `(CatalogPreparedPlan.uuid, CatalogPreparedPlan.group_id)`
7. `catalog_prepared_plan_token_digest_unique` — `(CatalogPreparedPlan.token_digest)`
8. `catalog_prepared_plan_chunk_identity_unique` — `(CatalogPreparedPlanChunk.uuid, CatalogPreparedPlanChunk.group_id)`
9. `catalog_prepared_plan_chunk_index_unique` — `(CatalogPreparedPlanChunk.plan_uuid, group_id, chunk_index)`

### Evidence + manifest control plane (5) — `evidence_manifest_schema_constraint_statements`
10. `catalog_evidence_link_identity_unique` — `(CatalogEvidenceLink.uuid, group_id)`
11. `catalog_evidence_link_key_unique` — `(CatalogEvidenceLink.group_id, link_key)`
12. `catalog_batch_manifest_identity_unique` — `(CatalogBatchManifest.uuid, group_id)`
13. `catalog_batch_manifest_chunk_identity_unique` — `(CatalogBatchManifestChunk.uuid, group_id)`
14. `catalog_batch_manifest_chunk_index_unique` — `(CatalogBatchManifestChunk.manifest_uuid, group_id, chunk_index)`

**Ready rule:** `neo4j_indexes='ready'` iff all 14 pass existing `_constraint_row_matches` shape checks via a single or composed SHOW CONSTRAINTS read. Missing any → `'unknown'`. Non-neo4j backend → `'n/a'`. No client / SHOW not attempted → `'unknown'`. SHOW attempted and raises → `'unknown'` (connectivity may still be `error`/`ok` from prior probe). Never CREATE/DROP/ALTER/ensure from capabilities. Never set `_schema_ready` / `_plan_schema_ready` / `_evidence_manifest_schema_ready`.

## 2. Ollama embeddings.ready contract

- Probe only when `embedder.provider == 'ollama'`.
- HTTP: `GET {api_url.rstrip('/')}/api/tags` with `httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS)`.
- Never call `/api/embed`, `embedder.create`, `create_batch`, or any inference path.
- **Normalization (documented, apply both sides):**
  - strip whitespace
  - casefold
  - if name contains `:`, keep full `name:tag`; also accept bare name match against configured model when configured model has no tag and tags entry name equals bare OR equals `bare:latest`
  - configured model `qwen3-embedding:0.6b` matches tags entry `name == 'qwen3-embedding:0.6b'` (exact after strip/casefold)
  - configured model `qwen3-embedding` matches `qwen3-embedding` or `qwen3-embedding:latest`
- **States:**
  - tags HTTP 200 AND configured model present after normalize → `embeddings.ready = 'ready'`
  - tags HTTP 200 AND configured model absent → `embeddings.ready = 'error'` (attempted probe, model not available)
  - tags request attempted and fails/timeout/non-200 → `embeddings.ready = 'error'`
  - provider not ollama, or ollama api_url missing → `embeddings.ready = 'unknown'`
- Response still exposes `embeddings.provider` / `embeddings.model` from config only; never api_url.

## 3. Allowed Cypher + forbidden side effects (tests must enforce)

**Allowlist (only these Cypher texts may be issued by capabilities probes):**
1. Connectivity fallback (if `health_check` absent): `RETURN 1 AS ok` (exact; or exact constant in module).
2. Schema inspect: the existing SHOW CONSTRAINTS query body used by store inspect:
   ```
   SHOW CONSTRAINTS
   YIELD name, type, entityType, labelsOrTypes, properties
   RETURN name, type, entityType, labelsOrTypes, properties
   ```
   Prefer `driver.health_check()` first when present (no Cypher).

**Forbidden (assert never called / never present in captured Cypher):**
- Cypher keywords: CREATE, DROP, ALTER, MERGE, SET, DELETE, REMOVE, DETACH, FOREACH, LOAD CSV, CALL dbms, CALL db.create
- Methods: `get_client`, `initialize`, `build_indices_and_constraints`, `ensure_uuid_uniqueness_constraints`, `ensure_plan_schema`, `ensure_evidence_manifest_schema`, `execute_write`, `embedder.create`, `embedder.create_batch`, queue enqueue, catalog domain upsert methods

## 4. Service / client matrix (locked)

| graphiti_service | service.client | behavior |
|---|---|---|
| `None` | n/a | `ErrorResponse(error='Graphiti service not initialized')` — no probes |
| set | `None` | `require_initialized_client` → None; pure config view; `connectivity='unknown'`; `neo4j_indexes='unknown'` if backend neo4j else `'n/a'`; embeddings per provider rules without live probe if no ollama url needed stays unknown; **never** call `get_client` |
| set | initialized Graphiti | pass client into async builder; run neo4j probes only if backend=='neo4j'; ollama tags if provider=='ollama' |

## 5. Timeout + redaction (pinned)

- Module constant: `PROBE_TIMEOUT_SECONDS = 2.0` in `catalog_capabilities.py`.
- Apply to: `asyncio.wait_for(..., timeout=PROBE_TIMEOUT_SECONDS)` for neo4j health/RETURN 1/SHOW; `httpx` timeout=2.0 for `/api/tags`.
- Redaction surfaces (must never appear in `model_dump()` string form or logger call args for capabilities path):
  - raw `uuid_namespace` / `GRAPHITI_CATALOG_UUID_NAMESPACE`
  - `password`, `api_key`, `Authorization`, bearer tokens
  - raw Neo4j URI (`bolt://`, `neo4j://`, `neo4j+s://`)
  - raw embedder `api_url` / host:port from ollama config
  - full exception messages that may embed URLs — log `type(e).__name__` only

## 6. Formal verify commands

Task 1:
```
cd mcp_server && uv run pytest tests/test_catalog_capabilities.py tests/test_legacy_mcp_contract_compatibility.py -q --tb=short
```

Task 2:
```
python -c "from pathlib import Path; r=Path('mcp_server/README.md').read_text(encoding='utf-8'); m=Path('mcp_server/docs/CATALOG_V2_MIGRATION.md').read_text(encoding='utf-8'); assert 'get_catalog_capabilities' in r; assert '/api/tags' in r; assert 'catalog_entity_identity_unique' in r or '14' in r and 'uniqueness' in r.lower(); assert 'neo4j_indexes' in r and 'constraint' in r.lower(); assert 'canary' in m.lower(); print('docs-ok')"
```

Task 3:
```
docker build -f mcp_server/docker/Dockerfile.standalone -t graphiti-mcp:local-capabilities-truth .
docker image inspect graphiti-mcp:local-capabilities-truth --format "{{.Id}}"
```

Out of scope forever for this plan: git commit of product code unless executor SUMMARY-only workflow requires it for planning artifacts; no push; no deploy; no Kubernetes edits; no canary; no mutation of `oracle-catalog-v2`; preserve unrelated working-tree dirt.

</locked_contracts>

<architecture>
## Current gap
- `build_catalog_capabilities` pure config; client unused; connectivity/embeddings.ready/neo4j_indexes always unknown.
- MCP wrapper hardcodes `client=None`, `connectivity='unknown'`.
- CatalogStore already owns all 14 constraint names + `_constraint_row_matches` + three `_*_uniqueness_present` SHOW helpers. Ensure paths CREATE; capabilities must only inspect.

## Target (minimal)
1. Public `CatalogNeo4jStore.inspect_catalog_v2_schema_readiness(executor) ->` structure with per-group booleans + `ready: bool` (all 14). Reuse private presence checks; no CREATE; no ready-flag mutation.
2. `async def build_catalog_capabilities_async(...)` overlays probe results onto pure builder (keep pure builder for static unit tests).
3. MCP: `require_initialized_client` only; matrix in locked_contracts §4.
4. Constants: `PROBE_TIMEOUT_SECONDS = 2.0`; optional `CONNECTIVITY_CYPHER = 'RETURN 1 AS ok'`; SHOW body shared with store.
</architecture>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Read-only schema inspect + truthful probes + matrix tests</name>
  <files>mcp_server/src/services/catalog_store.py, mcp_server/src/services/catalog_capabilities.py, mcp_server/src/graphiti_mcp_server.py, mcp_server/tests/test_catalog_capabilities.py</files>
  <behavior>
    - Service None → ErrorResponse; no probes
    - Service set, client None → capabilities response; connectivity unknown; get_client not called
    - Service set, client initialized, neo4j, health_check ok → connectivity ok
    - health_check/RETURN 1 raises or times out → connectivity error
    - All 14 constraints present via inspect → neo4j_indexes ready
    - Any of 14 missing after successful SHOW → neo4j_indexes unknown
    - SHOW raises → neo4j_indexes unknown
    - backend falkordb → neo4j_indexes n/a
    - Ollama tags 200 + model present (normalize) → embeddings.ready ready
    - Ollama tags 200 + model missing → embeddings.ready error
    - Ollama tags fail/timeout → embeddings.ready error
    - OpenAI/other → embeddings.ready unknown; no HTTP
    - Captured Cypher ⊆ allowlist; no CREATE/DROP/ALTER/MERGE/SET/DELETE
    - Spies: get_client, initialize, build_indices_and_constraints, ensure_uuid_uniqueness_constraints, ensure_plan_schema, ensure_evidence_manifest_schema, execute_write, embedder.create all not called
    - Redaction: dump/logs free of password, api_key, raw namespace, bolt://, raw api_url
    - Field set + features preserved; tool union remains 28
    - PROBE_TIMEOUT_SECONDS == 2.0 exported/used
  </behavior>
  <action>
    Implement locked_contracts §§1–5 exactly.

    catalog_store.py: add `async def inspect_catalog_v2_schema_readiness(self, executor)` that returns readiness for identity/plan/evidence_manifest groups by calling existing `_identity_uniqueness_present`, `_plan_uniqueness_present`, `_evidence_manifest_uniqueness_present` (or one SHOW + all 14 `_constraint_row_matches`). Document the 14 names. Do not call ensure_* or set process-local ready flags.

    catalog_capabilities.py:
    - `PROBE_TIMEOUT_SECONDS = 2.0`
    - pure `build_catalog_capabilities` retained for static fields
    - `async def build_catalog_capabilities_async(...)` runs connectivity, schema, ollama probes per locked rules; overlays results
    - ollama model normalize helper as §2
    - redaction: never put URLs/secrets into response or log message templates

    graphiti_mcp_server.py `get_catalog_capabilities`:
    - if graphiti_service is None → ErrorResponse
    - client = require_initialized_client(graphiti_service)  # never get_client
    - pass backend, embedder provider/model, ollama api_url from config.providers.ollama when present
    - await build_catalog_capabilities_async(...)

    tests/test_catalog_capabilities.py:
    - add matrix tests for service None / client None / initialized
    - schema ready with all 14 names mocked present; missing-one unknown
    - ollama ready/missing-model-error/http-error; non-ollama unknown
    - capture execute_query / session.run Cypher list; assert each is allowlisted; assert forbidden keywords absent
    - assert ensure/bootstrap/write/embed spies not called
    - assert PROBE_TIMEOUT_SECONDS == 2.0
    - keep existing CAPA fingerprint/limits/features tests green
  </action>
  <verify>
    <automated>cd mcp_server &amp;&amp; uv run pytest tests/test_catalog_capabilities.py tests/test_legacy_mcp_contract_compatibility.py -q --tb=short</automated>
  </verify>
  <done>
    Truthful connectivity/schema/ollama readiness; 14-constraint inspect; Cypher allowlist + ensure forbids in tests; matrix locked; redaction + 2.0s timeout; 28-tool contract green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Operator docs — readiness semantics</name>
  <files>mcp_server/README.md, mcp_server/docs/CATALOG_V2_MIGRATION.md</files>
  <action>
    README Capabilities contract:
    - connectivity: already-initialized client only; health_check or RETURN 1; unknown if uninitialized; never get_client bootstrap; timeout 2.0s
    - neo4j_indexes: legacy field name; means full required Catalog-v2 uniqueness-constraint readiness (enumerate or reference the 14 names); no product Catalog-v2 indexes; ready only when all 14 present via SHOW CONSTRAINTS; missing/uninitialized unknown; non-neo4j n/a; never CREATE/DROP/ensure from capabilities
    - embeddings.ready: ollama GET /api/tags + configured model presence with documented normalize; missing model error; non-ollama unknown; never /api/embed
    - redaction: no secrets, raw namespace, raw URLs

    CATALOG_V2_MIGRATION.md: short pre-canary note — call get_catalog_capabilities for readiness; probes mutation-free; this work stops before canary retry (no Phase 6 execution here).
  </action>
  <verify>
    <automated>python -c "from pathlib import Path; r=Path('mcp_server/README.md').read_text(encoding='utf-8'); m=Path('mcp_server/docs/CATALOG_V2_MIGRATION.md').read_text(encoding='utf-8'); assert 'get_catalog_capabilities' in r; assert '/api/tags' in r; assert 'catalog_entity_identity_unique' in r or ('14' in r and 'uniqueness' in r.lower()); assert 'neo4j_indexes' in r and 'constraint' in r.lower(); assert 'canary' in m.lower(); print('docs-ok')"</automated>
  </verify>
  <done>
    Docs state 14-constraint semantics, ollama model check, matrix, timeout, stop-before-canary.
  </done>
</task>

<task type="auto">
  <name>Task 3: Local source-bound Docker image build only</name>
  <files>mcp_server/docker/Dockerfile.standalone</files>
  <action>
    From repo root only:
    `docker build -f mcp_server/docker/Dockerfile.standalone -t graphiti-mcp:local-capabilities-truth .`
    Do not push, deploy, edit k8s, edit compose defaults, run canary, or clear graphs. Preserve prior canary artifacts and existing local config dirt. Record image id in SUMMARY. Stop.
  </action>
  <verify>
    <automated>docker image inspect graphiti-mcp:local-capabilities-truth --format "{{.Id}}"</automated>
  </verify>
  <done>
    Local image exists; no push/deploy/k8s/canary/commit of unrelated dirt.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP client → get_catalog_capabilities | Untrusted caller; no secrets; no mutation |
| Capabilities → Neo4j | health_check / RETURN 1 / SHOW CONSTRAINTS only; initialized client only |
| Capabilities → Ollama | GET /api/tags only; no embed body; no URL in response |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-udj-01 | Information Disclosure | response/logs | high | mitigate | Redact namespace/passwords/api keys/URLs; log exception types only |
| T-udj-02 | Tampering | schema probe | high | mitigate | SHOW-only inspect of exact 14 constraints; never ensure/CREATE/DROP/ALTER |
| T-udj-03 | Denial of Service | probes | medium | mitigate | PROBE_TIMEOUT_SECONDS=2.0 on all external waits |
| T-udj-04 | Elevation of Privilege | bootstrap | high | mitigate | require_initialized_client only; service/client matrix |
| T-udj-05 | Spoofing | embedder ready | medium | mitigate | Ollama ready only on tags 200 + model present after normalize |
| T-udj-SC | Tampering | installs | low | accept | No new package-manager dependencies |
</threat_model>

<verification>
- pytest capabilities + legacy 28-tool green
- Cypher allowlist + forbidden ensure/write/embed spies
- Docs mention tags + constraint readiness + canary stop
- docker image inspect succeeds
- No canary/push/deploy/k8s
</verification>

<success_criteria>
- Truthful ok/error/unknown from read-only evidence
- 14 named constraints drive neo4j_indexes ready
- Ollama model presence required for ready
- Field set + 28 tools preserved
- Timeout 2.0s; redaction holds
- Local Docker only; stop before canary
</success_criteria>

<output>
Create `.planning/quick/260719-udj-implement-truthful-mutation-free-catalog/260719-udj-SUMMARY.md` when done
</output>
