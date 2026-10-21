"""What a predicate-selected write's public verb returns, and when its statement
and its failures happen, against real Postgres."""

from __future__ import annotations

from typing import Any, Literal

import pytest

from parallax.core import MANY_TO_ONE, Attr, DomainModel, Entity, Rel, attr, rel
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.unit_work import MissingTargetError, RollbackOnlyError, StaleWriteError
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.adoption import raises_contextualized
from tests._support.root_ownership import own_root

_NAMESPACE = "predicate.counts"


class Shelf(Entity, table="pc_shelf", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)


class Bin(Entity, table="pc_bin", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    shelf_id: Attr[int | None]
    label: Attr[str] = attr(max_length=16)
    quantity: Attr[int]
    shelf: Rel[Shelf | None] = rel(cardinality=MANY_TO_ONE, join=("shelf_id", "id"))


_MODEL = DomainModel(Shelf, Bin)

type _Representation = Literal["typed", "wire"]
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_BIN = f"{_NAMESPACE}.Bin"


def _db(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(connect(profile_run.port, _MODEL)).using_database_login()
    db.transact(
        lambda tx: [
            tx.insert(Shelf(id=1, name="top")),
            tx.insert(Shelf(id=2, name="low")),
            tx.insert(Bin(id=1, shelf_id=1, label="a", quantity=1)),
            tx.insert(Bin(id=2, shelf_id=1, label="b", quantity=5)),
            tx.insert(Bin(id=3, shelf_id=2, label="a", quantity=1)),
            tx.insert(Bin(id=4, shelf_id=None, label="c", quantity=9)),
        ]
    )
    return db


def _control(profile_run: Any, *statements: str) -> None:
    control = profile_run.control()
    try:
        for statement in statements:
            control.execute_write(statement, [])
    finally:
        control.close()


def _bins(profile_run: Any) -> list[tuple[object, ...]]:
    rows = profile_run.port.execute("select id, label, quantity from pc_bin order by id", [])
    return [tuple(row) for row in rows]


def _wire_selection(predicate: dict[str, object]) -> dict[str, object]:
    return {"entity": _BIN, "predicate": predicate}


def _amend_quantity_below(
    tx: TxnContext, representation: _Representation, bound: int, label: str
) -> int:
    if representation == "typed":
        return tx.amend_where(Bin.where(Bin.quantity < bound), Bin.label.set(label))
    selection = _wire_selection({"lessThan": {"path": f"{_BIN}.quantity", "value": bound}})
    return tx.wire.amend_where(selection, {"label": label})


@_REPRESENTATIONS
def test_an_amendment_counts_every_row_it_matched_unchanged_ones_included(
    profile_run: Any, representation: _Representation
) -> None:
    db = _db(profile_run)
    # Bins 1 and 3 already hold label "a"; the update still matches both.
    counts = db.transact(
        lambda tx: [
            _amend_quantity_below(tx, representation, 2, "a"),
            _amend_quantity_below(tx, representation, 2, "z"),
            _amend_quantity_below(tx, representation, 0, "never"),
        ]
    )
    assert counts == [2, 2, 0]
    assert _bins(profile_run) == [(1, "z", 1), (2, "b", 5), (3, "z", 1), (4, "c", 9)]


@_REPRESENTATIONS
def test_a_replacement_counts_every_row_it_matched(
    profile_run: Any, representation: _Representation
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> int:
        if representation == "typed":
            return tx.replace_where(
                Bin.where(Bin.quantity > 4), Bin(id=0, shelf_id=None, label="r", quantity=7)
            )
        return tx.wire.replace_where(
            _wire_selection({"greaterThan": {"path": f"{_BIN}.quantity", "value": 4}}),
            {"shelfId": None, "label": "r", "quantity": 7},
        )

    assert db.transact(fn) == 2
    assert _bins(profile_run) == [(1, "a", 1), (2, "r", 7), (3, "a", 1), (4, "r", 7)]


@_REPRESENTATIONS
def test_a_deletion_counts_the_rows_it_deleted(
    profile_run: Any, representation: _Representation
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> list[int]:
        if representation == "typed":
            return [
                tx.delete_where(Bin.where(Bin.label == "a")),
                tx.delete_where(Bin.where(Bin.label == "a")),
            ]
        selection = _wire_selection({"eq": {"path": f"{_BIN}.label", "value": "a"}})
        return [tx.wire.delete_where(selection), tx.wire.delete_where(selection)]

    assert db.transact(fn) == [2, 0]
    assert _bins(profile_run) == [(2, "b", 5), (4, "c", 9)]


@_REPRESENTATIONS
def test_the_key_selecting_forms_count_the_rows_their_selection_matched(
    profile_run: Any, representation: _Representation
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> list[int]:
        if representation == "typed":
            return [
                tx.amend_where(Bin.where(Bin.shelf.name == "top"), Bin.quantity.set(3)),
                tx.delete_where(Bin.where(Bin.shelf.name == "low")),
            ]
        top = _wire_selection({"eq": {"path": f"{_BIN}.shelf.name", "value": "top"}})
        low = _wire_selection({"eq": {"path": f"{_BIN}.shelf.name", "value": "low"}})
        return [tx.wire.amend_where(top, {"quantity": 3}), tx.wire.delete_where(low)]

    assert db.transact(fn) == [2, 1]
    assert _bins(profile_run) == [(1, "a", 3), (2, "b", 3), (4, "c", 9)]


@_REPRESENTATIONS
def test_an_empty_mutation_answers_zero(profile_run: Any, representation: _Representation) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> int:
        if representation == "typed":
            return tx.amend_where(Bin.where(Bin.quantity < 2))
        return tx.wire.amend_where(
            _wire_selection({"lessThan": {"path": f"{_BIN}.quantity", "value": 2}}), {}
        )

    assert db.transact(fn) == 0
    assert _bins(profile_run) == [(1, "a", 1), (2, "b", 5), (3, "a", 1), (4, "c", 9)]


def test_an_update_a_before_update_trigger_suppresses_is_not_counted(profile_run: Any) -> None:
    db = _db(profile_run)
    _control(
        profile_run,
        "create trigger pc_bin_unchanged before update on pc_bin "
        "for each row execute function suppress_redundant_updates_trigger()",
    )
    # Bins 1 and 3 already hold label "a": the trigger skips both, so neither is
    # written nor counted; bin 2 changes.
    assert db.transact(lambda tx: _amend_quantity_below(tx, "typed", 6, "a")) == 1


def test_a_predicate_write_sees_what_was_buffered_before_it(profile_run: Any) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> int:
        tx.insert(Bin(id=5, shelf_id=None, label="new", quantity=0))
        source = tx.find(Bin.where(Bin.id == 2)).result()
        tx.amend(source.edit(quantity=0))
        return _amend_quantity_below(tx, "typed", 1, "empty")

    assert db.transact(fn) == 2
    assert _bins(profile_run)[1] == (2, "empty", 0)
    assert _bins(profile_run)[-1] == (5, "empty", 0)


def test_an_amendment_through_a_source_keeps_a_predicate_writes_assignments(
    profile_run: Any,
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(Bin.where(Bin.id == 2)).result()
        tx.amend_where(Bin.where(Bin.id == 2), Bin.label.set("marked"))
        tx.amend(source.edit(quantity=8))

    db.transact(fn)
    assert _bins(profile_run)[1] == (2, "marked", 8)


def test_a_replacement_through_a_source_writes_its_literal_state_over_them(
    profile_run: Any,
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(Bin.where(Bin.id == 2)).result()
        tx.amend_where(Bin.where(Bin.id == 2), Bin.label.set("marked"))
        tx.replace(source.edit(quantity=8))

    db.transact(fn)
    # The source's own label is what a replacement states.
    assert _bins(profile_run)[1] == (2, "b", 8)


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_a_source_whose_row_a_predicate_write_deleted_fails_its_own_write(
    profile_run: Any, concurrency: Literal["optimistic", "locking"]
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(Bin.where(Bin.id == 2)).result()
        assert tx.delete_where(Bin.where(Bin.quantity > 4)) == 2
        # Nothing identified the rows the predicate deleted, so the source is
        # admitted and its keyed update finds no row.
        tx.amend(source.edit(quantity=1))

    with raises_contextualized(MissingTargetError | StaleWriteError):  # type: ignore[arg-type]
        db.transact(fn, concurrency=concurrency, max_retries=0)
    assert len(_bins(profile_run)) == 4


def test_a_statement_failure_surfaces_at_the_call_and_dooms_the_transaction(
    profile_run: Any,
) -> None:
    db = _db(profile_run)
    _control(profile_run, "alter table pc_bin add constraint pc_bin_stocked check (quantity >= 0)")
    caught: list[BaseException] = []

    def fn(tx: TxnContext) -> None:
        tx.insert(Bin(id=6, shelf_id=None, label="pending", quantity=1))
        try:
            tx.amend_where(Bin.where(Bin.id == 1), Bin.quantity.set(-1))
        except DatabaseError as failure:
            caught.append(failure)
        tx.find(Bin.where(Bin.id == 1))

    with raises_contextualized(RollbackOnlyError):
        db.transact(fn, max_retries=0)
    assert len(caught) == 1
    # Everything the attempt wrote, the insert its flush ran first included, is
    # rolled back.
    assert _bins(profile_run) == [(1, "a", 1), (2, "b", 5), (3, "a", 1), (4, "c", 9)]


def test_a_deferred_constraint_a_predicate_write_violates_fails_at_commit(
    profile_run: Any,
) -> None:
    db = _db(profile_run)
    _control(
        profile_run,
        "create table pc_ref (id bigint primary key, shelf_id bigint not null "
        "references pc_shelf (id) deferrable initially deferred)",
        "insert into pc_ref (id, shelf_id) values (1, 2)",
    )
    answered: list[int] = []

    def fn(tx: TxnContext) -> None:
        tx.delete_where(Bin.where(Bin.shelf_id == 2))
        answered.append(tx.delete_where(Shelf.where(Shelf.id == 2)))

    with raises_contextualized(DatabaseError):
        db.transact(fn, max_retries=0)
    assert answered == [1]
    assert len(_bins(profile_run)) == 4
