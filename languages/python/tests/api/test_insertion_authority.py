"""What an admitted insertion's source edits, against real Postgres.

An insertion's original source stays an editing handle for its whole attempt:
before its insert flushes, edits transform the pending opening; after a helper
read flushes it, the same edits transform the rows the attempt opened. Each case
reads back every stored row — Transaction-Time interval, Valid-Time slice and
payload, under both storage layouts — so equivalent workflows are shown to leave
equivalent state, with one Transaction Instant and no history of their own,
through both representations and both effective strategies.

Standalone Docker-backed proofs, like `test_observed_rectangle.py`: each is a
developer choreography inside one transaction rather than a case's authored
observation. A :class:`~parallax.conformance.scripted_clock.ScriptedClock` makes
every instant known in advance.
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
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.execution import (
    ExecutionFailure,
    KeyedWriteValueError,
)
from parallax.core.unit_work import MissingTargetError
from parallax.snapshot import connect
from parallax.snapshot.handle import ScopedDatabase, Transaction
from tests._support.root_ownership import own_root

_NAMESPACE = "insertion.authority"
_EARLIER = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_ATTEMPT = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)
_LATER = dt.datetime(2024, 7, 15, tzinfo=dt.UTC)
_JAN, _MAR, _MAY, _JUN, _AUG, _SEP, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5, 6, 8, 9, 12)
)


class Origin(ValueObject):
    country: Attr[str | None]


class Spec(ValueObject):
    title: Attr[str | None]
    origin: Attr[Origin | None]


class ColumnsSpan(Bitemporal, table="ia_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[Spec | None]


class DocumentSpan(Bitemporal, table="ia_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[Spec | None]


class ColumnsLog(TxTemporal, table="ia_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class DocumentLog(TxTemporal, table="ia_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class ColumnsLedger(Entity, table="ia_columns_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentLedger(Entity, table="ia_document_ledger", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


_MODEL = DomainModel(
    ColumnsSpan, DocumentSpan, ColumnsLog, DocumentLog, ColumnsLedger, DocumentLedger
)
_SPEC = Spec(title="carried", origin=Origin(country="NZ"))
_SPEC_DOCUMENT = {"title": "carried", "origin": {"country": "NZ"}}
_TABLES: dict[type[Any], str] = {
    ColumnsSpan: "ia_columns_span",
    DocumentSpan: "ia_document_span",
    ColumnsLog: "ia_columns_log",
    DocumentLog: "ia_document_log",
    ColumnsLedger: "ia_columns_ledger",
    DocumentLedger: "ia_document_ledger",
}
_DOCUMENT = (DocumentSpan, DocumentLog, DocumentLedger)

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_REPRESENTATIONS: tuple[_Representation, ...] = ("typed", "wire")
_CONCURRENCIES: tuple[_Concurrency, ...] = ("optimistic", "locking")


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    clock = ScriptedClock(list(instants or (_ATTEMPT,)))
    return own_root(connect(profile_run.port, _MODEL, clock=clock)).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in _DOCUMENT else member


def _plain(row: tuple[object, ...]) -> tuple[object, ...]:
    """A raw row with document-resident scalars in the spelling a Column holds."""
    return tuple(int(cell) if isinstance(cell, float) else cell for cell in row)


def _span_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        "case when thru_z = 'infinity' then null else thru_z end, "
        f"{_member(entity, 'amount')}, {_member(entity, 'spec')} "
        f"from {_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _log_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_member(entity, 'label')} from {_TABLES[entity]} order by in_z, out_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _ledger_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = f"select id, {_member(entity, 'label')}, version from {_TABLES[entity]} order by id"
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


class _Opened:
    """The source one insertion was stated through, in either representation,
    and the writes it authorizes spelled once for both."""

    def __init__(self, tx: Transaction, representation: _Representation, source: Any) -> None:
        self._tx = tx
        self._representation = representation
        self.source = source

    def update(self, until: dt.datetime | None = None, **changes: object) -> None:
        bounds: dict[str, Any] = {} if until is None else {"until": until}
        if self._representation == "typed":
            self.source = self.source.edit(**changes)
            self._tx.update(self.source, **bounds)
        else:
            self._tx.wire.update(self.source, changes, **bounds)

    def terminate(self, until: dt.datetime | None = None) -> None:
        bounds: dict[str, Any] = {} if until is None else {"until": until}
        if self._representation == "typed":
            self._tx.terminate(self.source, **bounds)
        else:
            self._tx.wire.terminate(self.source, **bounds)


def _insert_span(
    tx: Transaction,
    entity: type[Any],
    representation: _Representation,
    *,
    valid_from: dt.datetime,
    until: dt.datetime | None = None,
    amount: int = 100,
) -> _Opened:
    bounds: dict[str, Any] = {} if until is None else {"until": until}
    if representation == "typed":
        source = entity(id=1, amount=amount, spec=_SPEC)
        tx.insert(source, valid_from=valid_from, **bounds)
        return _Opened(tx, representation, source)
    node = tx.wire.insert(
        _name(entity),
        {"id": 1, "amount": amount, "spec": _SPEC_DOCUMENT},
        valid_from=valid_from,
        **bounds,
    )
    return _Opened(tx, representation, node)


def _read_span(
    tx: Transaction, entity: type[Any], representation: _Representation, at: dt.datetime
) -> _Opened:
    if representation == "typed":
        return _Opened(
            tx, representation, tx.find(entity.where(entity.id == 1).as_of(valid_time=at)).result()
        )
    name = _name(entity)
    pin = f"{at:%Y-%m-%dT%H:%M:%S.%fZ}"
    node = tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}, "valid-time": {"asOf": pin}},
        }
    ).result()
    return _Opened(tx, representation, node)


def _read_log(tx: Transaction, entity: type[Any], representation: _Representation) -> None:
    if representation == "typed":
        tx.find(entity.where(entity.id == 1)).result()
        return
    name = _name(entity)
    tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    ).result()


def _current(*slices: tuple[dt.datetime, dt.datetime | None, int]) -> list[tuple[object, ...]]:
    """Rows the attempt opened and left current, each carrying the opening's spec."""
    return [(_ATTEMPT, None, start, end, amount, _SPEC_DOCUMENT) for start, end, amount in slices]


# --------------------------------------------------------------------------- #
# The pending-opening matrix, with and without a helper read between the insert #
# and the edit. Every edit starts at the opening's anchor, January; a bound      #
# inside the opening splits it, a bound at or beyond its end changes all of it, #
# and nothing extends it. The flushed variant revises or removes the rows the   #
# attempt opened, so both leave the same current rows at one instant and no    #
# history.                                                                      #
# --------------------------------------------------------------------------- #
_MATRIX: tuple[
    tuple[str, dt.datetime | None, dt.datetime | None, list[tuple[object, ...]]], ...
] = (
    ("unbounded-plain", None, None, _current((_JAN, None, 150))),
    ("unbounded-until", None, _JUN, _current((_JAN, _JUN, 150), (_JUN, None, 100))),
    ("finite-plain", _SEP, None, _current((_JAN, _SEP, 150))),
    ("finite-until-inside", _SEP, _JUN, _current((_JAN, _JUN, 150), (_JUN, _SEP, 100))),
    ("finite-until-its-end", _SEP, _SEP, _current((_JAN, _SEP, 150))),
    ("finite-until-beyond", _SEP, _DEC, _current((_JAN, _SEP, 150))),
)


@pytest.mark.parametrize("helper_read", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
@pytest.mark.parametrize(
    ("opening_end", "until", "expected"),
    [case[1:] for case in _MATRIX],
    ids=[case[0] for case in _MATRIX],
)
def test_an_insertion_source_edits_only_the_coverage_its_opening_holds(
    profile_run: Any,
    opening_end: dt.datetime | None,
    until: dt.datetime | None,
    expected: list[tuple[object, ...]],
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    helper_read: bool,
) -> None:
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        opened = _insert_span(tx, entity, representation, valid_from=_JAN, until=opening_end)
        if helper_read:
            _read_span(tx, entity, representation, _MAR)
        opened.update(until=until, amount=150)

    db.transact(edit, concurrency=concurrency)
    assert _span_rows(profile_run, entity) == expected


@pytest.mark.parametrize("helper_read", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_literal_reset_through_the_insertion_source_writes_the_reset_value(
    profile_run: Any, entity: type[Any], representation: _Representation, helper_read: bool
) -> None:
    # 100, then 150 until September, then 100 again: the last edit sets 100
    # over the whole opening, which a helper read between the edits does not
    # change.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        opened = _insert_span(tx, entity, representation, valid_from=_JAN)
        opened.update(until=_SEP, amount=150)
        if helper_read:
            _read_span(tx, entity, representation, _MAR)
        opened.update(amount=100)

    db.transact(edit)
    assert _span_rows(profile_run, entity) == (
        _current((_JAN, _SEP, 100), (_SEP, None, 100))
        if helper_read
        else _current((_JAN, None, 100))
    )


@pytest.mark.parametrize("helper_read", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_resubmitted_draft_reasserts_its_whole_touched_set(
    profile_run: Any, entity: type[Any], helper_read: bool
) -> None:
    # A Typed draft's assignments are cumulative: extending an earlier draft
    # after a later edit was submitted reasserts the earlier draft's amount
    # beside the member it adds, whether or not a helper read flushed between.
    # A Wire change document states one call's keys, so it has no counterpart.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        opened = entity(id=1, amount=100, spec=_SPEC)
        tx.insert(opened, valid_from=_JAN)
        draft = opened.edit(amount=150)
        tx.update(draft)
        if helper_read:
            _read_span(tx, entity, "typed", _MAR)
        tx.update(opened.edit(amount=200))
        tx.update(draft.edit(spec=None))

    db.transact(edit)
    assert _span_rows(profile_run, entity) == [(_ATTEMPT, None, _JAN, None, 150, None)]


@pytest.mark.parametrize("insertion_first", [True, False], ids=["insertion-first", "read-first"])
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_insertion_and_observed_assignments_compose_over_unequal_windows_after_a_flush(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    insertion_first: bool,
) -> None:
    # Opening [March, September) at 100; a read at May flushes it and yields an
    # observed source. The insertion source assigns 150 until June and the
    # observed source 175 until August; the later-authored write wins where
    # they overlap, and the opening's own value survives beyond both.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        opened = _insert_span(tx, entity, representation, valid_from=_MAR, until=_SEP)
        observed = _read_span(tx, entity, representation, _MAY)
        writes = [
            lambda: opened.update(until=_JUN, amount=150),
            lambda: observed.update(until=_AUG, amount=175),
        ]
        for write in writes if insertion_first else reversed(writes):
            write()

    db.transact(edit, concurrency=concurrency)
    assert _span_rows(profile_run, entity) == (
        _current((_MAR, _MAY, 150), (_MAY, _AUG, 175), (_AUG, _SEP, 100))
        if insertion_first
        else _current((_MAR, _JUN, 150), (_JUN, _AUG, 175), (_AUG, _SEP, 100))
    )


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_an_insertion_source_revises_its_transaction_time_row_across_helper_reads(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        if representation == "typed":
            source: Any = entity(id=1, label="opened", spec=_SPEC)
            tx.insert(source)
        else:
            source = tx.wire.insert(
                _name(entity), {"id": 1, "label": "opened", "spec": _SPEC_DOCUMENT}
            )
        for label in ("first", "second"):
            _read_log(tx, entity, representation)
            if representation == "typed":
                source = source.edit(label=label)
                tx.update(source)
            else:
                tx.wire.update(source, {"label": label})

    db.transact(edit, concurrency=concurrency)
    assert _log_rows(profile_run, entity) == [(_ATTEMPT, None, "second")]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLedger, DocumentLedger])
def test_an_insertion_source_advances_its_version_across_helper_reads(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        if representation == "typed":
            source: Any = entity(id=1, label="opened")
            tx.insert(source)
        else:
            source = tx.wire.insert(_name(entity), {"id": 1, "label": "opened"})
        for label in ("first", "second"):
            tx.find(entity.where(entity.id == 1)).result()
            if representation == "typed":
                source = source.edit(label=label)
                tx.update(source)
            else:
                tx.wire.update(source, {"label": label})

    db.transact(edit, concurrency=concurrency)
    assert _ledger_rows(profile_run, entity) == [(1, "second", 3)]


# --------------------------------------------------------------------------- #
# Removal and reinsertion. Removing everything an insertion opened retires its  #
# authority and admits a fresh insertion of the object, which executes after   #
# the removal; anything less keeps the first insertion standing.              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_completely_removed_insertion_admits_a_fresh_one_at_its_coordinates(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        first = _insert_span(tx, entity, representation, valid_from=_JAN)
        first.update(until=_JUN, amount=150)
        _read_span(tx, entity, representation, _MAR)
        first.terminate()
        second = _insert_span(tx, entity, representation, valid_from=_JAN, amount=200)
        with pytest.raises(KeyedWriteValueError) as refused:
            first.update(amount=1)
        assert refused.value.code == "write-value-not-stored"
        _read_span(tx, entity, representation, _MAR)
        second.update(until=_MAY, amount=250)

    db.transact(edit, concurrency=concurrency)
    assert _span_rows(profile_run, entity) == _current((_JAN, _MAY, 250), (_MAY, None, 200))


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_partial_removal_keeps_the_insertion_standing(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    # Terminating up to May leaves the opening's tail stored, so a second
    # insertion is a repeat; the first insertion's source still edits from its
    # anchor, which the removal took, and so cannot be written either.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        first = _insert_span(tx, entity, representation, valid_from=_JAN)
        _read_span(tx, entity, representation, _MAR)
        first.terminate(until=_MAY)
        with pytest.raises(KeyedWriteValueError) as refused:
            _insert_span(tx, entity, representation, valid_from=_JAN, amount=200)
        assert refused.value.code == "write-value-already-stored"

    db.transact(edit)
    assert _span_rows(profile_run, entity) == _current((_MAY, None, 100))


@pytest.mark.parametrize("helper_read", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_removal_that_moves_an_openings_end_keeps_the_insertion_standing(
    profile_run: Any, entity: type[Any], representation: _Representation, helper_read: bool
) -> None:
    # Terminating from May removes the stored opening's row and opens its
    # January head, which continues the insertion: a second insertion is a
    # repeat whether or not the removal has flushed, and once it has, the first
    # insertion's source still edits from its anchor.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        first = _insert_span(tx, entity, representation, valid_from=_JAN)
        _read_span(tx, entity, representation, _MAY).terminate()
        if helper_read:
            _read_span(tx, entity, representation, _MAR)
        with pytest.raises(KeyedWriteValueError) as refused:
            _insert_span(tx, entity, representation, valid_from=_JAN, amount=200)
        assert refused.value.code == "write-value-already-stored"
        if not helper_read:
            _read_span(tx, entity, representation, _MAR)
        first.update(amount=150)

    db.transact(edit)
    assert _span_rows(profile_run, entity) == _current((_JAN, _MAY, 150))


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_an_insertion_source_edits_across_an_interior_gap_its_anchor_survives(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # A read at May removes [May, June) from the stored opening, leaving its
    # anchor, January, covered. The insertion source's next plain edit reaches
    # every surviving interval from January on and leaves the gap a gap.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        opened = _insert_span(tx, entity, representation, valid_from=_JAN)
        _read_span(tx, entity, representation, _MAY).terminate(until=_JUN)
        _read_span(tx, entity, representation, _MAR)
        opened.update(amount=150)

    db.transact(edit, concurrency=concurrency)
    assert _span_rows(profile_run, entity) == _current((_JAN, _MAY, 150), (_JUN, None, 150))


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_an_edit_through_an_insertion_whose_anchor_was_removed_rolls_back(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    # A read at January removes the opening up to March; the insertion's
    # anchor is January, where nothing is current any more, so its next edit
    # fails at the flush that executes it and the whole attempt rolls back.
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        first = _insert_span(tx, entity, representation, valid_from=_JAN)
        _read_span(tx, entity, representation, _JAN).terminate(until=_MAR)
        _read_span(tx, entity, representation, _MAR)
        first.update(amount=150)

    with pytest.raises(ExecutionFailure) as failure:
        db.transact(edit)
    assert isinstance(failure.value.cause, MissingTargetError)
    assert _span_rows(profile_run, entity) == []


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_an_insertion_authority_ends_with_its_attempt(
    profile_run: Any, representation: _Representation
) -> None:
    db = _db(profile_run, _ATTEMPT, _LATER)
    opened: list[_Opened] = []

    def insert(tx: Transaction) -> None:
        opened.append(_insert_span(tx, ColumnsSpan, representation, valid_from=_JAN))

    db.transact(insert)

    def later(tx: Transaction) -> None:
        source = opened[0]
        source._tx = tx  # pyright: ignore[reportPrivateUsage] - the held source, in a new attempt
        with pytest.raises(KeyedWriteValueError) as refused:
            source.update(amount=150)
        assert refused.value.code == "write-value-not-stored"

    db.transact(later)
    assert _span_rows(profile_run, ColumnsSpan) == _current((_JAN, None, 100))


@pytest.mark.parametrize("helper_read", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_rewritten_earlier_coverage_is_no_part_of_an_insertion_it_precedes(
    profile_run: Any, entity: type[Any], representation: _Representation, helper_read: bool
) -> None:
    db = _db(profile_run, _EARLIER, _ATTEMPT)
    db.transact(lambda tx: _insert_span(tx, entity, representation, valid_from=_JAN, until=_MAR))

    def edit(tx: Transaction) -> None:
        inserted = _insert_span(tx, entity, representation, valid_from=_MAY, amount=300)
        _read_span(tx, entity, representation, _JAN).update(until=_MAR, amount=150)
        _read_span(tx, entity, representation, _MAY)
        inserted.terminate()
        if helper_read:
            _read_span(tx, entity, representation, _JAN)
        _insert_span(tx, entity, representation, valid_from=_MAY, amount=400)

    db.transact(edit)
    assert _span_rows(profile_run, entity) == [
        (_EARLIER, _ATTEMPT, _JAN, _MAR, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _MAR, 150, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAY, None, 400, _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("helper_read", [False, True], ids=["pending", "after-a-helper-read"])
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_reinsertion_at_a_later_anchor_is_removed_from_its_own_anchor(
    profile_run: Any, entity: type[Any], representation: _Representation, helper_read: bool
) -> None:
    db = _db(profile_run)

    def edit(tx: Transaction) -> None:
        first = _insert_span(tx, entity, representation, valid_from=_JAN)
        _read_span(tx, entity, representation, _MAR)
        first.terminate()
        second = _insert_span(tx, entity, representation, valid_from=_MAR, amount=200)
        _read_span(tx, entity, representation, _MAR)
        second.terminate()
        if helper_read:
            assert tx.find(entity.where(entity.id == 1).as_of(valid_time=_MAR)).results() == []
        _insert_span(tx, entity, representation, valid_from=_MAR, amount=300)

    db.transact(edit)
    assert _span_rows(profile_run, entity) == _current((_MAR, None, 300))
