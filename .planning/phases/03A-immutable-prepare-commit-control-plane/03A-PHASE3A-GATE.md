# Phase 3A Gate Report

## Readiness Derivation

Fail-closed authority for `ready_for_phase_3b`:

1. Local focused suites (prepare models/artifact/token/store/service/capabilities/MCP/hash) pass.
2. Scoped Ruff + configured Pyright pass.
3. Structural checks: wave0 files, 34/34 probe resolution, summaries, `features.prepare_commit=true`, control-plane methods present.
4. Safety ledger: `canary_executed=false`, `oracle_catalog_v2_queried=false`, `clear_graph_called=false`, `no_domain_write_on_prepare=true`, `no_external_call_on_commit=true`.
5. When `--require-neo4j`: live `test_catalog_prepare_neo4j_int.py` must pass (skip/fail blocks readiness).
6. D-29: `prepare_commit` true only after live immutable proof + re-test on final HEAD.

## Check Ledger

See `03A-GATE-RESULTS.json` for HEAD-bound results, digests, and per-check outcomes.

## Safety Invariants

- Test group only: `oracle-catalog-tool-test`
- Forbidden group: `oracle-catalog-v2` (never write target)
- No canary, no `clear_graph`, no deploy, no production writes
- Control labels never `Entity`; prepare creates no domain/evidence/status nodes

## Gate Contract

- Schema: `phase3a-gate-results.v1`
- Probe resolution: 34 unique `row_index` 0..33, `no_silent_drop=true`
- Runner: `mcp_server/tests/catalog_phase3a_gate_runner.py` / `run_phase3a_gate.py`
- Shell: `shell=False` argv only

## Scope Stop

local_gate_pass=false
nyquist_compliant=false
ready_for_phase_3b=false
prepare_commit=false
live_neo4j_immutable_proof=pending
live_neo4j_immutable_proof_pass=false
canary_executed=false
oracle_catalog_v2_queried=false
clear_graph_called=false
no_domain_write_on_prepare=true
no_external_call_on_commit=true
raw_edge_probe_count=34
resolution_count=34
