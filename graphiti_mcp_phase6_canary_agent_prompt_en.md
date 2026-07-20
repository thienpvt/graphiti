# Graphiti MCP Phase 6 Catalog-v2 Canary Operator Prompt

## Boundary

Operational proof only. No coding, configuration changes, deployment, direct Neo4j, cleanup, deletion, or protected-group access during a run. Source digests are host-calculated only. Standalone `docker run` (including `--rm`), image build/pull/push, container exec/restart/recreate, unapproved Compose services, and source digest calculation inside a container are forbidden. Schema bootstrap is a separate maintenance operation and must never run inside canary. The blocked run `20260719T200946Z-1c7f70b1` and all earlier evidence are immutable. Allocate a new run ID.

Protected IDs: `oracle-core`, `oracle-catalog-v2`, `oracle-catalog-tool-test`, `main`; trim/casefold equivalents also forbidden. Never call `clear_graph`, `delete_*`, `add_memory`, direct typed upserts, `upsert_provenance`, or direct Neo4j.

Canonical full payload persistence is allowed only as the builder-generated `accept-tab.payload.json` inside the immutable artifact directory. Never copy it into logs, receipts, reports, or evidence. Never persist credentials, URLs, UUID namespace, `plan_token`, token digest, embeddings, raw source text, or exception text.

## Gate 0: reviewed source attestation before transport

Before opening MCP transport, require:

- operator-confirmed committed HEAD;
- reviewed canonical LF-normalized source-map digest over runner, builder, this prompt, approved fixture, Phase 5 proof marker;
- reviewed LF-normalized runner digest;
- no relevant-path dirtiness;
- optional image/config fingerprints only when supplied, each lowercase SHA-256;
- exact approved fixture path and pinned LF-normalized digest;
- new immutable result directory outside artifact, golden, historical, blocked-run, and evidence roots.

Any mismatch is `BLOCKED` with zero transport calls. A changed/uncommitted harness requires review plus authorized commit; never bypass Gate 0.

## Gates 1-10

1. **Capabilities:** exact 28-tool registry; `get_status`; strict full `get_catalog_capabilities`. Require Neo4j, connectivity/read/write/index readiness, catalog-v2 identity/schema versions, safe 16-lowercase-hex namespace fingerprint, prepare/manifest/verification features. Default embedding policy requires `ready`. Optional live-manifest policy `allow_unknown_embedding_provider=openai` accepts only observed provider exactly `openai` plus observed readiness exactly `unknown`; never mutate response or report it as ready. Hash raw capability response before validation. Bind fingerprint and policy; never expose raw namespace. Successful prepare is functional embedding proof; any embedding failure stops before commit without retry or fallback.
2. **Fresh isolation:** exact status and paginated manifest absence for canary and empty control. Bind deterministic batch UUID. Search both groups; require no nodes/facts.
3. **Artifact:** exact payload/manifest directory, filenames, field set, hashes, schema/system, naming relationships, approved fixture, builder authority. Reject reused/blocked/protected paths.
4. **Dry-run:** exactly one `upsert_catalog_batch` with model-valid body and boolean `dry_run=true`. Require exact ordered item identities/UUID/content hashes/status/errors; exact created/updated/unchanged split; same batch UUID. Repeat status/manifest absence.
5. **Prepare:** same canonical domain body, no `dry_run`. Keep token only in RAM. Require dry-run-equivalent hashes, counts, exact created/updated/unchanged split. Repeat absence and batch UUID continuity. Process-loss resume after prepare is unsupported.
6. **Commit:** persist sanitized `commit-started` marker before transport. Commit envelope contains only token and optional expected request hash. Require exact plan/artifact/request/catalog/batch UUID/count/created-updated-unchanged binding.
7. **Ambiguity:** timeout, cancellation, transport error, malformed, or contradictory commit response triggers exactly one read-only reconciliation: one committed-status read, then complete bounded paginated manifest only when status is exactly committed. Never retry prepare/commit or mint replacement identity. Unproven outcome is durable `FAILED_AFTER_COMMIT`.
8. **Manifest/resolution/verification/evidence:** reconstruct every manifest page with advertised page size capped at 500; recompute manifest SHA. Resolve all entities then all edges. Require exact order, labels/types, UUIDs, endpoints, hashes, embeddings, no duplicate UUID/identity/anomaly/error. Build strict verify shell with identity schema, system, group, batch, and resolved endpoint UUIDs. Retrieve paginated evidence for every entity and edge, including zero-link targets; reconcile source/target/link identity/hash/metadata; excerpts disabled and null.
9. **Search/control:** search every entity/type and edge/type under only canary group. Fact identity is canonical only at `facts[].attributes.edge_key`; require dictionary attributes, exact manifest UUID once, exact group/type/source/target endpoints, reject conflicting top-level/nested identity, foreign rows, duplicates, and aliases. Re-run control status, manifest, node search, fact search absence after commit.
10. **Replay/finalization:** runtime currently does not advertise `same_token_replay`; record `skipped`. If advertised unexpectedly, fail closed. Atomically persist sanitized `final-report.json` and actual `tool-ledger.json` on every terminal path. Never clean up.

Strict catalog tools use exactly one FastMCP `{"request": body}` shell. Search/status tools retain their actual signatures. Builders must validate `VerifyCatalogBatchRequest`, `ResolveTypedEntitiesRequest`, and `ResolveTypedEdgesRequest` before transport. Forbidden legacy request fields include `graph_keys`, `expected_source_graph_key`, and `expected_target_graph_key`.

## Terminal classifications

- `PASSED`: all gates and durable committed state proven.
- `BLOCKED`: prerequisite/authorization/source/capability/isolation/artifact failure before dry-run transport.
- `FAILED_BEFORE_COMMIT`: dry-run or prepare path failed before commit transport began.
- `FAILED_AFTER_COMMIT`: commit transport began; durable exact outcome not fully proven.

Reports use current runner schema, Gates 0-10, sanitized identities/hashes/counts/flags, raw capability hash, exact observed embedding value/waiver/proof, ledger digest/call count/final ordinal, replay state, error code/type only. Ledger ordinals must be unique, contiguous, monotonic, and consistent with call count. Never report secrets, payloads, responses, transport URL, or exception text.
