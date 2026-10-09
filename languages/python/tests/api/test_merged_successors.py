"""Adjacent rows one temporal write produces with identical stored state merge
into one row, against real Postgres (`m-temporal-write` *Merging produced
successors*).

A two-rectangle history — [January, April) at 100 and [April, July) at 200 —
is amended or replaced from February until June, through Typed and Wire, under
both concurrency strategies and both storage layouts. Every case reads back
every row, current and historical: each original is still inactivated under
its own proof, and the parts the write leaves identical are one row. Later
writes of the same attempt reach the merged row through each original's own
part of it, never through another's.

Standalone Docker-backed proofs, like `test_disjoint_target_writes.py`; every
`Database` connects with a
:class:`~parallax.conformance.scripted_clock.ScriptedClock`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.execution import (
    ExecutionFailure,
    KeyedWriteValueError,
    TransactionTimePinReadOnlyError,
)
from parallax.core.unit_work import WriteEvidenceError, WritePreconditionError
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.adoption import raises_contextualized
from tests._support.root_ownership import own_root

_NAMESPACE = "temporal.merged"


class Spec(ValueObject):
    title: Attr[str | None]


class ColumnsSpan(Bitemporal, table="mrg_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]


class DocumentSpan(Bitemporal, table="mrg_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]


class Tag(Entity, table="mrg_tag", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL = DomainModel(ColumnsSpan, DocumentSpan, Tag)
_TABLES: dict[type[Any], str] = {
    ColumnsSpan: "mrg_columns_span",
    DocumentSpan: "mrg_document_span",
}

type _Concurrency = Literal["optimistic", "locking"]
type _Representation = Literal["typed", "wire"]
type _Row = tuple[object, ...]

_SPAN_AXES = pytest.mark.parametrize(
    "entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"]
)
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])

_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_TB = dt.datetime(2024, 1, 20, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in range(1, 8)
)
_S = {"title": "s"}


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)))
    ).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity is DocumentSpan else member


def _rows(profile_run: Any, entity: type[Any]) -> list[_Row]:
    members = ", ".join(_member(entity, name) for name in ("amount", "label", "spec"))
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, {members} "
        f"from {_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [
        tuple(int(cell) if isinstance(cell, float) else cell for cell in row)
        for row in profile_run.port.execute(sql, [])
    ]


def _seeded(
    profile_run: Any,
    entity: type[Any],
    *instants: dt.datetime,
    labels: tuple[str, str] = ("a", "a"),
) -> ScopedDatabase:
    """Span 1 as [January, April) at 100 opened at T0 and [April, July) at 200
    opened at T1, and tag 1."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _T1, *instants)

    def first(tx: Transaction) -> None:
        tx.insert(
            entity(id=1, amount=100, label=labels[0], spec=Spec(title="s")),
            valid_from=_JAN,
            until=_APR,
        )
        tx.insert(Tag(id=1, label="t"))

    db.transact(first)
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=200, label=labels[1], spec=Spec(title="s")),
            valid_from=_APR,
            until=_JUL,
        )
    )
    return db


def _find(tx: Transaction, entity: type[Any], at: dt.datetime) -> Any:
    return tx.find(entity.where(entity.id == 1).as_of(valid_time=at)).result()


def _wire_find(tx: Transaction, entity: type[Any], at: dt.datetime) -> Any:
    return tx.wire.find(
        {
            "target": _name(entity),
            "predicate": {"eq": {"attr": f"{_name(entity)}.id", "value": 1}},
            "temporal": {
                "transaction-time": {"asOf": "latest"},
                "valid-time": {"asOf": at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")},
            },
        }
    ).result()


def _amend(tx: Transaction, entity: type[Any], representation: _Representation) -> None:
    """Amend span 1 from February until June to 150, from a read at
    February."""
    if representation == "typed":
        tx.amend(_find(tx, entity, _FEB).edit(amount=150), until=_JUN)
    else:
        tx.wire.amend(_wire_find(tx, entity, _FEB), {"amount": 150}, until=_JUN)


def _history(labels: tuple[str, str] = ("a", "a")) -> list[_Row]:
    return [
        (_T0, _TA, _JAN, _APR, 100, labels[0], _S),
        (_T1, _TA, _APR, _JUL, 200, labels[1], _S),
    ]


# --------------------------------------------------------------------------- #
# The ticket's acceptance shapes.                                              #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_an_amendment_across_two_rectangles_leaves_three_current_rows(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded(profile_run, entity, _TA)
    db.transact(lambda tx: _amend(tx, entity, representation), concurrency=concurrency)
    # Both originals are closed as history; the changed parts of both hold one
    # state and are one row.
    assert _rows(profile_run, entity) == [
        *_history(),
        (_TA, None, _JAN, _FEB, 100, "a", _S),
        (_TA, None, _FEB, _JUN, 150, "a", _S),
        (_TA, None, _JUN, _JUL, 200, "a", _S),
    ]


@_SPAN_AXES
@_REPRESENTATIONS
def test_unassigned_members_that_differ_keep_four_current_rows(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seeded(profile_run, entity, _TA, labels=("A", "B"))
    db.transact(lambda tx: _amend(tx, entity, representation))
    assert _rows(profile_run, entity) == [
        *_history(("A", "B")),
        (_TA, None, _JAN, _FEB, 100, "A", _S),
        (_TA, None, _FEB, _APR, 150, "A", _S),
        (_TA, None, _APR, _JUN, 150, "B", _S),
        (_TA, None, _JUN, _JUL, 200, "B", _S),
    ]


@_SPAN_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_uniform_replacement_across_differing_rectangles_leaves_three_current_rows(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded(profile_run, entity, _TA, labels=("A", "B"))

    def replace(tx: Transaction) -> None:
        if representation == "typed":
            tx.replace(_find(tx, entity, _FEB).edit(amount=150, label="R"), until=_JUN)
        else:
            tx.wire.replace(
                _wire_find(tx, entity, _FEB),
                {"amount": 150, "label": "R", "spec": {"title": "s"}},
                until=_JUN,
            )

    db.transact(replace, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        *_history(("A", "B")),
        (_TA, None, _JAN, _FEB, 100, "A", _S),
        (_TA, None, _FEB, _JUN, 150, "R", _S),
        (_TA, None, _JUN, _JUL, 200, "B", _S),
    ]


@_SPAN_AXES
@_STRATEGIES
def test_a_failed_proof_rolls_back_the_merge_with_everything_else(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        tx.wire.amend_if(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_JUN, tx_start=_T1
        )

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn, concurrency=concurrency)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert [row[1] for row in _rows(profile_run, entity)] == [None, None]


# --------------------------------------------------------------------------- #
# Later writes of the same attempt reach the merged row.                       #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("pin", [_MAR, _MAY], ids=["first-original-part", "second-original-part"])
def test_a_fresh_read_of_the_merged_row_writes_from_its_own_pin(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, pin: dt.datetime
) -> None:
    db = _seeded(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        _amend(tx, entity, "typed")
        # The read flushes the merge; its pin, not the merged row's February
        # start, is where the next write starts.
        reread = _find(tx, entity, pin)
        assert (reread.amount, reread.label) == (150, "a")
        tx.amend(reread.edit(label="z"), until=_JUN)

    db.transact(fn, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        *_history(),
        (_TA, None, _JAN, _FEB, 100, "a", _S),
        (_TA, None, _FEB, pin, 150, "a", _S),
        (_TA, None, pin, _JUN, 150, "z", _S),
        (_TA, None, _JUN, _JUL, 200, "a", _S),
    ]


@_SPAN_AXES
def test_a_historical_read_of_a_merged_original_writes_nothing(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity, _TA, _TB)
    db.transact(lambda tx: _amend(tx, entity, "typed"))
    before = _rows(profile_run, entity)

    def fn(tx: Transaction) -> None:
        historical = tx.find(
            entity.where(entity.id == 1).as_of(valid_time=_MAY, tx_time=_T1)
        ).result()
        assert (historical.amount, historical.label) == (200, "a")
        tx.amend(historical.edit(label="z"), until=_JUN)

    with raises_contextualized(
        TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"
    ):
        db.transact(fn)
    assert _rows(profile_run, entity) == before


@_SPAN_AXES
@pytest.mark.parametrize("unchanged", [False, True], ids=["changed", "unchanged"])
def test_a_source_a_completed_write_spent_is_refused_however_its_rows_merged(
    profile_run: Any, entity: type[Any], unchanged: bool
) -> None:
    db = _seeded(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, _FEB)
        tx.amend(source.edit(amount=100 if unchanged else 150), until=_JUN)
        _find(tx, entity, _MAY)  # flush the write that spent the source
        with pytest.raises(WriteEvidenceError) as spent:
            tx.amend(source.edit(label="z"), until=_MAR)
        assert spent.value.code == "write-evidence-consumed"

    db.transact(fn)


def _barrier(tx: Transaction) -> None:
    tx.amend_where(Tag.where(Tag.id == 1), Tag.label.set("q"))


@_SPAN_AXES
@_STRATEGIES
def test_a_write_admitted_before_a_barrier_reaches_the_merged_row_through_its_own_original(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        early, may = _find(tx, entity, _FEB), _find(tx, entity, _MAY)
        tx.amend(early.edit(amount=150), until=_JUN)
        _barrier(tx)
        # Admitted on the second original before anything flushed: the merged
        # row holds May in the part that original contributed, so its own
        # proof carries the write there.
        tx.amend(may.edit(label="z"), until=_JUN)

    db.transact(fn, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        *_history(),
        (_TA, None, _JAN, _FEB, 100, "a", _S),
        (_TA, None, _FEB, _MAY, 150, "a", _S),
        (_TA, None, _MAY, _JUN, 150, "z", _S),
        (_TA, None, _JUN, _JUL, 200, "a", _S),
    ]


# --------------------------------------------------------------------------- #
# An insertion keeps only its own part of a merged row.                         #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "flushed"])
def test_an_insertion_stands_while_its_part_of_a_merged_row_does_and_ends_with_it(
    profile_run: Any, entity: type[Any], flushed: bool
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _TA)
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=200, label="b", spec=Spec(title="s")), valid_from=_MAY, until=_JUL
        )
    )

    def fn(tx: Transaction) -> None:
        opened = entity(id=1, amount=100, label="a", spec=Spec(title="s"))
        tx.insert(opened, valid_from=_JAN, until=_APR)
        if flushed:
            _find(tx, entity, _FEB)
        replaced = opened.edit(amount=300, label="r")
        tx.replace(replaced, until=_JUN)
        # The merged row [January, June) holds the insertion over January to
        # April; its later part came from the stored row and the gap.
        _find(tx, entity, _MAY)
        tx.amend(replaced.edit(label="s"), until=_FEB)
        _find(tx, entity, _MAY)
        # Terminating the insertion's whole part leaves the stored row's part
        # and the gap standing, but nothing it opened: its authority ends.
        tx.terminate(replaced, until=_APR)
        _find(tx, entity, _MAY)
        with pytest.raises(KeyedWriteValueError) as ended:
            tx.amend(replaced.edit(label="t"), until=_FEB)
        assert ended.value.code == "write-value-not-stored"

    db.transact(fn)
    current = [row for row in _rows(profile_run, entity) if row[1] is None]
    assert current == [
        (_TA, None, _APR, _JUN, 300, "r", _S),
        (_TA, None, _JUN, _JUL, 200, "b", _S),
    ]
