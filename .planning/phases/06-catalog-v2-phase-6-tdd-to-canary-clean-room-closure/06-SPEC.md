# Phase 6: Native Ollama Clean-Room Remediation and Final Canary — Specification

**Updated:** 2026-07-23
**Authority:** `fork/v1.1:spec/new-phase.md` at `ab5fdeb70ce18df64b03c28190ee6ad5ab6803db`
**Authorization:** `ITERATIVE_TDD_NATIVE_OLLAMA_REMEDIATION_AND_ONE_NEW_FINAL_CANARY`
**Requirements:** 13 locked

## Goal

Remediate the failed OpenAI-proxy embedding path through RED/GREEN TDD, bind the corrected native-Ollama source and image, stage an entirely new clean-room runtime, then execute exactly one new final Catalog-v2 canary without mutating the prior failed run or making any post-allocation edit, retry, rebuild, reconfiguration, or cleanup.

## Historical Terminal Boundary

The prior operation is immutable historical evidence:

- Classification: `FAILED_BEFORE_COMMIT`
- Run: `20260723t065038z-8b0d3621`
- Project: `graphiti-phase6-cleanroom-1f529136`
- Namespace fingerprint: `5d54f7f83eb90194`
- Prepare calls: 0
- Commit calls: 0
- Persistent writes: 0

Do not resume, retry, query, clean up, delete, or reclassify that run. Existing `06-CANARY-LEDGER.json`, `06-FINAL-REPORT.md`, and `06-R0`–`06-R3` receipts remain read-only historical evidence.

## Locked Requirements

1. **P6-OLL-AUTH-01 — Reviewed source and immutable history**
   - Operate on branch `v1.1` from reviewed HEAD `ab5fdeb70ce18df64b03c28190ee6ad5ab6803db` or a later explicitly reviewed fix-forward HEAD.
   - The only advance from expected starting HEAD `50d618453f0e6f50b0292a40c1fad9aa72914d87` at operation entry is the reviewed specification commit.
   - Never target the prior run, project, groups, namespace, containers, network, or volumes.

2. **P6-OLL-CONF-01 — Exact clean-room configuration**
   - The committed clean-room example and generated config use provider `ollama`, model `qwen3-embedding:0.6b`, dimensions `1024`, native container URL default `http://host.docker.internal:11434`, null/absent API key, `truncate=true`, and timeout `60` unless an already-reviewed local override exists.
   - `OLLAMA_EMBEDDER_API_URL` owns URL expansion. OpenAI embedder variables are absent from this path.
   - Materialization changes only the single Catalog UUID namespace token; the protected working file `mcp_server/config/config-docker-neo4j.yaml` remains untouched and unstaged.

3. **P6-OLL-EMB-01 — Native embedder and dimension authority**
   - `EmbedderFactory` creates existing `OllamaEmbedder`, never `OpenAIEmbedder`, with no API key requirement.
   - Requests use native `/api/embed`, exact model, `dimensions=1024`, and no `/v1`, proxy, public provider, or authorization header.
   - Responses require exactly one finite 1024-element vector per input; mismatch fails before graph writes.
   - Catalog prepare/commit invokes no LLM method.

4. **P6-OLL-CAPA-01 — Readiness and waiver policy**
   - `/api/tags` containing the exact model yields `embeddings.ready=ready`; missing model or unreachable Ollama yields `error`.
   - Capability output and logs never expose the raw endpoint.
   - Ollama `unknown` receives no waiver. The exact 22-field manifest retains `allow_unknown_embedding_provider=null`.

5. **P6-OLL-LAUNCH-01 — Freeze-bound conditional launcher**
   - Freeze authority binds provider `ollama`, model `qwen3-embedding:0.6b`, dimensions `1024`, expected readiness `ready`, null waiver, and the reviewed endpoint/config authority.
   - Builder and runner argv are derived conditionally; this Ollama operation receives no `--allow-unknown-embedding-provider` argument.
   - Provider, model, dimension, readiness, waiver, endpoint, config, image, or Git drift fails before identity allocation.

6. **P6-OLL-PREFLIGHT-01 — Sanitized local Ollama proof**
   - Confirm daemon reachability, GET `/api/tags`, and exact model presence before image/runtime work.
   - If absent, only one `ollama pull qwen3-embedding:0.6b` is authorized; no other model pull or deletion is allowed.
   - Run one harmless native embedding probe with no credential/proxy/LLM; retain only success, model presence, observed dimension `1024`, and `credential_used=false`, never vector values.

7. **P6-OLL-TDD-01 — Complete RED/GREEN matrix**
   - Stages A–D begin with intentional RED tests, then minimal GREEN changes and adjacent regressions.
   - Run changed-file compilation, native embedder/factory/config/materializer/capability/launcher/builder/runner/schema suites, Phase 5, Phase 6, combined remediation, relevant union, exact goldens, exact 22-field manifest, exact 28-tool registry, Ruff, format, Pyright, and required real local Ollama E2E.
   - No skip, deselection, suppression, weakening, or broad mock bypass.

8. **P6-OLL-BIND-01 — Fix-forward source binding**
   - Commit only task-owned source, tests, docs, and sanitized evidence.
   - Materialize a raw-Git LF-exact archive and prove exact members, modes, symlinks, and blob/context hashes.
   - Rerun the complete frozen matrix from that archive. Failed candidates remain immutable and are corrected only by new commits.

9. **P6-OLL-IMG-01 — New source-bound image**
   - Build a new commit-derived Ollama runtime image only from the passing archive; the previous OpenAI-path image is historical only.
   - Bind exact OCI revision and source-context labels. Do not push or retag.
   - Complete-image scanning covers filesystem, config, history, layers, and metadata and reports zero raw namespace, local config, API key, proxy token, credential, or evidence hit.

10. **P6-OLL-RT-01 — Entirely new clean-room runtime**
    - Create a new Compose project, data/log volumes, namespace, network, Neo4j container, MCP container, and later canary identities; reuse nothing from the failed project.
    - Prove absent-before-creation, one schema bootstrap `0/14` to first `14/14`, exact running image ID, exactly 28 tools, provider/model/dimensions/readiness authority, null waiver, bound namespace fingerprint, reachable native endpoint, and zero LLM calls.
    - Gate 2 `search_nodes` is the first read-only runtime embedding proof. Successful prepare is the second mandatory proof.

11. **P6-OLL-CAN-01 — Exactly one new final canary**
    - Allocate one new run/group/control/batch only after every TDD, Ollama, archive, image, runtime, freeze, and human-approval gate passes.
    - Require exact 22-field null-waiver manifest, one zero-write dry run with counts `3/2/1/5`, one prepare, one token-only commit, no commit retry, complete manifest/resolution/verification/evidence/search/control/replay gates, both fact searches by `attributes.edge_key`, contiguous sanitized ledger, and zero LLM calls.

12. **P6-OLL-SAFE-01 — Irreversible boundaries and preservation**
    - Never call prohibited Graphiti/LLM tools, touch `oracle-catalog-v2`, deploy, use Kubernetes, prune globally, clear/delete graph data, or mutate historical resources.
    - Once any new canary identity exists: no source edit, commit, rebuild, reconfiguration, alternate runtime, second canary, retry, graph cleanup, or volume deletion.
    - Leave the new final stack and volumes intact after success or failure.

13. **P6-OLL-REPT-01 — Sanitized terminal report**
    - Report reviewed Git authority, RED/GREEN evidence, exact sanitized Ollama configuration, model/probe results, dimension, `credential_used=false`, proxy bypass, image/resources/fingerprint, schema transition, capabilities, null waiver, Gate 2 and prepare proofs, zero LLM calls, canary identities/hashes/counts, Gates 0–10, and final classification.
    - Never report raw namespace, endpoint parameters, credentials, tokens, vectors, payloads, or full environments.

## Boundaries

**In scope:**
- Native Ollama clean-room config, existing factory/embedder verification, capability policy, conditional launcher, and TDD
- One sanitized local Ollama preflight and the single explicitly authorized model pull only if absent
- Fix-forward archive/image binding
- Entirely new isolated Compose runtime
- Exactly one new final canary after a new freeze approval
- Append-only `06-OLLAMA-*` evidence; prior terminal artifacts remain unchanged

**Out of scope:**
- New embedding-provider implementation
- OpenAI/proxy remediation or public-provider probing
- LLM calls, catalog extraction, full ingest, deployment, Kubernetes, migration, historical cleanup, or a second new canary
- Modification, query, retry, cleanup, deletion, or reclassification of the prior failed run

## Acceptance Criteria

- [ ] All 13 `P6-OLL-*` requirements have committed pre-allocation evidence or terminal uncommitted canary evidence as specified.
- [ ] Exact native Ollama model/dimension/readiness/null-waiver authority holds from config through runtime and runner.
- [ ] Required real local Ollama E2E, archive matrix, image scan, and new runtime gates pass.
- [ ] One new final canary reaches an allowed terminal classification without post-allocation mutation or retry.
- [ ] Old failed-canary evidence and resources remain unchanged; new final resources remain intact.

---

*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Updated authority: ab5fdeb70ce18df64b03c28190ee6ad5ab6803db*
