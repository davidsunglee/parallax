"""``parallax.conformance.adapter`` — the in-process conformance adapter core.

Plain functions returning **envelope** dicts: the JSON documents
``m-conformance-adapter`` defines as the wire surface (validated against
``core/schemas/conformance-adapter.schema.json``). ``describe`` reports the
claim; ``compile_case`` / ``run_case`` classify the request against the claim's
filters in contract order and, for a claimed case, emit an ``error`` envelope
until the compile/run lanes come online (COR-3 Phase 5+).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from parallax.conformance import case_format, engine
from parallax.conformance.claim import ADAPTER, SNAPSHOT_CLAIM, Adapter, Claim
from parallax.core.db_port import DbPort

__all__ = [
    "SCHEMA_VERSION",
    "Diagnostic",
    "Envelope",
    "classify",
    "compile_case",
    "describe",
    "error",
    "run_case",
    "unsupported",
    "unsupported_command",
]

SCHEMA_VERSION: Final[str] = "1"

Envelope = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One envelope diagnostic naming the failed filter (or the failure)."""

    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _common(command: str, status: str, adapter: Adapter) -> Envelope:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "command": command,
        "status": status,
        "adapter": adapter.to_json(),
    }


def _non_ok(command: str, status: str, diagnostic: Diagnostic, adapter: Adapter) -> Envelope:
    envelope = _common(command, status, adapter)
    envelope["diagnostics"] = [diagnostic.to_json()]
    return envelope


def describe(claim: Claim = SNAPSHOT_CLAIM, adapter: Adapter = ADAPTER) -> Envelope:
    """The ``describe`` envelope: the adapter's claimed capability set."""
    envelope = _common("describe", "ok", adapter)
    envelope["capabilities"] = claim.capabilities()
    return envelope


def classify(
    command: str,
    dialect: str,
    case: case_format.Case,
    claim: Claim = SNAPSHOT_CLAIM,
) -> Diagnostic | None:
    """Classify a case command against the claim's filters in contract order.

    Returns ``None`` when the case command is within the claim, or the
    diagnostic naming the **first** failed filter otherwise (command → dialect
    → shape → module tags → include → exclude).
    """
    if command not in claim.commands:
        return Diagnostic("unsupported-command", f"command {command!r} is not claimed")
    if dialect not in claim.dialects:
        return Diagnostic("unsupported-dialect", f"dialect {dialect!r} is not claimed")
    if case.shape not in claim.case_shapes:
        return Diagnostic("unsupported-case-shape", f"case shape {case.shape!r} is not claimed")
    unclaimed = sorted(case.module_tags - set(claim.modules))
    if unclaimed:
        return Diagnostic("unsupported-module", f"module tags outside the claim: {unclaimed}")
    include = set(claim.include)
    if include and set(case.tags).isdisjoint(include):
        return Diagnostic("unsupported-case-tag", f"case carries none of {sorted(include)}")
    exclude = set(claim.exclude)
    if exclude and not set(case.tags).isdisjoint(exclude):
        offending = sorted(set(case.tags) & exclude)
        return Diagnostic("unsupported-case-tag", f"case carries excluded tags: {offending}")
    return None


def unsupported_command(command: str, adapter: Adapter = ADAPTER) -> Envelope:
    """An ``unsupported`` envelope for a command the adapter never claims."""
    diagnostic = Diagnostic("unsupported-command", f"command {command!r} is not claimed")
    return _non_ok(command, "unsupported", diagnostic, adapter)


def error(command: str, diagnostic: Diagnostic, adapter: Adapter = ADAPTER) -> Envelope:
    """An ``error`` envelope carrying ``diagnostic`` (e.g. an unreadable case)."""
    return _non_ok(command, "error", diagnostic, adapter)


def unsupported(command: str, diagnostic: Diagnostic, adapter: Adapter = ADAPTER) -> Envelope:
    """An ``unsupported`` envelope carrying the first-failed-filter ``diagnostic``."""
    return _non_ok(command, "unsupported", diagnostic, adapter)


def _case_ref(path: Path) -> str:
    """The case path relative to the repo root (the `case` envelope field)."""
    root = case_format.find_repo_root()
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:  # pragma: no cover - case outside the repo tree
        return str(path)


def _echo(envelope: Envelope, case: case_format.Case, dialect: str) -> Envelope:
    """Echo the routing fields every compile/run envelope carries."""
    envelope["case"] = _case_ref(case.path)
    envelope["dialect"] = dialect
    envelope["caseShape"] = case.shape
    return envelope


def _boundary_lane_error(case: case_format.Case) -> engine.EngineError:
    # `run` classifies a boundary case out with the api-conformance reason
    # (m-case-format: every boundary case is on the api-conformance lane).
    return engine.EngineError(
        f"{case.path.name}: a boundary case carries no golden SQL; the api-conformance "
        "lane (the API Conformance Suite) verifies it, not compile/run"
    )


def _compile(case: case_format.Case, dialect: str) -> tuple[list[engine.Emission], int]:
    """Compile a claimed case by shape (read / scenario / writeSequence).

    The scenario and writeSequence lanes emit the keyed unit-of-work DML (and, for a
    scenario, the read-lock reads); an error case has no compile artifact (a
    lane-honest ``EngineError`` names the run lane that grades it); any other shape
    falls through to the read compiler, which raises the loud non-read
    ``EngineError`` the caller renders as an ``error``.
    """
    if case.shape == "scenario":
        return engine.compile_scenario_case(case, dialect)
    if case.shape == "writeSequence":
        return engine.compile_write_sequence_case(case, dialect)
    if case.shape == "error":
        # Only the single-connection statement-trigger sub-shape reaches here: the
        # two-connection choreography cases are corpus-declared run-only, as is
        # every boundary case, so `compile_case` short-circuits those earlier.
        raise engine.EngineError(
            f"{case.path.name}: an error case's trigger DML is authored, not compiled "
            "(m-case-format); `run` grades the single-connection trigger"
        )
    return engine.compile_read_case(case, dialect)


def _run(
    case: case_format.Case, dialect: str, port: DbPort
) -> tuple[list[engine.Emission], dict[str, Any]]:
    """Run a claimed case by shape, returning its emissions and observation envelope.

    A scenario / writeSequence run reports only ``roundTrips`` — the envelope carries no
    per-step rows (``additionalProperties: false``), so per-step row correctness is the
    oracle-test gate; a read run additionally records its observed ``rows``; an error
    run records the raised failure's classification (``errorClass`` / ``nativeCode``).
    """
    if case.shape == "scenario":
        emissions, round_trips = engine.run_scenario_case(case, dialect, port)
        return emissions, {"roundTrips": round_trips}
    if case.shape == "writeSequence":
        emissions, round_trips = engine.run_write_sequence_case(case, dialect, port)
        return emissions, {"roundTrips": round_trips}
    if case.shape == "error":
        emissions, error_class, native_code, round_trips = engine.run_error_case(
            case, dialect, port
        )
        return emissions, {
            "errorClass": error_class,
            "nativeCode": native_code,
            "roundTrips": round_trips,
        }
    if case.shape == "boundary":
        raise _boundary_lane_error(case)
    emissions, rows, round_trips = engine.run_read_case(case, dialect, port)
    return emissions, {"rows": rows, "roundTrips": round_trips}


def compile_case(
    case_path: str | Path,
    dialect: str,
    claim: Claim = SNAPSHOT_CLAIM,
    adapter: Adapter = ADAPTER,
) -> Envelope:
    """Compile one case: classify, honor compile-eligibility, then emit statements.

    A run-only case (`compileEligibility`, `m-case-format`) returns the defined
    ``run-only`` status with a ``compile-run-only`` diagnostic; a compile-eligible
    claimed read case returns ``ok`` with its ordered ``emissions`` and round
    trips. Compilation touches no database — the refusing port never sees a row
    request from a well-declared read.
    """
    case = case_format.load_case(Path(case_path))
    diagnostic = classify("compile", dialect, case, claim)
    if diagnostic is not None:
        return _non_ok("compile", "unsupported", diagnostic, adapter)
    run_only = engine.eligibility(case)
    if run_only is not None:
        envelope = _non_ok(
            "compile",
            "run-only",
            Diagnostic("compile-run-only", run_only.reason),
            adapter,
        )
        return _echo(envelope, case, dialect)
    try:
        emissions, round_trips = _compile(case, dialect)
    except engine.EngineError as exc:
        return _non_ok("compile", "error", Diagnostic("compile-failed", str(exc)), adapter)
    envelope = _common("compile", "ok", adapter)
    envelope["emissions"] = [e.to_json() for e in emissions]
    envelope["roundTrips"] = round_trips
    return _echo(envelope, case, dialect)


def run_case(
    case_path: str | Path,
    dialect: str,
    port: DbPort,
    claim: Claim = SNAPSHOT_CLAIM,
    adapter: Adapter = ADAPTER,
) -> Envelope:
    """Run one case (read / scenario / writeSequence) through ``port`` and report its
    emissions and observations."""
    case = case_format.load_case(Path(case_path))
    diagnostic = classify("run", dialect, case, claim)
    if diagnostic is not None:
        return _non_ok("run", "unsupported", diagnostic, adapter)
    try:
        emissions, observations = _run(case, dialect, port)
    except engine.EngineError as exc:
        return _non_ok("run", "error", Diagnostic("run-failed", str(exc)), adapter)
    envelope = _common("run", "ok", adapter)
    envelope["emissions"] = [e.to_json() for e in emissions]
    envelope["observations"] = observations
    return _echo(envelope, case, dialect)
