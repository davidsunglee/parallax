"""The interleaved ``uow`` lane: a scenario whose two `uow` groups interleave —
the optimistic-lock race (`m-opt-lock-012`) and the Isolation Level scenarios
alike — run as two real ``db.transact`` calls held open concurrently over two
dedicated sessions, their steps sequenced across two worker threads in
authored order, and reported as the emissions, round trips, conflict
``actual``, and find rows the run sweep grades.

Each group runs on a session the caller's execution factory opens for this
choreography alone (the scoped ``ProvisionedRun.interleaved_execution`` seam —
a different scoped-control consumer than the ``when.concurrency`` rounds
runner, which drives production routing rather than authored steps). The lane
constructs no connection of its own, and what it destroys to unstick a worker
is only a session it opened. The caller's port serves the case's out-of-band
``given.apply`` statements and the trailing ungrouped verify find, which the
write core this lane consumes from :mod:`~parallax.conformance._lanes.scenario`
runs over that port through a Handle of its own. A
:class:`~parallax.conformance._lanes.turnstile.Turnstile` hands control from
one thread to the other at every step, so there is never a genuine
Python-level race — optimistic mode's own reads take no lock — and a step
hands off only once it is whole: a streamed read's every page is drained
before the turnstile advances, so a peer's commit lands between two
deliveries and never inside one.

One admission guard, on oracle shape: a step stating `expectGraph` is refused
for lack of a `stepGraphs` channel to answer it, so read oracles here are
row-valued only, and a write step, stating no oracle of its own, is asked for
nothing. Which of the rest a sweep routes here is the sweep's own to say
(`test_run_sweep._INTERLEAVED_RUNNER_CASES`); a choreography needing a peer's
DML on the wire BEFORE that peer's own flush edge is left out there, not for
want of a channel here — a real unit of work buffers to its boundary, so that
window never opens and those oracles hold at EVERY isolation level, a pass
asserting nothing about isolation. The run sweep routes to this entry point
explicitly; the façade's ``run_scenario_case`` refuses the shape and names it.
"""

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
    INERT_CLOCK_INSTANT,
    CaseContext,
    GroupState,
    LoweredStep,
    graph_rows,
    run_group_step,
    run_standalone_find,
    scenario_group_step_indices,
    step_query,
)
from parallax.conformance._lanes.turnstile import Turnstile, await_workers
from parallax.conformance._lifecycle_observation import LifecycleObservation, LifecycleRun
from parallax.conformance._mechanism import case_document, envelope
from parallax.conformance._mechanism.envelope import Emission, EngineError
from parallax.conformance._mechanism.given_state import (
    apply_given_apply,
    seed_shadow_from_fixtures,
)
from parallax.conformance._mechanism.model_facts import case_serving_model
from parallax.conformance._mechanism.transaction_control import transact
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core.base import normalize_instant
from parallax.core.unit_work import FixedClock, OptimisticLockConflictError
from parallax.snapshot import handle

__all__ = ["run_interleaved_scenario_case"]


def _empty_group_rows() -> dict[int, list[Mapping[str, object]]]:
    return {}


@dataclass(slots=True)
class _InterleavedGroupResult:
    """One interleaved group's own report: its lowered steps (keyed by
    scenario step index), the conflict's own `actual` affected-row count
    when its LAST write step doomed the group via a genuine optimistic-lock
    conflict (`None` for a group that committed, or that never conflicts),
    any OTHER exception the worker thread raised (re-raised on the main
    thread once both join — never silently swallowed), and every OWN find
    step's own observed rows (keyed by scenario step index) — the group's own
    oracle for `expectRows`, the
    SAME grade the ordinary scenario run lane gives every OTHER find step through
    its `stepRows` observation; without this the caller has no way to grade a
    grouped find at all, only its DML shape."""

    lowered: dict[int, LoweredStep]
    conflict_actual: int | None = None
    failure: BaseException | None = None
    rows: dict[int, list[Mapping[str, object]]] = field(default_factory=_empty_group_rows)
    round_trips: int = 0


def _run_interleaved_group(
    session: ModeledExecution,
    observation: LifecycleObservation,
    context: CaseContext,
    steps: Sequence[Mapping[str, object]],
    indices: Sequence[int],
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
    conflict-write precedent) — caught HERE, its ``actual`` recorded, and the
    transaction aborts (never retried: `m-opt-lock-012`'s own `when.uow` sets no
    ``retryOptimisticConflicts`` opt-in, so :func:`~parallax.core.auto_retry.
    run_with_retry` surfaces it after exactly one attempt). Unlike
    :func:`~parallax.conformance._lanes.scenario._run_uow_group`'s own OWN
    ``doomed``/``rollback: true`` convention
    (an authored, EXPLICIT abort signal independent of any real conflict),
    this lane's ONE conflicting witness (`m-opt-lock-012`) authors
    ``rollback: true``
    ONLY on the step whose OWN flush already conflicts — the CONFLICT itself
    is what dooms the group, so no separate explicit-rollback trigger exists
    here; a genuinely non-conflict-driven interleaved abort is unwitnessed
    and out of scope (pinned semantics #10, "unwitnessed surfaces stay
    honest"). The turnstile only ADVANCES past the group's own last step once
    ``session.database.transact`` itself RETURNS (a REAL commit — the underlying
    port's transaction context manager has committed, not merely that this
    callback's own Python code finished): the OTHER group's next step must
    observe that commit for real, never a same-process illusion of one.

    ``session`` is passed beside the shared ``context`` rather than read out of
    it because the two groups run on two connections: each group's steps execute
    on, and lower in the spelling of, the dedicated session opened for it.

    ``context`` carries the SAME single :class:`TemporalShadow` every group
    shares (the keyed unit-of-work lane's own convention) — safe here ONLY
    because every model this lane witnesses is entirely NON-temporal (the
    tracker is never mutated for these instructions, so two threads never
    contend on it, and this group's own abort has nothing to discard). A
    genuinely temporal interleaved case would need its own per-group tracking
    discipline — the contiguous runner's whole-tracker staging cannot serve two
    groups advancing at once — unwitnessed and out of scope.

    Every OWN find step's observed rows land in ``result.rows`` (keyed by
    scenario step index): the caller's own
    oracle for that step's authored ``expectRows`` — without this, a grouped
    find's own DML is graded but its OBSERVATION never is, so a broken abort
    that left a doomed group's writes durable, or a group opened at the wrong
    Isolation Level, would report well-formed SQL and still pass. Keeping them
    is the one thing this runner does with a step's
    result that the contiguous runner does not.
    """
    lowered: dict[int, LoweredStep] = {}
    state = GroupState()

    def body(tx: handle.Transaction) -> None:
        for position, index in enumerate(indices):
            turnstile.wait_for(index)
            is_last = position == len(indices) - 1
            lowered[index], read = run_group_step(
                tx, session, context, state, steps[index], index, INERT_CLOCK_INSTANT, observation
            )
            if read is not None:
                result.rows[index] = graph_rows(
                    context.model, step_query(steps[index], context.model), read.roots
                )
            if not is_last:
                turnstile.advance()

    committed = False
    try:
        transact(
            session.database, body, concurrency=context.concurrency, isolation=context.isolation
        )
        committed = True
    except OptimisticLockConflictError as exc:
        result.conflict_actual = exc.actual
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


def run_interleaved_scenario_case(
    case: case_format.Case,
    port: CaseDatabase,
    execution_factory: InterleavedExecutionFactory,
) -> tuple[list[Emission], int, int | None, list[list[Mapping[str, object]]]]:
    """Run a two-group interleaved-`uow`-group scenario — the optimistic-lock
    race (`m-opt-lock-012`) and the Isolation Level scenarios alike, whose ONE
    admission guard is on ORACLE SHAPE (a step stating `expectGraph` is REFUSED
    here: this entry point carries no `stepGraphs` channel, so that oracle would
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

    Reports the ordered emissions, total round trips, and — when a group's
    own last write step conflicted — the conflict's ``actual`` affected-row
    count (`then.affectedRows`, the scenario shape's own EXTRA top-level
    assertion only the optimistic-lock race authors; ``None`` when no group
    conflicted), and
    EVERY find step's own observed rows (grouped or ungrouped, in scenario
    step order): the caller's own oracle for
    every authored `expectRows`, the SAME observable the ordinary scenario
    run lane grades for every OTHER find step. Routed to explicitly by the
    run sweep (`test_run_sweep.py`) rather than through `run_scenario_case`/
    `adapter.run_case` — this shape's own peer requirement has no seat in the
    ordinary shape-dispatched entry points, the SAME reasoning the rounds
    runner's own dispatch follows.

    Before either worker thread starts, every execution must DECLARE a trusted
    deterministic-termination contract (:func:`_refuse_untrusted_terminations`):
    an execution that declares none is refused loudly here, rather than
    surfacing only much later as an indefinite hang at
    :func:`~parallax.conformance._lanes.turnstile.await_workers`'s own
    unbounded post-ladder join.
    """
    steps = case_document.scenario_steps(case)
    serving = case_serving_model(case)
    model = models.accepted_model_of(serving.current().model)
    concurrency = case_document.concurrency(case)
    if any("expectGraph" in step for step in steps):
        raise EngineError(
            f"{case.path.name}: this entry point reports emissions, round trips and find "
            "rows, and carries no `stepGraphs` channel — a step stating relationship "
            "contents is an oracle nothing here would answer, so it is refused rather "
            "than silently unasserted"
        )
    groups = scenario_group_step_indices(steps)
    if len(groups) != 2:
        raise EngineError(  # pragma: no cover - defensive: every case reaching this entry has two
            f"{case.path.name}: run_interleaved_scenario_case supports exactly the "
            f"TWO-group interleaved shape, not {len(groups)} uow groups"
        )
    ungrouped = [i for i in range(len(steps)) if i not in {j for js in groups.values() for j in js}]
    (label_a, indices_a), (label_b, indices_b) = groups.items()
    shadow = TemporalShadow()
    seed_shadow_from_fixtures(case, model, shadow)
    apply_given_apply(case, port, shadow)
    instant = normalize_instant(dt.datetime.fromisoformat(INERT_CLOCK_INSTANT))
    # This lane reports no lifecycle oracle, and could not: two connections
    # driven at once have no single root order to state. The run is here so the
    # trailing ungrouped verify find has one to open its own Handle through.
    lifecycle = LifecycleRun()
    observed_a = lifecycle.observation()
    observed_b = lifecycle.observation()
    context = CaseContext(serving, model, concurrency, shadow, case_format.uow_isolation(case))
    turnstile = Turnstile()
    result_a = _InterleavedGroupResult(lowered={})
    result_b = _InterleavedGroupResult(lowered={})
    # Incremental protection: each execution is registered for release the
    # moment it opens, so a second-session failure — or the trust refusal below
    # — releases the first rather than leaking it, and the ordinary exit
    # releases both whatever the choreography did.
    plans = (
        (f"uow-{label_a}", observed_a, indices_a, result_a),
        (f"uow-{label_b}", observed_b, indices_b, result_b),
    )
    with contextlib.ExitStack() as stack:
        executions: dict[str, InterleavedExecution] = {}
        for name, observed, _indices, _result in plans:
            execution = execution_factory(
                serving, clock=FixedClock(instant), lifecycle_provider=observed.provider
            )
            stack.callback(execution.close)
            executions[name] = execution
        _refuse_untrusted_terminations(executions, case.path.name)
        workers = {
            name: (
                threading.Thread(
                    target=_run_interleaved_group,
                    args=(executions[name], observed, context, steps, indices, turnstile, result),
                    name=name,
                ),
                executions[name],
            )
            for name, observed, indices, result in plans
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
    rows_by_index: dict[int, list[Mapping[str, object]]] = {**result_a.rows, **result_b.rows}
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
        rows_by_index[index] = graph_rows(model, step_query(step, model), read.checked().results())
        round_trips += read_observed.round_trips
        lowered[index] = LoweredStep(
            f"/scenario/{index}/objectQuery", read_observed.reads, False, False
        )

    ordered = [lowered[index] for index in sorted(lowered)]
    emissions = envelope.emissions([(step.pointer, step.statements) for step in ordered])
    conflict_actual = result_a.conflict_actual
    if conflict_actual is None:
        conflict_actual = result_b.conflict_actual
    find_rows = [rows_by_index[index] for index in sorted(rows_by_index)]
    return emissions, round_trips, conflict_actual, find_rows
