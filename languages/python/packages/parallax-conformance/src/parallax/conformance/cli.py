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
from pathlib import Path
from typing import Final

from parallax.conformance import adapter, case_format
from parallax.conformance.profile import profile_for

__all__ = ["main"]

_EXIT: Final[dict[str, int]] = {"ok": 0, "unsupported": 10, "run-only": 11, "error": 1}


def _build_parser() -> argparse.ArgumentParser:
    """``compile`` names a dialect because it executes nothing and so has no adapter
    to read one off; ``run`` and ``benchmark`` name a declared profile, which carries
    the adapter — and with it the dialect — the case is executed in
    (m-conformance-adapter)."""
    parser = argparse.ArgumentParser(prog="parallax-conformance")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("describe", help="report the adapter's claimed capability set")

    compile_parser = sub.add_parser("compile", help="compile one compatibility case")
    compile_parser.add_argument("--case", required=True, help="path to the case YAML file")
    compile_parser.add_argument("--dialect", required=True, help="target SQL dialect")

    run_parser = sub.add_parser("run", help="run one compatibility case")
    run_parser.add_argument("--case", required=True, help="path to the case YAML file")
    run_parser.add_argument("--profile", required=True, help="declared matrix profile to run")

    benchmark = sub.add_parser("benchmark", help="run one benchmark fixture (unclaimed)")
    benchmark.add_argument("--benchmark", required=True, help="path to the benchmark YAML file")
    benchmark.add_argument("--profile", required=True, help="declared matrix profile to run")

    return parser


def _emit(envelope: adapter.Envelope) -> int:
    print(json.dumps(envelope))
    return _EXIT[str(envelope["status"])]


def _run_self_managed(
    case_path: str, profile_name: str
) -> adapter.Envelope:  # pragma: no cover - Docker
    """Resolve the profile, provision a fresh container, reset from the case, run it.

    The profile is resolved first and resolving it opens nothing, so a name no
    profile declares is refused as `unsupported` before a case is even read — the
    same guard an out-of-claim dialect gets under `compile`. The profile then
    constitutes the run itself: this function names no port, so the profile the
    envelope reports and the database the case executed against cannot come apart.

    A `rejected`-shape case is provisioning-free by contract
    (m-conformance-adapter): its run answer is the classified
    `rejectedRule`, touching no SQL, so it is dispatched BEFORE any
    provisioner is constructed — no container starts for it at all (the shape
    dispatch already lives in :func:`~parallax.conformance.adapter.run_case`; this
    only decides whether that call is preceded by provisioning).
    """
    try:
        profile = profile_for(profile_name)
    except ValueError as exc:
        return adapter.unsupported("run", adapter.Diagnostic("unsupported-profile", str(exc)))
    case = case_format.load_case(Path(case_path))
    diagnostic = adapter.classify("run", profile.dialect.name, case)
    if diagnostic is not None:
        return adapter.unsupported("run", diagnostic)
    if case.shape == "rejected":
        return adapter.run_case(case_path, profile.unprovisioned())

    from parallax.conformance import engine, provision

    with profile.provisioned() as run:
        meta = engine.load_case_metamodel(case)
        run.reset(meta, provision.load_fixtures(str(case.document["model"])))
        return adapter.run_case(case_path, run)


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
            envelope = _run_self_managed(args.case, args.profile)
    except (OSError, ValueError) as exc:
        diagnostic = adapter.Diagnostic("unreadable-case", f"cannot read case {args.case!r}: {exc}")
        print(json.dumps(adapter.error(command, diagnostic)))
        return 2
    return _emit(envelope)
