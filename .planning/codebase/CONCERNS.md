# Codebase Concerns

**Analysis Date:** 2026-07-16

## Tech Debt

**Monolithic orchestration file:**
- Issue: `Graphiti` class owns ingestion, search, communities, sagas, triplets, bulk paths, and telemetry in one file (~1798 lines)
- Files: `graphiti_core/graphiti.py`
- Impact: Hard to review, high regression risk on any episode/search change; many cross-cutting responsibilities share one surface
- Fix approach: Extract saga helpers, community rebuild, and bulk ingestion into focused modules under `graphiti_core/utils/maintenance/`; keep `Graphiti` as a thin facade

**God-file search utilities:**
- Issue: Hybrid search, fulltext building, embedding similarity, and provider branching live in one ~2064-line module
- Files: `graphiti_core/search/search_utils.py`
- Impact: Provider-specific branches (Neo4j / FalkorDB / Kuzu / Neptune) are hard to isolate; Kuzu FIXMEs sit mid-flow
- Fix approach: Split by concern (`fulltext.py`, `vector_search.py`, `node_relevance.py`) and per-provider search ops already under `graphiti_core/driver/*/operations/search_ops.py`

**MCP server as global-state monolith:**
- Issue: Single ~1439-line module with module-level `graphiti_service`, `queue_service`, `graphiti_client`, `semaphore`, and `config`; nearly every tool re-declares `global graphiti_service`
- Files: `mcp_server/src/graphiti_mcp_server.py`
- Impact: Untestable tools without full process boot; racey re-init; hard concurrent multi-tenant use
- Fix approach: Move tools onto a service class; inject deps; keep `main.py` as bootstrap only

**Dual semaphore defaults:**
- Issue: Core defaults `SEMAPHORE_LIMIT=20` (`graphiti_core/helpers.py`); MCP defaults `SEMAPHORE_LIMIT=10` (`mcp_server/src/graphiti_mcp_server.py`); k8s sets `"10"`
- Files: `graphiti_core/helpers.py`, `mcp_server/src/graphiti_mcp_server.py`, `mcp_server/k8s/graphiti-neo4j.yaml`
- Impact: Throughput and rate-limit behavior differ by entrypoint; operators must know which process they are tuning
- Fix approach: Document one canonical default; pass limit only through `Graphiti(max_coroutines=...)` / MCP config

**Legacy dual driver interfaces:**
- Issue: `search_interface` / `graph_operations_interface` kept “for backwards compatibility during Phase 1” alongside newer `*_ops` properties that default to `None`
- Files: `graphiti_core/driver/driver.py`, `graphiti_core/driver/graph_operations/graph_operations.py`
- Impact: Call sites try interface then fall back (`NotImplementedError` catch); incomplete ops silently degrade
- Fix approach: Finish Phase 1 migration; remove legacy interfaces or make ops non-optional on each concrete driver

**Kuzu support is incomplete and deprecated:**
- Issue: Upstream Kuzu unmaintained; extra marked for removal; bulk UNWIND and FTS variable binding broken
- Files: `pyproject.toml` (kuzu extra comment), `graphiti_core/utils/bulk_utils.py` (FIXME ~line 234), `graphiti_core/search/search_utils.py` (FIXME ~line 1287), `graphiti_core/driver/kuzu_driver.py`
- Impact: Kuzu path is row-by-row (slow bulk); `get_relevant_nodes()` FTS path does not work; dead maintenance cost
- Fix approach: Drop Kuzu from public support; gate remaining code behind explicit experimental flag until removed

**Azure AD auth unfinished:**
- Issue: Azure OpenAI factory only supports API keys; AD support is TODO twice
- Files: `mcp_server/src/services/factories.py` (~lines 195, 346)
- Impact: Enterprise Azure deployments cannot use managed identity / Entra auth through MCP
- Fix approach: Wire `DefaultAzureCredential` / token provider when `use_azure_ad` is true; cover with factory tests

**`organization_id` config is dead:**
- Issue: `OpenAIProviderConfig.organization_id` exists in schema and YAML, but factories never pass it into OpenAI clients; core `LLMConfig` / `OpenAIEmbedder` have no organization field
- Files: `mcp_server/src/config/schema.py`, `mcp_server/src/services/factories.py`, `graphiti_core/llm_client/config.py`, `graphiti_core/embedder/openai.py`
- Impact: Multi-org OpenAI accounts silently ignore configured org; dirty k8s change around `${OPENAI_ORGANIZATION_ID}` does not affect runtime
- Fix approach: Pass `organization=` into `AsyncOpenAI` in factories and core embedder/LLM clients, or remove the field from schema/config

**In-memory episode queue (MCP):**
- Issue: `QueueService` stores work in process-local `asyncio.Queue` per `group_id`; workers started via fire-and-forget `create_task`; no durability, no backpressure bound, no restart recovery
- Files: `mcp_server/src/services/queue_service.py`, `mcp_server/src/graphiti_mcp_server.py` (`add_memory`)
- Impact: Pod restart drops queued episodes; success response means “queued”, not “persisted”; unbounded memory under load
- Fix approach: Persist queue (Redis/DB) or make `add_memory` await completion with optional async mode; add max queue size and metrics

**FalkorDB fire-and-forget index build:**
- Issue: Constructor schedules `build_indices_and_constraints()` with `loop.create_task` when a loop exists; errors only surface later
- Files: `graphiti_core/driver/falkordb_driver.py` (~lines 176–184)
- Impact: First queries can race incomplete indexes; failures are easy to miss
- Fix approach: Require explicit `await driver.build_indices_and_constraints()` (same as Neo4j path) and remove auto-schedule from `__init__`

**Health checks use `print`:**
- Issue: Neo4j and FalkorDB health failures print to stdout instead of logger
- Files: `graphiti_core/driver/neo4j_driver.py` (~line 224), `graphiti_core/driver/falkordb_driver.py` (~line 344)
- Impact: Lost in structured log pipelines; noisy in MCP/stdio mode
- Fix approach: Use module `logger.exception` / `logger.error`

**Server package type-ignore pile and weak coupling:**
- Issue: `server/graph_service` uses many `# type: ignore` imports; depends on published `graphiti-core` version pin rather than monorepo path by default; only one live integration test
- Files: `server/graph_service/zep_graphiti.py`, `server/graph_service/routers/ingest.py`, `server/pyproject.toml`, `server/tests/test_live_falkordb_int.py`
- Impact: Server drifts from core APIs; type errors hidden; limited CI coverage of REST surface
- Fix approach: Path-depend on local core in monorepo; remove ignores; add router unit tests with mocked `ZepGraphiti`

**Dirty working tree / fork-specific deploy config:**
- Issue: Uncommitted `mcp_server/k8s/graphiti-neo4j.yaml` hardcodes cluster-internal defaults (`router9.shb-smartcard.svc.cluster.local`, NodePort `30080`, host `10.4.97.70`, image `ghcr.io/thienpvt/graphiti-mcp:sha-...`, Oracle entity ontology). Untracked `mcp_server/sample_catalog.json` (~1009 lines) and `.codegraph/` index DB
- Files: `mcp_server/k8s/graphiti-neo4j.yaml`, `mcp_server/sample_catalog.json`, `.codegraph/`
- Impact: Upstream PRs risk leaking environment-specific topology; sample catalog and codegraph artifacts should not ship as product defaults without review
- Fix approach: Parameterize k8s defaults for public/generic deploy; gitignore `.codegraph/`; treat sample catalog as fixture under `examples/` or docs

## Known Bugs

**Embedding dimension truncation without pad/check (OpenAI/Voyage):**
- Symptoms: Vectors silently sliced to `embedding_dim`; shorter vectors accepted as-is (no pad); similarity can degrade if model dim ≠ configured dim
- Files: `graphiti_core/embedder/openai.py` (lines 60, 66), `graphiti_core/embedder/voyage.py`
- Trigger: Set `embedding_dim` lower or higher than model native size
- Workaround: Match `embedding_dim` to model output; Ollama path already validates length in `graphiti_core/embedder/ollama.py`

**Kuzu relevance search broken:**
- Symptoms: `get_relevant_nodes()` FTS path cannot bind node fulltext variables on Kuzu
- Files: `graphiti_core/search/search_utils.py` (~line 1287)
- Trigger: Use Kuzu driver for node relevance / hybrid flows that call this path
- Workaround: Use Neo4j or FalkorDB

**Kuzu bulk insert not bulk:**
- Symptoms: Episode/node/edge bulk saves loop one row at a time
- Files: `graphiti_core/utils/bulk_utils.py` (~line 234)
- Trigger: `add_episode_bulk` / bulk save with Kuzu
- Workaround: Avoid bulk path on Kuzu; use Neo4j/FalkorDB

**Neptune AOSS index creation hard sleep:**
- Symptoms: `create_aoss_indices` always `await asyncio.sleep(60)` after create
- Files: `graphiti_core/driver/neptune_driver.py` (~line 327)
- Trigger: `build_indices_and_constraints` on Neptune
- Workaround: Accept 60s boot delay; replace with index-ready polling when fixing

**MCP `add_memory` success is not durability:**
- Symptoms: Client gets success when episode is only enqueued; worker errors log and drop task without client callback
- Files: `mcp_server/src/services/queue_service.py` (`_process_episode_queue` swallows exceptions), `mcp_server/src/graphiti_mcp_server.py` (`add_memory`)
- Trigger: LLM/DB failure during background processing after queue accept
- Workaround: Poll graph / logs; do not treat queue success as committed memory

## Security Considerations

**MCP NodePort without app auth or TLS:**
- Risk: Anyone who can reach the NodePort can call memory tools including `clear_graph`, `delete_episode`, `delete_entity_edge`
- Files: `mcp_server/k8s/graphiti-neo4j.yaml` (header comments + Service type `NodePort` 30080), `mcp_server/src/graphiti_mcp_server.py` (destructive tools)
- Current mitigation: DNS rebinding protection via `FASTMCP_HTTP_ALLOWED_HOSTS` / `TransportSecuritySettings`; comments warn to firewall/VPN/ingress
- Recommendations: Put authenticated TLS ingress in front; remove or gate destructive tools; network policies; never expose NodePort publicly

**REST graph service has no authentication:**
- Risk: Unauthenticated ingest/retrieve/delete if `server/` is network-reachable
- Files: `server/graph_service/main.py`, `server/graph_service/routers/ingest.py`, `server/graph_service/routers/retrieve.py`
- Current mitigation: None in application layer
- Recommendations: Add API key / mTLS / reverse-proxy auth before any non-local deploy

**Hardcoded internal LLM router defaults in committed k8s:**
- Risk: Fork deploy config points at private cluster DNS (`router9.shb-smartcard.svc.cluster.local`) and fixed host allowlist IP; merges can leak topology
- Files: `mcp_server/k8s/graphiti-neo4j.yaml` (LLM/embedder `api_url` defaults, `FASTMCP_HTTP_ALLOWED_HOSTS`)
- Current mitigation: Secrets via `graphiti-secrets`; comments document exposure risk
- Recommendations: Empty/public defaults in repo; inject cluster URLs only via env/sealed secrets

**Telemetry default-on with baked PostHog key:**
- Risk: Anonymous usage events leave process by default; some environments treat any outbound analytics as non-compliant
- Files: `graphiti_core/telemetry/telemetry.py` (`GRAPHITI_TELEMETRY_ENABLED` default true, public PostHog key)
- Current mitigation: Disable with env; no-op under pytest; silent failure on error
- Recommendations: Document opt-out prominently; consider default-off for enterprise builds

**Cypher label injection surface (mitigated, keep tests):**
- Risk: Dynamic node labels in queries if validation bypassed
- Files: `graphiti_core/helpers.py` (`SAFE_CYPHER_IDENTIFIER_PATTERN`, `validate_node_labels`), `tests/test_node_label_security.py`
- Current mitigation: Pydantic + query-builder validation; dedicated security tests
- Recommendations: Keep tests required in CI; never interpolate unvalidated labels

**Neptune parameter rewriting is brittle:**
- Risk: String `replace` of `$param` and embedding datetime literals into query text can mis-handle complex params
- Files: `graphiti_core/driver/neptune_driver.py` (`_sanitize_parameters`)
- Current mitigation: Parameterized values still mostly used; datetime special-case only
- Recommendations: Prefer driver-native temporal types / bound params only; add adversarial param tests

## Performance Bottlenecks

**Episode ingestion LLM fan-out:**
- Problem: Each episode triggers multiple LLM calls (extract nodes, edges, dedupe, attributes, optional communities)
- Files: `graphiti_core/graphiti.py` (`add_episode`, `add_episode_bulk`), `graphiti_core/utils/maintenance/node_operations.py`, `edge_operations.py`
- Cause: Sequential pipeline with concurrent LLM calls gated by semaphore
- Improvement path: Tune `SEMAPHORE_LIMIT`; cache embeddings; batch LLM where providers allow; skip community update unless requested

**Search utils size and provider branching:**
- Problem: Large query assembly and multiple hybrid strategies in one hot path
- Files: `graphiti_core/search/search_utils.py`, `graphiti_core/search/search.py`
- Cause: Fulltext + vector + graph distance + optional cross-encoder rerank
- Improvement path: Cache embeddings for repeated queries; short-circuit empty fulltext; profile per provider

**Kuzu row-by-row bulk:**
- Problem: O(n) round-trips for bulk episode materialization
- Files: `graphiti_core/utils/bulk_utils.py`
- Cause: STRUCT[] UNWIND unsupported
- Improvement path: Remove Kuzu or implement native batch once supported

**Neptune index wait:**
- Problem: Fixed 60s sleep on index create
- Files: `graphiti_core/driver/neptune_driver.py`
- Cause: No readiness poll
- Improvement path: Poll AOSS index health with timeout/backoff

**Community rebuild clears all communities first:**
- Problem: `build_communities` calls `remove_communities` then full rebuild
- Files: `graphiti_core/graphiti.py`, `graphiti_core/utils/maintenance/community_operations.py`
- Cause: Full graph community algorithm + LLM summaries
- Improvement path: Incremental community update path already exists for single-episode updates; prefer it over full rebuild

## Fragile Areas

**MCP global service lifecycle:**
- Files: `mcp_server/src/graphiti_mcp_server.py`
- Why fragile: Tools assume process-global init; partial init returns string errors; destroy-graph flag can wipe data on boot
- Safe modification: Change service methods first; keep tool wrappers thin; never add new globals
- Test coverage: MCP has unit/integration tests under `mcp_server/tests/`, but many paths need live DB/LLM

**Multi-driver query dialect:**
- Files: `graphiti_core/driver/*`, `graphiti_core/models/nodes/node_db_queries.py`, `graphiti_core/models/edges/edge_db_queries.py`, `graphiti_core/search/search_utils.py`
- Why fragile: Same logical operation has Neo4j / FalkorDB / Kuzu / Neptune variants; easy to fix one backend and break another
- Safe modification: Change via driver ops interfaces; run provider-specific tests; avoid raw Cypher in `graphiti.py`
- Test coverage: Integration tests marked `_int` need real DBs; unit suite mocks heavily in `tests/test_graphiti_mock.py`

**Episode queue worker error swallowing:**
- Files: `mcp_server/src/services/queue_service.py`
- Why fragile: Exceptions logged then discarded; no retry/DLQ; worker flag reset only on cancel/fatal
- Safe modification: Add structured failure events before expanding queue semantics
- Test coverage: Limited; queue behavior needs explicit failure tests

**Config env expansion empty-string → None:**
- Files: `mcp_server/src/config/schema.py` (`YamlSettingsSource._expand_env_vars`)
- Why fragile: `${VAR:}` and unset vars become `None`/empty; dirty k8s change from `${OPENAI_ORGANIZATION_ID:}` to `${OPENAI_ORGANIZATION_ID}` changes defaulting behavior
- Safe modification: Prefer explicit defaults; unit-test expansion edge cases (`mcp_server/tests/test_configuration.py`)

**`load_dotenv()` at import time:**
- Files: `graphiti_core/graphiti.py`, `graphiti_core/helpers.py`, `mcp_server/src/graphiti_mcp_server.py`
- Why fragile: Import order mutates process env; tests/library embeds can pick up unexpected `.env`
- Safe modification: Load env only in CLIs/entrypoints, not library import side effects

## Scaling Limits

**Single-replica Neo4j in k8s manifest:**
- Current capacity: `replicas: 1`, Recreate strategy, heap max 1G, pagecache 512m
- Limit: No HA; storage depends on NFS locking/fsync (noted in manifest comments)
- Scaling path: Neo4j cluster or managed Neo4j; separate PVC class validated for Neo4j

**MCP resource caps:**
- Current capacity: requests 500m/512Mi, limits 2 CPU / 1Gi; `SEMAPHORE_LIMIT=10`
- Limit: Concurrent episode processing and embedding/LLM payloads will OOM or throttle under multi-user load
- Scaling path: Horizontal pods only after queue is externalized; raise memory with larger embedding batches carefully

**In-process queue memory:**
- Current capacity: Unbounded `asyncio.Queue` per group
- Limit: Memory grows with backlog; multi-group multiplies workers
- Scaling path: Maxsize + reject/backpressure; external broker

**LLM provider rate limits:**
- Current capacity: Documented in MCP comments (OpenAI tiers, Anthropic RPM)
- Limit: 429s when semaphore too high
- Scaling path: Lower `SEMAPHORE_LIMIT`; multi-key routing outside this repo

## Dependencies at Risk

**Kuzu (optional extra):**
- Risk: Upstream unmaintained; removal planned
- Impact: Users on Kuzu lose supported backend
- Migration plan: Neo4j or FalkorDB; remove `kuzu` extra and driver package

**FalkorDB + redis pin:**
- Risk: `redis<9` required because redis-py 8.x breaks `falkordblite` embedded startup
- Impact: Cannot freely upgrade redis ecosystem packages on FalkorLite path
- Migration plan: Track falkordblite/redis-py fix; document pin in release notes

**`graphiti-core` version coupling in server:**
- Risk: `server` depends on `graphiti-core>=0.28.2` while monorepo core is `0.29.2`
- Impact: Container/server builds can lag core features/fixes
- Migration plan: Always release/server-build from same monorepo revision

**PostHog hard dependency:**
- Risk: `posthog>=3.0.0` is a core dependency even when telemetry disabled
- Impact: Extra install surface; outbound host must be allowed or blocked
- Migration plan: Make telemetry optional extra; lazy-import only

## Missing Critical Features

**Application-level auth for MCP HTTP and REST server:**
- Problem: No API keys/OAuth on tools or REST routers
- Blocks: Safe multi-tenant or internet-facing deployment

**Durable async ingestion with status API:**
- Problem: Queue is memory-only; no job id / status / retry
- Blocks: Reliable production ingestion and client confirmation

**Azure AD for Azure OpenAI in MCP:**
- Problem: API key only
- Blocks: Keyless Azure enterprise auth

**OpenAI organization propagation:**
- Problem: Config field unused end-to-end
- Blocks: Correct billing/org routing for multi-org OpenAI accounts

## Test Coverage Gaps

**Kuzu driver and broken search/bulk paths:**
- What's not tested: FTS variable limitation and STRUCT bulk workaround correctness under load
- Files: `graphiti_core/driver/kuzu_driver.py`, `graphiti_core/search/search_utils.py`, `graphiti_core/utils/bulk_utils.py`
- Risk: Silent wrong relevance results; severe bulk latency regressions
- Priority: Low if Kuzu is being removed; High if still advertised

**MCP queue failure/retry semantics:**
- What's not tested: Worker exception after enqueue; process restart mid-queue; backpressure
- Files: `mcp_server/src/services/queue_service.py`
- Risk: Data loss reported as success
- Priority: High

**REST server routers:**
- What's not tested: Most ingest/retrieve paths without live FalkorDB; no auth negative tests
- Files: `server/graph_service/routers/`, `server/tests/`
- Risk: API regressions ship unnoticed
- Priority: Medium

**Neptune driver:**
- What's not tested: `_sanitize_parameters` datetime rewrite edge cases; AOSS query mutation of shared `aoss_indices` query templates
- Files: `graphiti_core/driver/neptune_driver.py` (module-level `aoss_indices` mutated at runtime)
- Risk: Concurrent searches corrupt shared query dict; datetime bugs
- Priority: High for Neptune users; Medium overall

**Dirty k8s/config expansion:**
- What's not tested: `${OPENAI_EMBEDDER_API_KEY}` / required-vs-default organization expansion in real ConfigMap rendering
- Files: `mcp_server/k8s/graphiti-neo4j.yaml`, `mcp_server/src/config/schema.py`
- Risk: Pod starts with missing embedder key or wrong org
- Priority: Medium

**Core unit vs integration balance:**
- What's not tested: Full multi-provider matrix in CI without secrets/DBs; only 6 `*_int.py` core integration modules
- Files: `tests/test_*_int.py`, `tests/test_graphiti_mock.py`
- Risk: Provider-specific Cypher breaks between releases
- Priority: Medium

---

*Concerns audit: 2026-07-16*
