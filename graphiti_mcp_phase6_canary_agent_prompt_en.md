# Graphiti MCP Phase 6 Catalog-v2 Canary Operator Prompt

## Boundary

Operational proof only. No coding, configuration changes, deployment, direct Neo4j, cleanup, deletion, or protected-group access during a run. The blocked run `20260719T200946Z-1c7f70b1` and all earlier evidence are immutable. Allocate a new run ID.

Protected IDs: `oracle-core`, `oracle-catalog-v2`, `oracle-catalog-tool-test`, `main`; trim/casefold equivalents also forbidden. Never call `clear_graph`, `delete_*`, `add_memory`, direct typed upserts, `upsert_provenance`, or direct Neo4j.

Canonical full payload persistence is allowed only as the builder-generated `accept-tab.payload.json` inside the immutable artifact directory. Never copy it into logs, receipts, reports, or evidence. Never persist credentials, URLs, UUID namespace, `plan_token`, token digest, embeddings, raw source text, or exception text.

## Gate 0: reviewed source + execution authority before transport

Before opening MCP transport, require:

- operator-confirmed source HEAD plus explicit `git` or raw-archive authority mode;
- reviewed dual source-map digest over each committed HEAD Git blob: exact raw-byte SHA-256 plus canonical LF text SHA-256 for runner, builder, shared hasher, shared manifest contract, launcher, materializer, this prompt, approved fixture, Phase 5 proof marker; archive mode requires the same externally reviewed map and performs no Git lookup;
- reviewed canonical LF text runner digest from its committed HEAD Git blob; never call it raw SHA-256 or derive authority from checkout bytes;
- reviewed host execution-map digest (`--execution-map-sha256`) over raw-byte SHA-256 of exact fixed paths: base Compose `mcp_server/docker/docker-compose-neo4j.yml`, catalog-local override `mcp_server/docker/docker-compose-neo4j.catalog-local.override.yml`, and ignored generated `mcp_server/config/config-docker-neo4j.catalog-local.yaml` (missing override/base/config fails closed);
- no relevant-path dirtiness;
- optional image/config fingerprints only when supplied, each lowercase SHA-256;
- exact approved fixture path, pinned raw committed-Git-blob SHA-256, and pinned canonical LF text digest;
- new immutable result directory outside artifact, golden, historical, blocked-run, and evidence roots.

Any mismatch is `BLOCKED` with zero transport calls. CLI and direct programmatic `run_live_canary` both verify execution authority (injectable attestor cannot be omitted). A changed/uncommitted harness requires review plus authorized commit; never bypass Gate 0.

## Gates 1-10

1. **Capabilities:** exact 28-tool registry; `get_status`; strict full `get_catalog_capabilities`. Require Neo4j, connectivity/read/write/index readiness, catalog-v2 identity/schema versions, safe 16-lowercase-hex namespace fingerprint, prepare/manifest/verification features. Hash the unmodified raw server capability response (canonical SHA over the raw dict) before validation/policy; prove the raw dict is structurally unchanged after preflight; never hash a model projection and never rewrite readiness. Embedding policy: `ready` passes; `error` always fails; `unknown` fails unless CLI/live authority supplies exact `--allow-unknown-embedding-provider=openai` **and** observed `provider=openai`. Record observed provider/readiness and `waiver_applied`; never rewrite `unknown` to `ready`. Bind the fingerprint; never expose raw namespace.
2. **Fresh isolation:** exact status and paginated manifest absence for canary and empty control. Bind deterministic batch UUID. Search both groups; require no nodes/facts.
3. **Artifact:** exact payload/manifest directory, filenames, field set, hashes, schema/system, naming relationships, approved fixture, builder authority. Reject reused/blocked/protected paths.
4. **Dry-run:** exactly one `upsert_catalog_batch` with model-valid body and boolean `dry_run=true`. Require exact ordered item identities/UUID/content hashes/status/errors; exact created/updated/unchanged split; same batch UUID. Repeat status/manifest absence.
5. **Prepare:** same canonical domain body, no `dry_run`. Keep token only in RAM. Require dry-run-equivalent hashes, counts, exact created/updated/unchanged split. Repeat absence and batch UUID continuity. Successful prepare is functional embedding proof (`prepare_functional_embedding_proof=true`). Prepare embedding failure exits `FAILED_BEFORE_COMMIT` with no retry/fallback/commit. Process-loss resume after prepare is unsupported.
6. **Commit:** persist sanitized `commit-started` marker before transport. Commit envelope contains only token and optional expected request hash. Require exact plan/artifact/request/catalog/batch UUID/count/created-updated-unchanged binding.
7. **Ambiguity:** timeout, cancellation, transport error, malformed, or contradictory commit response triggers exactly one read-only reconciliation: one committed-status read, then complete bounded paginated manifest only when status is exactly committed. Never retry prepare/commit or mint replacement identity. Unproven outcome is durable `FAILED_AFTER_COMMIT`.
8. **Manifest/resolution/verification/evidence:** reconstruct every manifest page with advertised page size capped at 500; recompute manifest SHA. Resolve all entities then all edges. Require exact order, labels/types, UUIDs, endpoints, hashes, embeddings, no duplicate UUID/identity/anomaly/error. Build strict verify shell with identity schema, system, group, batch, and resolved endpoint UUIDs. Retrieve paginated evidence for every entity and edge, including zero-link targets; reconcile source/target/link identity/hash/metadata; excerpts disabled and null.
9. **Search/control:** search every entity/type and edge/type under only canary group. Gate 9 fact identity is canonical nested `facts[].attributes.edge_key` (dict attributes required). Require exact expected UUID once, exact group/type/key/source/target; unrelated same-group extras allowed; foreign group, duplicate UUID, alias/ambiguous identity, missing/non-dict attributes, and top/nested conflicts fail. Top-level-only `edge_key` does not satisfy the nested contract. Re-run control status, manifest, node search, fact search absence after commit.
10. **Replay/finalization:** runtime currently does not advertise `same_token_replay`; record `skipped`. If advertised unexpectedly, fail closed. Validate tool ledger before terminal artifacts: each entry exact keys `{ordinal,tool,stage,success,error_code}`; ordinals exact unique contiguous ints `1..N`; success requires `error_code=null`; failure requires non-empty string `error_code`. Report `tool_call_count` and `final_ordinal` must match validated ledger; `tool_count` remains registered MCP count 28. Invalid ledger rejects terminal artifacts (no inconsistent fallback write). Persist order: validated `tool-ledger.json`, then sanitized `final-report.json`, then `terminal-artifacts-manifest.json` last binding exact on-disk SHA-256 of both files plus counts/schema. Failure before the acceptance manifest leaves terminal artifacts unaccepted. Never clean up.

## Schema bootstrap (separate operator-only maintenance, never during canary)

`scripts/bootstrap_catalog_v2_schema.py` uses the official raw Neo4j async driver only — never Graphiti `Neo4jDriver`. Call order: `ensure_uuid_uniqueness_constraints` → `ensure_plan_schema` → `ensure_evidence_manifest_schema` → exactly one `inspect_catalog_v2_schema_readiness`. Require exact 14/14. Stop after first non-exact inspection; no retry/rollback/repair. Matcher accepts Neo4j `RELATIONSHIP_UNIQUENESS`.

## Execution boundary

First run `scripts/materialize_catalog_local_config.py`; it never normalizes config implicitly. Canonical operator entry is `scripts/run_catalog_canary_launcher.py`. Direct Compose is forbidden. Host-side execution authority digests only fixed paths: base `mcp_server/docker/docker-compose-neo4j.yml`, override `mcp_server/docker/docker-compose-neo4j.catalog-local.override.yml`, and ignored generated `mcp_server/config/config-docker-neo4j.catalog-local.yaml` (raw-byte SHA-256 map, canonical hash bound as `execution_map_sha256`; method recorded as `raw-byte-sha256`). Launcher owns fixed action argv, fixed Compose project identity, sanitized `COMPOSE_*` child environment, and is sole Compose subprocess owner. `up` targets only `graphiti-mcp` with `--no-deps --no-build --pull never`; `ps`/`logs` target only `graphiti-mcp`. `config` and `down` are forbidden because they can expose resolved secrets or affect Neo4j. Reject run/build/pull/exec, Neo4j targets, volume/orphan destruction, duplicate/unknown tokens, shell execution, and direct Compose bypass.

Strict catalog tools use exactly one FastMCP `{"request": body}` shell. Search/status tools retain their actual signatures. Builders must validate `VerifyCatalogBatchRequest`, `ResolveTypedEntitiesRequest`, and `ResolveTypedEdgesRequest` before transport. Forbidden legacy request fields include `graph_keys`, `expected_source_graph_key`, and `expected_target_graph_key`.

## Terminal classifications

- `PASSED`: all gates and durable committed state proven.
- `BLOCKED`: prerequisite/authorization/source/capability/isolation/artifact failure before dry-run transport.
- `FAILED_BEFORE_COMMIT`: dry-run or prepare path failed before commit transport began.
- `FAILED_AFTER_COMMIT`: commit transport began; durable exact outcome not fully proven.

Reports use `schema_version="phase6-canary-report-v1"`, Gates 0-10, sanitized identities/hashes/counts/flags, replay state, error code/type only. Never report secrets, payloads, responses, transport URL, or exception text.
