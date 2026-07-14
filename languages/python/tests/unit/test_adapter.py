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
from parallax.core.db_error import DatabaseError
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


def test_run_case_write_sequence_reports_table_state_and_round_trips() -> None:
    # The write-sequence observation reads back every model table after commit
    # (m-conformance-adapter "write-sequence cases report tableState"); the fake
    # port answers every read with its canned row, so both orders-model tables
    # report it here — the run sweep grades real state against then.tableState.
    envelope = adapter.run_case(_WRITE_SEQUENCE_CASE, "postgres", _WritePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "tableState": {
            "orders": [{"id": 7}],
            "order_item": [{"id": 7}],
            "order_status": [{"id": 7}],
            "order_tag": [{"id": 7}],
        },
        "roundTrips": 2,
    }
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


# --------------------------------------------------------------------------- #
# Error-shape run — the m-db-error classification lane (increment 4).          #
# --------------------------------------------------------------------------- #
_ERROR_CASE = case_format.default_cases_dir() / "m-db-error-001-unique-violation-pk.yaml"
_ERROR_CONCURRENCY_CASE = case_format.default_cases_dir() / "m-db-error-004-deadlock-cycle.yaml"
_BOUNDARY_CASE = (
    case_format.default_cases_dir() / "m-unit-work-004-callback-value-withheld-on-abort.yaml"
)


class _TriggerPort:
    """A port whose Nth `execute_write` raises the scripted failure (no Docker)."""

    def __init__(self, *, raise_on: int | None, failure: DatabaseError | None = None) -> None:
        self._raise_on = raise_on
        self._failure = failure
        self.writes = 0

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:  # pragma: no cover
        raise NotImplementedError

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes += 1
        if self.writes == self._raise_on and self._failure is not None:
            raise self._failure
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)


def _unique_violation() -> DatabaseError:
    return DatabaseError(category="uniqueViolation", native_code="23505", message="dup key")


def test_run_case_error_reports_the_classification() -> None:
    # The final trigger statement raises; the envelope reports the neutral
    # category + preserved native code (the schema amendment this increment adds).
    port = _TriggerPort(raise_on=2, failure=_unique_violation())
    envelope = adapter.run_case(_ERROR_CASE, "postgres", port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "errorClass": "uniqueViolation",
        "nativeCode": "23505",
        "roundTrips": 2,
    }
    assert [e["casePointer"] for e in envelope["emissions"]] == [
        "/then/statements/0",
        "/then/statements/1",
    ]


def test_run_case_error_rejects_a_premature_raise() -> None:
    port = _TriggerPort(raise_on=1, failure=_unique_violation())
    envelope = adapter.run_case(_ERROR_CASE, "postgres", port)
    assert envelope["status"] == "error"
    assert "raised before the final statement" in envelope["diagnostics"][0]["message"]


def test_run_case_error_rejects_a_trigger_that_does_not_raise() -> None:
    envelope = adapter.run_case(_ERROR_CASE, "postgres", _TriggerPort(raise_on=None))
    assert envelope["status"] == "error"
    assert "did not raise" in envelope["diagnostics"][0]["message"]


def test_run_case_error_rejects_an_unclassified_failure() -> None:
    unclassified = DatabaseError(category=None, native_code=None, message="connection torn down")
    port = _TriggerPort(raise_on=2, failure=unclassified)
    envelope = adapter.run_case(_ERROR_CASE, "postgres", port)
    assert envelope["status"] == "error"
    assert "unclassified" in envelope["diagnostics"][0]["message"]


def test_run_case_error_concurrency_names_the_provider_lane() -> None:
    # A two-connection choreography cannot run on the single-connection adapter
    # port; the envelope classifies it to the provider contract proof.
    envelope = adapter.run_case(_ERROR_CONCURRENCY_CASE, "postgres", _TriggerPort(raise_on=None))
    assert envelope["status"] == "error"
    assert "provider contract proof" in envelope["diagnostics"][0]["message"]


def test_compile_case_error_shape_names_the_run_lane() -> None:
    envelope = adapter.compile_case(_ERROR_CASE, "postgres")
    assert envelope["status"] == "error"
    assert "authored, not compiled" in envelope["diagnostics"][0]["message"]


def test_boundary_case_names_the_api_conformance_lane() -> None:
    # m-case-format: every boundary case is on the api-conformance lane — the
    # API Conformance Suite verifies it. Compile short-circuits on the case's
    # corpus-declared run-only eligibility (every boundary case carries one,
    # D-10); run classifies it out with the api-conformance reason.
    compile_envelope = adapter.compile_case(_BOUNDARY_CASE, "postgres")
    assert compile_envelope["status"] == "run-only"
    assert compile_envelope["diagnostics"][0]["code"] == "compile-run-only"
    run_envelope = adapter.run_case(_BOUNDARY_CASE, "postgres", _TriggerPort(raise_on=None))
    assert run_envelope["status"] == "error"
    assert "api-conformance" in run_envelope["diagnostics"][0]["message"]


def test_run_case_refuses_unsupported_write_forms_before_execution() -> None:
    # m-pk-gen-008: a reachable claimed writeSequence whose rows carry a DB-computed
    # marker ({increment: 3}) and a multi-row insert. The backbone review caught the
    # shipped run binding the marker literally and dropping the second row (a false
    # ok on a permissive port; an uncaught driver error on a real one). The lowering
    # now refuses BEFORE execution: an `error` envelope naming the deferral, and the
    # port never sees a statement.
    case_path = case_format.default_cases_dir() / "m-pk-gen-008-sequence-batch-partial.yaml"
    port = _TriggerPort(raise_on=None)
    envelope = adapter.run_case(case_path, "postgres", port)
    assert envelope["status"] == "error"
    # The refusal names its landing phase explicitly (forward-error posture).
    assert "COR-3 Phase 8; m-pk-gen" in envelope["diagnostics"][0]["message"]
    assert port.writes == 0  # refused pre-execution — nothing reached the port
