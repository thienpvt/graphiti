---
phase: 1
slug: strict-contracts-and-catalog-v2-identity
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-18
---

# Phase 1 — Security

> ASVS L1 verification of Phase 1 Plans 01-01 through 01-08. Blocking threshold: high. Closure requires executable or structural evidence; no user approval is asserted.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Client/agent → catalog Pydantic models | Untrusted request data enters strict validation | Bounded catalog-v2 fields only |
| Validated models → CatalogService/store | Invalid input must never reach side effects | Typed validated models |
| Identity inputs → UUIDv5 helpers | Caller data cannot become identity authority except through validated canonical material | Group, version, type, graph key |
| Validation/service failures → MCP/logs | Errors and logs must remain bounded and non-sensitive | Codes, paths, correlation IDs, counts, safe identifiers |
| Planning evidence → readiness | Mapping, validation, probes, and threat evidence must not produce false green | Structured rows and captured exit codes |
| Executor → Neo4j/canary/remote | Live catalog, canary, deployment, and remote mutation are prohibited | No request permitted |

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Evidence | Status |
|-----------|----------|-----------|----------|-------------|------------|----------|--------|
| T-01-01 | Tampering | Catalog request models | high | mitigate | Recursive `extra='forbid'` strict models reject unknown fields. | `mcp_server/tests/test_catalog_models.py::test_catalog_strict_model_rejects_unknown_shell_and_nested_fields` | closed |
| T-01-02 | Tampering | Immutable write flags | high | mitigate | Strict true aliases reject false and coercion for `atomic` and `strict_endpoints`. | `mcp_server/tests/test_catalog_models.py::test_strict_true_accepts_only_true_and_publishes_boolean_const_schema` | closed |
| T-01-03 | Spoofing | Identity version/system shell | high | mitigate | Required catalog-v2 version and finite FE/BO/COMMON system keys; no COMMON default. | `mcp_server/tests/test_catalog_models.py::test_identity_schema_version_required_and_rejects_non_v2`; `::test_system_key_required_closed_set` | closed |
| T-01-04 | Information Disclosure | Validation messages | medium | mitigate | Structured converter exposes bounded safe fields and excludes payload values. | `mcp_server/tests/test_catalog_models.py::test_structured_error_message_bounded_and_non_leaking` | closed |
| T-01-05 | Tampering | Silent catalog-v1 field acceptance | high | mitigate | Non-v2 identity version fails validation. | `mcp_server/tests/test_catalog_models.py::test_identity_schema_version_required_and_rejects_non_v2` | closed |
| T-01-06 | Tampering | Graph-key grammar | high | mitigate | Server-owned exact fullmatch grammar covers all 18 entity types. | `mcp_server/tests/test_catalog_models.py::test_grammar_positive_key_per_entity_type`; `::test_grammar_negative_rejects_invalid_keys` | closed |
| T-01-07 | Spoofing | System-scope mismatch | high | mitigate | Nested graph-key scope must match shell system key at exact field path. | `mcp_server/tests/test_catalog_models.py::test_graph_key_mismatch_has_exact_nested_invalid_system_key_location` | closed |
| T-01-08 | Tampering | Silent catalog-v1 graph-key acceptance | high | mitigate | Prefix-only v1 keys fail; no rewrite occurs. | `mcp_server/tests/test_catalog_models.py::test_grammar_rejects_catalog_v1_key_without_rewrite` | closed |
| T-01-09 | Elevation of Privilege | Unknown ownership to COMMON | high | mitigate | Missing keys remain missing; invalid explicit ownership fails `invalid_system_key`. | `mcp_server/tests/test_catalog_models.py::test_system_key_missing_stays_missing_and_structured_validation_error`; `::test_system_key_present_invalid_values_use_custom_error_type` | closed |
| T-01-10 | Tampering | Client key/Cypher schema | high | mitigate | Entity types remain fixed; grammar rejects unknown type/key forms before persistence. | `mcp_server/tests/test_catalog_models.py::test_entity_type_prefixes_has_eighteen_types`; `::test_entity_item_rejects_unknown_type` | closed |
| T-01-11 | Spoofing | Caller UUID | high | mitigate | Identity helpers have no caller UUID authority parameter. | `mcp_server/tests/test_catalog_identity.py::test_identity_functions_do_not_accept_caller_uuid_authority` | closed |
| T-01-12 | Tampering | FE/BO identity collision | high | mitigate | System-scoped keys and UUID material separate otherwise identical FE/BO objects. | `mcp_server/tests/test_catalog_identity.py::test_fe_bo_same_oracle_body_different_entity_uuids` | closed |
| T-01-13 | Tampering | Silent v1 UUID acceptance | high | mitigate | UUID material always includes catalog-v2; v1 material differs. | `mcp_server/tests/test_catalog_identity.py::test_v1_material_uuid_never_equals_catalog_v2` | closed |
| T-01-14 | Information Disclosure | Identity helpers | low | accept | Bounded plan-authorized residual: helpers are pure deterministic functions on a no-I/O/no-logging surface; future persistence or logging remains outside this acceptance. | `mcp_server/tests/test_catalog_identity.py::test_identity_module_has_no_io_imports`; `mcp_server/src/services/catalog_identity.py` | closed |
| T-01-15 | Information Disclosure | Structured error converter | high | mitigate | Converter emits only code, message, field path, retryability, and safe correlation ID. | `mcp_server/tests/test_catalog_models.py::test_structured_error_shape_has_safe_fields` | closed |
| T-01-16 | Tampering | Validation after side effect | high | mitigate | FastMCP typed validation and no-entry spies reject invalid requests before service/backend calls. | `mcp_server/tests/test_catalog_service.py -k 'no_side_effect or never_call or typed_pydantic or production_boundary'` | closed |
| T-01-17 | Denial of Service | Oversized error output | medium | mitigate | Client-visible validation messages remain bounded to 512 characters. | `mcp_server/tests/test_catalog_models.py::test_structured_error_message_bounded_and_non_leaking` | closed |
| T-01-18 | Information Disclosure | Catalog MCP/service logs | medium | mitigate | Both catalog product modules omit tenant group identifiers; AST and emitted-record tests cover source templates and runtime records. | `mcp_server/tests/test_catalog_service.py::test_catalog_logger_templates_omit_group_id`; `::test_catalog_resolve_logs_omit_group_id_runtime`; `::test_catalog_status_logs_omit_group_id_runtime`; `::test_catalog_wrapper_failure_logs_omit_group_id_runtime`; `mcp_server/src/graphiti_mcp_server.py`; `mcp_server/src/services/catalog_service.py` | closed |
| T-01-19 | Tampering | Phase 2 readiness false green | high | mitigate | Final runner captures all checks and derives readiness from in-memory return codes only. | `01-PHASE1-GATE.md` check ledger and Gate Contract | closed |
| T-01-20 | Tampering | Canary/live-group gate run | high | mitigate | Canary and `oracle-catalog-v2` access remain prohibited; Neo4j integration is skipped without probe. | `00-ISOLATION-POLICY.md`; `01-PHASE1-GATE.md` safety flags | closed |
| T-01-21 | Information Disclosure | Gate artifacts | medium | mitigate | Gate records argv, codes, bounded summaries, and counts only. | `01-PHASE1-GATE.md` | closed |
| T-01-22 | Tampering | Unrelated dirty-file inclusion | medium | mitigate | Task commits stage explicit planning allowlist paths only. | Git task commit diffs and worktree status checks | closed |
| T-01-23 | Tampering | Edge-probe silent drop | high | mitigate | All 53 dispositions are explicit; nine exact nodes collect once and pass. | `01-EDGE-PROBE.json`; `mcp_server/tests/test_catalog_edge_probe.py` | closed |
| T-01-06-01 | Tampering | Typed source references | high | mitigate | Strict typed source-ref fields, bounds, and recursive extra rejection. | `mcp_server/tests/test_catalog_models.py -k source_ref`; `mcp_server/tests/test_catalog_store_unit.py -k source_ref` | closed |
| T-01-06-02 | Tampering | Strict boolean aliases | high | mitigate | Pre-Literal strict identity check rejects coercion and false. | `mcp_server/tests/test_catalog_models.py -k strict_true` | closed |
| T-01-06-03 | Spoofing | Catalog-v2 system-key shells | high | mitigate | Every present invalid shell value emits custom invalid-system-key behavior. | `mcp_server/tests/test_catalog_models.py -k invalid_system_key` | closed |
| T-01-06-04 | Repudiation | Nested mismatch diagnostics | medium | mitigate | Request-relative child locations identify exact mismatches. | `mcp_server/tests/test_catalog_models.py -k graph_key_mismatch` | closed |
| T-01-06-05 | Denial of Service | Empty resolve request | medium | mitigate | Required nonempty bounded entity list rejects before service entry. | `mcp_server/tests/test_catalog_models.py mcp_server/tests/test_catalog_service.py -k empty_resolve` | closed |
| T-01-06-06 | Tampering | Stale readiness | high | mitigate | Readiness remained false through gap work and is regenerated only by Plan 01-08. | `01-VALIDATION.md`; Plan 01-06/01-07 summaries | closed |
| T-01-07-01 | Information Disclosure | Catalog MCP wrapper logs | medium | mitigate | Wrapper failures exclude tenant group values. | `mcp_server/tests/test_catalog_service.py::test_catalog_wrapper_failure_logs_omit_group_id_runtime` | closed |
| T-01-07-02 | Information Disclosure | CatalogService logs | medium | mitigate | Catalog service records exclude group identifiers while retaining bounded operational metadata. | `mcp_server/tests/test_catalog_service.py::test_catalog_resolve_logs_omit_group_id_runtime`; `::test_catalog_status_logs_omit_group_id_runtime` | closed |
| T-01-07-03 | Tampering | Logger sentinel scope | medium | mitigate | AST test scopes catalog calls and preserves legacy positive controls. | `mcp_server/tests/test_catalog_service.py::test_catalog_logger_templates_omit_group_id` | closed |
| T-01-07-04 | Tampering | Nine edge-probe dispositions | high | mitigate | Nine stable node IDs execute direct behavior assertions. | `mcp_server/tests/test_catalog_edge_probe.py` nine `test_edge_probe_*` nodes | closed |
| T-01-07-05 | Repudiation | Concurrent validation ordering | medium | mitigate | `asyncio.gather` tests assert independent results and stable locations/order. | `mcp_server/tests/test_catalog_edge_probe.py::test_edge_probe_cont01_model_validate_concurrency`; `::test_edge_probe_cont02_recursive_forbid_concurrency`; `::test_edge_probe_iden01_validation_concurrency` | closed |
| T-01-08-01 | Tampering | Requirements/roadmap mapping | high | mitigate | Structural parser proves 138 unique rows, exact phase equality, and remapped owners. | Plan 01-08 requirement verifier; `REQUIREMENTS.md`; `ROADMAP.md` | closed |
| T-01-08-02 | Spoofing | Current-HEAD validation rows | high | mitigate | JSON argv schema, shell-wrapper ban, and direct `shell=False` execution replace inversion wrappers. | `01-VALIDATION.md`; final `validation_rows` check | closed |
| T-01-08-03 | Tampering | Edge-probe evidence | high | mitigate | Collection parser and exact-node execution validate every new anchor. | `01-EDGE-PROBE.json`; final `edge_probe` check | closed |
| T-01-08-04 | Repudiation | Security dispositions | medium | mitigate | Unique structured rows require valid severity/disposition, evidence, and closed status. | This ledger; final `security_ledger` check | closed |
| T-01-08-05 | Spoofing | `ready_for_phase_2` | high | mitigate | Sentinel proves nonzero propagation; all real checks aggregate fail closed. | `01-PHASE1-GATE.md` runner and Gate Contract | closed |
| T-01-08-06 | Information Disclosure | Gate/security artifacts | medium | mitigate | Bounded outputs exclude payloads, source text, credentials, and raw tokens. | `01-PHASE1-GATE.md`; this ledger | closed |
| T-01-SC | Tampering | Package installation | high | mitigate | Non-applicable: no package installation task ran and no dependency/lockfile changed. The existing lockfile environment only was used. | Task diffs; `git diff 8a55b6e -- pyproject.toml mcp_server/pyproject.toml uv.lock mcp_server/uv.lock` is empty | closed |

## Accepted Risks Log

| Threat | Residual | Bound | Evidence |
|--------|----------|-------|----------|
| T-01-14 | Pure identity-helper values exist in process memory during deterministic computation. | Accepted only for the plan-authorized no-I/O/no-logging helper surface; any future persistence, endpoint, or logging use requires its owning phase review. | Purity import test and source module |

T-01-SC is non-applicable, not a residual acceptance: no installation task ran.

## Security Audit Trail

threats_total: 41
threats_closed: 41
threats_open: 0

| Audit Date | ASVS Level | Threats Total | Closed | Open | Basis |
|------------|------------|---------------|--------|------|-------|
| 2026-07-18 | L1 | 41 | 41 | 0 | Phase 1 plans, focused tests, structural validators, final runner |

## Sign-Off

- [x] Every threat ID is unique.
- [x] Every severity is critical, high, medium, or low.
- [x] Every disposition is mitigate, accept, or transfer.
- [x] Every row has nonempty evidence and closed status.
- [x] T-01-14 residual is bounded to plan-authorized pure no-I/O/no-logging helpers.
- [x] T-01-18 closure depends on both-module source/runtime log tests.
- [x] T-01-SC is non-applicable because no install task ran.
- [x] `threats_open: 0` is evidence-backed.

**Approval:** ASVS L1 evidence verified by automated checks; no human approval claimed.
