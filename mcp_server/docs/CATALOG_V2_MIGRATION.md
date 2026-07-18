# Catalog V2 Migration Notes

## Status

Catalog-v1 identity keys and content hashes are **obsolete**.

There is **no automatic migration**, rekey, rewrite, or in-place conversion from catalog-v1 identities to catalog-v2.

## Identity rules

- Catalog-v1 keys/hashes must not be treated as valid catalog-v2 identity authority.
- Old `ACCEPT_TAB` SHA values must **never** be reused for catalog-v2 acceptance or identity derivation.
- Server-derived UUIDv5 identity under the configured namespace remains the only identity authority for catalog-v2 writes.
- Backend scope for this path: **Neo4j 5.26+ only**. No non-Neo4j portability claim is made here.

## Historical canary materials

- Historical canary files are **read-only** and **non-authority**.
- They must not be used as source-of-truth for live identity, acceptance hashes, or write payloads.
- Hardened offline canary request path:

  `catalog/canary-v2-requests-hardened/`

## Offline regeneration

Regenerate hardened canary request payloads offline using the **builder only**.

1. Build request files offline via the catalog-v2 builder.
2. Validate offline against current contracts before any live use.
3. Do not rehydrate obsolete catalog-v1 keys/hashes into the regenerated payload set.
4. Do not reuse old `ACCEPT_TAB` SHA values.

## Future live path

When a live write path is authorized:

1. `prepare_catalog_batch`
2. token-only `commit_prepared_catalog_batch`

No other live commit sequence is authorized by this note.

## Phase 5 ban

- Phase 5 **never executes canary**.
- Current ban remains in force: do **not** query or mutate `oracle-catalog-v2`.

## Separate residual axis

Historical `a67789a` `test_policy` / `local_neo4j_no_corresponding_data` findings are a **separate residual axis**.

They are not resolved by this migration note and must not be conflated with catalog-v2 identity migration work.

## Explicit non-goals / bans

- No secrets in docs or logs
- No deployment actions
- No graph clear / delete / existing-data destruction
- No live-group writes from this note
- No non-Neo4j backend claims
- No automatic migration/rekey/rewrite tooling implied by this document
