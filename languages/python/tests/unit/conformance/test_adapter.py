"""Conformance adapter core (`parallax.conformance.adapter`) tests."""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest import mock

import psycopg
import pytest

from parallax.conformance import _case_ingress, adapter, case_format, engine, models
from parallax.conformance._database_control import CaseDatabase
from parallax.conformance._lanes import scenario
from parallax.conformance._lanes.scenario import case_wire_preparer
from parallax.conformance._lifecycle_observation import LifecycleRun
from parallax.conformance._mechanism import model_facts
from parallax.conformance.claim import Claim
from parallax.conformance.profile import Profile, profile_for
from parallax.conformance.provision import Provisioner
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import (
    PreparedInstruction,
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
    WriteInstruction,
)
from parallax.core.internal.base import (
    INFINITY,
    UsageError,
)
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import DatabaseConnection, Row, TransactionOutcome
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.object_query import AsOf, object_query, validate_object_query
from parallax.core.internal.predicate import (
    And,
    Comparison,
    FieldSubject,
    Presence,
    Quantifier,
    ScalarLiteral,
)
from parallax.core.internal.predicate import serialize as serialize_predicate
from parallax.core.internal.temporal_read import TimeInterval
from parallax.core.internal.write_plan.managed_row import named_members
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_row
from tests._support.errors import raises_code
from tests._support.repo import canonical_snapshot_claim, validate_adapter_envelope
from tests.unit._second_dialect import BACKTICKED

# The declared profile these suites run under, read off the one roster rather than
# spelled as a label. Nothing here provisions it: each run is built over the port the
# test stands in for a database, and says so by naming the substitution.
_PROFILE = profile_for("pg-full")
_READ_CASE = case_format.default_cases_dir() / "m-predicate-002-eq.yaml"


# The case-format boundary canonicalizes synthetic managed carriers before strict
# Wire preparation. Corpus-authored values already use canonical Wire carriers;
# classification, validation, and retained ownership remain assertions about its
# PreparedInstruction result or the core producer's own exception.


def test_case_write_adapter_accepts_canonical_wire_and_managed_decimal_values() -> None:
    model = models.load_models()["account"]
    for value in ("5.00", decimal.Decimal("5.00")):
        instruction = instructions.KeyedWriteInstruction(
            "insert",
            "parallax.compatibility.Account",
            ({"id": 7, "owner": "Newton", "balance": value, "version": 1},),
        )
        prepared = _prepare_case_write(instruction, model)
        assert isinstance(prepared, PreparedKeyedInstruction)
        assert named_members(prepared.rows[0])["balance"] == decimal.Decimal("5.00")


def test_case_write_adapter_normalizes_managed_temporal_bounds() -> None:
    stated = dt.datetime(2024, 7, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    instruction = instructions.KeyedWriteInstruction(
        "amend",
        "parallax.compatibility.Position",
        ({"id": 1, "value": decimal.Decimal("5.00")},),
        valid_from=stated,
    )
    prepared = _prepare_case_write(instruction, models.load_models()["position"])
    assert isinstance(prepared, PreparedKeyedInstruction)
    assert prepared.valid_time_window == TimeInterval(
        dt.datetime(2024, 7, 1, tzinfo=dt.UTC), INFINITY
    )


def test_case_write_adapter_leaves_unknown_entities_for_core_classification() -> None:
    instruction = instructions.KeyedWriteInstruction("insert", "Missing", ({"id": 1},))
    with raises_code(UsageError, "write-instruction-invalid", match="declares no entity 'Missing'"):
        _prepare_case_write(instruction, models.load_models()["account"])


def test_case_write_adapter_normalizes_nested_value_object_documents() -> None:
    # The adapter hands the authored document to core unread, and core answers the
    # document its shape gives it: every declared leaf decoded into its managed
    # carrier at every depth, and a key no member declares taking no part — the same
    # canonical form the occurrence is stored in.
    instruction = instructions.KeyedWriteInstruction(
        "insert",
        "parallax.compatibility.Sample",
        (
            {
                "id": 1,
                "label": "sample",
                "profile": {
                    "amount": "12.50",
                    "origin": {"city": "Oslo", "since": "2026-01-01"},
                    "entries": [{"kind": "opening", "price": "2.25", "future": None}],
                    "future": {"opaque": True},
                },
            },
        ),
    )

    prepared = _prepare_case_write(instruction, models.load_models()["document-codec"])

    assert isinstance(prepared, PreparedKeyedInstruction)
    profile = cast("Mapping[str, object]", named_members(prepared.rows[0])["profile"])
    assert profile["amount"] == decimal.Decimal("12.50")
    assert cast("Mapping[str, object]", profile["origin"])["since"] == dt.date(2026, 1, 1)
    entries = cast("Sequence[Mapping[str, object]]", profile["entries"])
    assert entries[0]["price"] == decimal.Decimal("2.25")
    assert "future" not in entries[0]
    assert "future" not in profile


_SHIPMENT = models.accepted_model(
    {
        "entity": {
            "name": "Shipment",
            "namespace": "parallax.compatibility",
            "table": "shipment",
            "temporality": "bitemporal",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "amount", "type": "numeric(18,2)", "nullable": True},
                {"name": "shippedAt", "type": "timestamp", "nullable": True},
            ],
            "valueObjects": [
                {
                    "name": "window",
                    "nullable": True,
                    "attributes": [
                        {"name": "validEnd", "type": "timestamp", "nullable": True},
                        {"name": "txEnd", "type": "timestamp", "nullable": True},
                    ],
                }
            ],
        }
    }
)
_SHIPMENT_ENTITY = model_facts.case_entity(_SHIPMENT, "parallax.compatibility.Shipment")
_STORED_SHIPMENT: Mapping[str, object] = {
    "id": 1,
    "validStart": "2024-01-01T00:00:00.000000Z",
    "validEnd": "infinity",
    "txStart": "2024-01-01T00:00:00.000000Z",
    "txEnd": "infinity",
}


def test_case_row_decoding_takes_declared_axis_ends_to_the_managed_open_bound() -> None:
    decoded = _case_ingress.decode_case_row(
        {**_STORED_SHIPMENT, "txEnd": INFINITY}, _SHIPMENT, _SHIPMENT_ENTITY
    )
    assert decoded == {
        "id": 1,
        "validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "validEnd": INFINITY,
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": INFINITY,
    }
    assert decoded["validEnd"] is INFINITY


@pytest.mark.parametrize(
    "row",
    [
        {**_STORED_SHIPMENT, "nickname": "Ada"},
        {"id": 1, "validStart": "2024-01-01T00:00:00.000000Z", "nickname": "Ada"},
    ],
    ids=["whole-row", "address-only"],
)
def test_case_row_decoding_refuses_a_logical_member_the_family_does_not_declare(
    row: Mapping[str, object],
) -> None:
    # The row is the whole persisted state a later write carries forward, or
    # retires with nothing carried, so a name decoding would drop is refused
    # before any write sees the row.
    with pytest.raises(ValueError, match=r"names \['nickname'\]"):
        _case_ingress.decode_case_row(row, _SHIPMENT, _SHIPMENT_ENTITY)


def test_case_row_decoding_recognizes_the_axis_ends_a_concrete_subtype_inherits() -> None:
    rate = models.load_models()["rate"]
    decoded = _case_ingress.decode_case_row(
        {
            "id": 1,
            "amount": "2.50",
            "grade": "A",
            "validStart": "2024-01-01T00:00:00.000000Z",
            "validEnd": "infinity",
            "txStart": "2024-02-01T00:00:00.000000Z",
            "txEnd": "infinity",
        },
        rate,
        model_facts.case_entity(rate, "parallax.compatibility.DepositRate"),
    )
    assert (decoded["validEnd"], decoded["txEnd"]) == (INFINITY, INFINITY)
    assert decoded["amount"] == Decimal("2.50")


@pytest.mark.parametrize(
    ("row", "path"),
    [
        ({"shippedAt": "infinity"}, "parallax.compatibility.Shipment.shippedAt"),
        ({"window": {"validEnd": "infinity"}}, "parallax.compatibility.Shipment.window.validEnd"),
        ({"window": {"txEnd": INFINITY}}, "parallax.compatibility.Shipment.window.txEnd"),
    ],
    ids=["ordinary-timestamp", "nested-valid-end-lookalike", "nested-tx-end-lookalike"],
)
def test_case_row_decoding_keeps_every_other_timestamp_finite(
    row: Mapping[str, object], path: str
) -> None:
    # Only the declared axis-end definitions hold the open bound; a leaf merely
    # named or typed like one is an ordinary finite Timestamp.
    with raises_code(UsageError, "neutral-literal-type-mismatch") as caught:
        _case_ingress.decode_case_row({**_STORED_SHIPMENT, **row}, _SHIPMENT, _SHIPMENT_ENTITY)
    assert caught.value.args[1].startswith(f"{path}: ")


def test_case_row_decoding_takes_a_native_timestamp_to_utc_without_a_wire_spelling() -> None:
    stated = dt.datetime(2024, 7, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    decoded = _case_ingress.decode_case_row(
        {**_STORED_SHIPMENT, "shippedAt": stated, "window": {"validEnd": stated}},
        _SHIPMENT,
        _SHIPMENT_ENTITY,
    )
    utc = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    assert decoded["shippedAt"] == utc
    assert cast("dt.datetime", decoded["shippedAt"]).tzinfo is dt.UTC
    assert cast("Mapping[str, object]", decoded["window"])["validEnd"] == utc


def test_case_row_decoding_refuses_a_native_timestamp_naming_no_instant() -> None:
    with raises_code(UsageError, "neutral-literal-type-mismatch"):
        _case_ingress.decode_case_row(
            {**_STORED_SHIPMENT, "shippedAt": dt.datetime(2024, 7, 1)},
            _SHIPMENT,
            _SHIPMENT_ENTITY,
        )


def test_case_row_decoding_keeps_the_codec_canonicalization_of_other_native_values() -> None:
    # A native non-Timestamp scalar still takes its Wire encoding and decoding,
    # which canonicalizes what Typed coercion would not, such as Decimal scale.
    decoded = _case_ingress.decode_case_row(
        {**_STORED_SHIPMENT, "amount": decimal.Decimal("5.000")}, _SHIPMENT, _SHIPMENT_ENTITY
    )
    assert str(decoded["amount"]) == "5.00"


def test_case_query_adapter_preserves_unresolved_predicate_values_for_core_validation() -> None:
    model = models.load_models()["document-codec"]
    query = object_query(
        model.entities[0].identity,
        And(
            operands=(
                Comparison(op="eq", subject=FieldSubject("unqualified"), value="plain"),
                Comparison(op="eq", subject=FieldSubject("Missing.value"), value="unknown"),
                Comparison(op="eq", subject=FieldSubject("shallow"), value="plain"),
                Comparison(op="eq", subject=FieldSubject("Missing.doc.value"), value="unknown"),
                Comparison(
                    op="eq",
                    subject=FieldSubject("parallax.compatibility.Sample.label.deeper"),
                    value="unknown",
                ),
                Quantifier(
                    "any",
                    "parallax.compatibility.Sample.profile.entries",
                    Comparison(op="eq", subject=FieldSubject("missing.value"), value="unknown"),
                ),
                Quantifier("any", "unqualified"),
                Quantifier(
                    "any",
                    "Missing.doc.child",
                    Comparison(op="eq", subject=FieldSubject("value"), value="unknown"),
                ),
            )
        ),
    )

    normalized = _case_ingress.normalize_case_query(query, model)

    assert serialize_predicate(normalized.predicate) == serialize_predicate(query.predicate)


@pytest.mark.parametrize(
    ("scope", "predicate_node", "expected"),
    [
        (
            "parallax.compatibility.Coverage",
            Quantifier(
                "any",
                "parallax.compatibility.Coverage.claims",
                Comparison(
                    op="eq",
                    subject=FieldSubject("reserve"),
                    value=cast("ScalarLiteral", Decimal("12.50")),
                ),
            ),
            {
                "any": {
                    "path": "parallax.compatibility.Coverage.claims",
                    "where": {"eq": {"path": "reserve", "value": "12.50"}},
                }
            },
        ),
        (
            "parallax.compatibility.Claim",
            Presence(
                "exists",
                "parallax.compatibility.Claim.coverage",
                Comparison(
                    op="eq",
                    subject=FieldSubject("amount"),
                    value=cast("ScalarLiteral", Decimal("12.50")),
                ),
            ),
            {
                "exists": {
                    "path": "parallax.compatibility.Claim.coverage",
                    "where": {"eq": {"path": "amount", "value": "12.50"}},
                }
            },
        ),
    ],
    ids=["defining", "reverse"],
)
def test_case_query_adapter_normalizes_managed_decimals_through_relationship_directions(
    scope: str, predicate_node: Quantifier | Presence, expected: Mapping[str, object]
) -> None:
    model = models.load_models()["policy"]
    root = model_facts.case_entity(model, scope)
    query = object_query(
        root.identity,
        predicate_node,
        temporal={
            "transaction-time": AsOf("latest"),
            "valid-time": AsOf("2024-03-01T00:00:00.000000Z"),
        },
    )

    normalized = _case_ingress.normalize_case_query(query, model)

    assert serialize_predicate(normalized.predicate) == expected
    validate_object_query(root, normalized, model)


class _NeverCalledPort(ConnectsAsItself):
    """An `m-db-port` that fails loudly if a run ever touches it."""

    dialect: Dialect = POSTGRES

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        raise AssertionError("this run must not execute SQL")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError("this run must not execute SQL")

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        raise AssertionError("this run must not open a transaction")


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


def test_describe_matches_canonical_claim_except_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(psycopg.capabilities, "has_pipeline", lambda: True)
    envelope = adapter.describe()
    validate_adapter_envelope(envelope)
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
        ("inspect", "postgres", _case(), "unsupported-command"),
        ("compile", "mariadb", _case(), "unsupported-dialect"),
        ("compile", "postgres", _case(shape="unknown-shape"), "unsupported-case-shape"),
        (
            "compile",
            "postgres",
            _case(tags=("m-unclaimed", "slice-snapshot-1")),
            "unsupported-module",
        ),
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


def test_compile_case_unsupported_for_an_out_of_claim_dialect() -> None:
    envelope = adapter.compile_case(_READ_CASE, "mariadb")
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-dialect"


class _UnclaimedDialectPort(_NeverCalledPort):
    """A port declaring a dialect no profile runs the suite against."""

    dialect: Dialect = BACKTICKED


def test_run_case_unsupported_for_an_out_of_claim_dialect() -> None:
    # `run` is asked for a profile, never for a dialect, so the dialect the claim
    # filters on is the one the PORT will execute in — a run cannot be classified
    # against a spelling other than the one it would have produced.
    envelope = adapter.run_case(_READ_CASE, _PROFILE.on_stand_in(_UnclaimedDialectPort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-dialect"


def test_run_case_unsupported_for_an_ordered_transport_case_on_a_connection_holding_none() -> None:
    (case_path,) = case_format.default_cases_dir().glob("m-execution-lifecycle-014-*.yaml")
    envelope = adapter.run_case(case_path, _PROFILE.on_stand_in(_NeverCalledPort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-case-tag"


def test_run_case_unsupported_for_a_profile_the_roster_does_not_declare() -> None:
    # A run is constructed by a profile, but a `Profile` is constructible without
    # being declared, and any name satisfies the schema's `profileName` pattern. So
    # the roster is still what the contract refuses against, and it refuses before
    # the case is read or the port is touched.
    undeclared = Profile("invented-profile", Provisioner)
    envelope = adapter.run_case(_READ_CASE, undeclared.on_stand_in(_NeverCalledPort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "unsupported"
    assert envelope["diagnostics"][0]["code"] == "unsupported-profile"
    assert "invented-profile" in envelope["diagnostics"][0]["message"]


class _WritePort(ConnectsAsItself):
    """A port that commits writes and returns canned find rows (no Docker)."""

    dialect: Dialect = POSTGRES

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        return [
            projected_row(
                sql,
                {"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1},
                document_reads,
            )
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return 1

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        return body_outcome(self, body)


_SCENARIO_CASE = case_format.default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml"
_WRITE_SEQUENCE_CASE = case_format.default_cases_dir() / "m-unit-work-003-fk-insert-ordering.yaml"


def test_run_case_scenario_reports_database_calls_and_the_rows_its_read_step_published() -> None:
    # A scenario run routes through the write lane: its write step commits and its
    # find reads committed state. The envelope carries `databaseCalls` and one
    # `stepRows` entry (m-conformance-adapter) — at the READ step's own pointer,
    # never the write step's, and carrying the row the find published rather than
    # anything the write buffered.
    envelope = adapter.run_case(_SCENARIO_CASE, _PROFILE.on_stand_in(_WritePort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "databaseCalls": 2,
        "stepRows": [
            {
                "at": "/scenario/1",
                "rows": [{"id": 7, "owner": "Newton", "balance": "5.00", "version": 1}],
            }
        ],
    }
    assert [e["casePointer"] for e in envelope["emissions"]] == [
        "/scenario/0/write",
        "/scenario/1/objectQuery",
    ]


def test_run_case_write_sequence_reports_table_state_and_database_calls() -> None:
    # The write-sequence observation reads back every model table after commit
    # (m-conformance-adapter "write-sequence cases report tableState"); the fake
    # port answers every read with its canned row, so every orders-model table
    # reports it here — the run sweep grades real state against then.tableState.
    envelope = adapter.run_case(_WRITE_SEQUENCE_CASE, _PROFILE.on_stand_in(_WritePort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "tableState": {
            "px": {
                "orders": [
                    {
                        "id": 7,
                        "name": None,
                        "sku": None,
                        "qty": None,
                        "price": None,
                        "active": None,
                        "ordered_on": None,
                    }
                ],
                "order_item": [
                    {
                        "id": 7,
                        "order_id": None,
                        "sku": None,
                        "quantity": None,
                        "shipped_on": None,
                    }
                ],
                "order_note": [{"id": 7, "order_id": None, "body": None, "resolved_on": None}],
                "order_status": [{"id": 7, "order_id": None, "order_item_id": None, "code": None}],
                "order_tag": [{"id": 7, "order_id": None, "label": None, "priority": None}],
            },
        },
        "databaseCalls": 2,
    }
    assert [e["casePointer"] for e in envelope["emissions"]] == [
        "/writeSequence/0",
        "/writeSequence/1",
    ]


# --------------------------------------------------------------------------- #
# The api-conformance-lane scenario dispatch: an `expectError`-bearing scenario #
# stays in the compile/run lanes (the engine grades the raised application-    #
# lifecycle error through the `errors` observation); every other one is still  #
# lane-honestly classified out to the API Conformance Suite.                   #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Error-shape run — the m-db-error classification lane.                        #
# --------------------------------------------------------------------------- #
_ERROR_CASE = case_format.default_cases_dir() / "m-db-error-001-unique-violation-pk.yaml"
_ERROR_CONCURRENCY_CASE = case_format.default_cases_dir() / "m-db-error-004-deadlock-cycle.yaml"


class _TriggerPort(ConnectsAsItself):
    """A port whose Nth `execute_write` raises the scripted failure (no Docker)."""

    dialect: Dialect = POSTGRES

    def __init__(self, *, raise_on: int | None, failure: DatabaseError | None = None) -> None:
        self._raise_on = raise_on
        self._failure = failure
        self.writes = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:  # pragma: no cover
        raise NotImplementedError

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes += 1
        if self.writes == self._raise_on and self._failure is not None:
            raise self._failure
        return 1

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def _unique_violation() -> DatabaseError:
    return DatabaseError(category="uniqueViolation", native_code="23505", message="dup key")


def test_run_case_error_rejects_a_premature_raise() -> None:
    port = _TriggerPort(raise_on=1, failure=_unique_violation())
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE.on_stand_in(port))
    assert envelope["status"] == "error"
    assert "raised before the final statement" in envelope["diagnostics"][0]["message"]


def test_run_case_error_rejects_a_trigger_that_does_not_raise() -> None:
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE.on_stand_in(_TriggerPort(raise_on=None)))
    assert envelope["status"] == "error"
    assert "did not raise" in envelope["diagnostics"][0]["message"]


def test_run_case_error_rejects_an_unclassified_failure() -> None:
    unclassified = DatabaseError(category=None, native_code=None, message="connection torn down")
    port = _TriggerPort(raise_on=2, failure=unclassified)
    envelope = adapter.run_case(_ERROR_CASE, _PROFILE.on_stand_in(port))
    assert envelope["status"] == "error"
    assert "unclassified" in envelope["diagnostics"][0]["message"]


def test_run_case_error_concurrency_names_the_provider_lane() -> None:
    # A two-connection choreography cannot run on the single-connection adapter
    # port; the envelope classifies it to the provider contract proof.
    envelope = adapter.run_case(
        _ERROR_CONCURRENCY_CASE, _PROFILE.on_stand_in(_TriggerPort(raise_on=None))
    )
    assert envelope["status"] == "error"
    assert "provider contract proof" in envelope["diagnostics"][0]["message"]


# --------------------------------------------------------------------------- #
# Rejected — the pre-SQL model-aware validation lane.                         #
# --------------------------------------------------------------------------- #
_REJECTED_QUERY_CASE = (
    case_format.default_cases_dir() / "m-inheritance-040-rejected-narrow-outside-position.yaml"
)
_REJECTED_MODEL_CASE = (
    case_format.default_cases_dir() / "m-inheritance-020-rejected-unknown-parent.yaml"
)


def test_compile_case_rejected_shape_is_shape_intrinsic_run_only() -> None:
    # A rejected case carries no `compileEligibility` declaration (its
    # run-only status is shape-intrinsic, not authored per-case) yet still
    # answers the defined run-only envelope.
    envelope = adapter.compile_case(_REJECTED_QUERY_CASE, "postgres")
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "run-only"
    assert envelope["caseShape"] == "rejected"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"
    assert engine.eligibility(case_format.load_case(_REJECTED_QUERY_CASE)) is None


def test_run_case_rejected_query_reports_the_classified_rule() -> None:
    envelope = adapter.run_case(_REJECTED_QUERY_CASE, _PROFILE.on_stand_in(_NeverCalledPort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok"
    assert envelope["emissions"] == []
    assert envelope["observations"] == {
        "rejectedRule": "narrow-outside-position",
        "databaseCalls": 0,
    }


def test_run_case_rejected_model_reports_the_classified_rule() -> None:
    envelope = adapter.run_case(_REJECTED_MODEL_CASE, _PROFILE.on_stand_in(_NeverCalledPort()))
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok"
    assert envelope["observations"] == {
        "rejectedRule": "inheritance-unknown-parent",
        "databaseCalls": 0,
    }


# --------------------------------------------------------------------------- #
# Run-lane routing: an ordinary write is executed through its public verb.    #
# --------------------------------------------------------------------------- #
def test_run_case_lowers_a_pk_gen_sequence_batch_as_one_grouped_insert() -> None:
    # m-pk-gen-008: a reachable claimed writeSequence whose SECOND entry hands
    # out 2 of a reserved 3-id block. The engine buffers each row as its own
    # single-row insert (m-pk-gen), which the planner never collapses, and
    # execution inserts both rows of the distinct objects with one grouped
    # statement. The registry UPDATE's `{increment: 3}` marker folds into a
    # self-referential `next_val = next_val + ?` SET.
    case_path = case_format.default_cases_dir() / "m-pk-gen-008-sequence-batch-partial.yaml"
    with (
        mock.patch.object(
            scenario,
            "_lower_marker_unit",
            wraps=scenario._lower_marker_unit,  # pyright: ignore[reportPrivateUsage] - observe marker routing
        ) as marker,
        mock.patch.object(
            scenario,
            "_resolve_entries",
            side_effect=AssertionError("ordinary writes must not use compile resolution"),
        ) as compile_resolution,
    ):
        envelope = adapter.run_case(case_path, _PROFILE.on_stand_in(_WritePort()))
    assert envelope["status"] == "ok", envelope
    assert len(envelope["emissions"]) == 2, envelope["emissions"]
    marker.assert_called_once()
    compile_resolution.assert_not_called()


# --------------------------------------------------------------------------- #
# The lifecycle observation (m-conformance-adapter): a call index naming a    #
# statement other than the emission it indexes is an adapter defect.          #
# --------------------------------------------------------------------------- #
class _AccountPort(ConnectsAsItself):
    """Returns the one `account.yaml` row `m-execution-lifecycle-001` reads."""

    dialect: Dialect = POSTGRES

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        return [(3, "Grace", Decimal("10.00"), 1)]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


def test_a_lifecycle_index_naming_a_different_statement_is_an_adapter_error() -> None:
    # A call's index and the emission it names are built independently on the
    # grouped-write lanes, so an index that would name a DIFFERENT statement is
    # an ADAPTER defect rather than a case failure: it is reported as an error
    # envelope, never as an observation the runner would then go on to grade.
    real_run = adapter._run  # pyright: ignore[reportPrivateUsage] - the adapter's own dispatch

    def _drifted(
        case: case_format.Case, port: CaseDatabase, lifecycle: LifecycleRun
    ) -> tuple[list[engine.Emission], dict[str, Any]]:
        emissions, observations = real_run(case, port, lifecycle)
        drifted = [
            engine.Emission(e.case_pointer, dataclasses.replace(e.statement, sql="select 0"))
            for e in emissions
        ]
        return drifted, observations

    case_path = case_format.default_cases_dir() / "m-execution-lifecycle-001-standalone-read.yaml"
    with mock.patch.object(adapter, "_run", _drifted):
        envelope = adapter.run_case(case_path, _PROFILE.on_stand_in(_AccountPort()))
    assert envelope["status"] == "error", envelope
    assert "would name a different statement" in envelope["diagnostics"][0]["message"]


def _prepare_case_write(
    instruction: WriteInstruction, model: Metamodel
) -> PreparedInstruction | PreparedTargetInstruction:
    return _case_ingress.prepare_case_write(instruction, model, case_wire_preparer(model))


_LEDGER = models.accepted_model(
    {
        "entity": {
            "name": "Ledger",
            "namespace": "parallax.compatibility",
            "table": "ledger",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "tags", "type": "string", "multiplicity": "many"},
                {"name": "amounts", "type": "numeric(18,2)", "multiplicity": "many"},
            ],
            "valueObjects": [
                {
                    "name": "lines",
                    "multiplicity": "many",
                    "attributes": [
                        {"name": "sku", "type": "string"},
                        {"name": "price", "type": "numeric(18,2)", "nullable": True},
                    ],
                }
            ],
        }
    }
)
_LEDGER_ENTITY = model_facts.case_entity(_LEDGER, "parallax.compatibility.Ledger")


def test_case_row_decoding_keeps_stated_state_its_structure_refuses_as_stated() -> None:
    # Stated state is weighed by nothing: a member the plan refuses for its
    # structure is read where it can be, element by element, and kept as stated
    # where it cannot, while a stored DB-computed marker keeps its document.
    decoded = _case_ingress.decode_case_row(
        {
            "id": {"computed": "maxPlusOne"},
            "tags": "untagged",
            "lines": [{"sku": "a"}, "loose", {}],
        },
        _LEDGER,
        _LEDGER_ENTITY,
    )

    assert decoded == {
        "id": {"computed": "maxPlusOne"},
        "tags": "untagged",
        "lines": ({"sku": "a"}, "loose", {}),
    }


def test_case_row_decoding_reads_each_element_of_a_collection_its_structure_refuses() -> None:
    decoded = _case_ingress.decode_case_row(
        {
            "id": 1,
            "amounts": [None, "1.00"],
            "lines": ({"sku": "a", "price": "2.50"}, "loose"),
        },
        _LEDGER,
        _LEDGER_ENTITY,
    )

    assert decoded == {
        "id": 1,
        "amounts": (None, Decimal("1.00")),
        "lines": ({"sku": "a", "price": Decimal("2.50")}, "loose"),
    }


@pytest.mark.parametrize(
    ("row", "path"),
    [
        ({"amounts": [None, "bad"]}, "parallax.compatibility.Ledger.amounts[1]"),
        (
            {"lines": ("loose", {"sku": "a", "price": "bad"})},
            "parallax.compatibility.Ledger.lines[1].price",
        ),
    ],
    ids=["scalar-collection", "occurrence-collection"],
)
def test_case_row_decoding_refuses_a_literal_beside_a_structural_refusal(
    row: Mapping[str, object], path: str
) -> None:
    with raises_code(UsageError, "neutral-literal-type-mismatch") as caught:
        _case_ingress.decode_case_row({"id": 1, **row}, _LEDGER, _LEDGER_ENTITY)

    assert caught.value.args[1].startswith(f"{path}: ")
