"""Native Float32 and Float64 columns read back exactly through the shipped verbs.

A Float32 cell must arrive as the binary32 value the server stored, not as the
nearest binary64 to its shortest spelling. The carrier is more than a displayed
value: it is the coordinate a stream resumes after, the identity a locking
stream and a keyed write address, the value an included child correlates on,
and the predecessor an acquiring write weighs its assignment against. Expected
values come from independent binary32 oracles, never from a float parse.
"""

from __future__ import annotations

import math
import struct
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import cycle, islice
from typing import Any, Literal, cast

import pytest

from parallax.core import (
    ONE_TO_MANY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Float32,
    Int32,
    Rel,
    attr,
    rel,
)
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.snapshot import connect
from parallax.snapshot.handle import ExecutionFailure, ScopedDatabase, SnapshotStream, Transaction
from tests._support.binary32 import narrowed, shortest_spelling
from tests._support.root_ownership import own_root

_NAMESPACE = "native.float"


class Reading(Entity, table="nf_reading", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    f32: Attr[float] = attr(type=Float32)
    f64: Attr[float]


class Marker(Entity, table="nf_marker", namespace=_NAMESPACE):
    id: Attr[float] = attr(type=Float32, primary_key=True)
    rank: Attr[int | None]
    name: Attr[str]


class Parent(Entity, table="nf_parent", namespace=_NAMESPACE):
    id: Attr[float] = attr(type=Float32, primary_key=True)
    children: Rel[tuple[Child, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "owner"), dependent=True
    )


class Child(Entity, table="nf_child", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[float] = attr(type=Float32)
    value: Attr[float] = attr(type=Float32)


class Asset(Entity, namespace=_NAMESPACE, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
    id: Attr[int] = attr(primary_key=True)
    value: Attr[float] = attr(type=Float32)


class Bond(Asset, table="nf_bond", namespace=_NAMESPACE, inheritance=ConcreteSubtype):
    coupon: Attr[float | None] = attr(type=Float32)


class Stock(Asset, table="nf_stock", namespace=_NAMESPACE, inheritance=ConcreteSubtype):
    shares: Attr[int]


_MODEL = DomainModel(Reading, Marker, Parent, Child, Asset, Bond, Stock)

type Representation = Literal["typed", "wire"]
type Direction = Literal["asc", "desc"]
_REPRESENTATIONS: tuple[Representation, ...] = ("typed", "wire")
_DIRECTIONS: tuple[Direction, ...] = ("asc", "desc")


def _binary32(bits: int) -> float:
    (value,) = struct.unpack("<f", struct.pack("<I", bits))
    return value


def _bits32(value: float) -> int:
    (bits,) = struct.unpack("<I", struct.pack("<f", value))
    return bits


def _bits(value: float) -> bytes:
    assert type(value) is float, f"{value!r} is carried as {type(value).__name__}, not float"
    return struct.pack("<d", value)


# Its shortest spelling parses to the binary64 midpoint between it and the next
# binary32 value up, so parsing and then narrowing reads that neighbour instead.
_MIDPOINT = 7.038530691851209e-26
_ABOVE_MIDPOINT = _binary32(_bits32(_MIDPOINT) + 1)
_BELOW_MIDPOINT = _binary32(_bits32(_MIDPOINT) - 1)
_SMALLEST_SUBNORMAL = _binary32(0x00000001)
_LARGEST_SUBNORMAL = _binary32(0x007FFFFF)
_SMALLEST_NORMAL = _binary32(0x00800000)
_LARGEST_FINITE = _binary32(0x7F7FFFFF)
assert narrowed(float(shortest_spelling(_MIDPOINT))) == _ABOVE_MIDPOINT

# Authored Float32 values, each stored as its nearest binary32 value.
_FLOAT32_WIDTHS: tuple[float, ...] = (
    0.0,
    -0.0,
    -1e-50,
    1.2,
    _MIDPOINT,
    _ABOVE_MIDPOINT,
    _BELOW_MIDPOINT,
    -_MIDPOINT,
    1e-45,
    _LARGEST_SUBNORMAL,
    _SMALLEST_NORMAL,
    _binary32(0x00800001),
    _binary32(0x3F7FFFFF),
    _binary32(0x3F800001),
    _LARGEST_FINITE,
    -_LARGEST_FINITE,
)
_FLOAT64_WIDTHS: tuple[float, ...] = (
    0.0,
    -0.0,
    5e-324,
    -5e-324,
    2.225073858507201e-308,
    2.2250738585072014e-308,
    1.7976931348623157e308,
    -1.7976931348623157e308,
    0.30000000000000004,
    0.1,
    1.2,
    _MIDPOINT,
    math.nextafter(1.0, 0.0),
    math.nextafter(1.0, 2.0),
    1e-45,
    _LARGEST_FINITE,
)
assert len(_FLOAT32_WIDTHS) == len(_FLOAT64_WIDTHS)
_WIDTH_IDS = range(1, len(_FLOAT32_WIDTHS) + 1)


def _stored32(authored: float) -> float:
    """The Typed carrier: the nearest binary32 value, with zero positive."""
    return narrowed(authored) + 0.0


def _stored64(authored: float) -> float:
    return authored + 0.0


def _wire32(authored: float) -> float:
    """The Wire rendering: the shortest spelling that rounds back to the stored value."""
    return float(shortest_spelling(_stored32(authored)))


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL)).using_database_login()


def _wire_query(entity: str, **clauses: object) -> dict[str, object]:
    return {"target": f"{_NAMESPACE}.{entity}", "predicate": {"all": {}}, **clauses}


def _wire_order(entity: str, attribute: str, direction: Direction = "asc") -> list[object]:
    return [{"attr": f"{_NAMESPACE}.{entity}.{attribute}", "direction": direction}]


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return cast("Mapping[str, object]", row).get(name)
    return getattr(row, name, None)


def _drained[Row](stream: SnapshotStream[Row], *, expected: int) -> list[Row]:
    """Every row ``stream`` yields, stopping once it has yielded more than it should."""
    rows: list[Row] = []
    with stream as opened:
        for row in opened:
            rows.append(row)
            if len(rows) > 2 * expected:
                break
    return rows


# --------------------------------------------------------------------------- #
# Widths                                                                       #
# --------------------------------------------------------------------------- #

type Writer = Literal["insert", "keyed", "predicate"]
_WRITERS: tuple[Writer, ...] = ("insert", "keyed", "predicate")


def _insert_widths(representation: Representation, widths: Iterable[tuple[int, float, float]]):
    def insert(tx: Transaction) -> None:
        for key, f32, f64 in widths:
            if representation == "typed":
                tx.insert(Reading(id=key, f32=f32, f64=f64))
            else:
                tx.wire.insert(f"{_NAMESPACE}.Reading", {"id": key, "f32": f32, "f64": f64})

    return insert


def _keyed_widths(representation: Representation, widths: Mapping[int, tuple[float, float]]):
    def update(tx: Transaction) -> None:
        if representation == "typed":
            for row in tx.find(Reading.where(Reading.all)).results():
                f32, f64 = widths[row.id]
                tx.update(row.edit(f32=f32, f64=f64))
        else:
            for node in tx.wire.find(_wire_query("Reading")).results():
                f32, f64 = widths[cast("int", node["id"])]
                tx.wire.update(node, {"f32": f32, "f64": f64})

    return update


def _predicate_widths(representation: Representation, widths: Mapping[int, tuple[float, float]]):
    def update(tx: Transaction) -> None:
        for key, (f32, f64) in widths.items():
            if representation == "typed":
                tx.update_where(
                    Reading.where(Reading.id == key), Reading.f32.set(f32), Reading.f64.set(f64)
                )
            else:
                tx.wire.update_where(
                    {
                        "entity": f"{_NAMESPACE}.Reading",
                        "predicate": {"eq": {"attr": f"{_NAMESPACE}.Reading.id", "value": key}},
                    },
                    {"f32": f32, "f64": f64},
                )

    return update


def _write_widths(
    db: ScopedDatabase, representation: Representation, writer: Writer
) -> Mapping[int, tuple[float, float]]:
    widths = dict(zip(_WIDTH_IDS, zip(_FLOAT32_WIDTHS, _FLOAT64_WIDTHS, strict=True), strict=True))
    if writer == "insert":
        db.transact(_insert_widths(representation, ((k, *v) for k, v in widths.items())))
    else:
        db.transact(_insert_widths("typed", ((key, 1.5, 2.5) for key in widths)))
        write = _keyed_widths if writer == "keyed" else _predicate_widths
        db.transact(write(representation, widths))
    return widths


type Reader = Literal["typed-eager", "typed-stream", "wire-eager", "wire-stream"]
_READERS: tuple[Reader, ...] = ("typed-eager", "typed-stream", "wire-eager", "wire-stream")


def _read_readings(db: ScopedDatabase, reader: Reader) -> list[Any]:
    typed = Reading.where(Reading.all).order_by(Reading.id.asc())
    wire = _wire_query("Reading", orderBy=_wire_order("Reading", "id"))
    expected = len(_FLOAT32_WIDTHS)
    match reader:
        case "typed-eager":
            return list(db.find(typed).results())
        case "typed-stream":
            return _drained(db.stream(typed, batch_size=1), expected=expected)
        case "wire-eager":
            return list(db.wire.find(wire).results())
        case "wire-stream":
            return _drained(db.wire.stream(wire, batch_size=1), expected=expected)


@pytest.mark.parametrize("writer", _WRITERS)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_every_width_edge_reads_back_exactly_and_rewriting_it_is_a_no_op(
    profile_run: Any, representation: Representation, writer: Writer
) -> None:
    db = _served(profile_run)
    widths = _write_widths(db, representation, writer)

    for reader in _READERS:
        rows = _read_readings(db, reader)
        observed = [(_field(row, "id"), _field(row, "f32"), _field(row, "f64")) for row in rows]
        render32 = _wire32 if reader.startswith("wire") else _stored32
        expected = [
            (key, render32(f32), _stored64(f64)) for key, (f32, f64) in sorted(widths.items())
        ]
        assert [(key, _bits(f32), _bits(f64)) for key, f32, f64 in observed] == [
            (key, _bits(f32), _bits(f64)) for key, f32, f64 in expected
        ], reader

    # Each write weighs what it states against the rows it read back, so none
    # finds anything to write. A Wire keyed write states what its node published.
    versions = {row.id: row.version for row in _read_readings(db, "typed-eager")}
    db.transact(_predicate_widths(representation, widths))
    if representation == "typed":
        db.transact(_keyed_widths(representation, widths))
    else:
        db.transact(_republished)
    assert {row.id: row.version for row in _read_readings(db, "typed-eager")} == versions


def _republished(tx: Transaction) -> None:
    for node in tx.wire.find(_wire_query("Reading")).results():
        tx.wire.update(node, {"f32": node["f32"], "f64": node["f64"]})


_NONFINITE = (math.nan, math.inf, -math.inf)


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_nonfinite_float_is_refused_before_any_write(
    profile_run: Any, representation: Representation
) -> None:
    db = _served(profile_run)
    db.transact(_insert_widths("typed", [(1, 1.5, 2.5)]))

    for invalid in _NONFINITE:
        for f32, f64 in ((invalid, 2.5), (1.5, invalid)):
            attempts: Sequence[Callable[[Transaction], None]] = (
                _insert_widths(representation, [(2, f32, f64)]),
                _keyed_widths(representation, {1: (f32, f64)}),
                _predicate_widths(representation, {1: (f32, f64)}),
            )
            for attempt in attempts:
                with pytest.raises(ExecutionFailure) as refused:
                    db.transact(attempt)
                assert not isinstance(refused.value.cause, DatabaseError)

    (row,) = _read_readings(db, "typed-eager")
    assert (row.id, row.version, _bits(row.f32), _bits(row.f64)) == (1, 1, _bits(1.5), _bits(2.5))


# --------------------------------------------------------------------------- #
# Identity, continuation, correlation, and family unions                       #
# --------------------------------------------------------------------------- #

# Float32 keys with signed values, both midpoint neighbours, a duplicate, and
# each width edge.
_KEYS: tuple[float, ...] = tuple(
    _stored32(value)
    for value in (
        1.2,
        -1.2,
        _MIDPOINT,
        _ABOVE_MIDPOINT,
        -_MIDPOINT,
        _SMALLEST_SUBNORMAL,
        -_SMALLEST_SUBNORMAL,
        _LARGEST_SUBNORMAL,
        _SMALLEST_NORMAL,
        _LARGEST_FINITE,
        -_LARGEST_FINITE,
        0.0,
    )
)


def _identity(representation: Representation, value: float) -> float:
    return _wire32(value) if representation == "wire" else value


# Identities whose shortest spelling parses onto a binary64 midpoint, and others.
_MIDPOINT_IDENTITIES = (_MIDPOINT, _ABOVE_MIDPOINT, -_MIDPOINT, -_ABOVE_MIDPOINT)
_ORDINARY_IDENTITIES = tuple(key for key in _KEYS if key not in _MIDPOINT_IDENTITIES)
_WIRE_MIDPOINT_IDENTITY = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "Wire publishes a Float32 whose shortest spelling parses onto a binary64 midpoint "
        "as that plain float, and a keyed write decodes it to the adjacent binary32 value, "
        "so it addresses the neighbouring identity"
    ),
)


def _identity_cases(*wire_midpoint: pytest.MarkDecorator) -> list[Any]:
    return [
        pytest.param("typed", _ORDINARY_IDENTITIES, id="typed-ordinary"),
        pytest.param("typed", _MIDPOINT_IDENTITIES, id="typed-midpoint"),
        pytest.param("wire", _ORDINARY_IDENTITIES, id="wire-ordinary"),
        pytest.param("wire", _MIDPOINT_IDENTITIES, id="wire-midpoint", marks=wire_midpoint),
    ]


def _lock_and_update_each(
    db: ScopedDatabase, representation: Representation, identities: tuple[float, ...]
) -> tuple[dict[float, int | None], list[Any]]:
    ranks = islice(cycle((2, 1, None, 1, None, 3)), len(identities))
    ranked = dict(zip(identities, ranks, strict=True))
    db.transact(
        lambda tx: [
            tx.insert(Marker(id=key, rank=rank, name="initial")) for key, rank in ranked.items()
        ]
    )

    def lock_and_update(tx: Transaction) -> list[Any]:
        if representation == "typed":
            query = Marker.where(Marker.all).order_by(Marker.rank.asc())
            rows = _drained(tx.stream(query, batch_size=1), expected=len(ranked))
            for row in rows:
                tx.update(row.edit(name="updated"))
        else:
            wire = _wire_query("Marker", orderBy=_wire_order("Marker", "rank"))
            rows = _drained(tx.wire.stream(wire, batch_size=1), expected=len(ranked))
            for node in rows:
                tx.wire.update(node, {"name": "updated"})
        return rows

    return ranked, db.transact(lock_and_update, concurrency="locking")


@pytest.mark.parametrize(("representation", "identities"), _identity_cases())
def test_a_locking_stream_in_nullable_order_yields_each_float32_identity_once(
    profile_run: Any, representation: Representation, identities: tuple[float, ...]
) -> None:
    ranked, rows = _lock_and_update_each(_served(profile_run), representation, identities)

    observed = [_field(row, "id") for row in rows]
    expected = {_identity(representation, key): rank for key, rank in ranked.items()}
    assert Counter(map(_bits, observed)) == Counter(map(_bits, expected))
    assert [expected[key] for key in observed] == sorted(
        ranked.values(), key=lambda rank: (rank is None, rank or 0)
    )


@pytest.mark.parametrize(("representation", "identities"), _identity_cases(_WIRE_MIDPOINT_IDENTITY))
def test_a_keyed_update_of_each_locked_float32_identity_updates_that_identity(
    profile_run: Any, representation: Representation, identities: tuple[float, ...]
) -> None:
    db = _served(profile_run)
    _lock_and_update_each(db, representation, identities)

    stored = db.find(Marker.where(Marker.all)).results()
    assert Counter((_bits(row.id), row.name) for row in stored) == Counter(
        (_bits(key), "updated") for key in identities
    )


@pytest.mark.parametrize("direction", _DIRECTIONS)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_stream_ordered_by_a_float32_key_yields_every_root_exactly_once(
    profile_run: Any, representation: Representation, direction: Direction
) -> None:
    db = _served(profile_run)
    values = (*_KEYS, _KEYS[0], _KEYS[2])
    db.transact(
        lambda tx: [
            tx.insert(Reading(id=key, f32=value, f64=0.0))
            for key, value in enumerate(values, start=1)
        ]
    )

    if representation == "typed":
        key = Reading.f32.asc() if direction == "asc" else Reading.f32.desc()
        stream = db.stream(Reading.where(Reading.all).order_by(key), batch_size=1)
    else:
        wire = _wire_query("Reading", orderBy=_wire_order("Reading", "f32", direction))
        stream = db.wire.stream(wire, batch_size=1)
    rows = _drained(stream, expected=len(values))

    assert sorted(_field(row, "id") for row in rows) == list(range(1, len(values) + 1))
    ordered = sorted(values, reverse=direction == "desc")
    assert [_bits(_field(row, "f32")) for row in rows] == [
        _bits(_identity(representation, value)) for value in ordered
    ]


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_included_children_correlate_on_a_float32_parent_identity(
    profile_run: Any, representation: Representation
) -> None:
    db = _served(profile_run)
    parents = (_stored32(1.2), _MIDPOINT, _ABOVE_MIDPOINT, -_MIDPOINT, _SMALLEST_SUBNORMAL)
    children = {parent: (_LARGEST_SUBNORMAL, -parent) for parent in parents}

    def insert(tx: Transaction) -> None:
        key = 0
        for parent, values in children.items():
            tx.insert(Parent(id=parent))
            for value in values:
                key += 1
                tx.insert(Child(id=key, owner=parent, value=value))

    db.transact(insert)

    if representation == "typed":
        query = Parent.where(Parent.all).include(Parent.children).order_by(Parent.id.asc())
        read = [
            list(db.find(query).results()),
            _drained(db.stream(query, batch_size=1), expected=len(parents)),
        ]
    else:
        wire = _wire_query(
            "Parent",
            orderBy=_wire_order("Parent", "id"),
            includes=[{"segments": [{"rel": f"{_NAMESPACE}.Parent.children"}]}],
        )
        read = [
            list(db.wire.find(wire).results()),
            _drained(db.wire.stream(wire, batch_size=1), expected=len(parents)),
        ]

    expected = [
        (
            _bits(_identity(representation, parent)),
            sorted(
                (_bits(_identity(representation, parent)), _bits(_identity(representation, value)))
                for value in children[parent]
            ),
        )
        for parent in sorted(parents)
    ]
    for rows in read:
        observed = [
            (
                _bits(_field(row, "id")),
                sorted(
                    (_bits(_field(child, "owner")), _bits(_field(child, "value")))
                    for child in _field(row, "children")
                ),
            )
            for row in rows
        ]
        assert observed == expected


@pytest.mark.parametrize("direction", _DIRECTIONS)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_family_union_ordered_by_a_shared_float32_key_yields_each_subtype_row_once(
    profile_run: Any, representation: Representation, direction: Direction
) -> None:
    db = _served(profile_run)
    bonds = {
        1: (_MIDPOINT, _SMALLEST_SUBNORMAL),
        2: (-_LARGEST_FINITE, None),
        3: (_KEYS[0], _MIDPOINT),
    }
    stocks = {4: _ABOVE_MIDPOINT, 5: _KEYS[0], 6: _LARGEST_SUBNORMAL}

    def insert(tx: Transaction) -> None:
        for key, (value, coupon) in bonds.items():
            tx.insert(Bond(id=key, value=value, coupon=coupon))
        for key, value in stocks.items():
            tx.insert(Stock(id=key, value=value, shares=key))

    db.transact(insert)

    if representation == "typed":
        key = Asset.value.asc() if direction == "asc" else Asset.value.desc()
        stream = db.stream(Asset.where(Asset.all).order_by(key), batch_size=1)
    else:
        wire = _wire_query("Asset", orderBy=_wire_order("Asset", "value", direction))
        stream = db.wire.stream(wire, batch_size=1)
    rows = _drained(stream, expected=len(bonds) + len(stocks))

    values = {key: value for key, (value, _) in bonds.items()} | stocks
    assert sorted(_field(row, "id") for row in rows) == sorted(values)
    assert [_bits(_field(row, "value")) for row in rows] == [
        _bits(_identity(representation, value))
        for value in sorted(values.values(), reverse=direction == "desc")
    ]
    for row in rows:
        key = _field(row, "id")
        if key in bonds:
            coupon = bonds[key][1]
            observed = _field(row, "coupon")
            assert (None if observed is None else _bits(observed)) == (
                None if coupon is None else _bits(_identity(representation, coupon))
            )
        else:
            assert _field(row, "shares") == key
