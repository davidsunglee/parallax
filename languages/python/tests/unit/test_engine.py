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
from typing import cast

import pytest

from parallax.conformance import case_format, engine, sweep
from parallax.core.base import InstantError
from parallax.core.db_port import DbPort, Row

pytestmark = pytest.mark.unit


def _rows(row: Row, key: str) -> list[Row]:
    """A graph leaf's relationship-attached rows, typed for test-side assertions
    (`then.graph`'s wire shape is intentionally a plain ``dict[str, object]``)."""
    return cast("list[Row]", row[key])


def _entry(entry: dict[str, object], key: str) -> Row:
    """A milestone-set `{pin, graph}` entry's own member, typed for test-side
    assertions (`then.graphs`' wire shape is a plain ``dict[str, object]``)."""
    return cast("Row", entry[key])


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


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these engine-function-level tests
    # exercise `run_conflict_case` on its own terms, never gated on whether
    # the case has ALSO been flipped visible in the sweep.
    (case,) = [c for c in case_format.load_cases() if c.case_id == case_id]
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


def test_run_read_case_materializes_family_variant_from_the_tph_tag_column() -> None:
    # m-inheritance-003 (Payment root, table-per-hierarchy): the compiled SELECT
    # projects the raw `kind` tag column; run_read_case materializes `familyVariant`
    # from the tag metadata map at row construction and never leaves the raw tag key
    # on the wire row (m-case-format: an abstract-target row carries `familyVariant`,
    # never the framework-owned tag).
    port = FakeDbPort(
        [
            {
                "id": 1,
                "amount": decimal.Decimal("100.00"),
                "card_network": "Visa",
                "tendered": None,
                "kind": "card",
            }
        ]
    )
    _emissions, rows, _round_trips = engine.run_read_case(
        _case("m-inheritance-003"), "postgres", port
    )
    assert rows == [
        {
            "id": 1,
            "amount": "100.00",
            "card_network": "Visa",
            "tendered": None,
            "familyVariant": "CardPayment",
        }
    ]


def test_run_read_case_materializes_family_variant_from_the_tpcs_literal_column() -> None:
    # m-inheritance-050 (Document root, table-per-concrete-subtype): the compiled
    # union-all projects the `family_variant` literal per branch; run_read_case just
    # renames the wire key, no tag map involved.
    port = FakeDbPort(
        [
            {
                "id": 1,
                "title": "Invoice-A",
                "folder_id": 100,
                "currency": "USD",
                "amount_due": decimal.Decimal("120.00"),
                "body": None,
                "paid_amount": None,
                "family_variant": "Invoice",
            }
        ]
    )
    _emissions, rows, _round_trips = engine.run_read_case(
        _case("m-inheritance-050"), "postgres", port
    )
    assert rows[0]["familyVariant"] == "Invoice"
    assert "family_variant" not in rows[0]


def test_run_read_case_concrete_target_read_carries_no_family_variant() -> None:
    # m-inheritance-001 (CardPayment, concrete target): the compiled SELECT never
    # projects a tag/literal column, so the row passes through wire rendering alone.
    port = FakeDbPort([{"id": 1, "amount": decimal.Decimal("100.00"), "card_network": "Visa"}])
    _emissions, rows, _round_trips = engine.run_read_case(
        _case("m-inheritance-001"), "postgres", port
    )
    assert rows == [{"id": 1, "amount": "100.00", "card_network": "Visa"}]
    assert "familyVariant" not in rows[0]


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
    # The temporal open-upper-bound sentinel renders as the canonical `infinity`
    # literal (a temporal read's current-row `out_z` reads back as native infinity).
    from parallax.core.base import INFINITY

    assert engine.wire_value(INFINITY) == "infinity"
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


# --------------------------------------------------------------------------- #
# Scenario / writeSequence — the unit-of-work write lanes (Docker-free).       #
# --------------------------------------------------------------------------- #
class FakeWritePort:
    """An in-memory ``m-db-port`` recording DML + read execution and commit/rollback."""

    def __init__(self, find_rows: list[Row] | None = None) -> None:
        self.find_rows = find_rows if find_rows is not None else []
        self.writes: list[tuple[str, list[object]]] = []
        self.reads: list[tuple[str, list[object]]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self.reads.append((sql, list(binds)))
        return list(self.find_rows)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, list(binds)))
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        try:
            result = body(self)
        except Exception:
            self.rollbacks += 1
            raise
        self.commits += 1
        return result


def _synthetic_write(shape: str, document: dict[str, object]) -> case_format.Case:
    from pathlib import Path

    document.setdefault("model", "models/account.yaml")
    return case_format.Case(
        path=Path("m-unit-work-999-synthetic.yaml"),
        case_id="m-unit-work-999",
        shape=shape,
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )


def test_run_scenario_case_commits_writes_and_reads_committed_state() -> None:
    port = FakeWritePort(find_rows=[{"id": 7}])
    emissions, round_trips = engine.run_scenario_case(_case("m-unit-work-001"), "postgres", port)
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/write", "/scenario/1/find"]
    assert emissions[0].sql.startswith("insert into account")
    assert emissions[1].sql.endswith("for share of t0")  # the read-lock suffix renders
    assert len(port.writes) == 1 and len(port.reads) == 1
    assert port.commits == 1 and port.rollbacks == 0


def test_run_scenario_case_rollback_step_aborts_but_counts_the_round_trip() -> None:
    port = FakeWritePort(find_rows=[])
    emissions, round_trips = engine.run_scenario_case(_case("m-unit-work-011"), "postgres", port)
    assert round_trips == 2  # the aborted insert still counts one round trip
    assert len(port.writes) == 1  # the DML executed before the abort
    assert port.rollbacks == 1 and port.commits == 0
    assert emissions[0].case_pointer == "/scenario/0/write"


def test_run_write_sequence_case_executes_the_sequence_in_one_transaction() -> None:
    port = FakeWritePort()
    emissions, table_state, round_trips = engine.run_write_sequence_case(
        _case("m-unit-work-003"), "postgres", port
    )
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/writeSequence/0", "/writeSequence/1"]
    assert len(port.writes) == 2 and port.commits == 1
    # The committed table state is read back for every model table (the
    # m-conformance-adapter write-sequence observation); the read-back is an
    # observation, so it never counts toward the case's round trips.
    assert set(table_state) == {"orders", "order_item", "order_status", "order_tag"}


def test_compile_write_sequence_case_lowers_each_entry_without_cross_entry_coalescing() -> None:
    # m-unit-work-007 inserts then deletes the same rows across four entries; each entry is
    # its own flush, so it emits FOUR statements (never coalesced to a net-zero cancel).
    emissions, round_trips = engine.compile_write_sequence_case(
        _case("m-unit-work-007"), "postgres"
    )
    assert round_trips == 4
    assert [e.case_pointer for e in emissions] == [f"/writeSequence/{i}" for i in range(4)]


def test_scenario_compile_wraps_a_lowering_failure_as_engine_error() -> None:
    bad = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "write": [
                            {
                                "mutation": "insert",
                                "entity": "Account",
                                "rows": [{"id": 1, "no": 2}],
                            }
                        ]
                    }
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="undeclared member"):
        engine.compile_scenario_case(bad, "postgres")


def test_write_sequence_compile_wraps_a_lowering_failure_as_engine_error() -> None:
    bad = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {"mutation": "insert", "entity": "Account", "rows": [{"id": 1, "no": 2}]}
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="undeclared member"):
        engine.compile_write_sequence_case(bad, "postgres")


# --------------------------------------------------------------------------- #
# Conflict — the optimistic-lock run lane (m-opt-lock, COR-3 Phase 8           #
# increment 3): single-attempt, given.apply, and when.attempts forms, each     #
# driven against the fake in-memory port (no Docker; the real conflict/retry   #
# semantics against a reset database are the Docker-gated pg-full proof,       #
# `tests/conformance/test_run_sweep.py::test_conflict_run_sweep`).             #
# --------------------------------------------------------------------------- #
def test_run_conflict_case_single_attempt() -> None:
    port = FakeWritePort()
    emissions, affected, table_state = engine.run_conflict_case(
        _load_case("m-opt-lock-006"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "account" in table_state


def test_run_conflict_case_applies_given_apply_out_of_band_first() -> None:
    port = FakeWritePort()
    emissions, affected, table_state = engine.run_conflict_case(
        _load_case("m-opt-lock-005"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    # given.apply's naive out-of-band bump, THEN the gated update.
    assert len(port.writes) == 2
    assert affected == 1  # the fake port always reports 1; the real 0-row
    # conflict proof runs against a reset database (test_conflict_run_sweep).
    assert table_state is not None


def test_run_conflict_case_attempts_form_scripts_each_attempt_independently() -> None:
    port = FakeWritePort()
    emissions, affected, table_state = engine.run_conflict_case(
        _load_case("m-opt-lock-007"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == [
        "/when/attempts/0/write",
        "/when/attempts/1/write",
    ]
    assert len(port.writes) == 3  # given.apply + two independent scripted attempts
    assert affected == 1
    assert table_state is not None


def test_apply_given_apply_is_a_no_op_when_given_carries_no_apply_list() -> None:
    from parallax.core.dialect import POSTGRES

    case = _synthetic_write("conflict", {"given": {"fixtures": True}})
    port = FakeWritePort()
    engine._apply_given_apply(case, POSTGRES, port)  # pyright: ignore[reportPrivateUsage]
    assert port.writes == []


def test_run_conflict_case_wraps_a_lowering_failure_as_engine_error() -> None:
    case = _synthetic_write("conflict", {"when": {"write": {"id": 1, "bogus": True}}})
    with pytest.raises(engine.EngineError, match="undeclared member"):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def test_run_conflict_case_refuses_a_temporal_close_form() -> None:
    # m-audit-write-006: a temporal / bitemporal optimistic-lock CLOSE conflict
    # (`when.at` / `when.observedInZ`) lands with the temporal write path
    # (COR-3 Phase 8 increment 4) — this lane refuses it loudly rather than
    # silently mishandling the milestone-pk-only row.
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-audit-write-006"]
    with pytest.raises(engine.EngineError, match="temporal write path"):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def test_scenario_case_without_when_is_rejected() -> None:
    with pytest.raises(engine.EngineError, match="has no `when`"):
        engine.compile_scenario_case(_synthetic_write("scenario", {}), "postgres")


def test_scenario_case_without_a_scenario_list_is_rejected() -> None:
    with pytest.raises(engine.EngineError, match=r"when\.scenario"):
        engine.compile_scenario_case(_synthetic_write("scenario", {"when": {}}), "postgres")


def test_scenario_find_step_missing_fields_is_rejected() -> None:
    bad = _synthetic_write(
        "scenario",
        {"when": {"scenario": [{"find": {"eq": {"attr": "Account.id", "value": 1}}}]}},
    )
    with pytest.raises(engine.EngineError, match="targetEntity"):
        engine.compile_scenario_case(bad, "postgres")


def test_write_sequence_case_without_a_sequence_list_is_rejected() -> None:
    with pytest.raises(engine.EngineError, match="writeSequence"):
        engine.compile_write_sequence_case(
            _synthetic_write("writeSequence", {"when": {}}), "postgres"
        )


# --------------------------------------------------------------------------- #
# Rejected — the pre-SQL model-aware validation lane (COR-3 Phase 7            #
# increment 1: resolved DQ3/DQ8). Three-way `when` dispatch.                   #
# --------------------------------------------------------------------------- #
def _rejected_case(case_id: str) -> case_format.Case:
    (case,) = [c for c in case_format.load_cases() if c.case_id == case_id]
    return case


def _synthetic_rejected(when: dict[str, object]) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path("m-op-algebra-998-synthetic-rejected.yaml"),
        case_id="m-op-algebra-998",
        shape="rejected",
        tags=("m-op-algebra", "rejected", "slice-snapshot-1"),
        model="models/animal.yaml",
        document={"model": "models/animal.yaml", "when": when, "then": {"rejectedRule": "x"}},
    )


def test_run_rejected_case_operation_dispatch_classifies_the_rule() -> None:
    case = _rejected_case("m-inheritance-040")
    assert engine.run_rejected_case(case) == "narrow-outside-position"


def test_run_rejected_case_operation_dispatch_over_a_value_object_model() -> None:
    case = _rejected_case("m-value-object-037")
    assert engine.run_rejected_case(case) == "find-root-value-object"


def test_run_rejected_case_model_dispatch_reuses_the_phase_3_validator() -> None:
    case = _rejected_case("m-inheritance-020")
    assert engine.run_rejected_case(case) == "inheritance-unknown-parent"


def test_run_rejected_case_write_dispatch_classifies_the_rule() -> None:
    case = _rejected_case("m-value-object-039")
    assert engine.run_rejected_case(case) == "write-required-attribute-missing"


def test_run_rejected_case_write_dispatch_over_an_inheritance_model() -> None:
    case = _rejected_case("m-inheritance-088")
    assert engine.run_rejected_case(case) == "abstract-write-target"


def test_run_rejected_case_raises_when_operation_unexpectedly_accepted() -> None:
    valid: dict[str, object] = {"operation": {"all": {}}}
    with pytest.raises(engine.EngineError, match="accepted an operation"):
        engine.run_rejected_case(_synthetic_rejected(valid))


def test_run_rejected_case_raises_when_model_unexpectedly_accepted() -> None:
    valid_model: dict[str, object] = {
        "model": {
            "entities": [
                {
                    "name": "Widget",
                    "table": "widget",
                    "attributes": [
                        {"name": "id", "type": "int64", "column": "id", "primaryKey": True}
                    ],
                }
            ]
        }
    }
    with pytest.raises(engine.EngineError, match="accepted an inline inheritance family"):
        engine.run_rejected_case(_synthetic_rejected(valid_model))


def test_run_rejected_case_raises_when_write_unexpectedly_accepted() -> None:
    from pathlib import Path

    valid_write: dict[str, object] = {
        "write": {"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}
    }
    document: dict[str, object] = {
        "model": "models/account.yaml",
        "when": valid_write,
        "then": {"rejectedRule": "x"},
    }
    case = case_format.Case(
        path=Path("m-unit-work-998-synthetic-rejected.yaml"),
        case_id="m-unit-work-998",
        shape="rejected",
        tags=("m-unit-work", "rejected", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )
    with pytest.raises(engine.EngineError, match="accepted a write"):
        engine.run_rejected_case(case)


def test_run_rejected_case_raises_for_a_malformed_operation() -> None:
    malformed_operation: dict[str, object] = {"operation": {"eq": {}}}
    with pytest.raises(engine.EngineError, match="missing required key"):
        engine.run_rejected_case(_synthetic_rejected(malformed_operation))


def test_run_rejected_case_raises_for_a_malformed_inline_model() -> None:
    malformed_model: dict[str, object] = {"model": {"entities": [{"attributes": []}]}}
    with pytest.raises(engine.EngineError, match="`name` must be a string"):
        engine.run_rejected_case(_synthetic_rejected(malformed_model))


def test_run_rejected_case_raises_when_when_carries_none_of_the_three_inputs() -> None:
    with pytest.raises(engine.EngineError, match="EXACTLY ONE"):
        engine.run_rejected_case(_synthetic_rejected({}))


def test_run_rejected_case_raises_when_when_carries_operation_and_model() -> None:
    # The schema `oneOf` cannot protect a caller that reaches the engine without
    # schema validation (a hand-built synthetic case, here) — the engine's own
    # mirror guard must still refuse a multi-input `when`.
    when: dict[str, object] = {"operation": {"all": {}}, "model": {"entities": []}}
    with pytest.raises(engine.EngineError, match="EXACTLY ONE"):
        engine.run_rejected_case(_synthetic_rejected(when))


def test_run_rejected_case_raises_when_when_carries_operation_and_write() -> None:
    when: dict[str, object] = {"operation": {"all": {}}, "write": {}}
    with pytest.raises(engine.EngineError, match="EXACTLY ONE"):
        engine.run_rejected_case(_synthetic_rejected(when))


def test_run_rejected_case_raises_when_when_carries_model_and_write() -> None:
    when: dict[str, object] = {"model": {"entities": []}, "write": {}}
    with pytest.raises(engine.EngineError, match="EXACTLY ONE"):
        engine.run_rejected_case(_synthetic_rejected(when))


def test_read_table_state_reads_each_physical_table_once() -> None:
    # The payment model is the degenerate layout: an abstract TABLELESS root
    # (Payment, table None — nothing to read) and two concrete subtypes SHARING
    # one table, which is read back exactly once.
    from parallax.conformance import models
    from parallax.core.dialect import POSTGRES

    port = FakeWritePort()
    meta = models.load_models()["payment"]
    state = engine.read_table_state(port, meta, POSTGRES)
    assert set(state) == {"payment"}
    assert len(port.reads) == 1


def test_read_table_state_projects_value_object_document_columns() -> None:
    # `_table_column_order`'s family-wide column resolution includes each
    # value-object's own document column last (m-sql `column_order`), even for
    # a plain (non-inheritance) entity — the customer model's `address`.
    from parallax.conformance import models
    from parallax.core.dialect import POSTGRES

    port = FakeWritePort()
    meta = models.load_models()["customer"]
    state = engine.read_table_state(port, meta, POSTGRES)
    assert "customer" in state
    sql, _ = port.reads[0]
    assert "address" in sql


# --------------------------------------------------------------------------- #
# Graph reads (m-deep-fetch / m-snapshot-read, COR-3 Phase 7 increment 5): the #
# `run_graph_case` / `run_graphs_case` rendering lane, and the internal graph- #
# node serializer / identityChecks evaluator / scenario `mutate` action.       #
# --------------------------------------------------------------------------- #
class QueueDbPort:
    """A fake `m-db-port` returning one canned response per `execute()` call."""

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        return self._responses.pop(0)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise NotImplementedError


def test_run_graph_case_renders_root_class_keyed_graph_with_relationships() -> None:
    port = QueueDbPort(
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
    emissions, graph, round_trips, identity_checks = engine.run_graph_case(
        _case("m-snapshot-read-001"), "postgres", port
    )
    assert round_trips == 3
    assert len(emissions) == 3
    assert identity_checks is None
    assert [item["id"] for item in _rows(graph["Order"][0], "items")] == [12, 11]
    assert _rows(graph["Order"][0], "itemsByShipDate")[0]["shipped_on"] == "2024-02-15"


def test_run_graph_case_evaluates_identity_checks_over_the_assembled_graph() -> None:
    port = QueueDbPort(
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
    _emissions, graph, round_trips, identity_checks = engine.run_graph_case(
        _case("m-snapshot-read-011"), "postgres", port
    )
    assert round_trips == 2
    assert identity_checks == [
        {"left": "/then/graph/Order/0", "right": "/then/graph/Order/0/items/0/order", "same": True},
        {"left": "/then/graph/Order/0", "right": "/then/graph/Order/0/items/1/order", "same": True},
    ]
    # The back-reference cycle position truncates to a PK-only stub in the wire
    # rendering — the SAME position identityChecks proved is the root's own
    # object, above, evaluated over the assembled (pre-truncation) graph.
    assert _rows(graph["Order"][0], "items")[0]["order"] == {"id": 1}


def test_render_node_does_not_stub_a_diamond_at_a_non_cyclic_position() -> None:
    from parallax.snapshot import materialize

    child = materialize.Node(fields={"id": 11, "name": "child"}, pk_columns=("id",))
    root = materialize.Node(fields={"id": 1, "a": child, "b": child}, pk_columns=("id",))
    rendered = engine._render_node(root, frozenset())  # pyright: ignore[reportPrivateUsage]
    assert rendered["a"] == {"id": 11, "name": "child"}
    assert rendered["b"] == {"id": 11, "name": "child"}


def test_render_node_truncates_a_true_ancestor_cycle_to_a_pk_only_stub() -> None:
    from parallax.snapshot import materialize

    root = materialize.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    root.fields["self"] = root
    rendered = engine._render_node(root, frozenset())  # pyright: ignore[reportPrivateUsage]
    assert rendered["self"] == {"id": 1}


def test_resolve_graph_pointer_rejects_a_malformed_pointer() -> None:
    from parallax.snapshot import materialize

    node = materialize.Node(fields={"id": 1}, pk_columns=("id",))
    with pytest.raises(engine.EngineError, match="malformed"):
        engine._resolve_graph_pointer(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-011"), {"Order": [node]}, "/nonsense"
        )


def test_apply_mutate_step_updates_the_targeted_nodes_fields_in_place() -> None:
    from parallax.snapshot import materialize

    node = materialize.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage]
        _case("m-snapshot-read-010"), step, [[node]]
    )
    assert node.fields["name"] == "Mutant"


def test_apply_mutate_step_raises_when_the_target_step_materialized_zero_nodes() -> None:
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="expected exactly one"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-010"), step, [[]]
        )


def test_apply_mutate_step_raises_when_the_target_step_materialized_many_nodes() -> None:
    from parallax.snapshot import materialize

    nodes = [materialize.Node(fields={}, pk_columns=()), materialize.Node(fields={}, pk_columns=())]
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="expected exactly one"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-010"), step, [nodes]
        )


def test_apply_mutate_step_raises_when_set_is_not_a_mapping() -> None:
    from parallax.snapshot import materialize

    node = materialize.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    step = {"action": "mutate", "on": 0, "set": "not-a-mapping"}
    with pytest.raises(engine.EngineError, match="needs a `set` mapping"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-010"), step, [[node]]
        )


def test_apply_mutate_step_raises_on_an_out_of_range_on_index() -> None:
    step = {"action": "mutate", "on": 5, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="invalid `on`"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-010"), step, [[]]
        )


# --------------------------------------------------------------------------- #
# Docker-free error paths (m-conformance-adapter's lane-honest ``EngineError``  #
# wrapping): a compiled/found operation that fails inside `m-sql` / `m-navigate`#
# / `m-temporal-read` is caught and re-raised as one `EngineError`, never a     #
# leaked lower-layer exception type.                                           #
# --------------------------------------------------------------------------- #
def test_compile_read_case_wraps_a_sql_gen_error() -> None:
    case = _synthetic(
        {
            "model": "models/orders.yaml",
            "when": {
                "targetEntity": "Order",
                "operation": {"eq": {"attr": "Order.doesNotExist", "value": 1}},
            },
        }
    )
    with pytest.raises(engine.EngineError, match="names no attribute"):
        engine.compile_read_case(case, "postgres")


def test_run_graph_case_wraps_a_temporal_read_error_from_the_find_executor() -> None:
    case = _synthetic(
        {
            "model": "models/policy.yaml",
            "when": {
                "targetEntity": "Policy",
                "operation": {
                    "asOf": {
                        "operand": {"all": {}},
                        "asOfAttr": "Policy.notAnAxis",
                        "date": "now",
                    }
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(engine.EngineError, match="undeclared axis"):
        engine.run_graph_case(case, "postgres", QueueDbPort([]))


def test_run_graphs_case_renders_ordered_milestone_pin_graphs() -> None:
    from parallax.core.base import INFINITY

    port = QueueDbPort(
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
    emissions, graphs, round_trips = engine.run_graphs_case(
        _case("m-snapshot-read-013"), "postgres", port
    )
    assert round_trips == 1
    assert len(emissions) == 1
    assert [_entry(g, "pin")["processingDate"] for g in graphs] == [
        "2024-01-01T00:00:00+00:00",
        "2024-04-01T00:00:00+00:00",
    ]
    assert [_rows(_entry(g, "graph"), "InvoiceLine")[0]["amount"] for g in graphs] == [
        "50.00",
        "75.00",
    ]


def test_run_graphs_case_wraps_an_error_from_the_find_executor() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "targetEntity": "InvoiceLine",
                "operation": {
                    "history": {"operand": {"all": {}}, "asOfAttr": "InvoiceLine.notAnAxis"}
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(engine.EngineError, match="undeclared axis"):
        engine.run_graphs_case(case, "postgres", QueueDbPort([]))


def test_render_value_recurses_into_a_nested_value_object_document() -> None:
    from parallax.snapshot import materialize

    node = materialize.Node(
        fields={"id": 1, "address": {"street": "x", "geo": {"country": "NO"}}},
        pk_columns=("id",),
    )
    rendered = engine._render_node(node, frozenset())  # pyright: ignore[reportPrivateUsage]
    assert rendered["address"] == {"street": "x", "geo": {"country": "NO"}}


def test_resolve_graph_pointer_rejects_a_path_continuing_past_a_scalar() -> None:
    from parallax.snapshot import materialize

    node = materialize.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    with pytest.raises(engine.EngineError, match="does not resolve"):
        engine._resolve_graph_pointer(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-011"), {"Order": [node]}, "/then/graph/Order/0/name/x"
        )


def test_resolve_graph_pointer_rejects_a_pointer_resolving_to_a_non_node() -> None:
    from parallax.snapshot import materialize

    node = materialize.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    with pytest.raises(engine.EngineError, match="does not name a graph node"):
        engine._resolve_graph_pointer(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-011"), {"Order": [node]}, "/then/graph/Order/0/name"
        )


def test_check_action_step_rejects_a_non_mutate_verb() -> None:
    with pytest.raises(engine.EngineError, match="graded by the API"):
        engine._check_action_step(  # pyright: ignore[reportPrivateUsage]
            _case("m-snapshot-read-010"), {"action": "access"}
        )


def test_compile_scenario_case_snapshot_lane_requires_target_entity_and_find() -> None:
    when = {
        "scenario": [
            {"action": "mutate", "on": 0, "set": {"x": 1}},
            {"targetEntity": "Order"},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="needs `targetEntity` and `find`"):
        engine.compile_scenario_case(case, "postgres")


def test_compile_scenario_case_snapshot_lane_wraps_a_sql_gen_error() -> None:
    when = {
        "scenario": [
            {"targetEntity": "Order", "find": {"eq": {"attr": "Order.nope", "value": 1}}},
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="names no attribute"):
        engine.compile_scenario_case(case, "postgres")


def test_run_scenario_case_snapshot_lane_requires_target_entity_and_find() -> None:
    when = {
        "scenario": [
            {"targetEntity": "Order"},
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="needs `targetEntity` and `find`"):
        engine.run_scenario_case(case, "postgres", QueueDbPort([]))


def test_run_scenario_case_snapshot_lane_wraps_an_error_from_the_find_executor() -> None:
    when = {
        "scenario": [
            {"targetEntity": "Order", "find": {"eq": {"attr": "Order.nope", "value": 1}}},
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="names no attribute"):
        engine.run_scenario_case(case, "postgres", QueueDbPort([]))


def test_run_scenario_case_snapshot_lane_mutates_in_memory_with_no_writeback() -> None:
    port = FakeWritePort(
        find_rows=[
            {
                "id": 1,
                "name": "Ada",
                "sku": "A-100",
                "qty": 5,
                "price": decimal.Decimal("10.50"),
                "active": True,
                "ordered_on": dt.date(2024, 1, 5),
            }
        ]
    )
    emissions, round_trips = engine.run_scenario_case(
        _case("m-snapshot-read-010"), "postgres", port
    )
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find", "/scenario/2/find"]
    assert len(port.reads) == 2
    assert len(port.writes) == 0
