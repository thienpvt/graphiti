"""Pure prepared-artifact serialization, chunking, and reassembly.

No network, Neo4j, embedder, LLM, or queue imports.
Token mint/digest lives in catalog_identity (single ownership); this module
never accepts or embeds raw plan tokens.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from typing import Any

PREPARED_ARTIFACT_SERIALIZATION_VERSION = 'prepared-artifact-v1'
DEFAULT_CHUNK_BYTES = 131_072
HARD_CHUNK_BYTES = 262_144
MAX_CHUNKS_PER_PLAN = 128

# Forbidden inside hashed body (digest is external to serialized bytes).
_FORBIDDEN_SELF_HASH_KEYS = frozenset({'artifact_sha256'})


def _reject_non_finite(obj: Any) -> None:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError('non-finite number')
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_non_finite(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_non_finite(v)


def serialize_prepared_artifact(body: dict[str, Any]) -> bytes:
    """Serialize prepared-artifact-v1 body to canonical UTF-8 JSON bytes.

    Rules match catalog_identity.canonical_sha256 JSON form.
    Rejects embedded artifact_sha256 so digest stays external (PLAN-05).
    """
    if not isinstance(body, dict):
        raise ValueError('prepared artifact body must be a dict')
    forbidden = _FORBIDDEN_SELF_HASH_KEYS.intersection(body.keys())
    if forbidden:
        raise ValueError(
            f'artifact body must not embed self-hash field(s): {sorted(forbidden)}'
        )
    version = body.get('artifact_serialization_version')
    if version is not None and version != PREPARED_ARTIFACT_SERIALIZATION_VERSION:
        raise ValueError(
            f'unsupported artifact_serialization_version: {version!r}; '
            f'expected {PREPARED_ARTIFACT_SERIALIZATION_VERSION!r}'
        )
    _reject_non_finite(body)
    return json.dumps(
        body, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    ).encode('utf-8')


def artifact_sha256(artifact_bytes: bytes) -> str:
    """Return 64 lowercase hex SHA-256 over complete canonical artifact bytes."""
    if not isinstance(artifact_bytes, (bytes, bytearray)):
        raise TypeError('artifact_bytes must be bytes')
    return hashlib.sha256(bytes(artifact_bytes)).hexdigest()


def chunk_artifact_bytes(
    artifact_bytes: bytes,
    *,
    chunk_size: int = DEFAULT_CHUNK_BYTES,
) -> list[dict[str, Any]]:
    """Split artifact bytes into ordered base64 chunks with per-chunk digests.

    Empty payload yields a single empty chunk (documented rule).
    Enforces HARD_CHUNK_BYTES and MAX_CHUNKS_PER_PLAN hard ceilings.
    """
    if not isinstance(artifact_bytes, (bytes, bytearray)):
        raise TypeError('artifact_bytes must be bytes')
    if not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError('chunk_size must be a positive integer')
    if chunk_size > HARD_CHUNK_BYTES:
        raise ValueError(
            f'chunk_size {chunk_size} exceeds hard max {HARD_CHUNK_BYTES}'
        )

    data = bytes(artifact_bytes)
    if not data:
        empty = b''
        return [
            {
                'chunk_index': 0,
                'byte_offset': 0,
                'byte_length': 0,
                'chunk_sha256': hashlib.sha256(empty).hexdigest(),
                'payload_b64': base64.b64encode(empty).decode('ascii'),
            }
        ]

    total = len(data)
    n_chunks = (total + chunk_size - 1) // chunk_size
    if n_chunks > MAX_CHUNKS_PER_PLAN:
        raise ValueError(
            f'chunk count {n_chunks} exceeds hard max {MAX_CHUNKS_PER_PLAN}'
        )

    chunks: list[dict[str, Any]] = []
    for index in range(n_chunks):
        offset = index * chunk_size
        slice_bytes = data[offset : offset + chunk_size]
        chunks.append(
            {
                'chunk_index': index,
                'byte_offset': offset,
                'byte_length': len(slice_bytes),
                'chunk_sha256': hashlib.sha256(slice_bytes).hexdigest(),
                'payload_b64': base64.b64encode(slice_bytes).decode('ascii'),
            }
        )
    return chunks


def reassemble_artifact_bytes(
    chunks: list[dict[str, Any]],
    *,
    expected_sha256: str | None = None,
    expected_length: int | None = None,
) -> bytes:
    """Reassemble ordered chunks; fail closed on corruption/reorder gaps/digest mismatch.

    Chunks are sorted by chunk_index before decode. Missing indices, bad base64,
    per-chunk digest mismatch, length mismatch, or artifact digest mismatch raise
    ValueError.
    """
    if not isinstance(chunks, list) or not chunks:
        raise ValueError('chunks must be a non-empty list')
    if len(chunks) > MAX_CHUNKS_PER_PLAN:
        raise ValueError(
            f'chunk count {len(chunks)} exceeds hard max {MAX_CHUNKS_PER_PLAN}'
        )

    try:
        ordered = sorted(chunks, key=lambda c: int(c['chunk_index']))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid chunk_index') from exc

    indices = [int(c['chunk_index']) for c in ordered]
    if indices != list(range(len(indices))):
        raise ValueError(
            f'missing or non-contiguous chunk_index sequence: {indices}'
        )

    parts: list[bytes] = []
    running_offset = 0
    for ch in ordered:
        try:
            payload_b64 = ch['payload_b64']
            declared_length = int(ch['byte_length'])
            declared_offset = int(ch['byte_offset'])
            declared_digest = str(ch['chunk_sha256'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('chunk missing required fields') from exc

        if declared_offset != running_offset:
            raise ValueError(
                f'byte_offset mismatch at index {ch["chunk_index"]}: '
                f'expected {running_offset}, got {declared_offset}'
            )

        try:
            payload = base64.b64decode(payload_b64, validate=True)
        except Exception as exc:
            raise ValueError('invalid payload_b64') from exc

        if len(payload) != declared_length:
            raise ValueError(
                f'chunk length mismatch at index {ch["chunk_index"]}: '
                f'declared {declared_length}, decoded {len(payload)}'
            )

        actual_digest = hashlib.sha256(payload).hexdigest()
        if actual_digest != declared_digest.lower():
            raise ValueError(
                f'chunk_sha256 mismatch at index {ch["chunk_index"]}'
            )

        parts.append(payload)
        running_offset += declared_length

    result = b''.join(parts)

    if expected_length is not None and len(result) != expected_length:
        raise ValueError(
            f'length mismatch: expected {expected_length}, got {len(result)}'
        )

    if expected_sha256 is not None:
        actual = artifact_sha256(result)
        if actual != expected_sha256.lower():
            raise ValueError(
                f'artifact_sha256 mismatch: expected {expected_sha256}, got {actual}'
            )

    return result
