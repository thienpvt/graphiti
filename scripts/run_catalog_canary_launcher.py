#!/usr/bin/env python3
"""Canonical catalog canary process launcher and sole Compose subprocess owner."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_catalog_canary_batch as runner  # pyright: ignore[reportMissingImports]  # noqa: E402


def run_compose(action: str) -> None:
    argv = runner.compose_argv(action)
    runner.attest_host_compose_argv(argv)
    runner.host_side_execution_authority_digests()
    env = {
        key: value for key, value in os.environ.items() if not key.upper().startswith('COMPOSE_')
    }
    env['COMPOSE_PROJECT_NAME'] = runner.COMPOSE_PROJECT_NAME
    env['COMPOSE_REMOVE_ORPHANS'] = '0'
    subprocess.run(argv, cwd=runner.ROOT, env=env, shell=False, check=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('up', 'ps', 'logs', 'canary'))
    parser.add_argument('runner_args', nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.action == 'canary':
        if not args.runner_args:
            raise runner.RunnerError(
                'execution_boundary_violation', 'canary arguments are required'
            )
        result = asyncio.run(runner.execute_cli(runner.parse_args(args.runner_args)))
        print(runner.json.dumps(result, sort_keys=True))
    else:
        if args.runner_args:
            raise runner.RunnerError(
                'execution_boundary_violation', 'extra launcher tokens forbidden'
            )
        run_compose(args.action)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
