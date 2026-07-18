---
phase: 03A
slug: immutable-prepare-commit-control-plane
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
---

# Phase 03A — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`mcp_server`) |
| **Config file** | `mcp_server/pytest.ini` |
| **Quick run command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_models.py mcp_server/tests/test_catalog_prepared_artifact.py mcp_server/tests/test_catalog_token.py -q --tb=line` |
| **Full focused command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_models.py mcp_server/tests/test_catalog_prepared_artifact.py mcp_server/tests/test_catalog_token.py mcp_server/tests/test_catalog_prepare_store.py mcp_server/tests/test_catalog_prepare_service.py mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_catalog_hash.py mcp_server/tests/test_catalog_service.py mcp_server/tests/test_graphiti_mcp_server.py -q --tb=line` |
| **Live Neo4j command** | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_neo4j_int.py -m integration -q --tb=line` |
| **Estimated runtime** | Quick: <30 seconds; full focused: <180 seconds; live proof: environment-dependent |

---

## Sampling Rate

- **After every task commit:** Run the task-specific test command; run the quick suite once its files exist.
- **After every plan wave:** Run the full focused suite plus scoped Ruff and Pyright.
- **Before `/gsd-verify-work`:** Full focused suite, Phase 3A gate runner, scoped Ruff, scoped Pyright, and required live Neo4j proof must be green.
- **Max unit feedback latency:** 180 seconds.
- **Hard-stop rule:** A skipped or failed live immutable-artifact proof keeps `ready_for_phase_3b=false`; never weaken payload, restart, immutability, or token-only contracts to obtain a pass.

---

## Per-Task Verification Map

Mapped to **6 plans / 12 tasks** (waves 1,1,2,3,4,5). Task IDs use `03A-NN-T0N`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03A-01-T01 | 01 | 1 | PLAN-01, PLAN-10 | T-03A-01, T-03A-04 | Strict prepare and token-only commit/discard models reject transport and replacement-payload authority recursively | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_models.py -q --tb=line -k "prepare or commit or discard"` | ✅ | green |
| 03A-01-T02 | 01 | 1 | PLAN-08 | T-03A-05 | Configured TTL, payload, chunk, and active-plan values cannot exceed immutable hard ceilings | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_models.py -q --tb=line -k "ttl or payload or chunk or active or HARD or plan_ttl"` | ✅ | green |
| 03A-02-T01 | 02 | 1 | PLAN-04, PLAN-05 | T-03A-03, T-03A-06 | Canonical bytes chunk and reassemble byte-identically; size/count/digest corruption fails closed | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepared_artifact.py -q --tb=line` | ✅ | green |
| 03A-02-T02 | 02 | 1 | PLAN-06, PLAN-07, PLAN-17 | T-03A-01, T-03A-02 | Tokens use `secrets`, domain-separated digests, `hmac.compare_digest` via plan_token_matches, binding helpers | unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_token.py -q --tb=line` | ✅ | green |
| 03A-03-T01 | 03 | 2 | PLAN-05, PLAN-09 | T-03A-03, T-03A-05 | Fixed control labels create immutable root/chunks only; capacity count and create serialize per group | store unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_store.py -q --tb=line -k "create or capacity or load or schema or label"` | ✅ | green |
| 03A-03-T02 | 03 | 2 | PLAN-11, PLAN-18, PLAN-19 | T-03A-01, T-03A-07 | CAS permits only legal state transitions; terminal plans never revive; discard idempotent only for discarded | store unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_store.py -q --tb=line -k "cas or state or discard or expired or conflict or consum"` | ✅ | green |
| 03A-04-T01 | 04 | 3 | PLAN-02, PLAN-20 | T-03A-03 | Characterize upsert then extract shared preflight; dry_run zero-write regression | service regression | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_service.py mcp_server/tests/test_catalog_hash.py -q --tb=line -k "dry_run or upsert_catalog_batch or request_sha256"` | ✅ | green |
| 03A-04-T02 | 04 | 3 | PLAN-03, PLAN-04, PLAN-06, SAFE-11 | T-03A-03, T-03A-08, T-03A-09 | Complete preflight and embeddings before plan persist; zero domain/status; one-time receipt | service spies | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_service.py -q --tb=line -k "prepare or embedding or zero_write or receipt or conflict or project"` | ✅ | green |
| 03A-05-T01 | 05 | 4 | PLAN-07, PLAN-10, PLAN-11, PLAN-12, PLAN-17, PLAN-18, PLAN-19 | T-03A-01, T-03A-02, T-03A-07, T-03A-08 | Token-only commit/discard; post-load plan_token_matches; zero domain/external; no revive | service spies | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_service.py -q --tb=line -k "commit or discard or expected_request or external or binding or revive or expired or consum or plan_token_matches or compare_digest"` | ✅ | green |
| 03A-05-T02 | 05 | 4 | PLAN-08, PLAN-20 | T-03A-04, T-03A-09 | Three additive tools; real limits; prepare_commit **false** pre-gate; manifests false; pagination 0 | MCP unit | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_capabilities.py mcp_server/tests/test_graphiti_mcp_server.py -q --tb=line -k "prepare or commit or discard or capabilit or tool or CATALOG_TOOL"` | ✅ | green |
| 03A-06-T01 | 06 | 5 | PLAN-03, PLAN-05, PLAN-09, SAFE-11 | T-03A-03, T-03A-05 | Real Neo4j round-trips configured-max immutable chunks across fresh session without Entity/domain/status contamination | live Neo4j | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_prepare_neo4j_int.py -m integration -q --tb=line` | ✅ | green |
| 03A-06-T02 | 06 | 5 | PLAN-07, PLAN-08, PLAN-11, PLAN-17, PLAN-18, PLAN-19, TEST-05 | T-03A-01..09 | Live proof then D-29 prepare_commit flip; re-test final HEAD; fail-closed ledger + 34/34 probe resolution; ready_for_phase_3b | gate + capa | `uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini mcp_server/tests/test_catalog_phase3a_gate_runner.py mcp_server/tests/test_catalog_capabilities.py -q --tb=line` then `uv run --project mcp_server python mcp_server/tests/run_phase3a_gate.py apply --require-local-pass --require-neo4j` | ✅ | green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `mcp_server/tests/test_catalog_prepare_models.py` — strict prepare/commit/discard models and limit clamps.
- [x] `mcp_server/tests/test_catalog_prepared_artifact.py` — canonical serialization, bounded chunking, byte-identical reassembly, corruption rejection.
- [x] `mcp_server/tests/test_catalog_token.py` — entropy, domain-separated digest, timing-safe comparison, binding.
- [x] `mcp_server/tests/test_catalog_prepare_store.py` — immutable create/load, group capacity lock, state CAS matrix.
- [x] `mcp_server/tests/test_catalog_prepare_service.py` — preflight, projections, embeddings-before-write, safe receipts, token-only load/discard, zero external/domain calls.
- [x] `mcp_server/tests/test_catalog_prepare_neo4j_int.py` — required restart-safe bounded immutable-storage proof using only `oracle-catalog-tool-test`.
- [x] `mcp_server/tests/catalog_phase3a_gate_runner.py` and `mcp_server/tests/run_phase3a_gate.py` — tracked fail-closed Phase 3A readiness authority.
- [x] Characterization coverage around shared `upsert_catalog_batch` preflight extraction before refactoring.

Existing pytest, asyncio, Neo4j fixtures, Ruff, and Pyright infrastructure is sufficient. No dependency addition is permitted or needed.

---

## Manual-Only Verifications

All Phase 3A behaviors are automatable. Live Neo4j availability is environmental, not a manual substitute: unavailable means truthful skip and `ready_for_phase_3b=false`, not approval. Tests must use only `oracle-catalog-tool-test`; never query or mutate `oracle-catalog-v2`, run canary scripts, deploy, call `clear_graph`, or touch remote state.

---

## Security Threat Map

| Threat Ref | Threat | Mitigation Evidence |
|------------|--------|---------------------|
| T-03A-01 | Token theft, guessing, replay, or cross-plan authorization | `secrets.token_urlsafe(32)`; one-time response; digest-only storage; scope binding; terminal states; TTL |
| T-03A-02 | Timing or token-validity oracle | `hmac.compare_digest`; bounded fixed error codes/messages; discarded maps to `prepared_plan_not_found` |
| T-03A-03 | Partial or mutable prepared artifact | All validation/reads/embeddings precede one real transaction; CREATE-once root/chunks; byte and digest verification |
| T-03A-04 | Client authority injection through commit or Cypher schema | Strict token-only model; fixed server labels/properties; no caller UUID/hash/payload authority |
| T-03A-05 | Control-plane storage denial through payload/cardinality/capacity races | Configured and hard ceilings; bounded chunks; per-group lock plus same-transaction count/create |
| T-03A-06 | Artifact truncation, reordering, corruption, or restart drift | Ordered chunk UUIDs; per-chunk digest/offset/length; total length/count and artifact digest; fresh-session live proof |
| T-03A-07 | Illegal state revival or duplicate writer after stranded COMMITTING | Explicit CAS table; no COMMITTING→PREPARED reset; same-token COMMITTING re-entry only; terminal states immutable |
| T-03A-08 | Embedding/provider failure leaves partial plan or commit invokes external services | Embed before plan transaction; commit consumes frozen embeddings; spies prove no embedder/LLM/queue/HTTP calls |
| T-03A-09 | Token, payload, source text, or embeddings leak through responses/logs | Receipt omits payload/embeddings; raw token returned only once; logs limited to IDs/counts/state/error code |

---

## Hard-Gate Evidence

Phase 3A cannot set `ready_for_phase_3b=true` until the tracked ledger proves all of the following:

1. Every one of PLAN-01..12, PLAN-17..20, SAFE-11, and TEST-05 maps to green automated evidence.
2. Prepare writes only fixed control-plane labels; zero domain, evidence, manifest, or `CatalogIngestBatch` mutation.
3. A configured-maximum artifact survives commit, driver close, fresh driver/session load, and byte-identical reassembly on Neo4j 5.26+.
4. Immutability, group isolation, capacity serialization, digest-only token storage, state transitions, expiry, discard, and COMMITTING re-entry pass live tests.
5. Commit accepts token plus optional expected request hash only and performs zero external calls or Phase 3B domain writes.
6. Existing 14 legacy and eight Phase 2 catalog tools remain compatible; three new tools are additive.
7. Ledger records `canary_executed=false`, `oracle_catalog_v2_queried=false`, `clear_graph_called=false`, and no deployment/remote mutation.

Neo4j rejection, corruption, unsafe capacity races, control-label search contamination, or required re-embedding is a hard stop. Report the blocker. Do not reduce the contract to hashes, accept replacement client payloads, or add provisional domain writes.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verification or explicit Wave 0 dependencies.
- [x] Sampling continuity: no three consecutive tasks without automated verification.
- [x] Wave 0 covers every missing test/gate artifact.
- [x] No watch-mode flags.
- [x] Unit feedback latency <180 seconds.
- [x] Full focused pytest passes.
- [x] Scoped Ruff passes.
- [x] Scoped Pyright passes or baseline-only failures are truthfully isolated.
- [x] Required Neo4j immutable-artifact proof passes; skip does not authorize Phase 3B.
- [x] Safety ledger proves no canary, no `oracle-catalog-v2`, no `clear_graph`, no deploy/remote mutation.
- [x] `nyquist_compliant: true` and `wave_0_complete: true` set only after evidence exists.

**Approval:** Phase 3A hard-gate evidence accepted (see Nyquist audit 2026-07-18)

---

## Nyquist Audit — 2026-07-18

**Auditor:** adversarial Nyquist coverage (primary checkout `C:\Users\thien\PyCharmMiscProject\graphiti`)
**Git HEAD at audit:** `99a517b64e6935ffb7218b664a2bfd94f8246beb` (docs-only rebind after clean review)
**Ledger `evaluated_head`:** `6bcfc13da707daeba5424e5bcd99ff0b8067f066` (ancestor; files since evaluated: `03A-GATE-RESULTS.json` only → ledger-only-child)

### Outcome

| Field | Value |
|-------|-------|
| `status` | `validated` (retained) |
| `nyquist_compliant` | `true` (retained — all 18 Phase-3A requirement IDs automated + green) |
| Gaps filled this audit | 0 new tests (coverage already present) |
| Escalations | none |
| Implementation edits | none |

### Requirement coverage map (18 IDs)

| Req | Classification | Automated evidence |
|-----|----------------|--------------------|
| PLAN-01 | COVERED | `test_catalog_prepare_models.py` (full shell / extra-field / dry_run reject) |
| PLAN-02 | COVERED | `test_catalog_prepare_service.py` preflight + `test_catalog_service.py` dry_run regression |
| PLAN-03 | COVERED | service zero-domain spies + `test_catalog_prepare_neo4j_int.py::test_prepare_zero_domain_and_status_contamination` |
| PLAN-04 | COVERED | `test_catalog_prepared_artifact.py` full membership+embeddings serialize |
| PLAN-05 | COVERED | artifact chunk/reassemble unit + live multi-chunk restart (`neo4j_int`) |
| PLAN-06 | COVERED | token mint one-time + prepare receipt fields (service) |
| PLAN-07 | COVERED | `test_catalog_token.py` digest/`compare_digest` + live digest-only root props |
| PLAN-08 | COVERED | model HARD clamps + capabilities plan limits |
| PLAN-09 | COVERED | store CREATE fixed labels + live non-Entity assert |
| PLAN-10 | COVERED | commit/discard token-only models |
| PLAN-11 | COVERED | service commit load/CAS reject matrix + store CAS |
| PLAN-12 | COVERED | commit zero external spies (embedder/LLM/queue/HTTP) |
| PLAN-17 | COVERED | token binding helpers + post-load `plan_token_matches` |
| PLAN-18 | COVERED | terminal no-revive unit + live discard/expiry |
| PLAN-19 | COVERED | discard idempotent service + live |
| PLAN-20 | COVERED | upsert dry_run retained; additive prepare/commit/discard tools |
| SAFE-11 | COVERED | embed-before-plan; embed failure zero writes; commit no external |
| TEST-05 | COVERED | suite + gate runner + live 9/9 + 34/34 probes |

### Probe resolution equality

- `03A-EDGE-PROBE-RESOLUTION.json`: **34** entries, `row_index` 0..33 unique, no silent drop
- verification: **32 explicit**, **2 backstop** (`SAFE-log`, `PLAN-schema`) — both still point at real test files
- gate check `edge_probe_resolution`: **pass** (ledger)

### Review fix tests (WR-01..07)

| WR | Test evidence |
|----|---------------|
| WR-01 | `test_plan_token_matches_malformed_stored_digest_returns_false` |
| WR-02 | store schema SHOW/fail-closed `neo4j_schema_failed` |
| WR-03 | prepare `check_batch_status=True` + committed conflict paths |
| WR-04 | coalesce + `provenance_link_conflict` service tests (membership length assert real; plan count line has vacuous `or True` — INFO residual IN-R03, not requirement gap) |
| WR-05 | default `CANONICALIZATION_VERSION` store test |
| WR-06 | uniqueness race → `prepared_plan_conflict` |
| WR-07 | live expiry requires terminal `EXPIRED` |

### Gate ledger (authoritative)

From `03A-GATE-RESULTS.json` (not re-applied this audit):

| Check | Status |
|-------|--------|
| runner_self_tests | pass 12 |
| focused_pytest | pass 388 |
| scoped_ruff / scoped_pyright | pass |
| wave0_files / edge_probe_resolution / summary_presence | pass |
| prepare_commit_true | pass (`prepare_commit=true`) |
| safety_no_probe | pass (`canary_executed=false`, `oracle_catalog_v2_queried=false`, `clear_graph_called=false`) |
| control_plane_present | pass |
| live_neo4j_immutable_proof | pass **9/9** |
| `ready_for_phase_3b` | true |
| `local_gate_pass` | true |
| `nyquist_compliant` | true |

### Fresh verification this audit

```text
uv run --project mcp_server python -m pytest -c mcp_server/pytest.ini \
  mcp_server/tests/test_catalog_prepare_models.py \
  mcp_server/tests/test_catalog_prepared_artifact.py \
  mcp_server/tests/test_catalog_token.py \
  mcp_server/tests/test_catalog_prepare_store.py \
  mcp_server/tests/test_catalog_prepare_service.py \
  mcp_server/tests/test_catalog_capabilities.py \
  mcp_server/tests/test_catalog_phase3a_gate_runner.py \
  -q --tb=line
# → 178 passed in 1.76s
```

Live Neo4j not re-run (ledger already 9/9; safety: no canary / no `oracle-catalog-v2` / no `clear_graph`).

### Residuals (non-blocking)

- IN-R03 vacuous `or True` on plan `evidence_link_count` assert — test still proves membership coalesce via artifact body length.
- REQUIREMENTS.md checkboxes for PLAN-01..12/17..20/SAFE-11/TEST-05 still show pending in the global tracker (doc lag vs phase gate; not a test gap).
