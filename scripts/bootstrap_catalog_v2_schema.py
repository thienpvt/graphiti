#!/usr/bin/env python3
"""Thin compatibility wrapper for the source-owned Catalog-v2 bootstrap CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SRC = ROOT / 'mcp_server' / 'src'
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from services.catalog_schema_bootstrap import (  # pyright: ignore[reportMissingImports]  # noqa: E402,F401
    CatalogNeo4jStore,
    RawNeo4jExecutor,
    _neo4j_config,
    bootstrap,
    main,
    parse_args,
)

if __name__ == '__main__':
    raise SystemExit(main())
