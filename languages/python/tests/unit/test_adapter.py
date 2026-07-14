"""Conformance adapter core (`parallax.conformance.adapter`) tests."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

import jsonschema
import pytest

from conftest import adapter_schema, canonical_snapshot_claim
from parallax.conformance import adapter, case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim
from parallax.core.db_port import DbPort, Row

pytestmark = pytest.mark.unit

_SCHEMA = adapter_schema()
_READ_CASE = case_format.default_cases_dir() / "m-op-algebra-002-eq.yaml"
_VO_READ_CASE = case_format.default_cases_dir() / "m-value-object-001-nested-eq.yaml"
_SCALAR_READ_CASE = case_format.default_cases_dir() / "m-core-001-scalar-types-roundtrip.yaml"
_RUN_ONLY_CASE = (
    case_format.default_cases_dir() / "m-audit-write-006-optimistic-gated-chaining-update.yaml"
)


class _FakePort:
    """An in-memory ``m-db-port`` returning canned rows (no Docker)."""

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        return [{"id": 1, "name": "Ada"}]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)


def _case(
    *,
    shape: str = "read",
    tags: tuple[str, ...] = ("m-op-algebra", "slice-snapshot-1"),
) -> case_format.Case:
    return case_format.Case(
        path=Path("m-op-algebra-001-x.yaml"),
        case_id="m-op-algebra-001",
        shape=shape,
        tags=tags,
        model="models/orders.yaml",
        document={},
    )


def test_describe_matches_canonical_claim_except_adapter() -> None:
    envelope = adapter.describe()
    jsonschema.validate(envelope, _SCHEMA)
    canonical = canonical_snapshot_claim()
    assert envelope["capabilities"] == canonical["capabilities"]
    assert envelope["command"] == "describe"
    assert envelope["status"] == "ok"
    # Only the adapter identity differs from the canonical (reference) claim.
    assert envelope["adapter"] == {
        "language": "python",
        "name": "parallax-core",
        "version": "0.1.0",
    }
    assert envelope["adapter"] != canonical["adapter"]


def test_classify_admits_an_in_claim_case() -> None:
    assert adapter.classify("compile", "postgres", _case()) is None


@pytest.mark.parametrize(
    ("command", "dialect", "case", "code"),
    [
        ("benchmark", "postgres", _case(), "unsupported-command"),
        ("compile", "mariadb", _case(), "unsupported-dialect"),
        ("compile", "postgres", _case(shape="coherence"), "unsupported-case-shape"),
        ("compile", "postgres", _case(tags=("m-agg", "slice-snapshot-1")), "unsupported-module"),
        ("compile", "postgres", _case(tags=("m-op-algebra",)), "unsupported-case-tag"),
    ],
)
def test_classify_names_the_first_failed_filter(
    command: str, dialect: str, case: case_format.Case, code: str
) -> None:
    diagnostic = adapter.classify(command, dialect, case)
    assert diagnostic is not None
    assert diagnostic.code == code


def test_classify_exclude_filter() -> None:
    claim = Claim(
        modules=("m-op-algebra",),
        dialects=("postgres",),
        case_shapes=("read",),
        include=("slice-snapshot-1",),
        exclude=("aggregation",),
        commands=("compile",),
        provisioning="self-managed",
    )
    case = _case(tags=("m-op-algebra", "slice-snapshot-1", "aggregation"))
    diagnostic = adapter.classify("compile", "postgres", case, claim)
    assert diagnostic is not None
    assert diagnostic.code == "unsupported-case-tag"


def test_describe_uses_the_supplied_claim() -> None:
    envelope = adapter.describe(SNAPSHOT_CLAIM)
    assert envelope["capabilities"]["provisioning"] == "self-managed"


def test_compile_case_emits_for_a_claimed_read() -> None:
    envelope = adapter.compile_case(_READ_CASE, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["command"] == "compile"
    assert envelope["status"] == "ok"
    assert envelope["caseShape"] == "read"
    assert envelope["roundTrips"] == 1
    assert envelope["emissions"][0]["casePointer"] == "/operation"


def test_compile_case_unsupported_for_an_out_of_claim_dialect() -> None:
    envelope = adapter.compile_case(_READ_CASE, "mariadb")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-dialect"


def test_run_case_unsupported_for_an_out_of_claim_dialect() -> None:
    envelope = adapter.run_case(_READ_CASE, "mariadb", port=None)  # type: ignore[arg-type]
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "unsupported"


def test_compile_case_run_only_for_a_declared_run_only_case() -> None:
    envelope = adapter.compile_case(_RUN_ONLY_CASE, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "run-only"
    assert envelope["caseShape"] == "conflict"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"


def test_run_case_ok_through_a_fake_port() -> None:
    envelope = adapter.run_case(_VO_READ_CASE, "postgres", _FakePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"]["rows"] == [{"id": 1, "name": "Ada"}]
    assert envelope["observations"]["roundTrips"] == 1


class _WritePort:
    """A port that commits writes and returns canned find rows (no Docker)."""

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        return [{"id": 7}]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(self)


_SCENARIO_CASE = case_format.default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml"
_WRITE_SEQUENCE_CASE = case_format.default_cases_dir() / "m-unit-work-003-fk-insert-ordering.yaml"


def test_run_case_scenario_reports_round_trips_only() -> None:
    # A scenario run routes through the write lane: its write step commits and its find
    # reads committed state; the envelope carries only `roundTrips` (no per-step rows).
    envelope = adapter.run_case(_SCENARIO_CASE, "postgres", _WritePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {"roundTrips": 2}
    assert [e["casePointer"] for e in envelope["emissions"]] == [
        "/scenario/0/write",
        "/scenario/1/find",
    ]


def test_run_case_write_sequence_reports_round_trips_only() -> None:
    envelope = adapter.run_case(_WRITE_SEQUENCE_CASE, "postgres", _WritePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {"roundTrips": 2}
    assert [e["casePointer"] for e in envelope["emissions"]] == [
        "/writeSequence/0",
        "/writeSequence/1",
    ]


class _ManagedPort:
    """A port returning the managed values psycopg decodes for the m-core-001 row."""

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        return [
            {
                "id": 1,
                "f32": 1.5,
                "amount": decimal.Decimal("12.34"),
                "local_time": dt.time(12, 34, 56),
                "external_id": uuid.UUID("123e4567-e89b-12d3-a456-426614174000"),
                "payload": b"\x01\x02\x03\x04",
                "ordered_on": dt.date(2024, 1, 2),
            }
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)


def test_run_observations_are_wire_rendered_and_json_serializable() -> None:
    # The adapter returns MANAGED values (Decimal / time / UUID / date / bytes);
    # the conformance boundary renders them to canonical wire form so the run
    # envelope is JSON-serializable (m-core-001 previously broke `json.dumps`).
    envelope = adapter.run_case(_SCALAR_READ_CASE, "postgres", _ManagedPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    (row,) = envelope["observations"]["rows"]
    assert row == {
        "id": 1,
        "f32": 1.5,
        "amount": "12.34",
        "local_time": "12:34:56",
        "external_id": "123e4567-e89b-12d3-a456-426614174000",
        "payload": "01020304",
        "ordered_on": "2024-01-02",
    }
    # The whole envelope now round-trips through the wire (json.dumps).
    assert json.loads(json.dumps(envelope)) == envelope


def test_run_case_error_on_an_engine_gap() -> None:
    # A run-only conflict case has no read operation, so the read engine refuses it.
    envelope = adapter.run_case(_RUN_ONLY_CASE, "postgres", _FakePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][0]["code"] == "run-failed"


def test_unsupported_helper_envelope() -> None:
    envelope = adapter.unsupported("compile", adapter.Diagnostic("unsupported-dialect", "nope"))
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "unsupported"


def test_unsupported_command_envelope() -> None:
    envelope = adapter.unsupported_command("benchmark")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["command"] == "benchmark"
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-command"


def test_error_envelope() -> None:
    envelope = adapter.error("compile", adapter.Diagnostic("unreadable-case", "boom"))
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][0]["message"] == "boom"
