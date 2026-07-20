---
phase: 1
slug: strict-contracts-and-catalog-v2-identity
status: in_progress
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
updated: 2026-07-18
---

# Phase 1 — Validation Strategy

> Current-HEAD commands are serialized argv contracts. Each command is decoded with `json.loads` and executed from repository root using `subprocess.run(argv, shell=False)`. Historical TDD failures are ancestry evidence only.
>
> `nyquist_compliant: true` derived only from verified Plan 01-11 runner apply on a complete green local ledger. Independent audits remain pending; `ready_for_phase_2` stays false.
>
> **2026-07-18 evidence refresh:** Plans 01-09 and 01-10 closed CR-02/WR-01 and CR-01/WR-02 respectively. Rows below include 01-09/01-10/01-11 current-HEAD argv contracts. Local readiness may flip only via verified runner apply; final readiness stays false while independent audits are pending.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `mcp_server/pytest.ini` |
| **Execution authority** | JSON `argv` arrays below; never display strings or shell parsing |
| **Expected exit** | Exactly integer `0` for every current-HEAD row |
| **Neo4j integration** | `skip` — Phase 1 unit policy; availability not probed |

## Per-Task Current-HEAD Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Expected Files | Status |
|---------|------|------|-------------|-----------|-------------------|----------------|--------|
| 01-01-T1 | 01-01 | 1 | CONT-01..06, CONT-08, IDEN-01, IDEN-02, TEST-01 | focused behavior | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","-k","strict or extra or misspel or strict_endpoints or atomic or identity_schema or system_key or preserve or trailing or error_code or order_preserv","-q","--tb=line"],"expected_exit":0}` | `mcp_server/tests/test_catalog_models.py` | green |
| 01-01-T2 | 01-01 | 1 | CONT-01..06, CONT-08, IDEN-01, IDEN-02, TEST-01 | unit | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","-q","--tb=line"],"expected_exit":0}` | catalog model source + tests | green |
| 01-02-T1 | 01-02 | 2 | IDEN-03..06, IDEN-08, IDEN-09, IDEN-12 | focused behavior | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","-k","grammar or overload or system_mismatch or v1_key or catalog_v1 or graph_key_echo","-q","--tb=line"],"expected_exit":0}` | `mcp_server/tests/test_catalog_models.py` | green |
| 01-02-T2 | 01-02 | 2 | IDEN-03..06, IDEN-08, IDEN-09, IDEN-12 | unit | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","-q","--tb=line"],"expected_exit":0}` | graph-key model source + tests | green |
| 01-03-T1 | 01-03 | 3 | IDEN-07, IDEN-08, IDEN-10, IDEN-11, IDEN-13, SAFE-05, TEST-03 | focused behavior | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_identity.py","mcp_server/tests/test_catalog_service.py","-k","uuid or catalog_v2 or graph_key_echo or overload or fe_bo or accept_tab","-q","--tb=line"],"expected_exit":0}` | identity + service tests | green |
| 01-03-T2 | 01-03 | 3 | IDEN-07, IDEN-08, IDEN-10, IDEN-11, IDEN-13, SAFE-05, TEST-03 | unit | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_identity.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","-q","--tb=line"],"expected_exit":0}` | identity source + tests | green |
| 01-04-T1 | 01-04 | 4 | CONT-07, SAFE-08 | focused behavior | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_service.py","-k","structured_error or no_side_effect or never_call or typed_pydantic or production_boundary","-q","--tb=line"],"expected_exit":0}` | model + service tests | green |
| 01-04-T2 | 01-04 | 4 | CONT-07, SAFE-08 | unit | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_identity.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","-q","--tb=line"],"expected_exit":0}` | converter, MCP boundary, tests | green |
| 01-05-T1 | 01-05 | 5 | TEST-01, TEST-03 | gate structure | `{"argv":["uv","run","--project","mcp_server","python","-c","from pathlib import Path; import re; t=Path('.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-PHASE1-GATE.md').read_text(encoding='utf-8'); required=('focused_pytest','scoped_ruff','scoped_pyright','catalog_neo4j_int','safety_invariants','edge_probe','ready_for_phase_2','canary_executed','oracle_catalog_v2_queried','no_new_store_or_control_plane_write_path'); pairs=re.findall(r'(?m)^([a-z0-9_]+)=(pass|fail|skip|true|false|\\d+)$',t); keys=[k for k,_ in pairs]; assert all(keys.count(k)==1 for k in required); vals=dict(pairs); assert vals['catalog_neo4j_int']=='skip' and vals['canary_executed']=='false' and vals['oracle_catalog_v2_queried']=='false' and vals['ready_for_phase_2'] in ('true','false')"],"expected_exit":0}` | `01-PHASE1-GATE.md` | green |
| 01-05-T2 | 01-05 | 5 | all Phase 1 edge probes | edge structure | `{"argv":["uv","run","--project","mcp_server","python","-c","import json; from pathlib import Path; d=json.loads(Path('.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-EDGE-PROBE.json').read_text(encoding='utf-8')); items=d['items']; c=d['coverage']; assert len(items)==53 and all(i['status']=='resolved' and i['verification']=='explicit' and i.get('resolution') for i in items); assert c['applicable']==c['resolved']==53 and c['unresolved']==0 and c['byVerification']=={'explicit':53,'backstop':0} and c['no_silent_drop']=={'source_count':53,'resolved_count':53,'key_equality':True,'null_dispositions':0}"],"expected_exit":0}` | `01-EDGE-PROBE.json` | green |

## Gap-Closure Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Expected Files | Status |
|---------|------|------|-------------|-----------|-------------------|----------------|--------|
| 01-06-T1 | 01-06 | 6 | strict contract audit gaps | focused behavior | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","-k","source_ref or strict_true or empty_resolve or invalid_system_key or graph_key_mismatch","-q","--tb=line"],"expected_exit":0}` | model, service, store tests | green |
| 01-06-T2 | 01-06 | 6 | CONT-01/02/04/05/06/07, IDEN-01..05, SAFE-08 | regression | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_store_unit.py","-q","--tb=line"],"expected_exit":0}` | Plan 01-06 source + tests | green |
| 01-07-T1 | 01-07 | 7 | SAFE-08 logging + nine probes | focused behavior | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_edge_probe.py","-k","catalog_logger or catalog_resolve_logs or catalog_status_logs or catalog_wrapper_failure_logs or edge_probe","-q","--tb=line"],"expected_exit":0}` | service + edge-probe tests | green |
| 01-07-T2 | 01-07 | 7 | CONT-01/02/07, IDEN-01/02/04/05, SAFE-08 | regression | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_edge_probe.py","-q","--tb=line"],"expected_exit":0}` | logging source + tests | green |
| 01-08-T1 | 01-08 | 8 | exact 138-ID ownership | structural | `{"argv":["uv","run","--project","mcp_server","python","-c","import re; from collections import Counter; from pathlib import Path; req=Path('.planning/REQUIREMENTS.md').read_text(encoding='utf-8'); road=Path('.planning/ROADMAP.md').read_text(encoding='utf-8'); defs=re.findall(r'^\\s*-\\s*\\[[ x]\\]\\s*\\*\\*([A-Z]{4}-\\d{2})\\*\\*:',req,re.M); rows=re.findall(r'^\\|\\s*([A-Z]{4}-\\d{2})\\s*\\|\\s*(Phase\\s+(?:0|1|2|3A|3B|4|5))\\s*\\|',req,re.M); ids=[i for i,_ in rows]; expected={'Phase 0':8,'Phase 1':23,'Phase 2':34,'Phase 3A':18,'Phase 3B':17,'Phase 4':21,'Phase 5':17}; assert len(defs)==len(set(defs))==len(rows)==len(set(ids))==138 and set(defs)==set(ids); assert Counter(p for _,p in rows)==Counter(expected); mapping=dict(rows); assert mapping['IDEN-08']=='Phase 4' and mapping['IDEN-13']=='Phase 5'; sections=list(re.finditer(r'(?m)^### (Phase (?:0|1|2|3A|3B|4|5)):',road)); road_by={m.group(1):set(re.findall(r'\\b([A-Z]{4}-\\d{2})\\b',re.search(r'(?m)^\\*\\*Requirements\\*\\*:\\s*(.+)$',road[m.end():sections[j+1].start() if j+1<len(sections) else len(road)]).group(1))) for j,m in enumerate(sections)}; req_by={p:{i for i,q in rows if q==p} for p in expected}; assert road_by==req_by and sum(map(len,road_by.values()))==138; assert re.search(r'Mapped:\\s*138/138',road) and re.search(r'Orphans:\\s*0',road) and re.search(r'Duplicates:\\s*0',road)"],"expected_exit":0}` | REQUIREMENTS + ROADMAP | green |
| 01-08-T2 | 01-08 | 8 | validation, probes, ASVS ledger | structural | `{"argv":["uv","run","--project","mcp_server","python","-c","import json,re; from pathlib import Path; base=Path('.planning/phases/01-strict-contracts-and-catalog-v2-identity'); v=(base/'01-VALIDATION.md').read_text(encoding='utf-8'); tick=chr(96); pattern=r'^\\| (01-(?:0[1-9]|1[0-1])-T\\d+) \\|.*?\\| '+tick+r'([^'+tick+r']+)'+tick+r' \\|'; rows=re.findall(pattern,v,re.M); ids=[i for i,_ in rows]; assert len(rows)>=17 and len(ids)==len(set(ids)); legacy=[i for i in ids if i.startswith('01-0') and int(i[3:5])<=8]; assert len(legacy)==17; specs=[json.loads(raw) for _,raw in rows]; assert all(set(s)=={'argv','expected_exit'} and type(s['expected_exit']) is int and s['expected_exit']==0 and isinstance(s['argv'],list) and s['argv'] and all(isinstance(a,str) and a for a in s['argv']) for s in specs); d=json.loads((base/'01-EDGE-PROBE.json').read_text(encoding='utf-8')); assert len(d['items'])==53 and all(i['status']=='resolved' and i['verification']=='explicit' and i.get('resolution') for i in d['items']); sec=(base/'01-SECURITY.md').read_text(encoding='utf-8'); assert re.search(r'(?m)^threats_open:\\s*0\\s*$',sec) and 'T-01-14' in sec and 'T-01-18' in sec and 'T-01-SC' in sec; assert not re.search(r'user (?:approved|accepted|acceptance)',sec,re.I)"],"expected_exit":0}` | VALIDATION + EDGE-PROBE + SECURITY | green |
| 01-08-T3 | 01-08 | 8 | fail-closed runner propagation | harness | `{"argv":["uv","run","--project","mcp_server","python","-c","import subprocess,sys; argv=[sys.executable,'-c','assert False']; result=subprocess.run(argv,shell=False); assert argv[2]=='assert False' and result.returncode!=0"],"expected_exit":0}` | in-memory runner contract | green |
| 01-09-T1 | 01-09 | 9 | CONT-08, SAFE-08 | focused CR-02/WR-01 | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_service.py","-k","gap_cr02 or gap_wr01","-q","--tb=line"],"expected_exit":0}` | model + service gap nodes | green |
| 01-09-T2 | 01-09 | 9 | CONT-08, IDEN-03/04, SAFE-08 | regression | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_models.py","mcp_server/tests/test_catalog_service.py","-q","--tb=line"],"expected_exit":0}` | provenance + graph-key sources | green |
| 01-10-T1 | 01-10 | 10 | CONT-07, IDEN-07, SAFE-08 | focused CR-01/WR-02 | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_store_unit.py","mcp_server/tests/test_catalog_service.py","mcp_server/tests/test_catalog_neo4j_fixtures.py","-k","gap_cr01 or gap_wr02","-q","--tb=line"],"expected_exit":0}` | store + service + fixtures | green |
| 01-10-T2 | 01-10 | 10 | TEST-01, TEST-03 | pure fixture unit | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_neo4j_fixtures.py","-q","--tb=line"],"expected_exit":0}` | `catalog_neo4j_fixtures.py` | green |
| 01-11-T1 | 01-11 | 11 | TEST-01, TEST-03 | gate runner self-test | `{"argv":["uv","run","--project","mcp_server","python","-m","pytest","-c","mcp_server/pytest.ini","mcp_server/tests/test_catalog_phase1_gate_runner.py","-q","--tb=short"],"expected_exit":0}` | gate runner + tests | green |
| 01-11-T2 | 01-11 | 11 | no-silent-drop CR/WR | structural | `{"argv":["uv","run","--project","mcp_server","python","-c","from pathlib import Path; import re; t=Path('.planning/phases/01-strict-contracts-and-catalog-v2-identity/01-REVIEW-GAPS.md').read_text(encoding='utf-8'); keys=re.findall(r'^### (CR-0[12]|WR-0[12])',t,re.M); assert keys==['CR-01','CR-02','WR-01','WR-02'] and 'key_equality = true' in t and 'silent_drops = 0' in t"],"expected_exit":0}` | `01-REVIEW-GAPS.md` | green |

## Historical RED Evidence

These ancestry commits prove the historical RED gates. They are not current-HEAD commands and never invert a current return code:

| Plan | Historical RED commit | Purpose |
|------|-----------------------|---------|
| 01-01 | `2ce9697` | Strict request contracts RED |
| 01-02 | `7ed00e5` | Graph-key grammar RED |
| 01-03 | `af1eadf` | Versioned identity RED |
| 01-04 | `bd84cc3` | Structured errors and typed boundary RED |
| 01-05 | `f66d5a3` | Hard-gate RED evidence |
| 01-09 | `f3843e9` | CR-02/WR-01 provenance and graph-key locations RED |
| 01-10 | `fd4c65f` | CR-01/WR-02 entity race and fixtures RED |

## Execution Rules

- Decode each backtick payload with `json.loads`; require exactly `argv` and `expected_exit`.
- Pass `argv` directly to `subprocess.run(..., shell=False, cwd=repo_root)`.
- Reject shell executables, standalone shell-control/redirection elements, malformed argv, nonzero real results, and historical return-code inversion programs.
- Do not infer row success from a broader suite.
- The deliberate runner propagation sentinel expects nonzero internally, but its enclosing row exits zero only after proving propagation.

## Validation Sign-Off

- [x] Every current-HEAD row executed successfully with `shell=False` by Plan 01-11 runner.
- [x] Nine exact edge-probe nodes remain in suite; gap anchors updated for CR/WR.
- [x] CR-01, CR-02, WR-01, WR-02 mapped once in `01-REVIEW-GAPS.md` with no silent drop.
- [x] Plan 01-08 historically derived `nyquist_compliant: true` from its then-complete green evidence.
- [x] Current Nyquist compliance derived true from verified local green ledger; independent audits still pending.

**Approval:** local Nyquist true via verified runner apply on 2026-07-18. Independent code/goal/Nyquist/security audits remain pending; no independent verdict claimed; `ready_for_phase_2=false`.
