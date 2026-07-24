# Phase 5: Verification, Security, Compatibility, and Migration Docs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-19
**Phase:** 05-verification-security-compatibility-and-migration-docs
**Mode:** Autonomous (`--auto`) — all gray areas selected; recommended options chosen in one pass
**Areas discussed:** Phase boundary, gate truth, artifact migration, compatibility/reporting, security/logging, docs layout, Ollama/cleanup

---

## Phase Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Stop at truthful Phase 5 readiness; `canary_executed=false` | Prove readiness only; never Phase 6 / real canary | ✓ |
| Run Phase 6 / execute regenerated canary | Proceed into live canary after docs | |

**User's choice:** Stop at readiness (recommended; locked).
**Notes:** `--auto` selected recommended. Phase 6 remains separate approval after `ready_to_regenerate_canary=true`.

---

## Gate Truth Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Pass / fail / availability-skip only | Unavailable infra → skip with reason; runnable failure blocks | ✓ |
| Treat skip as pass | Count missing infra as green | |
| Require unavailable infrastructure unconditionally | Fail if live Neo4j/Ollama absent | |

**User's choice:** Pass/fail/availability-skip; readiness only when available gates pass and skips are availability-based.
**Notes:** Aligns with TEST-12 and REPT-01; mirrors Phase 0/4 ledger honesty.

---

## Protected Group and Historical Safety

| Option | Description | Selected |
|--------|-------------|----------|
| Never query/mutate `oracle-catalog-v2`; offline metadata only; two-axis historical `a67789a` retained | Test group only for live work | ✓ |
| Reuse live `oracle-catalog-v2` for validation | Query/mutate historical canary group | |
| Rewrite historical ACCEPT_TAB / `a67789a` narrative | Collapse history into current green | |

**User's choice:** Full isolation + two-axis safety (recommended; locked).
**Notes:** Historical ACCEPT_TAB SHA, 10/16/1, 38/85 invalid for hardened v2; never auto-migrate or delete graph data.

---

## Artifact Migration (Offline Hardened Regeneration)

| Option | Description | Selected |
|--------|-------------|----------|
| Pure offline hardened prepare/commit regeneration; harden runner, do not execute | No network/DB/MCP/LLM/queue/embed side effects | ✓ |
| Reuse old direct-upsert goldens as hardened-v2 authority | Keep pre-hardening SHA/receipts as current | |
| Execute runner (including dry-run) against live/MCP | Run canary path in Phase 5 | |

**User's choice:** Offline prepare/commit regeneration only; runner hardened but not executed.
**Notes:** Implements IDEN-13 / DOCS-06 without Phase 6.

---

## Compatibility and Tool Counts

| Option | Description | Selected |
|--------|-------------|----------|
| 28 tools (14 legacy + 14 catalog); prepare/commit preferred; compatibility tools remain | Roadmap “seven” protects original seven names, not a cap | ✓ |
| Cap catalog surface at seven tools | Drop prepare/commit/reads/capabilities from public surface | |
| Break legacy names/contracts for cleanup | Rename/remove legacy tools | |

**User's choice:** 28-tool preservation + prepare/commit preferred path.
**Notes:** Matches Phase 4 registration proof; SAFE-09.

---

## Security / Logging / Prohibition Matrix

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded IDs/counts/codes/durations/states only; full prohibition + fail-closed conflict tests | SAFE-03/04/06/07 + TEST-10 | ✓ |
| Allow payload/source snippets in debug logs | Richer diagnostics at cost of leakage | |
| Rely on prior phases only; no Phase 5 matrix | Skip exhaustive security suite | |

**User's choice:** Exhaustive prohibition + scrubbing + fail-closed proofs.
**Notes:** Never credentials/auth headers/raw tokens/embeddings/stack traces/raw query/unsafe exceptions.

---

## Documentation Shape

| Option | Description | Selected |
|--------|-------------|----------|
| One operator reference + explicit migration/offline-regeneration guide; full inventory/grammar/map/hash/capabilities/lifecycle/evidence/manifest/gates/errors/config; no secrets | DOCS-01..06 | ✓ |
| README-only partial seven-tool update | Leave prepare/commit and migration underspecified | |
| Many small ad-hoc notes without migration guide | Scatter content | |

**User's choice:** Operator + migration pair; comprehensive content; no secrets.
**Notes:** Exact filenames/sections = Claude discretion.

---

## Final Report and Readiness Flag

| Option | Description | Selected |
|--------|-------------|----------|
| Machine-readable fail-closed report; bind commands/results/skips/safety axes; `ready_to_regenerate_canary` only after D-02 | REPT-01 | ✓ |
| Prose-only readiness narrative | No structured ledger | |
| Set `ready_to_regenerate_canary=true` despite runnable failures | Soft-pass readiness | |

**User's choice:** Structured fail-closed report; conditional readiness flag.
**Notes:** Always `canary_executed=false`; preserve current forbidden-access false + historical `a67789a`.

---

## Local Ollama E2E and Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Run local Ollama E2E before cleanup when available; test group only; truthful skip/fail; no cleanup without confirmation | Standing preference | ✓ |
| Skip Ollama entirely | Never attempt local E2E | |
| Cleanup/delete without confirmation | Auto-clean milestone artifacts | |

**User's choice:** Ollama E2E when available; explicit confirmation before cleanup.
**Notes:** Never protected group; no clear_graph/existing-data deletion.

---

## Operations Ban

| Option | Description | Selected |
|--------|-------------|----------|
| No deploy/push/remote/clear_graph/existing-data deletion/non-Neo4j portability claim; preserve unrelated dirty files | SAFE-12/13 + STATE | ✓ |
| Allow push/deploy as part of readiness | Remote mutation in Phase 5 | |

**User's choice:** Full operations ban + dirty-tree preserve.
**Notes:** Parent orchestrator owns merge/commit of these discussion artifacts safely.

---

## Claude's Discretion

- Exact doc filenames and section layout
- Offline artifact schema / version suffix
- Gate ledger schema and check grouping
- Minimal helper extraction for offline regen and Phase 5 gate runner

Never discretion over safety, readiness, tool counts, historical truth, or canary/protected-group bans.

## Deferred Ideas

- Phase 6 real canary
- Automatic v1→v2 migration / graph rewrite
- Full 14k ingest
- Non-Neo4j portability
- Deferred edge types and domain product features
- Cleanup without explicit confirmation
