# Phase 2 Final Digest Repair Summary

**Status:** complete (isolated worktree repair only — readiness remains orchestrator-owned)
**Base HEAD:** `e828ad28db613565b96ebaeec6aecdec2da95d97`
**Branch:** `worktree-agent-afbc0d87ff0ca0427`
**Date:** 2026-07-18

## One-liner

Phase 2 raw edge-probe digest is now LF-normalized SHA-256 `16144e5ebc2ae9a46cda9b45ce0206e1290b954988c227ce97ec0a05f6149ce0`, stable across CRLF/LF checkouts; product code and raw probe artifact unchanged.

## Root Cause

`load_raw_probe` hashed platform-native file bytes via `sha256_bytes(raw_bytes)`. Windows worktree checkouts surface `02-EDGE-PROBE.json` as CRLF while primary checkouts use LF. Same textual content, different SHA-256:

| Form | SHA-256 |
|------|---------|
| LF-normalized | `16144e5ebc2ae9a46cda9b45ce0206e1290b954988c227ce97ec0a05f6149ce0` |
| CRLF raw (this worktree) | `e515187cc229f7f24bd95444799abb900b3cf913900b3a65119e9befd6462599` |

`content_digest_map` already used `sha256_file_lf`; only the raw-probe identity path was inconsistent. Phase 1 runner already normalizes CRLF and lone CR before SHA-256.

## Fix

1. **Runner** (`mcp_server/tests/catalog_phase2_gate_runner.py`)
   - Added pure helpers `normalize_newlines_lf` (`CRLF→LF`, lone `CR→LF`) and `sha256_bytes_lf`.
   - `load_raw_probe` now returns `sha256_bytes_lf(raw_bytes)` while preserving `raw_bytes` unchanged for same-checkout re-read mutation assertion.
2. **Tests** (`mcp_server/tests/test_catalog_phase2_gate_runner.py`)
   - LF/CRLF/lone-CR normalization parity.
   - `sha256_bytes_lf` stability vs un-normalized difference.
   - Temporary LF and CRLF fixture copies yield identical digests; raw_bytes preserved.
   - Actual probe digest pinned to `16144e...`.
3. **Docs / ledger**
   - `02-EDGE-PROBE-RESOLUTION.json.raw_sha256` → `16144e...`
   - `02-PHASE2-GATE.md` Raw sha labeled **LF-normalized SHA-256** → `16144e...`
   - `02-05-SUMMARY.md` references updated.
   - `02-GATE-RESULTS.json` **not** hand-edited (still carries failed/primary-run residual `e515...` on `raw_edge_probe_sha256`); orchestrator regenerates after merge.

## Raw Artifact Unchanged Proof

| Check | Value |
|-------|-------|
| Git blob at base `e828ad28...` | `4b354a1f05d705c5015c2071c897816672865a9f` |
| Git blob of worktree file now | `4b354a1f05d705c5015c2071c897816672865a9f` |
| `git status` on `02-EDGE-PROBE.json` | clean (no modification) |
| Path | `.planning/phases/02-topology-authority-evidence-contract-hashes-and-capabilities/02-EDGE-PROBE.json` |

Raw artifact bytes and git object ID identical to base. Only the digest *interpretation* (LF-normalized) and ledger binding changed.

## Verification Run

| Check | Result |
|-------|--------|
| `pytest tests/test_catalog_phase2_gate_runner.py` | 15 passed |
| `check_edge_probe_raw` | OK |
| `check_edge_probe_resolution` | OK |
| load digest | `16144e5ebc2ae9a46cda9b45ce0206e1290b954988c227ce97ec0a05f6149ce0` |
| Ruff (scoped runner + tests) | All checks passed |
| Pyright (scoped runner + tests) | 0 errors |

## Commits

| Hash | Message |
|------|---------|
| `46ddae5` | `fix(02): LF-normalize raw edge-probe digest in load_raw_probe` |
| `e717695` | `docs(02): rebind edge-probe raw_sha256 to LF-normalized digest` |
| (this) | `docs(02): final digest repair summary` |

## Explicit Non-Actions

- No product/store/control-plane/domain code changes.
- No canary, oracle-catalog-v2, Neo4j, deploy, push, merge, tag.
- No rewrite of `02-EDGE-PROBE.json`.
- No hand-edit of `02-GATE-RESULTS.json` to green.
- No final gate/apply in this isolated worktree to claim primary readiness.
- STATE / ROADMAP / REQUIREMENTS not updated (orchestrator-owned).

## Canonical Digest

**LF-normalized SHA-256 of `02-EDGE-PROBE.json`:**
`16144e5ebc2ae9a46cda9b45ce0206e1290b954988c227ce97ec0a05f6149ce0`

## Self-Check

- [x] Runner helpers present (`normalize_newlines_lf`, `sha256_bytes_lf`)
- [x] `load_raw_probe` uses LF-normalized digest
- [x] Regression tests pass (LF/CRLF/lone-CR + actual probe pin)
- [x] RESOLUTION / PHASE2-GATE / 02-05-SUMMARY rebinding complete
- [x] GATE-RESULTS left for orchestrator
- [x] Raw probe blob `4b354a1f05d705c5015c2071c897816672865a9f` unchanged vs base
- [x] Commits present on `worktree-agent-afbc0d87ff0ca0427`
- [x] Worktree clean of temp scripts

## Self-Check: PASSED
