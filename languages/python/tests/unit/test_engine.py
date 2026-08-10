"""Conformance engine unit tests (compile / run against the spine).

The compile path is proven pure and golden-matching over a representative
exercised case; the run path is proven against a fake in-memory
``m-db-port`` (no Docker) so the port-execution seam, the `?` -> `%s` translation,
and the observation recording are covered in the unit lane. Compile-eligibility
reading and the engine's failure modes are pinned too.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import decimal
import re
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import pytest
from _metamodel_support import Declaration, key, source

from parallax.conformance import case_format, engine, sweep
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INFINITY, STRING, InstantError
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import dialect_for
from parallax.core.metamodel import (
    AbstractRoot,
    AttributeIdentity,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    RelationshipIdentity,
    Table,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.temporal_read import Edge, Pin
from parallax.core.unit_work import (
    Concurrency,
    KeyTarget,
    MissingTargetError,
    ObjectKey,
    ObservationKey,
    OptimisticLockConflictError,
    PredecessorRow,
    StaleWriteError,
    TemporalObservation,
    VersionObservation,
    WriteEffectError,
)
from parallax.snapshot import handle
from parallax.snapshot.materialize import RelationshipViewKey


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
    emissions, rows, round_trips, _trace = engine.run_read_case(
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
    _emissions, rows, _round_trips, _trace = engine.run_read_case(
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
    _emissions, rows, _round_trips, _trace = engine.run_read_case(
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
    _emissions, rows, _round_trips, _trace = engine.run_read_case(
        _case("m-inheritance-050"), "postgres", port
    )
    assert rows[0]["familyVariant"] == "Invoice"
    assert "family_variant" not in rows[0]


def test_run_read_case_concrete_target_read_carries_no_family_variant() -> None:
    # m-inheritance-001 (CardPayment, concrete target): the compiled SELECT never
    # projects a tag/literal column, so the row passes through wire rendering alone.
    port = FakeDbPort([{"id": 1, "amount": decimal.Decimal("100.00"), "card_network": "Visa"}])
    _emissions, rows, _round_trips, _trace = engine.run_read_case(
        _case("m-inheritance-001"), "postgres", port
    )
    assert rows == [{"id": 1, "amount": "100.00", "card_network": "Visa"}]
    assert "familyVariant" not in rows[0]


def test_run_read_case_reports_an_unresolvable_target_as_an_engine_error() -> None:
    # The lane's one refusal translation: whatever production raises while
    # resolving, building, or running the request is reported against the case
    # file, so a corpus defect names the case rather than a production frame.
    case = _case("m-value-object-001")
    document = dict(case.document)
    when = dict(cast("Mapping[str, object]", document["when"]))
    when["targetEntity"] = "parallax.compatibility.NoSuchEntity"
    document["when"] = when
    with pytest.raises(engine.EngineError, match=case.path.name):
        engine.run_read_case(
            dataclasses.replace(case, document=document), "postgres", FakeDbPort([])
        )


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
    emissions, round_trips, errors, _log = engine.run_scenario_case(
        _case("m-unit-work-001"), "postgres", port
    )
    assert round_trips == 2
    assert errors == []  # a keyed unit-of-work scenario reports no error observation
    assert [e.case_pointer for e in emissions] == ["/scenario/0/write", "/scenario/1/find"]
    assert emissions[0].sql.startswith("insert into account")
    assert emissions[1].sql.endswith("for share of t0")  # the read-lock suffix renders
    assert len(port.writes) == 1 and len(port.reads) == 1
    # An UNGROUPED find of a scenario declaring a participation mode runs in its
    # OWN transaction, exactly as `run_read_case` does: the read lock is the
    # transaction's, so the boundary is what renders it.
    assert port.commits == 2 and port.rollbacks == 0


def test_run_scenario_case_rollback_step_aborts_but_counts_the_round_trip() -> None:
    port = FakeWritePort(find_rows=[])
    emissions, round_trips, _errors, _log = engine.run_scenario_case(
        _case("m-unit-work-011"), "postgres", port
    )
    assert round_trips == 2  # the aborted insert still counts one round trip
    assert len(port.writes) == 1  # the DML executed before the abort
    # An UNGROUPED find of a scenario declaring a participation mode runs in its
    # OWN transaction, exactly as `run_read_case` does: the read lock is the
    # transaction's, so the boundary is what renders it.
    assert port.rollbacks == 1 and port.commits == 1
    assert emissions[0].case_pointer == "/scenario/0/write"


# --- `uow`-grouped scenario spans --------------------------------------------
#
# `m-unit-work-005/006/009/012` and `m-unit-work-002` are `compileEligibility:
# run-only` (their version binds are query-result-dependent), so they route
# through `_run_uow_group` here — a whole `uow` span in ONE `db.transact` call,
# never the ungrouped per-step path above. `FakeWritePort` returns the SAME
# canned `find_rows` for every read, which is enough to prove the MECHANICS
# (one transaction per group, the version advance derived from an observation
# this SAME call recorded, no oracle) without needing per-call differentiated
# rows — the exact observed values are pinned end-to-end against real
# Postgres/MariaDB by the reference-harness suite and the Docker run sweep.


def test_run_scenario_case_groups_a_committing_uow_span_into_one_transaction() -> None:
    # m-unit-work-005: all three steps (observe find, versioned update,
    # dependent find) share ONE `uow` group — a single `db.transact` call, not
    # three separate ones, so exactly one port-level commit fires.
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    emissions, round_trips, _errors, _log = engine.run_scenario_case(
        _case("m-unit-work-005"), "postgres", port
    )
    assert round_trips == 3
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/find",
        "/scenario/1/write",
        "/scenario/2/find",
    ]
    # The write's SET version bind is the OBSERVED version (1) advanced to 2 —
    # a genuine transaction-scoped observation this SAME group's own find
    # recorded, never an authored value (`update ... set balance = ?,
    # version = ? where id = ?`).
    assert emissions[1].sql.startswith("update account set")
    assert emissions[1].binds == (175.00, 2, 1)
    assert len(port.writes) == 1 and len(port.reads) == 2
    assert port.commits == 1 and port.rollbacks == 0


def test_run_scenario_case_doomed_uow_span_rolls_back_as_one_unit() -> None:
    # m-unit-work-002: steps 0-1 share the doomed `doomed-update` group (its
    # write declares `rollback: true`); step 2 is an UNGROUPED post-abort find.
    # The GROUP rolls back as ONE unit (one port-level rollback, zero commits)
    # — never a separate transaction per step.
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    emissions, round_trips, _errors, _log = engine.run_scenario_case(
        _case("m-unit-work-002"), "postgres", port
    )
    assert round_trips == 3
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/find",
        "/scenario/1/write",
        "/scenario/2/find",
    ]
    assert len(port.writes) == 1  # the doomed write's DML still executed (and counted)
    assert len(port.reads) == 2  # the grouped observe find + the ungrouped post-abort find
    # An UNGROUPED find of a scenario declaring a participation mode runs in its
    # OWN transaction, exactly as `run_read_case` does: the read lock is the
    # transaction's, so the boundary is what renders it.
    assert port.commits == 1 and port.rollbacks == 1


def _two_group_interleave_steps() -> list[dict[str, object]]:
    return [
        {
            "uow": "a",
            "targetEntity": "Account",
            "find": {"eq": {"attr": "Account.id", "value": 1}},
            "roundTrips": 1,
            "statements": [{"sql": {"postgres": "select ... where t0.id = ?"}, "binds": [1]}],
        },
        {
            "uow": "b",
            "targetEntity": "Account",
            "find": {"eq": {"attr": "Account.id", "value": 2}},
            "roundTrips": 1,
            "statements": [{"sql": {"postgres": "select ... where t0.id = ?"}, "binds": [2]}],
        },
        {
            "uow": "a",
            "write": [{"mutation": "update", "entity": "Account", "rows": [{"id": 1}]}],
            "roundTrips": 1,
            "statements": [
                {
                    "sql": {"postgres": "update account set balance = ? where id = ?"},
                    "binds": [1.0, 1],
                }
            ],
        },
    ]


def test_scenario_uow_spans_signals_the_two_group_interleave_with_none() -> None:
    # `m-opt-lock-012`'s own shape (two `uow` groups whose steps interleave):
    # `_scenario_uow_spans` returns `None` rather than raising — the caller
    # routes to `run_interleaved_scenario_case` instead, which needs a
    # second, peer-backed connection this
    # function does not construct.
    assert (
        engine._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            "m-unit-work-999-synthetic.yaml", _two_group_interleave_steps()
        )
        is None
    )


def test_run_scenario_case_routes_the_two_group_interleave_to_run_interleaved_scenario_case() -> (
    None
):
    # `run_scenario_case` itself constructs no second connection, so it
    # refuses loudly and names the entry point that does, rather than
    # silently mis-executing the interleave (or reference-harness-only
    # forever).
    case = _synthetic_write(
        "scenario",
        {
            "when": {"scenario": _two_group_interleave_steps()},
            "then": {"roundTrips": 3},
        },
    )
    with pytest.raises(engine.EngineError, match="run_interleaved_scenario_case"):
        engine.run_scenario_case(case, "postgres", FakeWritePort())


def test_scenario_uow_spans_rejects_interleaving_beyond_the_two_group_shape() -> None:
    # Three `uow` groups, one of them non-contiguous: `m-opt-lock-012`'s own
    # two-group interleave is the ONLY shape `run_interleaved_scenario_case`
    # supports (pinned semantics #4, "scope honestly") — anything beyond it
    # raises loudly rather than silently mis-executing a THIRD concurrent
    # session no seam here provides.
    steps: list[dict[str, object]] = [
        {"uow": "a", "targetEntity": "Account", "find": {"eq": {"attr": "Account.id", "value": 1}}},
        {"uow": "b", "targetEntity": "Account", "find": {"eq": {"attr": "Account.id", "value": 2}}},
        {"uow": "c", "targetEntity": "Account", "find": {"eq": {"attr": "Account.id", "value": 3}}},
        {
            "uow": "a",
            "write": [{"mutation": "update", "entity": "Account", "rows": [{"id": 1}]}],
        },
    ]
    with pytest.raises(engine.EngineError, match="interleave beyond the one witnessed"):
        engine._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            "m-unit-work-999-synthetic.yaml", steps
        )


class _ScriptedPort:
    """A `DbPort` fake with per-call SCRIPTED read rows / write-affected counts
    (`run_interleaved_scenario_case`'s own unit
    pins) — unlike `FakeWritePort` above (one constant `find_rows` for every
    `execute`, `write_affected` always `1`), a genuinely two-session
    choreography's own conflict needs each connection scripted with its OWN,
    call-ordered sequence to reproduce a real stale-version mismatch
    deterministically, with no real database involved.

    Carries the documented trust marker
    (`engine._TERMINATION_LADDER_TRUST_ATTR`): every method here is a plain
    synchronous, in-memory call that never blocks on real I/O at all, so
    there is nothing for the termination ladder to unblock in the first
    place — a genuinely truthful declaration, not a shortcut around it. This
    is what lets every entry-point pin below run through
    `run_interleaved_scenario_case`'s own preflight
    (`_require_interleaved_termination_capability`) unchanged; the same
    class also stands in directly for `_await_interleaved_workers`'s own
    pins, which bypass preflight entirely and so never consult this marker
    either way. Set via `setattr` below (never a hardcoded attribute name
    here) so this fake can never drift from `engine`'s own marker name."""

    def __init__(
        self,
        *,
        read_rows: Sequence[list[Row]] = (),
        write_affected: Sequence[int] = (),
        raise_on_read: BaseException | None = None,
    ) -> None:
        self._read_rows = [list(rows) for rows in read_rows]
        self._write_affected = list(write_affected)
        self._raise_on_read = raise_on_read
        self.reads: list[tuple[str, tuple[object, ...]]] = []
        self.writes: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        if self._raise_on_read is not None:
            raise self._raise_on_read
        self.reads.append((sql, tuple(binds)))
        return self._read_rows.pop(0) if self._read_rows else []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, tuple(binds)))
        return self._write_affected.pop(0) if self._write_affected else 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(self)

    def close(self) -> None:
        self.closed = True


# Round 5's own documented trust marker, declared on the class itself (every
# instance inherits it) rather than hardcoding `engine`'s own private
# attribute name as a string literal here.
setattr(
    _ScriptedPort,
    engine._TERMINATION_LADDER_TRUST_ATTR,  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    True,
)


def test_run_interleaved_scenario_case_renders_the_conflict_and_discards_the_abort() -> None:
    # `m-opt-lock-012` end to end over two SCRIPTED fake connections (never a
    # real database): the `ours` group's own observing find (step 0) is stale
    # by the time it flushes (step 3) — the `concurrent` group (steps 1-2)
    # committed its own gated update first — so the doomed group's SECOND
    # write (the version-gated update) affects 0 rows, and the group's own
    # buffered insert (account 9) is discarded with it. The trailing
    # ungrouped verify find (step 4) observes no rows for it.
    case = _load_case("m-opt-lock-012")
    row_v1: Row = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    main_port = _ScriptedPort(read_rows=[[row_v1], []], write_affected=[1, 0])
    peer_port = _ScriptedPort(read_rows=[[row_v1]], write_affected=[1])

    emissions, round_trips, conflict_actual, find_rows = engine.run_interleaved_scenario_case(
        case, "postgres", main_port, lambda: peer_port
    )

    assert round_trips == 6
    assert len(emissions) == 6
    assert conflict_actual == 0
    assert peer_port.closed
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/find",
        "/scenario/1/find",
        "/scenario/2/write",
        "/scenario/3/write",
        "/scenario/3/write",
        "/scenario/4/find",
    ]
    assert emissions[3].sql.startswith("insert into account")
    assert emissions[4].sql.startswith("update account set")
    assert len(main_port.writes) == 2  # the doomed group's insert + gated update
    assert len(peer_port.writes) == 1  # the concurrent group's own gated update
    # Every find step's own observed rows, in
    # scenario step order (0, 1, then the trailing ungrouped verify at 4) —
    # the doomed group's discarded insert leaves account 9 absent.
    assert find_rows == [[row_v1], [row_v1], []]


def test_run_interleaved_scenario_case_reports_the_second_groups_own_conflict_too() -> None:
    # The conflict-rendering fallback is symmetric: whichever group's own
    # last write conflicts, its `actual` affected-row count surfaces —
    # `m-opt-lock-012`'s own corpus witness always dooms the FIRST-labeled
    # (`ours`) group, but the engine's own logic does not assume that. A
    # synthetic two-group scenario (never `m-opt-lock-012` itself: its own
    # fixed step order makes the SECOND group's conflict turnstile-unsafe —
    # something downstream always waits on its final `advance()`) pins the
    # fallback: the SECOND group's own last step is also the scenario's
    # OVERALL last grouped step, so nothing waits on its advance either way.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "uow": {"concurrency": "optimistic"},
                "scenario": [
                    {
                        "uow": "x",
                        "targetEntity": "Account",
                        "find": {"eq": {"attr": "Account.id", "value": 2}},
                    },
                    {
                        "uow": "x",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 2, "balance": 260.00}],
                            }
                        ],
                    },
                    {
                        "uow": "y",
                        "targetEntity": "Account",
                        "find": {"eq": {"attr": "Account.id", "value": 2}},
                    },
                    {
                        "uow": "y",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 2, "balance": 270.00}],
                            }
                        ],
                    },
                ],
            },
            "then": {"roundTrips": 4},
        },
    )
    row_v1: Row = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    main_port = _ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    peer_port = _ScriptedPort(read_rows=[[row_v1]], write_affected=[0])

    _emissions, _round_trips, conflict_actual, _find_rows = engine.run_interleaved_scenario_case(
        case, "postgres", main_port, lambda: peer_port
    )

    assert conflict_actual == 0


def test_run_interleaved_group_buffers_a_non_last_write_without_flushing() -> None:
    # A group's own write step that is NOT its last step buffers without
    # forcing a flush (mirroring `_run_uow_group`'s own per-step buffering
    # for a contiguous span, `_run_interleaved_group`'s own generalization
    # of the SAME machinery) — unwitnessed by `m-opt-lock-012` itself (whose
    # own two groups each carry exactly one write, always last).
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "uow": {"concurrency": "optimistic"},
                "scenario": [
                    {
                        "uow": "x",
                        "targetEntity": "Account",
                        "find": {"eq": {"attr": "Account.id", "value": 2}},
                    },
                    {
                        "uow": "x",
                        "write": [
                            {
                                "mutation": "insert",
                                "entity": "Account",
                                "rows": [
                                    {"id": 90, "owner": "Noether", "balance": 5.00, "version": 1}
                                ],
                            }
                        ],
                    },
                    {
                        "uow": "x",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 2, "balance": 260.00}],
                            }
                        ],
                    },
                    {
                        "uow": "y",
                        "targetEntity": "Account",
                        "find": {"eq": {"attr": "Account.id", "value": 3}},
                    },
                ],
            },
            "then": {"roundTrips": 4},
        },
    )
    row_v1: Row = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    row3: Row = {"id": 3, "owner": "Ada", "balance": 10.00, "version": 1}
    main_port = _ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 1])
    peer_port = _ScriptedPort(read_rows=[[row3]])

    emissions, round_trips, conflict_actual, find_rows = engine.run_interleaved_scenario_case(
        case, "postgres", main_port, lambda: peer_port
    )

    assert conflict_actual is None
    assert round_trips == 4
    assert len(main_port.writes) == 2  # buffered together, flushed once at the group's last step
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/find",
        "/scenario/1/write",
        "/scenario/2/write",
        "/scenario/3/find",
    ]
    assert find_rows == [[row_v1], [row3]]


def test_run_interleaved_scenario_case_reraises_an_unexpected_worker_failure() -> None:
    # A worker thread's own UNEXPECTED defect (never a witnessed path) must
    # surface loudly on the main thread rather than hang the choreography —
    # `_Turnstile.release_all` unsticks the partner thread (blocked on
    # `wait_for` a later step that now never arrives) so `thread.join()`
    # itself never hangs either.
    case = _load_case("m-opt-lock-012")
    failure = RuntimeError("a worker thread's own unexpected defect")
    main_port = _ScriptedPort(raise_on_read=failure)
    peer_port = _ScriptedPort(
        read_rows=[
            [{"id": 2, "owner": "Linus", "balance": decimal.Decimal("250.00"), "version": 1}]
        ]
    )

    with pytest.raises(RuntimeError, match="unexpected defect"):
        engine.run_interleaved_scenario_case(case, "postgres", main_port, lambda: peer_port)
    assert peer_port.closed


def test_await_interleaved_workers_unsticks_both_on_timeout_then_joins_before_raising() -> None:
    # The join-timeout path: a genuine harness
    # defect (a missing turnstile `advance()` somewhere) leaves BOTH workers
    # blocked in `wait_for` forever — the timeout path must wake every one of
    # them (`_Turnstile.release_all`), close the peer connection, JOIN both
    # threads, and only THEN raise; no live thread and no open peer connection
    # may outlive the call. A tiny `timeout` (never the production 30s bound)
    # keeps this deterministic and fast. Neither worker's own connection ever
    # needs cancelling here (both wake on `release_all`), so a plain
    # `_ScriptedPort` stands in for `main_connection` too.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    main_connection = _ScriptedPort()
    peer = _ScriptedPort()

    def stuck(index: int) -> Any:
        def run() -> None:
            turnstile.wait_for(index)  # an index this choreography never advances to

        return run

    thread_a = threading.Thread(target=stuck(99), name="stuck-a")
    thread_b = threading.Thread(target=stuck(100), name="stuck-b")
    thread_a.start()
    thread_b.start()

    with pytest.raises(engine.EngineError, match="turnstile hand-off is missing"):
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            thread_a,
            thread_b,
            turnstile,
            main_connection,
            peer,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.05,
        )

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert peer.closed


class _CancellableBlockingConnection:
    """A fake `DbPort` whose ``execute`` blocks (standing in for a real
    driver call parked in socket I/O) until its own :meth:`cancel` seam
    fires — never on `_Turnstile.release_all` (nothing here is parked in
    `turnstile.wait_for`) and never on some OTHER connection closing (this
    is not the peer). This is the shape not otherwise covered: a worker
    blocked in REAL database
    I/O on its OWN session, which only :func:`~parallax.conformance.engine.
    _cancel_in_flight_work`'s duck-typed ``cancel()`` probe can reach — the
    first escalation (turnstile release + peer close) cannot wake it, and a
    survivor's OWN connection is exactly what the second escalation targets.
    """

    def __init__(self) -> None:
        self._released = threading.Event()
        self.cancel_calls = 0

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self._released.wait(timeout=5.0)  # self-bounded even if `cancel` is never called
        return []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)

    def cancel(self) -> None:
        self.cancel_calls += 1
        self._released.set()


def test_await_interleaved_workers_cancels_a_survivor_blocked_in_real_io_then_joins() -> None:
    # A worker blocked
    # in REAL database I/O on its OWN (CALLER-OWNED) connection survives the
    # first escalation intact — `release_all` has nothing to wake (the
    # worker is not inside `turnstile.wait_for`) and closing the peer
    # touches only the OTHER session. The second escalation must cancel that
    # survivor's OWN connection, rejoin bounded, and — once every worker is
    # (now) actually joined — raise the SAME ordinary timeout error this
    # function has always raised, with `is_alive()` false for every worker
    # before it does.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    main_connection = _CancellableBlockingConnection()
    peer = _ScriptedPort()

    def run_a() -> None:
        main_connection.execute("select 1", [])

    def run_b() -> None:
        turnstile.wait_for(100)  # an index this choreography never advances to

    thread_a = threading.Thread(target=run_a, name="uow-ours")
    thread_b = threading.Thread(target=run_b, name="uow-concurrent")
    thread_a.start()
    thread_b.start()

    with pytest.raises(engine.EngineError, match="turnstile hand-off is missing"):
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            thread_a,
            thread_b,
            turnstile,
            main_connection,
            peer,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.1,
        )

    assert main_connection.cancel_calls == 1
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert peer.closed


class _TerminableBlockingConnection:
    """A fake `DbPort` whose ``execute`` blocks (standing in for a real
    driver call parked in socket I/O) and exposes NO :meth:`cancel`
    capability at all — the shape a survivor neither `_Turnstile.release_all`
    nor :func:`~parallax.conformance.engine._cancel_in_flight_work`'s
    duck-typed ``cancel()`` probe can reach, forcing the THIRD, destructive
    escalation, :func:`~parallax.conformance.engine._terminate_connection`.
    Its own :meth:`close` mirrors REAL closed-connection semantics closely
    enough to prove that rung's own contract: the blocked ``execute`` call
    wakes and RAISES once ``close`` fires (a closed connection can never
    fulfil the in-flight call), and any LATER call raises immediately too,
    as far as this fake allows — never silently executing against a
    terminated connection."""

    def __init__(self) -> None:
        self._closed = threading.Event()
        self.close_calls = 0
        self.closed = False

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self._closed.wait(timeout=5.0)  # self-bounded even if `close` is never called
        raise RuntimeError("connection is closed")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True
        self._closed.set()


def test_await_interleaved_workers_terminates_a_survivor_with_no_cancel_capability() -> None:
    # A survivor
    # neither `release_all` nor the cancellation probe can reach (no
    # `cancel()` capability at all, `main_connection` here — the
    # CALLER-OWNED port) escalates to the THIRD, destructive rung —
    # `_terminate_connection` closes its OWN connection outright — rather
    # than this function ever raising while that worker remains alive; the
    # contract has no "loud leak" terminal state at all.
    # `is_alive()` must be False for EVERY worker at the moment of the
    # raise, and the raised error must report that the caller-owned port
    # was itself terminated. The fake's own `close()` seam mirrors REAL
    # close semantics closely enough to prove it: its blocked `execute`
    # wakes and raises once closed, and a later call raises too (as far as
    # the fake allows) rather than executing.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    main_connection = _TerminableBlockingConnection()
    peer = _ScriptedPort()

    def run_a() -> None:
        # expected collateral of the termination escalation itself
        with contextlib.suppress(RuntimeError):
            main_connection.execute("select 1", [])

    def run_b() -> None:
        turnstile.wait_for(100)  # an index this choreography never advances to

    thread_a = threading.Thread(target=run_a, name="uow-ours")
    thread_b = threading.Thread(target=run_b, name="uow-concurrent")
    thread_a.start()
    thread_b.start()

    with pytest.raises(engine.EngineError, match=r"terminated \(closed\).*unsafe to reuse"):
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            thread_a,
            thread_b,
            turnstile,
            main_connection,
            peer,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.1,
        )

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert main_connection.close_calls == 1
    assert main_connection.closed
    assert peer.closed
    with pytest.raises(RuntimeError):
        main_connection.execute("select 1", [])  # a terminated port raises, never executes


class _UnderlyingConnectionSeam:
    """The termination ladder's documented underlying-transport escalation
    seam for a test fake — mirrors `PostgresAdapter.connection`, the wrapped psycopg
    ``Connection`` a real adapter's own outer ``close()`` failure escalates
    to (:func:`~parallax.conformance.engine._terminate_connection`'s rung
    two). Closing THIS is what actually unblocks the survivor's blocked
    call; its own ``close()`` succeeding is what proves the ladder reaches
    PAST a broken outer ``close()`` rather than stopping there."""

    def __init__(self, released: threading.Event) -> None:
        self._released = released
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        self._released.set()


class _TerminableOnlyViaUnderlyingSeamConnection:
    """A fake `DbPort` whose own OUTER ``close()`` FAILS (mirroring a real
    driver's own close-time complaint) and whose ``cancel()`` capability is
    absent entirely — the adversarial shape where BOTH
    ``cancel()`` and ``close()`` fail on the same survivor. The
    escalation's first two rungs (:func:`~parallax.conformance.engine.
    _cancel_in_flight_work`'s probe, then ``connection.close()`` itself)
    both come up empty — a "close always works" assumption does
    not hold here BY DESIGN — forcing :func:`~parallax.conformance.engine.
    _terminate_connection` past the failing outer ``close()`` to the
    documented underlying seam (``self.connection``, mirroring
    `PostgresAdapter.connection`)."""

    def __init__(self) -> None:
        self._released = threading.Event()
        self.close_calls = 0
        self.connection = _UnderlyingConnectionSeam(self._released)

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self._released.wait(timeout=5.0)  # self-bounded even if the ladder never reaches it
        raise RuntimeError("connection is closed")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)

    def close(self) -> None:
        self.close_calls += 1
        raise RuntimeError("outer close failed")


def test_await_interleaved_workers_escalates_past_a_failing_close_to_the_underlying_seam() -> None:
    # `cancel()` absent AND `close()` raising
    # on the SAME survivor — `_terminate_connection`'s GUARANTEED
    # ladder must escalate past the failing outer `close()` to the fake's
    # documented underlying seam, unblock it there, join both workers, and
    # raise the SAME terminated-caller-port timeout error the close-succeeds
    # pin above raises — never a live worker at the raise, and the failing
    # outer `close()` itself must never be silently swallowed: it must
    # surface as recorded context on the raised error rather than masked.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    main_connection = _TerminableOnlyViaUnderlyingSeamConnection()
    peer = _ScriptedPort()

    def run_a() -> None:
        # expected collateral of the termination escalation itself
        with contextlib.suppress(RuntimeError):
            main_connection.execute("select 1", [])

    def run_b() -> None:
        turnstile.wait_for(100)  # an index this choreography never advances to

    thread_a = threading.Thread(target=run_a, name="uow-ours")
    thread_b = threading.Thread(target=run_b, name="uow-concurrent")
    thread_a.start()
    thread_b.start()

    with pytest.raises(
        engine.EngineError, match=r"terminated \(closed\).*unsafe to reuse"
    ) as exc_info:
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            thread_a,
            thread_b,
            turnstile,
            main_connection,
            peer,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.1,
        )

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert main_connection.close_calls == 1  # the failing outer close was still attempted
    assert main_connection.connection.close_calls == 1  # the underlying seam is what unblocked it
    assert peer.closed
    notes = "\n".join(exc_info.value.__notes__)
    assert "outer close failed" in notes  # the swallowed failure is recorded context


class _NoCloseNoUnderlyingConnection:
    """A connection shape exposing NEITHER a ``close()`` NOR a
    ``connection`` (underlying-transport) attribute at all —
    :func:`~parallax.conformance.engine._terminate_connection`'s own two
    "nothing more this rung can do" terminal branches, one per probe. A
    live worker parked on a connection this shape describes would never
    unblock — this module's own documented contract for an unreachable
    fake, not something a test should ever actually trigger through
    :func:`~parallax.conformance.engine._await_interleaved_workers` (that
    would hang the whole suite) — so this pin calls
    :func:`~parallax.conformance.engine._terminate_connection` directly and
    asserts on its own recorded return value instead."""


def test_terminate_connection_records_every_missing_capability() -> None:
    # `_terminate_connection`'s own two "nothing more this rung can do"
    # terminal branches: a connection exposing NEITHER `close()` NOR the
    # underlying `connection` escalation seam records BOTH misses (never
    # silently doing nothing, matching the ladder's own "every failure is
    # recorded" contract) rather than raising or hanging. See
    # `_NoCloseNoUnderlyingConnection` for why this calls the rung directly.
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _NoCloseNoUnderlyingConnection(), "uow-ours"
    )
    assert len(failures) == 2
    assert failures[0] == "uow-ours: connection exposes no close() capability"
    assert failures[1] == "uow-ours: connection exposes no underlying `connection` escalation seam"


class _FailingUnderlyingSeam:
    """An underlying-transport seam (:func:`~parallax.conformance.engine.
    _terminate_connection`'s rung two) whose OWN ``close()`` also fails and
    which exposes no ``fileno()`` either — forces the ladder all the way to
    (and back out of) rung three,
    :func:`~parallax.conformance.engine._terminate_underlying_socket`,
    without a real OS fd (that rung is real-transport only; see its own
    docstring)."""

    def close(self) -> None:
        raise RuntimeError("underlying close failed too")


class _FailingOuterCloseWithFailingUnderlyingSeam:
    """A connection whose OUTER ``close()`` fails AND whose own underlying
    ``connection`` seam ALSO fails to close —
    :func:`~parallax.conformance.engine._terminate_connection`'s own full
    ladder, every rung attempted and every rung's own failure recorded. A
    live worker parked on this shape would never unblock (see
    `_NoCloseNoUnderlyingConnection`'s own docstring for why this is
    exercised by calling the rung directly rather than end to end)."""

    def __init__(self) -> None:
        self.connection = _FailingUnderlyingSeam()

    def close(self) -> None:
        raise RuntimeError("outer close failed too")


def test_terminate_connection_escalates_through_every_rung_when_all_fail() -> None:
    # `_terminate_connection`'s own full ladder when EVERY rung fails: the
    # outer `close()`, the underlying seam's own `close()`, and rung
    # three's own `fileno()` probe (real-transport only) all miss or raise —
    # every one of them recorded, never silently dropped.
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _FailingOuterCloseWithFailingUnderlyingSeam(), "uow-ours"
    )
    assert len(failures) == 3
    assert (
        failures[0] == "uow-ours: connection.close() raised RuntimeError('outer close failed too')"
    )
    assert failures[1] == (
        "uow-ours: underlying connection.close() raised RuntimeError('underlying close failed too')"
    )
    assert (
        failures[2] == "uow-ours: underlying connection exposes no fileno() for OS-level teardown"
    )


class _CapabilityLessConnection:
    """A connection exposing NEITHER `close()`, NOR an underlying
    `connection` attribute, NOR `fileno()` anywhere, NOR the trust
    marker — the most defective refusal shape: preflight must name and
    refuse a connection like this BEFORE either worker thread starts, never
    let it surface only later as an indefinite join hang. `execute_calls` is this pin's own
    observable for "no thread ever started": a defect here refuses before
    either worker is even constructed, so nothing ever calls it."""

    def __init__(self) -> None:
        self.execute_calls = 0

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:  # pragma: no cover
        self.execute_calls += 1
        return []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        self.execute_calls += 1
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        return body(self)


@pytest.mark.parametrize(
    "main_defective, peer_defective, expected_labels",
    [
        (True, False, ("main connection",)),
        (False, True, ("peer connection",)),
        (True, True, ("main connection", "peer connection")),
    ],
)
def test_run_interleaved_scenario_case_refuses_before_any_worker_starts_capability_less(
    main_defective: bool, peer_defective: bool, expected_labels: tuple[str, ...]
) -> None:
    # A capability-less connection — no `close()`, no underlying transport,
    # no `fileno()`, no trust marker — must be refused loudly BEFORE either
    # worker thread starts, all defects reported at once rather than
    # first-failure-only. Covers both positions individually and together
    # (main only / peer only / both). `_ScriptedPort` stands in for the
    # HEALTHY side because it carries the trust marker (see its
    # own docstring) — the SAME reason it passes preflight everywhere else
    # in this module.
    case = _load_case("m-opt-lock-012")
    healthy_row: Row = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    main_connection: _CapabilityLessConnection | _ScriptedPort = (
        _CapabilityLessConnection() if main_defective else _ScriptedPort(read_rows=[[healthy_row]])
    )
    peer_connection: _CapabilityLessConnection | _ScriptedPort = (
        _CapabilityLessConnection() if peer_defective else _ScriptedPort(read_rows=[[healthy_row]])
    )

    with pytest.raises(engine.EngineError, match="refuses to start") as exc_info:
        engine.run_interleaved_scenario_case(
            case, "postgres", cast("Any", main_connection), lambda: cast("Any", peer_connection)
        )

    message = str(exc_info.value)
    for label in expected_labels:
        assert label in message

    # No worker thread ever started: a capability-less connection's own
    # `execute` was never called, and a HEALTHY counterpart (`_ScriptedPort`)
    # never executed anything either — the refusal happens strictly before
    # either thread is even constructed.
    for connection in (main_connection, peer_connection):
        if isinstance(connection, _CapabilityLessConnection):
            assert connection.execute_calls == 0
        else:
            assert connection.reads == []
            # A healthy peer opened via `peer_factory` is still cleaned up
            # on refusal even though nothing ran; a healthy MAIN connection
            # is the caller's own port and is left untouched either way.
            if connection is peer_connection:
                assert connection.closed


class _AllRungsRaiseConnection:
    """A structurally-plausible port whose EVERY runtime rung RAISES: a
    CALLABLE `close()`, a CALLABLE `cancel()`, and an underlying
    `connection` seam with a CALLABLE `close()` AND `fileno()` too — every
    one of those IS callable, so a merely structural check would PASS it
    (`preflight=('validated',)`, `helper_completed=False`). No trust
    marker, not a `PostgresAdapter` — the trust preflight must refuse it
    WITHOUT EVER CALLING a single one of the raising methods below (a pure
    trust check, never a behavioral probe): `calls` staying empty is this
    pin's own proof that no worker thread ever got far enough to discover
    any of this."""

    class _Underlying:
        def __init__(self, calls: list[str]) -> None:
            self._calls = calls

        def close(self) -> None:  # pragma: no cover - never reached; preflight refuses first
            self._calls.append("underlying.close")
            raise RuntimeError("underlying close raises")

        def fileno(self) -> int:  # pragma: no cover - never reached; preflight refuses first
            self._calls.append("underlying.fileno")
            raise RuntimeError("underlying fileno raises")

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.connection = self._Underlying(self.calls)

    def close(self) -> None:  # pragma: no cover - never reached; preflight refuses first
        self.calls.append("close")
        raise RuntimeError("close raises")

    def cancel(self) -> None:  # pragma: no cover - never reached; preflight refuses first
        self.calls.append("cancel")
        raise RuntimeError("cancel raises")

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:  # pragma: no cover
        self.calls.append("execute")
        return []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        self.calls.append("execute_write")
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        self.calls.append("transaction")
        return body(self)


def test_run_interleaved_scenario_case_refuses_before_any_worker_starts_all_rungs_raising() -> None:
    # A structurally-plausible port whose EVERY
    # runtime termination rung raises — a shape a merely structural
    # preflight check would pass, hanging the unbounded post-ladder join —
    # must be refused BEFORE either worker thread starts, and the refusal
    # must never invoke a single one of its raising methods.
    case = _load_case("m-opt-lock-012")
    healthy_row: Row = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    main_connection = _AllRungsRaiseConnection()
    peer_connection = _ScriptedPort(read_rows=[[healthy_row]])

    with pytest.raises(engine.EngineError, match="refuses to start") as exc_info:
        engine.run_interleaved_scenario_case(
            case, "postgres", cast("Any", main_connection), lambda: cast("Any", peer_connection)
        )

    assert "main connection" in str(exc_info.value)
    # No worker thread ever started: not one of this port's structurally
    # -plausible-but-lying methods was ever invoked, and the healthy peer
    # (still opened via `peer_factory`) never executed anything either.
    assert main_connection.calls == []
    assert peer_connection.reads == []
    assert peer_connection.closed


class _RungOneOnlyConnection:
    """A connection exposing a CALLABLE `close()` and nothing else — a merely
    structural check would accept a shape like this, but the trust preflight
    refuses it anyway, because a callable capability is never the same as a
    DECLARED trust contract. Reused
    directly by `_terminate_connection`'s own ladder-mechanics pins below,
    which bypass preflight entirely — proving the ladder itself is
    untouched by the trust gate."""

    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _RungTwoOnlyConnection:
    """Exposes NO outer `close()` at all, only an underlying `connection`
    seam whose OWN `close()` is callable — mirrors
    `PostgresAdapter.connection`'s own escalation seam, WITHOUT declaring
    the trust contract: refused by preflight for that reason
    alone, even though `_terminate_connection`'s own ladder (bypassing
    preflight, below) can act on it."""

    class _Underlying:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    def __init__(self) -> None:
        self.connection = self._Underlying()


class _RungThreeOnlyConnection:
    """Exposes NO outer `close()`, and an underlying `connection` seam
    with NEITHER a `close()` NOR anything but a callable `fileno()` — the
    OS-socket-only shape, undeclared and so refused by preflight the same
    way. Structural only: real OS-level socket teardown
    (`_terminate_underlying_socket`) is real-transport-only and exercised
    solely by the Docker lane, mirroring that function's own documented
    scope."""

    class _Underlying:
        def fileno(self) -> int:  # pragma: no cover - structural probe, never invoked
            raise NotImplementedError

    def __init__(self) -> None:
        self.connection = self._Underlying()


class _CancelOnlyConnection:
    """Exposes ONLY `cancel()` — `_cancel_in_flight_work`'s own
    best-effort rung, never a termination-ladder rung at all — refused by
    preflight for the SAME reason every undeclared shape here is: no trust
    grant, regardless of which capability it happens to carry."""

    def cancel(self) -> None:  # pragma: no cover - structural probe, never invoked
        pass


@pytest.mark.parametrize(
    "connection",
    [
        _RungOneOnlyConnection(),
        _RungTwoOnlyConnection(),
        _RungThreeOnlyConnection(),
        _CancelOnlyConnection(),
    ],
)
def test_validate_termination_trust_refuses_an_undeclared_but_healthy_shape(
    connection: object,
) -> None:
    # Round 5's own deepened contract: a WORKING capability — even exactly
    # the shape the termination ladder itself can act on — is refused when
    # nothing DECLARES the trust contract. Trust is never inferred from
    # shape or behavior, only granted by `PostgresAdapter`'s own
    # known-deterministic type or an explicit marker.
    defects = engine._validate_termination_trust(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        connection, "main connection"
    )
    assert len(defects) == 1
    assert "main connection" in defects[0]


def test_terminate_connection_succeeds_on_the_rung_one_only_shape() -> None:
    # `_terminate_connection`'s own ladder mechanics are untouched by round
    # 5's correction: this bypasses preflight entirely (mirroring
    # `_await_interleaved_workers`'s own direct pins above) and exercises
    # rung one (outer `close()`) directly.
    connection = _RungOneOnlyConnection()
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        connection, "main connection"
    )
    assert failures == []
    assert connection.close_calls == 1


def test_terminate_connection_succeeds_on_the_rung_two_only_shape() -> None:
    # Rung two (the underlying `connection` seam's own `close()`), bypassing
    # preflight the same way. The ladder still RECORDS rung one's own miss
    # (no outer `close()`) as trail context even though rung two succeeds
    # and actually terminates the connection — `_terminate_connection`'s
    # own documented contract ("every miss and every raise is RECORDED",
    # never a bare success/failure flag) — so what proves the ladder ACTED
    # on this shape is the underlying seam's own `close()` firing, not an
    # empty trail.
    connection = _RungTwoOnlyConnection()
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        connection, "main connection"
    )
    assert failures == ["main connection: connection exposes no close() capability"]
    assert connection.connection.close_calls == 1


class _FakeAdaptersRegistry:
    """A `connection.adapters` stand-in — just enough for
    `PostgresAdapter.__init__`'s own `register_loader` call — mirroring
    `test_postgres_adapter.py`'s own `_FakeAdapters`."""

    def register_loader(self, name: str, loader: object) -> None:
        pass


class _FakePsycopgConnection:
    """A minimal `psycopg.Connection` stand-in carrying only what
    `PostgresAdapter.__init__` touches — proving the real-type
    trust rule needs no live database at all: `isinstance` against the
    concrete `PostgresAdapter` class is what grants trust, never anything
    this fake's own connection does."""

    def __init__(self) -> None:
        self.adapters = _FakeAdaptersRegistry()


def test_validate_termination_trust_accepts_the_postgres_adapter_shape() -> None:
    # The known-deterministic real type (the OTHER trust path,
    # alongside the documented marker): the SAME concrete class
    # `provision.py`'s own `Provisioner.port` constructs, trusted BY
    # CONSTRUCTION — no marker required, nothing beyond `isinstance`
    # inspected.
    from parallax.postgres import PostgresAdapter

    adapter = PostgresAdapter(cast("Any", _FakePsycopgConnection()))
    assert (
        engine._validate_termination_trust(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            adapter, "main connection"
        )
        == []
    )


def test_require_interleaved_termination_capability_trusts_the_postgres_adapter_peer_too() -> None:
    # `provision.py`'s own `Provisioner.port` AND `Provisioner.peer()` both
    # construct this SAME concrete class (the peer seam) — the preflight
    # entry point trusts BOTH positions without
    # a marker, never raising.
    from parallax.postgres import PostgresAdapter

    main_connection = PostgresAdapter(cast("Any", _FakePsycopgConnection()))
    peer_connection = PostgresAdapter(cast("Any", _FakePsycopgConnection()))
    engine._require_interleaved_termination_capability(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        main_connection, peer_connection, "m-unit-work-999-synthetic.yaml"
    )


def test_require_interleaved_termination_capability_accepts_a_marked_fake() -> None:
    # The documented marker mechanism: a fake that DECLARES the
    # deterministic-termination contract passes preflight even though this
    # module never inspects its close()/fileno() shape at all — proven with
    # `_ScriptedPort`, which carries the marker (see its own docstring).
    # `run_interleaved_scenario_case`'s own entry-point pins above already
    # exercise the full helper path past this preflight; this pin isolates
    # the marker's own acceptance at the entry point itself.
    engine._require_interleaved_termination_capability(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        cast("Any", _ScriptedPort()), cast("Any", _ScriptedPort()), "m-unit-work-999-synthetic.yaml"
    )


def test_group_tx_instant_falls_back_to_inert_when_the_group_has_no_write() -> None:
    # A `uow` group of find-only steps (never reachable via the current corpus
    # — every group this round has a write) has no write entry to derive an
    # instant from, so the inert default stands in (ADR 0010: "a non-temporal
    # entry's clock value is inert, pick something deterministic").
    steps: list[dict[str, object]] = [
        {"uow": "a", "targetEntity": "Account", "find": {"eq": {"attr": "Account.id", "value": 1}}},
        {"uow": "a", "targetEntity": "Account", "find": {"eq": {"attr": "Account.id", "value": 1}}},
    ]
    assert (
        engine._group_tx_instant(steps, 0, 1)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        == engine._INERT_CLOCK_INSTANT  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    )


def test_versioned_non_temporal_version_attribute_is_none_for_a_temporal_entity() -> None:
    # A temporal entity observes a whole milestone rather than a version, so it has
    # no version attribute to resolve — `m-opt-lock`'s version column is a
    # non-temporal-only concept.
    meta = engine.load_case_metamodel(_load_case("m-navigate-012"))
    assert (
        engine._versioned_non_temporal_version_attribute(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            meta, "Policy"
        )
        is None
    )


_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_JUN = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_APR = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)

_POLICY = ObjectKey(EntityIdentity("parallax.compatibility", "Policy"), (("id", 1),))


def _policy_node(valid_start: dt.datetime, valid_end: object, name: str) -> Any:
    """One node a grouped find of a bitemporal `Policy` published: production's
    own identity and Observation Key for it, beside the milestone it is."""
    members: dict[str, object] = {
        "id": 1,
        "name": name,
        "validStart": valid_start,
        "validEnd": valid_end,
        "txStart": _APR,
        "txEnd": INFINITY,
    }
    return engine._ObservedNode(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        object_key=_POLICY,
        observation_key=ObservationKey(_POLICY, Edge(valid_time=valid_start, tx_time=_APR)),
        observation=TemporalObservation(predecessor=PredecessorRow(members=members)),
    )


def _settled(source: Any) -> Any:
    return engine._settled_against_source(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        "Policy", _POLICY, source
    )


def test_a_settled_write_settles_against_the_node_the_named_find_observed() -> None:
    # A milestone chain holds more than one row per primary key, so one find may
    # return several and each is evidence about the milestone it actually is. The
    # write settles against the ONE its own `on` reference named — carrying the
    # slot the unit of work filed that node under, so the real write reaches
    # production's own record rather than a coordinate this engine re-derived.
    head = _policy_node(_JAN, _JUN, "head")
    tail = _policy_node(_JUN, INFINITY, "tail")
    for node, expected in ((head, "head"), (tail, "tail")):
        key, observation = _settled((node,))
        assert key == node.observation_key
        assert isinstance(observation, TemporalObservation)
        assert observation.predecessor.members["name"] == expected


def test_a_settled_write_refuses_a_find_that_observed_no_row_of_its_key() -> None:
    # The reference names evidence that does not exist — an authoring defect,
    # refused where the diagnosis can name it rather than silently unobserved.
    with pytest.raises(engine.EngineError, match="settles against observed 0 rows"):
        _settled(())


def test_a_settled_write_refuses_a_find_that_observed_several_rows_of_its_key() -> None:
    # No single value could have come from two milestones, so a reference that
    # resolves to both names nothing a write could have been handed.
    with pytest.raises(engine.EngineError, match="settles against observed 2 rows"):
        _settled((_policy_node(_JAN, _JUN, "head"), _policy_node(_JUN, INFINITY, "tail")))


def test_a_write_step_naming_no_find_settles_against_tracked_state() -> None:
    assert (
        engine._source_find_milestones(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": []}, 2, {}
        )
        is None
    )


def test_a_source_find_reference_names_one_index() -> None:
    with pytest.raises(engine.EngineError, match="settles against ONE find step"):
        engine._source_find_milestones(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": [], "on": [0, 1]}, 2, {}
        )


def test_a_source_find_reference_answers_what_that_find_observed() -> None:
    # A find of the same group that observed nothing observable — an unversioned
    # or non-temporal target — still answers, with an empty record: the reference
    # resolved, and it is the WRITE's own resolution that then finds no milestone.
    assert (
        engine._source_find_milestones(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": [], "on": 1}, 2, {1: ()}
        )
        == ()
    )


def test_a_source_find_reference_names_a_find_of_its_own_group() -> None:
    # A reference the group's own recorded finds cannot satisfy names a step
    # outside the group, one that is not a find, or one that has not run yet —
    # refused rather than resolved to "the find observed nothing".
    with pytest.raises(engine.EngineError, match="not an EARLIER find step"):
        engine._source_find_milestones(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": [], "on": 0}, 2, {}
        )


def test_a_settled_write_targets_a_temporal_entity() -> None:
    # A versioned Non-Temporal target has one row per primary key, so its grouped
    # write already reaches its group's evidence by identity; the reference would
    # name nothing the resolution does not already have.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    with pytest.raises(engine.EngineError, match="a TEMPORAL entity"):
        engine._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": 5.00}]},
            meta,
            TemporalShadow(),
            set(),
            [],
            (),
        )


def _balance_node(tx_start: str, value: str) -> Any:
    """One node a grouped find of a Transaction-Time-Only `Balance` published."""
    key = ObjectKey(EntityIdentity("parallax.compatibility", "Balance"), (("id", 1),))
    start = dt.datetime.fromisoformat(tx_start)
    members: dict[str, object] = {
        "id": 1,
        "acctNum": "A",
        "value": decimal.Decimal(value),
        "txStart": start,
        "txEnd": INFINITY,
    }
    return engine._ObservedNode(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        object_key=key,
        observation_key=ObservationKey(key, Edge(tx_time=start)),
        observation=TemporalObservation(predecessor=PredecessorRow(members=members)),
    )


def test_a_settled_write_resolves_a_transaction_time_only_targets_named_milestone() -> None:
    # The arm an "is it temporal?" test cannot reach, and the one a Bitemporal-only
    # restriction would deny: a Transaction-Time-Only key holds one CURRENT
    # milestone but is read at as-of Transaction-Time coordinates resolving to
    # milestones of any age, so a group that reads the current milestone and then
    # reads the same key as of an earlier instant holds two pieces of evidence
    # about one key. The write settles against whichever find it names — which a
    # store keyed by identity alone could not answer, because the second read would
    # have erased the first.
    meta = engine.load_case_metamodel(_case("m-txtime-write-001"))
    current = _balance_node("2024-04-01T00:00:00+00:00", "100.00")
    historical = _balance_node("2024-01-01T00:00:00+00:00", "90.00")

    def settle(node: Any) -> object:
        write = engine._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"mutation": "update", "entity": "Balance", "rows": [{"id": 1, "value": 5.00}]},
            meta,
            TemporalShadow(),
            set(),
            [],
            (node,),
        )[0]
        assert write.execution_evidence == node.observation_key
        observation = write.oracle_observation
        assert isinstance(observation, TemporalObservation)
        return observation.predecessor.members["txStart"]

    assert settle(current) == current.observation.predecessor.members["txStart"]
    assert settle(historical) == historical.observation.predecessor.members["txStart"]


def test_run_scenario_case_settles_a_grouped_temporal_close_against_the_find_it_names() -> None:
    # m-unit-work-015: two finds of ONE bitemporal key observe two rectangles both
    # current on Transaction Time, and the write step names the first with `on`.
    # The evidence the write settles by is the Observation Key the unit of work
    # itself filed that node under, and the golden the oracle renders comes from
    # the same node's own milestone — so the close addresses R2's `thru_z`, which
    # a store keyed by identity alone could not have chosen between.
    port = FakeWritePort(
        find_rows=[
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("100.00"),
                "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "thru_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
                "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                "out_z": INFINITY,
            }
        ]
    )
    emissions, round_trips, _errors, log = engine.run_scenario_case(
        _load_case("m-unit-work-015"), "postgres", port
    )
    assert round_trips == 5
    assert log is not None and log.round_trips == 5
    # The close plus the two rectangles the split chains, all under the write
    # step's own pointer.
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/find",
        "/scenario/1/find",
        *["/scenario/2/write"] * 3,
    ]
    close = emissions[2]
    assert close.sql.startswith("update position set out_z = ?")
    # The close's address is the OBSERVED rectangle's own `thru_z`, derived from
    # the node the named find published — never the primary key alone.
    assert close.binds[2] == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def test_observed_nodes_refuses_an_output_that_is_not_a_graph() -> None:
    # A participating scenario find is graph-form: only the graph lane records the
    # evidence a later write settles against, so a row-form answer here would be a
    # find that observed nothing while reporting that it had.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    with pytest.raises(engine.EngineError, match="a participating scenario find is graph-form"):
        engine._observed_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            meta,
            engine.case_model(meta),
            "parallax.compatibility.Account",
            handle.NeutralRows(()),
        )


def test_observed_nodes_records_nothing_for_an_unversioned_non_temporal_target() -> None:
    # An unversioned, non-temporal target observes nothing at all (m-unit-work),
    # so the find publishes no evidence and a later write of it buffers bare.
    meta = engine.load_case_metamodel(_case("m-unit-work-003"))
    assert (
        engine._observed_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            meta,
            engine.case_model(meta),
            "parallax.compatibility.Order",
            handle.NeutralGraph((), Pin()),
        )
        == ()
    )


def test_observed_nodes_skips_a_node_the_unit_of_work_observed_nothing_of() -> None:
    # A node carrying no Observation Key is one the unit of work filed no evidence
    # for, so there is no slot a later write could settle against and it
    # contributes none.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    model = engine.case_model(meta)
    account = EntityIdentity("parallax.compatibility", "Account")
    node = handle.NeutralNode(entity=account, object_key=ObjectKey(account, (("id", 1),)))
    view = handle.NeutralNodeView(
        node=node,
        primary_key=(),
        family_variant=None,
        attributes={},
        value_objects={},
        relationships={},
    )
    assert (
        engine._observed_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            meta, model, "parallax.compatibility.Account", handle.NeutralGraph((view,), Pin())
        )
        == ()
    )


def test_observed_nodes_publishes_every_deep_fetch_level_and_walks_a_cycle_once() -> None:
    # A find observes every row it materialized, at the root and at every
    # deep-fetch level, and files a key for each. Reading only the roots would
    # discard evidence production recorded, so a later grouped write of an
    # INCLUDED object could not settle against it — the child here carries a
    # version of its own and appears in the result exactly once even though the
    # graph closes a cycle back through it.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    model = engine.case_model(meta)
    account = EntityIdentity("parallax.compatibility", "Account")
    version = AttributeIdentity(account, "version")
    peer = RelationshipIdentity(account, "peer")
    peers = RelationshipIdentity(account, "peers")
    owner = RelationshipIdentity(account, "owner")

    def view(
        pk: int,
        observed_version: int,
        relationships: dict[RelationshipViewKey, Any],
    ) -> handle.NeutralNodeView:
        key = ObjectKey(account, (("id", pk),))
        return handle.NeutralNodeView(
            node=handle.NeutralNode(
                entity=account, object_key=key, observation_key=ObservationKey(key, None)
            ),
            primary_key=(),
            family_variant=None,
            attributes={version: observed_version},
            value_objects={},
            relationships=relationships,
        )

    child_links: dict[RelationshipViewKey, Any] = {}
    child = view(2, 8, child_links)
    grandchild = view(3, 9, {})
    root = view(
        1,
        7,
        {
            RelationshipViewKey(peer): child,
            RelationshipViewKey(peers): (grandchild,),
            RelationshipViewKey(owner): None,
        },
    )
    child_links[RelationshipViewKey(peer)] = root  # the cycle back to the root

    observed = engine._observed_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        meta, model, "parallax.compatibility.Account", handle.NeutralGraph((root,), Pin())
    )
    assert [node.object_key.primary_key for node in observed] == [
        (("id", 1),),
        (("id", 2),),
        (("id", 3),),
    ]
    assert [cast("VersionObservation", node.observation).observed_version for node in observed] == [
        7,
        8,
        9,
    ]


def test_a_find_step_names_its_target_and_its_operation() -> None:
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    with pytest.raises(engine.EngineError, match="needs `targetEntity` and `find`"):
        engine._find_request(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"targetEntity": "Account"}, meta, engine.case_model(meta)
        )


def test_a_standalone_find_of_a_lockless_scenario_opens_no_transaction() -> None:
    # A scenario whose write steps are all READLESS predicate writes establishes
    # no observation for a lock to protect (`_scenario_needs_lock`), so its
    # verification finds are plain non-participating reads — no boundary, no lock
    # suffix.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    port = FakeWritePort(find_rows=[])
    result = engine._run_standalone_find(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        port,
        meta,
        engine.case_model(meta),
        dialect_for("postgres"),
        None,
        {"targetEntity": "Account", "find": {"eq": {"attr": "Account.id", "value": 1}}},
    )
    assert result.execution.round_trips == 1
    assert port.commits == 0 and port.rollbacks == 0
    assert not port.reads[0][0].endswith("for share of t0")


def test_the_aborting_port_passes_reads_and_writes_through() -> None:
    # It decorates the BOUNDARY alone: every statement still reaches the inner
    # port unchanged, so the DML a doomed unit of work flushes is the DML it would
    # have committed.
    inner = FakeWritePort(find_rows=[{"id": 1}])
    port = engine._AbortingPort(inner)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert port.execute("select 1", []) == [{"id": 1}]
    assert port.execute_write("update account set balance = ?", [1]) == 1
    assert inner.reads and inner.writes


def test_the_admitted_affected_guard_reraises_an_unadmitted_write_effect_error() -> None:
    # Every member of the family renders the same `actual` count, so admitting the
    # wrong one would report an identical observation whichever class the write
    # raised. Only the class the case's own declared facts imply is caught; every
    # other one propagates and fails the case.
    account = EntityIdentity("parallax.compatibility", "Account")
    target = KeyTarget(
        key_attributes=(AttributeIdentity(account, "id"),),
        key_values=((1,),),
    )

    def raises() -> int:
        raise StaleWriteError(account, target, expected=1, actual=0)

    with pytest.raises(StaleWriteError):
        engine._admitted_affected(MissingTargetError, raises)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly


class _FailingClosePort(FakeWritePort):
    """A port whose temporal CLOSE raises a translated transient failure — the
    case's own out-of-band `given.apply` writer still lands, so the failure is
    the close's own rather than the arrangement's."""

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        affected = super().execute_write(sql, binds)
        # The case's own `given.apply` writer runs first and binds nothing; the
        # close is the parameterized statement.
        if binds:
            raise DatabaseError(
                category="deadlock", native_code="40P01", message="deadlock detected"
            )
        return affected


def test_run_conflict_case_temporal_close_propagates_a_failed_call() -> None:
    # A close the port could not complete is recorded as a FAILED Database Call
    # and then propagates: the lane admits only the shortfall class the case's own
    # facts imply, and a transient database failure is not one.
    with pytest.raises(DatabaseError):
        engine.run_conflict_case(_load_case("m-temporal-read-010"), "postgres", _FailingClosePort())


def test_run_write_sequence_case_executes_each_entry_as_its_own_transaction() -> None:
    # Each writeSequence entry is its
    # OWN `db.transact` unit, never the whole sequence in one transaction.
    port = FakeWritePort()
    emissions, table_state, round_trips = engine.run_write_sequence_case(
        _case("m-unit-work-003"), "postgres", port
    )
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/writeSequence/0", "/writeSequence/1"]
    assert len(port.writes) == 2 and port.commits == 2
    # The committed table state is read back for every model table (the
    # m-conformance-adapter write-sequence observation); the read-back is an
    # observation, so it never counts toward the case's round trips.
    assert set(table_state) == {
        "orders",
        "order_item",
        "order_status",
        "order_tag",
        "order_note",
    }


def test_run_write_sequence_case_carries_the_temporal_observation_on_the_buffered_write() -> None:
    # m-txtime-write-002: the update entry's shadow-resolved observation rides to
    # planning on the buffered write itself, through the documented neutral seam
    # (`Transaction._buffer`'s `observation=` route, `_execute_write_unit`) —
    # exactly what a real caller's own prior find would have resolved for it.
    port = FakeWritePort()
    emissions, table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-txtime-write-002"), "postgres", port
    )
    assert round_trips == 3
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert len(port.writes) == 3 and port.commits == 2
    assert table_state is not None and "balance" in table_state


def test_run_write_sequence_case_buffers_a_bounded_bitemporal_valid_time_window() -> None:
    # m-bitemp-write-001: the updateUntil entry's
    # canonical instruction carries BOTH `validFrom` and `until`
    # (its bounded rectangle-split window) — `_execute_write_unit` threads both
    # onto the neutral `Transaction._buffer` route unchanged.
    port = FakeWritePort()
    _emissions, table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-bitemp-write-001"), "postgres", port
    )
    assert round_trips == 5
    assert len(port.writes) == 5 and port.commits == 2
    assert table_state is not None and "position" in table_state


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
# The observation-binding discriminator (`engine._binds_row_observations`) is #
# derived SEMANTICALLY — mutation kind, versioned-ness, pk-gen management,    #
# and (for update) per-key value uniformity                                   #
# — never from the case's own authored `statements` count, which is a         #
# count-consistency ASSERTION the real plan verifies independently            #
# (`_check_statement_count_consistency`). A structured predicate-write        #
# instruction reaching this seam refuses loudly, never a bare `KeyError`.     #
# --------------------------------------------------------------------------- #
def test_versioned_delete_decomposes_per_row() -> None:
    # m-batch-write-004's own shape: a versioned entity's multi-row delete
    # decomposes per row — each row is removed under its own prior observation,
    # so `batch_write.delete_collapses` refuses to collapse it — regardless of
    # the authored `statements` count matching `len(rows)` (which it does here
    # too — the discriminator does not consult it either way). The default
    # locking mode renders each key ungated.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "delete",
                        "entity": "Account",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "observedVersion": 1},
                            {"id": 2, "observedVersion": 1},
                        ],
                    }
                ]
            }
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 2
    assert [(e.sql, e.binds) for e in emissions] == [
        ("delete from account where id = ?", (1,)),
        ("delete from account where id = ?", (2,)),
    ]


def test_an_insert_row_authoring_an_observed_version_is_refused() -> None:
    # `m-unit-work`: inserts have no observation. The case schema's `writeRow`
    # says so in prose ("absent on a versioned insert") but shares one definition
    # across every mutation, so an insert row can author the reserved key anyway;
    # this engine refuses it rather than handing planning evidence about a
    # milestone that does not yet exist. The refusal is an authoring diagnosis,
    # not the structural guarantee — the carrier itself refuses an insert too.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Account",
                        "statements": 1,
                        "rows": [{"id": 1, "version": 1, "observedVersion": 1}],
                    }
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="an insert row authors no `observedVersion`"):
        engine.compile_write_sequence_case(case, "postgres")


def test_a_write_row_authoring_an_observed_tx_start_is_refused_even_when_versioned() -> None:
    # `observedTxStart` is not a write-row key in any shape: the case schema's
    # `writeRow` reserves `observedVersion` alone, and a temporal close's observed
    # `txStart` gate is authored beside the write (`when.observedTxStart`, or a
    # retry attempt's own field — `m-case-format`). A versioned target is the case
    # that hides the defect: it HAS an observation, so a refusal that only asks
    # whether the target is observable at all admits the token and then discards
    # it, letting the write advance its version while the Transaction-Time gate
    # the author wrote is silently ignored.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Account",
                        "statements": 1,
                        "rows": [
                            {
                                "id": 1,
                                "balance": 10.00,
                                "observedVersion": 7,
                                "observedTxStart": "2024-01-01T00:00:00+00:00",
                            }
                        ],
                    }
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="a write row authors no `observedTxStart`"):
        engine.compile_write_sequence_case(case, "postgres")


def test_an_unversioned_row_authoring_an_observation_control_key_is_refused() -> None:
    # `m-unit-work`: unversioned Non-Temporal writes have no observation, and the
    # case schema's `writeRow` says the same ("absent on ... a non-versioned
    # write") without being able to express it. Accepted, the key would wrap an
    # unversioned Wallet update in an observation carrier: the planner ignores it
    # (there is no version attribute to advance) but batching still excludes the
    # carrier, so these UNIFORM rows would emit two statements where the same
    # rows without the key collapse to one `IN`-list statement.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": 500.00, "observedVersion": 1},
                            {"id": 2, "balance": 500.00, "observedVersion": 1},
                        ],
                    }
                ]
            },
        },
    )
    with pytest.raises(engine.EngineError, match="an unversioned row authors no `observedVersion`"):
        engine.compile_write_sequence_case(case, "postgres")


def test_uniform_multi_row_update_collapses_to_one_in_list_statement() -> None:
    # m-batch-write-001's own update entry: an UNVERSIONED target whose rows
    # assign the SAME value collapses into ONE multi-row `IN`-list UPDATE
    # (m-batch-write "Set-based flush").
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Wallet",
                        "statements": 1,
                        "rows": [
                            {"id": 10, "balance": 500.00},
                            {"id": 11, "balance": 500.00},
                        ],
                    }
                ]
            },
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 1
    assert [e.sql for e in emissions] == ["update wallet set balance = ? where id in (?, ?)"]
    assert emissions[0].binds == (500.00, 10, 11)


def test_a_collapsed_multi_row_insert_decodes_its_wire_floats_before_real_execution() -> None:
    # m-batch-write-001's own insert shape, run for real (never through the
    # separate pure re-lowering `test_uniform_multi_row_update_collapses_to_
    # one_in_list_statement` grades): the case authors `decimal` balances as
    # wire-spelled floats, and the collapsed multi-row instruction has no
    # single-row `Transaction._buffer` route to decode through, so it must be
    # decoded before it ever reaches the unit of work directly.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Wallet",
                        "statements": 1,
                        "rows": [
                            {"id": 10, "owner": "Mira", "balance": 100.00},
                            {"id": 11, "owner": "Omar", "balance": 20.00},
                        ],
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    _emissions, _table_state, round_trips = engine.run_write_sequence_case(case, "postgres", port)
    assert round_trips == 1
    assert len(port.writes) == 1
    sql, binds = port.writes[0]
    assert sql == "insert into wallet(id, owner, balance) values (%s, %s, %s), (%s, %s, %s)"
    assert binds == [10, "Mira", decimal.Decimal("100.0"), 11, "Omar", decimal.Decimal("20.0")]
    assert isinstance(binds[2], decimal.Decimal) and isinstance(binds[5], decimal.Decimal)


def test_collapse_eligible_insert_entry_partitions_by_physical_slot_selection() -> None:
    # Collapse ELIGIBILITY is a property of the target alone, so a Wallet insert
    # entry never decomposes per row — but its rows still carry two different
    # filtered slot selections (the second omits the nullable `balance`). The
    # entry reaches the planner as individually buffered rows, which the SAME
    # batch grouping every write path uses partitions into two statements
    # (m-sql "Physical DML ordering") instead of one illegal mixed-shape insert.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 10, "owner": "Mira", "balance": 100.00},
                            {"id": 11, "owner": "Omar"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 2
    assert [e.sql for e in emissions] == [
        "insert into wallet(id, owner, balance) values (?, ?, ?)",
        "insert into wallet(id, owner) values (?, ?)",
    ]
    assert [e.binds for e in emissions] == [(10, "Mira", 100.00), (11, "Omar")]


def test_update_entry_uniform_within_each_physical_group_collapses_per_group() -> None:
    # An entry whose rows are non-uniform TAKEN AS A WHOLE, yet uniform WITHIN
    # each physical group: the first two rows assign only `balance`, the last
    # two only `owner`. Batch grouping partitions them into two runs before
    # collapse eligibility is asked of either (m-sql "Physical DML ordering"),
    # and each run's own rows ARE uniform, so both collapse into one `IN`-list
    # UPDATE (m-batch-write "Set-based flush"). The authored `statements: 2`
    # must agree with that per-group accounting, not with the row count.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": 500.00},
                            {"id": 2, "balance": 500.00},
                            {"id": 3, "owner": "Zed"},
                            {"id": 4, "owner": "Zed"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 2
    assert [e.sql for e in emissions] == [
        "update wallet set balance = ? where id in (?, ?)",
        "update wallet set owner = ? where id in (?, ?)",
    ]
    assert [e.binds for e in emissions] == [(500.00, 1, 2), ("Zed", 3, 4)]


def test_update_entry_non_uniform_within_a_physical_group_rejects_a_grouped_count() -> None:
    # The same two physical groups as above, but each group's own rows assign
    # DIFFERENT values, so neither collapses and the entry emits one keyed
    # UPDATE per row. `statements` stays a real assertion: an authored count of
    # 2 (the group count, not the statement count) is an authoring error and
    # refuses loudly rather than being accepted as "close enough".
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": 111.00},
                            {"id": 2, "balance": 222.00},
                            {"id": 3, "owner": "Zed"},
                            {"id": 4, "owner": "Ada"},
                        ],
                    }
                ]
            },
        },
    )
    with pytest.raises(engine.EngineError, match="does not match the 4 statement"):
        engine.compile_write_sequence_case(case, "postgres")


def test_non_uniform_multi_row_update_decomposes_per_distinct_key() -> None:
    # m-batch-write-002's own shape: non-uniform per-key values decompose into
    # one UPDATE per distinct key — genuinely lowering end to end (neither
    # versioned nor pk-gen-managed, so neither needs the multi-row refusal).
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": 111.00},
                            {"id": 2, "balance": 222.00},
                        ],
                    }
                ]
            },
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 2
    assert [e.sql for e in emissions] == [
        "update wallet set balance = ? where id = ?",
        "update wallet set balance = ? where id = ?",
    ]


def test_pk_gen_managed_insert_decomposes_per_row_even_with_literal_ids() -> None:
    # m-pk-gen-008's own shape: a `sequence`-strategy target's rows already
    # carry LITERAL, pre-resolved ids (no `{computed: ...}` marker — the
    # registry-read block reservation resolved them upstream). The ENTITY's
    # own pk-generator strategy, not the row's shape, drives decomposition:
    # each row's key allocation is independent, so this seam lowers each as
    # its own single-row insert.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/pk-sequence.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Pass",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "zone": "north"},
                            {"id": 2, "zone": "south"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 2
    assert [e.sql for e in emissions] == [
        "insert into pass(id, zone) values (?, ?)",
        "insert into pass(id, zone) values (?, ?)",
    ]


def test_elided_no_op_row_is_not_counted_as_a_statement() -> None:
    # A versioned UPDATE row that assigns nothing but its own primary key has an
    # EMPTY effective change set, so the planner's elision stage drops it
    # (m-opt-lock: a versioned update that changes no attribute issues no DML).
    # The authored count grades the statements the flush actually emits, so this
    # entry is ONE statement — the surviving `balance` update — not two.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Account",
                        "statements": 1,
                        "rows": [
                            {"id": 1, "observedVersion": 1},
                            {"id": 2, "balance": 5.00, "observedVersion": 1},
                        ],
                    }
                ]
            }
        },
    )
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 1
    assert [e.sql for e in emissions] == [
        "update account set balance = ?, version = ? where id = ?"
    ]
    assert emissions[0].binds == (5.00, 2, 2)


def test_an_entry_whose_every_row_elides_emits_no_statement() -> None:
    # Every row of the entry is a versioned primary-key-only no-op, so the whole
    # entry elides to NO DML. The derived count is 0, which no authored count can
    # match (`statements` is constrained to at least 1), so an authored count
    # still refuses loudly rather than silently passing on an empty flush.
    rows = [{"id": 1, "observedVersion": 1}, {"id": 2, "observedVersion": 1}]
    silent = _synthetic_write(
        "writeSequence",
        {"when": {"writeSequence": [{"mutation": "update", "entity": "Account", "rows": rows}]}},
    )
    emissions, round_trips = engine.compile_write_sequence_case(silent, "postgres")
    assert round_trips == 0
    assert emissions == []
    counted = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {"mutation": "update", "entity": "Account", "statements": 1, "rows": rows}
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="does not match the 0 statement"):
        engine.compile_write_sequence_case(counted, "postgres")


def test_authored_statement_count_mismatch_is_rejected() -> None:
    # `statements` is a count-consistency ASSERTION
    # (`compatibility-case.schema.json`), verified independently of the
    # derived instruction count — never the discriminator itself. Two rows of a
    # versioned delete (which decomposes regardless), each carrying its own
    # `observedVersion`, authored with a WRONG `statements: 1`.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "delete",
                        "entity": "Account",
                        "statements": 1,
                        "rows": [
                            {"id": 1, "observedVersion": 1},
                            {"id": 2, "observedVersion": 1},
                        ],
                    }
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="does not match"):
        engine.compile_write_sequence_case(case, "postgres")


def test_predicate_shaped_scenario_write_lowers_readless_not_a_keyerror() -> None:
    # `m-batch-write-005`'s shape: a structured PREDICATE-write instruction
    # (`target`/`predicate`) reaching the scenario compile lane is never
    # mistaken for a keyed-write entry list (no bare `KeyError`) — it lowers
    # readless end to end.
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/wallet.yaml",
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Wallet",
                                "predicate": {
                                    "lessThan": {"attr": "Wallet.balance", "value": 200.00}
                                },
                            },
                        }
                    }
                ]
            },
        },
    )
    emissions, round_trips = engine.compile_scenario_case(case, "postgres")
    assert round_trips == 1
    assert [e.sql for e in emissions] == ["delete from wallet where balance < ?"]
    assert emissions[0].binds == (200.00,)


def test_predicate_shaped_write_sequence_entry_refuses_loudly() -> None:
    # Defensive coverage for the writeSequence path: the writeSequence entry
    # vocabulary is keyed-only (`m-case-format`) — a structured predicate
    # instruction is scenario-write-only, so `_build_instructions` refuses it
    # loudly rather than a bare `KeyError('entity')`.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "delete",
                        "target": {
                            "entity": "Wallet",
                            "predicate": {"lessThan": {"attr": "Wallet.balance", "value": 200.00}},
                        },
                    }
                ]
            },
        },
    )
    with pytest.raises(engine.EngineError, match=r"scenario-write-only"):
        engine.compile_write_sequence_case(case, "postgres")


def test_canonical_predicate_doc_preserves_valid_time_bounds_and_drops_at() -> None:
    # `at` is Clock context, never an instruction field. Valid-Time bounds
    # already use their canonical instruction spelling.
    doc = engine._canonical_predicate_doc(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        {
            "mutation": "terminateUntil",
            "target": {
                "entity": "Position",
                "predicate": {"eq": {"attr": "Position.id", "value": 1}},
            },
            "at": "2024-10-01T00:00:00+00:00",
            "validFrom": "2024-07-01T00:00:00+00:00",
            "until": "2024-09-01T00:00:00+00:00",
        }
    )
    assert "at" not in doc
    assert doc["validFrom"] == "2024-07-01T00:00:00+00:00"
    assert doc["until"] == "2024-09-01T00:00:00+00:00"


def test_run_scenario_case_executes_a_readless_predicate_write() -> None:
    # `m-batch-write-005`'s own shape, run end to end (no Docker): an
    # unversioned, non-temporal target's predicate delete buffers through
    # `Transaction.write_neutral` and lowers to ONE readless
    # statement — `_run_readless_predicate_write`'s own production seam.
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/wallet.yaml",
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Wallet",
                                "predicate": {
                                    "lessThan": {"attr": "Wallet.balance", "value": 200.00}
                                },
                            },
                        }
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    emissions, round_trips, _errors, _log = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 1
    assert emissions[0].case_pointer == "/scenario/0/write"
    assert emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1 and port.commits == 1


def test_run_scenario_case_executes_a_materializing_predicate_write_pair() -> None:
    # A VERSIONED target's predicate delete MATERIALIZES (ADR 0014): the
    # scenario's own preceding find step pairs with it
    # (`_run_materializing_pair`), resolving through the SAME `FakeWritePort`
    # connection the subsequent per-row delete commits on — no Docker. The
    # default locking mode renders each key ungated.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "targetEntity": "Account",
                        "find": {"lessThan": {"attr": "Account.balance", "value": 200.00}},
                    },
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Account",
                                "predicate": {
                                    "lessThan": {"attr": "Account.balance", "value": 200.00}
                                },
                            },
                        }
                    },
                ]
            },
        },
    )
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    emissions, round_trips, _errors, _log = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find", "/scenario/1/write"]
    assert emissions[1].sql == "delete from account where id = ?"
    assert len(port.writes) == 1 and len(port.reads) == 1 and port.commits == 1


def test_run_scenario_case_readless_predicate_write_rollback_aborts_but_counts_the_round_trip() -> (
    None
):
    # `_run_readless_predicate_write`'s own abort contract mirrors the keyed-
    # write one (`test_run_scenario_case_rollback_step_aborts_but_counts_the_
    # round_trip`): the golden DML still executes (and counts its round trip)
    # before the forced flush + intentional abort discards it.
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/wallet.yaml",
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Wallet",
                                "predicate": {
                                    "lessThan": {"attr": "Wallet.balance", "value": 200.00}
                                },
                            },
                        },
                        "rollback": True,
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    emissions, round_trips, _errors, _log = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 1
    assert emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1
    assert port.commits == 0 and port.rollbacks == 1


def test_materializing_predicate_write_rollback_aborts_but_counts_the_round_trip() -> None:
    # `_run_materializing_pair`'s own abort contract: the resolve AND the
    # per-row DML its observations license still execute (and count their round
    # trips) before the forced flush + intentional abort discards them —
    # `_run_uow_group`'s doomed-group behavior, reproduced for a
    # materializing pair's own single held transaction.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "targetEntity": "Account",
                        "find": {"lessThan": {"attr": "Account.balance", "value": 200.00}},
                    },
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Account",
                                "predicate": {
                                    "lessThan": {"attr": "Account.balance", "value": 200.00}
                                },
                            },
                        },
                        "rollback": True,
                    },
                ]
            },
        },
    )
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    emissions, round_trips, _errors, _log = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find", "/scenario/1/write"]
    assert emissions[1].sql == "delete from account where id = ?"
    assert len(port.writes) == 1 and len(port.reads) == 1
    assert port.commits == 0 and port.rollbacks == 1


def test_is_materializing_write_step_returns_none_for_a_keyed_write_shape() -> None:
    # `_is_materializing_write_step`'s SHAPE guard: a keyed-write step's
    # `write` field is the buffered-entry LIST (`m-case-format`'s
    # `bufferedWriteSequence` shape) — never a `PredicateWrite` pairing
    # candidate. Peeked by the scenario run lane's own one-step look-ahead
    # (`run_scenario_case`); no reachable corpus scenario puts an ungrouped
    # find immediately before an ungrouped keyed write (every such adjacency
    # is either `uow`-grouped or predicate-shaped), so this pins the guard
    # directly at the function level.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    step: Mapping[str, object] = {
        "write": [{"mutation": "insert", "entity": "Account", "rows": [{"id": 1}]}]
    }
    assert (
        engine._is_materializing_write_step(step, meta)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        is None
    )


def test_is_materializing_write_step_returns_none_for_a_non_predicate_mapping() -> None:
    # Defensive coverage: a `write` field that IS a mapping but deserializes
    # to something other than a `PredicateWrite` (never schema-legal — the
    # mapping `write` shape is `predicateWrite`-only, `m-case-format`) still
    # falls through to `None` rather than an assertion failure.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    step: Mapping[str, object] = {
        "write": {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": 1.0}]}
    }
    assert (
        engine._is_materializing_write_step(step, meta)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        is None
    )


def test_run_materializing_pair_rejects_a_mismatched_preceding_find_target() -> None:
    # `_run_materializing_pair`'s own internal target-match guard: its SOLE
    # production caller (`run_scenario_case`'s look-ahead) already verifies
    # `find_step["targetEntity"] == pairing.target.entity` before ever
    # calling this function, so the guard is unreachable through the public
    # entry point — a genuine caller-contract defense, pinned here by
    # calling the function directly with a manufactured mismatch.
    from parallax.core.dialect import POSTGRES

    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    steps: list[Mapping[str, object]] = [
        {"targetEntity": "Wallet", "find": {"eq": {"attr": "Wallet.id", "value": 1}}},
        {
            "write": {
                "mutation": "delete",
                "target": {
                    "entity": "Account",
                    "predicate": {"lessThan": {"attr": "Account.balance", "value": 200.00}},
                },
            }
        },
    ]
    with pytest.raises(engine.EngineError, match="not preceded by"):
        engine._run_materializing_pair(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            FakeWritePort(), meta, POSTGRES, "locking", steps, 0
        )


def test_run_scenario_case_rejects_a_materializing_pair_whose_find_predicate_differs() -> None:
    # (`m-case-format.md:715`/`:719`): the preceding find must share
    # the write's own target predicate, not merely its entity — unlike the
    # entity-mismatch guard above, this IS reachable through the public
    # `run_scenario_case` entry point: the look-ahead pairing decision
    # (`run_scenario_case`) checks only `targetEntity`, so a same-entity,
    # DIFFERENT-predicate pair still routes into `_run_materializing_pair`,
    # whose own canonical-operation comparison is what catches it.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "targetEntity": "Account",
                        "find": {"eq": {"attr": "Account.balance", "value": 100.00}},
                    },
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Account",
                                "predicate": {
                                    "lessThan": {"attr": "Account.balance", "value": 200.00}
                                },
                            },
                        }
                    },
                ]
            },
        },
    )
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    with pytest.raises(engine.EngineError, match="SAME canonical operation"):
        engine.run_scenario_case(case, "postgres", port)


def test_run_write_sequence_case_wraps_a_lowering_error() -> None:
    # Defensive coverage: a `_LOWERING_ERRORS` member raised anywhere inside
    # the per-entry loop (here, `instructions.deserialize`'s own unknown-
    # entity `KeyError`) surfaces as this seam's own `EngineError`, never
    # propagating a bare driver/stdlib exception.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {"mutation": "insert", "entity": "Ghost", "statements": 1, "rows": [{"id": 1}]}
                ]
            }
        },
    )
    port = FakeWritePort()
    with pytest.raises(engine.EngineError, match="Ghost"):
        engine.run_write_sequence_case(case, "postgres", port)


# --------------------------------------------------------------------------- #
# Conflict — the optimistic-lock run lane (m-opt-lock):                        #
# single-attempt, given.apply, and when.attempts forms, each                   #
# driven against the fake in-memory port (no Docker; the real conflict/retry   #
# semantics against a reset database are the Docker-gated pg-full proof,       #
# `tests/compatibility/test_run_sweep.py::test_conflict_run_sweep`).           #
# --------------------------------------------------------------------------- #
def test_run_conflict_case_single_attempt() -> None:
    port = FakeWritePort()
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-006"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "account" in table_state


def test_run_conflict_case_applies_given_apply_out_of_band_first() -> None:
    port = FakeWritePort()
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-005"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    # given.apply's naive out-of-band bump, THEN the gated update.
    assert len(port.writes) == 2
    assert affected == 1  # the fake port always reports 1; the real 0-row
    # conflict proof runs against a reset database (test_conflict_run_sweep).
    assert table_state is not None


class _ZeroAffectedPort(FakeWritePort):
    """A port whose golden write reports a zero-row shortfall (a concurrent
    writer already moved or removed the row)."""

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        super().execute_write(sql, binds)
        return 0 if sql.startswith(("update account set", "delete from account where")) else 1


def test_run_conflict_case_renders_an_ungated_zero_row_delete_as_a_stale_write() -> None:
    # m-opt-lock-016: a locking-mode versioned DELETE renders no gate, so its
    # zero-row shortfall raises the NON-retriable StaleWriteError rather than an
    # optimistic conflict. The lane catches ONLY the class the case's own mode
    # implies, so the case's `affectedRows: 0` observation is reachable exactly
    # when the write classified its shortfall the way the mode requires.
    port = _ZeroAffectedPort()
    emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-016"), "postgres", port
    )
    assert [e.sql for e in emissions] == ["delete from account where id = ?"]
    assert affected == 0


def test_run_conflict_case_renders_a_gated_zero_row_update_as_a_conflict() -> None:
    port = _ZeroAffectedPort()
    _emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-005"), "postgres", port
    )
    assert affected == 0


class _ZeroAffectedClosePort(FakeWritePort):
    """A port whose golden milestone close reports a zero-row shortfall (the
    case's own `given.apply` already closed the current row out of band).

    Keyed on the DRIVER spelling of the golden close, so the naive literal
    `given.apply` statements the same lane applies first still report a row."""

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        super().execute_write(sql, binds)
        return 0 if sql.startswith("update balance set out_z = %s") else 1


def test_run_conflict_case_renders_an_ungated_zero_row_close_as_a_stale_write() -> None:
    # m-temporal-read-012: the locking-mode close renders its address and no gate,
    # so its shortfall is the non-retriable stale write — the temporal sibling of
    # the ungated versioned DELETE above, caught by the same one implied class.
    _emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-temporal-read-012"), "postgres", _ZeroAffectedClosePort()
    )
    assert affected == 0


def _unversioned_conflict_case(rows: list[dict[str, object]]) -> case_format.Case:
    return _synthetic_write(
        "conflict",
        {
            "model": "models/wallet.yaml",
            "when": {"uow": {"concurrency": "optimistic"}, "mutation": "update", "write": rows},
        },
    )


def test_a_conflict_attempt_row_authoring_an_unobservable_observed_version_is_refused() -> None:
    # A conflict attempt authors its `write` rows in the same `writeRow`
    # vocabulary a writeSequence entry does, and unversioned conflict targets are
    # a supported surface (m-unit-work-013/-014, m-batch-write-008). Accepted, the
    # key wraps each row in an observation carrier the planner ignores (there is
    # no version to advance) but batching still excludes, so the multi-key attempt
    # emits one statement per key instead of the single `IN`-list statement
    # `m-batch-write`'s uniform-value update collapse yields for these same rows
    # without the key — the collapse this lane exists to exercise.
    case = _unversioned_conflict_case(
        [
            {"id": 1, "balance": 500.00, "observedVersion": 1},
            {"id": 2, "balance": 500.00, "observedVersion": 1},
        ]
    )
    with pytest.raises(engine.EngineError, match="an unversioned row authors no `observedVersion`"):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def test_a_multi_key_unversioned_conflict_attempt_collapses_to_one_statement() -> None:
    emissions, _affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _unversioned_conflict_case([{"id": 1, "balance": 500.00}, {"id": 2, "balance": 500.00}]),
        "postgres",
        FakeWritePort(),
    )
    assert [(e.sql, e.binds) for e in emissions] == [
        ("update wallet set balance = ? where id in (?, ?)", (500.00, 1, 2))
    ]


def test_run_conflict_case_renders_a_gated_zero_row_close_as_a_conflict() -> None:
    _emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-temporal-read-010"), "postgres", _ZeroAffectedClosePort()
    )
    assert affected == 0


def _always_implying(
    error_cls: type[WriteEffectError],
) -> Callable[[bool, Concurrency], type[WriteEffectError]]:
    """An ``_implied_shortfall_error`` stand-in that ignores the case's own
    declared facts — a lane admitting the wrong shortfall class."""

    def implied(_observation_requiring: bool, _concurrency: Concurrency) -> type[WriteEffectError]:
        return error_cls

    return implied


class TestConflictShortfallClassification:
    """The shortfall class a conflict case's declared facts imply, and the lane's
    refusal to absorb any other one.

    Every member of the Write Effect Error family carries the same ``actual``
    count, so a lane catching the whole family would render `then.affectedRows: 0`
    identically whichever class the write raised, and a zero-row case would assert
    nothing about the classification (`m-opt-lock` "Classification follows the
    gate").
    """

    def test_optimistic_mode_implies_the_retriable_conflict(self) -> None:
        assert (
            engine._implied_shortfall_error(True, "optimistic")  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
            is OptimisticLockConflictError
        )

    def test_locking_mode_implies_the_non_retriable_stale_write(self) -> None:
        assert (
            engine._implied_shortfall_error(True, "locking")  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
            is StaleWriteError
        )

    @pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
    def test_an_observation_free_write_implies_a_missing_target_in_either_mode(
        self, concurrency: Concurrency
    ) -> None:
        # A write that observed nothing has no gate to classify by, so its
        # shortfall says only that the addressed rows are not there.
        assert (
            engine._implied_shortfall_error(False, concurrency)  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
            is MissingTargetError
        )

    def test_a_locking_shortfall_admitted_as_a_conflict_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The regression this pins: a lane admitting the retriable conflict where
        # the ungated locking-mode DELETE's shortfall is the stale write. The real
        # failure must NOT be swallowed into the same `affectedRows: 0`
        # observation m-opt-lock-016 asserts.
        monkeypatch.setattr(
            engine, "_implied_shortfall_error", _always_implying(OptimisticLockConflictError)
        )
        with pytest.raises(StaleWriteError):
            engine.run_conflict_case(_load_case("m-opt-lock-016"), "postgres", _ZeroAffectedPort())

    def test_a_gated_shortfall_admitted_as_a_stale_write_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(engine, "_implied_shortfall_error", _always_implying(StaleWriteError))
        with pytest.raises(OptimisticLockConflictError):
            engine.run_conflict_case(_load_case("m-opt-lock-005"), "postgres", _ZeroAffectedPort())


class _CollapsedDeletePort(FakeWritePort):
    """A port whose collapsed multi-key DELETE reports every key the statement
    named, so the write lands and the lane reports its own aggregate."""

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        super().execute_write(sql, binds)
        return len(binds) if sql.startswith("delete from wallet where id in") else 1


def test_run_conflict_case_collapses_a_multi_key_write_into_one_statement() -> None:
    # m-batch-write-008 authors `when.write` as an ORDERED ARRAY of keyed rows.
    # One unit of work buffers all three and the batching rule collapses them
    # into ONE set-based DELETE — so the lane's own pure re-lowering must inject
    # the same collapse policy the execution runs under, or it would report three
    # statements where one was emitted. The count it reports is the aggregate the
    # single complete Key Target owns, never a per-row 1.
    emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-batch-write-008"), "postgres", _CollapsedDeletePort()
    )
    assert [e.sql for e in emissions] == ["delete from wallet where id in (?, ?, ?)"]
    assert [e.binds for e in emissions] == [(1, 2, 3)]
    assert affected == 3


def test_run_conflict_case_refuses_a_multi_key_write_against_a_temporal_target() -> None:
    # A temporal target's write expands into a close plus its successors per key
    # and never collapses into one set-based statement, so the multi-key `write`
    # array — keyed and non-temporal — names no single milestone for the close to
    # address. It is refused rather than reduced to a row the case never chose.
    from pathlib import Path

    case = case_format.Case(
        path=Path("m-unit-work-999-synthetic.yaml"),
        case_id="m-unit-work-999",
        shape="conflict",
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/balance.yaml",
        document={
            "model": "models/balance.yaml",
            "when": {"write": [{"id": 1}, {"id": 2}], "at": "2024-10-01T00:00:00+00:00"},
        },
    )
    with pytest.raises(engine.EngineError, match="closes one milestone row"):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def test_run_conflict_case_attempts_form_scripts_each_attempt_independently() -> None:
    port = FakeWritePort()
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
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
    engine._apply_given_apply(case, POSTGRES, port)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert port.writes == []


def test_run_conflict_case_wraps_a_lowering_failure_as_engine_error() -> None:
    case = _synthetic_write("conflict", {"when": {"write": {"id": 1, "bogus": True}}})
    with pytest.raises(engine.EngineError, match="undeclared member"):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def test_run_conflict_case_temporal_close_form_composes_plan_temporal_close() -> None:
    # m-txtime-write-006: a temporal optimistic-lock CLOSE conflict (`when.at` /
    # `when.observedTxStart`, no `observedVersion`) is driven through
    # `handle.plan_temporal_close`, not the non-temporal versioned-UPDATE path.
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-txtime-write-006"]
    port = FakeWritePort()
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        case, "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert emissions[0].sql == (
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "balance" in table_state


@pytest.mark.parametrize(
    ("control_key", "value", "refusal"),
    [
        (
            "observedTxStart",
            "2020-01-01T00:00:00+00:00",
            "a write row authors no `observedTxStart`",
        ),
        (
            "observedValidStart",
            "2020-01-01T00:00:00+00:00",
            "a write row authors no `observedValidStart`",
        ),
        ("observedVersion", 99, "a temporal row authors no `observedVersion`"),
    ],
)
def test_a_temporal_close_row_authoring_an_observation_control_key_is_refused(
    control_key: str, value: object, refusal: str
) -> None:
    # A temporal conflict's close row is the write-row shape furthest from the
    # keyed non-temporal one: it never reaches `instructions.deserialize`, whose
    # durable-row schema forbids every control key, because a standalone close
    # settles straight through `handle.plan_temporal_close`, which addresses the
    # milestone by primary key alone. Accepted, the row's own token is projected
    # away and the close still gates on the SEPARATE `when.observedTxStart` — so
    # a case meaning to gate on the row's stale value emits the fresh gate's SQL
    # and passes. A temporal write is entitled to neither key: its observation is
    # a whole predecessor milestone `TemporalShadow` holds, and a close's gate
    # rides beside the write.
    case = _synthetic_write(
        "conflict",
        {
            "model": "models/balance.yaml",
            "when": {
                "uow": {"concurrency": "optimistic"},
                "write": {"id": 2, control_key: value},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-02-01T00:00:00+00:00",
            },
        },
    )
    with pytest.raises(engine.EngineError, match=re.escape(refusal)):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def _edge_named_close(document_when: dict[str, object]) -> case_format.Case:
    """A Bitemporal conflict close over the `position` fixtures, whose two current
    rectangles of key 1 differ only in their Valid-Time start."""
    return _synthetic_write(
        "conflict",
        {"model": "models/position.yaml", "when": document_when},
    )


def test_an_edge_named_close_derives_its_address_from_the_named_milestone() -> None:
    # Key 1 has TWO rectangles current on Transaction Time, sharing every
    # coordinate a close renders except `thru_z`. Naming the head's own edge
    # binds the head's `thru_z` (finite) and the tail's binds infinity, so the
    # discriminator is the observation rather than an authored address. A close
    # that resolved its observation by primary key alone has no way to render
    # both.
    #
    # The GATE is not under test and cannot be: the edge's Transaction-Time half
    # IS the milestone's `in_z`, so both rectangles gate on the same instant and
    # a gate copied straight from the authored coordinate renders the same bind.
    # `temporal_state.observed_close_coordinates` is where that derivation is
    # pinned, by construction rather than by observation.
    heads: list[list[object]] = []
    for valid_start in ("2024-01-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00"):
        port = FakeWritePort()
        emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "write": {"id": 1},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "observedValidStart": valid_start,
                }
            ),
            "postgres",
            port,
        )
        assert affected == 1
        assert emissions[0].sql == (
            "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ? "
            "and in_z = ?"
        )
        heads.append(list(emissions[0].binds))
    assert heads[0] == [
        "2024-10-01T00:00:00+00:00",
        1,
        "2024-06-01T00:00:00+00:00",
        "infinity",
        "2024-04-01T00:00:00+00:00",
    ]
    assert heads[1] == [
        "2024-10-01T00:00:00+00:00",
        1,
        "infinity",
        "infinity",
        "2024-04-01T00:00:00+00:00",
    ]


def test_a_close_naming_both_an_observed_edge_and_an_authored_address_is_refused() -> None:
    # The two spell the same fact from opposite ends. Agreeing, the authored
    # address proves nothing the derivation does not; disagreeing, one of them
    # would silently win — and whichever won, the case would be asserting the
    # other one's claim.
    with pytest.raises(engine.EngineError, match=re.escape("never both")):
        engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "write": {"id": 1, "validEnd": "2024-06-01T00:00:00+00:00"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "observedValidStart": "2024-01-01T00:00:00+00:00",
                }
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_non_temporal_conflict_target_may_not_name_an_observed_milestone() -> None:
    # A versioned target has one row per key and no milestone to observe, so the
    # coordinates would be read by nothing: the versioned conflict path never
    # looks at them, and a case authoring one would silently grade the shape it
    # did not mean to.
    with pytest.raises(engine.EngineError, match=re.escape("no milestone to observe")):
        engine.run_conflict_case(
            _synthetic_write(
                "conflict",
                {
                    "model": "models/account.yaml",
                    "when": {
                        "uow": {"concurrency": "optimistic"},
                        "write": {"id": 1, "name": "A", "observedVersion": 1},
                        "observedTxStart": "2024-04-01T00:00:00+00:00",
                    },
                },
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_non_temporal_retry_attempt_may_not_name_an_observed_milestone_either() -> None:
    # The target's entitlement holds wherever the coordinate is spelled. Checking
    # only the root `when` would let the same unentitled coordinate through on
    # the retry form, where the versioned path reads it exactly as little.
    with pytest.raises(engine.EngineError, match=re.escape("no milestone to observe")):
        engine.run_conflict_case(
            _synthetic_write(
                "conflict",
                {
                    "model": "models/account.yaml",
                    "when": {
                        "uow": {"concurrency": "optimistic"},
                        "attempts": [
                            {
                                "statements": [
                                    {"sql": {"postgres": "update account set name = ?"}}
                                ],
                                "affectedRows": 1,
                                "write": {"id": 1, "name": "A", "observedVersion": 1},
                                "observedTxStart": "2024-04-01T00:00:00+00:00",
                            }
                        ],
                    },
                },
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_retry_attempt_may_not_name_its_observed_milestones_edge() -> None:
    # An edge selects among the milestones the case's own fixtures hold, while a
    # retry re-reads what the concurrent `given.apply` writer left behind. No
    # lane performs the resolving read that would reconcile the two, so the
    # observation form is single-attempt only rather than resolving against
    # state the retry has already superseded.
    with pytest.raises(engine.EngineError, match=re.escape("names its observed milestone")):
        engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "attempts": [
                        {
                            "statements": [{"sql": {"postgres": "update position set out_z = ?"}}],
                            "affectedRows": 1,
                            "write": {"id": 1},
                            "at": "2024-10-01T00:00:00+00:00",
                            "observedTxStart": "2024-04-01T00:00:00+00:00",
                            "observedValidStart": "2024-01-01T00:00:00+00:00",
                        }
                    ],
                }
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_retry_sequence_may_not_leave_an_observation_coordinate_on_the_root() -> None:
    # The retry lane reads each attempt's own `at` / `observedTxStart` and never
    # the root `when`'s, so a root coordinate beside `attempts` is consumed by no
    # attempt and would sit in the document grading nothing. The two authoring
    # locations are alternatives, not a default and an override.
    with pytest.raises(engine.EngineError, match=re.escape("consumed by no attempt")):
        engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "attempts": [
                        {
                            "statements": [{"sql": {"postgres": "update position set out_z = ?"}}],
                            "affectedRows": 1,
                            "write": {"id": 1, "validEnd": "2024-06-01T00:00:00+00:00"},
                            "at": "2024-10-01T00:00:00+00:00",
                            "observedTxStart": "2024-04-01T00:00:00+00:00",
                        }
                    ],
                }
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_locking_close_may_not_author_a_lone_observed_gate() -> None:
    # Locking mode renders no gate at all, so the address form's gate candidate
    # reaches nothing: `plan_temporal_close` takes the coordinate and drops it,
    # and the case would claim a gate its own golden cannot carry.
    with pytest.raises(engine.EngineError, match=re.escape("renders no gate")):
        engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "locking"},
                    "write": {"id": 1, "validEnd": "2024-06-01T00:00:00+00:00"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                }
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_locking_retry_attempt_may_not_author_an_observed_gate() -> None:
    # A retry attempt never names an edge, so its `observedTxStart` is always the
    # gate candidate — checking only the root would let the same unentitled
    # coordinate through per attempt.
    with pytest.raises(engine.EngineError, match=re.escape("renders no gate")):
        engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "locking"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "attempts": [
                        {
                            "statements": [{"sql": {"postgres": "update position set out_z = ?"}}],
                            "affectedRows": 1,
                            "write": {"id": 1, "validEnd": "2024-06-01T00:00:00+00:00"},
                            "at": "2024-10-01T00:00:00+00:00",
                            "observedTxStart": "2024-04-01T00:00:00+00:00",
                        }
                    ],
                }
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_locking_close_may_still_name_its_observed_milestones_edge() -> None:
    # Beside `observedValidStart` the Transaction-Time coordinate is the edge's
    # own half, which SELECTS the milestone whose `thru_z` the address binds.
    # That selection happens in either mode; only the gate is optimistic-only,
    # so the locking golden carries the derived address and no `in_z` predicate.
    emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _edge_named_close(
            {
                "uow": {"concurrency": "locking"},
                "write": {"id": 1},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-04-01T00:00:00+00:00",
                "observedValidStart": "2024-01-01T00:00:00+00:00",
            }
        ),
        "postgres",
        FakeWritePort(),
    )
    assert affected == 1
    assert emissions[0].sql == (
        "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?"
    )
    assert list(emissions[0].binds) == [
        "2024-10-01T00:00:00+00:00",
        1,
        "2024-06-01T00:00:00+00:00",
        "infinity",
    ]


def test_a_close_naming_an_edge_no_current_milestone_carries_is_refused() -> None:
    # A named milestone that the case's own state does not hold is an authoring
    # defect, not a stale gate: falling back to whichever rectangle the key
    # happens to hold is the misresolution the naming exists to remove.
    with pytest.raises(engine.EngineError, match=re.escape("no current milestone of this key")):
        engine.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "write": {"id": 1},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "observedValidStart": "2023-01-01T00:00:00+00:00",
                }
            ),
            "postgres",
            FakeWritePort(),
        )


def test_a_temporal_write_sequence_row_authoring_an_observed_version_is_refused() -> None:
    # The same entitlement, decided at the same seam, for the OTHER temporal
    # producer — whose rows do reach the durable-row schema. The refusal must
    # still be this engine's own authoring diagnosis, naming the milestone a
    # temporal observation resolves from, rather than the downstream complaint
    # that a durable instruction cannot carry a control key.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/balance.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Balance",
                        "statements": 2,
                        "rows": [{"id": 2, "value": 100.00, "observedVersion": 7}],
                    }
                ]
            },
        },
    )
    with pytest.raises(engine.EngineError, match=re.escape("a temporal row authors no")):
        engine.compile_write_sequence_case(case, "postgres")


def test_a_multi_row_temporal_write_sequence_entry_is_refused() -> None:
    # The row-count axis of the same seam. `rows` is a schema-valid array of one
    # or more at every authoring location, and a temporal entity's row count is
    # not something the shared definition can constrain (it depends on the
    # model), so a plural temporal entry reaches this engine. It settles one
    # milestone chain per row and never a set-based statement, so the second row
    # is a second chain the case must author as its own entry — and translating
    # only the first would discard it before the entitlement seam ever sees it,
    # emitting the first row's statements and grading green.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/balance.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Balance",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "acctNum": "A", "value": 175.00},
                            {"id": 2, "acctNum": "B", "value": 999.00, "observedVersion": 77},
                        ],
                        "at": "2024-09-01T00:00:00+00:00",
                    }
                ]
            },
        },
    )
    with pytest.raises(engine.EngineError, match=re.escape("a temporal write entry carries ONE")):
        engine.compile_write_sequence_case(case, "postgres")


def test_a_multi_row_temporal_scenario_write_entry_is_refused() -> None:
    # The same refusal for the other shape that reaches the temporal producer: a
    # buffered scenario write entry, whose rows a unit of work would hold rather
    # than a writeSequence's ordered DML.
    when = {
        "scenario": [
            {
                "write": [
                    {
                        "mutation": "update",
                        "entity": "Balance",
                        "rows": [
                            {"id": 1, "acctNum": "A", "value": 175.00},
                            {"id": 2, "acctNum": "B", "value": 999.00},
                        ],
                        "at": "2024-09-01T00:00:00+00:00",
                    }
                ],
                "roundTrips": 2,
            }
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/balance.yaml", "when": when})
    with pytest.raises(engine.EngineError, match=re.escape("a temporal write entry carries ONE")):
        engine.compile_scenario_case(case, "postgres")


def test_run_conflict_case_resolves_target_from_the_inheritance_family() -> None:
    # m-inheritance-105: `when.write` names no entity of its own; for an
    # inheritance-participant model `_conflict_target` resolves to the family's
    # SOLE concrete subtype (MeterReading, tag `meter`) — never the abstract
    # root `_rejected_target` resolves to for the read lane's own default-target
    # convention.
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-inheritance-105"]
    port = FakeWritePort()
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        case, "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert emissions[0].sql == (
        "update reading set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?"
    )
    assert affected == 1
    assert table_state is not None and "reading" in table_state


def test_run_conflict_case_temporal_attempts_form_retries_the_gated_close() -> None:
    # m-temporal-read-011: a TEMPORAL `when.attempts` retry — each attempt its
    # own `db.transact` unit composing `handle.plan_temporal_close` directly
    # (the `is_temporal` branch of the attempts loop, distinct from the
    # non-temporal versioned-UPDATE retry `m-opt-lock-007` already covers).
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-temporal-read-011"]
    port = FakeWritePort()
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        case, "postgres", port
    )
    assert [e.case_pointer for e in emissions] == [
        "/when/attempts/0/write",
        "/when/attempts/1/write",
    ]
    assert len(port.writes) == 4  # given.apply's two out-of-band statements + two attempts
    assert affected == 1
    assert table_state is not None and "balance" in table_state


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
# Rejected — the pre-SQL model-aware validation lane.                          #
# Three-way `when` dispatch, and a three-form `when.write` inside it.          #
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
    case = _rejected_case("m-value-object-034")
    assert engine.run_rejected_case(case) == "nested-path-first-segment-not-value-object"


def test_run_rejected_case_model_dispatch_reuses_the_phase_3_validator() -> None:
    case = _rejected_case("m-inheritance-020")
    assert engine.run_rejected_case(case) == "inheritance-unknown-parent"


def test_run_rejected_case_write_dispatch_classifies_the_rule() -> None:
    case = _rejected_case("m-value-object-039")
    assert engine.run_rejected_case(case) == "write-required-attribute-missing"


def test_run_rejected_case_write_dispatch_over_an_inheritance_model() -> None:
    case = _rejected_case("m-inheritance-088")
    assert engine.run_rejected_case(case) == "abstract-write-target"


def test_run_rejected_case_refuses_a_bare_row_naming_an_undeclared_member() -> None:
    # An undeclared name resolves to no declared position, so no rule of the closed
    # vocabulary is about it. Grading the row anyway reports whichever rule some OTHER
    # member violates — here the missing required `owner` — and the case passes while
    # testing a member it never named. The keyed instruction form refuses the same
    # way, so one neutral write row is judged one way whichever form carries it.
    graded: dict[str, object] = {"id": 1, "balance": "10.00"}
    assert (
        engine.run_rejected_case(_synthetic_bare_row(graded, "models/account.yaml"))
        == "write-required-attribute-missing"
    )
    with pytest.raises(engine.EngineError, match=r"names \['bogus'\]"):
        engine.run_rejected_case(_synthetic_bare_row({**graded, "bogus": 1}, "models/account.yaml"))


def test_a_bare_row_carries_the_shared_observation_control_key() -> None:
    # `observedVersion` is flush-time context the shared row vocabulary admits at
    # every row position, so it is not a member name to refuse; the row is graded on
    # its declared members alone.
    row: dict[str, object] = {"id": 1, "balance": "10.00", "observedVersion": 3}
    assert (
        engine.run_rejected_case(_synthetic_bare_row(row, "models/account.yaml"))
        == "write-required-attribute-missing"
    )


def test_the_subtype_protocol_classifies_the_family_names_member_honesty_would_claim() -> None:
    # `tagValue` names no declared member either, but `m-inheritance` orders the
    # payload-shape rules first and gives it a rule of its own. Asking member honesty
    # before them would report an authoring failure for an input the corpus grades as
    # `subtype-write-metadata-field` (m-inheritance-087).
    row: dict[str, object] = {"id": 1, "amount": "10.00", "tagValue": "card"}
    assert (
        engine.run_rejected_case(_synthetic_bare_row(row, "models/payment.yaml"))
        == "subtype-write-metadata-field"
    )


def _synthetic_bare_row(row: dict[str, object], model: str) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path("m-value-object-996-synthetic-rejected.yaml"),
        case_id="m-value-object-996",
        shape="rejected",
        tags=("m-value-object", "rejected", "slice-snapshot-1"),
        model=model,
        document={"model": model, "when": {"write": row}, "then": {"rejectedRule": "x"}},
    )


def _synthetic_keyed_rejected(write: dict[str, object], model: str) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path("m-unit-work-997-synthetic-rejected.yaml"),
        case_id="m-unit-work-997",
        shape="rejected",
        tags=("m-unit-work", "rejected", "slice-snapshot-1"),
        model=model,
        document={"model": model, "when": {"write": write}, "then": {"rejectedRule": "x"}},
    )


def test_run_rejected_case_keyed_write_dispatch_classifies_the_rule() -> None:
    case = _rejected_case("m-unit-work-016")
    assert engine.run_rejected_case(case) == "temporal-keyed-write-multi-row"


def test_run_rejected_case_keyed_write_names_its_own_entity_not_the_default_target() -> None:
    # A keyed instruction brings its own handle, so the rule is judged against the
    # entity the instruction names rather than the model's default write root —
    # which here is `Tenant`, neither of the two entities written below. The same
    # plural rows are refused on the temporal entity and accepted on the
    # non-temporal one, so the handle, not the model, is what decided it.
    plural_temporal: dict[str, object] = {
        "mutation": "update",
        "entity": "Lease",
        "rows": [{"id": 1, "term": "annual"}, {"id": 2, "term": "monthly"}],
    }
    plural_non_temporal: dict[str, object] = {
        "mutation": "update",
        "entity": "LeaseNote",
        "rows": [{"id": 1, "text": "first"}, {"id": 2, "text": "second"}],
    }
    model = "models/lease.yaml"
    assert (
        engine.run_rejected_case(_synthetic_keyed_rejected(plural_temporal, model))
        == "temporal-keyed-write-multi-row"
    )
    with pytest.raises(engine.EngineError, match="accepted a keyed write instruction"):
        engine.run_rejected_case(_synthetic_keyed_rejected(plural_non_temporal, model))


def test_run_rejected_case_raises_for_a_malformed_keyed_instruction() -> None:
    malformed: dict[str, object] = {"mutation": "update", "rows": [{"id": 1}]}
    with pytest.raises(engine.EngineError, match="missing required key"):
        engine.run_rejected_case(_synthetic_keyed_rejected(malformed, "models/position.yaml"))


@pytest.mark.parametrize(
    "write",
    [[{"id": 1, "value": 150.00}], [{"id": 1, "value": 150.00}, {"id": 2, "value": 250.00}]],
)
def test_run_rejected_case_refuses_the_conflict_multi_key_array(
    write: list[dict[str, object]],
) -> None:
    # The array is the conflict lane's multi-key form and carries no member for
    # this dispatch to read. Asking it for one instead reaches the bare-row arm
    # with a list, which decodes as a mapping of pairs and fails on the row's own
    # data rather than on the form — a raw carrier error where the case's defect
    # is that no rejected lane defines this input at all.
    case = _synthetic_keyed_rejected(cast("dict[str, object]", write), "models/position.yaml")
    with pytest.raises(engine.EngineError, match="multi-key form"):
        engine.run_rejected_case(case)


def test_a_default_target_over_a_multi_family_model_is_refused() -> None:
    # The default-target convention names "the family root", singular, so a
    # model carrying several families has no default to resolve and the case
    # must name its target explicitly — never an arbitrary one of them.
    from pathlib import Path

    case = case_format.Case(
        path=Path("m-inheritance-997-synthetic-rejected.yaml"),
        case_id="m-inheritance-997",
        shape="rejected",
        tags=("m-inheritance", "rejected", "slice-snapshot-1"),
        model="models/workshop.yaml",
        document={
            "model": "models/workshop.yaml",
            "when": {"write": {"id": 1}},
            "then": {"rejectedRule": "x"},
        },
    )
    with pytest.raises(engine.EngineError, match="no single inheritance family root"):
        engine.run_rejected_case(case)


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
    with pytest.raises(engine.EngineError, match="accepted an inline model"):
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


def test_read_table_state_reads_each_physical_table_once_over_every_slot() -> None:
    # Payment's abstract root owns the shared table; descendants carry no local
    # table. The one read projects the layout's complete slot sequence, so a
    # CardPayment row still reports the sibling-only `tendered` column.
    from parallax.conformance import models
    from parallax.core.dialect import POSTGRES

    port = FakeWritePort()
    meta = models.load_models()["payment"]
    state = engine.read_table_state(port, meta, POSTGRES)
    assert set(state) == {"payment"}
    assert len(port.reads) == 1
    sql, _ = port.reads[0]
    assert sql == "select id, kind, amount, card_network, tendered from payment"


def test_read_table_state_reads_each_tpcs_concrete_table() -> None:
    from parallax.conformance import models
    from parallax.core.dialect import POSTGRES

    port = FakeWritePort()
    meta = models.load_models()["document"]
    state = engine.read_table_state(port, meta, POSTGRES)
    assert set(state) == {"invoice", "receipt", "memo", "folder"}
    assert len(port.reads) == 4


def test_read_table_state_projects_value_object_document_columns_last() -> None:
    # A document slot follows every scalar tier (m-storage-layout), even for a
    # plain non-inheritance entity — the customer model's `address`.
    from parallax.conformance import models
    from parallax.core.dialect import POSTGRES

    port = FakeWritePort()
    meta = models.load_models()["customer"]
    state = engine.read_table_state(port, meta, POSTGRES)
    assert "customer" in state
    sql, _ = port.reads[0]
    assert sql == "select id, name, address from customer"


def test_read_table_state_normalizes_values_without_changing_the_projection() -> None:
    # Value normalization is the wire encoder's own concern; the projection is the
    # layout's slot sequence and nothing re-resolves a physical column to reach it.
    import datetime as dt

    from parallax.conformance import models
    from parallax.core.dialect import POSTGRES

    instant = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = FakeWritePort(find_rows=[{"bal_id": 1, "acct_num": "A", "val": 1, "in_z": instant}])
    meta = models.load_models()["balance"]
    state = engine.read_table_state(port, meta, POSTGRES)
    (row,) = state["balance"]
    assert row["in_z"] == "2024-01-01T00:00:00+00:00"
    sql, _ = port.reads[0]
    assert sql == "select bal_id, acct_num, val, in_z, out_z from balance"


# --------------------------------------------------------------------------- #
# Graph reads (m-deep-fetch / m-snapshot-read): the                            #
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


def test_run_graph_case_keys_value_objects_by_canonical_member_name() -> None:
    port = FakeDbPort(
        [
            {
                "id": 1,
                "person_id": "person-1",
                "tax_i_d": "TAX-1",
                "line2_item": 2,
                "already_snake": "ready",
                "legacy__i_d": "legacy",
                "mailing_address": {"city": "Oslo"},
            }
        ]
    )
    _emissions, graph, _round_trips, _identity_checks = engine.run_graph_case(
        _case("m-descriptor-002"), "postgres", port
    )
    row = graph["MemberColumnDefaults"][0]
    assert row["mailingAddress"] == {"city": "Oslo"}
    assert "mailing_address" not in row


def test_relationship_attachment_preserves_a_same_named_value_object_storage_key() -> None:
    from parallax.conformance import _assembly, models
    from parallax.core.deep_fetch import CorrelationMember, FetchLevel, RootRef
    from parallax.descriptor._serde import parse_document

    model = models.accepted_model(
        parse_document(
            {
                "entities": [
                    {
                        "name": "Owner",
                        "table": "owner",
                        "attributes": [
                            {"name": "id", "type": "int64", "primaryKey": True},
                            {"name": "targetId", "type": "int64"},
                        ],
                        "valueObjects": [
                            {
                                "name": "profile",
                                "column": "details",
                                "attributes": [{"name": "label", "type": "string"}],
                            }
                        ],
                        "relationships": [
                            {
                                "name": "details",
                                "cardinality": "many-to-one",
                                "join": {
                                    "source": "targetId",
                                    "target": {"entity": "Target", "attribute": "id"},
                                },
                            }
                        ],
                    },
                    {
                        "name": "Target",
                        "table": "target",
                        "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                    },
                ]
            }
        )
    )
    owner_identity = EntityIdentity(None, "Owner")
    owner = model.entity(owner_identity)
    assert owner is not None
    assembler = _assembly.Assembler(model)
    parent_rows = [{"id": 1, "target_id": 7, "details": {"label": "stored"}}]
    parents = assembler.materialize_root(
        "Owner",
        parent_rows,
        resolved_entities=(owner_identity,),
        family_variants=(None,),
        documents=owner.declared_value_objects,
    )
    level = FetchLevel(
        attach_key="details",
        relationship=RelationshipIdentity(owner_identity, "details"),
        to_many=False,
        parent=RootRef(),
        owner=CorrelationMember(
            identity=AttributeIdentity(owner_identity, "targetId"), column="target_id"
        ),
        child_target="Target",
        related=CorrelationMember(
            identity=AttributeIdentity(EntityIdentity(None, "Target"), "id"),
            column="id",
            reference="Target.id",
        ),
    )
    target_identity = EntityIdentity(None, "Target")
    assembler.attach_level(
        level,
        parents,
        parent_rows,
        [{"id": 7}],
        resolved_entities=(target_identity,),
        family_variants=(None,),
    )

    graph = engine._render_graph(  # pyright: ignore[reportPrivateUsage] - integration test renders a real assembled relationship
        "Owner", parents, model
    )
    assert graph == {
        "Owner": [
            {
                "id": 1,
                "target_id": 7,
                "profile": {"label": "stored"},
                "details": {"id": 7},
            }
        ]
    }


_VARIANT_ROOT = EntityIdentity("catalog", "AssetRecord")
_NAMED_VARIANT = EntityIdentity("catalog", "NamedVariant")
_FIRST_SHARED_VARIANT = EntityIdentity("catalog", "SharedVariant")
_SECOND_SHARED_VARIANT = EntityIdentity("archive", "SharedVariant")
_UNRELATED_NAMED_VARIANT = EntityIdentity("unrelated", "NamedVariant")


def _rendering_value_object(name: str, column: str) -> ValueObjectOccurrenceDeclaration:
    return ValueObjectOccurrenceDeclaration(
        name=name,
        storage=Column(column),
        shape=ValueObjectShapeDeclaration(
            key=ValueObjectShapeKey(),
            attributes=(ValueObjectAttributeDeclaration("label", STRING),),
        ),
    )


_VARIANT_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_VARIANT_ROOT,
            container=Table("asset_record"),
            attributes=(key(_VARIANT_ROOT),),
            value_objects=(_rendering_value_object("mailingAddress", "familyVariant"),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_NAMED_VARIANT,
            value_objects=(_rendering_value_object("namedProfile", "named_profile"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "named"),
        ),
        Declaration(
            identity=_FIRST_SHARED_VARIANT,
            value_objects=(_rendering_value_object("catalogProfile", "catalog_profile"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "catalog-shared"),
        ),
        Declaration(
            identity=_SECOND_SHARED_VARIANT,
            value_objects=(_rendering_value_object("archiveProfile", "archive_profile"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "archive-shared"),
        ),
        Declaration(
            identity=_UNRELATED_NAMED_VARIANT,
            container=Table("unrelated_named_variant"),
            attributes=(key(_UNRELATED_NAMED_VARIANT),),
            value_objects=(_rendering_value_object("wrongProfile", "wrong_profile"),),
        ),
    )
)


def _value_object_node(*, resolved: EntityIdentity = _VARIANT_ROOT, variant: object = ...) -> Any:
    from parallax.conformance import _assembly

    value_objects: dict[str, object] = {
        "familyVariant": {"label": "mail"},
        "named_profile": {"label": "named"},
        "catalog_profile": {"label": "catalog"},
        "archive_profile": {"label": "archive"},
    }
    family_variant = cast("str | None", variant) if variant is not ... else None
    return _assembly.Node(
        fields={"id": 1},
        pk_columns=("id",),
        resolved_entity=resolved,
        value_objects=value_objects,
        family_variant=family_variant,
    )


def test_value_object_names_use_the_static_entity_when_variant_is_absent() -> None:
    names = engine._value_object_names(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance renderer's private helper
        _value_object_node(resolved=_NAMED_VARIANT), _VARIANT_MODEL
    )
    assert names == {
        "familyVariant": "mailingAddress",
        "named_profile": "namedProfile",
    }


def test_value_object_names_without_assembler_entity_bookkeeping_are_empty() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(fields={"id": 1}, pk_columns=("id",))
    assert (
        engine._value_object_names(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance renderer's defensive helper
            node, _VARIANT_MODEL
        )
        == {}
    )


def test_value_object_names_resolve_a_bare_variant_within_the_static_family() -> None:
    names = engine._value_object_names(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance renderer's private helper
        _value_object_node(resolved=_NAMED_VARIANT, variant="NamedVariant"), _VARIANT_MODEL
    )
    assert names["familyVariant"] == "mailingAddress"
    assert names["named_profile"] == "namedProfile"
    assert "wrong_profile" not in names


def test_value_object_names_resolve_a_qualified_namespaced_duplicate() -> None:
    names = engine._value_object_names(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance renderer's private helper
        _value_object_node(resolved=_SECOND_SHARED_VARIANT, variant="archive.SharedVariant"),
        _VARIANT_MODEL,
    )
    assert names == {
        "familyVariant": "mailingAddress",
        "archive_profile": "archiveProfile",
    }


def test_namespaced_duplicate_variants_flow_from_sql_plan_through_assembler_to_renderer() -> None:
    from parallax.conformance import _assembly
    from parallax.core.dialect import POSTGRES
    from parallax.core.op_algebra import All
    from parallax.core.sql_gen import compile_read

    root = _VARIANT_MODEL.entity(_VARIANT_ROOT)
    assert root is not None
    compiled = compile_read(All(), _VARIANT_MODEL, POSTGRES, root, result_form="instance")
    materialized = compiled.materialize_row(
        {
            "id": 1,
            "kind": "archive-shared",
            "familyVariant": {"label": "mail"},
            "named_profile": None,
            "catalog_profile": None,
            "archive_profile": {"label": "archive"},
        }
    )
    assert materialized.resolved_entity == _SECOND_SHARED_VARIANT
    assert materialized.family_variant == "archive.SharedVariant"
    assert materialized.values["familyVariant"] == {"label": "mail"}

    nodes = _assembly.Assembler(_VARIANT_MODEL).materialize_root(
        _VARIANT_ROOT.canonical,
        [materialized.values],
        resolved_entities=[materialized.resolved_entity],
        family_variants=[materialized.family_variant],
        documents=compiled.documents,
    )
    assert "familyVariant" not in nodes[0].fields
    assert nodes[0].value_objects["familyVariant"] == {"label": "mail"}
    assert nodes[0].family_variant == "archive.SharedVariant"
    graph = engine._render_graph(  # pyright: ignore[reportPrivateUsage] - integration test drives the renderer after real assembly
        _VARIANT_ROOT.canonical, nodes, _VARIANT_MODEL
    )
    assert graph[_VARIANT_ROOT.canonical] == [
        {
            "id": 1,
            "familyVariant": "archive.SharedVariant",
            "mailingAddress": {"label": "mail"},
            "archiveProfile": {"label": "archive"},
        }
    ]


def test_value_object_name_rendering_defensively_rejects_a_column_collision() -> None:
    claimed = {"shared": "Attribute catalog.NamedVariant.label"}
    with pytest.raises(engine.EngineError, match="ambiguously renders"):
        engine._claim_rendered_column(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance renderer's defensive helper
            claimed, "shared", "Value Object catalog.NamedVariant.profile"
        )


def test_render_node_does_not_stub_a_diamond_at_a_non_cyclic_position() -> None:
    from parallax.conformance import _assembly

    child = _assembly.Node(fields={"id": 11, "name": "child"}, pk_columns=("id",))
    root = _assembly.Node(
        fields={"id": 1},
        pk_columns=("id",),
        relationships={"a": child, "b": child},
    )
    rendered = engine._render_node(root, frozenset())  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert rendered["a"] == {"id": 11, "name": "child"}
    assert rendered["b"] == {"id": 11, "name": "child"}


def test_render_node_truncates_a_true_ancestor_cycle_to_a_pk_only_stub() -> None:
    from parallax.conformance import _assembly

    root = _assembly.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    root.relationships["self"] = root
    rendered = engine._render_node(root, frozenset())  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert rendered["self"] == {"id": 1}


def test_resolve_graph_pointer_rejects_a_malformed_pointer() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(fields={"id": 1}, pk_columns=("id",))
    with pytest.raises(engine.EngineError, match="malformed"):
        engine._resolve_graph_pointer(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-011"), {"Order": [node]}, "/nonsense"
        )


def test_apply_mutate_step_updates_the_targeted_nodes_fields_in_place() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _case("m-snapshot-read-010"), step, [[node]]
    )
    assert node.fields["name"] == "Mutant"


def test_apply_mutate_step_raises_when_the_target_step_materialized_zero_nodes() -> None:
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="expected exactly one"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-010"), step, [[]]
        )


def test_apply_mutate_step_raises_when_the_target_step_materialized_many_nodes() -> None:
    from parallax.conformance import _assembly

    nodes = [_assembly.Node(fields={}, pk_columns=()), _assembly.Node(fields={}, pk_columns=())]
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="expected exactly one"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-010"), step, [nodes]
        )


def test_apply_mutate_step_raises_when_set_is_not_a_mapping() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    step = {"action": "mutate", "on": 0, "set": "not-a-mapping"}
    with pytest.raises(engine.EngineError, match="needs a `set` mapping"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-010"), step, [[node]]
        )


def test_apply_mutate_step_raises_on_an_out_of_range_on_index() -> None:
    step = {"action": "mutate", "on": 5, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="invalid `on`"):
        engine._apply_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
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
            "model": "models/balance.yaml",
            "when": {
                "targetEntity": "Balance",
                "operation": {
                    "asOf": {
                        "operand": {"all": {}},
                        "dimension": "valid-time",
                        "coordinate": "latest",
                    }
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(engine.EngineError, match="undeclared dimension"):
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
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
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
                "operation": {"history": {"operand": {"all": {}}, "dimension": "valid-time"}},
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(engine.EngineError, match="undeclared dimension"):
        engine.run_graphs_case(case, "postgres", QueueDbPort([]))


def test_render_value_recurses_into_a_nested_value_object_document() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(
        fields={"id": 1, "address": {"street": "x", "geo": {"country": "NO"}}},
        pk_columns=("id",),
    )
    rendered = engine._render_node(node, frozenset())  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert rendered["address"] == {"street": "x", "geo": {"country": "NO"}}


def test_resolve_graph_pointer_rejects_a_path_continuing_past_a_scalar() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    with pytest.raises(engine.EngineError, match="does not resolve"):
        engine._resolve_graph_pointer(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-011"), {"Order": [node]}, "/then/graph/Order/0/name/x"
        )


def test_resolve_graph_pointer_rejects_a_pointer_resolving_to_a_non_node() -> None:
    from parallax.conformance import _assembly

    node = _assembly.Node(fields={"id": 1, "name": "Ada"}, pk_columns=("id",))
    with pytest.raises(engine.EngineError, match="does not name a graph node"):
        engine._resolve_graph_pointer(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-011"), {"Order": [node]}, "/then/graph/Order/0/name"
        )


def test_check_action_step_rejects_a_non_mutate_verb() -> None:
    with pytest.raises(engine.EngineError, match="graded by the API"):
        engine._check_action_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-010"), {"action": "access"}
        )


def test_compile_scenario_case_snapshot_lane_requires_target_and_find() -> None:
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


def test_run_scenario_case_snapshot_lane_requires_target_and_find() -> None:
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
    emissions, round_trips, errors, _log = engine.run_scenario_case(
        _case("m-snapshot-read-010"), "postgres", port
    )
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find", "/scenario/2/find"]
    assert len(port.reads) == 2
    assert len(port.writes) == 0
    assert errors == []  # an unpinned mutate is accepted: no error observation


# --------------------------------------------------------------------------- #
# The scenario `expectError` grading (m-conformance-adapter `errors`): the      #
# snapshot lane's `mutate` runs the SAME finite-Transaction-Time-pin refusal    #
# the keyed developer verbs run, against the referenced find step's own         #
# statement pin, and reports one `errors` entry per matched `expectError`.      #
# --------------------------------------------------------------------------- #
_POSITION_R1_ROW: dict[str, object] = {
    "pos_id": 1,
    "acct_num": "A",
    "val": decimal.Decimal("90.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
}


def test_run_scenario_case_grades_a_transaction_time_pin_read_only_mutate() -> None:
    port = FakeDbPort([dict(_POSITION_R1_ROW)])
    emissions, round_trips, errors, _log = engine.run_scenario_case(
        _case("m-bitemp-write-016"), "postgres", port
    )
    assert round_trips == 1
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find"]
    assert errors == [{"at": "/scenario/1", "errorClass": "transaction-time-pin-read-only"}]


def test_run_scenario_case_accepts_a_finite_valid_time_pin_mutate() -> None:
    # The writable half of the finite-pin contrast: a finite Valid-Time pin
    # (Transaction Time defaulted Latest) passes the SAME validator, so the
    # mutate applies in-memory and no error observation is reported.
    row = dict(_POSITION_R1_ROW, val=decimal.Decimal("100.00"))
    port = FakeDbPort([row])
    _emissions, round_trips, errors, _log = engine.run_scenario_case(
        _case("m-bitemp-write-015"), "postgres", port
    )
    assert round_trips == 1
    assert errors == []


def test_run_scenario_case_reports_an_undeclared_pin_refusal_loudly() -> None:
    # The mutate verb raised, but the step declares no expectError — a corpus/
    # implementation mismatch this lane names loudly, never a silently dropped
    # error observation.
    when = {
        "scenario": [
            {
                "targetEntity": "Position",
                "find": {
                    "asOf": {
                        "operand": {"eq": {"attr": "Position.id", "value": 1}},
                        "dimension": "transaction-time",
                        "coordinate": "2024-02-01T00:00:00+00:00",
                    }
                },
            },
            {"action": "mutate", "on": 0, "set": {"value": 999.00}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/position.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="declares no expectError"):
        engine.run_scenario_case(case, "postgres", FakeDbPort([dict(_POSITION_R1_ROW)]))


def test_run_scenario_case_mutate_grading_rejects_an_out_of_range_on_index() -> None:
    # The grading wrapper guards `on` itself (its identity and pin lookups both
    # index the find steps' own recorded state), before the in-memory apply ever
    # runs. One guard answers every way `on` can fail to name a find step —
    # out of range, absent, or naming an action step, which resolves no Entity.
    when = {"scenario": [{"action": "mutate", "on": 5, "set": {"name": "Mutant"}}]}
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="no earlier find step"):
        engine.run_scenario_case(case, "postgres", FakeDbPort([]))


def test_run_scenario_case_reports_an_unraised_expect_error_loudly() -> None:
    # The step declares expectError but the mutation was accepted (the find
    # carries no finite Transaction-Time pin) — the same loud mismatch, the
    # other direction.
    when = {
        "scenario": [
            {"targetEntity": "Order", "find": {"eq": {"attr": "Order.id", "value": 1}}},
            {
                "action": "mutate",
                "on": 0,
                "set": {"name": "Mutant"},
                "expectError": "transaction-time-pin-read-only",
            },
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = FakeDbPort([{"id": 1, "name": "Ada"}])
    with pytest.raises(engine.EngineError, match="but the mutation was accepted"):
        engine.run_scenario_case(case, "postgres", port)


# --------------------------------------------------------------------------- #
# Case-format ingestion decode (m-case-format / m-core): `decode_write_row`    #
# and its Value Object / predicate-assignment helpers, exercised directly     #
# over real corpus models -- customer.yaml's recursive nested composite (a    #
# to-one `geo`, a to-many `phones`) and account.yaml's decimal `balance`.      #
# --------------------------------------------------------------------------- #
def _accepted_entity(
    model_name: str, entity_name: str, namespace: str = "parallax.compatibility"
) -> tuple[Any, Any]:
    from parallax.conformance import models as _models
    from parallax.core.metamodel import EntityIdentity

    model = _models.accepted_model(_models.load_models()[model_name])
    entity = model.entity(EntityIdentity(namespace, entity_name))
    assert entity is not None
    return model, entity


def test_decode_write_row_decodes_a_to_one_value_objects_own_leaves() -> None:
    model, customer = _accepted_entity("customer", "Customer")
    row: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {"street": "s", "city": "c", "geo": {"country": "US", "elevation": 5}},
    }
    decoded = engine.decode_write_row(customer, row, model)
    address = cast("dict[str, object]", decoded["address"])
    geo = cast("dict[str, object]", address["geo"])
    assert geo["elevation"] == 5.0  # an int spells a float64 value (lossless)


def test_decode_write_row_decodes_each_element_of_a_many_value_object() -> None:
    model, customer = _accepted_entity("customer", "Customer")
    row: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {
            "street": "s",
            "city": "c",
            "phones": [{"type": "home", "number": "1"}, {"type": "work", "number": "2"}],
        },
    }
    decoded = engine.decode_write_row(customer, row, model)
    address = cast("dict[str, object]", decoded["address"])
    phones = cast("list[object]", address["phones"])
    assert len(phones) == 2


def test_decode_write_row_leaves_a_malformed_many_value_object_unchanged() -> None:
    # A string is technically a `Sequence`, but is never a legal `many`
    # occurrence value -- `_decoded_vo_value` leaves it exactly as authored,
    # the SAME structural shape `vo_document_violation` itself classifies as a
    # rejection; decoding never masks that.
    model, customer = _accepted_entity("customer", "Customer")
    row: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {"street": "s", "city": "c", "phones": "not-a-list"},
    }
    decoded = engine.decode_write_row(customer, row, model)
    address = cast("dict[str, object]", decoded["address"])
    assert address["phones"] == "not-a-list"


def test_decode_write_row_leaves_a_non_document_value_object_unchanged() -> None:
    model, customer = _accepted_entity("customer", "Customer")
    row = {"id": 1, "name": "Ada", "address": "not-a-document"}
    decoded = engine.decode_write_row(customer, row, model)
    assert decoded["address"] == "not-a-document"


def test_decode_write_row_decodes_an_int_literal_to_an_exact_decimal() -> None:
    model, account = _accepted_entity("account", "Account")
    decoded = engine.decode_write_row(account, {"id": 1, "owner": "Ada", "balance": 100}, model)
    assert decoded["balance"] == decimal.Decimal(100)


def test_decoded_assignment_value_decodes_a_value_object_assignment() -> None:
    # `_decoded_assignment_value`'s value-object branch -- a predicate-write
    # assignment naming a whole Value Object member, mirrored against the
    # SAME per-leaf decode `decode_write_row` applies to a keyed row.
    model, customer = _accepted_entity("customer", "Customer")
    value: dict[str, object] = {
        "street": "s",
        "city": "c",
        "geo": {"country": "US", "elevation": 5},
    }
    decoded = engine._decoded_assignment_value(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        customer, "address", value, model
    )
    geo = cast("dict[str, object]", cast("dict[str, object]", decoded)["geo"])
    assert geo["elevation"] == 5.0


def test_decoded_assignment_value_leaves_an_undeclared_member_unchanged() -> None:
    # A member matching neither a declared scalar attribute nor a value
    # object -- a garbage predicate-write target -- passes through untouched;
    # the member-name honesty check classifies THAT defect, not this decode.
    model, customer = _accepted_entity("customer", "Customer")
    assert (
        engine._decoded_assignment_value(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            customer, "nonsense", 42, model
        )
        == 42
    )
