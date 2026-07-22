# Phase 6: Catalog-v2 TDD-to-Canary Clean-Room Closure - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning
**Mode:** Autonomous infrastructure phase; fetched specification resolves all material decisions

<domain>
## Phase Boundary

Close the Phase 6 clean-room harness from the fixed `35227e0` baseline through RED/GREEN acceptance coverage, exact committed-source binding, source-bound image construction, fresh Compose authority staging, and exactly one final isolated Catalog-v2 canary. Preserve historical resources, user-owned state, secrets, catalog contracts, and the final clean-room stack. The terminal result is `PASSED` or a specification-authorized hard-stop/final-canary classification.

Existing committed work at `1031b79` already completed H1-H7 and stopped before image/runtime activity at `BLOCKED_POST_COMMIT_SOURCE_BINDING`; `090f39b` records that truthful stop. Phase 6 resumes from this evidence, fixes forward, and must not repeat completed work without cause.

</domain>

<decisions>
## Implementation Decisions

### Fixed Authority and Continuation
- `fork/v1.1:spec/new-phase.md` at `e52c1b5` is the Phase 6 authorization and acceptance authority.
- Fixed implementation baseline is commit `35227e0a2c697e643871b5c2052556988c404df6`, tree `fed171af3c49dc96701da26b53fd391511a00735`, source-context SHA-256 `dcf73073443be37b777fc7feef124133be3d9ee305696e84042d5631125ed92f`.
- Existing implementation commit `1031b7921fc1f6ca2b7f5aa20e7a02a0a2959ff8` and documentation commit `090f39bb87194c38d3806f8a75e5a52d51e13b31` are valid prior iteration history, not authority to skip remaining gates.
- Reuse the passing H1-H7 evidence. Correct the raw-Git/archive byte-binding defect with a new fix-forward commit; never amend prior candidates.

### Source, Test, and Image Gates
- Follow RED → minimal implementation → GREEN → adjacent regression → full matrix. Ordinary failures remain inside the loop.
- Exact raw-Git LF bytes are authoritative. Build and verify an exact archive without checkout/EOL transformation; membership, modes, symlinks, duplicates, collisions, hashes, and full frozen matrix must pass.
- Stage and commit task-owned source/tests/docs only. No push, merge, rebase, amend, or tag.
- Build the production image only from the exact passing archive, with commit-derived tag, exact OCI revision/context labels, no pull, no retag, no dirty context, and no secret/config/evidence inclusion.

### Clean-Room Runtime Authority
- Use only typed, fixed allow-listed launcher actions and structured subprocess argv. No shell or generic Compose passthrough.
- Preserve the legacy default project while using one explicit fresh validated project for the final runtime.
- Prove project network, containers, data volume, and log volume absent before creation; reject external/historical volumes and host database bind mounts.
- Generate exactly one UUIDv4 namespace via the canonical materializer, bind its fingerprint to project/data-volume identity, and never expose the raw value.
- Stage Neo4j only, run exactly one canonical application-owned 0/14 → 14/14 schema bootstrap, then stage MCP only without dependency recreation. Verify exact running image ID.
- Readiness calls are limited to exact tool registry, `get_status`, and zero-argument `get_catalog_capabilities`. No proactive embedding/provider probe and no generative LLM operation.

### Final Canary Boundary
- Before allocation of canary run/group/control-group/batch identity, harness/runtime defects may fix forward using new disposable candidates under the specification's proof and cleanup limits.
- Once any canary identity is allocated, freeze source, commit, image, and runtime. No edit, rebuild, new candidate, retry, reset, graph cleanup, or volume deletion.
- Execute exactly one final canary with new identities and the committed `graphiti_mcp_phase6_canary_agent_prompt_en.md` contract.
- An ambiguous commit transport permits bounded read-only reconciliation only; never retry commit.
- Authentication failure is classified exactly as `FAILED_BEFORE_COMMIT` or `FAILED_AFTER_COMMIT`; never change provider, model, endpoint, credential, response, or embedding dimension.
- Leave the final clean-room stack and volumes intact after success or failure.

### Preservation and Reporting
- Preserve `mcp_server/config/config-docker-neo4j.yaml` untouched and unstaged.
- Never run global Docker prune/removal, historical project cleanup, Kubernetes action, public OpenAI probe, deployment, or historical/live-group mutation.
- Never disclose raw namespace, proxy/API token, prepare token, credentials, full container environment, or sensitive endpoint parameters.
- Final evidence and ledgers are contiguous and sanitized; report baseline, RED/GREEN iterations, test matrix, candidate commits, exact hashes, image/runtime identities, schema transition, readiness, canary gates, and final classification.

### Claude's Discretion
- Minimal internal decomposition, test grouping, evidence filenames, and a raw-Git-exact archive implementation may follow existing project patterns, provided every fixed contract above remains exact.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/run_catalog_canary_launcher.py` already exposes staged launcher actions, validated project/image/resource authority, ordered state, and sanitization.
- `scripts/run_catalog_canary_batch.py` already carries the exact 22-field live manifest and canary ledger logic.
- `scripts/materialize_catalog_local_config.py` already owns UUIDv4 namespace materialization and fingerprint-safe output.
- `mcp_server/src/services/catalog_schema_bootstrap.py` already implements raw-driver, no-retry exact 0/14 → 14/14 bootstrap.
- `mcp_server/docker/docker-compose-neo4j.yml` plus the catalog-local override already support project-scoped resources and image selection.
- `mcp_server/tests/test_catalog_canary_scripts.py` and `test_catalog_schema_bootstrap.py` contain the H1-H7 contract coverage.
- `.planning/quick/260722-9s8-catalog-v2-phase-6-clean-room-harness-cl/` contains sanitized RED, full-matrix, binding-failure, summary, and operation evidence.

### Established Patterns
- Thin typed orchestration; fixed allowlists; structured argv; no shell interpolation.
- Raw Neo4j schema authority through application-owned `CatalogNeo4jStore` statements.
- Fail-closed exact counts/hashes/tool contracts; sanitized machine-readable receipts.
- Historical and current safety axes remain separate; prior evidence is never rewritten.
- Fix-forward candidate commits; exact committed source precedes image/runtime authority.

### Integration Points
- Replace the failing `git archive` byte-binding path with a raw-Git-exact archive/materialization path.
- Re-run the complete frozen matrix against the final candidate archive.
- Build and inspect the source-bound runtime image.
- Drive launcher R0-R3 readiness, then freeze and run the single final canary.
- Produce Phase 6 verification and final operation report without altering historical evidence.

</code_context>

<specifics>
## Specific Ideas

- Start from the existing `BLOCKED_POST_COMMIT_SOURCE_BINDING` receipt: 733/733 inventory matched; failure was EOL-transformed bytes, not missing files or harness behavior.
- Prefer Git plumbing (`ls-tree`/`cat-file` or equivalent raw-object materialization) over `git archive` when exact blob bytes are required.
- Treat successful `prepare_catalog_batch` as the first functional embedding proof.
- Preserve all existing dirty paths recorded at Phase 6 entry; task commits remain narrowly scoped.

</specifics>

<deferred>
## Deferred Ideas

- Production deployment, Kubernetes rollout, full catalog ingest, automatic catalog-v1 migration, non-Neo4j portability, historical resource cleanup, and any second canary remain out of scope.

</deferred>
