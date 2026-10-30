"""The Page's own schedule for publishing its roots: when states defer, which
projections a root reaches, and what a root's release frees."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

import pytest

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    DomainModel,
    Entity,
    Rel,
    TxTemporal,
    attr,
    opt_lock,
    rel,
)
from parallax.core.base import INFINITY
from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.entity import model_of
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
)
from parallax.core.read_delivery._page import (
    ROOT_LEVEL,
    ChildSlot,
    Page,
    PageBuilder,
    PageSchedule,
    ViewSchema,
    _rows,
    entity_state,
    page_rows,
    page_schedule,
    reach_into,
    release_finished_rows,
)
from parallax.core.temporal_read import Pin
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._prepared_read_support import compiled_read, convert_cells

_NAMESPACE = "page.schedule"


class Ledger(Entity, table="ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    entries: Rel[tuple[Entry, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "ledger_id"))


class Entry(Entity, table="entry", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    ledger_id: Attr[int]
    ledger: Rel[Ledger | None] = rel(reverse_of="entries")


class Account(Entity, table="account", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(optimistic_locking=True)


class Journal(TxTemporal, table="journal", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)


_META = model_of(DomainModel(Ledger, Entry, Account, Journal))
_CATALOGED = CatalogedModel(_META)
_WRITE_EVIDENCE = opt_lock.write_evidence(_META)
_ANIMAL = corpus_model("animal")

_ROWS: Mapping[str, Mapping[str, object]] = {
    "Ledger": {"id": 1},
    "Account": {"id": 1, "version": 1},
    "Journal": {"id": 1, "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC), "out_z": INFINITY},
}


def _identity(model: Metamodel, name: str) -> EntityIdentity:
    return next(entity.identity for entity in model.entities if entity.identity.name == name)


def _view(owner: str, name: str, model: Metamodel = _META) -> RelationshipViewKey:
    return RelationshipViewKey(RelationshipIdentity(_identity(model, owner), name))


_ENTRIES = _view("Ledger", "entries")
_LEDGER = _view("Entry", "ledger")


def _node(builder: PageBuilder, entity: str, cells: Mapping[str, object]) -> int:
    return convert_cells(
        _CATALOGED, compiled_read(_META, entity), cells, builder, source=ROOT_LEVEL
    )


def _flat_page(*entities: str) -> Page:
    """One Page with no relationship slots, rooted at one row of each named
    Entity, each its own logical node."""
    builder = PageBuilder(ViewSchema.of())
    roots = tuple(
        _node(builder, entity, {**_ROWS[entity], "id": position})
        for position, entity in enumerate(entities)
    )
    return builder.finish(roots, Pin())


def _graph_builder(*, ledger: str = "forward") -> PageBuilder:
    """A builder whose one source level attaches ``Ledger.entries`` and an
    ``Entry.ledger`` slot that is a ``forward`` hop or a ``reference`` back to
    already-converted Ledger claims."""
    targets = frozenset({_identity(_META, "Ledger")}) if ledger == "reference" else None
    return PageBuilder(ViewSchema(((ChildSlot(_ENTRIES), ChildSlot(_LEDGER, targets=targets)),)))


def _entry(builder: PageBuilder, entry_id: int, ledger_id: int = 1) -> int:
    return _node(builder, "Entry", {"id": entry_id, "ledger_id": ledger_id})


def _reached(page: Page, root: int) -> list[int]:
    reached: list[int] = []
    reach_into(page_rows(page), root, reached)
    return reached


def _refuse_walking(monkeypatch: pytest.MonkeyPatch) -> None:
    def walked(*_args: object) -> None:
        raise AssertionError("an edge-free root was walked")

    monkeypatch.setattr(_rows, "push_edges", walked)


# --------------------------------------------------------------------------- #
# Scheduling.                                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("roots", "defers"),
    [
        pytest.param(("Ledger",), False, id="unversioned"),
        pytest.param(("Account",), True, id="explicitly-versioned"),
        pytest.param(("Journal",), True, id="transaction-time-derived"),
        pytest.param(("Account", "Journal"), True, id="every-family-carries-evidence"),
        pytest.param(("Account", "Ledger"), False, id="mixed-family"),
    ],
)
def test_an_atomic_page_defers_states_exactly_when_every_root_family_carries_write_evidence(
    roots: tuple[str, ...], defers: bool
) -> None:
    page = _flat_page(*roots)

    schedule = page_schedule(page, _WRITE_EVIDENCE, atomic=True)

    assert schedule.defers_states is defers
    if not defers:
        assert schedule.last_uses is None
        return
    assert schedule.last_uses is not None
    projection_last, logical_last = schedule.last_uses
    assert tuple(projection_last) == tuple(range(len(roots)))
    assert tuple(logical_last) == tuple(range(len(roots)))


def test_an_atomic_page_with_no_roots_defers_vacuously_and_has_no_last_use() -> None:
    page = PageBuilder(ViewSchema.of()).finish((), Pin())

    schedule = page_schedule(page, _WRITE_EVIDENCE, atomic=True)

    assert schedule.defers_states is True
    assert schedule.last_uses is not None
    assert [tuple(last) for last in schedule.last_uses] == [(), ()]


def test_a_grouped_claim_releases_at_last_use_and_marks_every_claimant() -> None:
    builder = PageBuilder(ViewSchema.of())
    first = _node(builder, "Ledger", {"id": 1})
    other = _node(builder, "Ledger", {"id": 2})
    again = _node(builder, "Ledger", {"id": 1})
    page = builder.finish((first, other, again), Pin())

    schedule = page_schedule(page, _WRITE_EVIDENCE, atomic=True)

    assert schedule.defers_states is False
    assert schedule.last_uses is not None
    projection_last, logical_last = schedule.last_uses
    assert tuple(projection_last) == (2, 1, 2)
    assert tuple(logical_last) == (2, 1)


def test_a_stream_neither_defers_nor_releases_at_last_use() -> None:
    builder = PageBuilder(ViewSchema.of())
    roots = tuple(_node(builder, "Account", {"id": 1, "version": 1}) for _ in range(2))
    page = builder.finish(roots, Pin())

    assert page_schedule(page, _WRITE_EVIDENCE, atomic=False) == PageSchedule(None, False)


def test_scheduling_judges_no_root_state() -> None:
    builder = _graph_builder()
    ledgers = tuple(_node(builder, "Ledger", {"id": ledger}) for ledger in (1, 2))
    for ledger in ledgers:
        builder.write_view(ledger, _ENTRIES, (_entry(builder, 10 + ledger, ledger),))
    page = builder.finish(ledgers, Pin())
    rows = page_rows(page)

    page_schedule(page, _WRITE_EVIDENCE, atomic=True)
    page_schedule(page, lambda _entity: True, atomic=True)

    assert all(
        rows.judged_states.singleton(logical) is None
        for logical in range(len(rows.fetched_rows_by_logical_row))
    )


def test_an_edge_free_page_computes_its_last_uses_without_walking_a_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _flat_page("Account", "Account", "Journal")
    _refuse_walking(monkeypatch)

    schedule = page_schedule(page, _WRITE_EVIDENCE, atomic=True)

    assert schedule.last_uses is not None
    assert tuple(schedule.last_uses[0]) == (0, 1, 2)


# --------------------------------------------------------------------------- #
# Reach.                                                                      #
# --------------------------------------------------------------------------- #
def test_an_edge_free_root_reaches_itself_into_a_cleared_buffer_without_a_walk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _flat_page("Ledger", "Account")
    _refuse_walking(monkeypatch)
    reached = [99, 98]

    reach_into(page_rows(page), 1, reached)

    assert reached == [1]


def test_reach_follows_slots_in_order_then_overwritten_arms_each_projection_once() -> None:
    builder = _graph_builder()
    ledger = _node(builder, "Ledger", {"id": 1})
    first, second, replaced = (_entry(builder, entry) for entry in (11, 12, 13))
    builder.write_view(ledger, _ENTRIES, (replaced,))
    builder.write_view(ledger, _ENTRIES, (first, second))
    for entry in (first, second):
        builder.write_view(entry, _LEDGER, ledger)
    page = builder.finish((ledger,), Pin())

    assert _reached(page, ledger) == [ledger, first, second, replaced]
    assert _reached(page, first) == [first, ledger, second, replaced]


def test_reach_never_follows_a_back_reference() -> None:
    builder = _graph_builder(ledger="reference")
    ledger = _node(builder, "Ledger", {"id": 1})
    entry = _entry(builder, 11)
    builder.write_view(ledger, _ENTRIES, (entry,))
    builder.write_reference(
        entry,
        _LEDGER,
        _identity(_META, "Ledger"),
        AttributeIdentity(_identity(_META, "Entry"), "ledger_id"),
    )
    page = builder.finish((entry, ledger), Pin())

    assert page_rows(page).view_rows[entry]
    assert _reached(page, entry) == [entry]
    assert _reached(page, ledger) == [ledger, entry]


# --------------------------------------------------------------------------- #
# Release.                                                                    #
# --------------------------------------------------------------------------- #
def _shared_entry_page() -> tuple[Page, tuple[int, int], int]:
    """Two Ledger roots both attaching the one keyed Entry, judged already."""
    builder = _graph_builder()
    ledgers = (_node(builder, "Ledger", {"id": 1}), _node(builder, "Ledger", {"id": 2}))
    shared = _entry(builder, 11)
    for ledger in ledgers:
        builder.write_view(ledger, _ENTRIES, (shared,))
    page = builder.finish(ledgers, Pin())
    entity_state(page_rows(page), shared)
    return page, ledgers, shared


def test_raw_only_release_frees_reached_member_rows_and_keeps_judged_states() -> None:
    page, (first, second), shared = _shared_entry_page()
    rows = page_rows(page)
    logical = rows.logical_rows[shared]

    release_finished_rows(page, PageSchedule(None, False), 0, _reached(page, first))

    assert rows.member_rows[first] == () and rows.member_rows[shared] == ()
    assert rows.member_rows[second] != ()
    assert rows.keys[shared] is not None
    assert rows.view_rows[first]
    assert rows.judged_states.singleton(logical) is not None


def test_last_use_release_frees_a_projection_and_its_state_once_no_later_root_reaches_it() -> None:
    page, (first, second), shared = _shared_entry_page()
    rows = page_rows(page)
    logical = rows.logical_rows[shared]
    schedule = page_schedule(page, lambda _entity: True, atomic=True)

    release_finished_rows(page, schedule, 0, _reached(page, first))

    assert (rows.member_rows[first], rows.keys[first], rows.view_rows[first]) == ((), None, ())
    assert rows.member_rows[shared] == ()
    assert rows.keys[shared] is not None and rows.view_rows[shared]
    assert rows.judged_states.singleton(logical) is not None

    reached = _reached(page, second)
    release_finished_rows(page, schedule, 1, reached)
    released = (list(rows.member_rows), list(rows.keys), list(rows.logical_rows))
    release_finished_rows(page, schedule, 1, reached)

    assert (rows.keys[shared], rows.view_rows[shared], rows.stored_values[shared]) == (
        None,
        (),
        None,
    )
    assert rows.judged_states.singleton(logical) is None
    assert rows.fetched_rows_by_logical_row[logical] == 0
    assert (list(rows.member_rows), list(rows.keys), list(rows.logical_rows)) == released


def _shared_keyless_animal(owners: Sequence[int]) -> tuple[Page, int]:
    """Person roots ``owners``, each attaching one keyless Animal claim of an
    unknown concrete, whose payload decoder stays pending for every root
    reaching it."""
    animals = _view("Person", "animals", _ANIMAL)
    builder = PageBuilder(ViewSchema.of(animals))
    cataloged = CatalogedModel(_ANIMAL)
    animal = convert_cells(
        cataloged,
        compiled_read(_ANIMAL, "Animal"),
        {
            "id": 7,
            "kind": "unicorn",
            "name": "Uni",
            "owner_id": 1,
            "license_id": None,
            "indoor": None,
            "bark_volume": None,
            "tusk_length": None,
        },
        builder,
        source=ROOT_LEVEL,
    )
    people = compiled_read(_ANIMAL, "Person")
    roots = tuple(
        convert_cells(
            cataloged, people, {"id": owner, "name": f"P{owner}"}, builder, source=ROOT_LEVEL
        )
        for owner in owners
    )
    for root in roots:
        builder.write_view(root, animals, (animal,))
    return builder.finish(roots, Pin()), animal


@pytest.mark.parametrize("last_use", [False, True], ids=["raw-only", "before-last-use"])
def test_a_keyless_pending_claim_keeps_its_raw_row_until_its_last_use(last_use: bool) -> None:
    page, animal = _shared_keyless_animal((1, 2))
    rows = page_rows(page)
    assert rows.keys[animal] is None and rows.decoders.pending(animal)
    first, second = rows.roots
    schedule = (
        page_schedule(page, lambda _entity: True, atomic=True)
        if last_use
        else PageSchedule(None, False)
    )

    release_finished_rows(page, schedule, 0, _reached(page, first))

    assert rows.member_rows[first] == ()
    assert rows.member_rows[animal] != ()
    release_finished_rows(page, schedule, 1, _reached(page, second))
    assert (rows.member_rows[animal] == ()) is last_use
