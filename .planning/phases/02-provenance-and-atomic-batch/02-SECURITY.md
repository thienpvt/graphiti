---
phase: 02-provenance-and-atomic-batch
audited: 2026-07-17
head: d7c56f7
asvs_level: 1
block_on: high
verdict: SECURED
threats_total: 29
threats_closed: 29
threats_open: 0
---

# Phase 02: Security Audit

## Verdict

**SECURED** — all 29 authored threat entries closed. Twenty-three mitigated; six accepted low-risk supply-chain checks. No unregistered flags.

## Closed Threats

| Plan | Threats | Result | Evidence |
|---|---|---|---|
| 02-01 | T-02-01..04, T-02-SC | Closed | Server UUIDv5 identity; allowlisted/protected input; bounded status response; validated `group_id`; no dependencies added |
| 02-02 | T-02-10..14, T-02-SC | Closed | Fixed parameterized Cypher; deterministic source identity; complete target preflight; metadata-only logs; group-scoped links; no dependencies added |
| 02-03 | T-02-20..22, T-02-SC | Closed | Explicit bounded status properties; composite group-scoped reads; non-`Entity` status label; no dependencies added |
| 02-04 | T-02-30..34, T-02-SC | Closed | One atomic transaction; MATCH-only endpoint resolution; authoritative canonical hash; exception-type-only failure summary; generated-link product bound; no dependencies added |
| 02-05 | T-02-40..42, T-02-SC | Closed | Sole write group `oracle-catalog-tool-test`; exact element-ID teardown; sanitized fixture; no dependencies added |
| 02-06 | T-02-50..52, T-02-SC | Closed | Synthetic credential-free examples; canary recommendation only; exact unskipped gate evidence; no dependencies added |

## Remediation-Sensitive Evidence

- T-02-12: provenance resolves every target before its single write transaction.
- T-02-30: batch claim, entities, edges, provenance, and committed state share one transaction; failure rolls back before isolated failed-status persistence.
- T-02-31: persisted endpoints are MATCH-only; same-request entities form the sole endpoint union.
- T-02-32: optional caller hash is assertion-only; server canonical hash controls retry and conflict.
- T-02-40: commit `3e22f5e` removed the second write group. Current isolation probe is read-only; all integration writes target `oracle-catalog-tool-test` only.

## Final Remediation

- BLOCKER-01: transaction-local source identity/hash and MENTIONS/edge-link state checks close provenance TOCTOU drift in standalone and nested batches.
- BLOCKER-02: full-string group validation rejects trailing-newline hidden partitions and log delimiter injection.
- WARNING-01: divergent A/B/A entity and edge duplicates quarantine every occurrence before embedding or writes.
- Evidence: `02-REVIEW-FIX-3.md`.

## Verification

- Catalog units: **301 passed**.
- Required live Neo4j: **34 passed**, zero skipped.
- Combined catalog: **335 passed**.
- Existing MCP regressions: **86 passed**.
- Ruff: clean.
- Pyright: 0 errors, 0 warnings.
- Second-pass remediation: `02-REVIEW-FIX-2.md`.
- Final remediation: `02-REVIEW-FIX-3.md`.

## Operations Boundary

No deployment, production canary, `oracle-catalog-v2` write, full ingest, graph clear, existing-data deletion, registry push, or manifest mutation occurred.

**threats_open: 0**
