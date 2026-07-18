"""Pure plan-token mint/digest/compare contract (PLAN-06, PLAN-07, PLAN-17)."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from services import catalog_identity as identity_mod  # noqa: E402
from services.catalog_identity import (  # noqa: E402
    TOKEN_DIGEST_DOMAIN,
    mint_plan_token,
    plan_binding_fields,
    plan_token_digest,
    plan_token_matches,
)
from services.catalog_prepared_artifact import (  # noqa: E402
    serialize_prepared_artifact,
)

GROUP = 'oracle-catalog-tool-test'


def test_token_digest_domain_constant():
    assert TOKEN_DIGEST_DOMAIN == b'graphiti.catalog.plan_token.v1|'


def test_mint_plan_token_uses_secrets():
    src = inspect.getsource(mint_plan_token)
    assert 'secrets' in src
    assert 'token_urlsafe' in src
    # module imports secrets
    assert hasattr(identity_mod, 'secrets') or 'import secrets' in inspect.getsource(
        identity_mod
    )


def test_mint_plan_token_returns_urlsafe_and_differs():
    a = mint_plan_token()
    b = mint_plan_token()
    assert isinstance(a, str) and len(a) >= 32
    assert isinstance(b, str) and len(b) >= 32
    assert a != b
    # urlsafe alphabet only
    allowed = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_')
    assert set(a) <= allowed
    assert set(b) <= allowed


def test_mint_not_derived_from_plan_uuid_batch_or_hash():
    plan_uuid = str(uuid.uuid4())
    batch_id = 'batch-predictable'
    request_hash = 'a' * 64
    token = mint_plan_token()
    assert token != plan_uuid
    assert token != batch_id
    assert token != request_hash
    assert plan_uuid not in token
    assert batch_id not in token
    assert request_hash not in token


def test_plan_token_digest_stable_and_domain_separated():
    token = 'test-token-value-not-from-mint'
    digest = plan_token_digest(token)
    assert digest == plan_token_digest(token)
    assert len(digest) == 64
    expected = hashlib.sha256(
        TOKEN_DIGEST_DOMAIN + token.encode('utf-8')
    ).hexdigest()
    assert digest == expected
    # different domain would differ
    other = hashlib.sha256(b'other.domain|' + token.encode('utf-8')).hexdigest()
    assert digest != other
    # raw sha256 without domain differs
    bare = hashlib.sha256(token.encode('utf-8')).hexdigest()
    assert digest != bare


def test_plan_token_matches_true_and_false():
    token = mint_plan_token()
    digest = plan_token_digest(token)
    assert plan_token_matches(token, digest) is True
    assert plan_token_matches(token, digest.upper()) is True  # hex case-insensitive store
    assert plan_token_matches('wrong-token', digest) is False
    assert plan_token_matches(token, '0' * 64) is False
    assert plan_token_matches('', digest) is False


def test_plan_token_matches_uses_compare_digest():
    src = inspect.getsource(plan_token_matches)
    assert 'compare_digest' in src
    assert 'hmac.compare_digest' in src or 'compare_digest(' in src
    # plain == must not be the digest comparison path
    # allow == only for type/empty guards; require compare_digest present
    assert 'hmac' in inspect.getsource(identity_mod)


def test_helpers_have_no_io():
    for fn in (mint_plan_token, plan_token_digest, plan_token_matches, plan_binding_fields):
        src = inspect.getsource(fn)
        assert 'open(' not in src
        assert 'print(' not in src
        assert 'logger' not in src
        assert 'neo4j' not in src.lower()


def test_plan_binding_fields_pure_construct():
    binding = plan_binding_fields(
        plan_uuid='11111111-1111-1111-1111-111111111111',
        group_id=GROUP,
        batch_id='batch-1',
        identity_schema_version='catalog-v2',
        request_sha256='1' * 64,
        catalog_sha256='2' * 64,
        artifact_sha256='3' * 64,
    )
    assert binding == {
        'plan_uuid': '11111111-1111-1111-1111-111111111111',
        'group_id': GROUP,
        'batch_id': 'batch-1',
        'identity_schema_version': 'catalog-v2',
        'request_sha256': '1' * 64,
        'catalog_sha256': '2' * 64,
        'artifact_sha256': '3' * 64,
    }
    # no raw token field
    assert 'plan_token' not in binding
    assert 'token' not in binding


def test_raw_token_never_in_serialized_artifact():
    token = mint_plan_token()
    body = {
        'artifact_serialization_version': 'prepared-artifact-v1',
        'canonicalization_version': 'catalog-canonical-v1',
        'identity_schema_version': 'catalog-v2',
        'catalog_schema_version': 'catalog-schema-v1',
        'group_id': GROUP,
        'batch_id': 'batch-tok',
        'system_key': 'FE',
        'request_sha256': '1' * 64,
        'catalog_sha256': '2' * 64,
        'plan_id': 'batch-tok|' + ('1' * 64),
        'membership': {
            'entities': [],
            'edges': [],
            'sources': [],
            'evidence_links': [],
        },
        'request_canonical': {},
        'counts': {
            'entities': 0,
            'edges': 0,
            'sources': 0,
            'evidence_links': 0,
            'created': 0,
            'updated': 0,
            'unchanged': 0,
        },
    }
    raw = serialize_prepared_artifact(body)
    assert token.encode('utf-8') not in raw
    assert b'plan_token' not in raw
    # digest may appear only if caller put it — serialize helpers must not inject it
    digest = plan_token_digest(token)
    assert digest.encode('utf-8') not in raw


def test_compare_digest_behavior_matches_hmac():
    token = mint_plan_token()
    digest = plan_token_digest(token)
    # behavioral equivalence with hmac.compare_digest on digests
    assert hmac.compare_digest(plan_token_digest(token), digest) is True
    assert plan_token_matches(token, digest) is True
