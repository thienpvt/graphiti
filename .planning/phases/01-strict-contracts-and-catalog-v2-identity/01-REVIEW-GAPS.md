---
phase: 1
slug: strict-contracts-and-catalog-v2-identity
status: closed_local
findings: [CR-01, CR-02, WR-01, WR-02]
no_silent_drop: true
updated: 2026-07-18
---

# Phase 1 — Review Gap Closure Ledger

> Exactly four deep-review findings. Each maps once to Plan 01-09/01-10 evidence and current-HEAD nodes. No finding is silently dropped.

## Key Equality

```text
source_keys = {CR-01, CR-02, WR-01, WR-02}
resolved_keys = {CR-01, CR-02, WR-01, WR-02}
key_equality = true
null_dispositions = 0
silent_drops = 0
```

## Findings

### CR-01 — Concurrent entity-write race under deterministic UUID

| Field | Value |
|-------|-------|
| **Root cause** | Entity MERGE lacked lock-retained immutable/type arbitration; concurrent conflicting names could mutate after identity lock without typed `deterministic_uuid_conflict` |
| **Owner plan** | 01-10 |
| **RED commit** | `fd4c65f` (`test(01-10): add failing entity race and fixture coverage`) |
| **GREEN commit** | `3f3d173` (`feat(01-10): enforce locked entity conflicts and migrate fixtures`) |
| **Reset/docs** | `401d814` (plan summary metadata) |
| **Artifacts** | `mcp_server/src/services/catalog_store.py`, `mcp_server/src/services/catalog_service.py` |
| **Current-HEAD nodes** | `test_catalog_store_unit.py::test_gap_cr01_entity_upsert_cypher_lock_order_and_conflict_gating`; `::test_gap_cr01_entity_upsert_type_contract_covers_label_mismatch_cases`; `test_catalog_service.py::test_gap_cr01_write_status_from_row_error_never_falls_back_to_updated`; `::test_gap_cr01_atomic_route_race_rolls_back_typed_conflict`; `::test_gap_cr01_per_item_route_returns_exact_conflict_not_tx_failed`; `::test_gap_cr01_combined_batch_rolls_back_and_returns_typed_conflict` |
| **Live definition (unexecuted)** | `test_catalog_neo4j_int.py::test_concurrent_conflicting_entity_names_only_winner_persists` (integration-marked; never collected/run by Phase 1 gate) |
| **Status** | COVERED (unit/static/fake-race); live Neo4j remains skip/no-probe |

### CR-02 — Malformed provenance `reference_time`

| Field | Value |
|-------|-------|
| **Root cause** | Provenance accepted non-ISO / invalid calendar timestamps; malformed values lacked exact `('reference_time',)` locations and risked parser/exception leakage |
| **Owner plan** | 01-09 |
| **RED commit** | `f3843e9` (`test(01-09): add failing provenance and graph-key validation coverage`) |
| **GREEN commit** | `7f5b156` (`feat(01-09): harden provenance and graph-key validation`) |
| **Follow-up** | `02f4c99` (drop over-strict space-separator case) |
| **Reset/docs** | `291b6e1`, `b441307`, `0f5f692` |
| **Artifacts** | `mcp_server/src/models/catalog_provenance.py`, `mcp_server/src/services/catalog_service.py` |
| **Current-HEAD nodes** | `test_catalog_models.py::test_gap_cr02_reference_time_accepts_iso_forms_and_preserves_exact_input`; `::test_gap_cr02_malformed_reference_time_fails_at_exact_field_location`; `test_catalog_service.py::test_gap_cr02_fastmcp_malformed_reference_time_no_leak_no_side_effect` |
| **Status** | COVERED |

### WR-01 — Malformed graph-key field locations

| Field | Value |
|-------|-------|
| **Root cause** | Grammar failures surfaced at parent shells instead of concrete nested key paths across entity/edge/provenance/batch routes |
| **Owner plan** | 01-09 |
| **RED commit** | `f3843e9` |
| **GREEN commit** | `7f5b156` |
| **Follow-up** | `02f4c99` |
| **Artifacts** | `mcp_server/src/models/catalog_graph_key.py` (`validate_entity_graph_key_at`), `catalog_entities.py`, `catalog_edges.py`, `catalog_provenance.py` |
| **Current-HEAD nodes** | `test_catalog_models.py::test_gap_wr01_malformed_graph_key_reports_exact_field_location`; `::test_gap_wr01_valid_grammar_shell_mismatch_keeps_invalid_system_key`; `test_catalog_service.py::test_gap_wr01_fastmcp_malformed_graph_key_exact_path_no_side_effect`; `::test_gap_wr01_fastmcp_shell_mismatch_keeps_invalid_system_key` |
| **Status** | COVERED |

### WR-02 — Stale integration fixtures

| Field | Value |
|-------|-------|
| **Root cause** | Live Neo4j fixtures still carried pre-hardening catalog-v1 / non-FE shapes and mixed construction with network-capable imports |
| **Owner plan** | 01-10 |
| **RED commit** | `fd4c65f` |
| **GREEN commit** | `3f3d173` |
| **Artifacts** | `mcp_server/tests/catalog_neo4j_fixtures.py`, `mcp_server/tests/test_catalog_neo4j_fixtures.py`, `mcp_server/tests/test_catalog_neo4j_int.py` (import-only migration; never executed), `mcp_server/tests/fixtures/accept_tab_sanitized.json` |
| **Current-HEAD nodes** | `test_catalog_neo4j_fixtures.py::test_gap_wr02_pure_helper_has_no_forbidden_imports`; `::test_gap_wr02_constructs_all_fixture_variants_offline`; `::test_gap_wr02_accept_tab_json_is_catalog_v2_fe_scoped`; `::test_gap_wr02_no_network_or_driver_activation` |
| **Status** | COVERED (offline construction); integration execution remains skip/no-probe |

## No-Silent-Drop Assertion

- Required finding set size: 4
- Documented finding set size: 4
- Missing findings: none
- Extra findings: none
- `key_equality=true`

## Readiness Note

Local readiness remains false until Plan 01-11 runner verifies a complete green ledger. Independent code/goal/Nyquist/security audits remain pending and are never claimed here.
