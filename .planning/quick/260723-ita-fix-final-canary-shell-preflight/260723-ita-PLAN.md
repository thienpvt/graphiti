---
phase: quick
plan: 260723-ita
type: tdd
wave: 1
depends_on: []
files_modified:
  - scripts/run_catalog_phase6_final_canary.py
  - tests/script/test_run_catalog_phase6_final_canary.py
  - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md
  - .planning/quick/260723-ita-fix-final-canary-shell-preflight/260723-ita-SUMMARY.md
autonomous: true
requirements:
  - P6-SAFE-01
  - P6-PRES-01
  - P6-RT-00
must_haves:
  truths:
    - "run_final_canary validates the real phase 06-FINAL-REPORT.md live-field marker shell before _claim_allocation"
    - "Committed 06-FINAL-REPORT.md contains LIVE_FIELDS_START and LIVE_FIELDS_END around the live classification section so post-run mapping can succeed"
    - "Missing or malformed markers raise FinalCanaryError before any allocation claim file is created"
    - "Regression tests load the real phase shell path and prove marker shell validates; separate cases prove missing/malformed markers fail before _claim_allocation"
    - "Exact invocation semantics preserved; no argv relaxation; no runtime, MCP, provider, namespace, ID allocation, canary, cleanup, image rebuild, or lifecycle completion"
  artifacts:
    - path: scripts/run_catalog_phase6_final_canary.py
      provides: pre-allocation final-report shell marker validation (read-only)
    - path: .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md
      provides: committed LIVE_FIELDS markers in live classification section
    - path: tests/script/test_run_catalog_phase6_final_canary.py
      provides: real shell + pre-allocation fail-closed regression coverage
  key_links:
    - from: run_final_canary after phase_dir resolve / freeze+image checks
      to: _claim_allocation
      via: new read-only shell preflight using marker check shared with _final_report_text
    - from: _map_phase_outputs / _final_report_text
      to: committed 06-FINAL-REPORT.md markers
      via: LIVE_FIELDS_START / LIVE_FIELDS_END
  prohibitions:
    - statement: MUST NOT run final canary end-to-end, allocate IDs, invoke builder/runner, or touch MCP/provider/runtime
      status: planned
    - statement: MUST NOT edit 06-FREEZE-RECEIPT.json, 06-POST-APPROVAL-INVOCATION.json, 06-IMAGE-RECEIPT.json, protected config, STATE.md, or ROADMAP.md
      status: planned
    - statement: MUST NOT relax argv/exact-invocation validation to work around prior path-representation failures
      status: planned
    - statement: MUST NOT complete Phase 6 lifecycle, cleanup, or image rebuild
      status: planned
---

<objective>
Fix final-canary pre-allocation safety: validate the real `06-FINAL-REPORT.md` live-field marker shell before `_claim_allocation`, and commit the required markers into the phase final-report shell. Add regression tests that load the real shell and prove fail-closed pre-allocation behavior. Preserve exact invocation semantics. No runtime/canary/identity work.

Purpose: Current `run_final_canary` claims allocation near L561, then later `_map_phase_outputs` → `_final_report_text` requires `LIVE_FIELDS_START`/`LIVE_FIELDS_END`. Committed shell has no markers, so a successful or failed run would allocate first then fail phase-output mapping. Prior attempts already rejected before allocation (exact argv path representation); no allocation claim exists. Do not address argv by relaxing code.

Output: launcher preflight + committed shell markers + focused tests + quick SUMMARY only.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@scripts/run_catalog_phase6_final_canary.py
@tests/script/test_run_catalog_phase6_final_canary.py
@.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md

## Failure chain
- Launcher: `scripts/run_catalog_phase6_final_canary.py`
- Allocation: `run_final_canary` → `_claim_allocation` (~L561) after freeze/image checks
- Mapping: `_map_phase_outputs` → `_final_report_text` (~L471) requires:
  - `LIVE_FIELDS_START = '<!-- phase6-final-canary-live:start -->'`
  - `LIVE_FIELDS_END = '<!-- phase6-final-canary-live:end -->'`
- Committed shell `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md` section 3 "Classification shell" has pending live fields but **no** markers
- Result without fix: allocate run_id / group_id / batch_id, then fail on marker invalid / mapping

## Required fix shape
1. Read-only preflight of real phase shell **before** `_claim_allocation`
2. Reuse `_final_report_text` marker rules or extract a minimal helper that does not write
3. Commit markers into the real shell live classification section
4. Tests: real shell validates; missing/malformed markers never call `_claim_allocation`

## Preserve
- Exact argv / freeze / image / shell=false / env MCP URL semantics
- Existing allocation exclusivity and post-allocation mapping behavior for valid shells
- No argv relaxation for prior path-representation rejection (top-level will invoke exact expanded argv on next approval)

## Out of scope / do not touch
- Runtime, Compose, MCP, provider, namespace, ID allocation, canary, cleanup, image rebuild
- `06-FREEZE-RECEIPT.json`, `06-POST-APPROVAL-INVOCATION.json`, image/bind/matrix receipts
- `mcp_server/config/config-docker-neo4j.yaml`
- `.planning/STATE.md`, `.planning/ROADMAP.md`
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED/GREEN pre-allocation shell preflight + committed markers</name>
  <files>scripts/run_catalog_phase6_final_canary.py, tests/script/test_run_catalog_phase6_final_canary.py, .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md</files>
  <read_first>
    - scripts/run_catalog_phase6_final_canary.py: LIVE_FIELDS_* constants, `_final_report_text`, `_map_phase_outputs`, `run_final_canary` order around `_claim_allocation`
    - tests/script/test_run_catalog_phase6_final_canary.py: existing final-report fixture patterns that already embed LIVE_FIELDS markers
    - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md section 3 Classification shell
  </read_first>
  <behavior>
    - GREEN: loading the real committed phase `06-FINAL-REPORT.md` text (or path) through the shell preflight/marker validation succeeds after markers are added
    - GREEN: missing start marker, missing end marker, or end-before-start raises FinalCanaryError with message matching `final report live field markers are invalid` (same contract as `_final_report_text`)
    - GREEN: `run_final_canary` path with a phase dir whose `06-FINAL-REPORT.md` lacks markers raises before `_claim_allocation` (monkeypatch `_claim_allocation` to fail the test if called)
    - GREEN: existing happy-path tests that plant marker shells continue to pass
    - No end-to-end canary, no real allocation claim on disk outside tmp fixtures, no argv contract changes
  </behavior>
  <action>
    1. Tests first (RED expected until product + shell fix):
       - Add a unit that reads the real repo path `.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-FINAL-REPORT.md` and asserts both LIVE_FIELDS markers are present and ordered (start index less than end index). Prefer calling the same preflight helper the launcher will use rather than re-implementing find logic only in the test.
       - Add a unit that feeds marker-valid text through the helper and does not raise.
       - Add units for missing start, missing end, and inverted/empty span; each raises FinalCanaryError matching `final report live field markers are invalid`.
       - Add an integration-style unit of `run_final_canary` with fixtures like existing tests, but write a phase `06-FINAL-REPORT.md` without markers. Monkeypatch `_claim_allocation` to raise AssertionError if called. Assert FinalCanaryError from shell preflight and that claim was not called.
    2. Product fix in `scripts/run_catalog_phase6_final_canary.py`:
       - Add a minimal read-only helper (e.g. `_validate_final_report_shell(text: str) -> None` or `_require_final_report_live_markers(phase_dir: Path) -> None`) that applies the same start/end find rules as `_final_report_text` without writing. Prefer extracting shared marker validation so `_final_report_text` and preflight cannot drift.
       - In `run_final_canary`, after `phase_dir` is known and freeze/image checks that already precede allocation, call the preflight on `phase_dir / '06-FINAL-REPORT.md'` before `_claim_allocation`. Fail closed on OSError/missing file with a clear FinalCanaryError (shell unavailable) and on invalid markers with the existing markers-invalid message.
       - Do not change `_claim_allocation` semantics, argv validation, freeze binding, or builder/runner paths.
    3. Committed shell fix in `06-FINAL-REPORT.md`:
       - In section 3 Classification shell (live uncommitted), wrap the live classification content with the exact marker strings from launcher constants:
         HTML comment start marker phase6-final-canary-live:start and matching end marker phase6-final-canary-live:end (use the exact LIVE_FIELDS_START / LIVE_FIELDS_END string values from the launcher module).
       - Keep existing pending placeholders and shell-only status; do not fill live values; do not claim canary executed.
       - Do not invent a second live region; one ordered pair is enough for `_final_report_text` replacement.
    4. Run focused pytest until GREEN. Commit only launcher + tests + final-report shell (plus later SUMMARY). Never stage freeze/post-approval/image receipts, protected config, STATE, or ROADMAP.
  </action>
  <verify>
    <automated>pytest tests/script/test_run_catalog_phase6_final_canary.py -q -k "final_report or live_field or shell or allocation or marker or preflight or claim" --tb=short</automated>
  </verify>
  <done>
    Real shell has ordered LIVE_FIELDS markers; launcher validates them before `_claim_allocation`; missing/malformed markers fail closed without claim; exact invocation semantics unchanged; no runtime/canary executed.
  </done>
</task>

<task type="auto">
  <name>Task 2: Quick SUMMARY only — no STATE/ROADMAP/lifecycle edits</name>
  <files>.planning/quick/260723-ita-fix-final-canary-shell-preflight/260723-ita-SUMMARY.md</files>
  <read_first>
    - $HOME/.claude/gsd-core/templates/summary.md
    - this PLAN.md success criteria
  </read_first>
  <action>
    Write `260723-ita-SUMMARY.md` recording: root cause (allocation before marker shell validation; committed shell lacked LIVE_FIELDS markers), fix (preflight + committed markers + shared validation), test names, and explicit non-claims (no canary run, no ID allocation claim, no argv relaxation, no freeze/post-approval/image edits, no STATE/ROADMAP edits). Do not edit STATE.md, ROADMAP.md, freeze receipt, POST-APPROVAL JSON, protected config, or other Phase 6 lifecycle receipts.
  </action>
  <verify>
    <automated>test -f .planning/quick/260723-ita-fix-final-canary-shell-preflight/260723-ita-SUMMARY.md</automated>
  </verify>
  <done>
    SUMMARY written; product fix already committed; STATE/ROADMAP/lifecycle artifacts untouched.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| phase final-report shell → launcher | Committed shell must present exact live markers before any identity allocation |
| allocation claim file | Must not be created if shell mapping would fail |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-ita-01 | Tampering | pre-allocation ordering | high | mitigate | Validate markers before `_claim_allocation`; tests assert claim not called on bad shell |
| T-ita-02 | Denial of service | orphan allocation claims | medium | mitigate | Fail closed pre-claim so retries are not blocked by dead claims from shell defects |
| T-ita-03 | Elevation | accidental canary/runtime during fix | high | mitigate | Tests use fixtures/monkeypatch only; prohibitions bar e2e canary and lifecycle mutation |
| T-ita-SC | Tampering | package installs | low | accept | No new packages |
</threat_model>

<verification>
- Focused pytest on shell markers / preflight / pre-allocation claim gating green
- Real `06-FINAL-REPORT.md` contains both LIVE_FIELDS markers in order
- `git status` shows no edits to freeze/post-approval/image receipts, protected config, STATE, ROADMAP
- No canary artifacts or allocation claims created outside test tmp
</verification>

<success_criteria>
1. `run_final_canary` validates final-report live markers before `_claim_allocation`
2. Committed phase `06-FINAL-REPORT.md` has ordered LIVE_FIELDS_START/END around live classification content
3. Missing/malformed markers raise FinalCanaryError without creating an allocation claim
4. Regression tests load the real shell and prove preflight + fail-closed pre-allocation behavior
5. Only launcher + launcher tests + final-report shell + quick SUMMARY modified
6. No runtime/canary/identity/image/lifecycle/STATE/ROADMAP work; no argv relaxation
</success_criteria>

<output>
Create `.planning/quick/260723-ita-fix-final-canary-shell-preflight/260723-ita-SUMMARY.md` when done
</output>
