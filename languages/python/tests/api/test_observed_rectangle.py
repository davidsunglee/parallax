"""Which stored row a temporal write settles against, against real Postgres.

Two families of proof share the need for a real database: what a write leaves
CLOSED and CURRENT is only observable there, because a recording port reports
every addressed write as affecting a row whichever row it addressed.

The first is the observed-rectangle close under optimistic concurrency: one key
holding two current rectangles, read at two Valid-Time coordinates and corrected
from the first read's value. The Docker-free lane pins what the close ADDRESSES
and what its gate BINDS (`tests/unit/test_temporal_write_lowering.py`); only a
real database shows the gate MATCHED the right rectangle.

The second is repeated writes inside one attempt. Every flush of an attempt
stamps one Transaction Instant, so a later write can address a row an earlier
flush of the same attempt opened; such a row is revised or removed rather than
closed, and the cases read back complete current and historical state — every
Transaction-Time interval, every Valid-Time slice, and the payload carried
forward under both storage layouts — through both representations and both
effective strategies.

Like `test_stale_web_edit.py`, these are standalone Docker-backed proofs rather
than case-keyed `api_suite.EXAMPLES` entries: each is the developer choreography
of reads and writes inside one transaction, not a case's own authored
observation. Each `Database` connects with a
:class:`~parallax.conformance.scripted_clock.ScriptedClock`, so every
Transaction-Time instant is known in advance.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal, cast

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.story_models import Position
from parallax.core import (
    LATEST,
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.unit_work import RollbackOnlyError
from parallax.snapshot import ExecutionFailure, WriteEvidenceError, connect
from parallax.snapshot.handle import ScopedDatabase, Transaction
from tests._support.root_ownership import own_root

_POSITION = MODELS["position"]

# The three flushing transactions' instants: the two seeding inserts, then the
# correction.
_T1 = dt.datetime(2023, 11, 1, tzinfo=dt.UTC)
_T2 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T3 = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)

# The Valid-Time skeleton: the retroactive rectangle runs [V1, V2), the current
# one [V2, infinity), and the correction takes effect from V3 inside the latter.
# VP pins a read inside the retroactive rectangle.
_V1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_V2 = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_V3 = dt.datetime(2024, 8, 1, tzinfo=dt.UTC)
_VP = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)

_CURRENT_ROWS = (
    "select from_z, case when thru_z = 'infinity' then null else thru_z end as valid_end, val "
    "from position where out_z = 'infinity' order by from_z"
)
_CLOSED_ROWS = "select from_z from position where out_z <> 'infinity' order by from_z"


def test_an_optimistic_close_settles_against_the_rectangle_it_read(profile_run: Any) -> None:
    # A key carrying a retroactive rectangle beside its current one — what an
    # earlier correction leaves behind — is read latest, read again at a
    # Valid-Time instant inside the retroactive rectangle to compare against, and
    # then corrected from the value the FIRST read handed back. The current
    # rectangle is the one closed and split; the retroactive one is left exactly
    # as it was, still current on the Transaction-Time axis and still carrying its
    # own value. The distinction is that the optimistic gate cannot rescue a
    # misresolved address: it binds the same observation the address came from, so
    # a close aimed at the wrong rectangle gates on that rectangle's own `in_z`,
    # matches one row, and reports success. Which row was closed is therefore the
    # only observable that separates the two outcomes, and it needs a real
    # database to read.
    profile_run.reset(model_of(_POSITION), {})
    db = own_root(
        connect(profile_run.port, _POSITION, clock=ScriptedClock([_T1, _T2, _T3]))
    ).using_database_login()

    db.transact(
        lambda tx: tx.insert_until(
            Position(id=1, acct_num="A", value=Decimal("50.00")), valid_from=_V1, until=_V2
        )
    )
    db.transact(
        lambda tx: tx.insert(Position(id=1, acct_num="A", value=Decimal("100.00")), valid_from=_V2)
    )

    def correct(tx: Transaction) -> None:
        current = tx.find(Position.where(Position.id == 1).as_of(valid_time=LATEST)).result()
        tx.find(Position.where(Position.id == 1).as_of(valid_time=_VP)).result()
        tx.update(current.edit(value=Decimal("150.00")), valid_from=_V3)

    db.transact(correct, concurrency="optimistic")

    closed = profile_run.port.execute(_CLOSED_ROWS, [])
    assert [row[0] for row in closed] == [_V2]

    current_rows = profile_run.port.execute(_CURRENT_ROWS, [])
    assert current_rows == [
        (_V1, _V2, Decimal("50.00")),
        (_V2, _V3, Decimal("100.00")),
        (_V3, None, Decimal("150.00")),
    ]


# Repeated writes inside ONE attempt, every one of them through a fresh
# participating read of what the previous flush left. The attempt's first write
# closes the stored row into history and opens successors at the attempt's one
# Transaction Instant; each later write then addresses a row the attempt opened
# itself. Such a row has no history of its own to preserve, so it is revised in
# place, or removed and replaced, never closed into an empty `[T, T)` interval
# whose physical key would collide with the row the first flush closed.

_SAME_ATTEMPT = "same.attempt"
_SEEDED = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_ATTEMPT = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_FEB = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_APR = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_MAY = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)


class AttemptOrigin(ValueObject):
    country: Attr[str | None]


class AttemptSpec(ValueObject):
    title: Attr[str | None]
    origin: Attr[AttemptOrigin | None]


class ColumnsLog(TxTemporal, table="sa_columns_log", namespace=_SAME_ATTEMPT):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[AttemptSpec | None]


class DocumentLog(TxTemporal, table="sa_document_log", namespace=_SAME_ATTEMPT, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[AttemptSpec | None]


class ColumnsSpan(Bitemporal, table="sa_columns_span", namespace=_SAME_ATTEMPT):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[AttemptSpec | None]


class DocumentSpan(
    Bitemporal, table="sa_document_span", namespace=_SAME_ATTEMPT, layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[AttemptSpec | None]


_ATTEMPT_MODEL = DomainModel(ColumnsLog, DocumentLog, ColumnsSpan, DocumentSpan)
_SPEC = AttemptSpec(title="carried", origin=AttemptOrigin(country="NZ"))
_SPEC_DOCUMENT = {"title": "carried", "origin": {"country": "NZ"}}

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_REPRESENTATIONS: tuple[_Representation, ...] = ("typed", "wire")
_CONCURRENCIES: tuple[_Concurrency, ...] = ("optimistic", "locking")


def _attempt_db(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_ATTEMPT_MODEL), {})
    clock = ScriptedClock([_SEEDED, _ATTEMPT])
    return own_root(connect(profile_run.port, _ATTEMPT_MODEL, clock=clock)).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_SAME_ATTEMPT}.{entity.__name__}"


def _payload(entity: type[Any], member: str) -> str:
    if entity in (DocumentLog, DocumentSpan):
        return f"payload->'{member}'"
    return member


def _log_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        f"select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_payload(entity, 'label')}, {_payload(entity, 'spec')} "
        f"from {_LOG_TABLES[entity]} order by in_z, out_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _span_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        "case when thru_z = 'infinity' then null else thru_z end, "
        f"{_payload(entity, 'amount')}, {_payload(entity, 'spec')} "
        f"from {_SPAN_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


_LOG_TABLES = {ColumnsLog: "sa_columns_log", DocumentLog: "sa_document_log"}
_SPAN_TABLES = {ColumnsSpan: "sa_columns_span", DocumentSpan: "sa_document_span"}


def _plain(row: tuple[object, ...]) -> tuple[object, ...]:
    """A raw row with document-resident scalars in the spelling a Column holds."""
    return tuple(int(cell) if isinstance(cell, float) else cell for cell in row)


def _log_find(tx: Transaction, entity: type[Any], representation: _Representation) -> Any:
    if representation == "typed":
        return tx.find(entity.where(entity.id == 1)).result()
    name = _name(entity)
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    ).result()


def _span_find(
    tx: Transaction, entity: type[Any], representation: _Representation, at: dt.datetime | None
) -> Any:
    if representation == "typed":
        return tx.find(
            entity.where(entity.id == 1).as_of(valid_time=LATEST if at is None else at)
        ).result()
    name = _name(entity)
    pin = "latest" if at is None else f"{at:%Y-%m-%dT%H:%M:%S.%fZ}"
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
            "temporal": {
                "transaction-time": {"asOf": "latest"},
                "valid-time": {"asOf": pin},
            },
        }
    ).result()


def _log_update(
    tx: Transaction, observed: Any, representation: _Representation, label: str
) -> None:
    if representation == "typed":
        tx.update(observed.edit(label=label))
    else:
        tx.wire.update(observed, {"label": label})


def _span_update(
    tx: Transaction,
    observed: Any,
    representation: _Representation,
    amount: int,
    *,
    valid_from: dt.datetime,
    until: dt.datetime | None = None,
) -> None:
    if representation == "typed":
        edited = observed.edit(amount=amount)
        if until is None:
            tx.update(edited, valid_from=valid_from)
        else:
            tx.update_until(edited, valid_from=valid_from, until=until)
    elif until is None:
        tx.wire.update(observed, {"amount": amount}, valid_from=valid_from)
    else:
        tx.wire.update_until(observed, {"amount": amount}, valid_from=valid_from, until=until)


def _span_terminate(
    tx: Transaction,
    observed: Any,
    representation: _Representation,
    *,
    valid_from: dt.datetime,
    until: dt.datetime | None = None,
) -> None:
    if representation == "typed":
        if until is None:
            tx.terminate(observed, valid_from=valid_from)
        else:
            tx.terminate_until(observed, valid_from=valid_from, until=until)
    elif until is None:
        tx.wire.terminate(observed, valid_from=valid_from)
    else:
        tx.wire.terminate_until(observed, valid_from=valid_from, until=until)


def _wire_target(entity: type[Any]) -> dict[str, object]:
    name = _name(entity)
    return {"entity": name, "predicate": {"eq": {"attr": f"{name}.id", "value": 1}}}


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_a_transaction_time_row_the_attempt_opened_is_revised_in_place(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, label="seeded", spec=_SPEC)))

    def edit(tx: Transaction) -> None:
        _log_update(tx, _log_find(tx, entity, representation), representation, "first")
        _log_update(tx, _log_find(tx, entity, representation), representation, "second")

    db.transact(edit, concurrency=concurrency)

    assert _log_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, "seeded", _SPEC_DOCUMENT),
        (_ATTEMPT, None, "second", _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_terminating_a_transaction_time_row_the_attempt_opened_removes_it(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, label="seeded", spec=_SPEC)))

    def edit(tx: Transaction) -> None:
        _log_update(tx, _log_find(tx, entity, representation), representation, "first")
        opened = _log_find(tx, entity, representation)
        if representation == "typed":
            tx.terminate(opened)
        else:
            tx.wire.terminate(opened)

    db.transact(edit, concurrency=concurrency)

    assert _log_rows(profile_run, entity) == [(_SEEDED, _ATTEMPT, "seeded", _SPEC_DOCUMENT)]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_bitemporal_suffix_the_attempt_opened_is_split_in_place(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_JAN))

    def edit(tx: Transaction) -> None:
        current = _span_find(tx, entity, representation, None)
        _span_update(tx, current, representation, 150, valid_from=_FEB)
        suffix = _span_find(tx, entity, representation, None)
        _span_update(tx, suffix, representation, 175, valid_from=_MAR)

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _FEB, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _FEB, _MAR, 150, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAR, None, 175, _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_bounded_correction_inside_a_rectangle_the_attempt_opened_keeps_one_instant(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_JAN))

    def edit(tx: Transaction) -> None:
        current = _span_find(tx, entity, representation, _FEB)
        _span_update(tx, current, representation, 150, valid_from=_FEB, until=_APR)
        middle = _span_find(tx, entity, representation, _MAR)
        _span_update(tx, middle, representation, 175, valid_from=_MAR, until=_APR)

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _FEB, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _FEB, _MAR, 150, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAR, _APR, 175, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _APR, None, 100, _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_terminating_a_suffix_the_attempt_opened_replaces_it_with_its_head(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_JAN))

    def edit(tx: Transaction) -> None:
        current = _span_find(tx, entity, representation, None)
        _span_update(tx, current, representation, 150, valid_from=_FEB)
        suffix = _span_find(tx, entity, representation, None)
        _span_terminate(tx, suffix, representation, valid_from=_MAR)

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _FEB, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _FEB, _MAR, 150, _SPEC_DOCUMENT),
    ]


_ATTEMPT_HEAD = (_ATTEMPT, None, _JAN, _FEB, 100, _SPEC_DOCUMENT)
_SUFFIX_GEOMETRIES: dict[
    str, tuple[Callable[[Transaction, Any, _Representation], None], list[tuple[object, ...]]]
] = {
    "whole-value-change": (
        lambda tx, suffix, representation: _span_update(
            tx, suffix, representation, 175, valid_from=_FEB
        ),
        [_ATTEMPT_HEAD, (_ATTEMPT, None, _FEB, None, 175, _SPEC_DOCUMENT)],
    ),
    "bounded-termination": (
        lambda tx, suffix, representation: _span_terminate(
            tx, suffix, representation, valid_from=_MAR, until=_APR
        ),
        [
            _ATTEMPT_HEAD,
            (_ATTEMPT, None, _FEB, _MAR, 150, _SPEC_DOCUMENT),
            (_ATTEMPT, None, _APR, None, 150, _SPEC_DOCUMENT),
        ],
    ),
    "whole-termination": (
        lambda tx, suffix, representation: _span_terminate(
            tx, suffix, representation, valid_from=_FEB
        ),
        [_ATTEMPT_HEAD],
    ),
}


@pytest.mark.parametrize("geometry", list(_SUFFIX_GEOMETRIES))
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_suffix_the_attempt_opened_takes_each_geometry_without_history_of_its_own(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    geometry: str,
) -> None:
    write, opened = _SUFFIX_GEOMETRIES[geometry]
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_JAN))

    def edit(tx: Transaction) -> None:
        current = _span_find(tx, entity, representation, None)
        _span_update(tx, current, representation, 150, valid_from=_FEB)
        write(tx, _span_find(tx, entity, representation, None), representation)

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT),
        *opened,
    ]


@pytest.mark.parametrize("terminating", [False, True], ids=["update", "terminate"])
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_committed_rectangle_written_from_its_own_start_opens_no_empty_head(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    terminating: bool,
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_JAN))

    def edit(tx: Transaction) -> None:
        current = _span_find(tx, entity, representation, None)
        if terminating:
            _span_terminate(tx, current, representation, valid_from=_JAN)
        else:
            _span_update(tx, current, representation, 150, valid_from=_JAN)

    db.transact(edit, concurrency=concurrency)

    closed = (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT)
    assert _span_rows(profile_run, entity) == (
        [closed] if terminating else [closed, (_ATTEMPT, None, _JAN, None, 150, _SPEC_DOCUMENT)]
    )


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_terminating_a_rectangle_the_attempt_opened_from_its_own_end_leaves_it_writable(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # The termination covers none of the rectangle, so it changes no stored
    # state: a streamed root its page fetched before that termination is still
    # the current state and can be written from.
    db = _attempt_db(profile_run)

    def seed(tx: Transaction) -> None:
        for key in (1, 2):
            tx.insert(entity(id=key, amount=100, spec=_SPEC), valid_from=_JAN)

    db.transact(seed)
    name = _name(entity)

    def at_feb(tx: Transaction, key: int) -> Any:
        if representation == "typed":
            return tx.find(entity.where(entity.id == key).as_of(valid_time=_FEB)).result()
        return tx.wire.find(
            {
                "target": name,
                "predicate": {"eq": {"attr": f"{name}.id", "value": key}},
                "temporal": {
                    "transaction-time": {"asOf": "latest"},
                    "valid-time": {"asOf": f"{_FEB:%Y-%m-%dT%H:%M:%S.%fZ}"},
                },
            }
        ).result()

    def edit(tx: Transaction) -> None:
        _span_update(tx, at_feb(tx, 2), representation, 150, valid_from=_FEB, until=_MAR)
        stream = (
            tx.stream(entity.where(entity.id >= 1).as_of(valid_time=_FEB), batch_size=2)
            if representation == "typed"
            else tx.wire.stream(
                {
                    "target": name,
                    "predicate": {"all": {}},
                    "temporal": {
                        "transaction-time": {"asOf": "latest"},
                        "valid-time": {"asOf": f"{_FEB:%Y-%m-%dT%H:%M:%S.%fZ}"},
                    },
                    "orderBy": [{"attr": f"{name}.id", "direction": "asc"}],
                },
                batch_size=2,
            )
        )
        with stream as roots:
            for root in roots:
                key: object = (
                    cast("Any", root).id if representation == "typed" else cast("Any", root)["id"]
                )
                if key == 1:
                    _span_terminate(tx, at_feb(tx, 2), representation, valid_from=_MAR)
                    at_feb(tx, 2)
                    continue
                _span_update(tx, root, representation, 175, valid_from=_FEB, until=_MAR)

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT),
        (_SEEDED, None, _JAN, None, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _FEB, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _FEB, _MAR, 175, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAR, None, 100, _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_an_unsubmitted_read_of_a_changed_row_is_refused_and_a_fresh_read_carries_forward(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, label="seeded", spec=_SPEC)))
    other = {"title": "replaced", "origin": None}

    def edit(tx: Transaction) -> None:
        first = _log_find(tx, entity, representation)
        _log_update(tx, first, representation, "first")
        flushed = _log_find(tx, entity, representation)
        # A second read of the row the first write changed, never written from.
        unsubmitted = _log_find(tx, entity, representation)
        _log_update(tx, flushed, representation, "second")
        _log_find(tx, entity, representation)
        with pytest.raises(WriteEvidenceError) as refused:
            _log_update(tx, unsubmitted, representation, "stale")
        assert refused.value.code == "write-evidence-consumed"
        fresh = _log_find(tx, entity, representation)
        if representation == "typed":
            tx.update(fresh.edit(spec=AttemptSpec(title="replaced", origin=None)))
        else:
            tx.wire.update(fresh, {"spec": other})

    db.transact(edit, concurrency=concurrency)

    assert _log_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, "seeded", _SPEC_DOCUMENT),
        (_ATTEMPT, None, "second", other),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_an_own_change_leaves_reads_of_an_unaffected_rectangle_writable(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    profile_run.reset(model_of(_ATTEMPT_MODEL), {})
    clock = ScriptedClock([_SEEDED, _SEEDED, _ATTEMPT])
    db = own_root(connect(profile_run.port, _ATTEMPT_MODEL, clock=clock)).using_database_login()
    db.transact(
        lambda tx: tx.insert_until(entity(id=1, amount=50, spec=_SPEC), valid_from=_JAN, until=_MAR)
    )
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_MAR))

    def edit(tx: Transaction) -> None:
        early = _span_find(tx, entity, representation, _FEB)
        late = _span_find(tx, entity, representation, _APR)
        stale_late = _span_find(tx, entity, representation, _APR)
        _span_update(tx, late, representation, 150, valid_from=_APR)
        _span_find(tx, entity, representation, None)
        with pytest.raises(WriteEvidenceError):
            _span_update(tx, stale_late, representation, 175, valid_from=_APR)
        _span_update(tx, early, representation, 60, valid_from=_FEB)

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, _MAR, 50, _SPEC_DOCUMENT),
        (_SEEDED, _ATTEMPT, _MAR, None, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _FEB, 50, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _FEB, _MAR, 60, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAR, _APR, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _APR, None, 150, _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_a_row_committed_at_a_repeated_instant_is_closed_not_revised(
    profile_run: Any, entity: type[Any]
) -> None:
    # The clock answers the same instant to both attempts, so the stored row's
    # Transaction-Time start equals the second attempt's own; it was not that
    # attempt's opening, so it is closed into history as any committed row is.
    profile_run.reset(model_of(_ATTEMPT_MODEL), {})
    clock = ScriptedClock([_ATTEMPT, _ATTEMPT])
    db = own_root(connect(profile_run.port, _ATTEMPT_MODEL, clock=clock)).using_database_login()
    db.transact(lambda tx: tx.insert(entity(id=1, label="seeded", spec=_SPEC)))

    db.transact(lambda tx: _log_update(tx, _log_find(tx, entity, "typed"), "typed", "first"))

    assert _log_rows(profile_run, entity) == [
        (_ATTEMPT, _ATTEMPT, "seeded", _SPEC_DOCUMENT),
        (_ATTEMPT, None, "first", _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_a_row_the_attempt_inserted_is_revised_in_place(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    profile_run.reset(model_of(_ATTEMPT_MODEL), {})
    clock = ScriptedClock([_ATTEMPT])
    db = own_root(connect(profile_run.port, _ATTEMPT_MODEL, clock=clock)).using_database_login()

    def edit(tx: Transaction) -> None:
        # The predicate write's resolving read flushes the insert first, so the
        # row it selects is one the attempt itself opened.
        if representation == "typed":
            tx.insert(entity(id=1, label="inserted", spec=_SPEC))
            tx.update_where(entity.where(entity.id == 1), entity.label.set("edited"))
        else:
            tx.wire.insert(_name(entity), {"id": 1, "label": "inserted", "spec": _SPEC_DOCUMENT})
            tx.wire.update_where(_wire_target(entity), {"label": "edited"})

    db.transact(edit, concurrency=concurrency)

    assert _log_rows(profile_run, entity) == [(_ATTEMPT, None, "edited", _SPEC_DOCUMENT)]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan])
def test_a_predicate_write_revises_the_rectangles_the_attempt_opened(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100, spec=_SPEC), valid_from=_JAN))

    def edit(tx: Transaction) -> None:
        current = _span_find(tx, entity, representation, None)
        _span_update(tx, current, representation, 150, valid_from=_FEB)
        if representation == "typed":
            tx.update_where(entity.where(entity.id == 1), entity.amount.set(175), valid_from=_MAR)
            tx.update_until_where(
                entity.where(entity.id == 1), entity.amount.set(200), valid_from=_APR, until=_MAY
            )
        else:
            tx.wire.update_where(_wire_target(entity), {"amount": 175}, valid_from=_MAR)
            tx.wire.update_until_where(
                _wire_target(entity), {"amount": 200}, valid_from=_APR, until=_MAY
            )

    db.transact(edit, concurrency=concurrency)

    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, _JAN, None, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _JAN, _FEB, 100, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _FEB, _MAR, 150, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAR, _APR, 175, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _APR, _MAY, 200, _SPEC_DOCUMENT),
        (_ATTEMPT, None, _MAY, None, 175, _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_a_predicate_termination_removes_the_row_the_attempt_opened(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, label="seeded", spec=_SPEC)))

    def edit(tx: Transaction) -> None:
        for label in ("first", "second"):
            if representation == "typed":
                tx.update_where(entity.where(entity.id == 1), entity.label.set(label))
            else:
                tx.wire.update_where(_wire_target(entity), {"label": label})
            _log_find(tx, entity, representation)
        if representation == "typed":
            tx.terminate_where(entity.where(entity.id == 1))
        else:
            tx.wire.terminate_where(_wire_target(entity))

    db.transact(edit, concurrency=concurrency)

    assert _log_rows(profile_run, entity) == [(_SEEDED, _ATTEMPT, "seeded", _SPEC_DOCUMENT)]


def test_a_caught_dependent_read_failure_still_rolls_the_attempt_back(profile_run: Any) -> None:
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(ColumnsLog(id=1, label="seeded", spec=_SPEC)))
    outcomes: list[BaseException] = []

    def edit(tx: Transaction) -> str:
        _log_update(tx, _log_find(tx, ColumnsLog, "typed"), "typed", "first")
        tx.insert(DocumentLog(id=1, label="other", spec=_SPEC))
        # A second current row for the stored key: the flush the next read
        # forces fails on the physical key, and the callback swallows it.
        tx.insert(ColumnsLog(id=1, label="duplicate", spec=_SPEC))
        for attempted in (ColumnsLog, DocumentLog):
            try:
                _log_find(tx, attempted, "typed")
            except Exception as failure:
                outcomes.append(failure)
        return "withheld"

    with pytest.raises(ExecutionFailure) as escaped:
        db.transact(edit)
    flush_failure, refused = outcomes
    assert isinstance(flush_failure, DatabaseError)
    assert isinstance(refused, RollbackOnlyError)
    assert refused.__cause__ is flush_failure
    assert isinstance(escaped.value.cause, RollbackOnlyError)
    assert _log_rows(profile_run, ColumnsLog) == [(_SEEDED, None, "seeded", _SPEC_DOCUMENT)]
    assert _log_rows(profile_run, DocumentLog) == []


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_a_streamed_root_fetched_before_an_own_change_cannot_write_its_stale_state(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # The page delivering both roots was fetched before the second root's row
    # changed; that root's evidence is built only when it is written from, and
    # is judged against the state its page acquired.
    profile_run.reset(model_of(_ATTEMPT_MODEL), {})
    clock = ScriptedClock([_SEEDED, _SEEDED, _ATTEMPT])
    db = own_root(connect(profile_run.port, _ATTEMPT_MODEL, clock=clock)).using_database_login()
    for key in (1, 2):
        db.transact(lambda tx, key=key: tx.insert(entity(id=key, label="seeded", spec=_SPEC)))
    name = _name(entity)
    refusals: list[str] = []

    def by_id(tx: Transaction, key: int) -> Any:
        if representation == "typed":
            return tx.find(entity.where(entity.id == key)).result()
        return tx.wire.find(
            {
                "target": name,
                "predicate": {"eq": {"attr": f"{name}.id", "value": key}},
                "temporal": {"transaction-time": {"asOf": "latest"}},
            }
        ).result()

    def edit(tx: Transaction) -> None:
        stream = (
            tx.stream(entity.where(entity.id >= 1), batch_size=2)
            if representation == "typed"
            else tx.wire.stream(
                {
                    "target": name,
                    "predicate": {"all": {}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                    "orderBy": [{"attr": f"{name}.id", "direction": "asc"}],
                },
                batch_size=2,
            )
        )
        with stream as roots:
            for root in roots:
                key: object = (
                    cast("Any", root).id if representation == "typed" else cast("Any", root)["id"]
                )
                if key == 1:
                    _log_update(tx, by_id(tx, 2), representation, "changed")
                    by_id(tx, 2)
                    continue
                with pytest.raises(WriteEvidenceError) as refused:
                    _log_update(tx, root, representation, "stale")
                refusals.append(refused.value.code)

    db.transact(edit, concurrency=concurrency)

    assert refusals == ["write-evidence-consumed"]
    assert _log_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, "seeded", _SPEC_DOCUMENT),
        (_SEEDED, None, "seeded", _SPEC_DOCUMENT),
        (_ATTEMPT, None, "changed", _SPEC_DOCUMENT),
    ]


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog])
def test_a_read_stays_writable_until_a_change_to_its_state_completes(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # A local edit changes nothing stored, and a submitted write changes nothing
    # until its flush completes, so a second read of the same state stays
    # writable through both; only the completed change makes it ineligible.
    db = _attempt_db(profile_run)
    db.transact(lambda tx: tx.insert(entity(id=1, label="seeded", spec=_SPEC)))
    replaced = {"title": "replaced", "origin": None}

    def edit(tx: Transaction) -> None:
        first = _log_find(tx, entity, representation)
        second = _log_find(tx, entity, representation)
        if representation == "typed":
            second.edit(label="draft")  # a local draft, never submitted
            tx.update(first.edit(spec=AttemptSpec(title="replaced", origin=None)))
        else:
            tx.wire.update(first, {"spec": replaced})
        _log_update(tx, second, representation, "pending")
        _log_find(tx, entity, representation)
        with pytest.raises(WriteEvidenceError):
            _log_update(tx, second, representation, "after")

    db.transact(edit, concurrency=concurrency)

    assert _log_rows(profile_run, entity) == [
        (_SEEDED, _ATTEMPT, "seeded", _SPEC_DOCUMENT),
        (_ATTEMPT, None, "pending", replaced),
    ]
