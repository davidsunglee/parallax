"""The Read Scope's ladder, graded against a recording execution policy.

What the public read verbs cannot state is what this suite is for: that the
scope refuses re-entry before it asks its policy for anything — a Wire spelling
it cannot even lower included, since lowering is the call's own argument — that
it selects the model before it refuses a classless one, that a refused query
reaches no capability that executes, that one scope chooses its publication per
call rather than holding one, and that the body it hands the policy takes its port,
its Concurrency Preference, and its observation ledger from the inputs it was
handed rather than from anything it closed over.

A delivery is the same ladder read from the other side, and gets the same
treatment: that a stream verb refuses everything it can before it judges the page
size it was named with, that constructing one opens no activity and entering one
opens exactly the activity the policy answers, and that every page of a delivery
comes back to the ONE scope and the ONE selection it was opened with.

The recording policy here is the third adapter beside the two production ones:
it answers a fixed selection, records every capability call, and runs each body
with INERT activities over whichever :class:`ReadInputs` the case names. That is
what lets each claim be stated once, for both lanes and both interfaces, rather
than once per handle. What each production adapter DOES inside its own bracket
is `test_read_execution.py`'s subject, and what a whole read answers stays the
public-surface suites'.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import pytest
from _transact_support import ACCOUNT, BALANCE, NEW_ROW, balance_row

from _support import mirrored_models as mm
from _support.db_port import Read, ReadCall, RefusingPort, ScriptedPort
from parallax.core import LATEST, TX_TIME
from parallax.core.db_port import DbPort
from parallax.core.entity import graph_construction_of
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import cataloged_model
from parallax.core.execution_lifecycle import ExecutionLifecycleReentryError, ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    ActivityTarget,
    DatabaseCallScope,
    InstalledLifecycle,
    ReadActivity,
    SnapshotStreamActivity,
    StreamBatchActivity,
    installed_lifecycle,
)
from parallax.core.execution_lifecycle.testing import RecordingLifecycleProvider
from parallax.core.object_query import ObjectQueryError, ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import object_query_node
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.unit_work import Concurrency, ParticipationToken, RetainedObservation
from parallax.snapshot import QueryTargetError, SnapshotConnectionError
from parallax.snapshot._read_result import FindResult, HistoryFindResult, RowsResult
from parallax.snapshot.handle import _page as handle_page
from parallax.snapshot.handle import _read as handle_read
from parallax.snapshot.handle import _read_scope as read_scope_module
from parallax.snapshot.handle._page import At, PagePlan, StreamPage
from parallax.snapshot.handle._read_scope import (
    ReadInputs,
    ReadScope,
    SelectedReadModel,
)
from parallax.snapshot.handle._retention import ObservationLedger

_ACCOUNT_ROWS: Final = (NEW_ROW,)

_VALID_BATCH_SIZE: Final = 2


def _account_row(account_id: int) -> dict[str, object]:
    return {**NEW_ROW, "id": account_id}


def _selection(model: Any = ACCOUNT, *, materializing: bool = True) -> SelectedReadModel:
    cataloged: CatalogedModel = cataloged_model(model)
    return SelectedReadModel(
        model=cataloged,
        construction=graph_construction_of(model) if materializing else None,
    )


def _typed_query() -> Any:
    return mm.Account.where(mm.Account.id == 7)


def _wire_node() -> ObjectQueryNode:
    return deserialize_query(
        {"target": "Account", "predicate": {"eq": {"attr": "Account.id", "value": 7}}}
    )


def _rows_node() -> ObjectQueryNode:
    return object_query_node(_typed_query())


def _balance_node(temporal: dict[str, object]) -> ObjectQueryNode:
    return deserialize_query(
        {
            "target": "Balance",
            "predicate": {"eq": {"attr": "Balance.id", "value": 1}},
            "temporal": temporal,
        }
    )


class _LoweringReached(Exception):
    pass


class _Ledger:
    """The two things an observing read asks a transaction for, and nothing else.

    A stand-in rather than a unit of work, because what this suite grades is
    WHICH ledger the body was handed, never what a real one does with what it
    receives.
    """

    def __init__(self) -> None:
        self.retained: list[RetainedObservation] = []
        self._participation = ParticipationToken()

    @property
    def participation(self) -> ParticipationToken:
        return self._participation

    def retain(self, observation: RetainedObservation, /) -> RetainedObservation:
        self.retained.append(observation)
        return observation


class _Recording:
    """A recording ``_ReadExecution``: every capability call, in order.

    Each body runs immediately, with INERT activities and the fixed inputs this
    policy was built with, so a case reads what the scope DID rather than what
    it would have done.
    """

    def __init__(self, selected: SelectedReadModel, inputs: ReadInputs) -> None:
        self._selected = selected
        self._inputs = inputs
        self.calls: list[str] = []
        self.eager_calls: list[tuple[ActivityTarget, ReadInterface]] = []
        self.stream_calls: list[tuple[ActivityTarget, ReadInterface, int]] = []

    def begin(self) -> SelectedReadModel:
        self.calls.append("begin")
        return self._selected

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        self.calls.append("eager")
        self.eager_calls.append((target, interface))
        return body(INERT, self._inputs)

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> SnapshotStreamActivity:
        self.calls.append("open_stream")
        self.stream_calls.append((target, interface, batch_size))
        return INERT

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        self.calls.append("page")
        return body(INERT, self._inputs)

    @property
    def interfaces(self) -> list[ReadInterface]:
        return [interface for _, interface in self.eager_calls]


@dataclass(frozen=True, slots=True)
class _Executed:
    """One executor call the scope's body made, by name and by what it threaded."""

    executor: str
    port: DbPort
    preference: Concurrency | None
    ledger: ObservationLedger | None


def _recorded(patch: pytest.MonkeyPatch) -> list[_Executed]:
    """Which executor each body dispatched to, and the three inputs it threaded.

    Spelled with each executor's full signature rather than ``*args``, so a
    rename or a move to a positional parameter fails here rather than silently
    recording ``None`` forever.
    """
    executed: list[_Executed] = []

    def recording_find(
        query: ValidatedObjectQuery,
        model: CatalogedModel,
        port: DbPort,
        *,
        preference: Concurrency | None = None,
        ledger: ObservationLedger | None = None,
        calls: DatabaseCallScope = INERT,
    ) -> FindResult:
        executed.append(_Executed("find", port, preference, ledger))
        return handle_read.find(
            query, model, port, preference=preference, ledger=ledger, calls=calls
        )

    def recording_find_history(
        query: ValidatedObjectQuery,
        model: CatalogedModel,
        port: DbPort,
        *,
        read: ReadActivity = INERT,
    ) -> HistoryFindResult:
        executed.append(_Executed("find_history", port, None, None))
        return handle_read.find_history(query, model, port, read=read)

    def recording_find_rows(
        query: ValidatedObjectQuery,
        model: CatalogedModel,
        port: DbPort,
        *,
        preference: Concurrency | None = None,
        read: ReadActivity = INERT,
    ) -> RowsResult:
        executed.append(_Executed("find_rows", port, preference, None))
        return handle_read.find_rows(query, model, port, preference=preference, read=read)

    patch.setattr(read_scope_module, "find", recording_find)
    patch.setattr(read_scope_module, "find_history", recording_find_history)
    patch.setattr(read_scope_module, "find_rows", recording_find_rows)
    return executed


@dataclass(frozen=True, slots=True)
class _PageRead:
    """One page the scope's own body read, and what it read it under."""

    model: CatalogedModel
    port: DbPort
    preference: Concurrency | None
    ledger: ObservationLedger | None


def _recorded_pages(patch: pytest.MonkeyPatch) -> list[_PageRead]:
    """The model, port, preference, and ledger every page of a delivery was read
    under, spelled with the page reader's full signature for `_recorded`'s
    reason."""
    page_reads: list[_PageRead] = []

    def recording_read_stream_page(
        page_plan: PagePlan,
        at: At,
        model: CatalogedModel,
        port: DbPort,
        *,
        preference: Concurrency | None = None,
        ledger: ObservationLedger | None = None,
        calls: DatabaseCallScope = INERT,
    ) -> StreamPage:
        page_reads.append(_PageRead(model, port, preference, ledger))
        return handle_page.read_stream_page(
            page_plan, at, model, port, preference=preference, ledger=ledger, calls=calls
        )

    patch.setattr(read_scope_module, "read_stream_page", recording_read_stream_page)
    return page_reads


def _delivering() -> InstalledLifecycle:
    """A handle installation currently inside one of its own lifecycle contexts."""
    installed = installed_lifecycle(RecordingLifecycleProvider())
    assert installed is not None
    installed.delivering.active = True
    return installed


def _scope(
    port: DbPort,
    *,
    selected: SelectedReadModel | None = None,
    lifecycle: InstalledLifecycle | None = None,
    preference: Concurrency | None = None,
    ledger: ObservationLedger | None = None,
) -> tuple[ReadScope, _Recording]:
    resolved = selected if selected is not None else _selection()
    execution = _Recording(resolved, ReadInputs(port, preference, ledger))
    return ReadScope(lifecycle, execution), execution


# --------------------------------------------------------------------------- #
# Re-entry is the first line of every verb                                     #
# --------------------------------------------------------------------------- #
def test_every_verb_refuses_re_entry_before_it_asks_its_policy_for_anything() -> None:
    # The refusal precedes model selection, the classless check, the query's own
    # judgement, and every capability — which is what makes re-entry
    # completeness a property of this module rather than of a matrix.
    port = RefusingPort()
    scope, execution = _scope(port, lifecycle=_delivering())

    for verb in (
        lambda: scope.find(_typed_query()),
        lambda: scope.stream(_typed_query(), _VALID_BATCH_SIZE),
        lambda: scope.read_rows(_rows_node()),
        lambda: scope.wire_find(_wire_node()),
        lambda: scope.wire_stream(_wire_node(), _VALID_BATCH_SIZE),
    ):
        with pytest.raises(ExecutionLifecycleReentryError):
            verb()

    assert execution.calls == []


def test_a_wire_verb_refuses_re_entry_before_it_lowers_what_it_was_handed() -> None:
    # Lowering a Wire spelling is one of the CALL's own arguments rather than a
    # step above the refusal, so a mapping no deserializer could accept is
    # refused as re-entry from inside a lifecycle context and answers its own
    # complaint outside one — reaching, in both cases, no capability that
    # executes. Outside the context the selection is already made when the
    # lowering fails, which is what orders those two rungs.
    malformed: Any = {"target": "Account"}
    delivering, refusing = _scope(RefusingPort(), lifecycle=_delivering())
    quiet, lowering = _scope(RefusingPort())

    for refused in (
        lambda: delivering.wire_find(malformed),
        lambda: delivering.wire_stream(malformed, _VALID_BATCH_SIZE),
    ):
        with pytest.raises(ExecutionLifecycleReentryError):
            refused()
    for complaining in (
        lambda: quiet.wire_find(malformed),
        lambda: quiet.wire_stream(malformed, _VALID_BATCH_SIZE),
    ):
        with pytest.raises(ObjectQueryError, match="missing required clause"):
            complaining()

    assert refusing.calls == []
    assert lowering.calls == ["begin", "begin"]


# --------------------------------------------------------------------------- #
# Selection sits inside the boundary, ahead of the classless refusal           #
# --------------------------------------------------------------------------- #
def test_find_selects_its_model_before_it_refuses_a_classless_one() -> None:
    # The record the policy answers is what carries the refusal, so selection
    # has to have happened for the refusal to be possible at all — and nothing
    # below `begin` runs once it fires.
    port = ScriptedPort()
    scope, execution = _scope(port, selected=_selection(materializing=False))

    with pytest.raises(SnapshotConnectionError) as caught:
        scope.find(_typed_query())

    assert caught.value.code == "snapshot-class-backed-model-required"
    assert execution.calls == ["begin"]
    assert port.calls == []


def test_find_refuses_a_classless_model_before_it_lowers_its_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The connection's capability is judged before this call's own arguments
    # are, so a lowering that refuses everything it is handed never runs under a
    # classless selection — and DOES run under a class-backed one, which is what
    # proves the two rungs are ordered rather than merely both present.
    lowered: list[object] = []

    def refusing_lowering(query: object) -> ObjectQueryNode:
        lowered.append(query)
        raise _LoweringReached

    monkeypatch.setattr(read_scope_module, "object_query_node", refusing_lowering)
    port = RefusingPort()
    classless, execution = _scope(port, selected=_selection(materializing=False))
    class_backed, _ = _scope(port)

    with pytest.raises(SnapshotConnectionError) as refused:
        classless.find(_typed_query())
    with pytest.raises(_LoweringReached):
        class_backed.find(_typed_query())

    assert refused.value.code == "snapshot-class-backed-model-required"
    assert execution.calls == ["begin"]
    assert len(lowered) == 1


def test_the_wire_and_row_form_verbs_cross_no_classless_refusal() -> None:
    # Neither publishes an Entity Class instance, so neither needs the graph
    # construction the Typed lane refuses without — and both run to completion
    # under the same selection `find` was refused under.
    port = ScriptedPort(Read(rows=list(_ACCOUNT_ROWS)), Read(rows=list(_ACCOUNT_ROWS)))
    scope, execution = _scope(port, selected=_selection(materializing=False))

    published = scope.wire_find(_wire_node()).result()
    rows = scope.read_rows(_rows_node())

    assert published == {"id": 7, "owner": "Newton", "balance": "5.00", "version": 1}
    assert len(rows.rows) == 1
    assert execution.calls == ["begin", "eager", "begin", "eager"]


# --------------------------------------------------------------------------- #
# The gate precedes the bracket                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "verb_name",
    ["find", "read_rows", "wire_find"],
)
def test_a_query_the_gate_refuses_reaches_no_execution_capability(verb_name: str) -> None:
    # A refused read opens no activity and runs no body, which is what leaves a
    # participating one's buffer untouched: the flush lives inside `eager`, and
    # `eager` is never reached.
    unknown = deserialize_query({"target": "Balance", "predicate": {"all": {}}})
    port = RefusingPort()
    scope, execution = _scope(port)
    verbs: dict[str, Callable[[], object]] = {
        "find": lambda: scope.find(mm.Balance.where(mm.Balance.id == 1)),
        "read_rows": lambda: scope.read_rows(unknown),
        "wire_find": lambda: scope.wire_find(unknown),
    }

    with pytest.raises(QueryTargetError) as caught:
        verbs[verb_name]()

    assert caught.value.code == "query-target-not-in-model"
    assert execution.calls == ["begin"]


# --------------------------------------------------------------------------- #
# Publication is the call's, never the scope's                                 #
# --------------------------------------------------------------------------- #
def test_one_scope_chooses_its_publication_per_call() -> None:
    # Three reads through ONE scope, published three ways: the publication is
    # built after the refusal each time and is never retained, so a Handle and
    # its Wire view sharing one scope is not a Handle sharing one result format.
    port = ScriptedPort(*[Read(rows=list(_ACCOUNT_ROWS)) for _ in range(3)])
    scope, execution = _scope(port)

    scope.find(_typed_query()).result()
    scope.wire_find(_wire_node()).result()
    scope.read_rows(_rows_node())

    assert execution.interfaces == ["TYPED", "WIRE", "ROWS"]


# --------------------------------------------------------------------------- #
# One graph tail serves both interfaces and both temporal shapes               #
# --------------------------------------------------------------------------- #
def test_the_graph_tail_dispatches_the_milestone_set_read_for_both_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The history branch is written once, below both read interfaces, so which
    # executor runs is decided by the validated query and by nothing about the
    # caller — which is what keeps "a milestone-set read retains no evidence" a
    # property of one dispatch rather than of four call sites.
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = ScriptedPort(*[Read(rows=[balance_row(in_z=in_z)]) for _ in range(4)])
    scope, _ = _scope(port, selected=_selection(BALANCE))
    executed = _recorded(monkeypatch)

    scope.find(mm.Balance.where(mm.Balance.id == 1).as_of(tx_time=LATEST)).result()
    scope.find(mm.Balance.where(mm.Balance.id == 1).history(TX_TIME)).result()
    scope.wire_find(_balance_node({"transaction-time": {"asOf": "latest"}})).result()
    scope.wire_find(_balance_node({"transaction-time": {"history": {}}})).result()

    assert [call.executor for call in executed] == [
        "find",
        "find_history",
        "find",
        "find_history",
    ]


# --------------------------------------------------------------------------- #
# The body reads its lane off the inputs it is handed                          #
# --------------------------------------------------------------------------- #
def test_every_body_threads_the_port_preference_and_ledger_it_was_handed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The scope holds no port, no preference, and no ledger: all three arrive
    # with the body's own invocation, which is what lets one ladder serve a
    # standalone read and a participating one without a mode flag between them.
    standalone_port = ScriptedPort(Read(rows=list(_ACCOUNT_ROWS)))
    participating_port = ScriptedPort(Read(rows=list(_ACCOUNT_ROWS)))
    ledger = _Ledger()
    standalone, _ = _scope(standalone_port)
    participating, _ = _scope(participating_port, preference="locking", ledger=ledger)
    executed = _recorded(monkeypatch)

    standalone.find(_typed_query()).result()
    participating.find(_typed_query()).result()

    first, second = executed
    assert (first.port, first.preference, first.ledger) == (standalone_port, None, None)
    assert (second.port, second.preference) == (participating_port, "locking")
    assert second.ledger is ledger


def test_the_row_form_body_threads_the_preference_and_files_into_no_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The values lane locks like the graph lane and observes nothing: its
    # executor takes no ledger at all, so a preference reaching it while no
    # evidence does is a property of the one body that calls it.
    port = ScriptedPort(Read(rows=list(_ACCOUNT_ROWS)))
    ledger = _Ledger()
    scope, _ = _scope(port, preference="locking", ledger=ledger)
    executed = _recorded(monkeypatch)

    scope.read_rows(_rows_node())

    (call,) = executed
    assert (call.executor, call.port, call.preference) == ("find_rows", port, "locking")
    assert ledger.retained == []
    assert [type(op) for op in port.calls] == [ReadCall]


# --------------------------------------------------------------------------- #
# A stream's ladder runs at the call; its execution runs at the scope          #
# --------------------------------------------------------------------------- #
def test_a_stream_refuses_a_classless_selection_before_it_judges_its_page_size() -> None:
    # The stream verbs run `find`'s ladder with one more rung on it, and the
    # rung is LAST: what the connection can materialize at all is judged before
    # this call's own arguments are, so a classless selection is refused with an
    # invalid page size still unexamined. The same call under a class-backed
    # selection reaches the page size, which is what orders the two rather than
    # merely finding both present.
    port = RefusingPort()
    classless, execution = _scope(port, selected=_selection(materializing=False))
    class_backed, _ = _scope(port)

    with pytest.raises(SnapshotConnectionError) as refused:
        classless.stream(_typed_query(), 0)
    with pytest.raises(ValueError, match="batch_size requires a positive built-in int"):
        class_backed.stream(_typed_query(), 0)

    assert refused.value.code == "snapshot-class-backed-model-required"
    assert execution.calls == ["begin"]


def test_the_wire_stream_verb_crosses_no_classless_refusal_and_still_judges_its_size() -> None:
    # A Wire delivery publishes no Entity Class instance, so it needs no graph
    # construction — and reaches its own page size under exactly the selection
    # the Typed stream was refused under.
    port = RefusingPort()
    scope, execution = _scope(port, selected=_selection(materializing=False))

    with pytest.raises(ValueError, match="batch_size requires a positive built-in int"):
        scope.wire_stream(_wire_node(), 0)

    assert execution.calls == ["begin"]


@pytest.mark.parametrize(
    ("verb_name", "interface", "target"),
    [
        ("stream", "TYPED", "parallax.compatibility.Account"),
        ("wire_stream", "WIRE", "Account"),
    ],
)
def test_constructing_a_stream_opens_no_activity_and_entering_it_opens_one(
    verb_name: str, interface: ReadInterface, target: str
) -> None:
    # The stream's side-effect boundary is its scope rather than its
    # construction: the verb selects a model and answers an inert delivery, and
    # the activity that delivery is observed through is opened through THIS
    # scope when the caller enters it. Which activity that is stays the
    # execution policy's, so the scope passes the target, the interface, and the
    # page size and decides nothing.
    port = ScriptedPort(Read(rows=[_account_row(1)]))
    scope, execution = _scope(port)
    verbs: dict[str, Callable[[], Any]] = {
        "stream": lambda: scope.stream(_typed_query(), _VALID_BATCH_SIZE),
        "wire_stream": lambda: scope.wire_stream(_wire_node(), _VALID_BATCH_SIZE),
    }

    stream = verbs[verb_name]()

    assert execution.calls == ["begin"]
    assert port.calls == []
    with stream:
        assert execution.calls == ["begin", "open_stream"]
        opened_on, opened_as, batch_size = execution.stream_calls[0]
        assert (opened_on.canonical, opened_as, batch_size) == (
            target,
            interface,
            _VALID_BATCH_SIZE,
        )
        assert list(stream) != []
    assert execution.calls == ["begin", "open_stream", "page"]


def test_every_page_of_a_delivery_is_read_under_the_one_selection_it_opened_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A delivery holds the selection its verb answered and reads every page
    # under it, so no page of one stream is served by a second model however
    # many pages it takes. `begin` is called once for the whole delivery, and
    # every page reaches the SAME scope and the same policy the first one did —
    # which is what "no scope or adapter per page" is, stated as recorded calls
    # rather than as a byte count.
    selected = _selection()
    port = ScriptedPort(
        Read(rows=[_account_row(1), _account_row(2)]),
        Read(rows=[_account_row(2), _account_row(3)]),
        Read(rows=[_account_row(3)]),
    )
    scope, execution = _scope(port, selected=selected)
    page_reads = _recorded_pages(monkeypatch)

    with scope.stream(_typed_query(), 1) as stream:
        delivered = [root.id for root in stream]

    assert delivered == [1, 2, 3]
    assert execution.calls == ["begin", "open_stream", "page", "page", "page"]
    assert [read.model for read in page_reads] == [selected.model] * 3
    assert all(read.model is selected.model for read in page_reads)


def test_every_page_threads_the_port_preference_and_ledger_it_was_handed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A page IS an eager read of a bounded root query, so it takes its lane off
    # the same inputs an eager read's body does: the scope holds none of the
    # three and a participating delivery differs from a standalone one in what
    # its policy hands each page, never in what the loop above asks for.
    ledger = _Ledger()
    standalone_port = ScriptedPort(Read(rows=[_account_row(1)]))
    participating_port = ScriptedPort(Read(rows=[_account_row(1)]))
    standalone, _ = _scope(standalone_port)
    participating, _ = _scope(participating_port, preference="locking", ledger=ledger)
    page_reads = _recorded_pages(monkeypatch)

    for scope, expected_port in (
        (standalone, standalone_port),
        (participating, participating_port),
    ):
        with scope.stream(_typed_query(), _VALID_BATCH_SIZE) as stream:
            assert list(stream) != []
        assert page_reads[-1].port is expected_port

    first, second = page_reads
    assert (first.preference, first.ledger) == (None, None)
    assert second.preference == "locking"
    assert second.ledger is ledger
