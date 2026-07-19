---
status: verified
threats_open: 0
accepted_risks: []
evaluated_head: 27c4e2e4e5000d84d18cde24a99b010831771fe7
execution_input_digest: 43d85a2b3dc74a65c9b49b5154917f4bec7dc1179cbd3bcebc5c10a7003d3e68
reviewed_worktree_digest: e1cf97bcc69650c6680598363f9fd222c2dcf0bc09be1ee16aaa6f492bc7a27b
initial_ledger_sha256: 403c575443a93738901610bc015e0bcb9b268207825f11b9b9f8b49165287ca3
audited_at: '2026-07-19T13:05:54.897366Z'
---

# Phase 5 Security Audit

## Verdict

Verified. All Phase 5 high/critical threats closed. No accepted risks.

## Threat register

| Threat | Severity | Mitigation evidence | Status |
|---|---:|---|---|
| Untrusted identifier/property injection | high | Fixed entity/edge/label/property registries; parameterized client values; malicious identifier matrix | closed |
| Implicit endpoint/community creation | high | Missing endpoints fail before write; same-batch endpoint union explicit; no generic fallback creation | closed |
| Cross-group access | high | Every catalog read/write bound by `group_id`; live tests use only `oracle-catalog-tool-test` | closed |
| Protected-group access | critical | Current AST/source scanner plus canonical safety checks show no query/mutation of `oracle-catalog-v2`; historical `a67789a` preserved separately | closed |
| Partial atomic batch writes | critical | Neo4j real transaction commit/rollback; embeddings prepared before transaction; conflict/write failures roll back | closed |
| Commit replay after uncertain transport | high | Started checkpoint precedes network; uncertain state reconciles via status/manifest reads; unknown state blocks; no prepare replay | closed |
| Lost committed receipt after interruption | high | Token-free receipt persisted immediately; `BaseException` paths persist terminal evidence; explicit interruption/write-failure/post-read tests | closed |
| Plan-token/payload/credential disclosure | high | Raw token memory-only; bounded receipts; recursive leakage tests; count/batch-only logs | closed |
| Forged/stale post-execution audit | high | Exact YAML schemas; duplicate/merge rejection; HEAD/execution/worktree/initial-ledger binding; seven-day freshness; exact scope | closed |
| Torn proof package | high | Ledger/report/Markdown staged; marker published last; marker hashes bytes; directory fsync; invalid partial package rejected; rollback tests | closed |
| Legacy MCP compatibility regression | high | Exact 14 legacy + 14 catalog + union 28 metadata/default/schema contract tests | closed |
| Unauthorized Phase 6/canary/cleanup | critical | Phase 5 runner cannot shell canary; exact hardened offline inventory; `canary_executed=false`; no `clear_graph`, deployment, deletion, or migration | closed |
| Supply-chain mutation | high | No dependency added or installed | closed |

## Two-axis safety

- Historical: `a67789a`, class `test_policy`, scope `local_neo4j_no_corresponding_data`; preserved byte-for-byte.
- Current: `oracle-catalog-v2` query/mutation false.
- Development/live group: `oracle-catalog-tool-test` only.
- Canary: not executed.
- `clear_graph`: not called.

## Accepted Risks

None.

## Verification

- Security matrix: pass.
- Focused Phase 5 suite: 380 passed.
- Live Neo4j: 62 passed.
- Ollama E2E: 5 passed.
- Ruff clean; Pyright 0 errors.
- Independent final live-tree review found no current code/security defect.
