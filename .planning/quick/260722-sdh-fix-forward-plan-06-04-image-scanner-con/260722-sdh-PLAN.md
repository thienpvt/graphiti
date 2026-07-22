---
phase: quick
plan: 260722-sdh
type: tdd
wave: 1
depends_on: []
files_modified:
  - scripts/catalog_image_secret_scanner.py
  - tests/script/test_catalog_image_secret_scanner.py
  - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-PREBIND-MATRIX-RECEIPT.json
  - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-BIND-RECEIPT.json
  - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-MATRIX-RECEIPT.json
  - .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-IMAGE-RECEIPT.json
autonomous: true
requirements:
  - P6-IMG-01
  - P6-IMG-02
  - P6-IMG-03
  - P6-IMG-04
  - P6-IMG-05
  - P6-BASE-02
  - P6-PRES-01
  - P6-PRES-03
  - P6-SAFE-01
  - P6-RT-00
  - P6-PROV-01
must_haves:
  truths:
    - "Deterministic image secret scanner distinguishes literal secret values from Python declarations/references; no whole-path or whole-dependency waivers"
    - "Live token prefixes remain fail-closed only for real token shapes; sk-ecdsa algorithm names and non-token sk-* strings do not hit"
    - "GRAPHITI_CATALOG_UUID_NAMESPACE live UUID assignment remains fail-closed"
    - "Scanner covers complete image FS, config JSON, history, build log, inspect output, layer metadata; unknown/unparseable trust-boundary text fails closed"
    - "Scanner source+tests committed before rebind; d54abe9 invalidated; full PREBIND→freeze→raw-Git BIND→frozen matrix on NEW candidate"
    - "Exactly one new candidate-bound image after new bind; zero secret hits; 06-IMAGE-RECEIPT.json written only then"
    - "Failed prior image graphiti-mcp:phase6-cleanroom-d54abe9d3d22-bound / sha256:94d50fcab6cb6e9accb137687e74d8a4ef79bebcb627b955e6f9ad70769a7673 preserved (no delete/retag)"
    - "Protected dirty mcp_server/config/config-docker-neo4j.yaml never staged/touched"
    - "No runtime, MCP, provider, namespace generation, identity allocation, or canary"
  artifacts:
    - path: scripts/catalog_image_secret_scanner.py
      provides: stdlib-only deterministic image secret scanner (AST + structured literals + fail-closed token shape)
    - path: tests/script/test_catalog_image_secret_scanner.py
      provides: RED/GREEN cases for literals vs declarations, sk-ecdsa non-hit, live token/UUID hits, unparseable fail-closed
    - path: .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-IMAGE-RECEIPT.json
      provides: new-candidate image tag/id, dual hashes, excluded_paths, secret_pattern_hits=0, scanner authority
  key_links:
    - from: scanner unit tests
      to: scripts/catalog_image_secret_scanner.py
      via: pytest RED→GREEN before rebind
    - from: committed scanner HEAD
      to: PREBIND → BIND → MATRIX
      via: source-complete matrix then freeze new candidate (not d54abe9)
    - from: new BIND.commit archive projection
      to: one docker build + complete image secret scan
      via: Plan 06-04 projection/denylist semantics; scanner replaces blind _assert_no_sensitive_values over full image FS
  prohibitions:
    - statement: MUST NOT delete/retag failed image sha256:94d50fcab6cb6e9accb137687e74d8a4ef79bebcb627b955e6f9ad70769a7673 or historical 35227e0 bound image
      status: planned
    - statement: MUST NOT stage or modify mcp_server/config/config-docker-neo4j.yaml
      status: planned
    - statement: MUST NOT build image before new candidate BIND+MATRIX green; MUST NOT write IMAGE receipt until scan hits==0
      status: planned
    - statement: MUST NOT edit Dockerfile/source during image-build step; source only in Task 1 before rebind
      status: planned
    - statement: MUST NOT start runtime/compose, allocate canary IDs, generate namespace, push, prune
      status: planned
---

<objective>
Fix-forward Plan 06-04 image secret-scan contract. TDD a deterministic stdlib scanner that classifies literal secret values (not Python declarations/references), keep full-image path + namespace UUID + live token-prefix gates, commit source/tests, re-run PREBIND/BIND/frozen matrix on a new candidate, build exactly one new candidate-bound image, require zero secret hits, write IMAGE receipt only on zero-hit.

Purpose: Prior 06-04 attempt built `graphiti-mcp:phase6-cleanroom-d54abe9d3d22-bound` (`sha256:94d50fca…`) once; labels/exclusions passed but blind `_assert_no_sensitive_values` over complete image source/deps produced hundreds of false positives (declarations/references + `sk-ecdsa-*` algorithm name). Scanner source change invalidates candidate `d54abe9` — full rebind required.

Output: `scripts/catalog_image_secret_scanner.py` + tests committed; new PREBIND/BIND/MATRIX receipts; one new image; `06-IMAGE-RECEIPT.json` with `secret_pattern_hits=0`. No runtime/canary.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-04-PLAN.md
@.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-03-PLAN.md
@.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-BIND-RECEIPT.json
@.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-MATRIX-RECEIPT.json
@mcp_server/tests/catalog_phase5_gate_runner.py
@scripts/catalog_raw_git_archive.py
@mcp_server/docker/Dockerfile.standalone

## Known failed image (preserve)
- tag: `graphiti-mcp:phase6-cleanroom-d54abe9d3d22-bound`
- id: `sha256:94d50fcab6cb6e9accb137687e74d8a4ef79bebcb627b955e6f9ad70769a7673`
- Prior candidate: `d54abe9d3d224367cb3a4eb989683a2860a9add2` (invalidated by scanner source)
- Do not delete, retag, prune, or reuse as the Plan-04 success image

## Historical image (preserve)
- `graphiti-mcp:phase6-35227e0a2c69-bound` / `sha256:994e1d1307dfd64ba0955a5e2469324721318a81514093b901fd853ad341d099`

## Protected overlay
- `mcp_server/config/config-docker-neo4j.yaml` remains dirty/unstaged; never stage, edit, or bake user overlay

## Scanner contract (authority for image secret scan)
- Replaces blind whole-image application of `_assert_no_sensitive_values` for image FS walk
- Semantics preserve fail-closed intent of that symbol for true secrets while parsing literals conservatively
- IMAGE receipt still records `scanner_authority_symbol` as the new public entrypoint (e.g. `scan_text` / `scan_path` / module-level documented symbol) plus blob/file hash of `scripts/catalog_image_secret_scanner.py` at NEW BIND.commit
- Optional note that prior authority was `_assert_no_sensitive_values` — do not hardcode line ranges as authority

## Out of scope
- Runtime / compose up / MCP tool calls / provider probes
- Namespace generation / canary ID allocation / canary execution
- Dockerfile or product source edits during image-build step
- Push, prune, historical retag
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED/GREEN deterministic image secret scanner + commit</name>
  <files>scripts/catalog_image_secret_scanner.py, tests/script/test_catalog_image_secret_scanner.py</files>
  <read_first>
    - mcp_server/tests/catalog_phase5_gate_runner.py symbol _assert_no_sensitive_values (assignment regex, placeholder set, namespace UUID pattern, token prefix pattern)
    - scripts/catalog_raw_git_archive.py (stdlib style, single-quote, no deps)
    - scripts/__init__.py
    - tests/script/ layout of existing script tests
  </read_first>
  <behavior>
    - Declaration/reference non-hit: Python text with names/attrs/params like password, api_key, access_token, client_secret, or string keys in non-literal positions must not raise when no secret literal value is assigned
    - Literal assignment hit: password/api_key/access_token/refresh_token/client_secret assigned a non-placeholder string literal must hit (Python AST Assign/AnnAssign/keyword defaults where value is Constant str)
    - Placeholder allowlist non-hit: empty, none, ollama, password, demodemo, your_password, your_openai_api_key_here, your_anthropic_key, your_gemini_key, your_groq_key, sk-xxxxxxxx, omitted, redacted, your_*, ${…}, &lt;…&gt;
    - OpenAI-like token shape hit: sk- followed by long alphanumeric token body (exclude algorithm names) must hit; ghp- and glpat- live shapes must hit
    - sk-ecdsa non-hit: algorithm identifier sk-ecdsa-… (or similar non-token sk- forms) must not hit; do not waive all sk-*
    - Namespace UUID hit: GRAPHITI_CATALOG_UUID_NAMESPACE = live UUID must hit
    - Config/metadata structured literals: YAML/JSON/env-like KEY=value and "password": "real" style structured/text literals hit; keys alone do not
    - Unparseable trust-boundary fail-closed: binary/non-UTF8 or deliberately unparseable secret-bearing boundary text raises safe failure (scan incomplete / unparseable), never silent pass
    - Path walker: scan_path/scan_tree over temp fixture tree returns hit counts + path classes only; never echoes secret values
    - Zero-hit clean fixture: representative source-like tree with declarations only returns hits==0
  </behavior>
  <action>
    Create stdlib-only module `scripts/catalog_image_secret_scanner.py` and focused tests `tests/script/test_catalog_image_secret_scanner.py`. No new dependency.

    Design rules:
    1. Python: use `ast` to extract only string Constant values in credential-like assignment/keyword contexts; ignore Name/Attribute/arg annotations/docstrings that merely mention credential identifiers. Do not waive entire files or vendor paths.
    2. Non-Python config/text: conservative structured/text literal extraction (JSON loads when valid; line-oriented KEY=VALUE / key: value for env/yaml-like; quoted values). Keys without secret values are non-hits.
    3. Live token prefixes: fail-closed for real shapes. OpenAI-like: require `sk-` + token body that is not an algorithm/name fragment — specifically reject false positive family exemplified by sk-ecdsa by requiring a longer high-entropy alphanumeric body (document exact regex in module constants and tests). Keep `ghp-` and `glpat-` live patterns. Do not ignore all sk-*.
    4. Keep GRAPHITI_CATALOG_UUID_NAMESPACE live UUID pattern fail-closed (same spirit as gate runner).
    5. Public API minimum: pure functions such as `scan_text(text, *, label, path_hint=None) -> ScanResult` and `scan_tree(root) -> ScanResult` (names may vary; document one stable authority symbol for IMAGE receipt). ScanResult exposes hit_count, path_classes (or equivalent), and never stores raw secret substrings.
    6. Fail closed on unknown/unparseable content at trust boundaries (image config JSON, history JSON, exported text files under scan roots). Binary blobs: either skip only with explicit binary classification recorded, or fail closed — choose fail-closed for text-claimed paths; document binary handling in module docstring.
    7. CLI optional: `python -m` / `if __name__` path that prints only counts/classes/exit code (no secret values). Not required for tests.

    TDD order: write failing tests first (RED), implement minimal scanner (GREEN), keep tests green. Match repo style: single quotes, line length 100, ruff-clean.

    After green: commit ONLY task-owned source+tests atomically (scanner + test file). Do not stage protected config, planning receipts, Dockerfile, or unrelated dirt. Commit message style: `feat(catalog): add deterministic image secret scanner`. Do not amend. Do not write IMAGE/BIND/MATRIX in this task.
  </action>
  <verify>
    <automated>python -m pytest tests/script/test_catalog_image_secret_scanner.py -q --tb=line</automated>
  </verify>
  <done>Scanner + tests green and committed; d54abe9 no longer valid candidate; protected config still unstaged; no image built yet.</done>
</task>

<task type="auto">
  <name>Task 2: PREBIND + freeze new candidate + raw-Git BIND + frozen matrix</name>
  <files>.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-PREBIND-MATRIX-RECEIPT.json, .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-BIND-RECEIPT.json, .planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-MATRIX-RECEIPT.json</files>
  <read_first>
    - 06-03-PLAN.md Task 1–2 recipes (PREBIND then freeze/BIND/MATRIX)
    - existing 06-PREBIND-MATRIX-RECEIPT.json / 06-BIND-RECEIPT.json / 06-MATRIX-RECEIPT.json field shapes
    - scripts/catalog_raw_git_archive.py
    - git status / git rev-parse HEAD after Task 1 commit
  </read_first>
  <action>
    Scanner commit invalidates candidate d54abe9. Re-run full Plan-03 bind chain for a NEW candidate. Never amend d54abe9. Never rebuild image in this task.

    PREBIND:
    1. Assert Task-1 scanner+tests are committed; capture tested_source_head = HEAD.
    2. Assert protected dirty config-docker-neo4j.yaml remains unstaged and unmodified by this task.
    3. Run source-complete offline matrix equivalent to 06-03 Task 1: focused harness + Phase5 compatibility + catalog union checks used previously + raw-git archive suite + ruff/format/pyright/compile for touched paths + `tests/script/test_catalog_image_secret_scanner.py`. Zero unexplained skips. Do not weaken gates.
    4. Write 06-PREBIND-MATRIX-RECEIPT.json (overwrite/update) with tested_source_head, classification SOURCE_COMPLETE_GREEN (or equivalent green), image_build_count=0, candidate_frozen=false, note fix-forward after scanner. Include harn_checklist P6-HARN-01..19 map (offline green or deferred_* with evidence). Executor may commit PREBIND with docs separately from source.

    FREEZE + BIND + MATRIX:
    5. Freeze candidate_sha = HEAD after PREBIND commit lands (must include scanner source/tests; may include PREBIND docs per P6-BIND-01). Record parent/tree. This SHA must NOT be d54abe9.
    6. Materialize exact raw-Git archive of candidate_sha via catalog_raw_git_archive into `$CLAUDE_JOB_DIR/tmp/phase6-fixfwd-bind-*` only. blob_mismatch_count must be 0.
    7. Re-run frozen matrix from that archive authority (same categories as 06-03 frozen matrix; include scanner unit tests). Require classification READY_FOR_IMAGE_BINDING.
    8. Write 06-BIND-RECEIPT.json and 06-MATRIX-RECEIPT.json for the NEW commit. Record failed_candidate_commit=d54abe9… (or prior failed) with failed_candidate_preserved=true; fix_forward_commit=new SHA; image_build_count=0; runtime_start_count=0; canary_ids_allocated=false; canary_executed=false; protected_config_status remains modified_unstaged. MATRIX.commit == BIND.commit. archive_context_sha256 from raw-Git formula.
    9. Do not build Docker image. Do not start runtime. Do not stage protected config. Planning receipts commit separately from source if needed.
  </action>
  <verify>
    <automated>python -c "import json,subprocess; b=json.load(open('.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-BIND-RECEIPT.json')); m=json.load(open('.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-MATRIX-RECEIPT.json')); p=json.load(open('.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-PREBIND-MATRIX-RECEIPT.json')); assert m['classification']=='READY_FOR_IMAGE_BINDING'; assert b['blob_mismatch_count']==0 and m['commit']==b['commit']; assert b['commit']!='d54abe9d3d224367cb3a4eb989683a2860a9add2'; assert b.get('image_build_count',0)==0 and m.get('image_build_count',0)==0; assert b.get('canary_executed') is False; head=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(); st=subprocess.check_output(['git','status','--porcelain','--','mcp_server/config/config-docker-neo4j.yaml'], text=True); assert 'scripts/catalog_image_secret_scanner.py' in subprocess.check_output(['git','ls-tree','-r','--name-only',b['commit']], text=True); print('new-bind', b['commit'][:12], 'head', head[:12], 'prebind', p.get('classification'), 'protected', st.strip()[:40])"</automated>
  </verify>
  <done>New candidate bound exact; MATRIX READY_FOR_IMAGE_BINDING; scanner in candidate tree; d54abe9 not reused; no image yet.</done>
</task>

<task type="auto">
  <name>Task 3: One new filtered image + complete scanner zero-hit + IMAGE receipt</name>
  <files>.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-IMAGE-RECEIPT.json</files>
  <read_first>
    - 06-04-PLAN.md Task 2 projection/denylist/label/receipt fields
    - NEW 06-BIND-RECEIPT.json / 06-MATRIX-RECEIPT.json
    - scripts/catalog_image_secret_scanner.py (committed at BIND.commit)
    - mcp_server/docker/Dockerfile.standalone (read-only; no edit)
  </read_first>
  <action>
    Execute Plan 06-04 image half against NEW BIND.commit only. No source/Dockerfile edits in this task. One image only.

    Preconditions: MATRIX.classification==READY_FOR_IMAGE_BINDING; BIND.blob_mismatch_count==0; MATRIX.commit==BIND.commit; BIND.commit != d54abe9…. If fail: HARD_BLOCKED, no build.

    1. candidate_sha = BIND.commit; archive_context_sha256 = BIND.archive_context_sha256. Never substitute HEAD if it differs after receipt commits.

    2. Materialize exact archive of candidate_sha under `$CLAUDE_JOB_DIR/tmp/phase6-image-archive-*`. Confirm committed baseline config path present in archive. Do not read/alter dirty worktree config overlay.

    3. Build deterministic filtered projection under `$CLAUDE_JOB_DIR/tmp/phase6-image-projection-*` using only archive bytes + fixed denylist (config-docker-neo4j.yaml, .env/secrets, namespace authority, local Catalog-v2 config, runtime evidence, entire .planning/**). Record projection manifest + build_context_sha256 + excluded_paths. Docker context = projection only, never full archive root.

    4. docker build -f mcp_server/docker/Dockerfile.standalone --pull=false. Tag: graphiti-mcp:phase6-cleanroom-&lt;first-12-of-BIND.commit&gt;-bound. Labels only via --label / build-arg: org.opencontainers.image.revision=BIND.commit; org.graphiti.source-context-sha256=FULL BIND.archive_context_sha256. No Dockerfile edit. If labels require Dockerfile change: HARD stop.

    5. Inspect: Labels match; new image id recorded. Assert failed prior image sha256:94d50fca… still present and not retagged to the new tag. Assert historical 35227e0 bound image identity preserved. Do not prune/delete either.

    6. Exclusion proofs: denylisted paths absent from projection and image FS/layers; committed baseline config still in archive authority.

    7. Exhaustive secret scan with NEW scanner (not blind gate-runner regex over whole tree):
       - Export complete image FS + config JSON + history + layer tar metadata under `$CLAUDE_JOB_DIR/tmp/phase6-image-scan-*`
       - Also scan build log and inspect output
       - secret_scan_scope must be complete_image_fs_config_history
       - scanner_authority_path = scripts/catalog_image_secret_scanner.py
       - scanner_authority_symbol = public entrypoint name
       - scanner_authority_blob_sha1 and/or file_sha256 of that file at BIND.commit
       - Combine with fixed path denylist on exported paths
       - Never harvest host env/secrets for comparison; never write secret values into receipts/logs — counts + path classes only
       - Fail closed if any hit OR incomplete scope OR unparseable trust-boundary text
       - Do NOT write 06-IMAGE-RECEIPT.json until secret_pattern_hits==0

    8. On zero hits only: write 06-IMAGE-RECEIPT.json with tag, image_id, commit=BIND.commit, revision=BIND.commit, source_context_label_key, source_context_sha256, archive_context_sha256, build_context_sha256, projection manifest digest, excluded_paths, exclusion proofs, secret_scan_scope, scanner authority fields, secret_pattern_hits=0, docker_pull_flag=--pull=false, push_performed=false, historical_retag=false, prior_failed_image_id=sha256:94d50fca…, prior_failed_image_preserved=true, optional head_at_build audit. Never commit `$CLAUDE_JOB_DIR/tmp/**`. No compose up, no push, no prune, no protected-config touch.

    9. If scan non-zero: leave image as additional failed candidate artifact (do not delete); do not write success IMAGE receipt; stop HARD with hit counts/path classes only — no secret values.
  </action>
  <verify>
    <automated>python -c "import json,subprocess; b=json.load(open('.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-BIND-RECEIPT.json')); r=json.load(open('.planning/phases/06-catalog-v2-phase-6-tdd-to-canary-clean-room-closure/06-IMAGE-RECEIPT.json')); assert r['tag'].startswith('graphiti-mcp:phase6-cleanroom-') and r['tag'].endswith('-bound'); assert r['commit']==b['commit']==r['revision']; assert r['commit']!='d54abe9d3d224367cb3a4eb989683a2860a9add2'; assert r['source_context_sha256']==b['archive_context_sha256']==r['archive_context_sha256']; assert r.get('secret_scan_scope')=='complete_image_fs_config_history'; assert 'catalog_image_secret_scanner' in str(r.get('scanner_authority_path','')); assert r.get('scanner_authority_symbol'); assert r.get('scanner_authority_blob_sha1') or r.get('scanner_authority_file_sha256'); assert r.get('secret_pattern_hits',1)==0; assert r.get('push_performed') is False and r.get('historical_retag') is False; assert r.get('prior_failed_image_preserved') is True; assert r.get('excluded_config_absent_in_image') is True; st=subprocess.check_output(['git','status','--porcelain','--','mcp_server/config/config-docker-neo4j.yaml'], text=True); print(r['tag'], r['image_id'][:19], 'bind', r['commit'][:12], 'hits', r['secret_pattern_hits'], 'protected', bool(st.strip()))"</automated>
  </verify>
  <done>Exactly one new candidate-bound image; complete scan zero-hit; IMAGE receipt green; failed d54abe9 image preserved; no runtime/canary; protected config untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Image export → scanner | Untrusted complete FS/config/history; scanner must fail closed |
| Scanner classification | Declaration vs literal; token shape vs algorithm name |
| Archive → projection → Docker | Only archive bytes + fixed denylist; no dirty overlay |
| Local image tags | Failed and historical tags must not be overwritten |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-sdh-01 | Information Disclosure | image layers | high | mitigate | complete FS/config/history scan via deterministic scanner; path denylist; hits==0 required before IMAGE receipt; never log secret values |
| T-sdh-02 | Spoofing | token false-negative | high | mitigate | fail-closed live token shapes (sk- OpenAI-like, ghp-, glpat-) + namespace UUID; tests lock shapes |
| T-sdh-03 | Denial of Service / noise | false-positive flood | medium | mitigate | AST/literal classification; sk-ecdsa non-hit; no whole-path waivers |
| T-sdh-04 | Spoofing | candidate identity | high | mitigate | new PREBIND/BIND/MATRIX; image revision=BIND.commit not HEAD; d54abe9 invalidated |
| T-sdh-05 | Tampering | failed/historical images | high | mitigate | no delete/retag of 94d50fca… or 994e1d13… |
| T-sdh-06 | Information Disclosure | dirty config overlay | high | mitigate | never stage/bake config-docker-neo4j.yaml; denylist in projection |
| T-sdh-SC | Tampering | packages | high | mitigate | no new package installs; stdlib scanner only |
</threat_model>

<verification>
- pytest scanner suite green
- New BIND != d54abe9; MATRIX READY_FOR_IMAGE_BINDING
- One new image; secret_pattern_hits=0; IMAGE receipt present
- Failed prior image preserved; protected config still dirty/unstaged
- No runtime/canary/IDs
</verification>

<success_criteria>
1. Deterministic scanner distinguishes literals from declarations/references with tests
2. Live token + namespace UUID fail-closed; sk-ecdsa non-hit without waiving all sk-*
3. Source/tests committed; full PREBIND→BIND→MATRIX on new candidate
4. Exactly one new candidate-bound image after rebind; zero secret hits
5. 06-IMAGE-RECEIPT.json written only on zero-hit complete scan
6. Failed image 94d50fca… and historical 994e1d13… preserved
7. Protected config-docker-neo4j.yaml never staged
8. No runtime, MCP, provider, namespace, identity, or canary
</success_criteria>

<output>
Create `.planning/quick/260722-sdh-fix-forward-plan-06-04-image-scanner-con/260722-sdh-SUMMARY.md` when done
</output>
