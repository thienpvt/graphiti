"""No-network construction proof for pure catalog-v2 Neo4j fixtures (WR-02 / gap_wr02)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from types import ModuleType

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS_DIR))
sys.path.insert(0, str(_TESTS_DIR.parent / 'src'))


class _NetworkBlocked(RuntimeError):
    pass


def _block_socket(*_args, **_kwargs):
    raise _NetworkBlocked('network/socket blocked during pure fixture construction')


@pytest.fixture
def offline_env(monkeypatch: pytest.MonkeyPatch):
    """Install socket/driver/network tripwires for pure construction only."""
    monkeypatch.setattr(socket, 'socket', _block_socket)

    class _BlockedModule(ModuleType):
        def __getattr__(self, name: str):  # pragma: no cover - defensive
            raise _NetworkBlocked(f'forbidden module attribute access: {self.__name__}.{name}')

    for name in (
        'neo4j',
        'neo4j.async_driver',
        'graphiti_core.driver.neo4j_driver',
    ):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, _BlockedModule(name))

    # Import pure helper only after tripwires.
    import catalog_neo4j_fixtures as fixtures

    yield fixtures


def test_gap_wr02_pure_helper_has_no_forbidden_imports(offline_env):
    fixtures = offline_env
    helper_path = fixtures.__file__
    assert helper_path is not None
    source = Path(helper_path).read_text(encoding='utf-8')
    # Strip module docstring before scanning import/runtime surface.
    body = source
    if body.startswith('"""'):
        end = body.find('"""', 3)
        if end != -1:
            body = body[end + 3 :]
    forbidden_tokens = (
        'import pytest',
        'from pytest',
        'neo4j_driver',
        'catalog_client',
        'import socket',
        'from socket',
        'AsyncGraphDatabase',
        'test_catalog_neo4j_int',
        'graphiti_core.driver',
    )
    for token in forbidden_tokens:
        assert token not in body, f'pure helper must not reference {token!r}'


def test_gap_wr02_constructs_all_fixture_variants_offline(offline_env):
    fixtures = offline_env
    from models.catalog_entities import ResolveEntityRef, VerifyEntityRef

    entities = fixtures.build_six_entities()
    assert len(entities) == 6
    for item in entities:
        assert '::FE::' in item.graph_key
        assert item.graph_key.count('::') >= 2

    extra = fixtures.build_extra_table()
    assert extra.graph_key.startswith('TABLE::FE::')
    doc = fixtures.build_doc_entity()
    assert doc.graph_key.startswith('DOC::FE::')

    edges = fixtures.build_structural_and_fk_edges()
    assert len(edges) == 6
    for edge in edges:
        assert '::FE::' in edge.source_graph_key
        assert '::FE::' in edge.target_graph_key

    accept = fixtures.build_accept_tab_request()
    assert accept.identity_schema_version == 'catalog-v2'
    assert accept.system_key == 'FE'
    assert accept.group_id == fixtures.GROUP
    assert accept.group_id != fixtures.FORBIDDEN_GROUP
    for item in accept.entities:
        assert '::FE::' in item.graph_key
    for edge in accept.edges:
        assert '::FE::' in edge.source_graph_key
        assert '::FE::' in edge.target_graph_key

    entity_req = fixtures.build_upsert_entities_request(entities)
    assert entity_req.identity_schema_version == 'catalog-v2'
    assert entity_req.system_key == 'FE'
    assert entity_req.group_id == fixtures.GROUP

    edge_req = fixtures.build_upsert_edges_request(edges)
    assert edge_req.identity_schema_version == 'catalog-v2'
    assert edge_req.system_key == 'FE'

    resolve_req = fixtures.build_resolve_entities_request(
        [
            ResolveEntityRef.model_validate(
                {
                    'entity_type': 'Table',
                    'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                }
            )
        ]
    )
    assert resolve_req.system_key == 'FE'

    verify_req = fixtures.build_verify_batch_request(
        entities=[
            VerifyEntityRef.model_validate(
                {
                    'entity_type': 'Table',
                    'graph_key': 'TABLE::FE::ORCL.HR.EMPLOYEES',
                }
            )
        ]
    )
    assert verify_req.system_key == 'FE'

    prov_req = fixtures.build_provenance_request()
    assert prov_req.identity_schema_version == 'catalog-v2'
    assert prov_req.system_key == 'FE'
    assert prov_req.group_id == fixtures.GROUP

    winner, loser = fixtures.build_conflicting_entity_pair()
    assert winner.graph_key == loser.graph_key
    assert winner.name_raw != loser.name_raw
    assert winner.name_canonical != loser.name_canonical
    assert winner.summary != loser.summary


def test_gap_wr02_accept_tab_json_is_catalog_v2_fe_scoped(offline_env):
    fixtures = offline_env
    payload = fixtures.ACCEPT_TAB_FIXTURE.read_text(encoding='utf-8')
    assert 'identity_schema_version' in payload
    assert 'catalog-v2' in payload
    assert '"system_key": "FE"' in payload or '"system_key":"FE"' in payload
    assert 'TABLE::FE::' in payload
    assert 'TABLE::APP.' not in payload
    assert 'COLUMN::APP.' not in payload


def test_gap_wr02_no_network_or_driver_activation(offline_env):
    _ = offline_env
    with pytest.raises(_NetworkBlocked):
        socket.socket()
