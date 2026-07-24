# Phase 6 Native Ollama Terminal Report (shell)

**status:** TERMINAL_PASSED
**classification:** PASSED
**canary_executed:** true
**canary_ids_allocated:** true
**freeze_receipt_written:** true

## Authority

| Item | Value |
|------|-------|
| bind commit | `da8dce8e0d2719953405e33f9fbe2bd8b863662c` |
| source context | `5284da1bc2587178eb31f8f21b108f3bf9baaf61db8d569d8026aedc9438f163` |
| image ID | `sha256:85775ff1ead67b2b292ed171373ce496f2cdd83141528831d813a9f6668fc847` |
| project | `graphiti-phase6-cleanroom-a75e295d` |
| namespace fingerprint | `36d75a3ff057e090` |
| config fingerprint | `6550d751de6d2373506b0a1d64be6cdba9ef08f74d90d073d57cb07f31735633` |

## Runtime gates

| Gate | Result |
|------|--------|
| R0 | GREEN — fresh resources absent before creation; exact bound image selected |
| R1 | GREEN — Neo4j-only authority; MCP absent |
| R2 | GREEN — first inspection `0/14`; one bootstrap; first postflight `14/14`; retry count `0` |
| R3 | GREEN — Compose MCP healthy; image match; 28 tools; ollama/qwen3-embedding:0.6b/1024/ready; waiver null |
| Prefreeze | COMMITTED under 06-OLLAMA-* |
| Freeze | APPROVED — HEAD `9f0199808ede02c07f60292e002f428f87d3db94`, count `1636` |
| Final canary | PASSED — Gates 0–10; zero LLM; null waiver |

## Live markers

<!-- phase6-final-canary-live:start -->
- Classification: `PASSED`
- Run ID: `20260724t001855z-20d91c7c`
- Group ID: `oracle-catalog-v2-canary-20260724t001855z-20d91c7c`
- Control group ID: `oracle-catalog-v2-canary-20260724t001855z-20d91c7c-empty-control`
- Batch ID: `accept-tab-catalog-v2-canary-20260724t001855z-20d91c7c`
- Counts: `{"edges": 2, "entities": 3, "evidence_links": 5, "sources": 1}`
- Dry-run zero-write proven: `true`
- Replay: `skipped`
- Tool calls: `37`
- Final ordinal: `37`
- AUTH-01: `{"canary_invocation_count": 1, "deployment_applied": false, "historical_group_ids_used": false, "kubernetes_applied": false, "mode": "iterative_tdd_plus_one_final_clean_room_canary", "second_canary": false}`
- Stack preserved: `true`
<!-- phase6-final-canary-live:end -->

## Counts

| Operation | Count |
|-----------|------:|
| Canary identity allocation | 1 |
| Final-canary launcher invocation | 1 |
| Dry-run `upsert_catalog_batch` | 1 |
| `prepare_catalog_batch` | 1 |
| `commit_prepared_catalog_batch` | 1 |
| Committed catalog batch | 1 |
| Cleanup operations | 0 |

## Preservation

- Historical OpenAI-path evidence and stack remain unchanged.
- Prior failed Ollama project `graphiti-phase6-cleanroom-d19a171e` remains intact.
- Final project containers, network, and volumes remain running after terminal success.
- Protected user-owned config remains modified, unstaged, and uncommitted.
- No deployment, Kubernetes action, graph clear, data deletion, prune, or volume removal occurred.
- No raw namespace, credential, token, vector, full environment, raw endpoint, or sensitive endpoint parameter is recorded here.

## Terminal verification

- Gates 0–10: all pass.
- Exact dry run: 3 entities / 2 edges / 1 source / 5 evidence links; zero-write proven.
- Prepare count: 1. Token-only commit count: 1. Commit confirmed. Retry count: 0.
- Manifest, typed entity/edge resolution, five evidence links, node/fact search, control isolation: verified.
- Embeddings: ollama / qwen3-embedding:0.6b / 1024 / ready; waiver false; config fingerprint matched freeze.
- Protected groups queried: none. Prohibited tools called: none. Secrets persisted: false.
- Source HEAD and commit count remained frozen. Stack preserved. No cleanup.

## Disposition

Exactly one native-Ollama final canary passed. Run `20260724t001855z-20d91c7c`; terminal evidence remains uncommitted. No second canary. No GSD executor resume. No verify/complete/tag/cleanup lifecycle.
