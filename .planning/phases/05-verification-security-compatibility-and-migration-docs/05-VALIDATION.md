---
phase: 05
slug: verification-security-compatibility-and-migration-docs
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
evaluated_head: 27c4e2e4e5000d84d18cde24a99b010831771fe7
execution_input_digest: 43d85a2b3dc74a65c9b49b5154917f4bec7dc1179cbd3bcebc5c10a7003d3e68
reviewed_worktree_digest: e1cf97bcc69650c6680598363f9fd222c2dcf0bc09be1ee16aaa6f492bc7a27b
initial_ledger_sha256: 403c575443a93738901610bc015e0bcb9b268207825f11b9b9f8b49165287ca3
audited_at: '2026-07-19T13:05:54.897366Z'
---

# Phase 05 — Validation Strategy

> Pre-canary validation contract. Every execution result is pass, fail, or availability-skip. Skip is never pass. Final readiness additionally requires named post-execution audits.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Existing pytest + pytest-asyncio through `mcp_server` uv project; stdlib gate runner |
| **Config** | `mcp_server/pytest.ini` |
| **Quick offline** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py mcp_server/tests/test_catalog_canary_scripts.py mcp_server/tests/test_catalog_canary_review_regressions.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_gates.py mcp_server/tests/test_catalog_commit_recovery.py mcp_server/tests/test_catalog_concurrency.py mcp_server/tests/test_catalog_store_unit.py mcp_server/tests/test_legacy_mcp_contract_compatibility.py -q --tb=line` |
| **Initial package** | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py run-initial` |
| **Post-audit closure** | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py finalize --require-audits --require-ready --expected-requirements 17 --expected-edge-probes 37` |
| **Final proof check** | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py verify-final --require-ready --expected-requirements 17 --expected-edge-probes 37` |
| **Offline latency** | Target <30 seconds per focused task command |

## Sampling and Safety

- After every task: run its exact `<automated>` predicate.
- After every wave: focused offline suite plus `git diff --check`.
- Live Neo4j and local Ollama checks use only `oracle-catalog-tool-test`; unavailable infrastructure records availability-skip with non-empty reason.
- Never query or mutate `oracle-catalog-v2`; never execute the canary runner; never call `clear_graph`.
- Preserve historical `a67789a` separately from current safety truth; preserve historical artifact bytes/attempt count; hardened attempts stay zero.
- 05-06 always emits `phase_5_complete=false`, `post_execution_audits_pending=true`, `ready_to_regenerate_canary=false`.
- 05-07 alone may derive final readiness after named audits exist and pass exact predicates.

## Per-Task Verification Map

| ID | Plan/Wave | Requirement | Secure behavior | Automated predicate | RED owner |
|----|-----------|-------------|-----------------|---------------------|-----------|
| 05-W0-SEC | 01/1 | SAFE-03/04/06/07, TEST-10 | Collectable RED cases cover prohibited calls, fixed Cypher identifiers/property maps, missing/same-batch endpoint no-create, conflicts, log leakage | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py mcp_server/tests/test_catalog_store_unit.py mcp_server/tests/test_catalog_service.py --collect-only -q` | 05-01 Task 1 |
| 05-W0-COMP | 01/1 | SAFE-09 | Canonical metadata/default/schema/response-invariant baseline for all 14 legacy tools; exact 14 catalog separate; union 28 | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_legacy_mcp_contract_compatibility.py --collect-only -q` | 05-01 Task 1 |
| 05-W0-CAN | 01/1 | IDEN-13, DOCS-06 | Strict hardened fixture/manifest/receipt/checkpoint, historical byte/attempt preservation, leakage, no external side effect | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_canary_scripts.py --collect-only -q` | 05-01 Task 1 |
| 05-W0-LIVE | 01/1 | SAFE-10, TEST-11 | Named live gaps collect without DB; runtime uses test group only | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_neo4j_int.py mcp_server/tests/test_catalog_commit_neo4j_int.py mcp_server/tests/test_catalog_prepare_neo4j_int.py --collect-only -q` | 05-01 Task 1 |
| 05-W0-GATE | 01/1 | TEST-12, REPT-01 | Initial/final formula, atomic ledger, audit parser, safety defaults collect RED/fail closed | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase5_gate_runner.py -q --tb=line` | 05-01 Task 2 |
| 05-SEC-ID | 02/2 | SAFE-03/04, TEST-10 | Fixed registry/allowlist authority; malicious identifiers never enter Cypher or execute; endpoint semantics cause no implicit entity/community creation | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py mcp_server/tests/test_catalog_store_unit.py mcp_server/tests/test_catalog_service.py -k "prohibited or llm_or_queue or community or embed or cypher_identifier or property_allowlist or missing_endpoint or endpoint_union or implicit_endpoint" -q --tb=line` | 05-01 Task 1 |
| 05-SEC-LOG | 02/2 | SAFE-06/07, TEST-10 | Fail-closed conflict matrix and bounded logs | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_security_matrix.py -q --tb=line` | 05-01 Task 1 |
| 05-CAN-SCHEMA | 03/2 | IDEN-13, DOCS-06 | Complete artifact inventory, strict schemas, history split, attempt preservation, recursive leakage predicates, no execution | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_canary_scripts.py -k "historical_inventory or historical_bytes_unchanged or sanitized_hardened or hardened_manifest_schema or offline_receipt_schema or offline_checkpoint_schema or no_production_content or no_external_side_effect" -q --tb=line` | 05-01 Task 1 |
| 05-CAN-RUNNER | 03/2 | DOCS-06 | Pure prepare/token-only-commit/post-read sequence; no runner shell/network/DB/MCP/LLM/queue/embed | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_canary_scripts.py -q --tb=line` | 05-01 Task 1 |
| 05-COMP-CONTRACT | 04/3 | SAFE-09/10 | Canonical 14 legacy public contracts; separate exact 14 catalog; union 28; isolation units | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_legacy_mcp_contract_compatibility.py mcp_server/tests/test_catalog_gates.py -q --tb=short` | 05-01 Task 1 |
| 05-LIVE | 04/3 | TEST-11 | Rollback/search/evidence/manifest/control-label/outside-group proofs pass or availability-skip | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_neo4j_int.py mcp_server/tests/test_catalog_commit_neo4j_int.py mcp_server/tests/test_catalog_prepare_neo4j_int.py -q --tb=line` | 05-01 Task 1 |
| 05-DOC-OP | 05/4 | DOCS-01..04 | Exact tool/error sets and operator contract; no secrets | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py check-docs` | 05-01 Task 2 |
| 05-DOC-MIG | 05/4 | DOCS-05/06 | No automatic migration/old SHA reuse; offline hardened procedure; two-axis truth | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py check-migration` | 05-01 Task 2 |
| 05-OLL | 06/5 | TEST-12, D-23 | Local Ollama E2E test group only; pass/fail/availability-skip truthful; no cleanup | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase5_gate_runner.py mcp_server/tests/test_catalog_ollama_e2e.py -q --tb=line` | 05-01 Task 1/2 |
| 05-INITIAL | 06/5 | TEST-12, REPT-01 | Initial ledger/report binds execution evidence; four audits pending; complete/ready forced false | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py run-initial` | 05-01 Task 2 |
| 05-FINALIZE | 07/6 | TEST-12, REPT-01 | Exact audit parser; mandatory pass; optional availability-skip only; final HEAD/digests; atomic coherent set | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py finalize --require-audits --require-ready --expected-requirements 17 --expected-edge-probes 37` | 05-01 Task 2; GREEN support 05-06 |
| 05-TRACK | 07/6 | TEST-12, REPT-01 | Tracking changes only after final proof reread; Phase 6 untouched | `uv run --project mcp_server python mcp_server/tests/catalog_phase5_gate_runner.py verify-final --require-ready --expected-requirements 17 --expected-edge-probes 37` | 05-01 Task 2; GREEN support 05-06 |

## Wave 0 Requirements

- [x] `mcp_server/tests/catalog_phase5_gate_runner.py` and self-tests reserve `run-initial`, `finalize --require-audits`, `verify-final`, exact audit parser, readiness formula, atomic coherent output, two-axis safety.
- [x] Security/store/service RED cases reserve malicious entity/edge/property identifiers, zero query execution, missing endpoint, same-batch endpoint union, zero implicit endpoint/community writes.
- [x] `legacy_mcp_contract_baseline.json` and compatibility RED module reserve behavior-bearing FastMCP contracts for every legacy tool plus separate exact catalog set.
- [x] Canary RED extensions reserve full historical/hardened inventory, strict schemas, digests, attempt counts, content/secret/token/full-response leakage, and external-side-effect spies.
- [x] Existing three Neo4j modules reserve only missing TEST-11 cases; no duplicate integration suite.
- [x] `test_catalog_ollama_e2e.py` reserves pytest-based local harness and availability classification.
- [x] Initial `05-GATE-RESULTS.json` is fail closed: `canary_executed=false`, `phase_5_complete=false`, `ready_to_regenerate_canary=false`.
- [x] No framework/package install.

## Initial Gate Ledger Contract

| Check ID | Classification | Effect |
|----------|----------------|--------|
| `runner_self_tests` | pass/fail | fail blocks |
| `focused_pytest` | pass/fail | fail blocks |
| `security_matrix` | pass/fail | fail blocks |
| `legacy_contract_14` | pass/fail | fail blocks |
| `catalog_registration_14` | pass/fail | fail blocks |
| `tool_union_28` | pass/fail | fail blocks |
| `cypher_identifier_authority` | pass/fail | fail blocks |
| `endpoint_no_implicit_creation` | pass/fail | fail blocks |
| `safety_no_v2_current` | pass/fail | fail blocks |
| `historical_axis_preserved` | pass/fail | fail blocks |
| `historical_artifacts_unchanged` | pass/fail | fail blocks |
| `hardened_artifacts_strict` | pass/fail | fail blocks |
| `canary_not_executed` | pass/fail | fail blocks |
| `offline_canary_pure` | pass/fail | fail blocks |
| `docs_operator_sections` | pass/fail | fail blocks |
| `docs_migration_phrases` | pass/fail | fail blocks |
| `ruff` | pass/fail/availability-skip | runnable fail blocks; skip needs availability reason |
| `pyright` | pass/fail/availability-skip | runnable fail blocks; skip needs availability reason |
| `live_neo4j_test11` | pass/fail/availability-skip | runnable fail blocks; skip needs availability reason |
| `ollama_e2e` | pass/fail/availability-skip | runnable fail blocks; skip needs availability reason |

Initial output always remains incomplete/not ready because post-execution audits are pending.

## Post-Execution Audit Contract

| Artifact | Exact accepted state | Readiness effect |
|----------|----------------------|------------------|
| `05-REVIEW.md` | `status: clean`; blocker count 0 | otherwise block |
| `05-VALIDATION.md` | `status: validated`; `nyquist_compliant: true`; 37/37 probes resolved | otherwise block |
| `05-SECURITY.md` | `status: verified`; `threats_open: 0`; no high/critical accepted threat | otherwise block |
| `05-VERIFICATION.md` | `status: passed`; `score: 5/5 must-haves verified`; `behavior_unverified: 0`; `requirements_verified: 17/17`; `gaps: []` | otherwise block |

Final readiness is the fail-closed AND of complete initial classifications, exact audit states, safety invariants, final HEAD/digest binding, coherent atomic outputs, 17 requirement IDs, and 37 probe dispositions. Missing/malformed/stale/duplicate evidence blocks. No CLI override.

## Manual-Only Verifications

None. Cleanup/deletion is intentionally absent and needs later explicit confirmation. Phase 6 remains separate.

## Validation Sign-Off

- [x] Every task has an automated predicate.
- [x] RED precedes GREEN for all new behavior.
- [x] Exactly 37 probes retain concrete automated predicates.
- [x] Same-wave plan file ownership has no overlap.
- [x] Live/Ollama skip is availability-based, reasoned, never pass.
- [x] `canary_executed=false`; current protected access false; historical `a67789a` preserved.
- [x] `nyquist_compliant: true` set only by post-execution validation.

**Post-execution result:** 37/37 probes resolved by runnable or structural predicates. TEST-12 and REPT-01 final dispositions remain conditional on Plan 05-07 consuming all four exact-green audits; this validation artifact is one required input, not a closure claim.

**Approval:** validated after independent predicate audit and current exact initial gate pass.
