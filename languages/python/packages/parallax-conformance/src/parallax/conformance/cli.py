"""``parallax.conformance.cli`` enforcement scope (m-conformance-adapter).

The ``parallax-conformance`` console script: argv → the in-process adapter core
→ exactly one JSON envelope on stdout, plus the contract's exit codes
(0 ok / 10 unsupported / 11 compile-run-only / 1 error / 2 CLI usage error).
Human-readable logs, if any, go to stderr; stdout is always a single schema-valid
envelope. The ``run`` command self-provisions (spec §6 ``self-managed``): a fresh
container per claimed case, reset from the case's descriptor and fixtures.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from parallax.conformance import adapter, case_format
from parallax.core.db_port import DbPort, Row

__all__ = ["main"]

_EXIT: Final[dict[str, int]] = {"ok": 0, "unsupported": 10, "run-only": 11, "error": 1}


class _NoProvisioningPort:
    """A `DbPort` that raises if touched — the CLI's structural proof that a
    `rejected`-shape ``run`` never provisions and never executes SQL
    (m-conformance-adapter, resolved DQ3): ``run`` of a rejected case is
    dispatched with THIS port instead of a Docker-backed one, so a future
    regression that makes the rejected lane reach the port fails loudly rather
    than silently starting a container.
    """

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:  # pragma: no cover
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise AssertionError("a rejected-case run must not open a transaction")


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


def _run_self_managed(
    case_path: str, dialect: str
) -> adapter.Envelope:  # pragma: no cover - Docker
    """Provision a fresh container, reset from the case, and run it.

    A `rejected`-shape case is provisioning-free by contract
    (m-conformance-adapter, resolved DQ3): its run answer is the classified
    `rejectedRule`, touching no SQL, so it is dispatched BEFORE any
    :class:`~parallax.conformance.provision.Provisioner` is constructed — no
    container starts for it at all (the shape dispatch already lives in
    :func:`~parallax.conformance.adapter.run_case`; this only decides whether
    that call is preceded by provisioning).
    """
    case = case_format.load_case(Path(case_path))
    diagnostic = adapter.classify("run", dialect, case)
    if diagnostic is not None:
        return adapter.unsupported("run", diagnostic)
    if case.shape == "rejected":
        return adapter.run_case(case_path, dialect, _NoProvisioningPort())

    from parallax.conformance import engine, provision

    provisioner = provision.Provisioner()
    try:
        meta = engine.load_case_metamodel(case)
        provisioner.reset(meta, provision.load_fixtures(str(case.document["model"])))
        return adapter.run_case(case_path, dialect, provisioner.port)
    finally:
        provisioner.close()


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
            envelope = _run_self_managed(args.case, args.dialect)
    except (OSError, ValueError) as exc:
        diagnostic = adapter.Diagnostic("unreadable-case", f"cannot read case {args.case!r}: {exc}")
        print(json.dumps(adapter.error(command, diagnostic)))
        return 2
    return _emit(envelope)
