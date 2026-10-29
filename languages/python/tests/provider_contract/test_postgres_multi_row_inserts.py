"""Multi-row inserts bound as column arrays on a real server (`m-sql` *Batched
insert / update*, `m-dialect` *Bind parameter limit*).

Each shape inserts, in one transaction, more rows than 65,535 parameters would
bind one by one: ``ceil(65_535 / W) + 1_000`` rows of a statement listing ``W``
Columns. The insert is one statement binding ``W`` arrays of that many
elements, and every row reads back exactly as the generator wrote it — every
scalar Neutral Type with nulls, Value Objects with nulls, scalar collections,
both layouts, and both inheritance strategies. A null Value Object is SQL NULL
in its own Column however many rows its insert holds, and a literal JSON-null
document stays JSON null. A ranged temporal
write opens every successor in one statement however many there are.

The column-array form keeps the failures a row would raise alone: a duplicate
key names its index, an over-long string or out-of-range number is refused by
assignment rather than cut by the array's cast, and an exclusion conflict is
recognized and retried.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import FixedClock, ScriptedClock
from parallax.core import (
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Float32,
    Int32,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
    index,
    storage_layout,
)
from parallax.core.base import INT64, JSON, Json
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import JSON_NULL, ArrayBind, JsonDocument
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import (
    AttemptCommitted,
    AttemptRolledBack,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    TransactionAttemptFinished,
)
from parallax.core.metamodel import Table, TablePerConcreteSubtype
from parallax.core.sql_gen import LoweredStatement
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root
from tests._support.temporal_write_transport import (
    AMENDED_AT,
    AMOUNT,
    HistoryRow,
    expected_history,
    ordered_history,
    seeded_history,
    window,
)

_NAMESPACE: Final = "multi.row.inserts"
_PARAMETERS: Final = 65_535


class Place(ValueObject):
    city: Attr[str] = attr()
    rank: Attr[int] = attr(type=Int32)


class Wide(Entity, table="mri_wide", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    flag: Attr[bool | None] = attr()
    small: Attr[int | None] = attr(type=Int32)
    count: Attr[int | None] = attr()
    ratio: Attr[float | None] = attr(type=Float32)
    score: Attr[float | None] = attr()
    amount: Attr[Decimal | None] = attr(precision=12, scale=2)
    name: Attr[str | None] = attr(max_length=16)
    blob: Attr[bytes | None] = attr()
    day: Attr[dt.date | None] = attr()
    moment: Attr[dt.time | None] = attr()
    instant: Attr[dt.datetime | None] = attr()
    key: Attr[uuid.UUID | None] = attr()
    place: Attr[Place | None] = attr()
    tags: Attr[tuple[str, ...]] = attr()
    counts: Attr[tuple[int, ...]] = attr()


class WideSheet(Entity, table="mri_wide_sheet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    flag: Attr[bool | None] = attr()
    small: Attr[int | None] = attr(type=Int32)
    count: Attr[int | None] = attr()
    ratio: Attr[float | None] = attr(type=Float32)
    score: Attr[float | None] = attr()
    amount: Attr[Decimal | None] = attr(precision=12, scale=2)
    name: Attr[str | None] = attr(max_length=16)
    blob: Attr[bytes | None] = attr()
    day: Attr[dt.date | None] = attr()
    moment: Attr[dt.time | None] = attr()
    instant: Attr[dt.datetime | None] = attr()
    key: Attr[uuid.UUID | None] = attr()
    place: Attr[Place | None] = attr()
    tags: Attr[tuple[str, ...]] = attr()
    counts: Attr[tuple[int, ...]] = attr()


def _family(name: str, *, hierarchy: bool, document: bool) -> tuple[Any, Any, Any]:
    """An abstract root keyed by ``id`` with a ``label``, and two concretes:
    ``Disc`` with a Float64 ``size`` and ``Plate`` with a decimal one, the one
    member name declared twice as siblings may (`m-storage-layout`), each in a
    Column of its own where the family shares one Table's Columns."""
    shared = hierarchy and not document
    namespace = f"{_NAMESPACE}.{name}"
    table = f"mri_{name}"
    options: dict[str, Any] = {"layout": Document()} if document else {}
    root: Any = type(
        "Figure",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[int], "label": Attr[str]},
            "id": attr(primary_key=True),
            "label": attr(max_length=16),
        },
        namespace=namespace,
        inheritance=AbstractRoot(
            TablePerHierarchy("kind") if hierarchy else TablePerConcreteSubtype()
        ),
        **({"table": table} if hierarchy else {}),
        **options,
    )
    concretes = [
        type(
            concrete,
            (root,),
            {"__module__": __name__, "__annotations__": {"size": Attr[size]}, "size": member},
            namespace=namespace,
            inheritance=ConcreteSubtype(tag_value=concrete.lower())
            if hierarchy
            else ConcreteSubtype(),
            **({} if hierarchy else {"table": f"{table}_{concrete.lower()}"}),
        )
        for concrete, size, member in (
            ("Disc", float, attr(column="disc_size" if shared else None)),
            (
                "Plate",
                Decimal,
                attr(precision=10, scale=3, column="plate_size" if shared else None),
            ),
        )
    ]
    return root, concretes[0], concretes[1]


_FAMILIES: Final = {
    "tph_columns": _family("tph_columns", hierarchy=True, document=False),
    "tph_document": _family("tph_document", hierarchy=True, document=True),
    "tpcs_columns": _family("tpcs_columns", hierarchy=False, document=False),
}


class Opened(Bitemporal, table="mri_opened", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=24)
    amount: Attr[int]


class Coded(
    Entity,
    table="mri_coded",
    namespace=_NAMESPACE,
    indices=(index("mri_coded_code", "code", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    code: Attr[str] = attr(max_length=16)
    level: Attr[int]


class Log(TxTemporal, table="mri_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(
    Wide,
    WideSheet,
    *(cls for family in _FAMILIES.values() for cls in family),
    Opened,
    Coded,
    Log,
)


def _rows_past_the_limit(width: int) -> int:
    return math.ceil(_PARAMETERS / width) + 1_000


def _null_every(row: int, offset: int, value: object) -> object:
    """``value``, or null on every seventh row, each member on rows of its own."""
    return None if (row + offset) % 7 == 0 else value


_EXTREMES: Final[Mapping[int, Mapping[str, object]]] = {
    1: {
        "small": -(2**31),
        "count": -(2**63),
        "ratio": 3.4028234663852886e38,
        "score": 1e300,
        "amount": Decimal("9999999999.99"),
        "name": "",
        "blob": b"",
    },
    2: {
        "small": 2**31 - 1,
        "count": 2**63 - 1,
        "ratio": 1.401298464324817e-45,
        "score": -1e-300,
        "amount": Decimal("-9999999999.99"),
        "name": '{,}"NULL"\\ü',
        "blob": b"\x00\xff",
    },
}


def _wide(row: int) -> dict[str, object]:
    """Row ``row``'s members: both what it inserts and what it reads back."""
    members: dict[str, object] = {
        "id": row,
        "flag": _null_every(row, 0, row % 2 == 0),
        "small": _null_every(row, 1, row * 3 - 50_000),
        "count": _null_every(row, 2, row * 1_000_003),
        "ratio": _null_every(row, 3, row * 0.5),
        "score": _null_every(row, 4, row / 3),
        "amount": _null_every(row, 5, Decimal(row).scaleb(-2)),
        "name": _null_every(row, 6, f"n{row}"),
        "blob": _null_every(row, 0, row.to_bytes(4, "big")),
        "day": _null_every(row, 1, dt.date(2000, 1, 1) + dt.timedelta(days=row)),
        "moment": _null_every(
            row, 2, dt.time(row % 24, row % 60, (row * 7) % 60, (row * 37) % 1_000_000)
        ),
        "instant": _null_every(
            row, 3, dt.datetime(2020, 1, 1, tzinfo=dt.UTC) + dt.timedelta(microseconds=row * 1_009)
        ),
        "key": _null_every(row, 4, uuid.UUID(int=row * 7_919 + 1)),
        "place": _null_every(row, 5, Place(city=f"c{row}", rank=row)),
        "tags": tuple(f"t{row % 3}" for _ in range(row % 4)),
        "counts": tuple(range(row % 3)),
    }
    members.update(_EXTREMES.get(row, {}))
    return members


def _database(profile_run: Any, observation: LifecycleObservation) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()


def _inserts(observation: LifecycleObservation) -> list[LoweredStatement]:
    return [statement for statement in observation.writes if statement.sql.startswith("insert")]


def _assert_column_arrays(statement: LoweredStatement, width: int, rows: int) -> None:
    assert " select * from unnest(" in statement.sql
    assert len(statement.binds) == width
    assert all(isinstance(bind, ArrayBind) for bind in statement.binds)
    assert {len(bind.values) for bind in statement.binds if isinstance(bind, ArrayBind)} == {rows}
    assert rows * width > _PARAMETERS


def _read_back(db: ScopedDatabase, entity: Any) -> list[Any]:
    return list(db.find(entity.where(entity.id >= 0).order_by(entity.id.asc())).results())


@pytest.mark.parametrize(
    ("entity", "width"), [(Wide, 16), (WideSheet, 2)], ids=["columns", "document"]
)
def test_every_scalar_type_null_and_document_inserts_past_the_limit_in_one_statement(
    profile_run: Any, entity: Any, width: int
) -> None:
    observation = LifecycleObservation()
    db = _database(profile_run, observation)
    rows = _rows_past_the_limit(width)
    expected = [_wide(row) for row in range(1, rows + 1)]

    def insert(tx: TxnContext) -> None:
        for members in expected:
            tx.insert(entity(**members))

    db.transact(insert)

    (statement,) = _inserts(observation)
    _assert_column_arrays(statement, width, rows)
    stored = _read_back(db, entity)
    assert len(stored) == rows
    for row, members in zip(stored, expected, strict=True):
        assert {name: getattr(row, name) for name in members} == members, members["id"]
    # A null `place` is SQL NULL in its own Column, and JSON null at its path
    # inside the shared Structured Column.
    nulls = sum(members["place"] is None for members in expected)
    table, place, stored_nulls = (
        ("mri_wide", "place", (nulls, 0))
        if entity is Wide
        else ("mri_wide_sheet", "payload->'place'", (0, nulls))
    )
    ((sql_nulls, json_nulls),) = profile_run.port.execute(
        f"select count(*) filter (where {place} is null), "
        f"count(*) filter (where jsonb_typeof({place}) = 'null') from {table}",
        [],
    )
    assert (sql_nulls, json_nulls) == stored_nulls


def test_a_document_array_holds_one_document_per_element_none_being_sql_null(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    documents: list[object] = [None, JSON_NULL, {"kind": "object"}, ["nested", None], []]
    rows = profile_run.port.execute(
        "select t.v is null, jsonb_typeof(t.v), t.v::text, array_ndims(%s::jsonb[]) "
        "from unnest(cast(%s as jsonb[])) with ordinality as t(v, n) order by t.n",
        [ArrayBind(JSON, documents), ArrayBind(JSON, documents)],
    )
    assert [tuple(row) for row in rows] == [
        (True, None, None, 1),
        (False, "null", "null", 1),
        (False, "object", '{"kind": "object"}', 1),
        (False, "array", '["nested", null]', 1),
        (False, "array", "[]", 1),
    ]


def _stored_places(profile_run: Any) -> list[tuple[object, ...]]:
    """Each ``mri_wide`` row's ``place`` Column: SQL NULL, and its JSON kind."""
    return [
        tuple(row)
        for row in profile_run.port.execute(
            "select id, place is null, jsonb_typeof(place) from mri_wide order by id", []
        )
    ]


def _assert_document_column(statement: LoweredStatement, rows: int) -> None:
    assert " select * from unnest(" in statement.sql
    documents = [
        bind
        for bind in statement.binds
        if isinstance(bind, ArrayBind) and isinstance(bind.element_type, Json)
    ]
    assert documents and {len(bind.values) for bind in documents} == {rows}


def test_a_null_value_object_is_sql_null_whether_written_alone_or_in_a_column_array(
    profile_run: Any,
) -> None:
    observation = LifecycleObservation()
    db = _database(profile_run, observation)

    def batch(tx: TxnContext) -> None:
        tx.insert(Wide(id=2, place=None))
        tx.insert(Wide(id=3, place=Place(city="c", rank=1)))

    db.transact(lambda tx: tx.insert(Wide(id=1, place=None)))
    db.transact(batch)
    db.transact(lambda tx: tx.amend(tx.find(Wide.where(Wide.id == 3)).result().edit(place=None)))

    alone, columns = _inserts(observation)
    assert " values (" in alone.sql
    _assert_document_column(columns, rows=2)
    assert _stored_places(profile_run) == [(1, True, None), (2, True, None), (3, True, None)]


def test_a_literal_json_null_document_stays_json_null_alone_and_in_a_column_array(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    profile_run.port.execute_write(
        "insert into mri_wide(id, place, tags, counts) values (%s, %s, %s, %s)",
        [1, JsonDocument(None), JsonDocument([]), JsonDocument([])],
    )
    profile_run.port.execute_write(
        "insert into mri_wide(id, place, tags, counts) select * from unnest("
        "cast(%s as bigint[]), cast(%s as jsonb[]), cast(%s as jsonb[]), cast(%s as jsonb[]))",
        [
            ArrayBind(INT64, [2, 3]),
            ArrayBind(JSON, [JSON_NULL, None]),
            ArrayBind(JSON, [[], []]),
            ArrayBind(JSON, [[], []]),
        ],
    )
    assert _stored_places(profile_run) == [(1, False, "null"), (2, False, "null"), (3, True, None)]


@pytest.mark.parametrize(
    ("family", "width"),
    [("tph_columns", 4), ("tph_document", 3), ("tpcs_columns", 3)],
)
def test_an_inheritance_family_inserts_each_concretes_rows_in_one_statement(
    profile_run: Any, family: str, width: int
) -> None:
    root, disc, plate = _FAMILIES[family]
    observation = LifecycleObservation()
    db = _database(profile_run, observation)
    rows = _rows_past_the_limit(width)
    discs = [{"id": row, "label": f"d{row}", "size": row / 4} for row in range(1, rows + 1)]
    plates = [
        {"id": rows + row, "label": f"p{row}", "size": Decimal(row).scaleb(-3)}
        for row in range(1, 4)
    ]

    def insert(tx: TxnContext) -> None:
        for members in discs:
            tx.insert(disc(**members))
        for members in plates:
            tx.insert(plate(**members))

    db.transact(insert)

    many, few = _inserts(observation)
    _assert_column_arrays(many, width, rows)
    assert {len(bind.values) for bind in few.binds if isinstance(bind, ArrayBind)} == {3}
    stored = _read_back(db, root)
    assert [(type(row).__name__, row.id, row.label, row.size) for row in stored] == [
        *(("Disc", m["id"], m["label"], m["size"]) for m in discs),
        *(("Plate", m["id"], m["label"], m["size"]) for m in plates),
    ]


def _instant(value: object) -> str:
    if not isinstance(value, dt.datetime):
        return "infinity"
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def test_a_ranged_write_opens_every_successor_in_one_statement(profile_run: Any) -> None:
    milestones = 70
    seeded = seeded_history("keyed-amend", milestones, 0)
    profile_run.reset(
        model_of(_MODEL),
        {
            "Opened": [
                {
                    "id": row.key,
                    "label": row.label,
                    "amount": row.amount,
                    "validStart": _instant(row.valid_from),
                    "validEnd": _instant(row.valid_to),
                    "txStart": _instant(row.tx_from),
                    "txEnd": _instant(row.tx_to),
                }
                for row in seeded
            ]
        },
    )
    observation = LifecycleObservation()
    db = own_root(
        connect(
            profile_run.port,
            _MODEL,
            clock=FixedClock(AMENDED_AT),
            lifecycle_provider=observation.provider,
        )
    ).using_database_login()
    start, end = window(milestones)

    def amend(tx: TxnContext) -> None:
        source = tx.find(Opened.where(Opened.id == 1).as_of(valid_time=start)).result()
        tx.amend(source.edit(amount=AMOUNT), until=end)

    db.transact(amend)

    expected = expected_history("keyed-amend", milestones, 0)
    opened = [row for row in expected if row.tx_from == AMENDED_AT]
    (statement,) = _inserts(observation)
    assert {len(bind.values) for bind in statement.binds if isinstance(bind, ArrayBind)} == {
        len(opened)
    }
    assert len(opened) > 64
    stored = ordered_history(
        HistoryRow(*row)
        for row in profile_run.port.execute(
            "select id, from_z, thru_z, in_z, out_z, label, amount from mri_opened", []
        )
    )
    assert stored == ordered_history(expected)


# --------------------------------------------------------------------------- #
# Failures keep the kind a row alone raises.                                   #
# --------------------------------------------------------------------------- #


def _failure(db: ScopedDatabase, write: Callable[[TxnContext], None]) -> DatabaseError:
    with pytest.raises(ExecutionFailure) as failed:
        db.transact(write, max_retries=0)
    cause = failed.value.cause
    assert isinstance(cause, DatabaseError)
    return cause


def _coded(tx: TxnContext, rows: list[tuple[int, str, int]]) -> None:
    for key, code, level in rows:
        tx.insert(Coded(id=key, code=code, level=level))


def test_a_duplicate_within_one_statement_names_the_unique_index_it_violated(
    profile_run: Any,
) -> None:
    observation = LifecycleObservation()
    db = _database(profile_run, observation)

    error = _failure(db, lambda tx: _coded(tx, [(1, "a", 1), (2, "b", 1), (3, "a", 1)]))

    ((index_name,),) = profile_run.port.execute(
        "select indexname from pg_indexes where tablename = 'mri_coded' "
        "and indexdef like '%%(code)%%'",
        [],
    )
    assert (error.category, error.native_code) == ("uniqueViolation", "23505")
    assert error.violates_unique_index
    assert error.violated_index is not None
    assert error.violated_index.value == index_name
    (statement,) = _inserts(observation)
    _assert_rows(statement, 3)


def _assert_rows(statement: LoweredStatement, rows: int) -> None:
    assert " select * from unnest(" in statement.sql
    assert {len(bind.values) for bind in statement.binds if isinstance(bind, ArrayBind)} == {rows}


@pytest.mark.parametrize(
    ("alteration", "rows", "native_code"),
    [
        pytest.param(
            "alter column code type varchar(3)",
            [(1, "abc", 1), (2, "abcd", 1)],
            "22001",
            id="over-long-string",
        ),
        pytest.param(
            "alter column level type smallint",
            [(1, "a", 1), (2, "b", 40_000)],
            "22003",
            id="out-of-range-number",
        ),
    ],
)
def test_an_element_assignment_refuses_rather_than_truncates_or_rounds(
    profile_run: Any, alteration: str, rows: list[tuple[int, str, int]], native_code: str
) -> None:
    observation = LifecycleObservation()
    db = _database(profile_run, observation)
    control = profile_run.control()
    try:
        control.execute_write(f"alter table mri_coded {alteration}", [])
    finally:
        control.close()

    error = _failure(db, lambda tx: _coded(tx, rows))

    assert error.native_code == native_code
    (statement,) = _inserts(observation)
    _assert_rows(statement, len(rows))
    assert profile_run.port.execute("select count(*) from mri_coded", []) == [(0,)]


def test_an_exclusion_conflict_of_one_statement_is_recognized_and_retried(
    profile_run: Any,
) -> None:
    jan, mar, may, jun = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5, 6))
    profile_run.reset(model_of(_MODEL), {})

    def database(*instants: dt.datetime, provider: Any = None) -> ScopedDatabase:
        return own_root(
            connect(
                profile_run.port,
                _MODEL,
                clock=ScriptedClock(list(instants)),
                lifecycle_provider=provider,
            )
        ).using_database_login()

    seeded = database(jan, may)
    seeded.transact(lambda tx: tx.insert(Log(id=1, label="seeded")))
    seeded.transact(lambda tx: tx.terminate(tx.find(Log.where(Log.id == 1)).result()))
    attempts: list[None] = []

    def reopen(tx: TxnContext) -> None:
        # At March, object 1 would reopen inside its stored history; a retry
        # reopens both objects in June.
        attempts.append(None)
        tx.insert(Log(id=1, label="again"))
        tx.insert(Log(id=2, label="fresh"))

    error = _failure(database(mar), reopen)
    layout = storage_layout.view(model_of(_MODEL)).table(Table("mri_log"))
    assert layout is not None and layout.temporal_constraints is not None
    assert (error.category, error.native_code) == ("constraintViolation", "23P01")
    assert error.constraint_name == layout.temporal_constraints.exclusion_name

    provider = RecordingLifecycleProvider()
    database(mar, jun, provider=provider).transact(reopen)

    assert len(attempts) == 3
    events = [event for root in provider.roots for event in root.events]
    refused, committed = (
        event for event in events if isinstance(event, TransactionAttemptFinished)
    )
    assert isinstance(refused.outcome, AttemptRolledBack)
    assert refused.outcome.failure.retry_eligible
    assert isinstance(committed.outcome, AttemptCommitted)
    (failed,) = (
        event
        for event in events
        if isinstance(event, DatabaseCallFinished) and isinstance(event.outcome, DatabaseCallFailed)
    )
    (started,) = (
        event
        for event in events
        if isinstance(event, DatabaseCallStarted) and event.activity_id == failed.activity_id
    )
    _assert_rows(started.statement, 2)
    assert profile_run.port.execute(
        "select id, label, in_z, case when out_z = 'infinity' then null else out_z end "
        "from mri_log order by id, in_z",
        [],
    ) == [(1, "seeded", jan, may), (1, "again", jun, None), (2, "fresh", jun, None)]
