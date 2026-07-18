# Phase 4: Manifest-Backed Verification and Read-Only Diagnostics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-07-19
**Phase:** 04-manifest-backed-verification-and-read-only-diagnostics
**Mode:** Autonomous - standing approval selected every recommended option
**Areas discussed:** Manifest pagination/order, batch verify authority, explicit-key compatibility, edge/evidence diagnostics, split gates, missing status, registration/capabilities, tests/gates

---

## Manifest Pagination and Stable Ordering

| Option | Description | Selected |
|--------|-------------|----------|
| Offset/limit over durable canonical membership order | Page stable Phase 3B category sort; same params -> same page | Yes |
| Re-sort by live graph discovery / batch_id | Build pages from current domain rows | |
| Unbounded full dump only | No pagination; return entire membership always | |

**Selection:** Stable offset/limit (or equivalent cursor) over durable manifest order.
**Rationale:** MANI-05 + ROADMAP research note require pagination without lying about membership; Phase 3B already freezes order.

---

## Batch Verify Membership Authority

| Option | Description | Selected |
|--------|-------------|----------|
| Committed durable manifest is expected authority | Counts/members from manifest; live rows are observations only | Yes |
| Expected = live query result set | Set expected equal to objects returned by verify query | |
| Infer expected from entity/edge batch_id | Treat last-change metadata as membership | |

**Selection:** Manifest-backed expected membership and counts; never expected=observed.
**Rationale:** VERI-01/02 and pre-canary roadmap forbid circular verification and batch_id authority.

---

## Duplicate / Drift Reporting

| Option | Description | Selected |
|--------|-------------|----------|
| Report missing members and extra physical duplicates/drift distinctly | Fail closed; no silent normalize | Yes |
| Normalize extras away / collapse duplicates | Present only first match as success | |
| Counts-only without member identity drift | Ignore identity-level missing/extra | |

**Selection:** Distinct missing + extra/duplicate diagnostics.
**Rationale:** VERI-03/04 and TEST-08 require precise drift detection.

---

## Explicit-Key Verify Compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| Keep batch and/or explicit keys; both may combine | Explicit-key-only unchanged; batch uses manifest; combined = manifest expected + key diagnostics | Yes |
| Remove explicit-key path | Force batch_id only | |
| Explicit keys replace manifest when present | Drop manifest authority if any key supplied | |

**Selection:** Preserve VERI-06 explicit-key path alongside manifest-backed batch path.
**Rationale:** Existing `VerifyCatalogBatchRequest` contract and agent workflows depend on both scopes.

---

## Edge and Evidence Diagnostics

| Option | Description | Selected |
|--------|-------------|----------|
| Add resolve_typed_edges + get_catalog_evidence read-only | Exact typed edge resolve; compact paginated evidence; no embed/write | Yes |
| Rely on semantic search for edges/evidence | Use hybrid search tools only | |
| Defer evidence read to Phase 5 | Ship edge resolve without EVID-12 | |

**Selection:** Both tools in Phase 4; read-only, group-isolated, no repair.
**Rationale:** RESE-01..03 and EVID-12 are Phase 4 requirements; search is not exact identity authority.

---

## Split Read/Write Gates and Defaults

| Option | Description | Selected |
|--------|-------------|----------|
| Separate gates: writes default false, reads default true | Capabilities always callable; fix _read_gate write coupling | Yes |
| Single enabled flag for all catalog tools | Keep current write-coupled _read_gate | |
| Reads default false | Require explicit opt-in for diagnostics | |

**Selection:** Split gates with safe defaults (writes off, reads on).
**Rationale:** GATE-01..04; operators must verify while mutation is disabled.

---

## Missing Status Shape

| Option | Description | Selected |
|--------|-------------|----------|
| found=false / explicit not-found | Distinguish absence from committed and from operational failure | Yes |
| status=failed + validation_error only | Current get_catalog_ingest_status missing path | |
| Raise transport exception | Raw error to MCP client | |

**Selection:** found=false (or explicit not-found code/state).
**Rationale:** GATE-05; current failed/validation_error masquerade is a known gap.

---

## Registration and Capabilities

| Option | Description | Selected |
|--------|-------------|----------|
| Register new read tools; flip manifest_verification after proof; truthful read/write flags | Preserve 14 legacy + existing catalog tools; get_status compatible | Yes |
| Leave tools unregistered until Phase 5 | Capabilities claim support without tools | |
| Break get_status shape for richer gates | Replace status/message | |

**Selection:** Additive registration + truthful capability flags post-proof.
**Rationale:** TEST-09, CAPA/GATE-02, compatibility constraint.

---

## Tests and Phase Gate

| Option | Description | Selected |
|--------|-------------|----------|
| TEST-08/09 unit/service/store/registration + optional live on oracle-catalog-tool-test | Preserve a67789a; no canary/deploy/clear/delete/push; block Phase 5 on gate | Yes |
| Skip gate until Phase 5 | Mark Phase 4 complete without registration proofs | |
| Query oracle-catalog-v2 for realism | Use live catalog group | |

**Selection:** Fail-closed Phase 4 gate with isolation and historical audit preservation.
**Rationale:** ROADMAP dependency chain, TEST-08/09, standing safety constraints.

---

## Claude Discretion

- Exact Pydantic field names, cursor encoding, anomaly list shapes.
- Smallest store/service read extraction over existing manifest root/chunk loaders.
- Read-gate config field/env name with safe default.
- Additive verify response sections vs anomaly-list extension (must still meet EVID-13/VERI-03/04).

## Deferred Ideas

- Final security/compat matrix, migration/operator docs, offline canary regeneration, readiness report - Phase 5.
- Canary, `oracle-catalog-v2`, deployment, deletion, graph clear, push - separate approval / out of scope.
- Non-Neo4j portability and deferred edge types - future.

---

*Phase: 04-manifest-backed-verification-and-read-only-diagnostics*
*Discussion log date: 2026-07-19*

