#!/usr/bin/env python3
"""Entrypoint: run Phase 3A fail-closed gate and print ledger summary."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import catalog_phase3a_gate_runner as gate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    # Default command is run when invoked as wrapper with no args.
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        args = ['run']
    return gate.main(args)


if __name__ == '__main__':
    raise SystemExit(main())
