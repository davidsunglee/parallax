from __future__ import annotations

import contextlib
import datetime as dt
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from parallax.conformance import case_format, models
from parallax.conformance._database_control import (
    CaseDatabase,
    InterleavedExecution,
    InterleavedExecutionFactory,
    ModeledExecution,
)
from parallax.conformance._lanes.scenario import (
    CaseContext,
    GroupState,
    LoweredStep,
    flush_failure,
    group_tx_instant,
    read_table_state,
    refuse_a_conflict_retry_opt_in,
    run_group_step,
    run_standalone_find,
    scenario_group_step_indices,
    step_query,
    step_rows,
)
from parallax.conformance._lanes.turnstile import Turnstile, await_workers
from parallax.conformance._lifecycle_observation import LifecycleObservation, LifecycleRun
from parallax.conformance._mechanism import case_document, envelope
from parallax.conformance._mechanism.envelope import EngineError, ScenarioRun
from parallax.conformance._mechanism.given_state import apply_given_apply
from parallax.conformance._mechanism.model_facts import case_serving_model
from parallax.conformance._mechanism.transaction_control import transact
from parallax.conformance.scripted_clock import FixedClock
from parallax.core.base import normalize_instant
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.snapshot import handle

__all__ = ["run_interleaved_scenario_case"]


def _empty_group_rows() -> dict[int, dict[str, object]]:
    return {}


def _committed() -> dict[str, object]:
    return {"outcome": "committed"}


@dataclass(slots=True)
class _InterleavedGroupResult:
    """One interleaved group's own report: its lowered steps (keyed by
    scenario step index), its fate — committed, or rolled back by the
    optimistic-lock conflict its flush reported (`m-case-format` *Unit fates*) —
    any OTHER exception the worker thread raised (re-raised on the main
    thread once both join — never silently swallowed), and every OWN find
    step's `stepRows` observation (keyed by scenario step index) — the SAME
    observation the ordinary scenario run lane reports for every OTHER find
    step; without this the caller has no way to grade a grouped find at all,
    only its DML shape."""

    lowered: dict[int, LoweredStep]
    fate: dict[str, object] = field(default_factory=_committed)
    failure: BaseException | None = None
    rows: dict[int, dict[str, object]] = field(default_factory=_empty_group_rows)
    round_trips: int = 0


def _run_interleaved_group(
    session: ModeledExecution,
    observation: LifecycleObservation,
    context: CaseContext,
    steps: Sequence[Mapping[str, object]],
    indices: Sequence[int],
    tx_instant: str,
    turnstile: Turnstile,
    result: _InterleavedGroupResult,
) -> None:
    """Run one interleaved group's OWN steps (``indices``, in authored order,
    possibly non-contiguous across the WHOLE scenario) inside ONE real
    ``db.transact`` call on ``session``'s own Handle — the SAME
    :func:`~parallax.conformance._lanes.scenario.run_group_step` interpreter
    :func:`~parallax.conformance._lanes.scenario._run_uow_group` drives over a
    contiguous span,
    generalized to an explicit index list and gated by ``turnstile`` at every
    step. A write step's lowering is therefore recorded BEFORE the group's own
    flush executes it, so a step that later CONFLICTS still reports its own
    well-formed golden DML (`m-opt-lock` "Conflict detection" — the SQL is
    correct, the row count is not).

    The group's own boundary flushes what its last step buffered, and that
    flush may itself raise
    :class:`~parallax.core.unit_work.OptimisticLockConflictError` (the SAME
    signal a caller-driven retry catches, the keyed unit-of-work lane's own
    conflict-write precedent) — caught HERE, recorded as the group's flush
    failure where the flush ran, and the transaction aborts (never retried: a
    case whose groups would resolve the ``retryOptimisticConflicts`` opt-in
    under a positive bound — from `when.uow` or from its root — is refused
    before either worker starts, so
    :func:`~parallax.core.auto_retry.run_with_retry` surfaces the conflict after
    exactly one attempt). Unlike
    :func:`~parallax.conformance._lanes.scenario._run_uow_group`, this lane
    abandons no group: the only rollback it reports is the one a group's own
    conflicting flush causes. The turnstile only ADVANCES past the group's own
    last step once
    ``session.database.transact`` itself RETURNS (a REAL commit — the underlying
    port's transaction context manager has committed, not merely that this
    callback's own Python code finished): the OTHER group's next step must
    observe that commit for real, never a same-process illusion of one.

    ``session`` is passed beside the shared ``context`` rather than read out of
    it because the two groups run on two connections: each group's steps execute
    on, and lower in the spelling of, the dedicated session opened for it. Its
    steps run at ``tx_instant``, the group's own Transaction Instant — the same
    instant ``session``'s Clock answers, so the oracle and the execution plan at
    one value.

    ``context`` carries no case-state tracker, and that is the invariant two
    concurrent sessions rest on: a temporal write settles against what its own
    group's reads retained — the value production's verb is handed, through
    :class:`~parallax.conformance._lanes.scenario.GroupEvidence` — so the oracle
    models nothing the other session could have changed, the two threads share
    no mutable state, and a group's abort leaves nothing behind to discard. A
    write whose plan would need more than those reads retained — a coverage read
    its flush defers, or a second temporal write of a key its group already
    settled — is refused as unwitnessed rather than modeled, because that state
    includes the other session's commits, which only the database knows.

    Every OWN find step's `stepRows` observation lands in ``result.rows`` (keyed
    by scenario step index) — without this, a grouped find's own DML is graded
    but its OBSERVATION never is, so a broken abort that left a doomed group's
    writes durable, or a group opened at the wrong Isolation Level, would report
    well-formed SQL and still pass.
    """
    lowered: dict[int, LoweredStep] = {}
    state = GroupState()
    running: list[int] = []

    def body(tx: handle.Transaction) -> None:
        for position, index in enumerate(indices):
            turnstile.wait_for(index)
            running.append(index)
            is_last = position == len(indices) - 1
            lowered[index], read = run_group_step(
                tx, session, context, state, steps[index], index, tx_instant, observation
            )
            if read is not None:
                result.rows[index] = step_rows(
                    context.model, index, step_query(steps[index], context.model), read.roots
                )
            if not is_last:
                turnstile.advance()
        running.clear()

    committed = False
    try:
        transact(session.database, body, **context.requests)
        committed = True
    except OptimisticLockConflictError as exc:
        at = running[-1] if running else "commit"
        reported = flush_failure(context.model, exc, at)
        result.fate = {"outcome": "rolledBack", "flushFailure": reported}
    except BaseException as exc:  # re-raised on the main thread below
        result.failure = exc
        turnstile.release_all()  # never leave a partner thread hanging on this thread's own defect
    result.lowered = lowered
    result.round_trips = observation.round_trips
    if committed:
        turnstile.advance()


def _refuse_untrusted_terminations(
    executions: Mapping[str, InterleavedExecution], case_name: str
) -> None:
    """Refuse the choreography unless every execution grants termination trust.

    The lane's post-termination join is deliberately unbounded, so a worker it
    cannot unstick hangs there rather than racing the harness. What makes that
    trade sound is a DECLARED contract rather than an inspected shape: a
    structural check — that a session's own close and its transport's are
    callable — passes an implementation whose every rung raises, and that
    implementation hangs the same join anyway. So the refusal happens BEFORE
    either worker thread is constructed, naming EVERY execution that failed to
    declare it rather than stopping at the first, and nothing here calls into an
    execution at all.

    Past this gate, a hang at that join can only mean a grant was untruthful — a
    defect in the declaring type, diagnosable at that exact line.
    """
    defects = [
        f"{label} declares no trusted termination contract "
        f"(`termination_ladder_trusted`), so nothing promises the termination "
        f"ladder can unblock its own I/O"
        for label, execution in executions.items()
        if execution.termination_ladder_trusted is not True
    ]
    if not defects:
        return
    raise EngineError(
        f"{case_name}: the interleaved-group choreography refuses to start — {'; '.join(defects)}"
    )


def _refuse_graph_oracles(steps: Sequence[Mapping[str, object]], case_name: str) -> None:
    if any("expectGraph" in step for step in steps):
        raise EngineError(
            f"{case_name}: this entry point fills no `stepGraphs` channel — a step "
            "stating relationship contents is an oracle nothing here would answer, so it "
            "is refused rather than silently unasserted"
        )


def run_interleaved_scenario_case(
    case: case_format.Case,
    port: CaseDatabase,
    execution_factory: InterleavedExecutionFactory,
) -> ScenarioRun:
    """Run a two-group interleaved-`uow`-group scenario — the optimistic-lock
    race (`m-opt-lock-012`) and the Isolation Level scenarios alike, whose ONE
    admission guard is on ORACLE SHAPE (a step stating `expectGraph` is REFUSED
    here: this entry point fills no `stepGraphs` channel, so that oracle would
    go unasserted — read oracles are row-valued only, and a write step, stating
    no oracle of its own, is asked for nothing):
    each
    declared group on a DEDICATED session of its own (``execution_factory`` —
    this function constructs no connection itself), each a REAL ``db.transact``
    (production routing) whose steps lower in the dialect its OWN connection
    declares, steps sequenced across the two in AUTHORED order
    (:class:`~parallax.conformance._lanes.turnstile.Turnstile`). Neither group
    runs on the caller's ``port``: a stuck worker is unstuck by destroying the
    session it is parked in, and what this lane may destroy is only a session
    it opened for this one choreography. The
    caller's ``port`` therefore serves the case's out-of-band `given.apply`
    statements and any ungrouped step (each witnessed case's own trailing verify
    find), which runs AFTER both groups have resolved.

    Each group runs at its own Transaction Instant — its first write's `at`
    (:func:`~parallax.conformance._lanes.scenario.group_tx_instant`), the rule
    the contiguous lane applies — and the lane models no case state: each
    temporal write settles against its own group's reads (see
    :func:`_run_interleaved_group`).

    Reports a :class:`~parallax.conformance._mechanism.envelope.ScenarioRun`:
    the ordered emissions, total round trips, EVERY find step's `stepRows`
    observation (grouped or ungrouped, in scenario step order), each group's
    fate by label — committed, or rolled back by the conflict its flush
    reported — and, where the case states `then.tableState`, the tables read
    back once both groups have joined. Routed to explicitly by the
    run sweep (`test_run_sweep.py`) rather than through `run_scenario_case`/
    `adapter.run_case` — this shape's own peer requirement has no seat in the
    ordinary shape-dispatched entry points, the SAME reasoning the rounds
    runner's own dispatch follows.

    Before either worker thread starts, every execution must DECLARE a trusted
    deterministic-termination contract (:func:`_refuse_untrusted_terminations`):
    an execution that declares none is refused loudly here, rather than
    surfacing only much later as an indefinite hang at
    :func:`~parallax.conformance._lanes.turnstile.await_workers`'s own
    unbounded post-ladder join. A case whose groups would resolve the
    optimistic-conflict opt-in under a positive bound is refused at the same
    point
    (:func:`~parallax.conformance._lanes.scenario.refuse_a_conflict_retry_opt_in`):
    each group is one turnstile-sequenced production attempt, and a retried
    group would re-run its steps against a turnstile that has already passed
    them.
    """
    steps = case_document.scenario_steps(case)
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    concurrency = case_document.concurrency(case)
    refuse_a_conflict_retry_opt_in(
        case, case_format.effective_options(case), "`when.uow` or `given.databaseOptions`"
    )
    _refuse_graph_oracles(steps, case.path.name)
    groups = scenario_group_step_indices(steps)
    if len(groups) != 2:
        raise EngineError(  # pragma: no cover - defensive: every case reaching this entry has two
            f"{case.path.name}: run_interleaved_scenario_case supports exactly the "
            f"TWO-group interleaved shape, not {len(groups)} uow groups"
        )
    grouped = {index for indices in groups.values() for index in indices}
    ungrouped = [index for index in range(len(steps)) if index not in grouped]
    (label_a, indices_a), (label_b, indices_b) = groups.items()
    apply_given_apply(case, port, None)
    # This lane reports no lifecycle oracle, and could not: two connections
    # driven at once have no single root order to state. The run is here so the
    # trailing ungrouped verify find has one to open its own Handle through.
    lifecycle = LifecycleRun()
    observed_a = lifecycle.observation()
    observed_b = lifecycle.observation()
    context = CaseContext(
        serving,
        model,
        concurrency,
        None,
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    turnstile = Turnstile()
    result_a = _InterleavedGroupResult(lowered={})
    result_b = _InterleavedGroupResult(lowered={})
    # Incremental protection: each execution is registered for release the
    # moment it opens, so a second-session failure — or the trust refusal below
    # — releases the first rather than leaking it, and the ordinary exit
    # releases both whatever the choreography did.
    plans = (
        (f"uow-{label_a}", observed_a, indices_a, group_tx_instant(steps, indices_a), result_a),
        (f"uow-{label_b}", observed_b, indices_b, group_tx_instant(steps, indices_b), result_b),
    )
    with contextlib.ExitStack() as stack:
        executions: dict[str, InterleavedExecution] = {}
        for name, observed, _indices, tx_instant, _result in plans:
            execution = execution_factory(
                serving,
                options=context.options,
                clock=FixedClock(normalize_instant(dt.datetime.fromisoformat(tx_instant))),
                lifecycle_provider=observed.provider,
            )
            stack.callback(execution.close)
            executions[name] = execution
        _refuse_untrusted_terminations(executions, case.path.name)
        workers = {
            name: (
                threading.Thread(
                    target=_run_interleaved_group,
                    args=(
                        executions[name],
                        observed,
                        context,
                        steps,
                        indices,
                        tx_instant,
                        turnstile,
                        result,
                    ),
                    name=name,
                ),
                executions[name],
            )
            for name, observed, indices, tx_instant, result in plans
        }
        for thread, _execution in workers.values():
            thread.start()
        await_workers(workers, turnstile, case.path.name)
    for result in (result_a, result_b):
        if result.failure is not None:
            raise result.failure
    # Each group's writes reach the wire in its own boundary flush — a
    # conflicting flush included, whose gated statement reached the database and
    # reported zero rows — so a group's own steps are reconciled against its own
    # connection's delivery. Reconciled on this thread rather than inside the
    # worker, so a disagreement surfaces where every other failure of this lane
    # does.
    for result, observed in ((result_a, observed_a), (result_b, observed_b)):
        envelope.delivered(
            [
                statement
                for step in result.lowered.values()
                if step.is_write
                for statement in step.statements
            ],
            observed.writes,
            "an interleaved `uow` group",
        )

    lowered: dict[int, LoweredStep] = {**result_a.lowered, **result_b.lowered}
    rows_by_index: dict[int, dict[str, object]] = {**result_a.rows, **result_b.rows}
    # Each group's own transaction counted its own calls; the trailing ungrouped
    # verify finds add theirs below.
    round_trips = sum(result.round_trips for result in (result_a, result_b))
    for index in ungrouped:
        step = steps[index]
        if "write" in step:  # pragma: no cover - no witnessed ungrouped write is doomed-adjacent
            raise EngineError(
                f"{case.path.name}: an ungrouped write step ({index}) beside an "
                "interleaved uow race is unsupported — every witnessed case's own "
                "ungrouped step is a trailing verify find only"
            )
        read, read_observed = run_standalone_find(port, context, step, lifecycle)
        rows_by_index[index] = step_rows(
            model, index, step_query(step, model), read.checked().results()
        )
        round_trips += read_observed.round_trips
        lowered[index] = LoweredStep(
            f"/scenario/{index}/objectQuery", read_observed.reads, False, False
        )

    ordered = [lowered[index] for index in sorted(lowered)]
    emissions = envelope.emissions([(step.pointer, step.statements) for step in ordered])
    units = {label_a: result_a.fate, label_b: result_b.fate}
    observed_rows = [rows_by_index[index] for index in sorted(rows_by_index)]
    then = case.document.get("then")
    table_state = (
        read_table_state(port, model)
        if isinstance(then, Mapping) and "tableState" in then
        else None
    )
    return ScenarioRun(emissions, round_trips, [], observed_rows, [], units, table_state)
