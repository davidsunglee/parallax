"""Conformance engine unit tests (compile / run against the spine).

The compile path is proven pure and golden-matching over a representative
exercised case; the run path is proven against a fake in-memory
``m-db-port`` (no Docker) so the port-execution seam, the `?` -> `%s` translation,
and the observation recording are covered in the unit lane. Compile-eligibility
reading and the engine's failure modes are pinned too.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

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


# --- `uow`-grouped scenario spans (amendment-review remediation) -------------
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
    port = FakeWritePort(find_rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    emissions, round_trips = engine.run_scenario_case(_case("m-unit-work-005"), "postgres", port)
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
    port = FakeWritePort(find_rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    emissions, round_trips = engine.run_scenario_case(_case("m-unit-work-002"), "postgres", port)
    assert round_trips == 3
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/find",
        "/scenario/1/write",
        "/scenario/2/find",
    ]
    assert len(port.writes) == 1  # the doomed write's DML still executed (and counted)
    assert len(port.reads) == 2  # the grouped observe find + the ungrouped post-abort find
    assert port.commits == 0 and port.rollbacks == 1


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
    # routes to `run_interleaved_scenario_case` instead (COR-3 Phase 8
    # increment 6), which needs a second, peer-backed connection this
    # function does not construct.
    assert (
        engine._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage]
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
    # forever, the pre-increment-6 disposition).
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
        engine._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage]
            "m-unit-work-999-synthetic.yaml", steps
        )


class _ScriptedPort:
    """A `DbPort` fake with per-call SCRIPTED read rows / write-affected counts
    (COR-3 Phase 8 increment 6, `run_interleaved_scenario_case`'s own unit
    pins) — unlike `FakeWritePort` above (one constant `find_rows` for every
    `execute`, `write_affected` always `1`), a genuinely two-session
    choreography's own conflict needs each connection scripted with its OWN,
    call-ordered sequence to reproduce a real stale-version mismatch
    deterministically, with no real database involved.

    Carries round 5's own documented trust marker
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
    engine._TERMINATION_LADDER_TRUST_ATTR,  # pyright: ignore[reportPrivateUsage]
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
    # review remediation finding 1: every find step's own observed rows, in
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
        read_rows=[[{"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}]]
    )

    with pytest.raises(RuntimeError, match="unexpected defect"):
        engine.run_interleaved_scenario_case(case, "postgres", main_port, lambda: peer_port)
    assert peer_port.closed


def test_await_interleaved_workers_unsticks_both_on_timeout_then_joins_before_raising() -> None:
    # Review remediation finding 4 (the join-timeout path): a genuine harness
    # defect (a missing turnstile `advance()` somewhere) leaves BOTH workers
    # blocked in `wait_for` forever — the timeout path must wake every one of
    # them (`_Turnstile.release_all`), close the peer connection, JOIN both
    # threads, and only THEN raise; no live thread and no open peer connection
    # may outlive the call. A tiny `timeout` (never the production 30s bound)
    # keeps this deterministic and fast. Neither worker's own connection ever
    # needs cancelling here (both wake on `release_all`), so a plain
    # `_ScriptedPort` stands in for `main_connection` too.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage]
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
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage]
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
    is not the peer). This is the shape a confirmation pass on review
    remediation finding 4 found missing: a worker blocked in REAL database
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
    # Confirmation residual on review remediation finding 4: a worker blocked
    # in REAL database I/O on its OWN (CALLER-OWNED) connection survives the
    # first escalation intact — `release_all` has nothing to wake (the
    # worker is not inside `turnstile.wait_for`) and closing the peer
    # touches only the OTHER session. The second escalation must cancel that
    # survivor's OWN connection, rejoin bounded, and — once every worker is
    # (now) actually joined — raise the SAME ordinary timeout error this
    # function has always raised, with `is_alive()` false for every worker
    # before it does.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage]
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
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage]
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
    capability at all — the shape the round-2 confirmation pass on review
    remediation finding 4 needs: a survivor neither `_Turnstile.release_all`
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
    # Round-2 confirmation pass on review remediation finding 4: a survivor
    # neither `release_all` nor the cancellation probe can reach (no
    # `cancel()` capability at all, `main_connection` here — the
    # CALLER-OWNED port) escalates to the THIRD, destructive rung —
    # `_terminate_connection` closes its OWN connection outright — rather
    # than this function ever raising while that worker remains alive; the
    # corrected contract has no "loud leak" terminal state at all.
    # `is_alive()` must be False for EVERY worker at the moment of the
    # raise, and the raised error must report that the caller-owned port
    # was itself terminated. The fake's own `close()` seam mirrors REAL
    # close semantics closely enough to prove it: its blocked `execute`
    # wakes and raises once closed, and a later call raises too (as far as
    # the fake allows) rather than executing.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage]
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
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage]
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
    seam for a test fake (round-3 confirmation pass on review remediation
    finding 4) — mirrors `PostgresAdapter.connection`, the wrapped psycopg
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
    absent entirely — the round-3 confirmation pass's own adversarial shape
    on review remediation finding 4 (the reviewer's own reproduction: BOTH
    ``cancel()`` and ``close()`` forced to fail on the same survivor). The
    escalation's first two rungs (:func:`~parallax.conformance.engine.
    _cancel_in_flight_work`'s probe, then ``connection.close()`` itself)
    both come up empty — round 2's own "close always works" assumption does
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
    # Round-3 confirmation pass on review remediation finding 4 (the
    # reviewer's own reproduction): `cancel()` absent AND `close()` raising
    # on the SAME survivor — `_terminate_connection`'s corrected, GUARANTEED
    # ladder must escalate past the failing outer `close()` to the fake's
    # documented underlying seam, unblock it there, join both workers, and
    # raise the SAME terminated-caller-port timeout error the close-succeeds
    # pin above raises — never a live worker at the raise, and the failing
    # outer `close()` itself must never be silently swallowed: it must
    # surface as recorded context on the raised error rather than masked.
    turnstile = engine._Turnstile()  # pyright: ignore[reportPrivateUsage]
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
        engine._await_interleaved_workers(  # pyright: ignore[reportPrivateUsage]
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
    assert "outer close failed" in notes  # the swallowed-by-round-2 failure is now recorded context


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
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage]
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
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage]
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
    `connection` attribute, NOR `fileno()` anywhere, NOR round 5's own trust
    marker — the most defective refusal shape: preflight must name and
    refuse a connection like this BEFORE either worker thread starts, never
    let it surface only later as the indefinite join hang round 4's own
    confirmation pass first reproduced. `execute_calls` is this pin's own
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
    # HEALTHY side because it carries round 5's own trust marker (see its
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
    """The reviewer's own reproduction (the finding that forced the
    corrected contract to deepen from round 4's structural-only check to
    round 5's TRUSTED, DECLARED one): a structurally-plausible port — a
    CALLABLE `close()`, a CALLABLE `cancel()`, and an underlying
    `connection` seam with a CALLABLE `close()` AND `fileno()` too — that
    would have PASSED round 4's own structural check (every one of those IS
    callable) yet whose EVERY runtime rung RAISES (`preflight=
    ('validated',)`, `helper_completed=False` before this fix). No trust
    marker, not a `PostgresAdapter` — round 5's preflight must refuse it
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
    # The reviewer's demanded pin: a structurally-plausible port whose EVERY
    # runtime termination rung raises — a shape that PASSED round 4's own
    # structural preflight check and hung the unbounded post-ladder join —
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
    """A connection exposing a CALLABLE `close()` and nothing else — round
    4's own retired structural check accepted a shape like this alone;
    round 5 (the corrected contract) refuses it anyway, because a callable
    capability was never the same as a DECLARED trust contract. Reused
    directly by `_terminate_connection`'s own ladder-mechanics pins below,
    which bypass preflight entirely — proving the ladder itself is
    untouched by round 5's correction."""

    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _RungTwoOnlyConnection:
    """Exposes NO outer `close()` at all, only an underlying `connection`
    seam whose OWN `close()` is callable — mirrors
    `PostgresAdapter.connection`'s own escalation seam, WITHOUT declaring
    round 5's own trust contract: refused by preflight for that reason
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
    defects = engine._validate_termination_trust(  # pyright: ignore[reportPrivateUsage]
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
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage]
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
    failures = engine._terminate_connection(  # pyright: ignore[reportPrivateUsage]
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
    `PostgresAdapter.__init__` touches — proving round 5's own real-type
    trust rule needs no live database at all: `isinstance` against the
    concrete `PostgresAdapter` class is what grants trust, never anything
    this fake's own connection does."""

    def __init__(self) -> None:
        self.adapters = _FakeAdaptersRegistry()


def test_validate_termination_trust_accepts_the_postgres_adapter_shape() -> None:
    # The known-deterministic real type (round 5's OTHER trust path,
    # alongside the documented marker): the SAME concrete class
    # `provision.py`'s own `Provisioner.port` constructs, trusted BY
    # CONSTRUCTION — no marker required, nothing beyond `isinstance`
    # inspected.
    from parallax.postgres import PostgresAdapter

    adapter = PostgresAdapter(cast("Any", _FakePsycopgConnection()))
    assert (
        engine._validate_termination_trust(  # pyright: ignore[reportPrivateUsage]
            adapter, "main connection"
        )
        == []
    )


def test_require_interleaved_termination_capability_trusts_the_postgres_adapter_peer_too() -> None:
    # `provision.py`'s own `Provisioner.port` AND `Provisioner.peer()` both
    # construct this SAME concrete class (COR-3 Phase 8 increment 6's own
    # peer seam) — the preflight entry point trusts BOTH positions without
    # a marker, never raising.
    from parallax.postgres import PostgresAdapter

    main_connection = PostgresAdapter(cast("Any", _FakePsycopgConnection()))
    peer_connection = PostgresAdapter(cast("Any", _FakePsycopgConnection()))
    engine._require_interleaved_termination_capability(  # pyright: ignore[reportPrivateUsage]
        main_connection, peer_connection, "m-unit-work-999-synthetic.yaml"
    )


def test_require_interleaved_termination_capability_accepts_a_marked_fake() -> None:
    # The documented marker mechanism (round 5): a fake that DECLARES the
    # deterministic-termination contract passes preflight even though this
    # module never inspects its close()/fileno() shape at all — proven with
    # `_ScriptedPort`, which carries the marker (see its own docstring).
    # `run_interleaved_scenario_case`'s own entry-point pins above already
    # exercise the full helper path past this preflight; this pin isolates
    # the marker's own acceptance at the entry point itself.
    engine._require_interleaved_termination_capability(  # pyright: ignore[reportPrivateUsage]
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
        engine._group_tx_instant(steps, 0, 1)  # pyright: ignore[reportPrivateUsage]
        == engine._INERT_CLOCK_INSTANT  # pyright: ignore[reportPrivateUsage]
    )


def test_versioned_non_temporal_version_attribute_is_none_for_a_temporal_entity() -> None:
    # A temporal entity's observation flows through `TemporalShadow`, never
    # this map — `m-opt-lock`'s version column is a non-temporal-only concept.
    meta = engine.load_case_metamodel(_load_case("m-navigate-012"))
    assert (
        engine._versioned_non_temporal_version_attribute(  # pyright: ignore[reportPrivateUsage]
            meta, "Policy"
        )
        is None
    )


def test_observe_group_find_is_a_no_op_for_a_temporal_target() -> None:
    # `_observe_group_find` returns before ever touching `tx` for a temporal
    # (or unversioned) target, so passing no real transaction is safe here.
    meta = engine.load_case_metamodel(_load_case("m-navigate-012"))
    observations: engine.ScenarioObservations = {}
    engine._observe_group_find(  # pyright: ignore[reportPrivateUsage]
        cast("Any", None), observations, meta, "Policy", [{"id": 1}]
    )
    assert observations == {}


def test_observe_group_find_skips_a_row_missing_its_version_field() -> None:
    # A row carrying the primary key but no version column (never reachable
    # for a well-formed corpus find) is skipped, not a KeyError — this seam
    # takes no data on faith.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    observations: engine.ScenarioObservations = {}
    engine._observe_group_find(  # pyright: ignore[reportPrivateUsage]
        cast("Any", None), observations, meta, "Account", [{"id": 1}]
    )
    assert observations == {}


def test_run_write_sequence_case_executes_each_entry_as_its_own_transaction() -> None:
    # COR-3 Phase 8 increment 4 (DQ4 re-route): each writeSequence entry is its
    # OWN `db.transact` unit — "the whole sequence in one transaction" retires.
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
    assert set(table_state) == {"orders", "order_item", "order_status", "order_tag"}


def test_run_write_sequence_case_records_the_temporal_observation_on_the_unit_of_work() -> None:
    # m-audit-write-002 (COR-3 Phase 8 increment 4): the update entry's shadow-
    # resolved observation is recorded on THIS unit's own `UnitOfWork` via the
    # documented neutral seam (`Transaction._buffer` route + `uow.observe`,
    # `_execute_write_unit`) — exactly what a real caller's own prior find
    # would have recorded.
    port = FakeWritePort()
    emissions, table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-audit-write-002"), "postgres", port
    )
    assert round_trips == 3
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert len(port.writes) == 3 and port.commits == 2
    assert table_state is not None and "balance" in table_state


def test_run_write_sequence_case_buffers_a_bounded_bitemporal_business_window() -> None:
    # m-bitemp-write-001 (COR-3 Phase 8 increment 4): the updateUntil entry's
    # canonical instruction carries BOTH a `businessFrom` and a `businessTo`
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
# Phase-8 mid-phase review remediation, finding C: the row-decomposition       #
# discriminator (`engine._decomposes_per_row`) is derived SEMANTICALLY —       #
# mutation kind, versioned-ness, per-row observation control keys, pk-gen      #
# management, and (for update) per-key value uniformity — never from the       #
# case's own authored `statements` count, which is a count-consistency        #
# ASSERTION only (verified independently, `_check_statement_count_            #
# consistency`). Finding E: a structured predicate-write instruction reaching  #
# this seam refuses loudly, never a bare `KeyError`.                          #
# --------------------------------------------------------------------------- #
def test_versioned_delete_decomposes_per_row_and_gates_each_key() -> None:
    # m-batch-write-004's own shape: a versioned entity's multi-row delete
    # decomposes per row and gates on each row's own `observedVersion`,
    # regardless of the authored `statements` count matching `len(rows)`
    # (which it does here too — the discriminator does not consult it either
    # way).
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
    assert [e.sql for e in emissions] == [
        "delete from account where id = ? and version = ?",
        "delete from account where id = ? and version = ?",
    ]


def test_rows_carrying_observation_keys_decompose_per_row_even_when_unversioned() -> None:
    # A per-row `observedVersion`/`observedInZ` control key is an explicit
    # per-row-observation signal REGARDLESS of the target's own versioned-ness
    # — pinning the discriminator's own independent criterion. Uses UNIFORM
    # values (which would otherwise collapse per the update-uniformity rule)
    # to prove the observation-key check fires FIRST. No reachable corpus
    # witness combines an unversioned entity with authored `observedVersion`
    # rows today (`m-batch-write-004`'s versioned witness reaches the SAME
    # decomposition through the versioned-ness check instead).
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
    emissions, round_trips = engine.compile_write_sequence_case(case, "postgres")
    assert round_trips == 2
    assert [e.sql for e in emissions] == [
        "update wallet set balance = ? where id = ?",
        "update wallet set balance = ? where id = ?",
    ]


def test_uniform_multi_row_update_collapses_to_one_in_list_statement() -> None:
    # m-batch-write-001's own update entry: an UNVERSIONED target whose rows
    # assign the SAME value collapses into ONE multi-row `IN`-list UPDATE
    # (COR-3 Phase 8 increment 5; m-batch-write "Set-based flush").
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


def test_authored_statement_count_mismatch_is_rejected() -> None:
    # `statements` is a count-consistency ASSERTION
    # (`compatibility-case.schema.json`), verified independently of the
    # derived instruction count — never the discriminator itself. Two rows,
    # each carrying its own `observedVersion` (a per-row-observation signal
    # that decomposes regardless), authored with a WRONG `statements: 1`.
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
    # Finding E's own witness (`m-batch-write-005`'s shape): a structured
    # PREDICATE-write instruction (`target`/`predicate`) reaching the scenario
    # compile lane is never mistaken for a keyed-write entry list (no bare
    # `KeyError`) — COR-3 Phase 8 increment 5 lowers it readless end to end.
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


def test_canonical_predicate_doc_maps_until_to_business_to_and_drops_at() -> None:
    # `m-case-format`'s own predicate-write authoring aliases: `at` (the
    # Clock-context processing-instant authoring alias) is dropped — never an
    # instruction field, ADR 0010; `until` (the businessTo authoring alias)
    # canonicalizes to the instruction-level `businessTo` field.
    # `businessFrom` is already axis-explicit and needs no translation.
    doc = engine._canonical_predicate_doc(  # pyright: ignore[reportPrivateUsage]
        {
            "mutation": "terminateUntil",
            "target": {
                "entity": "Position",
                "predicate": {"eq": {"attr": "Position.id", "value": 1}},
            },
            "at": "2024-10-01T00:00:00+00:00",
            "businessFrom": "2024-07-01T00:00:00+00:00",
            "until": "2024-09-01T00:00:00+00:00",
        }
    )
    assert "at" not in doc
    assert doc["businessFrom"] == "2024-07-01T00:00:00+00:00"
    assert doc["businessTo"] == "2024-09-01T00:00:00+00:00"


def test_run_scenario_case_executes_a_readless_predicate_write() -> None:
    # `m-batch-write-005`'s own shape, run end to end (no Docker): an
    # unversioned, non-temporal target's predicate delete buffers through
    # `Transaction._buffer_predicate_instruction` and lowers to ONE readless
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
    emissions, round_trips = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 1
    assert emissions[0].case_pointer == "/scenario/0/write"
    assert emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1 and port.commits == 1


def test_run_scenario_case_executes_a_materializing_predicate_write_pair() -> None:
    # A VERSIONED target's predicate delete MATERIALIZES (ADR 0014): the
    # scenario's own preceding find step pairs with it
    # (`_run_materializing_pair`), resolving through the SAME `FakeWritePort`
    # connection the subsequent gated per-row delete commits on — no Docker.
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
    port = FakeWritePort(find_rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    emissions, round_trips = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find", "/scenario/1/write"]
    assert emissions[1].sql == "delete from account where id = ? and version = ?"
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
    emissions, round_trips = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 1
    assert emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1
    assert port.commits == 0 and port.rollbacks == 1


def test_materializing_predicate_write_rollback_aborts_but_counts_the_round_trip() -> None:
    # `_run_materializing_pair`'s own abort contract: the resolve AND the
    # per-row gated DML it licenses still execute (and count their round
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
    port = FakeWritePort(find_rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    emissions, round_trips = engine.run_scenario_case(case, "postgres", port)
    assert round_trips == 2
    assert [e.case_pointer for e in emissions] == ["/scenario/0/find", "/scenario/1/write"]
    assert emissions[1].sql == "delete from account where id = ? and version = ?"
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
        engine._is_materializing_write_step(step, meta)  # pyright: ignore[reportPrivateUsage]
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
        engine._is_materializing_write_step(step, meta)  # pyright: ignore[reportPrivateUsage]
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
        engine._run_materializing_pair(  # pyright: ignore[reportPrivateUsage]
            FakeWritePort(), meta, POSTGRES, "locking", steps, 0
        )


def test_run_scenario_case_rejects_a_materializing_pair_whose_find_predicate_differs() -> None:
    # Finding 4 (`m-case-format.md:715`/`:719`): the preceding find must share
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
    port = FakeWritePort(find_rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
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


def test_run_conflict_case_temporal_close_form_composes_lower_temporal_close() -> None:
    # m-audit-write-006 (COR-3 Phase 8 increment 4): a temporal optimistic-lock
    # CLOSE conflict (`when.at` / `when.observedInZ`, no `observedVersion`) is
    # now driven through `handle.lower_temporal_close`, not the non-temporal
    # versioned-UPDATE path.
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-audit-write-006"]
    port = FakeWritePort()
    emissions, affected, table_state = engine.run_conflict_case(case, "postgres", port)
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert emissions[0].sql == (
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "balance" in table_state


def test_run_conflict_case_resolves_target_from_the_inheritance_family() -> None:
    # m-inheritance-105: `when.write` names no entity of its own; for an
    # inheritance-participant model `_conflict_target` resolves to the family's
    # SOLE concrete subtype (MeterReading, tag `meter`) — never the abstract
    # root `_rejected_target` resolves to for the read lane's own default-target
    # convention.
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-inheritance-105"]
    port = FakeWritePort()
    emissions, affected, table_state = engine.run_conflict_case(case, "postgres", port)
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert emissions[0].sql == (
        "update reading set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?"
    )
    assert affected == 1
    assert table_state is not None and "reading" in table_state


def test_run_conflict_case_temporal_attempts_form_retries_the_gated_close() -> None:
    # m-temporal-read-011: a TEMPORAL `when.attempts` retry — each attempt its
    # own `db.transact` unit composing `handle.lower_temporal_close` directly
    # (the `is_temporal` branch of the attempts loop, distinct from the
    # non-temporal versioned-UPDATE retry `m-opt-lock-007` already covers).
    (case,) = [c for c in case_format.load_cases() if c.case_id == "m-temporal-read-011"]
    port = FakeWritePort()
    emissions, affected, table_state = engine.run_conflict_case(case, "postgres", port)
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
