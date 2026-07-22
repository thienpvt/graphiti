#!/usr/bin/env python3
"""Execute the single approved Phase 6 clean-room canary."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FinalCanaryError(RuntimeError):
    """Fail-closed final-canary launcher error."""


def resolve_job_tmp(environment: dict[str, str] | None = None) -> Path:
    raise NotImplementedError


def expand_argv(argv: list[str], *, job_tmp: Path) -> list[str]:
    raise NotImplementedError


def run_final_canary(
    *,
    freeze_receipt: Path,
    invocation: Path,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    del argv
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
