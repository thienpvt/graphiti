# Phase 04 — Edge Probe Disposition Ledger (canonical 42)

Independently enumerable. Exactly **42** rows. Linked from `04-06-PLAN.md` multi-source audit.

Probe ID format: `{REQ}-{category}`.
Disposition is concrete automated test intent. Wave 0 scaffolds: plan 01. GREEN: owning plan.
Pytest config for every automated disposition: `-c mcp_server/pytest.ini`.

| # | Probe ID | Requirement | Category | Owning plan | Disposition (acceptance / automated) |
|---|----------|-------------|----------|-------------|--------------------------------------|
| 1 | IDEN-08-unclassified | IDEN-08 | unclassified | 04-03 (+04-04/05 surfaces) | Full system-scoped `graph_key` on every entity-identifying field of manifest/verify/edge/evidence responses (not name-only). `pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_manifest_read.py -k graph_key` plus edge/evidence field asserts in 04-05 suites. |
| 2 | EVID-12-adjacency | EVID-12 | adjacency | 04-05 | Multi-link same target returns distinct link rows (no collapse). `test_catalog_evidence_read.py` adjacency case. |
| 3 | EVID-12-empty | EVID-12 | empty | 04-05 | Zero links → empty page, total 0, still group-scoped. `test_catalog_evidence_read.py` empty case. |
| 4 | EVID-12-ordering | EVID-12 | ordering | 04-05 | Stable ORDER BY uuid (or documented link_key) then offset/limit; repeat read same page. `test_catalog_evidence_read.py` ordering case. |
| 5 | EVID-13-unclassified | EVID-13 | unclassified | 04-04 | Exact evidence MATCH by `group_id + evidence-link uuid` from durable manifest; compare `link_key`/`content_sha256` after load; no link_key-only fallback when uuid present; missing/extra distinct (Q1 RESOLVED). `test_catalog_verify_manifest.py::test_exact_evidence`. |
| 6 | MANI-05-adjacency | MANI-05 | adjacency | 04-03 | Adjacent offset windows no silent overlap/drop for multi-member category. `test_catalog_manifest_read.py` adjacency. |
| 7 | MANI-05-empty | MANI-05 | empty | 04-03 | Empty category membership → empty page total 0; membership authority still manifest. `test_catalog_manifest_read.py` empty. |
| 8 | MANI-05-ordering | MANI-05 | ordering | 04-03 | Page order == Phase 3B canonical category order; stable across rereads. `test_catalog_manifest_read.py` ordering. |
| 9 | MANI-05-concurrency | MANI-05 | concurrency | 04-03 | Concurrent identical page reads same contents on frozen mock/store. `test_catalog_manifest_read.py` concurrency. |
| 10 | VERI-01-unclassified | VERI-01 | unclassified | 04-04 | batch_id path loads committed manifest before live match; expected set equals manifest members. `test_batch_only_uses_manifest`. |
| 11 | VERI-02-boundary | VERI-02 | boundary | 04-04 | expected count 0 legal when manifest empty categories; live rows become extras. `test_expected_not_live_count` boundary. |
| 12 | VERI-02-precision | VERI-02 | precision | 04-04 | expected ints equal manifest counts, never `len(rows)` / float. `test_expected_not_live_count` precision. |
| 13 | VERI-03-unclassified | VERI-03 | unclassified | 04-04 | missing list and extras list both populated when both conditions true. `test_missing_and_extra`. |
| 14 | VERI-04-boundary | VERI-04 | boundary | 04-04 | missing embedding vs present embedding distinct; endpoint null fails closed. `test_consistency_checks` boundary. |
| 15 | VERI-04-empty | VERI-04 | empty | 04-04 | empty evidence_links in manifest → expected evidence 0; live links report extras. `test_consistency_checks` empty. |
| 16 | VERI-04-encoding | VERI-04 | encoding | 04-04 | graph_key compared as exact full system-scoped UTF-8 strings. `test_consistency_checks` encoding. |
| 17 | VERI-04-precision | VERI-04 | precision | 04-04 | UUID string equality exact; count equality exact ints; content_sha256 hex compare with edge RETURN (Q2). `test_consistency_checks` precision. |
| 18 | VERI-04-concurrency | VERI-04 | concurrency | 04-04 | concurrent verify same batch_id same result for frozen mock; no shared mutable expected mutation. `test_consistency_checks` concurrency. |
| 19 | VERI-05-unclassified | VERI-05 | unclassified | 04-04 | missing root / incomplete chunks / digest mismatch on committed batch → `CatalogErrorCode.manifest_mismatch`; missing status is not this code (Q3). `test_missing_manifest_code`. |
| 20 | VERI-06-unclassified | VERI-06 | unclassified | 04-04 | keys-only path never uses manifest load as expected authority. `test_explicit_keys_only`. |
| 21 | RESE-01-unclassified | RESE-01 | unclassified | 04-05 | resolve_typed_edges returns uuid, endpoints+graph keys, type, content_sha256, embedding presence, anomalies (Q2 RETURN). `test_resolve_typed_edges_fields`. |
| 22 | RESE-02-concurrency | RESE-02 | concurrency | 04-05 | concurrent resolves → same anomaly set; zero repair/write spies. `test_anomalies` concurrency. |
| 23 | RESE-03-adjacency | RESE-03 | adjacency | 04-05 | cross-group edge key not returned. isolation assert in `test_catalog_resolve_edges.py`. |
| 24 | RESE-03-empty | RESE-03 | empty | 04-05 | empty refs list → empty results or request validation per model. resolve empty case. |
| 25 | RESE-03-ordering | RESE-03 | ordering | 04-05 | results order stable by request order or documented key sort. resolve ordering case. |
| 26 | GATE-01-unclassified | GATE-01 | unclassified | 04-02 | `reads_enabled` default true, write `enabled` default false; independent flags. `test_catalog_gates.py` / capabilities. |
| 27 | GATE-02-unclassified | GATE-02 | unclassified | 04-02 (+04-06) | `get_catalog_capabilities` callable with both gates false; mutation-free. capabilities + registration residual. |
| 28 | GATE-03-unclassified | GATE-03 | unclassified | 04-02 (+04-06) | six read tools usable when writes disabled (three new after 04-06 registration). `test_read_tools_when_writes_disabled` + 04-06 smoke. |
| 29 | GATE-04-unclassified | GATE-04 | unclassified | 04-02 (+04-05/06) | zero schema init / write tx / embedder / LLM / queue on read paths (spies). `test_reads_no_schema_write_embed`. |
| 30 | GATE-05-unclassified | GATE-05 | unclassified | 04-02 | missing batch status → `found=false` (not committed success; not sole status=failed+validation_error). `test_missing_status_found_false`. |
| 31 | GATE-06-adjacency | GATE-06 | adjacency | 04-02 | foreign group_id rows never appear in tool-test group results. isolation adjacency fixture. |
| 32 | GATE-06-empty | GATE-06 | empty | 04-02 | empty/invalid group_id rejected at validation; no unscoped MATCH. store/model unit. |
| 33 | GATE-06-ordering | GATE-06 | ordering | 04-02 | isolation checks use set equality on group_id independent of result order. store unit. |
| 34 | TEST-08-boundary | TEST-08 | boundary | 04-04 | shared unchanged member missing from live → missing diagnostic (not dropped from expected). verify suite. |
| 35 | TEST-08-adjacency | TEST-08 | adjacency | 04-04/05 | edge twin → duplicate_key anomaly without repair. verify + resolve suites. |
| 36 | TEST-08-empty | TEST-08 | empty | 04-04 | empty batch membership verifies clean when live empty. verify suite. |
| 37 | TEST-08-ordering | TEST-08 | ordering | 04-04 | missing/extra lists deterministic sorted by key. verify suite. |
| 38 | TEST-08-precision | TEST-08 | precision | 04-04 | count drift off-by-one detected. verify suite. |
| 39 | TEST-08-concurrency | TEST-08 | concurrency | 04-04 | two verifies no shared mutable expected mutation. verify suite. |
| 40 | TEST-09-adjacency | TEST-09 | adjacency | 04-06 | three new tools adjacent to existing catalog set; no rename of legacy 14. `test_catalog_service.py` registration. |
| 41 | TEST-09-empty | TEST-09 | empty | 04-06 | CATALOG_TOOL_NAMES exact membership size 14 (complete non-empty set). registration exact set. |
| 42 | TEST-09-ordering | TEST-09 | ordering | 04-06 | frozenset/set equality of tool names; order irrelevant. registration set equality. |

## Count proof

| Req | Categories | n |
|-----|------------|---|
| IDEN-08 | unclassified | 1 |
| EVID-12 | adjacency, empty, ordering | 3 |
| EVID-13 | unclassified | 1 |
| MANI-05 | adjacency, empty, ordering, concurrency | 4 |
| VERI-01 | unclassified | 1 |
| VERI-02 | boundary, precision | 2 |
| VERI-03 | unclassified | 1 |
| VERI-04 | boundary, empty, encoding, precision, concurrency | 5 |
| VERI-05 | unclassified | 1 |
| VERI-06 | unclassified | 1 |
| RESE-01 | unclassified | 1 |
| RESE-02 | concurrency | 1 |
| RESE-03 | adjacency, empty, ordering | 3 |
| GATE-01 | unclassified | 1 |
| GATE-02 | unclassified | 1 |
| GATE-03 | unclassified | 1 |
| GATE-04 | unclassified | 1 |
| GATE-05 | unclassified | 1 |
| GATE-06 | adjacency, empty, ordering | 3 |
| TEST-08 | boundary, adjacency, empty, ordering, precision, concurrency | 6 |
| TEST-09 | adjacency, empty, ordering | 3 |
| **Total** | | **42** |

Silent drops: none. All dispositions automated (unit/service/contract) or Wave 0 → GREEN in owning plan.
