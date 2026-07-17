---
phase: 02-provenance-and-atomic-batch
fixed: 2026-07-17
source_review: 02-REVIEW.md
findings_addressed: 7
status: fixes_green_pending_rereview
---

# Phase 02: Code Review Remediation

## Result

All six critical findings and one warning from `02-REVIEW.md` received atomic fixes and focused regression coverage. Local catalog, live Neo4j, legacy MCP, Ruff, and Pyright gates are green. Independent adversarial re-review remains the final review gate.

## Findings

| Finding | Resolution | Commits |
|---|---|---|
| CR-01 | Optional caller batch hash is now an assertion against the server-derived canonical SHA-256. Only the server hash controls persisted idempotency. | `80e682a` |
| CR-02 | Nested provenance sources, hashes, times, targets, existing identities, and link state now complete preflight before dry-run return, embedding, schema initialization, or transaction opening. | `51f56b8` |
| CR-03 | Optional nested source hashes are checked against server-derived canonical hashes and fail with `content_hash_mismatch` before side effects. | `b98357f` |
| CR-04 | Hard and configured provenance limits now count generated links as `sources * (entity_targets + edge_targets)`; source collections are bounded. | `05f4b58` |
| CR-05 | Exact composite uniqueness constraints now cover `Entity`, `RELATES_TO`, `Episodic`, `MENTIONS`, and `CatalogIngestBatch`; post-create `SHOW CONSTRAINTS` validation fails closed. | `5a68e94` |
| CR-06 | The domain transaction now claims/rechecks batch identity under the composite constraint before domain writes. Different hashes conflict, committed retries short-circuit, failed status cannot replace committed status. Rolled-back claims can persist bounded failed status. | `ad07266`, `fc78343` |
| WR-01 | Non-atomic provenance transaction failure now marks previously attempted siblings `rolled_back`, matching Neo4j rollback semantics. | `cdb1ab6` |

Test doubles and stale caller-hash expectations were aligned with the stricter product behavior in `5dc8490`.

## Verification Evidence

| Gate | Result |
|---|---|
| Focused catalog unit suite | `268 passed in 2.05s` |
| Required live Neo4j suite | `34 passed in 23.80s`, zero skipped |
| Combined catalog suite | `302 passed in 24.46s` |
| Existing MCP regressions | `86 passed in 1.39s` |
| Ruff format | `16 files already formatted` |
| Ruff lint | `All checks passed!` |
| Scoped Pyright | `0 errors, 0 warnings, 0 informations` |
| Git whitespace check | clean |

Live tests used only `oracle-catalog-tool-test` against the local Neo4j 5.26 test container. No deployment, push, production canary, full ingest, graph clear, existing-data deletion, or `oracle-catalog-v2` mutation occurred.

## Fix Commits

```text
80e682a fix(02): CR-01 enforce authoritative batch hash
05f4b58 fix(02): CR-04 bound generated provenance links
5a68e94 fix(02): CR-05 constrain provenance and batch identities
51f56b8 fix(02): CR-02 preflight complete batch provenance
b98357f fix(02): CR-03 validate nested source hashes
ad07266 fix(02): CR-06 serialize batch status claims
cdb1ab6 fix(02): WR-01 report provenance rollback accurately
fc78343 fix(02): persist failed status after claim rollback
5dc8490 test(02): align review fix gates
```
