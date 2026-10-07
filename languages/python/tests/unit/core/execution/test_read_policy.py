"""The two production begun reads, each through every capability it offers.

A standalone read is what an Execution Scope begins for one operation, and a
participating read is the Attempt itself. Each is a bracket around a body the
read operations hand it, so what it is can only be stated by what the body sees
when it runs: which activity is open, what has already happened to the unit of
work, and which connection, Concurrency Preference, and observation ledger
arrived with it. Every case therefore passes a recording body and grades the
moment that body ran.

That is where the two orderings live. A participating eager read force-flushes
and then opens its Read INSIDE that flush, so the dependency Write Batch is the
Read's ordered sibling under one attempt; a participating page does the same
around its Stream Batch. A standalone read and a standalone page flush nothing
and own their roots, and a standalone read is begun by adopting the Serving
Model's current selection — once per operation, retained for everything done
through that read, and named on whatever ordinary failure escapes it.

Both reads are reached through a real root whose scope factory and transaction
factory answer the Execution Scope and the Attempt themselves, over the scripted
port. What the ladder ABOVE these does is the read-ladder suite's subject, and
what a whole read answers stays the public-surface suites'.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

import pytest

from parallax.conformance._lifecycle_recording import (
    RecordedRoot,
    RecordingLifecycleProvider,
)
from parallax.core.execution import ExecutionFailure, ServingModel, prepare_model
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._publication import read_projection
from parallax.core.execution._read_policy import ReadInputs
from parallax.core.execution._scope import ExecutionScope
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ReadStarted,
    StreamStarted,
    WriteBatchStarted,
)
from parallax.core.execution_lifecycle._activity import ActivityTarget, StreamActivity
from parallax.core.unit_work import Concurrency
from tests._support.db_port import ScriptedAdapter, Transact, Write, WriteCall
from tests.unit.core.execution._execution_support import (
    ACCOUNT,
    account_insert,
    itself,
    scope,
)

_SERVING: Final = ServingModel(prepare_model(ACCOUNT, edition="test"))


def _scope(
    adapter: ScriptedAdapter,
    *,
    provider: RecordingLifecycleProvider | None = None,
    serving: ServingModel = _SERVING,
) -> ExecutionScope:
    return scope(adapter, serving, provider=provider)


def _participating(
    run: Callable[[Attempt], None],
    adapter: ScriptedAdapter,
    *,
    provider: RecordingLifecycleProvider | None = None,
    concurrency: Concurrency = "optimistic",
) -> None:
    """Run ``run`` over the actual Attempt one committed transaction constructs."""
    _scope(adapter, provider=provider).transact(run, itself, concurrency=concurrency)


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
    writes: int


_ANSWER: Final = object()


class _Body:
    """A recording body: it answers a sentinel and records the moment it ran.

    The transitions and the statements written are read INSIDE the call rather
    than after it, which is the whole point — an ordering claim about a bracket
    is unprovable from the outside, where every event has already been
    delivered.
    """

    def __init__(
        self,
        provider: RecordingLifecycleProvider | None = None,
        adapter: ScriptedAdapter | None = None,
    ) -> None:
        self.runs: list[_Ran] = []
        self._provider = provider
        self._adapter = adapter

    def __call__(self, activity: object, inputs: ReadInputs) -> object:
        self.runs.append(
            _Ran(
                activity,
                inputs,
                _transitions(self._provider),
                0 if self._adapter is None else _writes(self._adapter),
            )
        )
        return _ANSWER

    @property
    def only(self) -> _Ran:
        (run,) = self.runs
        return run


def _writes(adapter: ScriptedAdapter) -> int:
    return sum(1 for call in adapter.calls if isinstance(call, WriteCall))


def _transitions(provider: RecordingLifecycleProvider | None) -> tuple[str, ...]:
    if provider is None:
        return ()
    return tuple(type(event).__name__ for root in provider.roots for event in root.events)


def _events(root: RecordedRoot) -> list[str]:
    return [type(event).__name__ for event in root.events]


def _parentage(
    root: RecordedRoot, kinds: Iterable[str] | None = None
) -> list[tuple[str, int, int | None]]:
    """Each event's name, activity, and parent — only those whose activity kind
    is among ``kinds``, where given."""
    kept = None if kinds is None else tuple(kinds)

    def named(event: ExecutionEvent) -> tuple[str, int, int | None]:
        return (type(event).__name__, event.activity_id, event.parent_activity_id)

    return [
        named(event)
        for event in root.events
        if kept is None or type(event).__name__.startswith(kept)
    ]


_UNDER_THE_ATTEMPT: Final = (
    "TransactionInvocation",
    "TransactionAttempt",
    "WriteBatch",
    "Read",
    "Stream",
)
"""The activity kinds an ordering claim about a participating read is made over;
the attempt's own connection lease and each batch's Database Calls are other
suites' subjects."""


def _batch_triggers(root: RecordedRoot) -> list[str]:
    return [event.trigger for event in root.events if isinstance(event, WriteBatchStarted)]


# --------------------------------------------------------------------------- #
# begin: the read each lane answers                                            #
# --------------------------------------------------------------------------- #
def test_each_lane_answers_the_selection_it_was_begun_under() -> None:
    # A scope adopts from its Serving Model at each `begin`, and an attempt
    # answers itself, over the selection it adopted: what both promise is that
    # the record arrives through the begun read rather than off the scope.
    scope = _scope(ScriptedAdapter(Transact()))
    current = read_projection(_SERVING.current())
    assert scope.begin().selected is current
    assert scope.begin().selected is current

    def run(attempt: Attempt) -> None:
        assert attempt.begin() is attempt
        assert attempt.selected is current

    scope.transact(run, itself)


def test_a_standalone_begin_adopts_once_per_operation_and_retains_it() -> None:
    # Adoption is per operation: two begun reads over one Serving Model may
    # differ once a publication lands between them, and the earlier one keeps
    # what it adopted however long it lives — a publication reaches the next
    # operation and never an existing read.
    a = prepare_model(ACCOUNT, edition="a")
    b = prepare_model(ACCOUNT, edition="b")
    serving = ServingModel(a)
    scope = _scope(ScriptedAdapter(), serving=serving)

    first = scope.begin()
    serving.publish(b, expected=a)
    second = scope.begin()

    assert first.selected is read_projection(a)
    assert second.selected is read_projection(b)
    assert (first.selected.edition, second.selected.edition) == ("a", "b")
    assert first.selected is read_projection(a)


# --------------------------------------------------------------------------- #
# eager: the standalone bracket                                                #
# --------------------------------------------------------------------------- #
def test_a_standalone_eager_read_runs_inside_a_read_root_of_its_own() -> None:
    provider = RecordingLifecycleProvider()
    body = _Body(provider)

    assert (
        _scope(ScriptedAdapter(), provider=provider).begin().eager(_TARGET, "typed", body)
        is _ANSWER
    )

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
    # acquired for itself rather than one the scope was holding.
    adapter = ScriptedAdapter()
    body = _Body()

    _scope(adapter).begin().eager(_TARGET, "typed", body)

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
    boom = RuntimeError("the executor failed")

    def failing(_activity: object, _inputs: ReadInputs) -> object:
        raise boom

    try:
        _scope(ScriptedAdapter(), provider=provider).begin().eager(_TARGET, "typed", failing)
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

    def run(attempt: Attempt) -> None:
        try:
            attempt.eager(_TARGET, "typed", failing)
        except RuntimeError as raised:
            assert raised is boom
        else:  # pragma: no cover - the assertion is the except arm
            raise AssertionError("a participating read wrapped its failure")

    _participating(run, ScriptedAdapter(Transact()))


def test_a_standalone_read_lets_a_control_flow_exception_pass_untouched() -> None:
    def interrupting(_activity: object, _inputs: ReadInputs) -> object:
        raise KeyboardInterrupt

    try:
        _scope(ScriptedAdapter()).begin().eager(_TARGET, "typed", interrupting)
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - the assertion is the except arm
        raise AssertionError("a control-flow exception was contextualized")


# --------------------------------------------------------------------------- #
# eager: the participating bracket                                             #
# --------------------------------------------------------------------------- #
def test_a_participating_eager_read_force_flushes_before_its_body_runs() -> None:
    # `uow.read` flushes what is buffered and only then runs what it was handed,
    # so the body sees a unit of work whose pending write has already executed.
    provider = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Transact(Write()))
    body = _Body(adapter=adapter)

    def run(attempt: Attempt) -> None:
        attempt.uow.buffer(account_insert(9))
        assert attempt.eager(_TARGET, "typed", body) is _ANSWER

    _participating(run, adapter, provider=provider)

    assert body.only.writes == 1
    (root,) = provider.roots
    assert _batch_triggers(root) == ["read_dependency"]


def test_a_participating_read_opens_inside_the_flush_as_the_batchs_ordered_sibling() -> None:
    # The Read is a child of the ATTEMPT and the flush's Write Batch is its
    # ordered sibling — never its parent — which is what makes the activity tree
    # a record of causation rather than of nesting.
    provider = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Transact(Write()))
    body = _Body(provider, adapter)

    def run(attempt: Attempt) -> None:
        attempt.uow.buffer(account_insert(9))
        attempt.eager(_TARGET, "typed", body)

    _participating(run, adapter, provider=provider)

    (root,) = provider.roots
    shown = _parentage(root, _UNDER_THE_ATTEMPT)
    attempt = shown[1][1]
    assert [name for name, _activity, _parent in shown] == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
        "WriteBatchFinished",
        "ReadStarted",
        "ReadFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    batch, read = shown[2], shown[4]
    assert (batch[2], read[2]) == (attempt, attempt)
    assert batch[1] != read[1]
    # And the body itself ran after the whole batch and inside the Read.
    ran = [name for name in body.only.transitions if name.startswith(_UNDER_THE_ATTEMPT)]
    assert ran == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "WriteBatchStarted",
        "WriteBatchFinished",
        "ReadStarted",
    ]


def test_a_participating_body_is_handed_the_attempts_connection_preference_and_unit_of_work() -> (
    None
):
    # Every participating read runs on the one connection the attempt acquired
    # for its whole life, so an eager body and a page body are handed the same
    # one, and no read acquires another.
    adapter = ScriptedAdapter(Transact())
    eager = _Body()
    paged = _Body()

    def run(attempt: Attempt) -> None:
        attempt.eager(_TARGET, "typed", eager)
        with attempt.open_stream(_TARGET, "typed", 5) as stream:
            attempt.paged(stream.batch(), paged)
        for handed in (eager.only.inputs, paged.only.inputs):
            assert (handed.preference, handed.ledger) == ("locking", attempt.uow)
        assert eager.only.inputs.connection is paged.only.inputs.connection

    _participating(run, adapter, concurrency="locking")

    assert adapter.acquisitions == 1


# --------------------------------------------------------------------------- #
# open_stream: whose activity a stream is                                      #
# --------------------------------------------------------------------------- #
def test_a_standalone_stream_opens_a_root_execution_of_its_own() -> None:
    provider = RecordingLifecycleProvider()

    activity: StreamActivity = (
        _scope(ScriptedAdapter(), provider=provider).begin().open_stream(_TARGET, "typed", 5)
    )
    with activity:
        pass

    (root,) = provider.roots
    assert root.execution.kind == "stream"
    assert _parentage(root) == [
        ("StreamStarted", 1, None),
        ("StreamFinished", 1, None),
    ]
    started = root.events[0]
    assert isinstance(started, StreamStarted)
    assert started.edition == "test"


def test_a_participating_stream_is_a_child_of_the_current_attempt() -> None:
    provider = RecordingLifecycleProvider()

    def run(attempt: Attempt) -> None:
        with attempt.open_stream(_TARGET, "typed", 5):
            pass

    _participating(run, ScriptedAdapter(Transact()), provider=provider)

    (root,) = provider.roots
    assert root.execution.kind == "transaction_invocation"
    shown = _parentage(root, _UNDER_THE_ATTEMPT)
    attempt = shown[1][1]
    assert [(name, parent) for name, _activity, parent in shown] == [
        ("TransactionInvocationStarted", None),
        ("TransactionAttemptStarted", shown[0][1]),
        ("StreamStarted", attempt),
        ("StreamFinished", attempt),
        ("TransactionAttemptFinished", shown[0][1]),
        ("TransactionInvocationFinished", None),
    ]


# --------------------------------------------------------------------------- #
# paged: one page's own bracket                                                #
# --------------------------------------------------------------------------- #
def test_a_standalone_page_enters_its_batch_around_the_body_and_flushes_nothing() -> None:
    provider = RecordingLifecycleProvider()
    body = _Body(provider)

    read = _scope(ScriptedAdapter(), provider=provider).begin()
    with read.open_stream(_TARGET, "typed", 5) as stream:
        assert read.paged(stream.batch(), body) is _ANSWER

    (root,) = provider.roots
    # The page's Stream Batch starts before its lease, and the body runs only
    # after that batch-owned Acquisition has finished.
    assert body.only.transitions == (
        "StreamStarted",
        "StreamBatchStarted",
        "AcquisitionStarted",
        "AcquisitionFinished",
    )
    assert _parentage(root) == [
        ("StreamStarted", 1, None),
        ("StreamBatchStarted", 2, 1),
        ("AcquisitionStarted", 3, 2),
        ("AcquisitionFinished", 3, 2),
        ("ReleaseStarted", 4, 2),
        ("ReleaseFinished", 4, 2),
        ("StreamBatchFinished", 2, 1),
        ("StreamFinished", 1, None),
    ]
    handed = body.only.inputs
    assert (handed.preference, handed.ledger) == (None, None)


def test_every_participating_page_flushes_first_and_opens_its_batch_inside_that_flush() -> None:
    # Participation is per PAGE: a loop that writes as it reads sees its own
    # writes at every page, and each page's Stream Batch is the dependency
    # batch's ordered sibling rather than its parent.
    provider = RecordingLifecycleProvider()
    adapter = ScriptedAdapter(Transact(Write()))
    body = _Body(provider, adapter)

    def run(attempt: Attempt) -> None:
        with attempt.open_stream(_TARGET, "typed", 5) as stream:
            attempt.uow.buffer(account_insert(9))
            attempt.paged(stream.batch(), body)

    _participating(run, adapter, provider=provider)

    assert body.only.writes == 1
    (root,) = provider.roots
    assert _batch_triggers(root) == ["read_dependency"]
    shown = _parentage(root, _UNDER_THE_ATTEMPT)
    assert [name for name, _activity, _parent in shown] == [
        "TransactionInvocationStarted",
        "TransactionAttemptStarted",
        "StreamStarted",
        "WriteBatchStarted",
        "WriteBatchFinished",
        "StreamBatchStarted",
        "StreamBatchFinished",
        "StreamFinished",
        "TransactionAttemptFinished",
        "TransactionInvocationFinished",
    ]
    attempt, stream, batch, page = shown[1][1], shown[2][1], shown[3], shown[5]
    assert (batch[2], page[2]) == (attempt, stream)


# --------------------------------------------------------------------------- #
# advance: one advance of a delivery, under the read's failure bracket         #
# --------------------------------------------------------------------------- #
def test_a_standalone_advance_names_the_edition_and_a_participating_one_does_not() -> None:
    # The page bracket reports the underlying failure to the batch and the
    # stream above it; the ADVANCE is where a standalone delivery names its
    # edition, once, on the way out to the caller. A participating advance is
    # the body itself.
    boom = RuntimeError("the page failed")

    def failing() -> object:
        raise boom

    read = _scope(ScriptedAdapter()).begin()
    assert read.advance(lambda: _ANSWER) is _ANSWER
    try:
        read.advance(failing)
    except ExecutionFailure as failure:
        assert (failure.edition, failure.cause) == ("test", boom)
    else:  # pragma: no cover - the assertion is the except arm
        raise AssertionError("a standalone advance's failure was not contextualized")

    def run(attempt: Attempt) -> None:
        assert attempt.begin().advance(lambda: _ANSWER) is _ANSWER
        try:
            attempt.begin().advance(failing)
        except RuntimeError as raised:
            assert raised is boom
        else:  # pragma: no cover - the assertion is the except arm
            raise AssertionError("a participating advance wrapped its failure")

    _participating(run, ScriptedAdapter(Transact()))
