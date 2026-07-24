# Phase 6: Native Ollama Clean-Room Remediation and Final Canary - Context

**Gathered:** 2026-07-23
**Status:** Ready for gap planning
**Mode:** Autonomous; updated specification resolves all material decisions

<domain>
## Phase Boundary

Remediate the terminal failed OpenAI-proxy canary through native Ollama TDD, exact fix-forward source/image binding, a wholly new clean-room runtime, and exactly one new final canary. Preserve the prior failed run and all historical resources/evidence unchanged. Stop permanently after the new canary terminal result; never retry or clean up after identity allocation.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**13 requirements are locked.** See `06-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `06-SPEC.md` and `spec/new-phase.md` before planning or implementing.

**In scope:** native Ollama config/factory/capability/launcher TDD, sanitized model/probe preflight, fix-forward archive/image, new isolated runtime, one new final canary, append-only sanitized evidence.

**Out of scope:** new provider implementation, OpenAI/proxy workaround, LLM calls, deployment, full ingest, historical mutation/cleanup, and any second new canary.

</spec_lock>

<decisions>
## Implementation Decisions

### Authority and Historical Isolation
- **D-01:** Reviewed operation authority is branch `v1.1` at `ab5fdeb70ce18df64b03c28190ee6ad5ab6803db`; the only intervening change from expected `50d6184` is `spec/new-phase.md`.
- **D-02:** Run `20260723t065038z-8b0d3621`, project `graphiti-phase6-cleanroom-1f529136`, fingerprint `5d54f7f83eb90194`, and its `FAILED_BEFORE_COMMIT` evidence are immutable. Never resume, retry, query, clean, delete, or reclassify them.
- **D-03:** Existing `06-CANARY-LEDGER.json`, `06-FINAL-REPORT.md`, `06-R0-RECEIPT.json` through `06-R3-RECEIPT.json`, old image, and old runtime remain historical only. New work writes distinct `06-OLLAMA-*` artifacts.
- **D-04:** Preserve the intentional absence of `06-05-SUMMARY.md`; do not manufacture scheduler completion for the old irreversible operation. Add append-only gap plans and execute only those plans under explicit orchestration.

### Native Ollama Configuration
- **D-05:** Exact embedding route: MCP → existing `OllamaEmbedder` → local native `/api/embed` → `qwen3-embedding:0.6b` → 1024 dimensions.
- **D-06:** Container base URL defaults to `http://host.docker.internal:11434`, expands from `OLLAMA_EMBEDDER_API_URL`, carries no `/v1`, API key, OpenAI embedder variable, proxy token, or authorization header.
- **D-07:** `truncate=true`; timeout 60 unless an already-reviewed local override exists. The generated config changes only the one namespace token.
- **D-08:** `mcp_server/config/config-docker-neo4j.yaml` remains protected, unstaged, and unmodified. Optional base-default correction is skipped if exact hunk separation from user changes is not provable.

### Factory, Dimensions, and Zero-LLM Contract
- **D-09:** Reuse the existing native provider; no new provider or abstraction. Factory tests must prove `OllamaEmbedder`, exact native request body/path, no credential, and no `OpenAIEmbedder` construction.
- **D-10:** Every returned vector must contain exactly 1024 finite numbers. Dimension mismatch fails before any graph write.
- **D-11:** Catalog prepare/commit and the whole canary make zero LLM calls. Existing LLM config may remain only for server construction.

### Capability and Waiver Policy
- **D-12:** Exact model presence from `/api/tags` yields `embeddings.ready=ready`; missing model or unreachable daemon yields `error`; raw endpoint stays absent from outputs/logs.
- **D-13:** Ollama never receives an unknown-readiness waiver. Manifest remains exactly 22 fields with `allow_unknown_embedding_provider=null`.
- **D-14:** Provider, model, dimensions, readiness, null waiver, endpoint/config authority, image, and Git state are freeze-bound and fail closed on drift.

### Launcher and Evidence Namespacing
- **D-15:** Builder and runner argv are conditional. Ollama gets no `--allow-unknown-embedding-provider` pair; OpenAI waiver behavior may remain for separately authorized deployments.
- **D-16:** The new launcher/freeze path writes only `06-OLLAMA-*` freeze, invocation, canary-ledger, and final-report artifacts. It must not map new output into old evidence paths.
- **D-17:** Freeze receipt records only sanitized endpoint/config authority, never the raw URL or namespace.

### Local Ollama Preflight
- **D-18:** Before image/runtime work, check daemon, GET `/api/tags`, and exact model presence. If absent, only one `ollama pull qwen3-embedding:0.6b` is authorized.
- **D-19:** Run one harmless native embedding probe with exact dimensions and no credential/proxy/LLM. Persist only reachability, model presence, endpoint success, observed dimension 1024, and `credential_used=false`; never vector values.

### New Runtime and Final Boundary
- **D-20:** Create a new Compose project, data/log volumes, network, namespace, Neo4j container, MCP container, and canary identities. Reuse none from the failed project.
- **D-21:** Runtime gate requires absent-before-creation, `0/14` → one bootstrap → first `14/14`, exact image ID, 28 tools, exact Ollama model/dimensions, readiness `ready`, null waiver, bound namespace fingerprint, endpoint reachable, and zero LLM calls.
- **D-22:** Gate 2 `search_nodes` is the first read-only runtime embedding proof; successful prepare is the second mandatory proof.
- **D-23:** Commit the new prefreeze package before IDs, then stop at a blocking human freeze checkpoint. Top-level writes the uncommitted freeze receipt and consumes explicit approval; never resume the old or new final executor after that checkpoint.
- **D-24:** After any new ID allocation: no edit, commit, rebuild, reconfiguration, retry, alternate runtime, cleanup, or deletion. Execute one builder and one runner only; leave the final stack intact.

### Claude's Discretion
- Use the minimum source/test changes that satisfy RED tests. Prefer existing `OllamaEmbedder`, readiness probe, raw-Git archive, scanner, materializer, launcher, builder, runner, and schema bootstrap.
- Group the append-only gap work into sequential TDD, bind, image, and runtime/final-canary plans. No parallel mutation across these authorities.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Updated Authority
- `spec/new-phase.md` — canonical native Ollama operation and final-canary authorization.
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-SPEC.md` — locked requirement IDs and scope.

### Immutable Prior Terminal Evidence
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-CANARY-LEDGER.json` — canonical prior terminal ledger; read-only.
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md` — prior Gate 2 terminal report; read-only.
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-R0-RECEIPT.json` through `06-R3-RECEIPT.json` — prior runtime receipts; read-only.

### Existing Contracts
- `graphiti_mcp_phase6_canary_agent_prompt_en.md` — exact canary protocol and Gate 0 source authority.
- `mcp_server/config/config-docker-neo4j.catalog-local.example.yaml` — committed clean-room config target.
- `scripts/materialize_catalog_local_config.py` — namespace-exclusive config materializer.
- `scripts/run_catalog_phase6_final_canary.py` — freeze validation, allocation, builder/runner launch, and output mapping authority to remediate.
- `scripts/build_catalog_canary_requests.py` — exact 22-field manifest builder.
- `scripts/run_catalog_canary_batch.py` — runtime readiness and Gates 0–10 authority.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `graphiti_core/embedder/ollama.py`: existing native `/api/embed` client already sends model, dimensions, and truncate; validates cardinality, dimension, and finite values.
- `mcp_server/src/services/factories.py`: existing `ollama` factory branch requires no API key and constructs `OllamaEmbedderConfig` from typed config.
- `mcp_server/src/services/catalog_capabilities.py`: existing read-only `/api/tags` probe already maps exact-model present to `ready`, missing/unreachable to `error`, and logs only exception type.
- `scripts/materialize_catalog_local_config.py`: exclusive clean-room authority and one-token namespace replacement.
- `scripts/catalog_raw_git_archive.py` and `scripts/catalog_image_secret_scanner.py`: exact source and complete-image proof machinery.
- `scripts/run_catalog_phase6_final_canary.py`: exact-argv, job-temp, freeze, allocation, and one-shot child launch guards; hardcoded OpenAI waiver/output paths are the focused remediation seam.

### Established Patterns
- RED → minimal GREEN → adjacent regression → full frozen matrix.
- Structured subprocess argv with `shell=False`; fixed allowlists; no secret-bearing argv.
- Fix-forward commits and exact raw-Git archive binding.
- Sanitized receipts; raw namespace, URL parameters, credentials, tokens, vectors, payloads, and environments never enter evidence.
- Embeddings complete before write transactions; commit performs no network/LLM operation.

### Integration Points
- Replace only the clean-room example embedder block; materializer should remain generic.
- Thread configured embedding dimensions into sanitized capability/freeze authority only if required by tests; never expose endpoint.
- Make final-canary builder/runner waiver flags conditional and new output paths operation-specific.
- Keep exact 22-field manifest and exact 28-tool registry unchanged.

</code_context>

<specifics>
## Specific Ideas

- Use append-only plans `06-06` onward; preserve old `06-05` plan and missing-summary guard.
- Use `06-OLLAMA-*` filenames for all new receipts, freeze inputs, invocation, ledger, and report.
- Required real E2E environment: `CATALOG_OLLAMA_REQUIRED=1`, `CATALOG_OLLAMA_MODEL=qwen3-embedding:0.6b`, `CATALOG_OLLAMA_DIMENSIONS=1024`.
- Never include a vector or raw endpoint in evidence, even for the harmless probe.

</specifics>

<deferred>
## Deferred Ideas

- Public/OpenAI provider remediation, automatic migration, full catalog ingest, deployment, Kubernetes, historical cleanup, other Ollama models, and any second canary remain out of scope.

</deferred>

---

*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Context gathered: 2026-07-23*
