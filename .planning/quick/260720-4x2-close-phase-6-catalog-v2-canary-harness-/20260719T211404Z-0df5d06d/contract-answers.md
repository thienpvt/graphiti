# Offline Contract Answers

1. Yes. The dry-run body is the exact validated live domain payload plus boolean `dry_run=true`; strict `UpsertCatalogBatchRequest` validation runs before transport.
2. Yes. Prepare uses the same domain payload with no `dry_run` or token and validates as `PrepareCatalogBatchRequest`.
3. Yes. `CatalogService.batch_request_sha256` binds the identical canonical domain body; no second request-hash algorithm was introduced.
4. Comparable dry-run fields: group ID, batch ID, valid batch UUID, identity schema, catalog SHA, request SHA, atomic/status/error fields, and projected entity/edge/source totals. Artifact SHA is prepare-only and is not invented as overlap.
5. Exact post-dry-run status and manifest reads prove absence. Status requires `found=false`, deterministic valid batch UUID, `status=failed`, `error_summary=batch status not found`, no errors/hashes/timestamps, and zero counts. Manifest requires `found=false`, `manifest_mismatch`, `manifest root not found`, exact pagination, no hashes/versions/members, and zero counts. Unexpected shapes fail.
6. Yes. The live transport guard permits one `upsert_catalog_batch` call only with explicit boolean true. Builder/runner reject false, missing at domain boundary, strings, numbers, and null before transport.
7. Protected groups are rejected before calls. Only explicit fresh canary/control IDs enter live requests. Control checks are read-only.
8. Yes. Temp golden regeneration matched all five tracked hardened files byte-for-byte; tracked files remained unchanged.
9. Yes. `control_group_id` exists only in the live run manifest and read-only isolation requests; it is absent from domain payload/provenance.
10. Yes. Checkpoints persist only exact `DRY_RUN_PASSED` binding. Post-dry-run token-bound resume is refused; process loss requires a fresh run that repeats dry-run. No plan token or token digest is persisted.

No MCP tools, Neo4j queries, prepared plans, commits, Docker/Kubernetes operations, or canary execution occurred while producing this evidence.
