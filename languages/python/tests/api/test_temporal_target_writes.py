"""Caller-addressed patch and replacement of temporal objects, against real Postgres.

A web client holds a key, the Valid-Time instant it edits from, and the
Transaction-Time start an earlier query returned. Each case commits a starting
history, writes it from the caller's own milestone in a later transaction, and
reads back every row — current and historical, under both storage layouts: what
each existing interval became, what a gap or a scheduled termination left
absent or a replacement filled, and what history the write closed. When the
caller's milestone no longer holds, nothing changes and nothing retries; when
another session changes a later row after the flush read it, the attempt rolls
back and retries with the caller's milestone unchanged.

Standalone Docker-backed proofs, like `test_target_writes.py`: each is a
developer choreography rather than a case's authored observation. Every
`Database` connects with a
:class:`~parallax.conformance.scripted_clock.ScriptedClock`, so every
Transaction-Time instant is known in advance.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Literal, cast

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure, KeyedWriteValueError
from parallax.core.unit_work import (
    OptimisticLockConflictError,
    WriteEvidenceError,
    WritePreconditionError,
)
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root
from tests.api._coverage_interleaving import AfterCoverageRead

_NAMESPACE = "temporal.target"


class Spec(ValueObject):
    title: Attr[str | None]


class Mark(ValueObject):
    code: Attr[str | None]


class ColumnsSpan(Bitemporal, table="ttw_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class DocumentSpan(Bitemporal, table="ttw_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class ColumnsLog(TxTemporal, table="ttw_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class DocumentLog(TxTemporal, table="ttw_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


_MODEL = DomainModel(ColumnsSpan, DocumentSpan, ColumnsLog, DocumentLog)
_SPANS = (ColumnsSpan, DocumentSpan)
_LOGS = (ColumnsLog, DocumentLog)
_DOCUMENT = (DocumentSpan, DocumentLog)
_TABLES: dict[type[Any], str] = {
    ColumnsSpan: "ttw_columns_span",
    DocumentSpan: "ttw_document_span",
    ColumnsLog: "ttw_columns_log",
    DocumentLog: "ttw_document_log",
}

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_SPAN_AXES = pytest.mark.parametrize("entity", _SPANS, ids=["columns", "document"])
_LOG_AXES = pytest.mark.parametrize("entity", _LOGS, ids=["columns", "document"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])

# Seeding instants, the writing attempts' instants, and a peer's.
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_TP = dt.datetime(2024, 1, 5, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_TB = dt.datetime(2024, 1, 20, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _AUG, _SEP = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in range(1, 10)
)

_S1 = {"title": "s1"}
_S2 = {"title": "s2"}
_M = [{"code": "m"}]


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)))
    ).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in _DOCUMENT else member


def _plain(row: tuple[object, ...]) -> tuple[object, ...]:
    """A raw row with document-resident scalars in the spelling a Column holds."""
    return tuple(int(cell) if isinstance(cell, float) else cell for cell in row)


def _span_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    members = ", ".join(_member(entity, name) for name in ("amount", "label", "spec", "marks"))
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, {members} "
        f"from {_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _log_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    members = ", ".join(_member(entity, name) for name in ("label", "spec", "marks"))
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{members} from {_TABLES[entity]} order by in_z, out_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _seeded_spans(profile_run: Any, entity: type[Any], *instants: dt.datetime) -> ScopedDatabase:
    """Two rectangles of span 1 — [January, April) at T0 and [June, August) at
    T1 — with a gap between them and nothing after August."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _T1, *instants)
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=(Mark(code="m"),)),
            valid_from=_JAN,
            until=_APR,
        )
    )
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=200, label="b", spec=Spec(title="s2"), marks=()),
            valid_from=_JUN,
            until=_AUG,
        )
    )
    return db


def _span_patch(
    tx: Transaction,
    entity: type[Any],
    *,
    valid_from: dt.datetime = _MAR,
    until: dt.datetime | None = None,
    tx_start: dt.datetime = _T0,
    **changes: object,
) -> None:
    if until is None:
        tx.wire.amend_if(
            _name(entity), {"id": 1, **changes}, valid_from=valid_from, tx_start=tx_start
        )
    else:
        tx.wire.amend_if(
            _name(entity),
            {"id": 1, **changes},
            valid_from=valid_from,
            until=until,
            tx_start=tx_start,
        )


def _span_replace(
    tx: Transaction,
    entity: type[Any],
    representation: _Representation,
    *,
    valid_from: dt.datetime = _MAR,
    until: dt.datetime | None = None,
    tx_start: dt.datetime = _T0,
    amount: int = 300,
    label: str = "r",
) -> None:
    bounds: dict[str, Any] = {"valid_from": valid_from, "tx_start": tx_start}
    if until is not None:
        bounds["until"] = until
    if representation == "typed":
        tx.replace_if(entity(id=1, amount=amount, label=label), **bounds)
    else:
        tx.wire.replace_if(_name(entity), {"id": 1, "amount": amount, "label": label}, **bounds)


def _span_find(tx: Transaction, entity: type[Any], at: dt.datetime) -> Any:
    return tx.find(entity.where(entity.id == 1).as_of(valid_time=at)).result()


type _SpanRow = tuple[object, ...]

_SEED_HISTORY: tuple[_SpanRow, ...] = (
    (_T0, _TA, _JAN, _APR, 100, "a", _S1, _M),
    (_T1, _TA, _JUN, _AUG, 200, "b", _S2, []),
)
_SEED_CURRENT: list[_SpanRow] = [
    (_T0, None, _JAN, _APR, 100, "a", _S1, _M),
    (_T1, None, _JUN, _AUG, 200, "b", _S2, []),
]


# --------------------------------------------------------------------------- #
# Range geometry: per-interval patch, gaps and termination, replacement fill.  #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_STRATEGIES
def test_a_patch_assigns_each_existing_interval_from_its_start_and_creates_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    db.transact(lambda tx: _span_patch(tx, entity, amount=150), concurrency=concurrency)
    # The start lies inside [January, April); the later rectangle keeps its own
    # label, document and occurrences, the gap and everything after August stay
    # absent, and the token the caller stated certified only the start.
    assert _span_rows(profile_run, entity) == [
        *_SEED_HISTORY,
        (_TA, None, _JAN, _MAR, 100, "a", _S1, _M),
        (_TA, None, _MAR, _APR, 150, "a", _S1, _M),
        (_TA, None, _JUN, _AUG, 150, "b", _S2, []),
    ]


@_SPAN_AXES
@_STRATEGIES
def test_a_bounded_patch_stops_at_its_exclusive_end_inside_a_later_interval(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    db.transact(
        lambda tx: _span_patch(tx, entity, until=_JUL, label="p", spec={"title": "whole"}),
        concurrency=concurrency,
    )
    assert _span_rows(profile_run, entity) == [
        *_SEED_HISTORY,
        (_TA, None, _JAN, _MAR, 100, "a", _S1, _M),
        (_TA, None, _MAR, _APR, 100, "p", {"title": "whole"}, _M),
        (_TA, None, _JUN, _JUL, 200, "p", {"title": "whole"}, []),
        (_TA, None, _JUL, _AUG, 200, "b", _S2, []),
    ]


@_SPAN_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_replacement_states_its_complete_state_over_gaps_and_after_termination(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    db.transact(lambda tx: _span_replace(tx, entity, representation), concurrency=concurrency)
    replaced: _SpanRow = (300, "r", None, [])
    assert _span_rows(profile_run, entity) == [
        *_SEED_HISTORY,
        (_TA, None, _JAN, _MAR, 100, "a", _S1, _M),
        (_TA, None, _MAR, _APR, *replaced),
        (_TA, None, _APR, _JUN, *replaced),
        (_TA, None, _JUN, _AUG, *replaced),
        (_TA, None, _AUG, None, *replaced),
    ]


@_SPAN_AXES
@_REPRESENTATIONS
def test_a_bounded_replacement_fills_only_up_to_its_exclusive_end(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    db.transact(lambda tx: _span_replace(tx, entity, representation, until=_SEP))
    replaced: _SpanRow = (300, "r", None, [])
    assert _span_rows(profile_run, entity) == [
        *_SEED_HISTORY,
        (_TA, None, _JAN, _MAR, 100, "a", _S1, _M),
        (_TA, None, _MAR, _APR, *replaced),
        (_TA, None, _APR, _JUN, *replaced),
        (_TA, None, _JUN, _AUG, *replaced),
        (_TA, None, _AUG, _SEP, *replaced),
    ]


# --------------------------------------------------------------------------- #
# Unchanged milestones: the caller's milestone is authority, not new history.  #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_STRATEGIES
def test_an_equal_patch_keeps_the_rectangle_it_leaves_and_rewrites_the_later_one(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded_spans(profile_run, entity, _TA, _TB)
    db.transact(lambda tx: _span_patch(tx, entity, amount=100), concurrency=concurrency)
    # The start already holds 100 over everything the window reaches of it, so
    # it keeps its milestone; equality there suppresses nothing later.
    assert _span_rows(profile_run, entity) == [
        (_T0, None, _JAN, _APR, 100, "a", _S1, _M),
        (_T1, _TA, _JUN, _AUG, 200, "b", _S2, []),
        (_TA, None, _JUN, _AUG, 100, "b", _S2, []),
    ]
    # The caller's milestone still stands, so a later caller stating it succeeds.
    db.transact(lambda tx: _span_patch(tx, entity, until=_APR, amount=150))
    assert _span_rows(profile_run, entity)[:2] == [
        (_T0, _TB, _JAN, _APR, 100, "a", _S1, _M),
        (_T1, _TA, _JUN, _AUG, 200, "b", _S2, []),
    ]


def _equal_replacement(
    tx: Transaction, entity: type[Any], representation: _Representation, **bounds: Any
) -> None:
    if representation == "typed":
        tx.replace_if(
            entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=(Mark(code="m"),)),
            **bounds,
        )
    else:
        tx.wire.replace_if(
            _name(entity),
            {"id": 1, "amount": 100, "label": "a", "spec": _S1, "marks": _M},
            **bounds,
        )


@_SPAN_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_replacement_stating_what_its_rectangle_holds_keeps_it(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    db.transact(
        lambda tx: _equal_replacement(
            tx, entity, representation, valid_from=_FEB, until=_APR, tx_start=_T0
        ),
        concurrency=concurrency,
    )
    assert _span_rows(profile_run, entity) == _SEED_CURRENT


@_SPAN_AXES
@_REPRESENTATIONS
def test_an_equal_replacement_of_a_stale_milestone_still_fails_its_precondition(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    with pytest.raises(ExecutionFailure) as failed:
        db.transact(
            lambda tx: _equal_replacement(
                tx, entity, representation, valid_from=_FEB, until=_APR, tx_start=_T1
            ),
            retry_optimistic_conflicts=True,
        )
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _span_rows(profile_run, entity) == _SEED_CURRENT


@pytest.mark.parametrize(
    ("label", "kept"), [("a", True), ("z", False)], ids=["unchanged", "changed"]
)
def test_an_unchanged_replacement_keeps_stored_content_no_member_declares(
    profile_run: Any, label: str, kept: bool
) -> None:
    db = _seeded_spans(profile_run, DocumentSpan, _TA)
    control = profile_run.control()
    try:
        control.execute_write(
            "update ttw_document_span set payload = jsonb_set(payload, '{spec,ledger}', '7') "
            "where from_z = %s",
            [_JAN],
        )
    finally:
        control.close()
    db.transact(
        lambda tx: tx.wire.replace_if(
            _name(DocumentSpan),
            {"id": 1, "amount": 100, "label": label, "spec": _S1, "marks": _M},
            valid_from=_FEB,
            until=_APR,
            tx_start=_T0,
        )
    )
    specs = profile_run.port.execute(
        "select in_z, from_z, payload->'spec' from ttw_document_span "
        "where out_z = 'infinity' and from_z < %s order by from_z",
        [_JUN],
    )
    if kept:
        # Every declared value is the one stored, so the milestone stays whole,
        # its undeclared ledger included.
        assert [tuple(row) for row in specs] == [(_T0, _JAN, {"title": "s1", "ledger": 7})]
    else:
        # A changed rectangle executes every stated member: its carried head
        # keeps the stored occurrence, the replaced piece states its own.
        assert [tuple(row) for row in specs] == [
            (_TA, _JAN, {"title": "s1", "ledger": 7}),
            (_TA, _FEB, {"title": "s1"}),
        ]


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize(
    "stated",
    [
        pytest.param({"valid_from": _MAY}, id="a-start-in-a-gap"),
        pytest.param({"valid_from": _SEP}, id="a-start-after-termination"),
        pytest.param({"tx_start": _T1}, id="another-milestone"),
    ],
)
def test_a_target_whose_start_does_not_stand_at_its_callers_milestone_changes_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, stated: dict[str, Any]
) -> None:
    db = _seeded_spans(profile_run, entity, _TA, _TB)
    attempts = 0

    def stale(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        _span_replace(tx, entity, "wire", **stated)

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(stale, concurrency=concurrency, retry_optimistic_conflicts=True)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert failed.value.cause.expected == stated.get("tx_start", _T0)
    assert attempts == 1
    assert _span_rows(profile_run, entity) == _SEED_CURRENT


@_LOG_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_transaction_time_target_chains_one_milestone_from_its_callers(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _T1, _TA, _TB)
    db.transact(lambda tx: tx.insert(entity(id=1, label="seed", spec=Spec(title="s1"))))
    db.transact(
        lambda tx: tx.wire.amend_if(_name(entity), {"id": 1, "label": "patched"}, tx_start=_T0),
        concurrency=concurrency,
    )
    assert _log_rows(profile_run, entity) == [
        (_T0, _T1, "seed", _S1, []),
        (_T1, None, "patched", _S1, []),
    ]

    def replace(tx: Transaction) -> None:
        if representation == "typed":
            tx.replace_if(entity(id=1, label="replaced", marks=(Mark(code="r"),)), tx_start=_T1)
        else:
            tx.wire.replace_if(
                _name(entity),
                {"id": 1, "label": "replaced", "marks": [{"code": "r"}]},
                tx_start=_T1,
            )

    db.transact(replace, concurrency=concurrency)
    assert _log_rows(profile_run, entity) == [
        (_T0, _T1, "seed", _S1, []),
        (_T1, _TA, "patched", _S1, []),
        (_TA, None, "replaced", None, [{"code": "r"}]),
    ]
    with pytest.raises(ExecutionFailure) as failed:
        db.transact(
            lambda tx: tx.wire.amend_if(_name(entity), {"id": 1, "label": "x"}, tx_start=_T1),
            concurrency=concurrency,
        )
    assert isinstance(failed.value.cause, WritePreconditionError)


# --------------------------------------------------------------------------- #
# Exact composition with observed writes of the starting rectangle.            #
# --------------------------------------------------------------------------- #
def _single(profile_run: Any, entity: type[Any], *instants: dt.datetime) -> ScopedDatabase:
    """Span 1 as one rectangle [January, infinity) opened at T0."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, *instants)
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=(Mark(code="m"),)),
            valid_from=_JAN,
        )
    )
    return db


_SEQUENCES: dict[str, _SpanRow | None] = {
    # P assigns the amount, then two observed edits overwrite it — the second
    # restating the first's amount beside its own label.
    "P-O-O": (175, "o", _S1, _M),
    # The replacement's empties survive the observed amount and the patch label.
    "R-O-P": (175, "p", None, []),
    "O-R-D": None,
    "P-D": None,
}


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("sequence", list(_SEQUENCES), ids=list(_SEQUENCES))
def test_target_and_observed_writes_of_one_window_compose_into_one_range(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, sequence: str
) -> None:
    db = _single(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        source = _span_find(tx, entity, _MAR)
        for step in sequence.split("-"):
            if step == "P":
                if sequence == "P-O-O":
                    _span_patch(tx, entity, until=_SEP, amount=150)
                else:
                    _span_patch(tx, entity, until=_SEP, label="p")
            elif step == "R":
                _span_replace(tx, entity, "wire", until=_SEP)
            elif step == "D":
                tx.terminate(source, until=_SEP)
            else:
                source = source.edit(
                    **({"amount": 175} if source.amount != 175 else {"label": "o"})
                )
                tx.amend(source, until=_SEP)
        # A dependent read flushes the range, which spends the observed source.
        _span_find(tx, entity, _JAN)
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.amend(source.edit(label="again"), until=_SEP)

    db.transact(fn, concurrency=concurrency)
    middle = _SEQUENCES[sequence]
    seed: _SpanRow = (100, "a", _S1, _M)
    expected: list[_SpanRow] = [
        (_T0, _TA, _JAN, None, *seed),
        (_TA, None, _JAN, _MAR, *seed),
        *([] if middle is None else [(_TA, None, _MAR, _SEP, *middle)]),
        (_TA, None, _SEP, None, *seed),
    ]
    assert _span_rows(profile_run, entity) == expected


@_SPAN_AXES
def test_a_stale_observed_source_composed_with_a_replacement_fails_as_its_precondition(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _single(profile_run, entity, _T1, _TA)
    stale = db.find(entity.where(entity.id == 1).as_of(valid_time=_MAR)).result()
    db.transact(lambda tx: tx.amend(_span_find(tx, entity, _FEB).edit(label="peer"), until=_APR))
    before = _span_rows(profile_run, entity)

    def fn(tx: Transaction) -> None:
        tx.amend(stale.edit(amount=1), until=_SEP)
        _span_replace(tx, entity, "wire", until=_SEP)

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _span_rows(profile_run, entity) == before


# --------------------------------------------------------------------------- #
# Dependent reads in both directions, the attempt's own flushes, insertions.   #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_STRATEGIES
def test_a_target_then_a_read_then_an_observed_write_each_stand_on_their_own(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _single(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        before = _span_find(tx, entity, _JUN)
        _span_patch(tx, entity, amount=150)
        fresh = _span_find(tx, entity, _JUN)
        assert fresh.amount == 150
        # The read taken before the target's flush describes a state that flush
        # replaced; the fresh one writes, and keeps the patched amount.
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.amend(before.edit(label="stale"))
        tx.amend(fresh.edit(label="fresh"))

    db.transact(fn, concurrency=concurrency)
    seed = (100, "a", _S1, _M)
    assert _span_rows(profile_run, entity) == [
        (_T0, _TA, _JAN, None, *seed),
        (_TA, None, _JAN, _MAR, *seed),
        (_TA, None, _MAR, _JUN, 150, "a", _S1, _M),
        (_TA, None, _JUN, None, 150, "fresh", _S1, _M),
    ]


@_SPAN_AXES
@_STRATEGIES
def test_a_target_after_this_attempts_own_flush_states_the_milestone_it_left(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _single(profile_run, entity, _TA, _TB)

    def fn(tx: Transaction) -> None:
        tx.amend(_span_find(tx, entity, _MAR).edit(amount=150))
        rewritten = _span_find(tx, entity, _APR)
        assert rewritten.amount == 150
        _span_patch(tx, entity, valid_from=_APR, tx_start=_TA, amount=175)

    db.transact(fn, concurrency=concurrency)
    seed = (100, "a", _S1, _M)
    # The rows the attempt opened are revised in place: one instant, and no
    # history of the attempt's own.
    assert _span_rows(profile_run, entity) == [
        (_T0, _TA, _JAN, None, *seed),
        (_TA, None, _JAN, _MAR, *seed),
        (_TA, None, _MAR, _APR, 150, "a", _S1, _M),
        (_TA, None, _APR, None, 175, "a", _S1, _M),
    ]

    def outdated(tx: Transaction) -> None:
        tx.amend(_span_find(tx, entity, _MAR).edit(amount=1))
        _span_find(tx, entity, _JAN)
        _span_patch(tx, entity, valid_from=_APR, tx_start=_TA, amount=2)

    before = _span_rows(profile_run, entity)
    with pytest.raises(ExecutionFailure) as failed:
        db.transact(outdated, concurrency=concurrency)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _span_rows(profile_run, entity) == before


@pytest.mark.parametrize(
    "entity", (*_SPANS, *_LOGS), ids=["bt-columns", "bt-document", "tt-columns", "tt-document"]
)
@_STRATEGIES
@_REPRESENTATIONS
def test_a_temporal_target_of_an_object_this_attempt_inserted_is_refused_until_commit(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _TA, _TB)
    bitemporal = entity in _SPANS
    bounds: dict[str, Any] = {"valid_from": _JAN} if bitemporal else {}
    seed = {"amount": 100} if bitemporal else {"label": "seed"}

    def target(tx: Transaction, **changes: object) -> None:
        if representation == "typed" and changes:
            tx.replace_if(entity(id=1, **{**seed, **changes}), tx_start=_TA, **bounds)
        else:
            tx.wire.amend_if(_name(entity), {"id": 1, **changes}, tx_start=_TA, **bounds)

    member = "amount" if bitemporal else "label"
    changed: object = 150 if bitemporal else "target"

    def fn(tx: Transaction) -> None:
        inserted = tx.wire.insert(_name(entity), {"id": 1, **seed}, **bounds)
        for flushed in (False, True):
            if flushed:
                # A read of the row itself flushes the insertion.
                tx.find(
                    entity.where(entity.id == 1).as_of(valid_time=_JAN)
                    if bitemporal
                    else entity.where(entity.id == 1)
                ).result()
            with pytest.raises(WriteEvidenceError, match="write-evidence-inserted"):
                target(tx, **{member: changed})
            target(tx)
        tx.wire.amend(inserted, {member: 175 if bitemporal else "authored"})

    db.transact(fn, concurrency=concurrency)
    db.transact(lambda tx: target(tx, **{member: changed}), concurrency=concurrency)
    rows = _span_rows(profile_run, entity) if bitemporal else _log_rows(profile_run, entity)
    assert [row[1] for row in rows] == [_TB, None]
    assert rows[-1][4 if bitemporal else 2] == changed


# --------------------------------------------------------------------------- #
# Two sessions: losses after the flush read, and the Locking acquisition.      #
# --------------------------------------------------------------------------- #
def _two_rectangles(profile_run: Any, entity: type[Any]) -> None:
    """Span 1 as [January, June) opened at T0 and [June, infinity) at T1."""
    profile_run.reset(model_of(_MODEL), {})
    seeder = _db(profile_run, _T0, _T1)
    seeder.transact(
        lambda tx: tx.insert(entity(id=1, amount=100, label="a"), valid_from=_JAN, until=_JUN)
    )
    seeder.transact(lambda tx: tx.insert(entity(id=1, amount=200, label="b"), valid_from=_JUN))


def _peer_split(label: str) -> list[tuple[object, ...]]:
    return [
        (_T0, _TP, _JAN, _JUN, 100, "a"),
        (_T1, None, _JUN, None, 200, "b"),
        (_TP, None, _JAN, _FEB, 100, "a"),
        (_TP, None, _FEB, _APR, 100, label),
        (_TP, None, _APR, _JUN, 100, "a"),
    ]


_PEER_ROWS: dict[str, list[tuple[object, ...]]] = {
    "start": _peer_split("peer"),
    "start-by-overlapping-replacement": [
        (_T0, _TP, _JAN, _JUN, 100, "a"),
        (_T1, _TP, _JUN, None, 200, "b"),
        (_TP, None, _JAN, _APR, 100, "a"),
        (_TP, None, _APR, _JUN, 900, "peer"),
        (_TP, None, _JUN, None, 900, "peer"),
    ],
}


@_SPAN_AXES
@pytest.mark.parametrize("lost", ["start", "start-by-overlapping-replacement", "later"])
def test_a_row_another_session_revises_after_the_flush_read_it_fails_by_whose_it_was(
    profile_run: Any, entity: type[Any], lost: str
) -> None:
    _two_rectangles(profile_run, entity)
    peer_db = _db(profile_run, _TP)

    def peer() -> None:
        if lost == "start-by-overlapping-replacement":
            # Another caller's replacement shares the coverage from April on.
            peer_db.transact(
                lambda tx: tx.wire.replace_if(
                    _name(entity),
                    {"id": 1, "amount": 900, "label": "peer"},
                    valid_from=_APR,
                    tx_start=_T0,
                )
            )
            return
        at, until = (_JUL, _SEP) if lost == "later" else (_FEB, _APR)
        peer_db.transact(
            lambda tx: tx.amend(_span_find(tx, entity, at).edit(label="peer"), until=until)
        )

    interleaving = AfterCoverageRead(_TABLES[entity], peer)
    ours = own_root(
        connect(
            profile_run.port,
            _MODEL,
            clock=ScriptedClock([_TA, _TB]),
            lifecycle_provider=interleaving,
        )
    ).using_database_login()
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        _span_patch(tx, entity, amount=150)

    if lost != "later":
        peer_rows = _PEER_ROWS[lost]
        with pytest.raises(ExecutionFailure) as failed:
            ours.transact(fn, retry_optimistic_conflicts=True)
        assert isinstance(failed.value.cause, WritePreconditionError)
        assert (attempts, interleaving.failures) == (1, [])
        # Only the peer's change stands: the attempt's effects rolled back.
        assert [row[:6] for row in _span_rows(profile_run, entity)] == peer_rows
        return
    ours.transact(fn, retry_optimistic_conflicts=True)
    assert (attempts, interleaving.failures) == (2, [])
    # The retry stated the same milestone for the untouched start and binds
    # the peer's later rows, each keeping its own label.
    assert [row[:6] for row in _span_rows(profile_run, entity)] == [
        (_T0, _TB, _JAN, _JUN, 100, "a"),
        (_T1, _TP, _JUN, None, 200, "b"),
        (_TP, _TB, _JUN, _JUL, 200, "b"),
        (_TP, _TB, _JUL, _SEP, 200, "peer"),
        (_TP, _TB, _SEP, None, 200, "b"),
        (_TB, None, _JAN, _MAR, 100, "a"),
        (_TB, None, _MAR, _JUN, 150, "a"),
        (_TB, None, _JUN, _JUL, 150, "b"),
        (_TB, None, _JUL, _SEP, 150, "peer"),
        (_TB, None, _SEP, None, 150, "b"),
    ]


@_SPAN_AXES
def test_a_peers_equal_patch_of_the_start_leaves_the_stated_milestone_standing(
    profile_run: Any, entity: type[Any]
) -> None:
    _two_rectangles(profile_run, entity)
    peer_db = _db(profile_run, _TP)

    def peer() -> None:
        # The peer's patch assigns the label the start already holds, so its
        # guard keeps that milestone, and its Transaction-Time start with it.
        peer_db.transact(
            lambda tx: tx.wire.amend_if(
                _name(entity),
                {"id": 1, "label": "a"},
                valid_from=_FEB,
                until=_APR,
                tx_start=_T0,
            )
        )

    interleaving = AfterCoverageRead(_TABLES[entity], peer)
    ours = own_root(
        connect(
            profile_run.port, _MODEL, clock=ScriptedClock([_TA]), lifecycle_provider=interleaving
        )
    ).using_database_login()
    ours.transact(lambda tx: _span_patch(tx, entity, amount=150))
    assert interleaving.failures == []
    assert [row[:6] for row in _span_rows(profile_run, entity)] == [
        (_T0, _TA, _JAN, _JUN, 100, "a"),
        (_T1, _TA, _JUN, None, 200, "b"),
        (_TA, None, _JAN, _MAR, 100, "a"),
        (_TA, None, _MAR, _JUN, 150, "a"),
        (_TA, None, _JUN, None, 150, "b"),
    ]


@_SPAN_AXES
def test_a_later_row_lost_after_the_flush_read_rolls_back_without_retries(
    profile_run: Any, entity: type[Any]
) -> None:
    _two_rectangles(profile_run, entity)
    peer_db = _db(profile_run, _TP)

    def peer() -> None:
        peer_db.transact(
            lambda tx: tx.amend(_span_find(tx, entity, _JUL).edit(label="peer"), until=_SEP)
        )

    interleaving = AfterCoverageRead(_TABLES[entity], peer)
    ours = own_root(
        connect(
            profile_run.port, _MODEL, clock=ScriptedClock([_TA]), lifecycle_provider=interleaving
        )
    ).using_database_login()
    with pytest.raises(ExecutionFailure) as failed:
        ours.transact(lambda tx: _span_patch(tx, entity, amount=150))
    assert isinstance(failed.value.cause, OptimisticLockConflictError)
    assert [row[:2] for row in _span_rows(profile_run, entity)][:2] == [(_T0, None), (_T1, _TP)]


@_SPAN_AXES
def test_a_locking_target_holds_its_start_until_commit_against_another_session(
    profile_run: Any, entity: type[Any]
) -> None:
    _two_rectangles(profile_run, entity)
    peer_db = _db(profile_run, _TP)
    control = profile_run.control()
    peer_failures: list[BaseException] = []

    def peer() -> None:
        try:
            peer_db.transact(
                lambda tx: tx.amend(_span_find(tx, entity, _FEB).edit(label="peer"), until=_APR)
            )
        except BaseException as failure:
            peer_failures.append(failure)

    def waiting() -> bool:
        ((count,),) = control.execute("select count(*) from pg_locks where not granted", [])
        return bool(count)

    ours = _db(profile_run, _TA)
    thread = threading.Thread(target=peer)

    def fn(tx: Transaction) -> None:
        _span_patch(tx, entity, amount=150)
        thread.start()
        deadline = time.monotonic() + 10.0
        while not waiting():
            assert time.monotonic() < deadline, "the peer never waited on the shared lock"
            time.sleep(0.05)

    try:
        ours.transact(fn, concurrency="locking")
        thread.join(timeout=10.0)
    finally:
        control.close()
    # The peer's close waited for the commit, then found its milestone gone.
    (failure,) = peer_failures
    assert isinstance(failure, ExecutionFailure)
    assert isinstance(failure.cause, OptimisticLockConflictError)
    assert [row[:6] for row in _span_rows(profile_run, entity)] == [
        (_T0, _TA, _JAN, _JUN, 100, "a"),
        (_T1, _TA, _JUN, None, 200, "b"),
        (_TA, None, _JAN, _MAR, 100, "a"),
        (_TA, None, _MAR, _JUN, 150, "a"),
        (_TA, None, _JUN, None, 150, "b"),
    ]


# --------------------------------------------------------------------------- #
# A source-authorized replacement establishes the same window a caller's does: #
# its source supplies the authority and the start, and the complete state it  #
# states fills every gap its window reaches.                                  #
# --------------------------------------------------------------------------- #
def _source_replace(tx: Transaction, entity: type[Any], representation: _Representation) -> None:
    if representation == "typed":
        found = _span_find(tx, entity, _MAR)
        tx.replace(found.edit(amount=300, label="r"), until=_SEP)
        return
    node = tx.wire.find(_wire_span_query(entity, _MAR)).result()
    data = tx.wire.editable_data(node)
    data["amount"] = 300
    data["label"] = "r"
    tx.wire.replace(node, data, until=_SEP)


def _instant(at: dt.datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _wire_span_query(entity: type[Any], at: dt.datetime) -> dict[str, object]:
    return {
        "target": _name(entity),
        "predicate": {"eq": {"attr": f"{_name(entity)}.id", "value": 1}},
        "temporal": {
            "transaction-time": {"asOf": "latest"},
            "valid-time": {"asOf": _instant(at)},
        },
    }


@_SPAN_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_source_replacement_establishes_its_window_across_gaps(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)
    db.transact(lambda tx: _source_replace(tx, entity, representation), concurrency=concurrency)
    replaced: _SpanRow = (300, "r", _S1, _M)
    assert _span_rows(profile_run, entity) == [
        *_SEED_HISTORY,
        (_TA, None, _JAN, _MAR, 100, "a", _S1, _M),
        (_TA, None, _MAR, _APR, *replaced),
        (_TA, None, _APR, _JUN, *replaced),
        (_TA, None, _JUN, _AUG, *replaced),
        (_TA, None, _AUG, _SEP, *replaced),
    ]


@_SPAN_AXES
@_REPRESENTATIONS
def test_a_source_amendment_of_the_same_window_leaves_its_gaps(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seeded_spans(profile_run, entity, _TA)

    def amend(tx: Transaction) -> None:
        if representation == "typed":
            tx.amend(_span_find(tx, entity, _MAR).edit(amount=300), until=_SEP)
        else:
            node = tx.wire.find(_wire_span_query(entity, _MAR)).result()
            tx.wire.amend(node, {"amount": 300}, until=_SEP)

    db.transact(amend)
    assert _span_rows(profile_run, entity) == [
        *_SEED_HISTORY,
        (_TA, None, _JAN, _MAR, 100, "a", _S1, _M),
        (_TA, None, _MAR, _APR, 300, "a", _S1, _M),
        (_TA, None, _JUN, _AUG, 300, "b", _S2, []),
    ]


@_SPAN_AXES
def test_a_source_replacement_whose_evidence_fails_opens_nothing(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded_spans(profile_run, entity, _TP, _TA)
    found = db.find(entity.where(entity.id == 1).as_of(valid_time=_MAR)).result()
    db.transact(lambda peer: peer.amend(_span_find(peer, entity, _MAR).edit(label="p")))
    with pytest.raises(ExecutionFailure) as failed:
        db.transact(lambda tx: tx.replace(found.edit(amount=300), until=_SEP))
    assert isinstance(failed.value.cause, OptimisticLockConflictError)
    rows = _span_rows(profile_run, entity)
    assert all(row[4] != 300 for row in rows)
    assert not any(row[2] == _APR for row in rows)


# --------------------------------------------------------------------------- #
# A replacement an insertion authorizes establishes the same state whether the #
# insertion is still pending or has already executed.                          #
# --------------------------------------------------------------------------- #
def _seeded_later(profile_run: Any, entity: type[Any], *instants: dt.datetime) -> ScopedDatabase:
    """Span 1 stored over [May, July) only."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, *instants)
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=200, label="b", spec=Spec(title="s2"), marks=()),
            valid_from=_MAY,
            until=_JUL,
        )
    )
    return db


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "flushed"])
def test_an_insertion_replacement_reaches_later_coverage_whether_or_not_it_flushed(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, flushed: bool
) -> None:
    db = _seeded_later(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        opened = entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=())
        tx.insert(opened, valid_from=_JAN, until=_APR)
        if flushed:
            _span_find(tx, entity, _FEB)
        tx.replace(opened.edit(amount=300, label="r"), until=_JUN)

    db.transact(fn, concurrency=concurrency)
    replaced: _SpanRow = (300, "r", _S1, [])
    assert _span_rows(profile_run, entity) == [
        (_T0, _TA, _MAY, _JUL, 200, "b", _S2, []),
        (_TA, None, _JAN, _APR, *replaced),
        (_TA, None, _APR, _MAY, *replaced),
        (_TA, None, _MAY, _JUN, *replaced),
        (_TA, None, _JUN, _JUL, 200, "b", _S2, []),
    ]


@_SPAN_AXES
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "flushed"])
def test_a_terminated_insertion_replacement_removes_what_it_reached_whether_or_not_it_flushed(
    profile_run: Any, entity: type[Any], flushed: bool
) -> None:
    db = _seeded_later(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        opened = entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=())
        tx.insert(opened, valid_from=_JAN, until=_APR)
        if flushed:
            _span_find(tx, entity, _FEB)
        tx.replace(opened.edit(amount=300, label="r"), until=_JUN)
        tx.terminate(opened, until=_JUN)

    db.transact(fn)
    assert _span_rows(profile_run, entity) == [
        (_T0, _TA, _MAY, _JUL, 200, "b", _S2, []),
        (_TA, None, _JUN, _JUL, 200, "b", _S2, []),
    ]


@_SPAN_AXES
@pytest.mark.parametrize("flushed", [False, True], ids=["pending", "flushed"])
def test_a_reinsertion_follows_the_removal_of_all_an_insertion_replacement_reached(
    profile_run: Any, entity: type[Any], flushed: bool
) -> None:
    db = _seeded_later(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        first = entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=())
        tx.insert(first, valid_from=_JAN, until=_APR)
        if flushed:
            _span_find(tx, entity, _FEB)
        tx.replace(first.edit(amount=300, label="r"), until=_JUN)
        tx.terminate(first, until=_JUN)
        tx.insert(
            entity(id=1, amount=400, label="c", spec=Spec(title="s1"), marks=()),
            valid_from=_JAN,
            until=_JUN,
        )
        with pytest.raises(KeyedWriteValueError, match="write-value-not-stored"):
            tx.replace(first.edit(amount=500), until=_JUN)

    db.transact(fn)
    assert _span_rows(profile_run, entity) == [
        (_T0, _TA, _MAY, _JUL, 200, "b", _S2, []),
        (_TA, None, _JAN, _JUN, 400, "c", _S1, []),
        (_TA, None, _JUN, _JUL, 200, "b", _S2, []),
    ]


@_SPAN_AXES
def test_an_ended_insertion_authorizes_no_replacement(profile_run: Any, entity: type[Any]) -> None:
    db = _seeded_later(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        opened = entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=())
        tx.insert(opened, valid_from=_JAN, until=_APR)
        tx.terminate(opened, until=_APR)
        with pytest.raises(KeyedWriteValueError, match="write-value-not-stored"):
            tx.replace(opened.edit(amount=300), until=_JUN)

    db.transact(fn)
    assert _span_rows(profile_run, entity) == [(_T0, None, _MAY, _JUL, 200, "b", _S2, [])]


@_SPAN_AXES
def test_a_rolled_back_insertion_replacement_leaves_nothing(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded_later(profile_run, entity, _TA)

    class _Abandoned(Exception):
        pass

    def fn(tx: Transaction) -> None:
        opened = entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=())
        tx.insert(opened, valid_from=_JAN, until=_APR)
        tx.replace(opened.edit(amount=300), until=_JUN)
        _span_find(tx, entity, _MAY)
        raise _Abandoned

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn)
    assert isinstance(failed.value.cause, _Abandoned)
    assert _span_rows(profile_run, entity) == [(_T0, None, _MAY, _JUL, 200, "b", _S2, [])]


# --------------------------------------------------------------------------- #
# A historical observation can state a conditional replacement under a current #
# condition and new bounds, without being copied first.                        #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_REPRESENTATIONS
def test_a_historical_observation_restores_its_state_under_a_current_condition(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seeded_spans(profile_run, entity, _TA, _TB)
    db.transact(lambda tx: tx.amend(_span_find(tx, entity, _FEB).edit(amount=150, label="c")))

    def restore(tx: Transaction) -> None:
        if representation == "typed":
            historical = tx.find(
                entity.where(entity.id == 1).as_of(valid_time=_FEB, tx_time=_T1)
            ).result()
            tx.replace_if(historical, tx_start=_TA, valid_from=_FEB, until=_APR)
            return
        query = _wire_span_query(entity, _FEB)
        temporal = cast("dict[str, object]", query["temporal"])
        temporal["transaction-time"] = {"asOf": _instant(_T1)}
        historical_node = tx.wire.find(query).result()
        tx.wire.replace_if(historical_node, tx_start=_TA, valid_from=_FEB, until=_APR)

    db.transact(restore)
    current = [row for row in _span_rows(profile_run, entity) if row[1] is None]
    assert current == [
        (_TA, None, _JAN, _FEB, 100, "a", _S1, _M),
        (_TA, None, _JUN, _AUG, 150, "c", _S2, []),
        (_TB, None, _FEB, _APR, 100, "a", _S1, _M),
    ]


@_LOG_AXES
@_REPRESENTATIONS
def test_a_transaction_time_source_replacement_chains_its_complete_state(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _TA)
    db.transact(lambda tx: tx.insert(entity(id=1, label="a", spec=Spec(title="s1"), marks=())))

    def replace(tx: Transaction) -> None:
        if representation == "typed":
            found = tx.find(entity.where(entity.id == 1)).result()
            tx.replace(found.edit(label="r"))
            return
        node = tx.wire.find(
            {
                "target": _name(entity),
                "predicate": {"eq": {"attr": f"{_name(entity)}.id", "value": 1}},
                "temporal": {"transaction-time": {"asOf": "latest"}},
            }
        ).result()
        tx.wire.replace(node, {"label": "r", "marks": [{"code": "m"}]})

    db.transact(replace)
    spec = _S1 if representation == "typed" else None
    marks = [] if representation == "typed" else _M
    assert _log_rows(profile_run, entity) == [
        (_T0, _TA, "a", _S1, []),
        (_TA, None, "r", spec, marks),
    ]
