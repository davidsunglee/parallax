"""``parallax.conformance.adapter`` — the in-process conformance adapter core.

Plain functions returning **envelope** dicts: the JSON documents
``m-conformance-adapter`` defines as the wire surface (validated against
``core/schemas/conformance-adapter.schema.json``). ``describe`` reports the
claim; ``compile_case`` / ``run_case`` classify the request against the claim's
filters in contract order and, for a claimed case, emit an ``error`` envelope
until the compile/run lanes come online.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from parallax.conformance import case_format, engine
from parallax.conformance._lifecycle_observation import (
    LifecycleRun,
    StatementIndexError,
    execution_lifecycle_observation,
)
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


def _scenario_lane_error(case: case_format.Case) -> engine.EngineError:
    # A `scenario`-shape case whose top-level `lane` is `api-conformance` (m-
    # snapshot-read-009, `action: access`'s closed-world absence witness): its
    # observable is a per-language surfacing (the developer-facing surface
    # `parallax.snapshot.handle` builds), not a wire-observable golden this
    # lane can grade — the SAME `_boundary_lane_error` precedent, extended to
    # a second shape. A `mutate`-action-only scenario is the one exception:
    # the engine grades the mutate verb itself, including its `expectError`
    # application-lifecycle-error step through the `errors` observation
    # (`m-conformance-adapter`), so the dispatch below never classifies one
    # out.
    return engine.EngineError(
        f"{case.path.name}: this scenario's lane is `api-conformance` (m-case-format); "
        "the API Conformance Suite verifies it, not compile/run"
    )


def _is_scenario_lane_dispatched(case: case_format.Case) -> bool:
    if case.shape != "scenario" or case.document.get("lane") != "api-conformance":
        return False
    return not _scenario_actions_all_mutate(case)


def _scenario_actions_all_mutate(case: case_format.Case) -> bool:
    """Whether the scenario carries lifecycle action steps and every one is a
    `mutate`, including a step's declared `expectError` through the `errors`
    observation (`m-conformance-adapter` / `errorObservation.errorClass`). Such
    an api-conformance-lane scenario stays in the compile/run lanes (the
    finite-pin mutation contrast pair).

    Consulted only for an api-conformance-lane scenario, which is authored to
    assert a per-language surfacing. An `access` step there names a
    representation the wire cannot see, so the case dispatches to the API
    Conformance Suite — unlike a harness-lane `access`, which the engine grades
    against `expectGraph`."""
    when = case.document.get("when")
    if not isinstance(when, Mapping):
        return False
    steps = cast("Mapping[str, object]", when).get("scenario")
    if not isinstance(steps, list):
        return False
    actions = [
        cast("Mapping[str, object]", step)["action"]
        for step in cast("list[object]", steps)
        if isinstance(step, Mapping) and "action" in cast("Mapping[str, object]", step)
    ]
    return bool(actions) and all(action == "mutate" for action in actions)


def _compile(case: case_format.Case, dialect: str) -> tuple[list[engine.Emission], int]:
    """Compile a claimed case by shape (read / scenario / writeSequence).

    The scenario and writeSequence lanes emit the keyed unit-of-work DML (and, for a
    scenario, the read-lock reads); an error case has no compile artifact (a
    lane-honest ``EngineError`` names the run lane that grades it); every reachable
    conflict case declares ``compileEligibility: run-only`` (m-opt-lock's own
    single-connection concurrency intent — `compile_case` already answers the
    defined ``run-only`` envelope before ever reaching here), so a conflict case
    reaching this dispatch is mis-declared, named loudly rather than silently
    falling through to the read compiler's unrelated ``EngineError``; any other
    shape falls through to the read compiler, which raises the loud non-read
    ``EngineError`` the caller renders as an ``error``.
    """
    if _is_scenario_lane_dispatched(case):
        raise _scenario_lane_error(case)
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
    if case.shape == "conflict":
        raise engine.EngineError(
            f"{case.path.name}: a conflict case's single-connection concurrency intent "
            "(m-opt-lock) is always declared `compileEligibility: run-only`; a reachable "
            "conflict case missing that declaration is mis-declared, not compilable"
        )
    return engine.compile_read_case(case, dialect)


def _read_observations(
    case: case_format.Case, dialect: str, port: DbPort, lifecycle: LifecycleRun
) -> dict[str, Any]:
    """A read case's own observation shape (m-case-format "Read result form"):
    ``then.graphs`` (a milestone-set snapshot read) / ``then.graph`` (a deep
    fetch or a plain instance-form materialization) / ``then.rows`` (row-form) —
    a case satisfies its `then` requirement with exactly one, so exactly one of
    these three run lanes ever answers it.

    ``when.stream`` selects WITHIN each graph lane rather than beside them,
    because it names the DELIVERY and not the result: a streamed case reports the
    same observation its eager peer does — ``graph``, or ``graphs`` for a
    milestone-set read — and running the eager read to produce it would match the
    case's result while producing none of the page partition the case states
    (`m-conformance-adapter` *Streamed reads*). Its ``emissions`` are the
    delivery's own — every page's statements in execution order, read off the
    Database Calls the Snapshot Stream publishes, like every other lane's.
    """
    then = case.document.get("then")
    when = case.document.get("when")
    streamed = isinstance(when, Mapping) and "stream" in when
    if isinstance(then, Mapping) and "graphs" in then:
        run_graphs = engine.run_streamed_graphs_case if streamed else engine.run_graphs_case
        emissions, graphs, round_trips = run_graphs(case, dialect, port, lifecycle)
        return {
            "emissions": emissions,
            "observations": {"graphs": graphs, "roundTrips": round_trips},
        }
    if streamed or (isinstance(then, Mapping) and "graph" in then):
        run = engine.run_stream_case if streamed else engine.run_graph_case
        graph_emissions, graph, round_trips, stored_data_issues = run(
            case, dialect, port, lifecycle
        )
        observations: dict[str, Any] = {"graph": graph, "roundTrips": round_trips}
        if stored_data_issues is not None:
            observations["storedDataIssues"] = stored_data_issues
        return {"emissions": graph_emissions, "observations": observations}
    emissions, rows, round_trips = engine.run_read_case(case, dialect, port, lifecycle)
    return {"emissions": emissions, "observations": {"rows": rows, "roundTrips": round_trips}}


def _report_execution_lifecycle(
    case: case_format.Case,
    observations: dict[str, Any],
    lifecycle: LifecycleRun,
    emissions: list[engine.Emission],
) -> None:
    """Attach the `executionLifecycle` observation for a case authoring the oracle.

    The key is optional and additive (`m-conformance-adapter`) and reported
    exactly where a case asks for it, because a case not authoring it states
    nothing about the stream and the run sweep admits no observed key a case
    left unasserted.
    """
    then = case.document.get("then")
    if not isinstance(then, Mapping) or "executionLifecycle" not in then:
        return
    try:
        observations["executionLifecycle"] = execution_lifecycle_observation(
            lifecycle.roots,
            [emission.sql for emission in emissions],
            lifecycle.resolving_read_calls,
        )
    except StatementIndexError as exc:
        raise engine.EngineError(f"{case.path.name}: {exc}") from exc


def _run(
    case: case_format.Case, dialect: str, port: DbPort, lifecycle: LifecycleRun
) -> tuple[list[engine.Emission], dict[str, Any]]:
    """Run a claimed case by shape, returning its emissions and observation envelope.

    A read run records its observed ``rows`` / ``graph`` / ``graphs``
    (:func:`_read_observations`); a writeSequence run records the committed
    ``tableState`` read back from the model tables (the `m-conformance-adapter`
    write-sequence observation); a conflict run (m-opt-lock) records the FINAL
    ``affectedRows`` (single-attempt, or the last of a ``when.attempts`` retry
    sequence) and, when the case authors it, the resulting ``tableState``; an
    error run records the raised failure's classification (``errorClass`` /
    ``nativeCode``). A scenario run reports the contract observations
    (``roundTrips``, plus one ``errors`` entry per `expectError` step whose
    verb raised its declared application-lifecycle error, one ``stepGraphs``
    entry per step declaring `expectGraph` in either placement — an `access`
    step's retained view, or an include-bearing read step's own materialized
    graph — and one ``stepRows`` entry per read step it drove, carrying the values
    that step published, which is what the run sweep grades against each step's
    ``expectRows``). A rejected run touches no database and no port: it reports
    the classified ``rejectedRule`` with ``roundTrips: 0`` (m-conformance-
    adapter).
    """
    if _is_scenario_lane_dispatched(case):
        raise _scenario_lane_error(case)
    if case.shape == "scenario":
        run = engine.run_scenario_case(case, dialect, port, lifecycle)
        scenario_observations: dict[str, Any] = {"roundTrips": run.round_trips}
        if run.errors:
            scenario_observations["errors"] = run.errors
        if run.step_rows:
            scenario_observations["stepRows"] = run.step_rows
        if run.step_graphs:
            scenario_observations["stepGraphs"] = run.step_graphs
        return run.emissions, scenario_observations
    if case.shape == "writeSequence":
        emissions, table_state, round_trips = engine.run_write_sequence_case(
            case, dialect, port, lifecycle
        )
        return emissions, {"tableState": table_state, "roundTrips": round_trips}
    if case.shape == "conflict":
        emissions, affected_rows, table_state, round_trips = engine.run_conflict_case(
            case, dialect, port, lifecycle
        )
        observations: dict[str, Any] = {"affectedRows": affected_rows, "roundTrips": round_trips}
        if table_state is not None:
            observations["tableState"] = table_state
        return emissions, observations
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
    if case.shape == "rejected":
        rule = engine.run_rejected_case(case)
        return [], {"rejectedRule": rule, "roundTrips": 0}
    result = _read_observations(case, dialect, port, lifecycle)
    return result["emissions"], result["observations"]


def _rejected_shape_run_only(adapter: Adapter) -> Envelope:
    # A `rejected` case carries no golden SQL BY CONSTRUCTION (`then.statements` is
    # disallowed, m-case-format): it is implicitly run-graded, a shape-intrinsic
    # rule needing no per-case `compileEligibility` authoring (m-conformance-adapter)
    # — unlike the query-result-dependent run-only cases above.
    return _non_ok(
        "compile",
        "run-only",
        Diagnostic(
            "compile-run-only",
            "a rejected case carries no golden SQL by construction; it is implicitly "
            "run-graded (m-conformance-adapter)",
        ),
        adapter,
    )


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
    request from a well-declared read. A `rejected` case answers the same
    ``run-only`` envelope unconditionally — its run-only status is shape-intrinsic,
    not authored per-case (see :func:`_rejected_shape_run_only`).
    """
    case = case_format.load_case(Path(case_path))
    diagnostic = classify("compile", dialect, case, claim)
    if diagnostic is not None:
        return _non_ok("compile", "unsupported", diagnostic, adapter)
    if case.shape == "rejected":
        return _echo(_rejected_shape_run_only(adapter), case, dialect)
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
    lifecycle = LifecycleRun()
    try:
        emissions, observations = _run(case, dialect, port, lifecycle)
        _report_execution_lifecycle(case, observations, lifecycle, emissions)
    except engine.EngineError as exc:
        return _non_ok("run", "error", Diagnostic("run-failed", str(exc)), adapter)
    envelope = _common("run", "ok", adapter)
    envelope["emissions"] = [e.to_json() for e in emissions]
    envelope["observations"] = observations
    return _echo(envelope, case, dialect)
