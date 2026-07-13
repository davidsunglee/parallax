"""Conformance engine unit tests (compile / run against the spine).

The compile path is proven pure and golden-matching over a representative
exercised case; the run path is proven against a fake in-memory
``m-db-port`` (no Docker) so the port-execution seam, the `?` -> `%s` translation,
and the observation recording are covered in the unit lane. Compile-eligibility
reading and the engine's failure modes are pinned too.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Callable, Sequence

import pytest

from parallax.conformance import case_format, engine, sweep
from parallax.core.base import InstantError
from parallax.core.db_port import DbPort, Row

pytestmark = pytest.mark.unit


class FakeDbPort:
    """An in-memory port that records executed SQL and returns canned rows."""

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, list[object]]] = []

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return self.rows

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)


def _case(case_id: str) -> case_format.Case:
    (case,) = [c for c in sweep.reachable_cases() if c.case_id == case_id]
    return case


def test_compile_read_case_matches_golden() -> None:
    emissions, round_trips = engine.compile_read_case(_case("m-value-object-001"), "postgres")
    assert round_trips == 1
    assert emissions[0].case_pointer == "/operation"
    assert emissions[0].sql == (
        "select t0.id, t0.name from customer t0 where jsonb_extract_path_text(t0.address, ?) = ?"
    )
    assert emissions[0].binds == ("city", "Oslo")
    assert emissions[0].to_json()["casePointer"] == "/operation"


def test_run_read_case_executes_driver_sql_and_records_rows() -> None:
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    emissions, rows, round_trips = engine.run_read_case(
        _case("m-value-object-001"), "postgres", port
    )
    assert round_trips == 1
    assert rows == [{"id": 1, "name": "Grace"}]
    assert emissions[0].sql.count("?") == 2
    driver_sql, driver_binds = port.executed[0]
    assert "%s" in driver_sql and "?" not in driver_sql
    assert driver_binds == ["city", "Oslo"]


def test_run_read_case_wire_renders_managed_row_values() -> None:
    # The port returns managed values; run_read_case records canonical wire form.
    port = FakeDbPort([{"id": 1, "external_id": uuid.UUID("123e4567-e89b-12d3-a456-426614174000")}])
    _emissions, rows, _round_trips = engine.run_read_case(
        _case("m-value-object-001"), "postgres", port
    )
    assert rows == [{"id": 1, "external_id": "123e4567-e89b-12d3-a456-426614174000"}]


def test_wire_value_covers_the_managed_type_set() -> None:
    assert engine.wire_value(None) is None
    assert engine.wire_value(True) is True
    assert engine.wire_value(decimal.Decimal("12.34")) == "12.34"
    # A `datetime` is an instant: an aware UTC value renders with the `+00:00`
    # offset (canonical UTC), a `date`/`time` (not an instant) renders as-is.
    assert engine.wire_value(dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.UTC)) == (
        "2024-01-02T03:04:05+00:00"
    )
    assert engine.wire_value(dt.date(2024, 1, 2)) == "2024-01-02"
    assert engine.wire_value(dt.time(3, 4, 5)) == "03:04:05"
    assert engine.wire_value(memoryview(b"\x01\x02")) == "0102"
    sentinel = object()  # an unrecognized value passes through unchanged
    assert engine.wire_value(sentinel) is sentinel


def test_wire_value_normalizes_an_aware_non_utc_datetime_to_utc() -> None:
    # A `timestamp` observation is normalized through the m-core UTC-instant path
    # BEFORE ISO-rendering, so a non-UTC offset is canonicalized to UTC rather than
    # graded verbatim (2024-01-02T03:04:05+05:00 -> 2024-01-01T22:04:05+00:00).
    aware = dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.timezone(dt.timedelta(hours=5)))
    assert engine.wire_value(aware) == "2024-01-01T22:04:05+00:00"


def test_wire_value_rejects_a_naive_datetime() -> None:
    # A naive `datetime` carries no offset and cannot be an instant: the m-core
    # boundary rejects it loudly rather than silently rendering an ambiguous form.
    with pytest.raises(InstantError):
        engine.wire_value(dt.datetime(2024, 1, 2, 3, 4, 5))


def test_eligibility_reads_the_case_declaration() -> None:
    assert engine.eligibility(_case("m-value-object-001")) is None
    cases = case_format.load_cases()
    run_only = [c for c in cases if engine.eligibility(c) is not None]
    assert run_only, "the corpus declares at least one run-only case"
    first = engine.eligibility(run_only[0])
    assert first is not None and first.reason  # a non-empty reason


def test_compile_rejects_non_read_shape() -> None:
    write_seq = next(c for c in case_format.load_cases() if c.shape == "writeSequence")
    with pytest.raises(engine.EngineError, match="only `read`-shape compile"):
        engine.compile_read_case(write_seq, "postgres")


def _synthetic(document: dict[str, object]) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path("m-op-algebra-999-synthetic.yaml"),
        case_id="m-op-algebra-999",
        shape="read",
        tags=("m-op-algebra", "slice-snapshot-1"),
        model="models/orders.yaml",
        document=document,
    )


def test_eligibility_non_run_only_declaration_is_compile_eligible() -> None:
    case = _synthetic({"compileEligibility": {"mode": "eligible"}})
    assert engine.eligibility(case) is None


def test_load_case_metamodel_rejects_a_non_string_model() -> None:
    case = _synthetic({"model": 42})
    with pytest.raises(engine.EngineError, match="`model` must be a string"):
        engine.load_case_metamodel(case)


@pytest.mark.parametrize(
    "document, message",
    [
        ({"model": "models/orders.yaml"}, "no `when`"),
        ({"model": "models/orders.yaml", "when": {}}, "no `targetEntity`"),
        ({"model": "models/orders.yaml", "when": {"targetEntity": "Order"}}, "no `operation`"),
    ],
)
def test_compile_read_case_reports_missing_fields(
    document: dict[str, object], message: str
) -> None:
    with pytest.raises(engine.EngineError, match=message):
        engine.compile_read_case(_synthetic(document), "postgres")
