# Operation: Phase 6 Native Ollama Clean-Room Remediation and Final Canary

Authorization:
ITERATIVE_TDD_NATIVE_OLLAMA_REMEDIATION_AND_ONE_NEW_FINAL_CANARY

## 1. Source authority

Start from and verify the current v1.1 authority:

- Expected branch: v1.1
- Expected starting HEAD:
  50d618453f0e6f50b0292a40c1fad9aa72914d87

If the branch has advanced, inspect the intervening commits and bind the
operation to the actual reviewed HEAD. Do not silently apply this plan to an
unreviewed source state.

The previous failed canary remains immutable:

- Classification: FAILED_BEFORE_COMMIT
- Run: 20260723t065038z-8b0d3621
- Project: graphiti-phase6-cleanroom-1f529136
- Namespace fingerprint: 5d54f7f83eb90194
- Prepare calls: 0
- Commit calls: 0
- Persistent writes: 0

Do not resume, retry, query, clean up, delete, or reclassify that run.

## 2. Correct target architecture

The embedding path must be exactly:

Graphiti MCP
→ native graphiti_core.embedder.ollama.OllamaEmbedder
→ local Ollama native /api/embed
→ qwen3-embedding:0.6b
→ dimensions=1024

Embedding traffic must not pass through:

- OpenAI;
- an OpenAI-compatible proxy;
- OmniRoute;
- a chat/completion route;
- any public provider.

No LLM operation is required or authorized.

Do not call:

- add_memory;
- summarize_saga;
- build_communities;
- LLM extraction;
- chat completion;
- response generation.

The existing LLM configuration may remain available for server construction,
but this canary must make zero LLM calls.

## 3. Native Ollama authority

Use:

- provider: ollama
- model: qwen3-embedding:0.6b
- dimensions: 1024
- API URL from the MCP container:
  http://host.docker.internal:11434
- API key: absent/null
- truncate: true
- timeout: 60 unless an already reviewed local override exists

The local Ollama endpoint requires no credential.

Never populate:

- OPENAI_EMBEDDER_API_KEY;
- OPENAI_EMBEDDER_API_URL;
- an embedding proxy token;
- OLLAMA_API_KEY for the local endpoint.

Do not change or expose unrelated LLM configuration or local proxy credentials.

## 4. TDD Stage A — Clean-room configuration RED tests

Write failing tests before production changes.

Prove that the committed Catalog-v2 clean-room example and generated local
configuration contain:

- embedder.provider == ollama;
- embedder.model == qwen3-embedding:0.6b;
- embedder.dimensions == 1024;
- providers.ollama.api_url resolves from OLLAMA_EMBEDDER_API_URL;
- default Docker value is http://host.docker.internal:11434;
- providers.ollama.api_key is absent/null;
- truncate == true;
- no OpenAI embedder requirement;
- exactly one Catalog UUID namespace token before materialization;
- no raw namespace or credentials in evidence.

Prove the materializer preserves the Ollama section byte-for-byte except for
the Catalog UUID namespace replacement.

The generated clean-room file must not fall back to provider=openai.

## 5. TDD Stage B — Native factory and dimension tests

Retain and extend tests proving:

- provider=ollama creates OllamaEmbedder;
- it does not create OpenAIEmbedder;
- local Ollama requires no API key;
- base URL remains the native Ollama root without `/v1`;
- requests go to `/api/embed`;
- request body carries model qwen3-embedding:0.6b;
- request body carries dimensions=1024;
- returned vectors must have exactly 1024 elements;
- mismatched dimensions fail before any graph write;
- no LLM client method is invoked by catalog prepare/commit.

Do not implement a new embedding provider. The native provider already exists.

## 6. TDD Stage C — Capability and waiver policy

Add tests proving:

- provider=ollama plus `/api/tags` containing
  qwen3-embedding:0.6b returns embeddings.ready=ready;
- missing model returns error;
- unreachable Ollama returns error;
- raw Ollama URL is absent from capability output and logs;
- provider=ollama with ready=unknown does not receive a waiver;
- provider=ollama with ready=ready passes without any waiver.

For the Ollama clean-room manifest:

allow_unknown_embedding_provider = null

Do not change the exact 22-field manifest schema.

The existing OpenAI waiver implementation may remain for separately authorized
OpenAI deployments, but it must not be selected by this Ollama canary.

## 7. TDD Stage D — Final-canary launcher

Remove the unconditional hardcoded arguments:

--allow-unknown-embedding-provider openai

from the native Ollama final-canary execution path.

Bind the freeze receipt to sanitized embedding authority:

- embedding_provider: ollama
- embedding_model: qwen3-embedding:0.6b
- embedding_dimensions: 1024
- expected_embedding_readiness: ready
- allow_unknown_embedding_provider: null

Build builder and runner argv conditionally from reviewed freeze authority.

For this Ollama operation:

- builder receives no waiver argument;
- runner receives no waiver argument;
- manifest field remains null;
- observed provider must be ollama;
- observed model must be qwen3-embedding:0.6b;
- observed readiness must be ready.

Reject:

- observed provider=openai;
- observed readiness=unknown;
- non-null OpenAI waiver;
- model drift;
- dimension drift;
- endpoint switching after freeze.

## 8. Configuration changes

Update:

mcp_server/config/config-docker-neo4j.catalog-local.example.yaml

to use native Ollama with model qwen3-embedding:0.6b and dimensions 1024.

Also correct committed default dimension for the same model where safely
possible.

The working-tree file:

mcp_server/config/config-docker-neo4j.yaml

may contain user-owned local changes.

Do not overwrite or stage unrelated hunks from that file.

If changing its committed default would overlap user-owned modifications:

- preserve the working file;
- use path-specific/partial staging only if exact separation is proven;
- otherwise leave that optional base-default correction for a separate commit;
- do not block the clean-room config fix.

The Catalog clean-room override mounts the generated catalog-local config, so
that config is the runtime authority for this canary.

## 9. Local Ollama preflight

Before building or starting a final clean-room stack, perform sanitized
read-only checks:

1. Confirm the local Ollama daemon is reachable.
2. GET /api/tags.
3. Confirm exact model qwen3-embedding:0.6b is installed.

If the exact model is absent, this operation authorizes one:

ollama pull qwen3-embedding:0.6b

Do not pull any other model and do not delete existing models.

After availability is established, execute one native embedding probe with:

- a fixed harmless test string;
- dimensions=1024;
- no API key;
- no proxy;
- no LLM.

Require:

- HTTP success;
- one embedding;
- exactly 1024 finite numeric values.

Do not persist or report the vector.

Report only:

- daemon reachable;
- model present;
- native endpoint successful;
- observed dimension=1024;
- credential_used=false.

## 10. Complete TDD loop

Run RED → GREEN iterations until all focused tests pass.

Then run:

- changed Python compilation;
- native Ollama embedder tests;
- factory tests;
- configuration/materializer tests;
- Catalog capability tests;
- final-canary launcher tests;
- builder/runner tests;
- schema-bootstrap tests;
- Phase 5 suite;
- Phase 6 suite;
- combined remediation suite;
- full relevant union;
- exact golden hashes;
- exact 22-field manifest check;
- exact 28-tool registry check;
- Ruff check;
- Ruff format check;
- Pyright;
- required real local Ollama E2E with:
  CATALOG_OLLAMA_REQUIRED=1
  CATALOG_OLLAMA_MODEL=qwen3-embedding:0.6b
  CATALOG_OLLAMA_DIMENSIONS=1024

Ordinary failures caused by this task remain inside the TDD loop.

Do not skip, deselect, suppress, or weaken tests.

## 11. Commit and source-bound image

After the full matrix passes:

1. Commit only task-owned source, tests, and documentation.
2. Preserve user-owned dirty paths.
3. Produce a raw-Git LF-exact archive.
4. Rerun the complete frozen matrix from that archive.
5. Build a new source-bound runtime image.
6. Bind OCI revision and source-context labels.
7. Scan for namespaces, local config, API keys, proxy tokens, and evidence.
8. Do not push or retag.

The previous OpenAI-path runtime image is not authority for the new Ollama
canary.

## 12. New clean-room runtime

Create entirely new:

- Compose project;
- Neo4j data volume;
- Neo4j log volume;
- namespace;
- network;
- MCP container;
- canary identifiers.

Do not reuse the failed clean-room project or volumes.

Before canary allocation require:

- Neo4j clean-room volume initially 0/14;
- one schema bootstrap;
- first post-bootstrap result 14/14;
- exactly 28 MCP tools;
- provider=ollama;
- model=qwen3-embedding:0.6b;
- embeddings.ready=ready;
- no waiver;
- native endpoint reachable;
- namespace fingerprint bound;
- running image ID exact;
- zero LLM calls.

Gate 2 search_nodes is the first read-only runtime embedding proof.

Successful prepare_catalog_batch is the second mandatory embedding proof.

## 13. One final canary

Only after every TDD, image, Ollama, and runtime gate passes, allocate one new
canary.

Require:

- new run/group/control/batch;
- exact 22-field manifest with null waiver;
- exactly one dry_run=true;
- expected 3 entities, 2 edges, 1 source, 5 evidence links;
- zero-write dry-run proof;
- exactly one prepare;
- exactly one token-only commit;
- no commit retry;
- complete manifest, resolution, verification, evidence, and search gates;
- both fact searches use attributes.edge_key;
- controlled replay;
- contiguous sanitized ledger;
- zero LLM calls.

Once new canary IDs are allocated, close the TDD retry loop.

Do not edit, rebuild, reconfigure, retry, or clean up afterward.

## 14. Final report

Report:

- starting and resulting Git authority;
- RED/GREEN evidence;
- exact clean-room Ollama configuration;
- model availability;
- native /api/embed proof;
- observed dimension;
- credential_used=false;
- confirmation the embedding proxy was bypassed;
- final image ID;
- clean-room project and volumes;
- namespace fingerprint only;
- schema 0/14 → 14/14;
- capabilities provider/model/readiness;
- manifest waiver=null;
- Gate 2 embedding proof;
- prepare embedding proof;
- zero LLM calls;
- canary IDs and hashes;
- dry-run/prepare/commit counts;
- Gates 0–10;
- final classification.
