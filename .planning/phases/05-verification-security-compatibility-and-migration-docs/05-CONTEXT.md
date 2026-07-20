# Phase 5: Verification, Security, Compatibility, and Migration Docs - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Autonomous (`--auto`) — all gray areas selected; recommended options chosen in one pass
**Phase 4 product gate:** `ready_for_phase_5=true`; `manifest_verification=true`; `canary_executed=false`
**Historical 03B-06 live suite commit (preserved, never rewrite):** `a67789a04ca0cc2f2a56d7498c65be3460215f77`

<domain>
## Phase Boundary

Maintainers can prove catalog-v2 pre-canary readiness with truthful checks, isolation, security, compatibility, and migration guidance **without executing a canary**.

Phase 5 delivers:

- Exhaustive security/prohibition matrix for deterministic catalog paths (SAFE-03/04/06/07, TEST-10)
- Compatibility proof: 14 legacy + 14 catalog tools = 28 total; `group_id` isolation; Neo4j 5.26+ only (SAFE-09/10, TEST-09 foundation + TEST-12)
- Live Neo4j proofs on `oracle-catalog-tool-test` when available — atomic rollback, search interop, exact evidence/manifest, control labels excluded, zero writes outside test group (TEST-11)
- Truthful unit/service/store/MCP/concurrency/live/Ruff/Pyright gate ledger — pass/fail/availability-skip only (TEST-12)
- Operator reference + migration/offline-regeneration guide (DOCS-01..06)
- Offline hardened catalog-v2 canary artifact regeneration under prepare/commit + identity/hash/evidence/manifest contracts (IDEN-13, DOCS-06) — **no runner execution**
- Final machine-readable readiness report with `canary_executed=false` and conditional `ready_to_regenerate_canary` (REPT-01)
- Local Ollama E2E before milestone cleanup (availability-truthful; test group only)

**Hard stop:** Phase 5 ends at truthful readiness. Never Phase 6 / real canary. Never query or mutate `oracle-catalog-v2`. Never deploy/push/remote/clear_graph/existing-data deletion. Never automatic catalog-v1 migration or graph rewrite.

</domain>

<decisions>
## Implementation Decisions

### Phase Boundary and Readiness Semantics
- **D-01:** Stop after truthful Phase 5 readiness. Never enter Phase 6 or execute a real canary. Final report always sets `canary_executed=false`.
- **D-02:** `ready_to_regenerate_canary=true` only when every **available** gate passes, every skip is availability-based (not silent failure), no unexplained internal failures remain, and no blocking review/security/goal gaps remain. Any runnable required failure blocks readiness.
- **D-03:** Unavailable live Neo4j (or other optional infra) → truthful skip with reason. Do not treat skip as pass. Do not require unavailable infrastructure unconditionally.

### Isolation and Protected Groups
- **D-04:** No query or mutation of `oracle-catalog-v2`. That group may appear only in offline historical inventory or future-canary metadata (paths, digests, counts, receipts). Development and live DB tests use only `oracle-catalog-tool-test`.
- **D-05:** Preserve two-axis safety: current forbidden-access flags remain false; historical `a67789a` audit truth is retained and never rewritten. Historical ACCEPT_TAB SHA, 10/16/1 receipt, and 38/85 plan remain historical and invalid for hardened catalog-v2.
- **D-06:** No deploy, push, merge, tag, remote-state mutation, `clear_graph`, existing-data deletion, or non-Neo4j catalog portability claim.

### Compatibility and Tool Surface
- **D-07:** Preserve all 14 legacy MCP tools (names + public contracts) plus the current 14 catalog tools = **28 total**. Roadmap wording about “seven catalog names” protects the original seven names; it is **not** a cap on catalog surface. Prepare/commit is the preferred large-payload path; compatibility tools (`upsert_typed_entities`, `upsert_typed_edges`, `upsert_provenance`, `upsert_catalog_batch`, resolve/verify/status/capabilities, Phase 3A prepare/commit/discard, Phase 4 manifest/edge/evidence reads) remain registered.
- **D-08:** Catalog-v2 request contracts may break catalog-v1 payloads **explicitly**; never silently reinterpret, normalize, re-key, or rewrite catalog-v1 as catalog-v2. No automatic in-place identity migration.

### Offline Canary Artifact Migration (IDEN-13 / DOCS-06)
- **D-09:** Offline-regenerate hardened catalog-v2 canary artifacts under current identity, hash, evidence, manifest, and prepare+commit contracts. Regeneration is pure offline: no network, DB, MCP transport, LLM, queue, or embedding side effect.
- **D-10:** Harden the future runner (`scripts/run_catalog_canary_batch.py`) for prepare/commit-era contracts as needed, but **do not execute** it (including dry-run against live/MCP). Offline unit tests of builder/runner pure logic remain allowed.
- **D-11:** Historical goldens (pre-hardening ACCEPT_TAB request/catalog SHA, 10/16/1 receipt, 38/85 plan) must not be reused as hardened-v2 authority. New artifacts supersede them offline only; no graph rewrite or data deletion.

### Security, Logging, and Prohibition Matrix (SAFE-03/04/06/07, TEST-10)
- **D-12:** Deterministic catalog paths never invoke prohibited Graphiti tools: `add_memory`, `add_triplet`, `update_entity`, `delete_entity_edge`, `delete_episode`, `clear_graph`, `build_communities` (and never implicit endpoint creation or community creation).
- **D-13:** Deterministic catalog paths never invoke LLM extraction, async queue ingestion, or external embedding/LLM/queue/network on commit (prepare may embed before control-plane persist per SAFE-11 foundation).
- **D-14:** Identity, type, endpoint, provenance, manifest, uniqueness, and hash conflicts fail closed — no silent repair, merge, delete, or rewrite of graph data/constraints.
- **D-15:** Logs/metrics expose only bounded IDs, counts, structured codes, durations, and states. Never payloads, source text, credentials, auth headers, raw plan tokens, embeddings, stack traces, raw Cypher/query text, or unsafe exception bodies that may contain catalog content.
- **D-16:** Tests prove prohibition matrix on deterministic paths (spies/static/contract) and fail-closed conflict behavior.

### Documentation (DOCS-01..06)
- **D-17:** Ship **one** operator reference plus an explicit migration/offline-regeneration guide (two docs, not a sprawl). Exact filenames/section layout are Claude discretion; content is not.
- **D-18:** Operator reference covers: full tool inventory (legacy + catalog, 28 total), prepare/commit preferred large-payload path, catalog-v2 system-scoped graph-key grammar, FE/BO single-group guidance, overload handling, entity/edge registries, complete endpoint type map, hash coverage/exclusions, capabilities fields, prepare/commit/discard lifecycle, TTL/payload limits, explicit evidence examples, manifest semantics, read/write gates, every structured error code, rollout config/env vars — **no secrets**.
- **D-19:** Migration guide states: catalog-v1 keys and golden hashes obsolete; no automatic identity migration; canary artifacts must be regenerated under catalog-v2 prepare/commit; old ACCEPT_TAB SHA must not be reused; offline regeneration procedure; historical vs current safety axes.

### Gate Ledger and Final Report (TEST-12, REPT-01)
- **D-20:** Run targeted unit, service, store, MCP, concurrency, live Neo4j, Ruff, and Pyright checks when available. Each final result reports pass/fail/skip truthfully without “fixing” unrelated baseline failures by reclassification.
- **D-21:** Final machine-readable report binds check commands, results, skip reasons, historical/current safety axes, tool/compatibility facts, migration status, known limitations, and risks. Always `canary_executed=false`. Sets `ready_to_regenerate_canary=true` only under D-02.
- **D-22:** Keep current forbidden-access flags false while preserving historical `a67789a` truth (two-axis ledger pattern from Phases 3B/4).

### Local Ollama E2E Before Cleanup
- **D-23:** Run local Ollama E2E before milestone cleanup/final closure when local services are available; scope to local services and `oracle-catalog-tool-test` only — never protected group. Report skip/fail truthfully if unavailable. No cleanup/deletion without explicit human confirmation.

### Claude's Discretion
- Exact operator/migration doc filenames and section layout
- Artifact schema and version suffix for regenerated offline canary artifacts
- Gate ledger schema / check grouping / machine-readable report field layout (must still satisfy REPT-01 axes)
- Minimal helper extraction for offline regeneration and gate runners
- **Never** discretion over: safety isolation, readiness semantics, tool counts (28), historical truth, canary ban, or protected-group ban

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and Phase Contract
- `.planning/ROADMAP.md` — Phase 5 goal, success criteria, hard gates, non-goals; Phase 6 separate
- `.planning/REQUIREMENTS.md` — IDEN-13, SAFE-03, SAFE-04, SAFE-06, SAFE-07, SAFE-09, SAFE-10, TEST-10, TEST-11, TEST-12, DOCS-01..06, REPT-01
- `.planning/graphiti_mcp_pre_canary_roadmap_en.md` § Phase 5 — verification suite, security/ops limits, compatibility/migration, final pre-canary gate; exit criteria forbid canary execution
- `.planning/PROJECT.md` — core value, active milestone, out-of-scope (canary, auto migration, deploy, clear/delete)
- `.planning/STATE.md` — Phase 5 next; pending Ollama E2E before cleanup; dirty-tree preserve list

### Prior Phase Authorities
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-CONTEXT.md` — baseline inventory intent
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-ISOLATION-POLICY.md` — test group, canary ban, dirty-tree, remote ban, logging ban
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-COMPATIBILITY-POLICY.md` — 14 legacy freeze; original 7 catalog name freeze; non-silent-migration rules
- `.planning/phases/00-baseline-inventory-and-compatibility-policy/00-PHASE0-GATE.md` — early `canary_executed=false` pattern
- `.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-CONTEXT.md` — strict contracts, identity, safe errors
- `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-CONTEXT.md` — endpoint map, evidence, hashes, capabilities
- `.planning/phases/03A-immutable-prepare-commit-control-plane/03A-CONTEXT.md` — prepare/commit/discard, token, zero-external commit
- `.planning/phases/03B-atomic-catalog-exact-evidence-and-durable-manifest-writes/03B-CONTEXT.md` — atomic co-commit, manifest, evidence; two-axis safety
- `.planning/phases/04-manifest-backed-verification-and-read-only-diagnostics/04-CONTEXT.md` — read tools, split gates, 28-tool registration, Phase 5 handoff
- `.planning/phases/04-manifest-backed-verification-and-read-only-diagnostics/04-VERIFICATION.md` — Phase 4 complete; `ready_for_phase_5=true`
- `.planning/phases/04-manifest-backed-verification-and-read-only-diagnostics/04-GATE-RESULTS.json` — gate ledger shape; `canary_executed=false`
- Historical live suite commit `a67789a04ca0cc2f2a56d7498c65be3460215f77` — preserve; never rewrite

### Canary Scripts, Fixtures, Tests
- `scripts/build_catalog_canary_requests.py` — offline builder (currently pre-hardening goldens / direct-upsert shaped)
- `scripts/run_catalog_canary_batch.py` — future runner; **do not execute** in Phase 5
- `mcp_server/tests/test_catalog_canary_scripts.py` — offline builder/runner pure tests; prohibited legacy tool set
- `catalog/canary-v2-requests/` — historical payloads/receipts (invalid as hardened-v2 authority)
- `catalog/CANARY_V2_SUMMARY.md` — offline historical inventory
- `catalog/catalog.json.graphiti-canary-v2-state.json` — checkpoint; attempts must not grow from canary execution

### Product Code and Docs Surfaces
- `mcp_server/src/graphiti_mcp_server.py` — `CATALOG_TOOL_NAMES` (14 catalog) + 14 legacy = 28 `@mcp.tool`; thin wrappers
- `mcp_server/src/services/catalog_service.py` — deterministic catalog orchestration
- `mcp_server/src/services/catalog_store.py` — Neo4j store; group isolation
- `mcp_server/src/services/catalog_capabilities.py` — capabilities truth
- `mcp_server/src/services/catalog_identity.py` / hash helpers — identity and SHA authority
- `mcp_server/src/models/catalog_*.py` — request/response contracts and error codes
- `mcp_server/src/config/schema.py` — catalog config, read/write gates, namespace
- `mcp_server/README.md` — operator docs to update (still documents original seven; must expand to full inventory + prepare/commit preferred path)
- `mcp_server/tests/catalog_phase4_gate_runner.py` — prior fail-closed gate runner pattern to extend/supersede for Phase 5

### Project Instructions
- `CLAUDE.md` — Graphiti core conventions, Neo4j 5.26+, test commands
- `.claude/CLAUDE.md` — catalog extension constraints (isolation, logging, identity, no deploy/clear/delete)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 4 registration already proves **28** tools (`CATALOG_TOOL_NAMES` size 14; `@mcp.tool` count 28) and preserves legacy names — Phase 5 re-proves, does not redesign.
- Split read/write gates, manifest-backed verify, resolve/evidence reads, prepare/commit/discard, and atomic co-commit are product-complete; Phase 5 verifies and documents.
- Prior gate runners (`catalog_phase4_gate_runner.py`, Phase 0/1/2/3 ledgers) establish pass/fail/skip + two-axis safety JSON patterns for REPT-01.
- `scripts/build_catalog_canary_requests.py` + `test_catalog_canary_scripts.py` provide offline regeneration substrate; goldens and runner commit sequence still pre-hardening (direct `upsert_catalog_batch` sequence) and must be migrated offline to prepare/commit contracts.
- `PROHIBITED_LEGACY_TOOLS` in canary script tests is a seed for the broader SAFE-03/TEST-10 prohibition matrix.

### Established Patterns
- Thin FastMCP wrappers → `CatalogService` → fixed Cypher store; no client label interpolation.
- Structured errors + bounded logs (IDs/counts/codes only).
- Group isolation on every path; test group `oracle-catalog-tool-test` only.
- Control records never carry `Entity` / searchable embeddings.
- Historical vs current safety axes recorded separately; history never rewritten.

### Integration Points
- Offline builder/runner hardening under prepare/commit + catalog-v2 identity/hash/evidence/manifest — pure offline validation only.
- Security spy/static tests over deterministic catalog entrypoints (service + MCP wrappers).
- Live Neo4j suite expansion (when available) for TEST-11 isolation/rollback/search/control-label proofs.
- Operator README + new migration guide content; no secrets.
- Final Phase 5 gate runner + machine-readable report binding all checks and safety axes.
- Optional local Ollama E2E on test group before cleanup confirmation.

### Known Gaps Phase 5 Must Close
- README still centers “seven catalog tools”; must document full 28-tool inventory and prepare/commit preferred path.
- Canary builder/runner still bound to pre-hardening goldens and direct-upsert tool sequence.
- No Phase 5 final readiness report / consolidated TEST-10..12 ledger yet.
- Security prohibition matrix and log scrubbing need exhaustive Phase 5 proof, not only prior partial coverage.
- Migration guide and offline regeneration procedure do not yet exist as dedicated operator artifacts.

</code_context>

<specifics>
## Specific Ideas

- Prefer prepare/commit as the documented large-payload agent path; keep direct upsert tools for compatibility, not preference.
- Reuse Phase 4 gate-runner two-axis safety fields rather than inventing a third historical narrative.
- Offline regenerated artifacts should version/suffix distinctly so historical ACCEPT_TAB goldens remain readable as history.
- User pre-approved every recommended discussion option (`--auto`). Transient parser/internal errors may be retried only when product, security, validation, and hard-gate truth remain intact. Stop on real contract conflict.
- Preserve unrelated dirty files/worktrees (`.planning/config.json`, Docker/K8s configs, `.codegraph/`, bulk `catalog/*` dumps, `mcp_server/sample_catalog.json`, etc.).

</specifics>

<deferred>
## Deferred Ideas

- Phase 6 real canary execution / production or `oracle-catalog-v2` writes — separate explicit approval only after `ready_to_regenerate_canary=true`
- Automatic catalog-v1 → catalog-v2 identity migration, re-keying, or graph rewrite
- Full ~14k catalog ingest
- FalkorDB/Kuzu/Neptune catalog portability claims
- `LikelyReferencesTo`, `MapsTo`, `SynchronizesTo`
- Oracle/SQL/PL/SQL parsing, relationship inference, path/impact tools, delta/retirement, business-transaction entities
- Deployment, push/merge/tag, graph clear/delete without explicit confirmation
- Long-term observability dashboards beyond bounded metrics/logging required here
- Milestone cleanup/deletion — requires explicit human confirmation after Ollama E2E (or truthful skip)

</deferred>

---

*Phase: 05-verification-security-compatibility-and-migration-docs*
*Context gathered: 2026-07-19*
