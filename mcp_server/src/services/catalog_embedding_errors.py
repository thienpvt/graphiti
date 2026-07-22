"""Sanitized embedding transport error classification."""

from __future__ import annotations

from typing import Any

EMBEDDING_TRANSPORT_AUTH = 'embedding_transport_auth'
_AUTH_STATUSES = frozenset({401, 403})


def _numeric_status(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def is_embedding_transport_auth(exc: BaseException) -> bool:
    """Classify provider authentication without reading exception text or arguments."""
    if type(exc).__name__ == 'AuthenticationError' and type(exc).__module__.startswith('openai'):
        return True
    return any(
        _numeric_status(getattr(exc, attribute, None)) in _AUTH_STATUSES
        for attribute in ('status_code', 'status')
    )


def embedding_error_message(exc: BaseException) -> str:
    return (
        EMBEDDING_TRANSPORT_AUTH
        if is_embedding_transport_auth(exc)
        else 'embedding generation failed'
    )
