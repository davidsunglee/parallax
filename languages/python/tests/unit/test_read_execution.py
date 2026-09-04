"""The two production execution policies, each through all four capabilities.

A policy is a bracket around a body the Read Scope hands it, so what it is can
only be stated by what the body sees when it runs: which activity is open, what
has already happened to the unit of work, and which port, Concurrency
Preference, and observation ledger arrived with it. Every case here therefore
passes a recording body and grades the moment that body ran.

That is where the two orderings the handles used to each restate now live. A
participating eager read force-flushes and then opens its Read INSIDE that
flush, so the dependency Write Batch is the Read's ordered sibling under one
attempt; a participating page does the same around its Stream Batch. A
standalone read and a standalone page flush nothing and own their roots.

What the ladder ABOVE these does is `test_read_scope.py`'s subject, and what a
whole read answers stays the public-surface suites'.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from _transact_support import ACCOUNT, FIXED

from _support.db_port import RefusingPort
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.core.db_port import DbPort
from parallax.core.entity import graph_construction_of
from parallax.core.entity._model import cataloged_model
from parallax.core.execution_lifecycle import ExecutionEvent
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
from parallax.snapshot.handle import _read_scope as read_scope_module
from parallax.snapshot.handle import build_write_planner
from parallax.snapshot.handle._read_scope import ReadInputs, SelectedReadModel

# The two production adapters are what this suite grades, and module privacy is
# what closes their construction — so they are reached here exactly as the
# module's own factories reach them, and nowhere else.
_Standalone: Final = read_scope_module._StandaloneExecution  # pyright: ignore[reportPrivateUsage]
_Participating: Final = read_scope_module._ParticipatingExecution  # pyright: ignore[reportPrivateUsage]

_META: Final = cataloged_model(ACCOUNT).meta
_SELECTED: Final = SelectedReadModel(
    model=cataloged_model(ACCOUNT), construction=graph_construction_of(ACCOUNT)
)


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
    conn: DbPort | None = None,
    provider: RecordingLifecycleProvider | None = None,
    concurrency: Concurrency = "optimistic",
    flushes: _Flushes | None = None,
) -> T:
    """One physical attempt's collaborators, wired as ``Database.transact`` wires
    them, with ``run`` standing in for the transaction the closure would receive.

    The flush executor records rather than lowers: what these cases grade is
    WHEN a flush happened relative to a body, never what its statements were.
    """
    port = conn if conn is not None else RefusingPort()
    executor = flushes if flushes is not None else _Flushes()
    root = open_transaction_root(
        installed_lifecycle(provider),
        concurrency=concurrency,
        retries=0,
        retry_optimistic_conflicts=False,
        isolation=None,
        extra_retriable=None,
    )
    with root as invocation, invocation.attempt() as attempt:
        attempt.begun()

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
# begin: the selection each policy serves                                      #
# --------------------------------------------------------------------------- #
def test_each_policy_answers_the_selection_it_was_built_with() -> None:
    # Neither adapter selects per operation in this shape, and the scope above
    # assumes neither does: what both promise is that the record arrives through
    # `begin` rather than off the handle.
    port = RefusingPort()
    standalone = _Standalone(None, _SELECTED, ReadInputs(port, None, None))
    assert standalone.begin() is _SELECTED
    assert standalone.begin() is _SELECTED

    def run(execution: Any, _uow: UnitOfWork) -> None:
        assert execution.begin() is _SELECTED
        assert execution.begin() is _SELECTED

    _participating(run)


# --------------------------------------------------------------------------- #
# eager: the standalone bracket                                                #
# --------------------------------------------------------------------------- #
def test_a_standalone_eager_read_runs_inside_a_read_root_of_its_own() -> None:
    provider = RecordingLifecycleProvider()
    port = RefusingPort()
    execution = _Standalone(installed_lifecycle(provider), _SELECTED, ReadInputs(port, None, None))
    body = _Body(provider)

    assert execution.eager(_TARGET, "TYPED", body) is _ANSWER

    (root,) = provider.roots
    assert root.execution.kind == "READ"
    # The body ran with the Read open and nothing else around it: no flush, no
    # batch, and no second activity.
    assert body.only.transitions == ("ReadStarted",)
    assert _events(root) == ["ReadStarted", "ReadFinished"]


def test_a_standalone_body_is_handed_the_port_and_neither_a_preference_nor_a_ledger() -> None:
    # Non-transactional in the three ways that reach the executor, stated where
    # the three values are actually chosen.
    port = RefusingPort()
    execution = _Standalone(None, _SELECTED, ReadInputs(port, None, None))
    body = _Body()

    execution.eager(_TARGET, "TYPED", body)

    handed = body.only.inputs
    assert (handed.port, handed.preference, handed.ledger) == (port, None, None)


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
        assert execution.eager(_TARGET, "TYPED", body) is _ANSWER

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
        execution.eager(_TARGET, "TYPED", body)

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
    port = RefusingPort()
    body = _Body()

    def run(execution: Any, uow: UnitOfWork) -> None:
        execution.eager(_TARGET, "TYPED", body)
        handed = body.only.inputs
        assert (handed.port, handed.preference, handed.ledger) == (port, "locking", uow)

    _participating(run, conn=port, concurrency="locking")


# --------------------------------------------------------------------------- #
# open_stream: whose activity a stream is                                      #
# --------------------------------------------------------------------------- #
def test_a_standalone_stream_opens_a_root_execution_of_its_own() -> None:
    provider = RecordingLifecycleProvider()
    execution = _Standalone(
        installed_lifecycle(provider), _SELECTED, ReadInputs(RefusingPort(), None, None)
    )

    activity: SnapshotStreamActivity = execution.open_stream(_TARGET, "TYPED", 5)
    with activity:
        pass

    (root,) = provider.roots
    assert root.execution.kind == "SNAPSHOT_STREAM"
    assert _parentage(root) == [
        ("SnapshotStreamStarted", 1, None),
        ("SnapshotStreamFinished", 1, None),
    ]


def test_a_participating_stream_is_a_child_of_the_current_attempt() -> None:
    provider = RecordingLifecycleProvider()

    def run(execution: Any, _uow: UnitOfWork) -> None:
        with execution.open_stream(_TARGET, "TYPED", 5):
            pass

    _participating(run, provider=provider)

    (root,) = provider.roots
    assert root.execution.kind == "TRANSACTION_INVOCATION"
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
    port = RefusingPort()
    execution = _Standalone(installed_lifecycle(provider), _SELECTED, ReadInputs(port, None, None))
    body = _Body(provider)

    with execution.open_stream(_TARGET, "TYPED", 5) as stream:
        assert execution.page(stream.batch(), body) is _ANSWER

    (root,) = provider.roots
    # Nothing precedes the batch: it opens where the page begins, and the body
    # runs inside it.
    assert body.only.transitions == ("SnapshotStreamStarted", "StreamBatchStarted")
    assert _parentage(root) == [
        ("SnapshotStreamStarted", 1, None),
        ("StreamBatchStarted", 2, 1),
        ("StreamBatchFinished", 2, 1),
        ("SnapshotStreamFinished", 1, None),
    ]
    handed = body.only.inputs
    assert (handed.port, handed.preference, handed.ledger) == (port, None, None)


def test_every_participating_page_flushes_first_and_opens_its_batch_inside_that_flush() -> None:
    # Participation is per PAGE: a loop that writes as it reads sees its own
    # writes at every page, and each page's Stream Batch is the dependency
    # batch's ordered sibling rather than its parent.
    provider = RecordingLifecycleProvider()
    flushes = _Flushes()
    body = _Body(provider, flushes)

    def run(execution: Any, uow: UnitOfWork) -> None:
        with execution.open_stream(_TARGET, "TYPED", 5) as stream:
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
    port = RefusingPort()
    body = _Body()

    def run(execution: Any, uow: UnitOfWork) -> None:
        with execution.open_stream(_TARGET, "TYPED", 5) as stream:
            execution.page(stream.batch(), body)
        handed = body.only.inputs
        assert (handed.port, handed.preference, handed.ledger) == (port, "locking", uow)

    _participating(run, conn=port, concurrency="locking")
