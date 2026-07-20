---
phase: quick-260717-wvz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/ROADMAP.md
  - .planning/REQUIREMENTS.md
  - .planning/STATE.md
autonomous: true
requirements: []
must_haves:
  truths:
    - ROADMAP.md and REQUIREMENTS.md phase structure match canonical English roadmap (Phase 0, 1, 2, 3A, 3B, 4, 5; Phase 6 canary out of scope)
    - Every v1.1 requirement ID appears exactly once in REQUIREMENTS.md Traceability (count=138, unique=138, missing=0, duplicates=0)
    - Evidence-contract write requirements sit in Phase 2; prepare control plane in 3A; domain+evidence+manifest atomic writes in 3B; manifest-backed verify/diagnostics in Phase 4
    - Shipped v1.0 Phase 1–2 history preserved; no product code, tests, config, k8s, docker, or catalog/* touched
    - Dirty-worktree unrelated files remain unstaged and uncommitted
  artifacts:
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
  key_links:
    - REQUIREMENTS Traceability phase labels match ROADMAP phase headings
    - ROADMAP Coverage counts equal Traceability per-phase counts and sum to 138
    - Canonical source .planning/graphiti_mcp_pre_canary_roadmap_en.md remains authoritative for structure; not deleted
---

<objective>
Reconcile `.planning/ROADMAP.md` and `.planning/REQUIREMENTS.md` to the canonical English pre-canary roadmap, remapping all 138 requirement IDs uniquely, without implementing product code.

Purpose: Current GSD artifacts use offset phases 3–7 with evidence still co-located with prepare/commit. Canonical source uses Phase 0 / 1 / 2 / 3A / 3B / 4 / 5 and moves evidence contract into Phase 2, splitting prepare control plane from atomic domain writes.

Output: Updated planning docs only; verified 138/138 unique mappings; STATE.md focus aligned.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/graphiti_mcp_pre_canary_roadmap_en.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/PROJECT.md

## Dirty worktree — DO NOT TOUCH
Unrelated modified/untracked paths must not be edited, staged, or committed:
- `.planning/config.json`
- `mcp_server/config/config-docker-neo4j.yaml`
- `mcp_server/k8s/graphiti-neo4j.yaml`
- `.codegraph/`
- `catalog/`
- `mcp_server/sample_catalog.json`

Allowed commit files only:
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
- this quick-task plan/summary under `.planning/quick/260717-wvz-reconcile-planning-roadmap-md-and-planni/`

## Canonical phase spine (authoritative)
From `.planning/graphiti_mcp_pre_canary_roadmap_en.md` §3–§4:

| Canonical phase | Role |
|---|---|
| Phase 0 | Baseline, inventory, compatibility policy (entry gate; may carry BASE + worktree/isolation policy only) |
| Phase 1 | Strict contracts + catalog-v2 identity |
| Phase 2 | Topology authority, **evidence contract**, canonical hashes, capabilities |
| Phase 3A | Immutable prepare/commit **control plane** (prepare/discard/token; no domain graph write) |
| Phase 3B | Atomic catalog + **exact evidence persist** + durable **manifest write** |
| Phase 4 | Manifest-backed verification + read-only diagnostics + split gates |
| Phase 5 | Verification, security, compatibility, observability, migration docs, final report |
| Phase 6 | Canary as **separate task** — out of scope; no requirement IDs |

## Current (pre-reconcile) mapping to replace
GSD currently uses offset phases after shipped v1.0:

| Current phase | Count | Categories (approx) |
|---|---:|---|
| Phase 3 | 33 | BASE, SAFE (baseline/isolation), CONT, IDEN, TEST-01/03 |
| Phase 4 | 27 | EDGE, HASH, CAPA, TEST-02/04 |
| Phase 5 | 42 | PLAN, EVID (write), MANI (write), SAFE-11, TEST-05/06/07 |
| Phase 6 | 20 | MANI-05, VERI, RESE, GATE, EVID-12/13, TEST-08/09 |
| Phase 7 | 16 | SAFE (security/compat), TEST-10/11/12, DOCS, REPT |
| **Total** | **138** | |

## Required remaps (canon §4)
1. **Evidence-contract requirements move from old Phase 5 → Phase 2** (with EDGE/HASH/CAPA). Includes write-side EVID model/validation IDs that freeze the contract before prepare hashing freezes: at minimum `EVID-01`–`EVID-06`, `EVID-14`, and any pure-contract parts of `EVID-07`–`EVID-11` that define the schema (not Neo4j persist). Prefer moving **all schema/contract EVID IDs that do not require store writes** into Phase 2; keep **persist/interop/read** EVID IDs in 3B/4 as appropriate.
2. **Old Phase 5 PLAN/MANI/SAFE-11/TEST-05/06/07 split into 3A vs 3B:**
   - **3A (control plane):** prepare/discard tools, immutable payload storage, token digest, TTL/limits, no domain mutation proofs, commit accepts token-only, no external calls on commit path, state machine, concurrency/replay of token scope — typically `PLAN-01`–`PLAN-12`, `PLAN-17`–`PLAN-20`, control-plane parts of `PLAN-14`–`PLAN-16`, `SAFE-11`, `TEST-05` (prepare), parts of `TEST-06` (token concurrency).
   - **3B (atomic domain write):** domain+evidence+manifest co-commit, exact evidence persist, manifest membership authority write, rollback, search interop evidence records — typically `PLAN-13`–`PLAN-16` domain-tx truths, `EVID-07`–`EVID-11` (persist), `MANI-01`–`MANI-04`, `MANI-06`–`MANI-07`, `TEST-06` (no duplicate domain/manifest), `TEST-07`.
3. **Phase 4** keeps read/verify/diagnostics: `MANI-05`, `VERI-*`, `RESE-*`, `GATE-*`, `EVID-12`–`EVID-13`, `TEST-08`–`TEST-09`.
4. **Phase 5** keeps final security/docs/report: remaining `SAFE-*`, `TEST-10`–`TEST-12`, `DOCS-*`, `REPT-01`.
5. **Phase 0** absorbs baseline inventory/policy from old Phase 3: `BASE-01`–`BASE-04`, and isolation/worktree/remote policy that is baseline-only (`SAFE-01`, `SAFE-02`, `SAFE-12`, `SAFE-13`) if they fit exit criteria without product contract code. Remaining identity/error SAFEs stay Phase 1 or Phase 5 as today (`SAFE-05`/`SAFE-08` with identity; security SAFEs with Phase 5).
6. **Phase 1** holds CONT + IDEN + contract TESTs (+ identity-adjacent SAFE).
7. **Do not invent, drop, or renumber requirement IDs.** Same 138 IDs only. Future/out-of-scope sections may stay; they are not in the 138.

## v1.0 history preservation
- Keep Shipped Milestones section for **v1.0 Phase 1–2** with archive links.
- Avoid ambiguous bare "Phase 1" for v1.0 vs v1.1: label shipped rows as `v1.0 Phase 1` / `v1.0 Phase 2` and active work as canonical `Phase 0`…`Phase 5`.
- Do not rewrite milestone archives under `.planning/milestones/`.

## Hard constraints
- Documentation/planning only — no product code, tests, runtime config, deploy manifests, catalog outputs.
- No push/merge/deploy/tag.
- No canary execution; no `oracle-catalog-v2` query/mutation language that implies live ops.
- Preserve core value, non-goals, hard gates spirit from both sources; rephrase gates to match 0/1/2/3A/3B/4/5 order.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build remap matrix and rewrite ROADMAP.md to canonical spine</name>
  <files>.planning/ROADMAP.md</files>
  <action>
Read canonical `.planning/graphiti_mcp_pre_canary_roadmap_en.md` and current `.planning/ROADMAP.md` fully once.

Produce an internal remap matrix (may live only in commit message / SUMMARY, or a short comment block at bottom of ROADMAP Coverage — prefer no extra files):

1. List all 138 IDs from REQUIREMENTS Traceability.
2. Assign each ID to exactly one of: Phase 0, Phase 1, Phase 2, Phase 3A, Phase 3B, Phase 4, Phase 5 per rules in context.
3. Ensure category counts remain sensible and **sum to 138**. Expected rough targets after remap (adjust only by moving whole IDs, never splitting an ID):
   - Phase 0: BASE-01..04 + baseline SAFE isolation/worktree/remote (typically 4–8 IDs)
   - Phase 1: CONT + IDEN + TEST-01/03 + identity SAFE (remainder of old 33 after Phase 0 pull)
   - Phase 2: EDGE + HASH + CAPA + TEST-02/04 + evidence-contract EVID IDs moved from old Phase 5
   - Phase 3A + 3B: remaining PLAN/MANI-write/SAFE-11/TEST-05/06/07 + persist EVID (old 42 minus EVID moved to Phase 2)
   - Phase 4: 20 (same membership as old Phase 6 unless an ID clearly belongs elsewhere)
   - Phase 5: 16 (same membership as old Phase 7)
   - If evidence move changes Phase 2 and 3A/3B counts away from 27/42, that is **required** by canon; do **not** force old 27/42. Only total must stay 138.

Rewrite `.planning/ROADMAP.md`:
- Overview: describe v1.1 pre-canary hardening using canonical phase names; keep note that v1.0 shipped typed primitives + provenance/atomic batch.
- Shipped Milestones: preserve v1.0 table and archive links; label as v1.0 phases.
- Phases checklist: Phase 0, 1, 2, 3A, 3B, 4, 5 incomplete; mention Phase 6 canary is out of scope / separate approval.
- Hard Gates: restate gates in canonical order (no store writes before Phase 1–2 unit gates; no commit before 3A prepare/discard proofs; no manifest-backed verify before 3B atomic co-commit; final readiness Phase 5; stop-and-report if Neo4j cannot store prepared payloads or co-commit).
- Phase Details: one section per Phase 0/1/2/3A/3B/4/5 with Goal, Depends on, **Requirements:** full ID list for that phase, Success Criteria (outcome-shaped from canon exit criteria + current success truths), Plans: TBD, phase-specific Research/Stop condition where canon has them (3A/3B Neo4j payload/tx limits).
- Coverage table: per-phase counts + total 138; Mapped 138/138; Orphans 0; Duplicates 0.
- Explicit Non-Goals: merge current non-goals with canon §5 (no real canary, no auto v1→v2 migration, no parsers/inference, no live-group writes, no multi-backend catalog claims, no deploy/push).
- Do not delete or modify the canonical source file.

Do not touch product code or dirty unrelated files.
  </action>
  <verify>
    <automated>python -c "from pathlib import Path; import re; t=Path('.planning/ROADMAP.md').read_text(encoding='utf-8'); assert 'Phase 0' in t and 'Phase 3A' in t and 'Phase 3B' in t; assert 'Phase 7' not in t or 'v1.0' in t; ids=re.findall(r'\b([A-Z]{4}-\d{2})\b', t); print('roadmap_id_mentions', len(ids), 'unique_in_roadmap', len(set(ids))); print('OK structure')" </automated>
  </verify>
  <done>ROADMAP.md uses canonical Phase 0/1/2/3A/3B/4/5 structure with full requirement lists, v1.0 history preserved, coverage totals stated as 138.</done>
</task>

<task type="auto">
  <name>Task 2: Rewrite REQUIREMENTS Traceability and phase alignment; update STATE.md</name>
  <files>.planning/REQUIREMENTS.md, .planning/STATE.md</files>
  <action>
Update `.planning/REQUIREMENTS.md`:
- Keep all 138 requirement **definitions** (checkbox body text) unchanged in meaning; only adjust wording if a phase reference inside a definition is wrong after remap.
- Rebuild **Traceability** table so every ID maps to exactly one of: `Phase 0`, `Phase 1`, `Phase 2`, `Phase 3A`, `Phase 3B`, `Phase 4`, `Phase 5` matching ROADMAP Task 1 lists.
- Update Coverage summary counts by phase; total 138; unmapped 0; duplicates 0.
- Keep Future Requirements and Out of Scope tables; align out-of-scope language with canon §5 if needed without adding IDs to the 138.
- Update footer timestamp note: reconciled to `graphiti_mcp_pre_canary_roadmap_en.md` on 2026-07-17.

Update `.planning/STATE.md`:
- Current focus: Phase 0 (or Phase 1 if Phase 0 is marked pure entry with zero IDs — prefer Phase 0 if it owns BASE IDs).
- Progress: total_phases for active v1.1 spine = 7 work units (0,1,2,3A,3B,4,5) or document clearly; completed still 0 for v1.1.
- Decisions: add bullet that planning artifacts were remapped from offset Phases 3–7 to canonical 0/1/2/3A/3B/4/5; evidence contract before prepare; 3A control plane before 3B domain write; 138 IDs preserved.
- Session continuity: next is plan Phase 0 or Phase 1 after roadmap approval — not "plan Phase 3".
- Preserve dirty-worktree and no-push blockers.

Do not modify requirement ID strings. Do not implement code.
  </action>
  <verify>
    <automated>python -c "
import re
from pathlib import Path
from collections import Counter
req = Path('.planning/REQUIREMENTS.md').read_text(encoding='utf-8')
road = Path('.planning/ROADMAP.md').read_text(encoding='utf-8')
# definition IDs
defs = re.findall(r'^\s*-\s*\[[ x]\]\s*\*\*([A-Z]{4}-\d{2})\*\*:', req, re.M)
# traceability
rows = re.findall(r'^\|\s*([A-Z]{4}-\d{2})\s*\|\s*(Phase\s+(?:0|1|2|3A|3B|4|5))\s*\|', req, re.M)
print('defs', len(defs), 'unique_defs', len(set(defs)))
print('trace_rows', len(rows), 'unique_trace', len(set(i for i,_ in rows)))
dups = [k for k,v in Counter(i for i,_ in rows).items() if v>1]
missing = sorted(set(defs) - set(i for i,_ in rows))
extra = sorted(set(i for i,_ in rows) - set(defs))
print('dups', dups, 'missing', missing, 'extra', extra)
print('by_phase', dict(sorted(Counter(p for _,p in rows).items())))
assert len(defs)==138 and len(set(defs))==138
assert len(rows)==138 and len(set(i for i,_ in rows))==138
assert not dups and not missing and not extra
# ROADMAP must list each ID at least once in a Requirements line
road_ids=set()
for m in re.finditer(r'\*\*Requirements\*\*:\s*(.+)', road):
    road_ids.update(re.findall(r'\b([A-Z]{4}-\d{2})\b', m.group(1)))
assert set(defs)==road_ids, f'roadmap_req_symdiff={sorted(set(defs)^road_ids)[:20]}'
print('ALIGN_OK')
" </automated>
  </verify>
  <done>REQUIREMENTS Traceability is 138 unique phase mappings aligned with ROADMAP; STATE.md points at canonical Phase 0/1 start.</done>
</task>

<task type="auto">
  <name>Task 3: Deterministic coverage verification and scoped commit</name>
  <files>.planning/ROADMAP.md, .planning/REQUIREMENTS.md, .planning/STATE.md</files>
  <action>
Run the full verification script below; it must print `PASS` with count=138 unique=138 missing=0 duplicates=0 and phase-alignment OK. Fix any doc drift until it passes.

```python
# save as ephemeral / run via python -c — do not leave a new permanent tool unless already desired
import re
from pathlib import Path
from collections import Counter, defaultdict
req = Path('.planning/REQUIREMENTS.md').read_text(encoding='utf-8')
road = Path('.planning/ROADMAP.md').read_text(encoding='utf-8')
state = Path('.planning/STATE.md').read_text(encoding='utf-8')
defs = re.findall(r'^\s*-\s*\[[ x]\]\s*\*\*([A-Z]{4}-\d{2})\*\*:', req, re.M)
rows = re.findall(r'^\|\s*([A-Z]{4}-\d{2})\s*\|\s*(Phase\s+(?:0|1|2|3A|3B|4|5))\s*\|', req, re.M)
ids = [i for i,_ in rows]
phases = [p for _,p in rows]
ctr = Counter(ids)
dups = sorted([k for k,v in ctr.items() if v>1])
missing = sorted(set(defs)-set(ids))
extra = sorted(set(ids)-set(defs))
by = Counter(phases)
road_ids=set()
for m in re.finditer(r'\*\*Requirements\*\*:\s*(.+)', road):
    road_ids.update(re.findall(r'\b([A-Z]{4}-\d{2})\b', m.group(1)))
# per-phase set equality
road_by=defaultdict(set)
for m in re.finditer(r'### (Phase (?:0|1|2|3A|3B|4|5))[^\n]*\n(?:.*?\n)*?\*\*Requirements\*\*:\s*(.+)', road):
    road_by[m.group(1)].update(re.findall(r'\b([A-Z]{4}-\d{2})\b', m.group(2)))
req_by=defaultdict(set)
for i,p in rows:
    req_by[p].add(i)
phase_mismatch = {p: (sorted(req_by[p]-road_by[p]), sorted(road_by[p]-req_by[p])) for p in sorted(set(req_by)|set(road_by)) if req_by[p]!=road_by[p]}
assert 'Phase 3A' in road and 'Phase 3B' in road
assert 'canonical' in state.lower() or 'Phase 0' in state or '3A' in state
ok = (len(defs)==138 and len(set(defs))==138 and len(ids)==138 and len(set(ids))==138
      and not dups and not missing and not extra and not phase_mismatch and set(defs)==road_ids)
print('count', len(ids), 'unique', len(set(ids)), 'missing', len(missing), 'duplicates', len(dups))
print('by_phase', dict(sorted(by.items())))
print('phase_mismatch', phase_mismatch)
print('PASS' if ok else 'FAIL')
raise SystemExit(0 if ok else 1)
```

Also confirm with `git status` that only allowed planning files are modified for this task; leave dirty unrelated paths alone.

Commit **only** allowed files with message like:
`docs(planning): reconcile ROADMAP/REQUIREMENTS to pre-canary canonical phases`

Do not push. Do not stage dirty unrelated paths.
  </action>
  <verify>
    <automated>python -c "
import re
from pathlib import Path
from collections import Counter, defaultdict
req = Path('.planning/REQUIREMENTS.md').read_text(encoding='utf-8')
road = Path('.planning/ROADMAP.md').read_text(encoding='utf-8')
defs = re.findall(r'^\s*-\s*\[[ x]\]\s*\*\*([A-Z]{4}-\d{2})\*\*:', req, re.M)
rows = re.findall(r'^\|\s*([A-Z]{4}-\d{2})\s*\|\s*(Phase\s+(?:0|1|2|3A|3B|4|5))\s*\|', req, re.M)
ids=[i for i,_ in rows]
dups=[k for k,v in Counter(ids).items() if v>1]
missing=sorted(set(defs)-set(ids)); extra=sorted(set(ids)-set(defs))
road_ids=set();
for m in re.finditer(r'\*\*Requirements\*\*:\s*(.+)', road):
    road_ids.update(re.findall(r'\b([A-Z]{4}-\d{2})\b', m.group(1)))
road_by=defaultdict(set)
for m in re.finditer(r'### (Phase (?:0|1|2|3A|3B|4|5))[^\n]*\n(?:.*?\n)*?\*\*Requirements\*\*:\s*(.+)', road):
    road_by[m.group(1)].update(re.findall(r'\b([A-Z]{4}-\d{2})\b', m.group(2)))
req_by=defaultdict(set)
for i,p in rows: req_by[p].add(i)
phase_mismatch={p:(sorted(req_by[p]-road_by[p]), sorted(road_by[p]-req_by[p])) for p in set(req_by)|set(road_by) if req_by[p]!=road_by[p]}
ok=len(defs)==138 and len(set(defs))==138 and len(ids)==138 and len(set(ids))==138 and not dups and not missing and not extra and not phase_mismatch and set(defs)==road_ids
print('count',len(ids),'unique',len(set(ids)),'missing',len(missing),'duplicates',len(dups))
print('by_phase',dict(sorted(Counter(p for _,p in rows).items())))
print('PASS' if ok else 'FAIL')
raise SystemExit(0 if ok else 1)
" </automated>
  </verify>
  <done>Verification prints PASS with count=138 unique=138 missing=0 duplicates=0; ROADMAP/REQUIREMENTS/STATE committed without unrelated dirty files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| planning docs → implementers | Phase/req mapping is the execution contract for later code phases |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-quick-01 | Tampering | ROADMAP/REQUIREMENTS remap | medium | mitigate | Deterministic 138 unique gate; no silent ID drop/dup |
| T-quick-02 | Information Disclosure | commit scope | low | mitigate | Stage only allowed planning paths; exclude catalog/config/k8s |
| T-quick-03 | Elevation | accidental canary/live ops language | low | accept | Docs only; Phase 6 remains out of scope; no runtime changes |
| T-quick-SC | Tampering | package installs | low | accept | No package installs in this plan |
</threat_model>

<verification>
1. Structure: ROADMAP has Phase 0, 1, 2, 3A, 3B, 4, 5; Phase 6 canary noted out of scope.
2. Coverage script: count=138, unique=138, missing=0, duplicates=0.
3. Per-phase set equality between ROADMAP `**Requirements:**` lines and REQUIREMENTS Traceability.
4. Evidence-contract IDs present under Phase 2; prepare control-plane under 3A; co-commit writes under 3B.
5. `git status` shows no accidental staging of dirty unrelated paths.
</verification>

<success_criteria>
- Planning artifacts reconciled to canonical English roadmap phase spine
- Exactly 138 unique requirement mappings, zero orphans/duplicates
- v1.0 history and project safety constraints preserved
- No product code or unrelated dirty-tree changes
</success_criteria>

<output>
Create `.planning/quick/260717-wvz-reconcile-planning-roadmap-md-and-planni/260717-wvz-SUMMARY.md` when done
</output>
