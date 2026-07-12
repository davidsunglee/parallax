"""``parallax.conformance.cli`` enforcement scope (m-conformance-adapter).

The ``parallax-conformance`` console script: argv → the in-process adapter core
→ exactly one JSON envelope on stdout, plus the contract's exit codes
(0 ok / 10 unsupported / 1 error / 2 CLI usage error). Human-readable logs, if
any, go to stderr; stdout is always a single schema-valid envelope.
"""

from __future__ import annotations

import argparse
import json
from typing import Final

from parallax.conformance import adapter

__all__ = ["main"]

_EXIT: Final[dict[str, int]] = {"ok": 0, "unsupported": 10, "error": 1}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parallax-conformance")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("describe", help="report the adapter's claimed capability set")

    for name in ("compile", "run"):
        case_parser = sub.add_parser(name, help=f"{name} one compatibility case")
        case_parser.add_argument("--case", required=True, help="path to the case YAML file")
        case_parser.add_argument("--dialect", required=True, help="target SQL dialect")

    benchmark = sub.add_parser("benchmark", help="run one benchmark fixture (unclaimed)")
    benchmark.add_argument("--benchmark", required=True, help="path to the benchmark YAML file")
    benchmark.add_argument("--dialect", required=True, help="target SQL dialect")

    return parser


def _emit(envelope: adapter.Envelope) -> int:
    print(json.dumps(envelope))
    return _EXIT[str(envelope["status"])]


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point (returns the process exit code)."""
    args = _build_parser().parse_args(argv)
    command: str = args.command

    if command == "describe":
        return _emit(adapter.describe())
    if command == "benchmark":
        return _emit(adapter.unsupported_command("benchmark"))

    try:
        if command == "compile":
            envelope = adapter.compile_case(args.case, args.dialect)
        else:
            envelope = adapter.run_case(args.case, args.dialect)
    except (OSError, ValueError) as exc:
        diagnostic = adapter.Diagnostic("unreadable-case", f"cannot read case {args.case!r}: {exc}")
        print(json.dumps(adapter.error(command, diagnostic)))
        return 2
    return _emit(envelope)
