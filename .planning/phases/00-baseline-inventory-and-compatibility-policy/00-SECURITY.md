---
phase: 0
slug: baseline-inventory-and-compatibility-policy
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-18
---

# Phase 0 — Security

> ASVS L1 verification of the threat registers authored in both Phase 0 plans. Blocking threshold: high.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Executor → local checks | Test, Ruff, and Pyright output enters baseline artifacts | Bounded paths, counts, hashes, failure IDs |
| Executor → repository canary artifacts | Historical evidence informs inventory only | Offline receipts, checkpoint, hashes, counts |
| Executor → Neo4j / MCP | Live catalog access is prohibited | No request or response permitted |
| Executor → dirty worktree | Phase commits must exclude unrelated changes | Explicit phase-file allowlist |
| Executor → remote state | Push, merge, deploy, and tag are prohibited | No remote mutation permitted |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-0-01 | Tampering | `scripts/run_catalog_canary_batch.py` | high | mitigate | Plan actions and isolation policy ban runner invocation, including dry-run; ledger and gate record `canary_executed=false`. | closed |
| T-0-02 | Tampering | `oracle-catalog-v2` | high | mitigate | Repository evidence is offline-only; ledger and gate record `oracle_catalog_v2_queried=false`; no live-group command exists in execution commits. | closed |
| T-0-03 | Tampering | Dirty worktree | high | mitigate | Explicit excluded-path list, phase-directory commit allowlist, and fail-hard unexpected-path verification; execution diff contains only planning artifacts. | closed |
| T-0-04 | Information Disclosure | Baseline and policy artifacts | medium | mitigate | Artifacts contain bounded paths, counts, hashes, and failure IDs; secret-pattern scan found no credentials, authorization headers, raw tokens, or payload dumps. | closed |
| T-0-05 | Spoofing | Check and readiness status | high | mitigate | Check statuses are restricted to `pass`, `fail`, or `skip`; recorded fail and skip remain unchanged; Phase 1 readiness requires artifacts plus safety invariants. | closed |
| T-0-06 | Elevation / Tampering | Git remote and deployment | high | mitigate | SAFE-13 policy bans push, merge, deploy, and tag; execution used local commits only. | closed |
| T-0-SC | Tampering | Package installation | low | accept | Phase 0 adds no dependency and performs no package installation; supply-chain exposure is absent. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*

---

## Accepted Risks Log

No residual risks accepted. T-0-SC is non-applicable because the phase installed no package.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-18 | 7 | 7 | 0 | GSD ASVS L1 verification |

Evidence:
- `00-baseline-checks.json` validates truthful status values and false canary/live-group flags.
- `00-PHASE0-GATE.md` records five passing safety invariants.
- Phase execution commits create planning artifacts only; no product source path changed.
- Secret-pattern scan across Phase 0 deliverables returned no matches.

---

## Sign-Off

- [x] All threats have a disposition.
- [x] No residual accepted risk requires tracking.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

**Approval:** verified 2026-07-18
