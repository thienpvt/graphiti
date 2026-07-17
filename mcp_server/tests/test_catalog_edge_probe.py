"""Executable backstops for Phase 1 catalog contract edge probes."""

from __future__ import annotations

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.catalog_common import (  # noqa: E402
    CatalogErrorCode,
    catalog_validation_error_to_structured,
)
from models.catalog_entities import (  # noqa: E402
    CatalogEntityItem,
    UpsertTypedEntitiesRequest,
)

GROUP = 'oracle-catalog-tool-test'


def _entity(
    graph_key: str = 'TABLE::FE::ORCL.HR.EMPLOYEES',
    **overrides: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        'entity_type': 'Table',
        'graph_key': graph_key,
        'name_raw': graph_key.rsplit('.', 1)[-1],
        'name_canonical': graph_key.rsplit('.', 1)[-1].lower(),
        'database_qualified_name': graph_key.split('::', 2)[-1],
        'summary': 'Catalog entity',
    }
    item.update(overrides)
    return item


def _request(entities: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'identity_schema_version': 'catalog-v2',
        'system_key': 'FE',
        'group_id': GROUP,
        'batch_id': 'edge-probe',
        'entities': entities,
    }
    payload.update(overrides)
    return payload


async def _validate(payload: dict[str, Any]) -> UpsertTypedEntitiesRequest:
    await asyncio.sleep(0)
    return UpsertTypedEntitiesRequest.model_validate(payload)


async def _errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    await asyncio.sleep(0)
    try:
        UpsertTypedEntitiesRequest.model_validate(payload)
    except ValidationError as exc:
        return exc.errors(include_url=False, include_context=False, include_input=False)
    raise AssertionError('payload unexpectedly validated')


@pytest.mark.asyncio
async def test_edge_probe_cont01_model_validate_concurrency():
    repeated = [_entity(), _entity()]
    distinct = [_entity('TABLE::FE::ORCL.HR.DEPARTMENTS')]
    payloads = [_request(repeated), _request(distinct), _request(deepcopy(repeated))]
    snapshots = deepcopy(payloads)

    results = await asyncio.gather(*(_validate(payload) for payload in payloads))

    assert payloads == snapshots
    assert [len(result.entities) for result in results] == [2, 1, 2]
    assert results[0].entities[0] == results[0].entities[1]
    assert results[0].entities[0] is not results[0].entities[1]
    assert results[0].entities[0] is not results[2].entities[0]


@pytest.mark.asyncio
async def test_edge_probe_cont02_recursive_forbid_concurrency():
    payloads = [
        _request([_entity(source_refs=[{'page': 1, 'raw_text': 'a', 'extra_a': True}])]),
        _request([_entity(source_refs=[{'page': 2, 'raw_text': 'b', 'extra_b': True}])]),
    ]

    results = await asyncio.gather(*(_errors(payload) for payload in payloads))

    assert [[tuple(error['loc']) for error in errors] for errors in results] == [
        [('entities', 0, 'source_refs', 0, 'extra_a')],
        [('entities', 0, 'source_refs', 0, 'extra_b')],
    ]
    assert all(errors[0]['type'] == 'extra_forbidden' for errors in results)


def test_edge_probe_cont07_error_encoding_contract():
    sentinel = '秘密🔒PAYLOAD_SENTINEL'
    payload = _request(
        [
            _entity(unknown_first=sentinel),
            _entity('TABLE::FE::ORCL.HR.DEPARTMENTS', unknown_second=sentinel),
        ]
    )

    with pytest.raises(ValidationError) as caught:
        UpsertTypedEntitiesRequest.model_validate(payload)

    errors = caught.value.errors(include_url=False, include_context=False, include_input=False)
    structured = catalog_validation_error_to_structured(caught.value)
    encoded = json.dumps(structured, ensure_ascii=False, default=str)

    assert [tuple(error['loc']) for error in errors] == [
        ('entities', 0, 'unknown_first'),
        ('entities', 1, 'unknown_second'),
    ]
    assert structured['field_path'] == 'entities.0.unknown_first'
    assert structured['code'] == CatalogErrorCode.validation_error
    assert len(structured['message']) <= 512
    assert sentinel not in encoded
    assert json.loads(encoded)['field_path'] == 'entities.0.unknown_first'


def test_edge_probe_cont07_finite_confidence_precision_contract():
    for invalid in (float('nan'), float('inf'), float('-inf'), -0.0001, 1.0001):
        with pytest.raises(ValidationError):
            CatalogEntityItem.model_validate(_entity(confidence=invalid))

    assert CatalogEntityItem.model_validate(_entity(confidence=0.0)).confidence == 0.0
    assert CatalogEntityItem.model_validate(_entity(confidence=1.0)).confidence == 1.0


def test_edge_probe_iden01_validation_ordering():
    service_entries: list[str] = []
    invalid = _request([_entity()], identity_schema_version='catalog-v1')

    with pytest.raises(ValidationError) as caught:
        request = UpsertTypedEntitiesRequest.model_validate(invalid)
        service_entries.append(request.identity_schema_version)

    structured = catalog_validation_error_to_structured(caught.value)
    assert service_entries == []
    assert caught.value.errors()[0]['loc'] == ('identity_schema_version',)
    assert structured['code'] == CatalogErrorCode.unsupported_identity_schema
    assert structured['field_path'] == 'identity_schema_version'


@pytest.mark.asyncio
async def test_edge_probe_iden01_validation_concurrency():
    payloads = [
        _request([_entity()], batch_id='valid-a'),
        _request([_entity()], batch_id='invalid', identity_schema_version='catalog-v1'),
        _request([_entity()], batch_id='valid-b'),
    ]

    results = await asyncio.gather(
        *(_validate(payload) for payload in payloads), return_exceptions=True
    )

    assert [type(result) for result in results] == [
        UpsertTypedEntitiesRequest,
        ValidationError,
        UpsertTypedEntitiesRequest,
    ]
    assert results[0].batch_id == 'valid-a'
    assert results[2].batch_id == 'valid-b'
    invalid = results[1]
    assert isinstance(invalid, ValidationError)
    assert invalid.errors()[0]['loc'] == ('identity_schema_version',)


def test_edge_probe_iden02_system_key_ordering():
    invalid_shell = _request([_entity()], system_key='fe')
    with pytest.raises(ValidationError) as shell_error:
        UpsertTypedEntitiesRequest.model_validate(invalid_shell)

    mismatch = _request(
        [
            _entity('TABLE::FE::ORCL.HR.EMPLOYEES'),
            _entity('TABLE::BO::ORCL.HR.DEPARTMENTS'),
        ]
    )
    with pytest.raises(ValidationError) as nested_error:
        UpsertTypedEntitiesRequest.model_validate(mismatch)

    shell_structured = catalog_validation_error_to_structured(shell_error.value)
    nested_structured = catalog_validation_error_to_structured(nested_error.value)
    assert shell_error.value.errors()[0]['type'] == 'invalid_system_key'
    assert shell_structured['code'] == CatalogErrorCode.invalid_system_key
    assert shell_structured['field_path'] == 'system_key'
    assert nested_error.value.errors()[0]['type'] == 'invalid_system_key'
    assert nested_structured['field_path'] == 'entities.1.graph_key'


def test_edge_probe_iden04_graph_key_ordering():
    keys = [
        'TABLE::FE::ORCL.HR.ZETA',
        'TABLE::FE::ORCL.HR.ALPHA',
        'TABLE::FE::ORCL.HR.ZETA',
    ]
    request = UpsertTypedEntitiesRequest.model_validate(_request([_entity(key) for key in keys]))
    assert [item.graph_key for item in request.entities] == keys

    mismatches = _request(
        [
            _entity('TABLE::BO::ORCL.HR.ZETA'),
            _entity('TABLE::BO::ORCL.HR.ALPHA'),
        ]
    )
    with pytest.raises(ValidationError) as caught:
        UpsertTypedEntitiesRequest.model_validate(mismatches)
    assert [error['loc'] for error in caught.value.errors()] == [
        ('entities', 0, 'graph_key'),
    ]


def test_edge_probe_iden05_overload_ordering():
    keys = [
        'PROCEDURE::FE::ORCL.HR.PKG.SYNC#1',
        'FUNCTION::FE::ORCL.HR.PKG.SYNC#1',
        'PROCEDURE::FE::ORCL.HR.PKG.SYNC#2',
        'FUNCTION::FE::ORCL.HR.SYNC#STANDALONE',
    ]
    entities = [
        _entity(key, entity_type='Procedure' if key.startswith('PROCEDURE') else 'Function')
        for key in keys
    ]

    request = UpsertTypedEntitiesRequest.model_validate(_request(entities))

    assert [item.graph_key for item in request.entities] == keys
    assert len({item.graph_key for item in request.entities}) == len(keys)
