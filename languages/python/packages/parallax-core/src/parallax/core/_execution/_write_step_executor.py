from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, cast, overload

from parallax.core._execution._unit_work.effects import (
    allocated_keys,
    enforce_affected_rows,
    returns_rows,
)
from parallax.core._execution._write_lowering import LoweringCursor
from parallax.core.db_port import (
    DatabaseConnection,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    OrderedWriteResultIntegrityError,
    OrderedWriteResultInterrupted,
    OrderedWriteTransport,
    StatementFailed,
    StatementNotExecuted,
)
from parallax.core.diagnostics import qualified_type
from parallax.core.execution_lifecycle._activity import (
    ActivityTarget,
    FlushActivity,
    OrderedCallObservation,
)
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.write_plan.payload import PatchedDocument, WritePayloadPreparer
from parallax.core.write_plan.steps import (
    PlannedDelete,
    PlannedInsert,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

__all__ = ["WriteStepExecutor"]

_ORDERED_STATEMENTS: Final = 64
"""The most statements one ordered write transport invocation presents. It
bounds the original and lowered statement pairs live at once, and how far past
a shortfall not yet enforced the database may already have run; a longer run of
effects continues in another invocation once this one is enforced."""


class WriteStepExecutor:
    """Lowers, executes, and enforces sequences of Planned Steps on one
    attempt's connection.

    It holds what every execution of its attempt shares — the connection, the
    connection's ordered write transport, the adopted planner's payload
    preparer, and the model — and no Flush: each invocation is handed the
    Flush it runs inside, and retains neither that Flush nor the steps after
    returning.
    """

    __slots__ = ("_connection", "_meta", "_ordered", "_payloads")

    def __init__(
        self,
        connection: DatabaseConnection,
        *,
        payloads: WritePayloadPreparer,
        meta: Metamodel,
    ) -> None:
        self._connection = connection
        # Read once: a connection's transport capability is fixed for its
        # lifetime, and everything this executes runs on this connection.
        self._ordered = connection.ordered_write_transport
        self._payloads = payloads
        self._meta = meta

    def execute(
        self,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        allocates: bool,
        flush: FlushActivity,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]:
        """Lower, execute, and enforce each of ``steps`` in order as calls of
        ``flush``, and answer the keys the database allocated, in step order,
        where ``allocates`` asks for any. The payloads lowering demands are
        handed to ``capture_insert`` and ``capture_revision`` as
        :class:`~parallax.core._execution._write_lowering.LoweringCursor`
        describes, where they are given; executing decides nothing of them.

        Each statement stores the payload the preparer prepares for it when its
        turn comes. A temporal mutation's effect on its predecessor precedes the
        rows it opens, so a failure there aborts BEFORE those rows ever execute.
        A step that runs alone is lowered only once every earlier step has been
        enforced, and nothing is taken ahead of that but the one step a run
        looks at to find where it ends, which waits unprepared. Where the
        connection has ordered write transport, a run of two or more contiguous
        count-only effects on one row each is instead lowered whole and
        presented together before any of it is enforced (:meth:`_run_ordered`).
        A run of contiguous compatible single-entry inserts is inserted by one
        multi-row statement (:meth:`_run_grouped_insert`), each insert remaining
        its own step.

        This performs NO classification of its own: the adopted Write Planner
        already spent the concurrency mode while settling each step, and this
        reports only the driver's count to
        :func:`~parallax.core.unit_work.enforce_affected_rows`, which owns the
        authoritative reading of the step's Affected Rows Policy (ADR 0048).
        That enforcement runs inside its own attribution bracket, because a
        shortfall is judged AFTER the call it judges has already completed: the
        bracket is what lets the Flush's failure name that completed call
        instead of the enforcement being read as a failure of the Flush itself.

        An insert whose key the database allocates for a row the steps record
        answers that key: it runs as row-producing DML, core reads the key from
        the rows it returned (:func:`~parallax.core.unit_work.allocated_keys`)
        inside the same bracket, and the keys are answered in step order.
        """
        allocated: list[object] = []
        transport = self._ordered
        cursor = LoweringCursor(
            steps,
            self._payloads,
            self._meta,
            self._connection.dialect,
            capture_insert=capture_insert,
            capture_revision=capture_revision,
        )
        step = cursor.take()
        while step is not None:
            if transport is not None:
                parameter_ceiling = cursor.ordered_parameter_ceiling(step)
                if parameter_ceiling is not None:
                    step = self._run_ordered(step, parameter_ceiling, cursor, transport, flush)
                    continue
            first = cursor.grouped_insert_start(step)
            if first is not None:
                step = self._run_grouped_insert(first, cursor, flush)
                continue
            statement = cursor.lowered(step)
            if allocates and returns_rows(step):
                allocated.extend(self._run_returning_insert(step, statement, flush))
            else:
                self._run_single(step, statement, flush)
            step = cursor.take()
        return tuple(allocated)

    def execute_with_count(
        self, step: PlannedUpdate | PlannedDelete, /, *, flush: FlushActivity
    ) -> int:
        """Lower, execute, and enforce ``step`` alone as one call of
        ``flush``, exactly as :meth:`execute` runs a step alone, and answer the
        affected-row count the driver reported once enforcement accepted it."""
        cursor = LoweringCursor((step,), self._payloads, self._meta, self._connection.dialect)
        return self._run_single(step, cursor.lowered(step), flush)

    def _run_ordered(
        self,
        first: PlannedStep,
        parameter_ceiling: int,
        cursor: LoweringCursor,
        transport: OrderedWriteTransport,
        flush: FlushActivity,
    ) -> PlannedStep | None:
        """Present ``first`` and the effects following it in one ordered
        transport invocation, enforce what it established, and answer the step
        after the run — taken from ``cursor`` but not lowered — or ``None``
        where ``cursor`` ran out.

        The step after ``first`` is taken before anything is lowered: where
        transport cannot carry it, or none remains, ``first`` would be the
        run's only effect and runs alone instead.

        Otherwise the run ends before a step transport cannot carry, and at
        :data:`_ORDERED_STATEMENTS` before another step is even taken. Lowering
        a later effect may fail ordinarily: the effects already lowered are
        then presented and enforced as they were selected, and only if they
        succeed does that failure propagate. ``first`` failing presents
        nothing, and a control-flow or fatal exception presents none of them.
        """
        following = cursor.take()
        following_ceiling = (
            None if following is None else cursor.ordered_parameter_ceiling(following)
        )
        if following is None or following_ceiling is None:
            self._run_single(first, cursor.lowered(first), flush)
            return following
        invocation = OrderedInvocation()
        invocation.append(first, cursor.lowered_within(first, parameter_ceiling))
        failure: Exception | None = None
        capped = True
        while True:
            try:
                invocation.append(following, cursor.lowered_within(following, following_ceiling))
            except Exception as error:
                failure = error
                break
            following = None
            if len(invocation) >= _ORDERED_STATEMENTS:
                break
            following = cursor.take()
            if following is None:
                capped = False
                break
            following_ceiling = cursor.ordered_parameter_ceiling(following)
            if following_ceiling is None:
                capped = False
                break
        try:
            _run_ordered_invocation(invocation, transport, flush)
        except BaseException:
            # The prefix's own failure is the one raised; the lowering failure
            # it overtook is dropped rather than kept reachable from it.
            failure = None
            raise
        _raise_held(failure)
        return cursor.take() if capped else following

    def _run_grouped_insert(
        self, first: PlannedInsert, cursor: LoweringCursor, flush: FlushActivity
    ) -> PlannedStep | None:
        """Insert ``first`` and the compatible inserts following it with one
        statement (:meth:`LoweringCursor.lowered_grouped_insert`), and answer
        the step after the run — taken from ``cursor`` but not lowered — or
        ``None`` where ``cursor`` ran out.

        The statement is one ordinary Database Call, enforced as an insert is,
        and its failure is the whole statement's own, however many objects its
        rows belong to: it is neither attributed to one of the inserts nor
        replayed one insert at a time. A later insert failing ordinarily to be
        prepared ends the run: the inserts appended before it are inserted as
        selected, and only if they succeed does that failure propagate.
        ``first`` failing inserts nothing, and a control-flow or fatal exception
        inserts none of the run. The step after a run that reached its capacity
        is taken only once the run's statement has run.
        """
        statement, following, failure = cursor.lowered_grouped_insert(first)
        try:
            self._run_single(first, statement, flush)
        except BaseException:
            # The statement's own failure is the one raised; the preparation
            # failure it overtook is dropped rather than kept reachable from it.
            failure = None
            raise
        _raise_held(failure)
        return cursor.take() if following is None else following

    def _run_single(
        self, step: PlannedStep, statement: LoweredStatement, flush: FlushActivity
    ) -> int:
        connection = self._connection
        with flush.database_call(statement, "write", step.entity) as call:
            affected = connection.execute_write(
                connection.dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
            call.write_completed(affected)
        with flush.enforcing(call):
            enforce_affected_rows(step, affected)
        return affected

    def _run_returning_insert(
        self, step: PlannedInsert, statement: LoweredStatement, flush: FlushActivity
    ) -> tuple[object, ...]:
        connection = self._connection
        with flush.database_call(statement, "write", step.entity) as call:
            rows = connection.execute(
                connection.dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
            call.write_rows_completed(rows)
        with flush.enforcing(call):
            return allocated_keys(step, rows)


def _run_ordered_invocation(
    invocation: OrderedInvocation, transport: OrderedWriteTransport, flush: FlushActivity
) -> None:
    """Present ``invocation`` through ``transport`` in one call observed by
    ``flush``, then enforce, in original order, what the result established.

    The whole result is proved well formed before any call finishes from it or
    any count is enforced, so a malformed entry outranks an earlier shortfall.
    """
    invocation.seal()
    with flush.ordered_calls(invocation) as observation:
        result = observation.invoke(transport, invocation)
        _validate_ordered_result(result, len(invocation))
        observation.finish_calls(result)
        _enforce_ordered_result(invocation, result, observation)


class OrderedInvocation(Sequence[LoweredStatement]):
    """The statements one ordered transport invocation presents, each held
    with the exact original step it was lowered from.

    Transport and observation read it as the statements; enforcement reads
    each original back by position. It is sealed before it is presented and
    stays unchanged until its result has been enforced.
    """

    __slots__ = ("_sealed", "_statements", "_steps")

    def __init__(self) -> None:
        self._steps: list[PlannedStep] = []
        self._statements: list[LoweredStatement] = []
        self._sealed = False

    def append(self, step: PlannedStep, statement: LoweredStatement) -> None:
        if self._sealed:
            raise RuntimeError("a presented ordered invocation admits no further statement")
        self._steps.append(step)
        self._statements.append(statement)

    def seal(self) -> None:
        self._sealed = True

    def __len__(self) -> int:
        return len(self._statements)

    @overload
    def __getitem__(self, index: int, /) -> LoweredStatement: ...

    @overload
    def __getitem__(self, index: slice, /) -> Sequence[LoweredStatement]: ...

    def __getitem__(self, index: int | slice, /) -> LoweredStatement | Sequence[LoweredStatement]:
        return self._statements[index]

    def step(self, index: int) -> PlannedStep:
        return self._steps[index]

    def target(self, index: int) -> ActivityTarget:
        return self._steps[index].entity


def _raise_held(failure: Exception | None) -> None:
    """Raise ``failure``, the ordinary failure a run stopped at, once the steps
    selected before it have succeeded."""
    if failure is not None:
        raise failure


def _integrity(problem: str) -> OrderedWriteResultIntegrityError:
    return OrderedWriteResultIntegrityError(f"an ordered write transport result {problem}")


def _validate_ordered_result(result: object, presented: int) -> None:
    """Refuse ``result`` unless it is a well-formed answer for ``presented``
    statements.

    The whole structure is checked before anything reads it: its closed form,
    an outcome or partition for exactly the statements presented, nonnegative
    integer counts, Exception failures, and confirmed non-execution only after
    a confirmed failure. An interrupted result's unsent suffix is explained by
    the interruption itself.
    """
    failed = False
    for index, outcome in enumerate(_confirmed(result, presented)):
        if type(outcome) is int:
            if outcome < 0:
                raise _integrity(f"counts a negative number of rows for statement {index}")
        elif isinstance(outcome, StatementFailed):
            _require_exception(outcome.error, f"statement {index}'s failure")
            failed = True
        elif isinstance(outcome, StatementNotExecuted):
            if not failed:
                raise _integrity(
                    f"reports statement {index} not executed after no confirmed failure"
                )
        else:
            raise _integrity(f"reports a {qualified_type(outcome)} for statement {index}")


def _confirmed(result: object, presented: int) -> tuple[object, ...]:
    """``result``'s confirmed outcomes, once its form accounts for exactly
    ``presented`` statements."""
    match result:
        case OrderedWriteResultComplete():
            confirmed = _outcomes(result.outcomes)
            if len(confirmed) != presented:
                raise _integrity(f"answers {len(confirmed)} outcomes for {presented} statements")
        case OrderedWriteResultInterrupted():
            confirmed = _outcomes(result.confirmed)
            unconfirmed = _statement_count(result.unconfirmed_count, "unconfirmed")
            unsent = _statement_count(result.unsent_count, "unsent")
            if len(confirmed) + unconfirmed + unsent != presented:
                raise _integrity(
                    f"partitions {len(confirmed)} confirmed, {unconfirmed} unconfirmed, and "
                    f"{unsent} unsent statements of {presented}"
                )
            _require_exception(result.error, "its interruption")
        case _:
            raise _integrity(
                f"is a {qualified_type(result)}, neither a complete nor an interrupted result"
            )
    return confirmed


def _outcomes(outcomes: object) -> tuple[object, ...]:
    if type(outcomes) is not tuple:
        raise _integrity(f"holds its outcomes in a {qualified_type(outcomes)}, not a tuple")
    return cast("tuple[object, ...]", outcomes)


def _statement_count(count: object, name: str) -> int:
    if type(count) is not int or count < 0:
        raise _integrity(
            f"counts its {name} statements with a {qualified_type(count)} that is no "
            "nonnegative integer"
        )
    return count


def _require_exception(error: object, name: str) -> None:
    if not isinstance(error, Exception):
        raise _integrity(f"reports {name} as a {qualified_type(error)}, not an Exception")


def _enforce_ordered_result(
    invocation: OrderedInvocation, result: OrderedWriteResult, observation: OrderedCallObservation
) -> None:
    """Interpret ``result``'s confirmed outcomes in original order, each
    against its own original, then raise the interruption that ended it.

    A count goes to the unit of work's enforcement, and a statement failure is
    raised as itself, each attributed to its own call. An earlier shortfall
    therefore outranks a later statement failure or interruption, and nothing
    runs after the first failure.
    """
    confirmed = (
        result.outcomes if isinstance(result, OrderedWriteResultComplete) else result.confirmed
    )
    for index, outcome in enumerate(confirmed):
        with observation.enforcing(index):
            if isinstance(outcome, StatementFailed):
                raise outcome.error
            # Confirmed non-execution only ever follows a confirmed failure,
            # which has already been raised.
            enforce_affected_rows(invocation.step(index), cast("int", outcome))
    if isinstance(result, OrderedWriteResultInterrupted):
        raise result.error
