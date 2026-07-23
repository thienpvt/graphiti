---
phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
plan: 09
subsystem: catalog-ollama-bind-image
tags: [ollama, raw-git, archive, image, secret-scan, bind, projection]

requires:
  - phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure
    provides: Ollama preflight + MATRIX_GREEN (06-08)
provides:
  - exact raw-Git Ollama BIND for candidate 3b349dd
  - archive-rooted 18-check READY_FOR_IMAGE_BINDING matrix
  - one source-bound Ollama image with complete zero-hit scan
  - 06-OLLAMA-BIND-RECEIPT.json and 06-OLLAMA-IMAGE-RECEIPT.json
affects:
  - 06-10 R0-R3 prefreeze
  - 06-11 freeze/canary handoff

tech-stack:
  added: []
  patterns:
    - new evidence uses 06-OLLAMA-* only; OpenAI 06-BIND/IMAGE immutable non-authority
    - raw-Git LF-exact archive via materialize_raw_git_archive; disposable archive-local Git for matrix
    - deterministic filtered projection denylists config-docker-neo4j.yaml and .planning/**
    - OCI revision=full candidate SHA; org.graphiti.source-context-sha256=full archive context
    - one image ceiling; candidate-bound scan_complete_image; --pull=false

key-files:
  created:
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-BIND-RECEIPT.json
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-IMAGE-RECEIPT.json
  modified: []

key-decisions:
  - "Candidate authority is HEAD after 06-08 docs: 3b349dd7cc9aa48a0b1ffdfa52f905097248c60f"
  - "Prior OpenAI image sha256:3602956… is non-authority for Ollama path"
  - "Image projection uses fixed COPY_SET + denylist unlink of config-docker-neo4j.yaml only"
  - "Regular-file rootfs materialization for Windows-safe complete-image scan"

patterns-established:
  - "06-OLLAMA-BIND/IMAGE receipts mirror OpenAI BIND/IMAGE schema with prior_openai_image_not_authority"
  - "Archive matrix reuses 06-08 18 named checks archive-rooted with disposable Git metadata"

requirements-completed: [P6-OLL-BIND-01, P6-OLL-IMG-01]

coverage:
  - id: D1
    description: Exact raw-Git bind of Ollama candidate with zero blob mismatch and READY_FOR_IMAGE_BINDING matrix
    requirement: P6-OLL-BIND-01
    verification:
      - kind: other
        ref: .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-BIND-RECEIPT.json
        status: pass
      - kind: unit
        ref: archive-rooted 18-check matrix (compile/pytest/ruff/pyright/e2e)
        status: pass
    human_judgment: false
  - id: D2
    description: One archive-projection source-bound image with complete secret scan zero hits
    requirement: P6-OLL-IMG-01
    verification:
      - kind: other
        ref: .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-IMAGE-RECEIPT.json
        status: pass
      - kind: other
        ref: scan_complete_image over export rootfs/config/history/layers
        status: pass
    human_judgment: false

duration: 16min
completed: 2026-07-23
status: complete
---

# Phase 06 Plan 09: Ollama Bind and Source-Bound Image Summary

**Exact raw-Git bind of candidate `3b349dd` (803 blobs) plus one archive-projection image `sha256:431a246…` with complete secret scan zero hits; OpenAI image remains non-authority**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-07-23T11:21:00Z
- **Completed:** 2026-07-23T11:37:26Z
- **Tasks:** 2
- **Files modified:** 2 receipts (+ SUMMARY)

## Accomplishments

- Froze Ollama remediation candidate `3b349dd7cc9aa48a0b1ffdfa52f905097248c60f` / tree `168dcdf3c6fc12d246c28271087d0ba808d7f82a`
- Exact raw-Git archive: 803 members; missing/extra/mismatch `0/0/0`
- Context `3d782aa9eeb2f84798b7586e4c5f02012f68a0032fb26bbae3cea795e7afc76f`
- Archive-rooted 18-check matrix `READY_FOR_IMAGE_BINDING` including required Ollama E2E (5 passed)
- One image: `graphiti-mcp:phase6-cleanroom-3b349dd7cc9a-bound` / `sha256:431a24619ac4…`
- OCI labels: revision=full candidate; source-context=full archive context; `--pull=false`
- Projection: 205 members; protected config and `.planning/**` excluded
- Complete-image scan: secret_pattern_hits=0; denylisted_path_count=0
- Prior OpenAI image `sha256:3602956…` preserved and non-authority
- No runtime/Compose start, canary IDs, push, retag, or historical mutation

## Task Commits

1. **Task 1: Commit candidate + raw-Git exact archive bind + archive matrix** - `278a455` (test)
2. **Task 2: Source-bound Ollama image + secret scan** - `6071b0d` (test)

**Plan metadata:** (pending final docs commit)

## Files Created/Modified

- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-BIND-RECEIPT.json` - exact bind + matrix gate
- `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-OLLAMA-IMAGE-RECEIPT.json` - image/tag/labels/scan

## Candidate Authority

- **Commit:** `3b349dd7cc9aa48a0b1ffdfa52f905097248c60f`
- **Parent:** `5f787121e2a3bb007b553ce3cd4539acdb8d4eb9`
- **Tree:** `168dcdf3c6fc12d246c28271087d0ba808d7f82a`
- **Files:** 803
- **Context:** `3d782aa9eeb2f84798b7586e4c5f02012f68a0032fb26bbae3cea795e7afc76f`
- **Image tag:** `graphiti-mcp:phase6-cleanroom-3b349dd7cc9a-bound`
- **Image ID prefix:** `sha256:431a24619ac4`
- **Build count:** 1

## Decisions Made

- Candidate freeze = post-06-08 HEAD `3b349dd` (no additional product fix-forward required)
- Write only `06-OLLAMA-*` receipts; leave OpenAI `06-BIND/IMAGE` immutable
- Projection uses archive bytes + fixed denylist; never dirty checkout
- Image identity from BIND.commit + BIND.archive_context_sha256 only

## Deviations from Plan

None - plan executed exactly as written (matrix helper used disposable job-dir scripts; no product source edits).

## Issues Encountered

- `py_compile` initially included YAML example (SyntaxError) — restricted compile set to `.py` only in disposable runner
- Manifest field check needed `scripts.catalog_canary_manifest_contract.LIVE_MANIFEST_FIELDS` import path

## Auth Gates

None

## Known Stubs

None

## Threat Flags

None beyond plan mitigations (denylist + complete-image scan; no second image)

## Matrix Check Counts (archive-rooted)

| # | Check | Status |
|---|-------|--------|
| 1 | changed_python_compile | pass (14 py files) |
| 2 | root_ollama_embedder_tests | pass (22) |
| 3 | mcp_factory_tests | pass (28) |
| 4 | cleanroom_config_materializer | pass (5) |
| 5 | catalog_capabilities | pass (41) |
| 6 | final_canary_launcher | pass (33) |
| 7 | builder_runner_related | pass (75) |
| 8 | schema_bootstrap | pass (8) |
| 9 | phase5_focused_suite | pass (413) |
| 10 | phase6_focused_suite | pass (187) |
| 11 | combined_remediation_union | pass (517) |
| 12 | golden_contract_hash | pass (17; intentional -k) |
| 13 | exact_22_field_manifest | pass (22 fields) |
| 14 | exact_28_tool_registry | pass (4 selected) |
| 15 | ruff_check | pass |
| 16 | ruff_format_check | pass |
| 17 | pyright_touched_packages | pass (root/mcp 0) |
| 18 | required_real_ollama_e2e | pass (5) |

- **image_build_count:** 1
- **runtime_start_count:** 0
- **canary_ids_allocated:** false

## Next Phase Readiness

- Ollama BIND+IMAGE green for 06-10 new R0–R3 on new runtime resources
- Do not reuse OpenAI clean-room project `graphiti-phase6-cleanroom-1f529136` or OpenAI image as authority
- Never create 06-05-SUMMARY or 06-11-SUMMARY in this wave

## Self-Check: PASSED

- FOUND: `06-OLLAMA-BIND-RECEIPT.json`
- FOUND: `06-OLLAMA-IMAGE-RECEIPT.json`
- FOUND: `06-09-SUMMARY.md`
- FOUND commits: `278a455`, `6071b0d`
- Historical `06-BIND-RECEIPT.json` / `06-IMAGE-RECEIPT.json` unchanged
- Prior OpenAI image still inspectable; new image ID differs
- image_build_count exactly 1

---
*Phase: 06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure*
*Completed: 2026-07-23*
