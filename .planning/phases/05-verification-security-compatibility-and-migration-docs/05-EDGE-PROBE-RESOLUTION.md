# Phase 05 — Edge Probe Disposition Ledger (canonical 37)

Independently enumerable. Exactly **37** rows from `05-EDGE-PROBE-LEDGER.json` fallback.
Probe ID format: `{REQ}-{category}`. Silent drops: **none**.
Disposition = concrete acceptance predicate + owning plan. Wave 0 RED: plan 01. GREEN: owning plan.
Pytest config: `-c mcp_server/pytest.ini`.

| # | Probe ID | Category | Owning plan | Disposition (status → acceptance / automated) |
|---|----------|----------|-------------|-----------------------------------------------|
| 1 | IDEN-13-unclassified | unclassified | 05-03 | **covered.** Historical ACCEPT_TAB request SHA, 10/16/1 receipt, 38/85 plan marked historical-only; hardened offline artifacts under `catalog/canary-v2-requests-hardened/` use catalog-v2 identity/hash/evidence/prepare+commit and must not equal historical golden as authority. `pytest … test_catalog_canary_scripts.py -k historical_or_hardened`. |
| 2 | SAFE-03-unclassified | unclassified | 05-02 | **covered.** Deterministic catalog service+MCP wrapper AST/static scan contains none of `add_memory,add_triplet,update_entity,delete_entity_edge,delete_episode,clear_graph,build_communities` as call targets on catalog paths. `test_catalog_security_matrix.py -k prohibited_tools`. |
| 3 | SAFE-04-concurrency | concurrency | 05-02 | **covered.** Sequential/concurrent spies prove LLM/queue/commit embedding/community counts stay zero. Missing persisted endpoints return existing `missing_endpoint` semantics before embedding/transaction/status/entity/edge writes. Same-batch endpoints resolve only from the validated entity union; persisted lookup stays unawaited and only requested entities may write later. MATCH-only store lookup and call-count assertions prove zero implicit endpoint creation. `pytest … test_catalog_security_matrix.py test_catalog_store_unit.py test_catalog_service.py -k "llm_or_queue or missing_endpoint or endpoint_union or implicit_endpoint"`. |
| 4 | SAFE-06-concurrency | concurrency | 05-02 | **covered.** Concurrent conflict paths (identity/type/endpoint/provenance/manifest/hash) each return structured fail-closed codes; zero silent repair/merge/delete/rewrite spies. `test_catalog_security_matrix.py -k fail_closed` (+ existing conflict suites reasserted). |
| 5 | SAFE-07-empty | empty | 05-02 | **covered.** Empty/minimal catalog log events still omit payload/source/token/credential fields; caplog on empty-batch path has only IDs/counts/codes. `test_catalog_security_matrix.py -k log_empty`. |
| 6 | SAFE-07-encoding | encoding | 05-02 | **covered.** Log scrub compares UTF-8 string templates via AST; forbids embedding raw plan_token bytes, source text, Cypher text; equality is exact string containment ban (not normalized). `test_catalog_security_matrix.py -k log_encoding` + AST logger scan. |
| 7 | SAFE-09-empty | empty | 05-04 | **covered.** Checked-in canonical baseline contains exactly all 14 legacy public contracts and current registration contains them; catalog exact set is asserted separately as 14; union exact 28; empty baseline/registration/set fails. `pytest … test_legacy_mcp_contract_compatibility.py test_catalog_gates.py`. |
| 8 | SAFE-09-encoding | encoding | 05-04 | **covered.** Every legacy callable name, parameter name/type, required flag, default, canonical input schema, exposed output schema, and bounded response invariant compares exactly after removing only description/title/order/source-location metadata; catalog names remain separate exact Unicode equality. Same compatibility module. |
| 9 | SAFE-09-concurrency | concurrency | 05-04 | **covered.** Two independent FastMCP metadata collections canonicalize to the same 14-legacy contract map, separate 14-catalog set, and exact union 28; registration order/races cannot shrink or mutate public contracts. Same compatibility module. |
| 10 | SAFE-10-adjacency | adjacency | 05-04 | **covered.** Adjacent groups: rows for foreign `group_id` never appear in `oracle-catalog-tool-test` results; equal keys across groups remain separate. Live/unit isolation tests. |
| 11 | SAFE-10-empty | empty | 05-04 | **covered.** Empty/invalid `group_id` rejected before Cypher; no unscoped MATCH. Store/service unit. |
| 12 | SAFE-10-ordering | ordering | 05-04 | **covered.** Isolation proofs use set equality on `group_id` independent of result order. Store/live unit. |
| 13 | TEST-10-empty | empty | 05-02 | **covered.** Empty-spy baseline executes no prohibited call/query. Every Cypher builder/property preparer accepting client-facing type/attributes is inventoried; omission or an empty fixed-authority registry fails. `pytest … test_catalog_security_matrix.py test_catalog_store_unit.py -k "empty or cypher_identifier or property_allowlist"`. |
| 14 | TEST-10-encoding | encoding | 05-02 | **covered.** Cypher metacharacters in client entity type, edge type, and attribute/property keys fail before `tx.run`/`execute_query`; executor spies prove malicious bytes never enter query text. Log forbidden tokens (`plan_token=`, credential keys, payload markers) remain exact UTF-8 containment bans. `pytest … test_catalog_security_matrix.py test_catalog_store_unit.py -k "encoding or cypher_identifier or property_allowlist"`. |
| 15 | TEST-11-empty | empty | 05-04 | **covered.** Empty committed membership / empty evidence still group-scoped; control labels excluded from entity search when zero domain entities. Live suite gap tests when Neo4j available else availability-skip. |
| 16 | TEST-11-encoding | encoding | 05-04 | **covered.** Live group_id compared exact string `oracle-catalog-tool-test`; never `oracle-catalog-v2`. Fixture constant + zero outside-group write proof. |
| 17 | TEST-12-adjacency | adjacency | 05-06,05-07 | **covered.** Initial pass/fail/availability-skip classes are mutually exclusive and skip never counts as pass. Finalizer additionally requires adjacent review/Nyquist/ASVS/goal artifacts with exact accepted states before readiness. `test_catalog_phase5_gate_runner.py` plus `catalog_phase5_gate_runner.py finalize --require-audits …`. |
| 18 | TEST-12-empty | empty | 05-06,05-07 | **covered.** Empty/missing/duplicate required checks, absent skip reason, or missing/malformed audit yields false readiness and no tracking mutation. Gate unit plus finalizer failure fixtures. |
| 19 | TEST-12-ordering | ordering | 05-06,05-07 | **covered.** Initial check IDs and final artifact SHA-256 map sort deterministically; final model binds final HEAD, 17 requirement IDs, 37 probes, four audits, live/Ollama classifications, hardened manifest, compatibility baseline. `finalize` then `verify-final`. |
| 20 | TEST-12-idempotency | idempotency | 05-06,05-07 | **covered.** Re-running initial gate on identical inputs preserves false readiness; rerunning finalizer on identical final inputs yields the same canonical content proof without changing safety/history/attempt facts or manufacturing passes. Gate self-tests. |
| 21 | TEST-12-concurrency | concurrency | 05-06,05-07 | **covered.** Ledger + JSON report + Markdown report derive from one model, write temp+fsync+validate+replace as a coherent set, reread after replacement, and leave prior coherent artifacts/tracking untouched on failure. Finalizer atomic-set tests. |
| 22 | DOCS-01-adjacency | adjacency | 05-05 | **covered.** Operator inventory lists legacy and catalog as adjacent disjoint sets totaling 28; prepare/commit marked preferred without removing compatibility tools. Structural doc check. |
| 23 | DOCS-01-empty | empty | 05-05 | **covered.** Inventory table non-empty; missing tool name fails structural check. `catalog_phase5_gate_runner.py check-docs`. |
| 24 | DOCS-01-ordering | ordering | 05-05 | **covered.** Inventory may be any order; gate verifies set membership not sequence. Doc structural set check. |
| 25 | DOCS-02-adjacency | adjacency | 05-05 | **covered.** FE/BO identical Oracle names documented as distinct graph keys in one group (no merge). Operator reference grammar section. |
| 26 | DOCS-02-empty | empty | 05-05 | **covered.** Empty system_key / missing grammar rows forbidden; docs state fail-closed invalid_system_key. Structural phrases. |
| 27 | DOCS-02-ordering | ordering | 05-05 | **covered.** Endpoint map documented as finite server-owned pairs; order irrelevant, completeness required. Doc section present. |
| 28 | DOCS-02-concurrency | concurrency | 05-05 | **covered.** Docs state single endpoint-map authority shared by upsert/prepare/verify/resolve (no concurrent divergent maps). Phrase check. |
| 29 | DOCS-03-unclassified | unclassified | 05-05 | **covered.** Hash coverage/exclusions, capabilities fields, prepare/commit/discard lifecycle, TTL/payload limits, evidence examples, manifest semantics, read/write gates all present. `check-docs`. |
| 30 | DOCS-04-adjacency | adjacency | 05-05 | **covered.** Error code list matches CatalogErrorCode adjacency (no silent drop/add of CONT-08 codes). Structural enum-vs-doc check. |
| 31 | DOCS-04-empty | empty | 05-05 | **covered.** Error/config sections non-empty; no blank secret placeholders with real values. Doc check. |
| 32 | DOCS-04-ordering | ordering | 05-05 | **covered.** Error codes compared as set equality to enum; order free. Doc check. |
| 33 | DOCS-05-unclassified | unclassified | 05-05 | **covered.** Migration guide states v1 keys/hashes obsolete, no automatic migration, offline regenerate under prepare/commit, old ACCEPT_TAB SHA not reused, two-axis safety. `check-migration`. |
| 34 | DOCS-06-unclassified | unclassified | 05-03 | **covered.** Manifest inventories builder, token-aware runner, synthetic fixture, every hardened payload, simulated prepare/commit receipts, hardened checkpoint, historical artifacts, and offline tests. Strict schema/version/cross-digest checks; historical bytes and exact checkpoint attempt count unchanged; hardened attempt count zero; recursive leakage scan bans production source content, secrets, auth headers, raw tokens, payload bodies, and full transport responses. Runner import tests prove prepare/token-only-commit/post-read sequence and zero network/DB/MCP/LLM/queue/embed; static audit proves no Phase 5 command shells it. Full `test_catalog_canary_scripts.py`. |
| 35 | REPT-01-adjacency | adjacency | 05-06,05-07 | **covered.** Initial report binds execution checks, historical/current safety, tools/contracts, migration, risks, pending named audits while remaining incomplete. Final report adds exact audit/live/Ollama classifications, final HEAD/digests, 17/17 requirements, and 37/37 probes without collapsing axes. Report schema/finalizer tests. |
| 36 | REPT-01-empty | empty | 05-06,05-07 | **covered.** Empty blockers/skips may be represented, but empty/missing required proofs, audit fields, availability reasons, requirement IDs, or probe dispositions force false readiness and leave tracking untouched. Report/gate/finalizer unit tests. |
| 37 | REPT-01-ordering | ordering | 05-06,05-07 | **covered.** Initial report has stable schema and pending audit slots. Final ledger and both reports derive from one canonical sorted model, share final HEAD/content digests/readiness/safety, then `verify-final` rereads before tracking edits. |

## Count proof

| Req | Categories | n |
|-----|------------|---|
| IDEN-13 | unclassified | 1 |
| SAFE-03 | unclassified | 1 |
| SAFE-04 | concurrency | 1 |
| SAFE-06 | concurrency | 1 |
| SAFE-07 | empty, encoding | 2 |
| SAFE-09 | empty, encoding, concurrency | 3 |
| SAFE-10 | adjacency, empty, ordering | 3 |
| TEST-10 | empty, encoding | 2 |
| TEST-11 | empty, encoding | 2 |
| TEST-12 | adjacency, empty, ordering, idempotency, concurrency | 5 |
| DOCS-01 | adjacency, empty, ordering | 3 |
| DOCS-02 | adjacency, empty, ordering, concurrency | 4 |
| DOCS-03 | unclassified | 1 |
| DOCS-04 | adjacency, empty, ordering | 3 |
| DOCS-05 | unclassified | 1 |
| DOCS-06 | unclassified | 1 |
| REPT-01 | adjacency, empty, ordering | 3 |
| **Total** | | **37** |

Unresolved after planning: **0**. Backstop-only rows: **0** (all have automated structural/unit/integration predicates).
Historical ledger JSON `status: unresolved` is superseded by this resolution file for plan execution.
