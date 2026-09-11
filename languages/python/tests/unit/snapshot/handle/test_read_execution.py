"""The two production execution policies, each through the read it begins and
every capability of that read.

A policy answers a begun read, and a begun read is a bracket around a body the
Read Scope hands it, so what it is can only be stated by what the body sees
when it runs: which activity is open, what has already happened to the unit of
work, and which port, Concurrency Preference, and observation ledger arrived
with it. Every case here therefore passes a recording body and grades the
moment that body ran.

That is where the two orderings the handles used to each restate now live. A
participating eager read force-flushes and then opens its Read INSIDE that
flush, so the dependency Write Batch is the Read's ordered sibling under one
attempt; a participating page does the same around its Stream Batch. A
standalone read and a standalone page flush nothing and own their roots, and a
standalone read is begun by adopting the Serving Model's current selection —
once per operation, retained for everything done through that read, and named
on whatever ordinary failure escapes it.

What the ladder ABOVE these does is `test_read_scope.py`'s subject, and what a
whole read answers stays the public-surface suites'.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import pytest

from parallax.core.db_port import DatabaseConnection
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ReadStarted,
    SnapshotStreamStarted,
)
from parallax.core.execution_lifecycle._activity import (
    ActivityTarget,
    SnapshotStreamActivity,
    installed_lifecycle,
    open_transaction_root,
)
from parallax.core.execution_lifecycle.testing import (
    RecordedRoot,
    RecordingLifecycleProvider,
)
from parallax.core.unit_work import (
    Concurrency,
    FixedClock,
    KeyedWrite,
    TransactionSettings,
    UnitOfWork,
    WriteBatchTrigger,
    WritePlan,
    run_unit_of_work,
)
from parallax.core.unit_work.instructions import PreparedKeyedWrite, prepare_typed_write
from parallax.snapshot.handle import ExecutionFailure, build_write_planner, prepare_model
from parallax.snapshot.handle import _read_scope as read_scope_module
from parallax.snapshot.handle._publication import SelectedReadModel, ServingModel, read_projection
from parallax.snapshot.handle._read_scope import ReadInputs
from tests._support.db_port import RefusingAdapter, ScriptedAdapter
from tests._support.model_capabilities import cataloged_for, graph_construction_for
from tests._support.planner_probes import TEST_SUBJECT_IDENTITY
from tests.unit._transact_support import ACCOUNT, FIXED

# The two production adapters are what this suite grades, and module privacy is
# what closes their construction — so they are reached here exactly as the
# module's own factories reach them, and nowhere else.
_Standalone: Final = read_scope_module._StandaloneExecution  # pyright: ignore[reportPrivateUsage]
_Participating: Final = read_scope_module._ParticipatingExecution  # pyright: ignore[reportPrivateUsage]

_META: Final = cataloged_for(ACCOUNT).meta
_SELECTED: Final = SelectedReadModel(
    edition="test", model=cataloged_for(ACCOUNT), construction=graph_construction_for(ACCOUNT)
)
_SERVING: Final = ServingModel(prepare_model(ACCOUNT, edition="test"))


class _Target:
    """An activity target whose spelling costs nothing to read."""

    @property
    def canonical(self) -> str:
        return "parallax.compatibility.Account"


_TARGET: Final[ActivityTarget] = _Target()


@dataclass(frozen=True, slots=True)
class _Ran:
    """One recorded body run: what it was handed, and what had happened by then."""

    activity: object
    inputs: ReadInputs
    transitions: tuple[str, ...]
    flushes: int


_ANSWER: Final = object()


class _Body:
    """A recording body: it answers a sentinel and records the moment it ran.

    The transitions and the flush count are read INSIDE the call rather than
    after it, which is the whole point — an ordering claim about a bracket is
    unprovable from the outside, where every event has already been delivered.
    """

    def __init__(
        self,
        provider: RecordingLifecycleProvider | None = None,
        flushes: _Flushes | None = None,
    ) -> None:
        self.runs: list[_Ran] = []
        self._provider = provider
        self._flushes = flushes

    def __call__(self, activity: object, inputs: ReadInputs) -> object:
        self.runs.append(
            _Ran(
                activity,
                inputs,
                _transitions(self._provider),
                0 if self._flushes is None else len(self._flushes.plans),
            )
        )
        return _ANSWER

    @property
    def only(self) -> _Ran:
        (run,) = self.runs
        return run


class _Flushes:
    """Every Write Plan the unit of work handed its executor, in flush order."""

    def __init__(self) -> None:
        self.plans: list[WritePlan] = []
        self.triggers: list[WriteBatchTrigger] = []

    def __call__(self, plan: WritePlan, *, trigger: WriteBatchTrigger) -> None:
        self.plans.append(plan)
        self.triggers.append(trigger)


def _transitions(provider: RecordingLifecycleProvider | None) -> tuple[str, ...]:
    if provider is None:
        return ()
    return tuple(type(event).__name__ for root in provider.roots for event in root.events)


def _events(root: RecordedRoot) -> list[str]:
    return [type(event).__name__ for event in root.events]


def _parentage(root: RecordedRoot) -> list[tuple[str, int, int | None]]:
    def named(event: ExecutionEvent) -> tuple[str, int, int | None]:
        return (type(event).__name__, event.activity_id, event.parent_activity_id)

    return [named(event) for event in root.events]


def _account_insert(account_id: int) -> PreparedKeyedWrite:
    prepared = prepare_typed_write(
        KeyedWrite("insert", "Account", ({"id": account_id, "owner": "N", "balance": 5},)), _META
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _participating[T](
    run: Callable[[Any, UnitOfWork], T],
    *,
    conn: DatabaseConnection | None = None,
    provider: RecordingLifecycleProvider | None = None,
    concurrency: Concurrency = "optimistic",
    flushes: _Flushes | None = None,
) -> T:
    """One physical attempt's collaborators, wired as ``Database.transact`` wires
    them, with ``run`` standing in for the transaction the closure would receive.

    The flush executor records rather than lowers: what these cases grade is
    WHEN a flush happened relative to a body, never what its statements were.
    """
    port = conn if conn is not None else RefusingAdapter()
    executor = flushes if flushes is not None else _Flushes()
    root = open_transaction_root(
        installed_lifecycle(provider),
        concurrency=concurrency,
        retries=0,
        retry_optimistic_conflicts=False,
        isolation=None,
        extra_retriable=None,
    )
    with root as invocation, invocation.attempt("test") as attempt:

        def in_a_unit_of_work(uow: UnitOfWork) -> T:
            execution = _Participating(
                _SELECTED, uow, attempt, ReadInputs(port, uow.settings.concurrency, uow)
            )
            return run(execution, uow)

        answered = run_unit_of_work(
            in_a_unit_of_work,
            settings=TransactionSettings(concurrency=concurrency),
            clock=FixedClock(FIXED),
            meta=_META,
            flush_executor=executor,
            write_batch_opening=attempt.write_batch,
            planner=build_write_planner(_META),
            subject_identity=TEST_SUBJECT_IDENTITY,
        )
        attempt.committed()
        return answered


# --------------------------------------------------------------------------- #
# begin: the read each policy answers                                          #
# --------------------------------------------------------------------------- #
def test_each_policy_answers_the_selection_it_was_built_with() -> None:
    # A standalone execution adopts from its Serving Model at each `begin`, and
    # a participating one answers itself, over the transaction's fixed record:
    # what both promise is that the record arrives through the begun read
    # rather than off the handle.
    runtime = ScriptedAdapter().open()
    standalone = _Standalone(None, _SERVING, runtime)
    current = read_projection(_SERVING.current())
    assert standalone.begin().selected is current
    assert standalone.begin().selected is current

    def run(execution: Any, _uow: UnitOfWork) -> None:
        assert execution.begin() is execution
        assert execution.begin().selected is _SELECTED

    _participating(run)


def test_a_standalone_begin_adopts_once_per_operation_and_retains_it() -> None:
    # Adoption is per operation: two begun reads over one Serving Model may
    # differ once a publication lands between them, and the earlier one keeps
    # what it adopted however long it lives — a publication reaches the next
    # operation and never an existing read.
    a = prepare_model(ACCOUNT, edition="a")
    b = prepare_model(ACCOUNT, edition="b")
    serving = ServingModel(a)
    execution = _Standalone(None, serving, ScriptedAdapter().open())

    first = execution.begin()
    serving.publish(b, expected=a)
    second = execution.begin()

    assert first.selected is read_projection(a)
    assert second.selected is read_projection(b)
    assert (first.selected.edition, second.selected.edition) == ("a", "b")
    assert first.selected is read_projection(a)


# --------------------------------------------------------------------------- #
# eager: the standalone bracket                                                #
# --------------------------------------------------------------------------- #
def test_a_standalone_eager_read_runs_inside_a_read_root_of_its_own() -> None:
    provider = RecordingLifecycleProvider()
    runtime = ScriptedAdapter().open()
    execution = _Standalone(installed_lifecycle(provider), _SERVING, runtime)
    body = _Body(provider)

    assert execution.begin().eager(_TARGET, "typed", body) is _ANSWER

    (root,) = provider.roots
    assert root.execution.kind == "read"
    # The body ran with the Read open and its connection already taken, and
    # nothing else around it: no flush, no batch, and no activity but the two
    # ends of that connection.
    assert body.only.transitions == ("ReadStarted", "AcquisitionStarted", "AcquisitionFinished")
    assert _events(root) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]
    started = root.events[0]
    assert isinstance(started, ReadStarted)
    assert started.edition == "test"


def test_a_standalone_body_is_handed_its_own_connection_and_no_preference_or_ledger() -> None:
    # Non-transactional in the three ways that reach the executor, stated where
    # the three values are actually chosen — and over a connection this read
    # acquired for itself rather than one the handle was holding.
    adapter = ScriptedAdapter()
    execution = _Standalone(None, _SERVING, adapter.open())
    body = _Body()

    execution.begin().eager(_TARGET, "typed", body)

    handed = body.only.inputs
    assert (handed.preference, handed.ledger) == (None, None)
    assert adapter.acquisitions == 1
    # The connection the body ran on is gone by the time this reads it back: the
    # eager read released at its own end, so what escaped executes nothing.
    with pytest.raises(RuntimeError):
        handed.connection.execute("select 1", [])


def test_a_standalone_read_names_its_edition_on_a_failure_and_the_root_sees_the_cause() -> None:
    # The failure bracket sits OUTSIDE the root activity: the root's own
    # Finished event reports the underlying failure, and only then does the
    # caller receive it named under the edition this read adopted. A
    # participating read brackets nothing, because the invocation above it
    # names the attempt's edition once.
    provider = RecordingLifecycleProvider()
    execution = _Standalone(installed_lifecycle(provider), _SERVING, ScriptedAdapter().open())
    boom = RuntimeError("the executor failed")

    def failing(_activity: object, _inputs: ReadInputs) -> object:
        raise boom

    try:
        execution.begin().eager(_TARGET, "typed", failing)
    except ExecutionFailure as failure:
        assert (failure.edition, failure.cause) == ("test", boom)
        assert failure.__cause__ is boom
    else:  # pragma: no cover - the assertion is the except arm
        raise AssertionError("a standalone read's failure was not contextualized")
    (root,) = provider.roots
    # The connection is acquired before the body and released after it however
    # the body left, so a read whose executor raised still gives it back.
    assert _events(root) == [
        "ReadStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "ReleaseStarted",
        "ReleaseFinished",
        "ReadFinished",
    ]

    def run(execution: Any, _uow: UnitOfWork) -> None:
        try:
            execution.begin().eager(_TARGET, "typed", failing)
        except RuntimeError as raised:
            assert raised is boom
        else:  # pragma: no cover - the assertion is the except arm
            raise AssertionError("a participating read wrapped its failure")

    _participating(run)


def test_a_standalone_read_lets_a_control_flow_exception_pass_untouched() -> None:
    execution = _Standalone(None, _SERVING, ScriptedAdapter().open())

    def interrupting(_activity: object, _inputs: ReadInputs) -> object:
        raise KeyboardInterrupt

    try:
        execution.begin().eager(_TARGET, "typed", interrupting)
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - the assertion is the except arm
        raise AssertionError("a control-flow exception was contextualized")


# --------------------------------------------------------------------------- #
# eager: the participating bracket                                             #
# --------------------------------------------------------------------------- #
def test_a_participating_eager_read_force_flushes_before_its_body_runs() -> None:
    # `uow.read` flushes what is buffered and only then runs what it was handed,
    # so the body sees a unit of work whose pending write has already gone.
    flushes = _Flushes()
    body = _Body(flushes=flushes)

    def run(execution: Any, uow: UnitOfWork) -> None:
        uow.buffer(_account_insert(9))
        assert execution.eager(_TARGET, "typed", body) is _ANSWER

    _participating(run, flushes=flushes)

    assert body.only.flushes == 1
    assert flushes.triggers[0] == "read_dependency"


def test_a_participating_read_opens_inside_the_flush_as_the_batchs_ordered_sibling() -> None:
    # The Read is a child of the ATTEMPT and the flush's Write Batch is its
    # ordered sibling — never its parent — which is what makes the activity tree
    # a record of causation rather than of nesting.
    provider = RecordingLifecycleProvider()
    flushes = _Flushes()
    body = _Body(provider, flushes)

    def run(execution: Any, uow: UnitOfWork) -> None:
        uow.buffer(_account_insert(9))
        execution.eager(_TARGET, "typed", body)

    _participating(run, provider=provider, flushes=flushes)

    (root,) = provider.roots
    assert _parentage(root) == [
        ("TransactionInvocationStarted", 1, None),
        ("TransactionAttemptStarted", 2, 1),
        ("WriteBatchStarted", 3, 2),
        ("WriteBatchFinished", 3, 2),
        ("ReadStarted", 4, 2),
        ("ReadFinished", 4, 2),
        ("TransactionAttemptFinished", 2, 1),
        ("TransactionInvocationFinished", 1, None),
    ]
    # And the body itself ran after the whole batch and inside the Read.
    assert body.only.transitions == (
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
        "WriteBatchFinished",
        "ReadStarted",
    )


def test_a_participating_body_is_handed_the_connection_the_preference_and_the_unit_of_work() -> (
    None
):
    port = RefusingAdapter()
    body = _Body()

    def run(execution: Any, uow: UnitOfWork) -> None:
        execution.eager(_TARGET, "typed", body)
        handed = body.only.inputs
        assert (handed.connection, handed.preference, handed.ledger) == (port, "locking", uow)

    _participating(run, conn=port, concurrency="locking")


# --------------------------------------------------------------------------- #
# open_stream: whose activity a stream is                                      #
# --------------------------------------------------------------------------- #
def test_a_standalone_stream_opens_a_root_execution_of_its_own() -> None:
    provider = RecordingLifecycleProvider()
    execution = _Standalone(installed_lifecycle(provider), _SERVING, ScriptedAdapter().open())

    activity: SnapshotStreamActivity = execution.begin().open_stream(_TARGET, "typed", 5)
    with activity:
        pass

    (root,) = provider.roots
    assert root.execution.kind == "snapshot_stream"
    assert _parentage(root) == [
        ("SnapshotStreamStarted", 1, None),
        ("SnapshotStreamFinished", 1, None),
    ]
    started = root.events[0]
    assert isinstance(started, SnapshotStreamStarted)
    assert started.edition == "test"


def test_a_participating_stream_is_a_child_of_the_current_attempt() -> None:
    provider = RecordingLifecycleProvider()

    def run(execution: Any, _uow: UnitOfWork) -> None:
        with execution.open_stream(_TARGET, "typed", 5):
            pass

    _participating(run, provider=provider)

    (root,) = provider.roots
    assert root.execution.kind == "transaction_invocation"
    assert _parentage(root) == [
        ("TransactionInvocationStarted", 1, None),
        ("TransactionAttemptStarted", 2, 1),
        ("SnapshotStreamStarted", 3, 2),
        ("SnapshotStreamFinished", 3, 2),
        ("TransactionAttemptFinished", 2, 1),
        ("TransactionInvocationFinished", 1, None),
    ]


# --------------------------------------------------------------------------- #
# page: one page's own bracket                                                 #
# --------------------------------------------------------------------------- #
def test_a_standalone_page_enters_its_batch_around_the_body_and_flushes_nothing() -> None:
    provider = RecordingLifecycleProvider()
    runtime = ScriptedAdapter().open()
    execution = _Standalone(installed_lifecycle(provider), _SERVING, runtime)
    body = _Body(provider)

    read = execution.begin()
    with read.open_stream(_TARGET, "typed", 5) as stream:
        assert read.page(stream.batch(), body) is _ANSWER

    (root,) = provider.roots
    # Nothing precedes the batch but the delivery taking its connection: the
    # Acquisition is the stream's own child and stands in front of the first
    # page, the batch opens where the page begins, and the body runs inside it.
    assert body.only.transitions == (
        "SnapshotStreamStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
        "StreamBatchStarted",
    )
    assert _parentage(root) == [
        ("SnapshotStreamStarted", 1, None),
        ("AcquisitionStarted", 2, 1),
        ("AcquisitionFinished", 2, 1),
        ("StreamBatchStarted", 3, 1),
        ("StreamBatchFinished", 3, 1),
        ("SnapshotStreamFinished", 1, None),
    ]
    handed = body.only.inputs
    assert (handed.preference, handed.ledger) == (None, None)


def test_every_participating_page_flushes_first_and_opens_its_batch_inside_that_flush() -> None:
    # Participation is per PAGE: a loop that writes as it reads sees its own
    # writes at every page, and each page's Stream Batch is the dependency
    # batch's ordered sibling rather than its parent.
    provider = RecordingLifecycleProvider()
    flushes = _Flushes()
    body = _Body(provider, flushes)

    def run(execution: Any, uow: UnitOfWork) -> None:
        with execution.open_stream(_TARGET, "typed", 5) as stream:
            uow.buffer(_account_insert(9))
            execution.page(stream.batch(), body)

    _participating(run, provider=provider, flushes=flushes)

    assert body.only.flushes == 1
    assert flushes.triggers[0] == "read_dependency"
    (root,) = provider.roots
    assert _parentage(root) == [
        ("TransactionInvocationStarted", 1, None),
        ("TransactionAttemptStarted", 2, 1),
        ("SnapshotStreamStarted", 3, 2),
        ("WriteBatchStarted", 4, 2),
        ("WriteBatchFinished", 4, 2),
        ("StreamBatchStarted", 5, 3),
        ("StreamBatchFinished", 5, 3),
        ("SnapshotStreamFinished", 3, 2),
        ("TransactionAttemptFinished", 2, 1),
        ("TransactionInvocationFinished", 1, None),
    ]


def test_a_participating_page_hands_its_body_the_same_inputs_every_read_gets() -> None:
    port = RefusingAdapter()
    body = _Body()

    def run(execution: Any, uow: UnitOfWork) -> None:
        with execution.open_stream(_TARGET, "typed", 5) as stream:
            execution.page(stream.batch(), body)
        handed = body.only.inputs
        assert (handed.connection, handed.preference, handed.ledger) == (port, "locking", uow)

    _participating(run, conn=port, concurrency="locking")


# --------------------------------------------------------------------------- #
# advance: one advance of a delivery, under the read's failure bracket         #
# --------------------------------------------------------------------------- #
def test_a_standalone_advance_names_the_edition_and_a_participating_one_does_not() -> None:
    # The page bracket reports the underlying failure to the batch and the
    # stream above it; the ADVANCE is where a standalone delivery names its
    # edition, once, on the way out to the caller. A participating advance is
    # the body itself.
    execution = _Standalone(None, _SERVING, ScriptedAdapter().open())
    boom = RuntimeError("the page failed")

    def failing() -> object:
        raise boom

    read = execution.begin()
    assert read.advance(lambda: _ANSWER) is _ANSWER
    try:
        read.advance(failing)
    except ExecutionFailure as failure:
        assert (failure.edition, failure.cause) == ("test", boom)
    else:  # pragma: no cover - the assertion is the except arm
        raise AssertionError("a standalone advance's failure was not contextualized")

    def run(execution: Any, _uow: UnitOfWork) -> None:
        assert execution.begin().advance(lambda: _ANSWER) is _ANSWER
        try:
            execution.begin().advance(failing)
        except RuntimeError as raised:
            assert raised is boom
        else:  # pragma: no cover - the assertion is the except arm
            raise AssertionError("a participating advance wrapped its failure")

    _participating(run)
