---
phase: 02-topology-authority-evidence-contract-hashes-and-capabilities
reviewed: 2026-07-18T13:00:00Z
depth: deep
files_reviewed: 18
files_reviewed_list:
  - mcp_server/src/graphiti_mcp_server.py
  - mcp_server/src/models/catalog_batch.py
  - mcp_server/src/models/catalog_edges.py
  - mcp_server/src/models/catalog_evidence.py
  - mcp_server/src/models/catalog_responses.py
  - mcp_server/src/models/catalog_topology.py
  - mcp_server/src/services/catalog_capabilities.py
  - mcp_server/src/services/catalog_identity.py
  - mcp_server/src/services/catalog_service.py
  - mcp_server/tests/catalog_phase2_gate_runner.py
  - mcp_server/tests/run_phase2_gate.py
  - mcp_server/tests/test_catalog_capabilities.py
  - mcp_server/tests/test_catalog_evidence.py
  - mcp_server/tests/test_catalog_hash.py
  - mcp_server/tests/test_catalog_models.py
  - mcp_server/tests/test_catalog_phase2_gate_runner.py
  - mcp_server/tests/test_catalog_service.py
  - mcp_server/tests/test_catalog_topology.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: clean
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-18T13:00:00Z
**Depth:** deep
**Files Reviewed:** 18
**Status:** clean

## Summary

Deep re-review at primary HEAD `aa76806` (after `7aee976` WR-R01, `aa76806` WR-R02).

All prior Critical/Warning findings are fixed. Shared helper `_batch_provenance_item_count` now drives pre-read committed replay, in-tx `already_committed` replay, and failed/committed batch-status `provenance_count` as `sources + evidence_links`. Unit coverage added for both residual paths. No new Critical or Warning defects. Two non-blocking Info residuals preserved.

All reviewed files meet quality standards for Phase 2 ship criteria on Critical/Warning tiers.

## Narrative Findings (AI reviewer)

## Info

### IN-01: `CATALOG_TOOL_NAMES` SAFE-08 set still excludes `get_catalog_capabilities`

**File:** `mcp_server/src/graphiti_mcp_server.py:208-217`
**Issue:** Frozen SAFE-08 rewrite set lists the original seven request tools only. `get_catalog_capabilities` is registered and has no request model, so practical impact is near zero.
**Fix:** When capabilities gains parameters, add it to `CATALOG_TOOL_NAMES`. Optional now.

### IN-02: Evidence-link UUID helper unused on write path (Phase 3B deferred)

**File:** `mcp_server/src/services/catalog_identity.py:59-63`; `mcp_server/src/services/catalog_service.py` batch provenance loop
**Issue:** `catalog_evidence_link_uuid` / `evidence_link_key` feed request hashing coalesce, but `upsert_catalog_batch` never assigns evidence-link UUIDs or validates per-link `content_sha256` against `evidence_canonical_payload`. Links expand into source→target MENTIONS / edge episode attachments only. Acceptable Phase 2 deferral (EVID-07..11 / 3B).
**Fix:** No Phase 2 code change required. Phase 3B must wire UUID + content-hash checks.

## Prior findings disposition

| ID | Status | Evidence |
|----|--------|----------|
| CR-01 gate hash echo | **Fixed** (prior) | `upsert_catalog_batch` hashes before gate; `test_batch_gate_failure_echoes_request_hash` |
| WR-01 sources under configured max | **Fixed** (prior) | `_batch_gate_error` dual source/link caps; sources unit test |
| WR-02 pre-read committed replay | **Fixed** (prior) | `_batch_provenance_item_count` at pre-read short-circuit |
| WR-03 pagination limits | **Fixed** (prior) | `max_page_size` on configured + hard maps |
| WR-R01 in-tx `already_committed` | **Fixed** | `catalog_service.py:4843`; `test_batch_in_tx_already_committed_counts_evidence_links_as_unchanged` (`7aee976`) |
| WR-R02 status `provenance_count` | **Fixed** | `catalog_service.py:4596`, `:4824` via helper; `test_batch_status_provenance_count_includes_evidence_links` (`aa76806`) |
| IN-01 capabilities SAFE-08 | **Preserved** | non-blocking |
| IN-02 evidence UUID write path | **Preserved** | non-blocking / Phase 3B |

## Cross-file notes (no extra findings)

- Helper `_batch_provenance_item_count` is the single authority for request-domain provenance membership on replay + status write paths.
- Topology: `EDGE_ENDPOINT_MAP` keys match `CATALOG_EDGE_TYPES` (16); deferred types absent; model + service share `validate_edge_endpoint_pair` before embed/tx.
- Evidence model: exclusive target, kind allowlist, finite confidence, SHA-256 format, Cartesian rejected without conversion.
- Hash recipe: single `CANONICALIZATION_VERSION`, excludes `dry_run` / caller `request_sha256`, order-invariant collections, byte-identical evidence coalesce.
- Capabilities: mutation-free, fingerprint domain-separated, raw namespace never returned; pagination keys present.
- Gate runner: shell-exec forbid, integration module forbid, sentinel `assert False` nonzero, `ready_for_phase_3a` fail-closed.
- Coarse `failed=` ceilings on some error paths still use `len(provenance_sources)` (prepared sources only). Not a membership/hash contract field; not elevated to Warning.

---

_Reviewed: 2026-07-18T13:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
