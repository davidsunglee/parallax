"""The adapter's compiled text loaders, graded against independent oracles.

The loaders are compiled, so no line coverage reaches them; these differential
checks are what grade them. Every stored cell is read through a session
initialized exactly as an owned connection is, so the loader under test is the
one the adapter registered; a spelling no stored value produces is handed to
that loader directly. A ``real`` is graded against PostgreSQL's own binary-format
result and against exact rational rounding of the text the server sent; a
finite ``timestamptz`` against an independently stated UTC instant, under
session zones that spell it differently, and a spelling psycopg cannot read
against its own C text loader's refusal of the same bytes.
"""

from __future__ import annotations

import math
import random
import struct
import sys
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast

import psycopg
import pytest
from psycopg.abc import Loader
from psycopg.pq import Format
from psycopg.rows import TupleRow

from parallax.conformance._postgres_control import PostgresControl
from parallax.core.base import INFINITY
from parallax.postgres._compiled_loaders import compiled_loaders
from tests._support.binary32 import narrowed, rounded_once, rounding_witnesses

type Session = psycopg.Connection[TupleRow]

_LOADERS = compiled_loaders(psycopg.pq.__impl__)
_FLOAT4_OID = psycopg.postgres.types["float4"].oid
_TIMESTAMPTZ_OID = psycopg.postgres.types["timestamptz"].oid
_RANDOM_CORPUS = 20_000


@pytest.fixture(scope="module")
def session(profile_run: Any) -> Iterator[Session]:
    control = cast("PostgresControl", profile_run.control())
    try:
        yield control.native
    finally:
        control.close()


def _rows(session: Session, sql: bytes, *, binary: bool = False) -> list[tuple[Any, ...]]:
    with session.cursor(binary=binary) as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def _driver_loader(oid: int) -> type[Loader]:
    """psycopg's own text loader for ``oid``, as a connection nobody configured reads it."""
    loader = psycopg.adapters.get_loader(oid, Format.TEXT)
    assert loader is not None
    return loader


def _bits(value: float) -> bytes:
    return struct.pack("<d", value)


# --------------------------------------------------------------------------- #
# Float32                                                                      #
# --------------------------------------------------------------------------- #


def _stored(session: Session, values: list[float]) -> tuple[list[float], list[str], list[float]]:
    """``values`` stored as ``real``, read back through the adapter's text loader, as
    the server spelled them, and through psycopg's binary loader, in order."""
    session.execute(b"drop table if exists float32_readback")
    session.execute(b"create temp table float32_readback (position int, value real)")
    session.execute(
        "insert into float32_readback select position, value::real "
        "from unnest(%s::float8[]) with ordinality as stored(value, position)",
        [values],
    )
    select = b"select value, value::text from float32_readback order by position"
    loaded = _rows(session, select)
    truth = _rows(session, b"select value from float32_readback order by position", binary=True)
    return (
        [cast("float", value) for value, _ in loaded],
        [cast("str", spelling) for _, spelling in loaded],
        [cast("float", value) for (value,) in truth],
    )


def _counting_fallbacks(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record every call the Float32 loader makes to its exact converter."""
    module = sys.modules[_LOADERS.float4.__module__]
    exact = cast("Callable[[str], object]", module.nearest_binary32_of_spelling)
    calls: list[object] = []

    def counted(spelling: str) -> object:
        calls.append(spelling)
        return exact(spelling)

    monkeypatch.setattr(module, "nearest_binary32_of_spelling", counted)
    return calls


@pytest.mark.parametrize(
    ("value", "exact_parse", "midpoint"),
    [
        pytest.param(1.5, True, False, id="exactly-representable"),
        pytest.param(narrowed(1.2), False, False, id="ordinary-rounded"),
        # Its shortest spelling, parsed to binary64, lands exactly on the
        # midpoint between two binary32 values and narrows to the wrong one.
        pytest.param(7.038530691851209e-26, False, True, id="midpoint"),
        pytest.param(-7.038530691851209e-26, False, True, id="negative-midpoint"),
        pytest.param(1.401298464324817e-45, False, False, id="smallest-subnormal"),
        pytest.param(1.1754942106924411e-38, False, False, id="largest-subnormal"),
        pytest.param(1.1754943508222875e-38, False, False, id="smallest-normal"),
        pytest.param(3.4028234663852886e38, False, False, id="largest-finite"),
        pytest.param(0.0, True, False, id="zero"),
        pytest.param(-0.0, True, False, id="negative-zero"),
    ],
)
def test_each_float32_branch_reads_the_stored_binary32_value(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    value: float,
    exact_parse: bool,
    midpoint: bool,
) -> None:
    assert narrowed(value) == value
    fallbacks = _counting_fallbacks(monkeypatch)

    (loaded,), (spelling,), (truth,) = _stored(session, [value])

    assert _bits(truth) == _bits(value)
    assert _bits(loaded) == _bits(truth)
    assert _bits(rounded_once(spelling)) == _bits(truth)
    parsed = float(spelling)
    assert (parsed == truth) is exact_parse
    assert (narrowed(parsed) != truth) is midpoint
    assert len(fallbacks) == (1 if midpoint else 0)


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["positive", "negative"])
def test_a_spelling_that_parses_onto_a_subnormal_midpoint_rounds_by_its_exact_decimal(
    monkeypatch: pytest.MonkeyPatch, sign: float
) -> None:
    # No shortest spelling of a ``real`` parses onto a subnormal midpoint, so
    # this one, a digit longer, is loaded directly.
    spelling = f"{'-' if sign < 0 else ''}7.0064923216240854e-46"
    fallbacks = _counting_fallbacks(monkeypatch)

    loaded = cast("float", _LOADERS.float4(_FLOAT4_OID).load(spelling.encode()))

    assert _bits(float(spelling)) == _bits(math.copysign(math.ldexp(1, -150), sign))
    assert narrowed(float(spelling)) == 0.0
    assert _bits(loaded) == _bits(rounded_once(spelling))
    assert _bits(loaded) == _bits(math.copysign(math.ldexp(1, -149), sign))
    assert len(fallbacks) == 1


def test_the_float32_loader_rounds_each_witness_spelling_once() -> None:
    loader = _LOADERS.float4(_FLOAT4_OID)
    witnesses = rounding_witnesses()

    loaded = [cast("float", loader.load(spelling.encode())) for spelling in witnesses]

    assert [_bits(value) for value in loaded] == [
        _bits(rounded_once(spelling)) for spelling in witnesses
    ]


@pytest.mark.parametrize("spelling", ["NaN", "Infinity", "-Infinity"])
def test_a_nonfinite_float32_reads_as_psycopgs_float_loader_reads_it(
    session: Session, spelling: str
) -> None:
    select = f"select '{spelling}'::real".encode()
    ((loaded,),) = _rows(session, select)
    ((truth,),) = _rows(session, select, binary=True)
    driver_loader = _driver_loader(_FLOAT4_OID)
    expected = cast("float", driver_loader(_FLOAT4_OID, session).load(spelling.encode()))

    assert type(loaded) is float
    if math.isnan(expected):
        assert math.isnan(loaded)
        assert math.isnan(truth)
    else:
        assert loaded == expected == truth


def test_random_finite_binary32_values_read_back_exactly(session: Session) -> None:
    generator = random.Random(185)
    values: list[float] = []
    while len(values) < _RANDOM_CORPUS:
        (value,) = struct.unpack("<f", generator.getrandbits(32).to_bytes(4, "little"))
        if math.isfinite(value):
            values.append(value)

    loaded, spellings, truth = _stored(session, values)

    assert [_bits(value) for value in truth] == [_bits(value) for value in values]
    assert [_bits(value) for value in loaded] == [_bits(value) for value in truth]
    assert [_bits(rounded_once(spelling)) for spelling in spellings] == [
        _bits(value) for value in truth
    ]


# --------------------------------------------------------------------------- #
# timestamptz                                                                  #
# --------------------------------------------------------------------------- #


def test_native_infinity_reads_as_the_neutral_unbounded_instant(session: Session) -> None:
    ((loaded,),) = _rows(session, b"select 'infinity'::timestamptz")

    assert loaded is INFINITY


_ZONES = ["UTC", "Etc/UTC", "Asia/Kathmandu", "America/St_Johns", "America/New_York"]
_ORDINARY_INSTANTS = [
    ("2024-02-29 12:34:56.789012+00", datetime(2024, 2, 29, 12, 34, 56, 789012, tzinfo=UTC)),
    ("1999-12-31 23:59:59.999999-08", datetime(2000, 1, 1, 7, 59, 59, 999999, tzinfo=UTC)),
    ("2038-01-19 03:14:07.5+05:45", datetime(2038, 1, 18, 21, 29, 7, 500000, tzinfo=UTC)),
    ("1900-06-01 00:00:00+01:30", datetime(1900, 5, 31, 22, 30, tzinfo=UTC)),
]
_MINIMUM = ("0001-01-01 00:00:00+00", datetime(1, 1, 1, tzinfo=UTC))
_MAXIMUM = ("9999-12-31 23:59:59.999999+00", datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC))


@contextmanager
def _zone(session: Session, zone: str) -> Generator[None]:
    session.execute(f"set time zone '{zone}'".encode())
    try:
        assert session.info.parameter_status("TimeZone") == zone
        yield
    finally:
        session.execute(b"reset time zone")


def _read(session: Session, instant: str) -> object:
    ((loaded,),) = _rows(session, f"select '{instant}'::timestamptz".encode())
    return loaded


@pytest.mark.parametrize(
    ("zone", "instant", "expected"),
    [
        *(
            pytest.param(zone, instant, expected, id=f"{zone}-{instant}")
            for zone in _ZONES
            for instant, expected in _ORDINARY_INSTANTS
        ),
        # Each edge under every zone that spells it within years 1 to 9999, the
        # years psycopg's text parser reads.
        *(
            pytest.param(zone, *_MINIMUM, id=f"{zone}-minimum")
            for zone in ("UTC", "Etc/UTC", "Asia/Kathmandu")
        ),
        *(
            pytest.param(zone, *_MAXIMUM, id=f"{zone}-maximum")
            for zone in ("UTC", "Etc/UTC", "America/St_Johns", "America/New_York")
        ),
    ],
)
def test_a_finite_timestamptz_reads_as_its_utc_instant_whatever_the_session_zone(
    session: Session, zone: str, instant: str, expected: datetime
) -> None:
    with _zone(session, zone):
        loaded = _read(session, instant)

    assert type(loaded) is datetime
    assert loaded.tzinfo is UTC
    assert loaded == expected


@pytest.mark.parametrize("zone", _ZONES)
@pytest.mark.parametrize(
    "instant",
    ["0001-01-01 00:30:00+01", "9999-12-31 23:59:59.999999-01"],
    ids=["before-the-minimum", "after-the-maximum"],
)
def test_an_instant_outside_the_utc_range_is_refused_whatever_the_session_zone(
    session: Session, zone: str, instant: str
) -> None:
    with _zone(session, zone), pytest.raises(psycopg.DataError):
        _read(session, instant)


@pytest.mark.parametrize(
    "spelling",
    [
        "0001-01-01 00:00:00+01",
        "0001-01-01 00:59:59.999999+01",
        "0001-01-01 00:00:00+00:00:01",
        "9999-12-31 23:59:59.999999-01",
        "9999-12-31 23:00:00-01:00:01",
    ],
)
def test_a_local_reading_whose_utc_instant_overflows_is_refused(
    session: Session, spelling: str
) -> None:
    # A session spells an instant in its own zone; this offset leaves the
    # reading in range and its UTC instant out of it.
    loader = _LOADERS.timestamptz(_TIMESTAMPTZ_OID, session)

    with pytest.raises(psycopg.DataError):
        loader.load(spelling.encode())


def _outcome(load: Callable[[], object]) -> object:
    """What ``load`` returns, or the refusal it raises as its class and text."""
    try:
        return load()
    except psycopg.DataError as refusal:
        return (type(refusal), str(refusal))


@pytest.mark.parametrize("spelling", ["2024-02-30 00:00:00+00", "not a timestamp"])
def test_a_spelling_psycopg_cannot_read_is_refused_as_psycopg_refuses_it(
    session: Session, spelling: str
) -> None:
    driver_loader = _driver_loader(_TIMESTAMPTZ_OID)

    expected = _outcome(lambda: driver_loader(_TIMESTAMPTZ_OID, session).load(spelling.encode()))
    loaded = _outcome(
        lambda: _LOADERS.timestamptz(_TIMESTAMPTZ_OID, session).load(spelling.encode())
    )

    assert isinstance(expected, tuple)
    assert loaded == expected


@pytest.mark.parametrize("zone", _ZONES)
def test_native_negative_infinity_is_refused_as_psycopg_refuses_it(
    session: Session, zone: str
) -> None:
    driver_loader = _driver_loader(_TIMESTAMPTZ_OID)
    with _zone(session, zone):
        ((spelling,),) = _rows(session, b"select '-infinity'::timestamptz::text")
        expected = _outcome(
            lambda: driver_loader(_TIMESTAMPTZ_OID, session).load(cast("str", spelling).encode())
        )
        loaded = _outcome(lambda: _read(session, "-infinity"))

    assert isinstance(expected, tuple)
    assert loaded == expected


def test_the_session_reads_through_the_compiled_loaders(session: Session) -> None:
    assert session.adapters.get_loader(_FLOAT4_OID, Format.TEXT) is _LOADERS.float4
    assert session.adapters.get_loader(_TIMESTAMPTZ_OID, Format.TEXT) is _LOADERS.timestamptz
