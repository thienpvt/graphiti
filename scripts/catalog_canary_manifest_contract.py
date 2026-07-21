"""Canonical live catalog canary manifest contract."""

LIVE_MANIFEST_FIELDS = frozenset(
    {
        'artifact_schema_version',
        'profile',
        'run_id',
        'group_id',
        'control_group_id',
        'batch_id',
        'identity_schema_version',
        'system_key',
        'fixture',
        'fixture_sha256',
        'fixture_lf_sha256',
        'catalog_sha256',
        'request_sha256',
        'artifact_sha256',
        'payload',
        'counts',
        'builder',
        'builder_sha256',
        'allow_unknown_embedding_provider',
        'source_digest_origin',
        'execution_surface',
        'canary_executed',
    }
)
SOURCE_DIGEST_ORIGIN_HOST = 'host'
EXECUTION_SURFACE_COMPOSE = 'compose-graphiti-mcp-only'
WAIVER_OPENAI = 'openai'
