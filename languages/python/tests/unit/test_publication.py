"""Prepared Model Selections and the Serving Model (spec §2 *Model preparation
and the Serving Model*).

What preparation guarantees is graded as completeness: every product a request
path reads is derived while ``prepare_model`` runs, so the derivations are made
to fail afterwards and a read and a write still succeed. What the Serving Model
guarantees is graded under contention that is arranged rather than hoped for:
every reader is made to span the publication before its observations are judged,
and every publisher is made to reach the compare/replace window before any of
them may leave one, so a holder that compared outside that window fails rather
than passes on favorable scheduling.

Docker-free, against the shared recording port.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Final

import pytest
from _transact_support import FIXED, NEW_ROW, new_account

from _support import mirrored_models as mm
from _support.db_port import Read, ScriptedPort, Transact, Write
from parallax.core.entity import DomainModel, EntityGraphConstruction
from parallax.core.entity import _graph_construction as graph_construction_module
from parallax.core.entity import _layout as layout_module
from parallax.core.entity import _row_codec as row_codec_module
from parallax.core.entity._model import model_of
from parallax.core.metamodel import UnresolvedEntityDeclaration
from parallax.core.unit_work import FixedClock
from parallax.snapshot import (
    ModelSelection,
    PublicationConflictError,
    ServingModel,
    SnapshotConnectionError,
    connect,
    prepare_model,
)
from parallax.snapshot.handle import Database, Transaction
from parallax.snapshot.handle._publication import read_projection, write_projection

_ACCOUNT: Final = mm.ACCOUNT_MODEL

_RENDEZVOUS: Final = 10.0
"""Seconds a worker waits for the others to reach the window it shares with
them. Long enough that a loaded machine never reaches it, so exceeding it is a
failure to arrive rather than slow arrival."""

_SETTLE: Final = 0.1
"""Seconds allowed for workers released together to run as far as they can. What
is graded is where they cannot get, so this bounds a negative observation."""


class _ClasslessSource:
    """A descriptor-frontend formation input composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (mm.Account,)


def _descriptor_backed() -> DomainModel:
    return DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam


def _identities(model: DomainModel) -> set[Any]:
    return {entity.identity for entity in model.entities}


def _refuse_every_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every per-Entity derivation fail from here on, so anything a request
    path still derives is a failure rather than a cost."""

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a per-Entity derivation ran after preparation")

    monkeypatch.setattr(layout_module.LayoutCatalog, "_build", refuse)
    monkeypatch.setattr(row_codec_module, "_row_facts", refuse)
    monkeypatch.setattr(graph_construction_module, "_entity_facts", refuse)


# --------------------------------------------------------------------------- #
# prepare_model: complete, whole, and refused before any derivation.          #
# --------------------------------------------------------------------------- #


def test_a_class_backed_model_prepares_every_product_for_every_entity() -> None:
    selection = prepare_model(_ACCOUNT, edition="one")
    read, write = read_projection(selection), write_projection(selection)

    assert selection.model is _ACCOUNT
    assert selection.edition == "one"
    assert read.edition == write.edition == "one"
    assert read.model is write.model
    assert read.model.meta is model_of(_ACCOUNT)
    assert isinstance(read.construction, EntityGraphConstruction)
    expected = _identities(_ACCOUNT)
    assert set(read.model.layouts._layouts) == expected  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
    assert set(write.codec._facts_by_identity) == expected  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
    assert set(read.construction._facts) == expected  # pyright: ignore[reportPrivateUsage] - the derivation is the claim


def test_a_descriptor_backed_model_prepares_with_no_graph_construction() -> None:
    selection = prepare_model(_descriptor_backed(), edition="wire-only")
    read, write = read_projection(selection), write_projection(selection)

    assert read.construction is None
    assert set(read.model.layouts._layouts) == _identities(selection.model)  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
    assert write.codec.full_row(mm.Account(id=1, owner="Ada", balance=NEW_ROW["balance"])) == {
        "id": 1,
        "owner": "Ada",
        "balance": NEW_ROW["balance"],
    }


def test_nothing_fallible_remains_after_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    port = ScriptedPort(Read(rows=[NEW_ROW]), Transact(Write()))
    db = connect(port, _ACCOUNT, clock=FixedClock(FIXED))
    _refuse_every_derivation(monkeypatch)

    assert db.find(mm.Account.where(mm.Account.id == 7)).result().owner == "Newton"

    def insert(tx: Transaction) -> None:
        tx.insert(new_account())

    db.transact(insert)


def test_a_descriptor_backed_connection_still_refuses_a_typed_read_before_io() -> None:
    db = Database.connect(ScriptedPort(), _descriptor_backed(), clock=FixedClock(FIXED))
    with pytest.raises(SnapshotConnectionError, match="snapshot-class-backed-model-required"):
        db.find(mm.Account.where(mm.Account.id == 7))


@pytest.mark.parametrize("edition", ["", None, 7], ids=["empty", "none", "not-a-string"])
def test_an_edition_that_is_no_nonempty_string_is_refused_before_derivation(
    edition: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _refuse_every_derivation(monkeypatch)
    with pytest.raises(ValueError, match="nonempty string"):
        prepare_model(_ACCOUNT, edition=edition)


def test_a_value_that_is_no_domain_model_is_refused_before_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _refuse_every_derivation(monkeypatch)
    with pytest.raises(TypeError, match="takes a Domain Model"):
        prepare_model(model_of(_ACCOUNT), edition="bare")  # pyright: ignore[reportArgumentType] - the refusal under test


def test_two_preparations_of_one_model_are_distinct_selections() -> None:
    first = prepare_model(_ACCOUNT, edition="same")
    second = prepare_model(_ACCOUNT, edition="same")
    assert first is not second
    assert first != second
    assert first.edition == second.edition


# --------------------------------------------------------------------------- #
# ModelSelection: opaque, read-only, and closed to subclassing.                #
# --------------------------------------------------------------------------- #


def test_a_selection_exposes_its_model_and_edition_and_nothing_else() -> None:
    selection = prepare_model(_ACCOUNT, edition="one")
    assert not hasattr(selection, "__dict__")
    public = {name for name in dir(selection) if not name.startswith("_")}
    assert public == {"model", "edition"}
    assert repr(selection) == "ModelSelection(edition='one')"


@pytest.mark.parametrize("name", ["model", "edition"])
def test_a_selections_properties_are_read_only(name: str) -> None:
    selection = prepare_model(_ACCOUNT, edition="one")
    with pytest.raises(AttributeError):
        setattr(selection, name, object())


def test_a_selection_admits_no_subclass() -> None:
    with pytest.raises(TypeError, match="admits no subclass"):

        class _Wider(ModelSelection):  # pyright: ignore[reportUnusedClass] - the refusal under test
            pass


def test_no_caller_can_construct_a_selection() -> None:
    # Preparation is the only way one comes into being. A caller who could name
    # a constructor could pair a model with no projections at all, or with
    # another selection's, and a Serving Model would hold the result as
    # prepared — so the class refuses to be called, whatever it is handed.
    prepared = prepare_model(_ACCOUNT, edition="one")
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
    a = prepare_model(_ACCOUNT, edition="a")
    serving = ServingModel(a)
    assert serving.current() is a
    assert serving.current() is serving.current()
    assert repr(serving) == "ServingModel(current=ModelSelection(edition='a'))"


def test_publishing_against_the_held_selection_replaces_it() -> None:
    a, b = prepare_model(_ACCOUNT, edition="a"), prepare_model(_ACCOUNT, edition="b")
    serving = ServingModel(a)
    serving.publish(b, expected=a)
    assert serving.current() is b


def test_a_stale_publication_is_refused_with_what_was_expected_and_held() -> None:
    a, b, c = (prepare_model(_ACCOUNT, edition=edition) for edition in "abc")
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


def test_a_selection_with_an_equal_edition_is_not_the_expected_one() -> None:
    # Publication compares selection identity, never edition equality.
    a = prepare_model(_ACCOUNT, edition="same")
    twin = prepare_model(_ACCOUNT, edition="same")
    serving = ServingModel(a)
    with pytest.raises(PublicationConflictError):
        serving.publish(prepare_model(_ACCOUNT, edition="b"), expected=twin)
    assert serving.current() is a


def test_a_failed_candidate_preparation_leaves_the_held_selection_serving() -> None:
    a = prepare_model(_ACCOUNT, edition="a")
    serving = ServingModel(a)
    with pytest.raises(TypeError):
        serving.publish(prepare_model(object(), edition="b"), expected=a)  # pyright: ignore[reportArgumentType] - the failure under test
    assert serving.current() is a


def test_a_serving_model_holds_and_publishes_only_prepared_selections() -> None:
    with pytest.raises(TypeError, match="prepared ModelSelection"):
        ServingModel(_ACCOUNT)  # pyright: ignore[reportArgumentType] - the refusal under test
    serving = ServingModel(prepare_model(_ACCOUNT, edition="a"))
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
    a, b = prepare_model(_ACCOUNT, edition="a"), prepare_model(_ACCOUNT, edition="b")
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


def test_two_publishers_racing_one_expectation_leave_exactly_one_holding() -> None:
    a = prepare_model(_ACCOUNT, edition="a")
    candidates = [prepare_model(_ACCOUNT, edition=f"candidate-{n}") for n in range(8)]
    serving = ServingModel(a)
    # The compare/replace window itself, held here so that every publisher is
    # inside one before any of them can finish one. Holding it is what makes the
    # contention necessary rather than lucky: a check-then-set that compared
    # outside the window would not be stopped by it, and all eight would replace
    # what they each saw held.
    window = serving._lock  # pyright: ignore[reportPrivateUsage] - the window under test
    calling = threading.Barrier(len(candidates) + 1)
    refusals: list[PublicationConflictError] = []
    published: list[ModelSelection] = []
    outcomes = threading.Lock()

    def publish(candidate: ModelSelection) -> None:
        calling.wait(_RENDEZVOUS)
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
    for thread in threads:
        thread.start()
    calling.wait(_RENDEZVOUS)
    time.sleep(_SETTLE)
    assert all(thread.is_alive() for thread in threads), "a publisher completed outside the window"
    assert serving.current() is a
    window.release()
    for thread in threads:
        thread.join(_RENDEZVOUS)

    winner = serving.current()
    assert published == [winner]
    assert len(refusals) == len(candidates) - 1
    assert all(refused.expected is a and refused.held is winner for refused in refusals)


# --------------------------------------------------------------------------- #
# The static connection prepares once, under an edition of its own.            #
# --------------------------------------------------------------------------- #


def test_a_static_connection_prepares_once_under_a_generated_edition() -> None:
    first = connect(ScriptedPort(), _ACCOUNT, clock=FixedClock(FIXED))
    second = connect(ScriptedPort(), _ACCOUNT, clock=FixedClock(FIXED))
    editions = {
        db._selected.edition  # pyright: ignore[reportPrivateUsage] - the generated edition is the claim
        for db in (first, second)
    }
    assert len(editions) == 2
    assert all(edition.startswith("static-") for edition in editions)
