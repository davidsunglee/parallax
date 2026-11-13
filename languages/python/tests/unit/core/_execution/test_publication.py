"""Prepared Model Selections and the Serving Model (`execution.md`).

What preparation guarantees is graded as completeness: every product a request
path reads is derived while ``prepare_model`` runs, so the derivations are made
to fail afterwards and a read and a write still succeed. What the Serving Model
guarantees is graded under contention that is arranged rather than hoped for:
every reader is made to span the publication before its observations are judged,
and the compare/replace window is wrapped so that both entering and leaving it
are recorded: it is held shut until every publisher has entered, and no
publisher runs past it until every publisher has left. A holder that compared
before taking that window, or replaced after leaving it, fails rather than
passes on favorable scheduling. A further publication is landed at the instant
the window closes, so a holder that carried a reread of the served selection
into its refusal, rather than what its comparison read, fails there too.

What the Snapshot connection doors add on top — refusing what is no model,
preparing a static model once, and refusing a Typed read over a model naming no
class — is the Snapshot database suite's.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.core import ConflictError, UsageError
from parallax.core._execution import _planning as planning_module
from parallax.core._execution._publication import (
    read_projection,
    write_projection,
)
from parallax.core._execution._unit_work import preparation as preparation_module
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity import DomainModel
from parallax.core.internal.entity import _graph_construction as graph_construction_module
from parallax.core.internal.entity import _layout as layout_module
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.execution import (
    ModelSelection,
    PublicationConflictError,
    ServingModel,
    prepare_model,
)
from parallax.core.internal.metamodel import UnresolvedEntityDeclaration
from parallax.snapshot import connect
from tests._support import mirrored_models as mm
from tests._support.bindings import TEST_BINDING, binding_for
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.root_ownership import own_root

_ACCOUNT: Final = mm.ACCOUNT_MODEL
_ACCOUNT_SPELLING: Final = mm.Account.identity.canonical
_BALANCE: Final = Decimal("5.00")
_ROW: Final = {"id": 7, "owner": "Ada", "balance": _BALANCE, "version": 1}

_RENDEZVOUS: Final = 10.0
"""Seconds a worker waits for the others at a point they share. Nothing is
graded by how long an arrival takes; the bound is what turns a worker that
never arrives into a failure instead of a hung suite."""


class _RecordedWindow:
    """A Serving Model's compare/replace window with both of its edges recorded.

    ``publish`` enters this in place of the lock itself, so arrival is recorded
    BEFORE the publisher can take the window and therefore after everything the
    holder does outside one, and departure is recorded AFTER the window is
    released and therefore before anything the holder does past it. A test that
    holds the window shut can then wait for every publisher to arrive rather
    than sleeping and reading arrival off thread liveness, and holding every
    publisher at the departure edge makes each of them take the window, in
    turn, with no other publisher yet past it.
    """

    def __init__(
        self, window: threading.Lock, arriving: threading.Barrier, leaving: threading.Barrier
    ) -> None:
        self._window = window
        self._arriving = arriving
        self._leaving = leaving

    def __enter__(self) -> None:
        self._arriving.wait(_RENDEZVOUS)
        self._window.acquire()

    def __exit__(self, *_exception: object) -> None:
        self._window.release()
        self._leaving.wait(_RENDEZVOUS)


class _AdvancingWindow:
    """A Serving Model's compare/replace window with a further publication
    landed at the instant it closes.

    ``publish`` enters this in place of the lock itself, so the advance takes
    the window as soon as it is free — the earliest a third publisher could win
    it, and before anything the holder does past the window. That is exactly
    where a holder rereading the served selection would take the value its
    refusal reports. No thread is needed to stand in for that publisher: what
    is graded is which read the refusal carries, a property of one publication
    rather than of a race.
    """

    def __init__(
        self, window: threading.Lock, serving: ServingModel, further: ModelSelection
    ) -> None:
        self._window = window
        self._serving = serving
        self._further = further

    def __enter__(self) -> None:
        self._window.acquire()

    def __exit__(self, *_exception: object) -> None:
        self._window.release()
        with self._window:
            self._serving._selection = self._further  # pyright: ignore[reportPrivateUsage] - the third publisher this stands in for, replacing where one could


class _ClasslessSource:
    """A descriptor-frontend formation input composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (mm.Account,)


def _descriptor_backed() -> DomainModel:
    return DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam


def _refuse_every_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every per-Entity derivation fail from here on, so anything a request
    path still derives is a failure rather than a cost."""

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a per-Entity derivation ran after preparation")

    monkeypatch.setattr(layout_module.LayoutCatalog, "_build", refuse)
    monkeypatch.setattr(preparation_module, "_entity_preparation", refuse)
    monkeypatch.setattr(graph_construction_module, "_entity_facts", refuse)
    monkeypatch.setattr(planning_module, "_wire_entity_facts", refuse)
    monkeypatch.setattr(planning_module, "narrowed_view_keys", refuse)


# --------------------------------------------------------------------------- #
# prepare_model: complete, whole, and refused before any derivation.          #
# --------------------------------------------------------------------------- #


def test_a_class_backed_selection_reads_and_writes_with_every_derivation_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = prepare_model(_ACCOUNT, edition="one", binding=TEST_BINDING)
    _refuse_every_derivation(monkeypatch)
    port = ScriptedAdapter(Read(rows=[_ROW]), Read(rows=[_ROW]), Transact(Write()))
    database = own_root(connect(port, ServingModel(selection))).using_database_login()
    query = mm.Account.where(mm.Account.id == 7)

    assert database.find(query).result().owner == "Ada"
    assert database.wire.find(query).result()["owner"] == "Ada"
    database.transact(lambda tx: tx.insert(mm.Account(id=9, owner="Bo", balance=_BALANCE)))

    assert [type(call) for call in port.calls] == [
        ReadCall,
        ReadCall,
        BeginCall,
        WriteCall,
        CommitCall,
    ]


def test_a_descriptor_backed_selection_reads_and_writes_with_every_derivation_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = prepare_model(_descriptor_backed(), edition="wire-only", binding=TEST_BINDING)
    assert write_projection(selection).preparation.entity(mm.Account.identity).typed_class is None
    _refuse_every_derivation(monkeypatch)
    port = ScriptedAdapter(Read(rows=[_ROW]), Transact(Write()))
    database = own_root(connect(port, ServingModel(selection))).using_database_login()

    assert database.wire.find(mm.Account.where(mm.Account.id == 7)).result()["owner"] == "Ada"
    database.transact(
        lambda tx: tx.wire.insert(_ACCOUNT_SPELLING, {"id": 9, "owner": "Bo", "balance": "5.00"})
    )

    assert [type(call) for call in port.calls] == [ReadCall, BeginCall, WriteCall, CommitCall]


@pytest.mark.parametrize("edition", ["", None, 7], ids=["empty", "none", "not-a-string"])
def test_an_edition_that_is_no_nonempty_string_is_refused_before_derivation(
    edition: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _refuse_every_derivation(monkeypatch)
    with pytest.raises(ValueError, match="nonempty string"):
        prepare_model(_ACCOUNT, edition=edition, binding=TEST_BINDING)


def test_a_value_that_is_no_domain_model_is_refused_before_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _refuse_every_derivation(monkeypatch)
    with pytest.raises(TypeError, match="takes a Domain Model"):
        prepare_model(model_of(_ACCOUNT), edition="bare", binding=TEST_BINDING)  # pyright: ignore[reportArgumentType] - the refusal under test


def test_two_preparations_of_one_model_are_distinct_selections() -> None:
    first = prepare_model(_ACCOUNT, edition="same", binding=TEST_BINDING)
    second = prepare_model(_ACCOUNT, edition="same", binding=TEST_BINDING)
    assert first is not second
    assert first != second
    assert first.edition == second.edition
    assert read_projection(first).wire is not read_projection(second).wire


# --------------------------------------------------------------------------- #
# ModelSelection: opaque, read-only, and closed to subclassing.                #
# --------------------------------------------------------------------------- #


def test_a_selection_exposes_its_model_and_edition_and_nothing_else() -> None:
    selection = prepare_model(_ACCOUNT, edition="one", binding=TEST_BINDING)
    assert selection.model is _ACCOUNT
    assert selection.edition == "one"
    assert read_projection(selection).edition == write_projection(selection).edition == "one"
    assert read_projection(selection).model.meta is model_of(_ACCOUNT)
    assert not hasattr(selection, "__dict__")
    public = {name for name in dir(selection) if not name.startswith("_")}
    assert public == {"model", "edition"}
    assert repr(selection) == "ModelSelection(edition='one')"


@pytest.mark.parametrize("name", ["model", "edition"])
def test_a_selections_properties_are_read_only(name: str) -> None:
    selection = prepare_model(_ACCOUNT, edition="one", binding=TEST_BINDING)
    with pytest.raises(AttributeError):
        setattr(selection, name, object())


@pytest.mark.parametrize("slot", ["_edition", "_model", "_read", "_write"])
def test_no_holder_can_alter_what_a_selection_was_prepared_with(slot: str) -> None:
    # Refusing the constructor closes only the way IN. A holder that could
    # assign a slot could give a published selection an empty edition, or one
    # model's catalog under another model's write planner, and every entry
    # reached through it would resolve against one and encode against the
    # other; deleting one would fail deep inside a request instead.
    selection = prepare_model(_ACCOUNT, edition="one", binding=TEST_BINDING)
    other = prepare_model(_ACCOUNT, edition="two", binding=TEST_BINDING)
    forged: dict[str, Any] = {
        "_edition": "",
        "_model": other.model,
        "_read": read_projection(other),
        "_write": write_projection(other),
    }
    with pytest.raises(AttributeError, match="immutable"):
        setattr(selection, slot, forged[slot])
    with pytest.raises(AttributeError, match="immutable"):
        delattr(selection, slot)

    assert selection.edition == "one"
    assert read_projection(selection).model is write_projection(selection).model
    assert read_projection(selection) is not read_projection(other)
    assert write_projection(selection) is not write_projection(other)


def test_a_selection_admits_no_subclass() -> None:
    with pytest.raises(TypeError, match="admits no subclass"):

        class _Wider(ModelSelection):  # pyright: ignore[reportUnusedClass] - the refusal under test
            pass


def test_no_caller_can_construct_a_selection() -> None:
    # Preparation is the only way one comes into being. A caller who could name
    # a constructor could pair a model with no projections at all, or with
    # another selection's, and a Serving Model would hold the result as
    # prepared — so the class refuses to be called, whatever it is handed.
    prepared = prepare_model(_ACCOUNT, edition="one", binding=TEST_BINDING)
    with pytest.raises(TypeError, match="prepared rather than constructed"):
        ModelSelection()
    with pytest.raises(TypeError, match="prepared rather than constructed"):
        ModelSelection("forged", _ACCOUNT, None, None)
    with pytest.raises(TypeError, match="prepared rather than constructed"):
        ModelSelection("forged", _ACCOUNT, read_projection(prepared), write_projection(prepared))
    with pytest.raises(TypeError, match="prepared rather than constructed"):
        ModelSelection(edition="forged", model=_ACCOUNT)


# --------------------------------------------------------------------------- #
# ServingModel: one holder, identity compare-and-replace, refused when stale.  #
# --------------------------------------------------------------------------- #


def test_a_serving_model_answers_the_exact_selection_it_holds() -> None:
    a = prepare_model(_ACCOUNT, edition="a", binding=TEST_BINDING)
    serving = ServingModel(a)
    assert serving.current() is a
    assert serving.current() is serving.current()
    assert repr(serving) == "ServingModel(current=ModelSelection(edition='a'))"


def test_publishing_against_the_held_selection_replaces_it() -> None:
    a, b = (
        prepare_model(_ACCOUNT, edition="a", binding=TEST_BINDING),
        prepare_model(_ACCOUNT, edition="b", binding=TEST_BINDING),
    )
    serving = ServingModel(a)
    serving.publish(b, expected=a)
    assert serving.current() is b


def test_a_stale_publication_is_refused_with_what_was_expected_and_held() -> None:
    a, b, c = (prepare_model(_ACCOUNT, edition=edition, binding=TEST_BINDING) for edition in "abc")
    serving = ServingModel(a)
    serving.publish(b, expected=a)

    with pytest.raises(PublicationConflictError) as refusal:
        serving.publish(c, expected=a)
    assert refusal.value.expected is a
    assert refusal.value.held is b
    assert serving.current() is b
    # The loser rebases on what it lost to and succeeds without a second read.
    serving.publish(c, expected=refusal.value.held)
    assert serving.current() is c


def test_a_refusal_reports_the_comparison_it_was_raised_with() -> None:
    a, b, c = (prepare_model(_ACCOUNT, edition=edition, binding=TEST_BINDING) for edition in "abc")
    serving = ServingModel(a)
    serving.publish(b, expected=a)

    with pytest.raises(PublicationConflictError) as refusal:
        serving.publish(c, expected=a)
    # A handler holding the refusal can neither restate what the publisher
    # expected nor swap what the comparison found held.
    for name in ("expected", "held"):
        with pytest.raises(AttributeError):
            setattr(refusal.value, name, c)
        with pytest.raises(AttributeError):
            delattr(refusal.value, name)
    assert (refusal.value.expected, refusal.value.held) == (a, b)
    assert isinstance(refusal.value, ConflictError)
    assert (refusal.value.code, refusal.value.entity, refusal.value.key) == (
        "publication-conflict",
        None,
        None,
    )
    assert not refusal.value.is_transient


def test_a_refusal_leaves_interpreter_owned_state_writable() -> None:
    # Read-only is about the two selections this refusal reports, not about the
    # machinery every exception carries: chaining and notes still work.
    a, b = (prepare_model(_ACCOUNT, edition=edition, binding=TEST_BINDING) for edition in "ab")
    refusal = PublicationConflictError(expected=a, held=b)
    replacement = ValueError("chaining stays interpreter-owned")
    refusal.__cause__ = replacement
    refusal.add_note("annotated")
    assert refusal.__cause__ is replacement
    assert refusal.__notes__ == ["annotated"]


def test_a_refusal_carries_what_its_comparison_read_and_not_a_later_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `held` is evidence about the comparison that failed, which is the whole
    # reason a loser may rebase on it instead of calling `current()` again: a
    # second read may already answer a third selection. So a third publication
    # is landed the instant the window closes — after the losing comparison,
    # before anything the publisher does past the window — and the refusal must
    # still name what the comparison read. A holder that left the window and
    # reread would hand the loser a selection it never compared against.
    a, b, c = (prepare_model(_ACCOUNT, edition=edition, binding=TEST_BINDING) for edition in "abc")
    third = prepare_model(_ACCOUNT, edition="third", binding=TEST_BINDING)
    serving = ServingModel(a)
    serving.publish(b, expected=a)
    window = serving._lock  # pyright: ignore[reportPrivateUsage] - the compare/replace window under test
    monkeypatch.setattr(serving, "_lock", _AdvancingWindow(window, serving, third))

    with pytest.raises(PublicationConflictError) as refusal:
        serving.publish(c, expected=a)

    assert serving.current() is third, "the third publication never landed"
    assert refusal.value.expected is a
    assert refusal.value.held is b


def test_a_selection_with_an_equal_edition_is_not_the_expected_one() -> None:
    # Publication compares selection identity, never edition equality.
    a = prepare_model(_ACCOUNT, edition="same", binding=TEST_BINDING)
    twin = prepare_model(_ACCOUNT, edition="same", binding=TEST_BINDING)
    serving = ServingModel(a)
    with pytest.raises(PublicationConflictError):
        serving.publish(prepare_model(_ACCOUNT, edition="b", binding=TEST_BINDING), expected=twin)
    assert serving.current() is a


def test_a_serving_model_holds_and_publishes_only_prepared_selections() -> None:
    with pytest.raises(TypeError, match="prepared ModelSelection"):
        ServingModel(_ACCOUNT)  # pyright: ignore[reportArgumentType] - the refusal under test
    serving = ServingModel(prepare_model(_ACCOUNT, edition="a", binding=TEST_BINDING))
    with pytest.raises(TypeError, match="prepared ModelSelection"):
        serving.publish(_ACCOUNT, expected=serving.current())  # pyright: ignore[reportArgumentType] - the refusal under test


def test_a_serving_model_admits_no_subclass() -> None:
    with pytest.raises(TypeError, match="admits no subclass"):

        class _Custom(ServingModel):  # pyright: ignore[reportUnusedClass] - the refusal under test
            pass


def test_concurrent_readers_observe_only_a_complete_a_or_b() -> None:
    # Every reader is made to SPAN the publication rather than left to race it:
    # each takes its first observation before the publisher is released, and
    # each then reads without pause until it has observed the replacement, so a
    # reader running wholly before or wholly after it cannot be what passes.
    # Each records the selections it saw CHANGE between, so the whole history of
    # a reader that observed only complete states is exactly A then B: a stale,
    # reverted, or half-replaced answer is one more entry.
    a, b = (
        prepare_model(_ACCOUNT, edition="a", binding=TEST_BINDING),
        prepare_model(_ACCOUNT, edition="b", binding=TEST_BINDING),
    )
    serving = ServingModel(a)
    observations: list[list[ModelSelection]] = [[] for _ in range(4)]
    reading = threading.Barrier(len(observations) + 1)

    def read(into: list[ModelSelection]) -> None:
        into.append(serving.current())
        reading.wait(_RENDEZVOUS)
        deadline = time.monotonic() + _RENDEZVOUS
        while into[-1] is not b and time.monotonic() < deadline:
            observed = serving.current()
            if observed is not into[-1]:
                into.append(observed)

    def publish() -> None:
        reading.wait(_RENDEZVOUS)
        serving.publish(b, expected=a)

    readers = [threading.Thread(target=read, args=(into,)) for into in observations]
    publisher = threading.Thread(target=publish)
    for thread in (*readers, publisher):
        thread.start()
    for thread in (*readers, publisher):
        thread.join(_RENDEZVOUS * 2)

    for seen in observations:
        assert seen == [a, b], "a reader spanning the publication observed something else"
    assert serving.current() is b


def test_two_publishers_racing_one_expectation_leave_exactly_one_holding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The contention is necessary rather than lucky: the window records each
    # publisher at both edges, the test holds it shut until all eight have
    # entered, and no publisher may run past it until all eight have left. So
    # the eight compares happen one at a time with nothing else in between,
    # and only the replacement each compare is fused to can decide the rest.
    # A holder that compared BEFORE taking the window would have every compare
    # behind it when the window opens; one that replaced AFTER leaving it would
    # have every compare read the selection they each saw held, since no
    # replacement can run until the last compare is done. Either way all eight
    # replace and all eight succeed. A holder that took no window at all would
    # finish without ever being recorded.
    a = prepare_model(_ACCOUNT, edition="a", binding=TEST_BINDING)
    candidates = [
        prepare_model(_ACCOUNT, edition=f"candidate-{n}", binding=TEST_BINDING) for n in range(8)
    ]
    serving = ServingModel(a)
    window = serving._lock  # pyright: ignore[reportPrivateUsage] - the compare/replace window under test
    arriving = threading.Barrier(len(candidates) + 1)
    leaving = threading.Barrier(len(candidates))
    monkeypatch.setattr(serving, "_lock", _RecordedWindow(window, arriving, leaving))
    refusals: list[PublicationConflictError] = []
    published: list[ModelSelection] = []
    outcomes = threading.Lock()

    def publish(candidate: ModelSelection) -> None:
        try:
            serving.publish(candidate, expected=a)
        except PublicationConflictError as refused:
            with outcomes:
                refusals.append(refused)
        else:
            with outcomes:
                published.append(candidate)

    threads = [threading.Thread(target=publish, args=(one,)) for one in candidates]
    window.acquire()
    try:
        for thread in threads:
            thread.start()
        try:
            arriving.wait(_RENDEZVOUS)
        except threading.BrokenBarrierError as unarrived:
            raise AssertionError(
                "a publisher never entered the compare/replace window"
            ) from unarrived
        assert published == [], "a publisher completed outside the window"
        assert serving.current() is a
    finally:
        # Both in the same finally: a publisher left blocked on a window this
        # test still holds would outlive the suite that failed.
        window.release()
        for thread in threads:
            if thread.is_alive():
                thread.join(_RENDEZVOUS)

    winner = serving.current()
    assert published == [winner]
    assert len(refusals) == len(candidates) - 1
    assert all(refused.expected is a and refused.held is winner for refused in refusals)


def test_a_candidate_prepared_for_another_backend_is_refused_and_nothing_is_replaced() -> None:
    a = prepare_model(_ACCOUNT, edition="a", binding=TEST_BINDING)
    elsewhere = prepare_model(
        _ACCOUNT,
        edition="b",
        binding=binding_for(dataclasses.replace(POSTGRES, name="mariadb")),
    )
    serving = ServingModel(a)
    with pytest.raises(UsageError) as refused:
        serving.publish(elsewhere, expected=a)
    assert refused.value.code == "publication-backend-mismatch"
    assert serving.current() is a
