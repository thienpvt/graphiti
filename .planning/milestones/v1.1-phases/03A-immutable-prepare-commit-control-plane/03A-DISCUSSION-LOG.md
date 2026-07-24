# Phase 3A: Immutable Prepare/Commit Control Plane - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves alternatives considered.

**Date:** 2026-07-18
**Phase:** 3A-immutable-prepare-commit-control-plane
**Mode:** `--auto`; recommended options selected under standing user approval
**Areas discussed:** Prepared artifact representation, Opaque token and lifecycle, Prepare validation and projection, Compatibility and Phase 3A gate

---

## Prepared Artifact Representation

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded plan root plus chunks | Complete canonical artifact stored in deterministic bounded non-Entity control records | ✓ |
| Single large plan node | Simpler, but unsafe against Neo4j/property and payload ceilings | |
| External object storage | Adds infrastructure and new failure/authorization boundary | |

**Auto-selected choice:** Bounded plan root plus ordered immutable chunks.
**Notes:** Hashes/counts alone cannot support token-only external-call-free commit. Hard-stop if Neo4j cannot prove safe immutable bounded storage.

---

## Opaque Token and Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| One-time opaque token + digest | `secrets` token, domain-separated digest only, timing-safe compare | ✓ |
| Signed self-contained token | Exposes/repeats artifact authority client-side and complicates revocation | |
| Deterministic plan ID token | Predictable; violates opaque high-entropy contract | |

**Auto-selected choice:** One-time opaque token; persist digest only.
**Notes:** Explicit PREPARED/COMMITTING/COMMITTED/DISCARDED/EXPIRED CAS state machine; no terminal revival.

---

## Prepare Validation and Projection

| Option | Description | Selected |
|--------|-------------|----------|
| Full preflight + embeddings first | Freeze complete validated identities, membership, projections, and embeddings before persistence | ✓ |
| Defer conflicts to commit | Allows prepared artifacts that cannot safely commit | |
| Persist first, enrich later | Embedding failure could strand partial plans | |

**Auto-selected choice:** Complete preflight and external precomputation before plan transaction.
**Notes:** Commit accepts token plus optional expected request hash only; no replacement payload or external calls.

---

## Compatibility and Phase 3A Gate

| Option | Description | Selected |
|--------|-------------|----------|
| Additive preferred path | Preserve direct batch upsert and zero-write dry-run; add three tools | ✓ |
| Replace direct batch upsert | Unnecessary compatibility break | |
| Deprecate immediately | Premature before Phase 3B domain commit is complete | |

**Auto-selected choice:** Additive tools; advertise support only after contract gate passes.
**Notes:** Prepare writes control-plane state only. Phase 3B remains blocked until token, immutability, restart, limits, and zero-domain-write proofs pass.

---

## Claude's Discretion

- Conservative configured/hard numeric ceilings after Neo4j research.
- UTF-8 canonical JSON versus base64 artifact encoding.
- Exact fixed control labels/property names and chunk identities.
- Deterministic stranded-COMMITTING recovery mechanism compatible with Phase 3B atomic finalization.
- Minimal module split preserving current service/store/MCP patterns.

## Deferred Ideas

- Atomic domain/evidence/manifest/terminal-state co-commit — Phase 3B.
- Manifest/evidence diagnostics and verification — Phase 4.
- Operational retention/metrics/migration docs — Phase 5 unless required for correctness.
- Canary or `oracle-catalog-v2` access — separate Phase 6 approval.
