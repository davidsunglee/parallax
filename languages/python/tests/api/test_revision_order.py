"""An in-place revision runs after the closes and removals it absorbs, against
real Postgres.

Two target amendments of one object over adjacent windows merge into one row,
and the row the attempt opened at the later window is revised in place to start
at the earlier one (`m-temporal-write` *Merging produced successors*). The
earlier window's row — stored, or one the attempt opened — is closed or removed,
and that statement runs first whichever condition the caller stated first, so no
statement leaves two current rows of the object overlapping
(`m-temporal-write` *Predecessor Expansion*).

Each table carries the generated exclusion, which checks every statement as it
runs (`m-storage-layout` *Temporal history constraints*), so a transient overlap
would refuse the flush; each proof also reads the flush's statement order from
the execution lifecycle beside the stored history that results.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final, Literal

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, attr
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import DatabaseCallStarted, FlushStarted
from parallax.snapshot import ScopedDatabase, TxnContext, connect, edge_of
from tests._support.root_ownership import own_root

_NAMESPACE: Final = "revision.order"


class ColumnsSpan(Bitemporal, table="ro_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class DocumentSpan(Bitemporal, table="ro_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


_MODEL: Final = DomainModel(ColumnsSpan, DocumentSpan)
_TABLES: Final[dict[type[Any], str]] = {
    ColumnsSpan: "ro_columns_span",
    DocumentSpan: "ro_document_span",
}

_T0, _T1, _TA = (
    dt.datetime(2023, 12, 1, tzinfo=dt.UTC),
    dt.datetime(2023, 12, 15, tzinfo=dt.UTC),
    dt.datetime(2024, 1, 10, tzinfo=dt.UTC),
)
_JAN, _APR = dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 4, 1, tzinfo=dt.UTC)

type _Neighbour = Literal["stored", "owned"]
type _Stated = Literal["owned-first", "neighbour-first"]
type _Effect = Literal["close", "remove", "revise", "insert"]

_FINAL_HISTORY: Final = [
    (_JAN, None, _T0, _T1, 100),
    (_JAN, _APR, _T1, _TA, 100),
    (_APR, None, _T1, _TA, 200),
    (_JAN, None, _TA, None, 175),
]
"""What every arrangement stores: the seeded history closed at the attempt's
instant, and the one row the attempt revised to cover all of it."""


def _member(entity: type[Any]) -> str:
    return "payload->>'amount'" if entity is DocumentSpan else "amount"


def _history(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select from_z, case when thru_z = 'infinity' then null else thru_z end, in_z, "
        "case when out_z = 'infinity' then null else out_z end, "
        f"({_member(entity)})::int from {_TABLES[entity]} where id = 1 order by in_z, from_z"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _seeded(
    profile_run: Any, entity: type[Any], provider: RecordingLifecycleProvider
) -> ScopedDatabase:
    """Object 1 stored as ``[January, April)`` at 100 and ``[April, ∞)`` at 200,
    both current since T1; the edit's attempt runs at TA."""
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(
        connect(
            profile_run.port,
            _MODEL,
            clock=ScriptedClock([_T0, _T1, _TA]),
            lifecycle_provider=provider,
        )
    ).using_database_login()
    db.transact(lambda tx: tx.insert(entity(id=1, amount=100), valid_from=_JAN))
    db.transact(
        lambda tx: tx.amend_if(entity, entity.amount.set(200), key=1, tx_start=_T0, valid_from=_APR)
    )
    return db


def _edit(entity: type[Any], neighbour: _Neighbour, stated: _Stated) -> Any:
    """Open the attempt's own April row — and, for an owned neighbour, its own
    January row — in one flush, then amend both windows to 175 in another,
    stating the conditions in ``stated`` order."""

    def edit(tx: TxnContext) -> None:
        tx.amend_if(entity, entity.amount.set(150), key=1, tx_start=_T1, valid_from=_APR)
        if neighbour == "owned":
            tx.amend_if(
                entity, entity.amount.set(120), key=1, tx_start=_T1, valid_from=_JAN, until=_APR
            )
        owned = tx.find(entity.where(entity.id == 1).as_of(valid_time=_APR)).result()
        assert edge_of(owned).tx_time == _TA

        def amend_owned() -> None:
            tx.amend_if(entity, entity.amount.set(175), key=1, tx_start=_TA, valid_from=_APR)

        def amend_neighbour() -> None:
            tx.amend_if(
                entity,
                entity.amount.set(175),
                key=1,
                tx_start=_T1 if neighbour == "stored" else _TA,
                valid_from=_JAN,
                until=_APR,
            )

        first, second = (
            (amend_owned, amend_neighbour)
            if stated == "owned-first"
            else (amend_neighbour, amend_owned)
        )
        first()
        second()

    return edit


def _last_flush(provider: RecordingLifecycleProvider) -> list[str]:
    """The SQL of every write the last root's last flush presented, in order."""
    events = provider.roots[-1].events
    start = max(index for index, event in enumerate(events) if isinstance(event, FlushStarted))
    return [
        event.statement.sql
        for event in events[start:]
        if isinstance(event, DatabaseCallStarted) and event.kind == "write"
    ]


def _effect(sql: str) -> _Effect:
    if sql.startswith("delete "):
        return "remove"
    if sql.startswith("insert "):
        return "insert"
    return "close" if _assigned(sql) == ["out_z"] else "revise"


def _assigned(sql: str) -> list[str]:
    """The columns an update's ``set`` clause names, in order; a comma inside
    an assigned expression separates nothing."""
    clause = sql.split(" set ", 1)[1].split(" where ", 1)[0]
    columns: list[str] = []
    depth, start = 0, 0
    for index, character in enumerate(f"{clause},"):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            columns.append(clause[start:index].split(" = ", 1)[0].strip())
            start = index + 1
    return columns


@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"])
@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
@pytest.mark.parametrize("neighbour", ["stored", "owned"])
@pytest.mark.parametrize("stated", ["owned-first", "neighbour-first"])
def test_a_revision_moving_its_start_earlier_runs_after_the_row_it_absorbs_ends(
    profile_run: Any,
    entity: type[Any],
    concurrency: Literal["optimistic", "locking"],
    neighbour: _Neighbour,
    stated: _Stated,
) -> None:
    provider = RecordingLifecycleProvider()
    db = _seeded(profile_run, entity, provider)

    db.transact(_edit(entity, neighbour, stated), concurrency=concurrency, max_retries=0)

    writes = _last_flush(provider)
    vacating: _Effect = "close" if neighbour == "stored" else "remove"
    assert [_effect(sql) for sql in writes] == [vacating, "revise"]
    assert {"in_z", "out_z", "thru_z"}.isdisjoint(_assigned(writes[1]))
    assert "from_z" in _assigned(writes[1])
    assert _history(profile_run, entity) == _FINAL_HISTORY
