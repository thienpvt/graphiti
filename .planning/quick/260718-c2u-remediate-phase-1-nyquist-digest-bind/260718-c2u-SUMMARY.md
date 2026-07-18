---
phase: quick
plan: 260718-c2u
status: complete
date: 2026-07-18
---

# Quick 260718-c2u: Remediate Phase 1 Nyquist digest bind Summary

Cleared independent Nyquist NON-COMPLIANT digest-bind blockers on primary `claude/v1.1-pre-canary-hardening`.

## Fixes

1. **LF-stable digests** — `catalog_phase1_gate_runner.content_digest_map` now hashes newline-normalized (LF) bytes via `sha256_file_lf`. Windows autocrlf / text-mode writes no longer break run→apply verification.
2. **LF writers** — `write_text_lf` used for VALIDATION/PHASE1-GATE apply writes; no platform CRLF on gate docs.
3. **Scope Stop** — removed stale rebound HEAD `6728672b8822`; cites primary line HEAD `cfdbeec` + ledger-only-child policy.
4. **Rebind** — runner `run` + `apply` green: `evaluated_head=cfdbeec…`, `local_gate_pass=true`, `nyquist_compliant=true`, `ready_for_phase_2=false`, four `independent_*=pending`.

## Verify

- `verify_ledger` ok / head_reason=exact / errors=[]
- All 7 GATE_INPUT digests match LF-normalized content; on-disk files LF-only
- Runner self-tests 8/8 pass
- Unrelated dirt preserved

## Notes

- Product matrix not re-executed beyond runner path (prior green retained in ledger results).
- Phase 2 not started.
