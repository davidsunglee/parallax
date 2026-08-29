"""Conformance adapter core (`parallax.conformance.adapter`) tests."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import mock

import jsonschema
import pytest
from _second_dialect import BACKTICKED

from _support.db_port import body_outcome
from _support.repo import adapter_schema, canonical_snapshot_claim
from parallax.conformance import adapter, case_format, engine
from parallax.conformance._lifecycle_observation import LifecycleRun
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim
from parallax.core.base import PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect

_SCHEMA = adapter_schema()
# The declared profile a `run` reports; these suites hand their own port, so the
# name is the reporting label under test rather than a lane that gets provisioned.
_PROFILE = "pg-full"
_READ_CASE = case_format.default_cases_dir() / "m-predicate-002-eq.yaml"
_VO_READ_CASE = case_format.default_cases_dir() / "m-value-object-001-nested-eq.yaml"
_SCALAR_READ_CASE = case_format.default_cases_dir() / "m-core-001-scalar-types-roundtrip.yaml"
_RUN_ONLY_CASE = (
    case_format.default_cases_dir() / "m-txtime-write-006-optimistic-gated-chaining-update.yaml"
)
# A materializing predicate-write scenario; against `_FakePort` — a wrong-shaped
# canned row and a write path that always raises — it still surfaces a loud
# `run-failed` error, exercising this lane's own error-reporting contract.
_ENGINE_GAP_CASE = (
    case_format.default_cases_dir() / "m-txtime-write-007-predicate-terminate-materialize.yaml"
)


class _FakePort:
    """An in-memory ``m-db-port`` returning canned rows (no Docker)."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return [{"id": 1, "name": "Ada"}]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def _case(
    *,
    shape: str = "read",
    tags: tuple[str, ...] = ("m-predicate", "slice-snapshot-1"),
) -> case_format.Case:
    return case_format.Case(
        path=Path("m-predicate-001-x.yaml"),
        case_id="m-predicate-001",
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
        ("compile", "postgres", _case(tags=("m-predicate",)), "unsupported-case-tag"),
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
        modules=("m-predicate",),
        case_shapes=("read",),
        include=("slice-snapshot-1",),
        exclude=("aggregation",),
        commands=("compile",),
        provisioning="self-managed",
    )
    case = _case(tags=("m-predicate", "slice-snapshot-1", "aggregation"))
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
    assert envelope["emissions"][0]["casePointer"] == "/objectQuery"


def test_compile_case_unsupported_for_an_out_of_claim_dialect() -> None:
    envelope = adapter.compile_case(_READ_CASE, "mariadb")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-dialect"


class _UnclaimedDialectPort(_FakePort):
    """A port declaring a dialect no profile runs the suite against."""

    dialect: Dialect = BACKTICKED


def test_run_case_unsupported_for_an_out_of_claim_dialect() -> None:
    # `run` is asked for a profile, never for a dialect, so the dialect the claim
    # filters on is the one the PORT will execute in — a run cannot be classified
    # against a spelling other than the one it would have produced.
    envelope = adapter.run_case(_READ_CASE, _PROFILE, _UnclaimedDialectPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-dialect"


def test_compile_case_run_only_for_a_declared_run_only_case() -> None:
    envelope = adapter.compile_case(_RUN_ONLY_CASE, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "run-only"
    assert envelope["caseShape"] == "conflict"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"


def test_compile_dispatch_refuses_a_conflict_case_missing_its_run_only_declaration() -> None:
    # Every reachable conflict case declares `compileEligibility: run-only`
    # (m-opt-lock's single-connection intent), so `compile_case` short-
    # circuits before `_compile` ever runs; a hypothetically mis-declared one
    # reaching the internal dispatch is refused loudly by its own conflict
    # branch, never silently falling through to the read compiler.
    case = _case(shape="conflict", tags=("m-opt-lock", "slice-snapshot-1"))
    with pytest.raises(engine.EngineError, match="always declared"):
        adapter._compile(case, "postgres")  # pyright: ignore[reportPrivateUsage] - unit test drives the adapter's private compile helper


def test_run_case_ok_through_a_fake_port() -> None:
    envelope = adapter.run_case(_VO_READ_CASE, _PROFILE, _FakePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    # The envelope answers two different questions: which adapter configuration
    # was asked for, and which spelling actually executed. The second is read off
    # the port rather than echoed back from the request.
    assert envelope["profile"] == _PROFILE
    assert envelope["dialect"] == "postgres"
    assert envelope["observations"]["rows"] == [{"id": 1, "name": "Ada"}]
    assert envelope["observations"]["roundTrips"] == 1


class _WritePort:
    """A port that commits writes and returns canned find rows (no Docker)."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return [{"id": 7}]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return body_outcome(self, body)


class _AccountWritePort(_WritePort):
    """``_WritePort`` answering the Account row a conflict attempt's source read
    resolves, which is the value its keyed write is addressed and licensed by."""

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return [{"id": 2, "owner": "Linus", "balance": decimal.Decimal("250.00"), "version": 1}]


def test_run_case_conflict_reports_affected_rows_and_table_state() -> None:
    # m-opt-lock's run-only conflict shape: the
    # adapter's own `run` dispatch wraps `engine.run_conflict_case`'s tuple
    # into the schema's one `affectedRows` observation slot, plus
    # `tableState` when the case authors it.
    case_path = case_format.default_cases_dir() / "m-opt-lock-006-success.yaml"
    envelope = adapter.run_case(case_path, _PROFILE, _AccountWritePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    assert envelope["observations"]["affectedRows"] == 1
    assert "account" in envelope["observations"]["tableState"]


_SCENARIO_CASE = case_format.default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml"
_WRITE_SEQUENCE_CASE = case_format.default_cases_dir() / "m-unit-work-003-fk-insert-ordering.yaml"


def test_run_case_scenario_reports_round_trips_and_the_rows_its_read_step_published() -> None:
    # A scenario run routes through the write lane: its write step commits and its
    # find reads committed state. The envelope carries `roundTrips` and one
    # `stepRows` entry (m-conformance-adapter) — at the READ step's own pointer,
    # never the write step's, and carrying the row the find published rather than
    # anything the write buffered.
    envelope = adapter.run_case(_SCENARIO_CASE, _PROFILE, _WritePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "roundTrips": 2,
        "stepRows": [{"at": "/scenario/1", "rows": [{"id": 7}]}],
    }
    assert [e["casePointer"] for e in envelope["emissions"]] == [
        "/scenario/0/write",
        "/scenario/1/objectQuery",
    ]


def test_run_case_write_sequence_reports_table_state_and_round_trips() -> None:
    # The write-sequence observation reads back every model table after commit
    # (m-conformance-adapter "write-sequence cases report tableState"); the fake
    # port answers every read with its canned row, so every orders-model table
    # reports it here — the run sweep grades real state against then.tableState.
    envelope = adapter.run_case(_WRITE_SEQUENCE_CASE, _PROFILE, _WritePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "tableState": {
            "orders": [{"id": 7}],
            "order_item": [{"id": 7}],
            "order_note": [{"id": 7}],
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

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
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

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_run_observations_are_wire_rendered_and_json_serializable() -> None:
    # The adapter returns MANAGED values (Decimal / time / UUID / date / bytes);
    # the conformance boundary renders them to canonical wire form so the run
    # envelope is JSON-serializable (m-core-001 previously broke `json.dumps`).
    envelope = adapter.run_case(_SCALAR_READ_CASE, _PROFILE, _ManagedPort())
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
    # `_ENGINE_GAP_CASE` (m-txtime-write-007) is a materializing predicate-write
    # scenario: its `_FakePort` returns a canned
    # row shaped for a DIFFERENT model and raises `NotImplementedError` on any
    # write, so materialization's own internal resolve/write sequence fails —
    # this lane still reports a loud `run-failed` error rather than silently
    # mishandling it (a real port drives this case successfully, `test_run_
    # sweep.py::test_write_run_sweep`, Docker-gated).
    envelope = adapter.run_case(_ENGINE_GAP_CASE, _PROFILE, _FakePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][0]["code"] == "run-failed"


# --------------------------------------------------------------------------- #
# The api-conformance-lane scenario dispatch: an `expectError`-bearing scenario #
# stays in the compile/run lanes (the engine grades the raised application-    #
# lifecycle error through the `errors` observation); every other one is still  #
# lane-honestly classified out to the API Conformance Suite.                   #
# --------------------------------------------------------------------------- #
_PIN_READ_ONLY_CASE = (
    case_format.default_cases_dir() / "m-bitemp-write-016-transaction-time-pin-read-only.yaml"
)
_ACCESS_WITNESS_CASE = (
    case_format.default_cases_dir() / "m-snapshot-read-009-closed-world-unloaded-access.yaml"
)


class _PositionPort:
    """A port returning the superseded position milestone the pin-read-only
    contrast's find step selects (no Docker)."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return [
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("90.00"),
                "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
                "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
            }
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_run_case_grades_a_scenario_expect_error_through_the_errors_observation() -> None:
    envelope = adapter.run_case(_PIN_READ_ONLY_CASE, _PROFILE, _PositionPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    assert envelope["observations"]["roundTrips"] == 1
    assert envelope["observations"]["errors"] == [
        {"at": "/scenario/1", "errorClass": "transaction-time-pin-read-only"}
    ]


def test_compile_case_compiles_an_expect_error_scenarios_find_steps() -> None:
    envelope = adapter.compile_case(_PIN_READ_ONLY_CASE, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    assert envelope["roundTrips"] == 1
    assert [e["casePointer"] for e in envelope["emissions"]] == ["/scenario/0/objectQuery"]


_TX_PAST_READ_ONLY_CASE = (
    case_format.default_cases_dir() / "m-identity-map-010-transaction-time-past-is-read-only.yaml"
)
# A test-only claim admitting exactly the managed-lifecycle pin case above:
# `spec/python.md` defers the managed-object lifecycle, so the public
# `SNAPSHOT_CLAIM` never claims `m-identity-map` or the `slice-managed-1`
# tag — grading this case through the real run path needs a claim scoped to
# the case's own routing (its module tags, shape, and slice tag).
_TX_PAST_READ_ONLY_CLAIM = Claim(
    modules=("m-identity-map", "m-temporal-read"),
    case_shapes=("scenario",),
    include=("slice-managed-1",),
    exclude=(),
    commands=("run",),
    provisioning="self-managed",
)


class _BalancePort:
    """A port returning the superseded balance milestone the finite
    Transaction-Time pin selects (no Docker)."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return [
            {
                "bal_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("100.00"),
                "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "out_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            }
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_run_case_grades_the_managed_pin_case_end_to_end_under_a_scoped_claim() -> None:
    # The managed-lifecycle read-only-pin case (m-identity-map / m-temporal-
    # read's finite-pin mutation row) runs END-TO-END through the real
    # adapter/engine path: the pinned find materializes through the port, and
    # the mutate step's `expectError: transaction-time-pin-read-only` is
    # GRADED through the `errorObservation.errorClass` contract
    # (`m-conformance-adapter`), not schema-validated only. The `errors`
    # assertion fails if the run lane ever stops reporting the observation;
    # the write-raising port and the single find emission prove the refused
    # mutation emitted no DML.
    envelope = adapter.run_case(
        _TX_PAST_READ_ONLY_CASE, _PROFILE, _BalancePort(), claim=_TX_PAST_READ_ONLY_CLAIM
    )
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    assert [e["casePointer"] for e in envelope["emissions"]] == ["/scenario/0/objectQuery"]
    assert envelope["observations"]["roundTrips"] == 1
    assert envelope["observations"]["errors"] == [
        {"at": "/scenario/1", "errorClass": "transaction-time-pin-read-only"}
    ]


def test_the_public_snapshot_claim_still_classifies_the_managed_pin_case_out() -> None:
    # Under the public claim the same case stays `unsupported` (first failed
    # filter: its `m-identity-map` module tag) — the deferred managed
    # lifecycle is graded only through the scoped test claim above, never by
    # widening `SNAPSHOT_CLAIM`.
    envelope = adapter.run_case(_TX_PAST_READ_ONLY_CASE, _PROFILE, _BalancePort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-module"


def test_scenario_lane_without_expect_error_is_still_dispatched_out() -> None:
    compile_envelope = adapter.compile_case(_ACCESS_WITNESS_CASE, "postgres")
    assert compile_envelope["status"] == "error"
    assert "api-conformance" in compile_envelope["diagnostics"][0]["message"]
    run_envelope = adapter.run_case(_ACCESS_WITNESS_CASE, _PROFILE, _NeverCalledPort())
    assert run_envelope["status"] == "error"
    assert "api-conformance" in run_envelope["diagnostics"][0]["message"]


def test_scenario_actions_all_mutate_guards_malformed_and_action_free_documents() -> None:
    def scenario_case(document: dict[str, object]) -> case_format.Case:
        return case_format.Case(
            path=Path("m-predicate-001-x.yaml"),
            case_id="m-predicate-001",
            shape="scenario",
            tags=("m-predicate", "slice-snapshot-1"),
            model="models/orders.yaml",
            document=document,
        )

    checks: list[tuple[dict[str, object], bool]] = [
        ({}, False),  # no `when` at all
        ({"when": {"scenario": "not-a-list"}}, False),
        # No lifecycle action step at all: nothing for the mutate lane to
        # grade, so the ordinary api-conformance dispatch still applies.
        ({"when": {"scenario": [{"objectQuery": {"target": "Order"}}]}}, False),
        ({"when": {"scenario": [{"action": "mutate"}, {"action": "access"}]}}, False),
        ({"when": {"scenario": [{"action": "mutate", "on": 0}]}}, True),
    ]
    for document, expected in checks:
        observed = adapter._scenario_actions_all_mutate(  # pyright: ignore[reportPrivateUsage] - unit test drives the adapter's private scenario helper
            scenario_case(document)
        )
        assert observed is expected, document


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
# Error-shape run — the m-db-error classification lane.                        #
# --------------------------------------------------------------------------- #
_ERROR_CASE = case_format.default_cases_dir() / "m-db-error-001-unique-violation-pk.yaml"
_ERROR_CONCURRENCY_CASE = case_format.default_cases_dir() / "m-db-error-004-deadlock-cycle.yaml"
_BOUNDARY_CASE = (
    case_format.default_cases_dir() / "m-unit-work-004-callback-value-withheld-on-abort.yaml"
)


class _TriggerPort:
    """A port whose Nth `execute_write` raises the scripted failure (no Docker)."""

    dialect: Dialect = POSTGRES

    def __init__(self, *, raise_on: int | None, failure: DatabaseError | None = None) -> None:
        self._raise_on = raise_on
        self._failure = failure
        self.writes = 0

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:  # pragma: no cover
        raise NotImplementedError

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes += 1
        if self.writes == self._raise_on and self._failure is not None:
            raise self._failure
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def _unique_violation() -> DatabaseError:
    return DatabaseError(category="uniqueViolation", native_code="23505", message="dup key")


def test_run_case_error_reports_the_classification() -> None:
    # The final trigger statement raises; the envelope reports the neutral
    # category + preserved native code (the schema amendment this increment adds).
    port = _TriggerPort(raise_on=2, failure=_unique_violation())
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE, port)
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
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE, port)
    assert envelope["status"] == "error"
    assert "raised before the final statement" in envelope["diagnostics"][0]["message"]


def test_run_case_error_rejects_a_trigger_that_does_not_raise() -> None:
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE, _TriggerPort(raise_on=None))
    assert envelope["status"] == "error"
    assert "did not raise" in envelope["diagnostics"][0]["message"]


def test_run_case_error_rejects_an_unclassified_failure() -> None:
    unclassified = DatabaseError(category=None, native_code=None, message="connection torn down")
    port = _TriggerPort(raise_on=2, failure=unclassified)
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE, port)
    assert envelope["status"] == "error"
    assert "unclassified" in envelope["diagnostics"][0]["message"]


def test_run_case_error_concurrency_names_the_provider_lane() -> None:
    # A two-connection choreography cannot run on the single-connection adapter
    # port; the envelope classifies it to the provider contract proof.
    envelope = adapter.run_case(_ERROR_CONCURRENCY_CASE, _PROFILE, _TriggerPort(raise_on=None))
    assert envelope["status"] == "error"
    assert "provider contract proof" in envelope["diagnostics"][0]["message"]


def test_compile_case_error_shape_names_the_run_lane() -> None:
    envelope = adapter.compile_case(_ERROR_CASE, "postgres")
    assert envelope["status"] == "error"
    assert "authored, not compiled" in envelope["diagnostics"][0]["message"]


def test_boundary_case_names_the_api_conformance_lane() -> None:
    # m-case-format: every boundary case is on the api-conformance lane — the
    # API Conformance Suite verifies it. Compile short-circuits on the case's
    # corpus-declared run-only eligibility (every boundary case carries one);
    # run classifies it out with the api-conformance reason.
    compile_envelope = adapter.compile_case(_BOUNDARY_CASE, "postgres")
    assert compile_envelope["status"] == "run-only"
    assert compile_envelope["diagnostics"][0]["code"] == "compile-run-only"
    run_envelope = adapter.run_case(_BOUNDARY_CASE, _PROFILE, _TriggerPort(raise_on=None))
    assert run_envelope["status"] == "error"
    assert "api-conformance" in run_envelope["diagnostics"][0]["message"]


# --------------------------------------------------------------------------- #
# Rejected — the pre-SQL model-aware validation lane.                         #
# --------------------------------------------------------------------------- #
_REJECTED_QUERY_CASE = (
    case_format.default_cases_dir() / "m-inheritance-040-rejected-narrow-outside-position.yaml"
)
_REJECTED_MODEL_CASE = (
    case_format.default_cases_dir() / "m-inheritance-020-rejected-unknown-parent.yaml"
)
_REJECTED_WRITE_CASE = (
    case_format.default_cases_dir()
    / "m-value-object-039-rejected-write-required-attribute-depth-1.yaml"
)


class _NeverCalledPort:
    """An `m-db-port` that fails loudly if a rejected run ever touches it."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        raise AssertionError("a rejected-case run must not execute SQL")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError("a rejected-case run must not execute SQL")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise AssertionError("a rejected-case run must not open a transaction")


def test_compile_case_rejected_shape_is_shape_intrinsic_run_only() -> None:
    # A rejected case carries no `compileEligibility` declaration (its
    # run-only status is shape-intrinsic, not authored per-case) yet still
    # answers the defined run-only envelope.
    envelope = adapter.compile_case(_REJECTED_QUERY_CASE, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "run-only"
    assert envelope["caseShape"] == "rejected"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"
    assert engine.eligibility(case_format.load_case(_REJECTED_QUERY_CASE)) is None


def test_run_case_rejected_query_reports_the_classified_rule() -> None:
    envelope = adapter.run_case(_REJECTED_QUERY_CASE, _PROFILE, _NeverCalledPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["emissions"] == []
    assert envelope["observations"] == {
        "rejectedRule": "narrow-outside-position",
        "roundTrips": 0,
    }


def test_run_case_rejected_model_reports_the_classified_rule() -> None:
    envelope = adapter.run_case(_REJECTED_MODEL_CASE, _PROFILE, _NeverCalledPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "rejectedRule": "inheritance-unknown-parent",
        "roundTrips": 0,
    }


def test_run_case_rejected_write_reports_the_classified_rule() -> None:
    envelope = adapter.run_case(_REJECTED_WRITE_CASE, _PROFILE, _NeverCalledPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["emissions"] == []
    assert envelope["observations"] == {
        "rejectedRule": "write-required-attribute-missing",
        "roundTrips": 0,
    }


# --------------------------------------------------------------------------- #
# Read-result dispatch (`_read_observations`): `then.graph` / `then.graphs` /  #
# `then.rows` are mutually exclusive, so `run_case` must route each read case  #
# to its own rendering lane, not just the plain-rows fallback.                 #
# --------------------------------------------------------------------------- #
class _QueuePort:
    """A fake `m-db-port` returning one canned response per `execute()` call,
    in call order (the per-level find executor issues more than one query)."""

    dialect: Dialect = POSTGRES

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return self._responses.pop(0)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise NotImplementedError


_GRAPH_CASE = case_format.default_cases_dir() / "m-snapshot-read-011-back-reference-cycle.yaml"
_GRAPHS_CASE = (
    case_format.default_cases_dir() / "m-snapshot-read-013-history-edge-pinned-graphs.yaml"
)


def test_run_case_graph_observation_reports_the_assembled_graph() -> None:
    # `then.graph` (a snapshot graph, not a bare rows list) routes through
    # `run_graph_case`; the envelope carries `graph` and `roundTrips`, and — for
    # a conforming read — no `storedDataIssues` entry at all.
    port = _QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A-100",
                    "qty": 5,
                    "price": decimal.Decimal("10.50"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 5),
                }
            ],
            [
                {
                    "id": 12,
                    "order_id": 1,
                    "sku": "B-200",
                    "quantity": 1,
                    "shipped_on": dt.date(2024, 2, 15),
                },
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
        ]
    )
    envelope = adapter.run_case(_GRAPH_CASE, _PROFILE, port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"]["roundTrips"] == 2
    assert envelope["observations"]["graph"]["Order"][0]["id"] == 1
    assert "storedDataIssues" not in envelope["observations"]
    # The whole envelope round-trips through the wire (json.dumps).
    assert json.loads(json.dumps(envelope)) == envelope


_GRAPH_CASE_CONFORMING = case_format.default_cases_dir() / "m-snapshot-read-003-null-to-one.yaml"
_GRAPH_CASE_CLASSIFIED = (
    case_format.default_cases_dir()
    / "m-storage-layout-027-classified-read-layout-twin-columns.yaml"
)


def test_run_case_graph_observation_reports_the_positions_a_read_classified() -> None:
    # The optional `storedDataIssues` observation's present branch: a read whose
    # stored state contradicted the model reports one entry per invalid position
    # beside the graph, and the whole envelope still round-trips through the wire.
    port = _QueuePort(
        [
            [{"id": 1, "profile": PresentDocument({"city": "Oslo"})}],
            [],
        ]
    )
    envelope = adapter.run_case(_GRAPH_CASE_CLASSIFIED, _PROFILE, port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    (record,) = envelope["observations"]["storedDataIssues"]
    assert record["ordinal"] == 0
    assert record["hydrated"] is True
    assert json.loads(json.dumps(envelope)) == envelope


def test_run_case_graph_observation_omits_classification_when_every_position_conformed() -> None:
    # A `then.graph` case whose read publishes no record carries no such key at
    # all in the envelope (the OTHER branch of `_read_observations`' optional
    # `storedDataIssues`).
    port = _QueuePort(
        [
            [
                {"id": 101, "order_id": 1, "order_item_id": None, "code": "NEW"},
                {
                    "id": 201,
                    "order_id": 1,
                    "order_item_id": 11,
                    "code": "PICKED",
                },
            ],
            [
                {
                    "id": 11,
                    "order_id": 1,
                    "sku": "A-100",
                    "quantity": 2,
                    "shipped_on": None,
                }
            ],
        ]
    )
    envelope = adapter.run_case(_GRAPH_CASE_CONFORMING, _PROFILE, port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert "storedDataIssues" not in envelope["observations"]
    assert json.loads(json.dumps(envelope)) == envelope


_STREAM_CASE = (
    case_format.default_cases_dir() / "m-snapshot-read-029-page-invariance-batch-size-twin-2.yaml"
)


def _order(identifier: int, name: str) -> dict[str, object]:
    return {
        "id": identifier,
        "name": name,
        "sku": "A-100",
        "qty": 5,
        "price": decimal.Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def test_run_case_streamed_observation_reports_the_delivered_roots() -> None:
    # `when.stream` routes ahead of the result member, through `run_stream_case`
    # and the shipped streamed read — three pages at `batchSize: 2` over four
    # roots, the third returning nothing because a full final page proves no
    # exhaustion. The envelope carries the delivered graph, the round trips the
    # delivery cost, and one emission per page: a Snapshot Stream publishes a
    # Stream Batch per page and that page's Database Calls under it, so the
    # statements come off the delivered lifecycle exactly as every other lane's
    # do. The seek is what shows they are the DELIVERY's rather than an eager
    # read's — page 2 continues from the id page 1 delivered last.
    port = _QueuePort(
        [
            [_order(1, "Ada"), _order(2, "Linus")],
            [_order(3, "ada"), _order(42, "Grace")],
            [],
        ]
    )
    envelope = adapter.run_case(_STREAM_CASE, _PROFILE, port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert [emission["binds"] for emission in envelope["emissions"]] == [
        [1, 2, 3, 42, 2],
        [1, 2, 3, 42, 2, 2],
        [1, 2, 3, 42, 42, 2],
    ]
    assert envelope["observations"]["roundTrips"] == 3
    assert [root["id"] for root in envelope["observations"]["graph"]["Order"]] == [1, 2, 3, 42]
    assert "storedDataIssues" not in envelope["observations"]
    assert json.loads(json.dumps(envelope)) == envelope


def test_run_case_graphs_observation_reports_ordered_milestone_pin_graphs() -> None:
    # `then.graphs` (a milestone-set snapshot read) routes through
    # `run_graphs_case`; the envelope's `observations["graphs"]` carries the
    # chronologically ordered per-milestone pin+graph entries.
    from parallax.core.base import INFINITY

    port = _QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": decimal.Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                    "out_z": INFINITY,
                },
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": decimal.Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                },
            ]
        ]
    )
    envelope = adapter.run_case(_GRAPHS_CASE, _PROFILE, port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok"
    assert envelope["observations"]["roundTrips"] == 1
    graphs = envelope["observations"]["graphs"]
    assert [g["pin"]["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00+00:00",
        "2024-04-01T00:00:00+00:00",
    ]
    assert json.loads(json.dumps(envelope)) == envelope


class _WriteAndReadBackPort:
    """A no-Docker port that accepts writes (never raising) and answers every
    read with ``rows`` — the resolving read a keyed write's source needs, and
    enough for a writeSequence case's trailing ``read_table_state`` call-back,
    which this test does not inspect.

    ``affected`` scripts the row count each successive write reports, defaulting
    to one. A batched keyed write expects every row its target addresses, so a
    collapsed statement that reported a single row would read as a shortfall.
    """

    dialect: Dialect = POSTGRES

    def __init__(self, affected: Sequence[int] = (), rows: Sequence[Row] = ()) -> None:
        self.writes = 0
        self._affected = list(affected)
        self._rows = list(rows)

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return list(self._rows)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes += 1
        return self._affected.pop(0) if self._affected else 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_run_case_runs_a_genuine_batch_collapse_write() -> None:
    # m-batch-write-001: a reachable claimed writeSequence whose FIRST entry
    # buffers three inserts collapsing into ONE multi-row INSERT (`statements:
    # 1` for 3 rows — the case author's own declared batch-COLLAPSE intent,
    # `m-batch-write` "Set-based flush") and whose SECOND entry batches a
    # uniform-value UPDATE over an `IN`-list: the
    # engine passes each row list through as one multi-row instruction, and
    # the lowering seam renders it end to end — two `execute_write` calls total,
    # reporting the three and two rows their targets respectively address.
    #
    # The canned rows are what the update entry's own resolving read publishes:
    # one membership read over the keys that entry addresses, which is what keeps
    # the collapse intact — a read between the two writes would flush the first
    # alone (`m-case-format` *Resolving reads a write owes*).
    case_path = case_format.default_cases_dir() / "m-batch-write-001-set-based-flush.yaml"
    port = _WriteAndReadBackPort(
        [3, 2],
        rows=[
            {"id": 10, "owner": "Mira", "balance": Decimal("100.00")},
            {"id": 11, "owner": "Omar", "balance": Decimal("20.00")},
        ],
    )
    envelope = adapter.run_case(case_path, _PROFILE, port)
    assert envelope["status"] == "ok", envelope
    assert envelope["observations"]["roundTrips"] == 3
    assert port.writes == 2


def test_run_case_lowers_a_pk_gen_sequence_batch_that_decomposes_per_row() -> None:
    # m-pk-gen-008: a reachable claimed writeSequence whose SECOND entry hands
    # out 2 of a reserved 3-id block — `statements: 2` for 2 rows (the case
    # author's own declared per-row DECOMPOSE intent, distinct from the
    # collapse-intent case above), so the engine splits it into two
    # independent single-row INSERTs (m-pk-gen)
    # rather than refusing. The registry UPDATE's `{increment: 3}` marker
    # folds into a self-referential `next_val = next_val + ?` SET.
    case_path = case_format.default_cases_dir() / "m-pk-gen-008-sequence-batch-partial.yaml"
    envelope = adapter.run_case(case_path, _PROFILE, _WritePort())
    assert envelope["status"] == "ok", envelope
    # The registry UPDATE + two independent Pass INSERTs (never one collapsed
    # multi-row INSERT — the id list is derived, not authored).
    assert len(envelope["emissions"]) == 3, envelope["emissions"]


# --------------------------------------------------------------------------- #
# The lifecycle observation (m-conformance-adapter): a run installs a Provider #
# and reports the stream it delivered, for a case that authors the oracle and  #
# for no other — a case asserting nothing about the stream is handed no        #
# observed key to explain.                                                     #
# --------------------------------------------------------------------------- #
class _AccountPort:
    """Returns the one `account.yaml` row `m-execution-lifecycle-001` reads."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return [{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_a_case_authoring_the_oracle_gets_the_stream_its_run_delivered() -> None:
    case_path = case_format.default_cases_dir() / "m-execution-lifecycle-001-standalone-read.yaml"
    envelope = adapter.run_case(case_path, _PROFILE, _AccountPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    assert envelope["observations"]["executionLifecycle"] == {
        "roots": [
            {
                "execution": 1,
                "kind": "read",
                "events": [
                    {
                        "sequence": 1,
                        "activity": 1,
                        "parent": None,
                        "readStarted": {
                            "target": "parallax.compatibility.Account",
                            "interface": "rows",
                        },
                    },
                    {
                        "sequence": 2,
                        "activity": 2,
                        "parent": 1,
                        "databaseCallStarted": {
                            "target": "parallax.compatibility.Account",
                            "kind": "read",
                            "statement": 0,
                        },
                    },
                    {
                        "sequence": 3,
                        "activity": 2,
                        "parent": 1,
                        "databaseCallFinished": {"outcome": "readCompleted", "returnedRows": 1},
                    },
                    {
                        "sequence": 4,
                        "activity": 1,
                        "parent": None,
                        "readFinished": {"outcome": "completed"},
                    },
                ],
            }
        ]
    }


def test_a_lifecycle_index_naming_a_different_statement_is_an_adapter_error() -> None:
    # A call's index and the emission it names are built independently on the
    # grouped-write lanes, so an index that would name a DIFFERENT statement is
    # an ADAPTER defect rather than a case failure: it is reported as an error
    # envelope, never as an observation the runner would then go on to grade.
    real_run = adapter._run  # pyright: ignore[reportPrivateUsage] - the adapter's own dispatch

    def _drifted(
        case: case_format.Case, port: DbPort, lifecycle: LifecycleRun
    ) -> tuple[list[engine.Emission], dict[str, Any]]:
        emissions, observations = real_run(case, port, lifecycle)
        drifted = [engine.Emission(e.case_pointer, "select 0", e.binds) for e in emissions]
        return drifted, observations

    case_path = case_format.default_cases_dir() / "m-execution-lifecycle-001-standalone-read.yaml"
    with mock.patch.object(adapter, "_run", _drifted):
        envelope = adapter.run_case(case_path, _PROFILE, _AccountPort())
    assert envelope["status"] == "error", envelope
    assert "would name a different statement" in envelope["diagnostics"][0]["message"]


def test_a_case_authoring_no_oracle_reports_no_lifecycle_observation() -> None:
    # The stream a run delivers is reported where a case asks for it and
    # nowhere else: an observed key a case left unasserted is one the corpus
    # comparator would have to be told to ignore.
    envelope = adapter.run_case(_VO_READ_CASE, _PROFILE, _FakePort())
    assert set(envelope["observations"]) == {"rows", "roundTrips"}


_INCLUDE_SCENARIO_CASE = (
    case_format.default_cases_dir() / "m-snapshot-read-016-edit-keeps-loaded-items.yaml"
)


class _OrderWithItemsPort:
    """A canned ``m-db-port`` answering the root level then the include level."""

    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self._responses: list[list[Row]] = [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A-100",
                    "qty": 5,
                    "price": Decimal("10.50"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 5),
                }
            ],
            [
                {
                    "id": 12,
                    "order_id": 1,
                    "sku": "B-200",
                    "quantity": 1,
                    "shipped_on": dt.date(2024, 2, 15),
                },
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
        ]

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return self._responses.pop(0)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_run_case_scenario_reports_a_step_graph_for_an_access_step() -> None:
    # The per-step graph channel (`m-conformance-adapter` *Per-step graph
    # observations*): an `access` step declaring `expectGraph` publishes one
    # `stepGraphs` entry at its own pointer, beside `roundTrips`, and the envelope
    # still validates against the adapter schema.
    envelope = adapter.run_case(_INCLUDE_SCENARIO_CASE, _PROFILE, _OrderWithItemsPort())
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    assert envelope["observations"]["roundTrips"] == 2
    step_graphs = envelope["observations"]["stepGraphs"]
    assert [entry["at"] for entry in step_graphs] == ["/scenario/2"]
    assert sorted(node["id"] for node in step_graphs[0]["graph"]["OrderItem"]) == [11, 12]
