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
from pathlib import Path
from typing import Any, Final, cast

import pytest
from _metamodel_support import Declaration, attribute, key, source

from _support.document_reads import fold_mapping_rows
from parallax.conformance import case_format, engine, sweep
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INFINITY, STRING, AuthoredNumber, InstantError, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, Row
from parallax.core.metamodel import (
    AbstractRoot,
    AttributeIdentity,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    Table,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.temporal_read import Edge, Pin
from parallax.core.unit_work import (
    Concurrency,
    KeyTarget,
    MissingTargetError,
    ObjectKey,
    OptimisticLockConflictError,
    PredecessorRow,
    RetainedObservation,
    StaleWriteError,
    TemporalObservation,
    TemporalStateKey,
    VersionedStateKey,
    VersionObservation,
    WriteEffectError,
)
from parallax.snapshot import DeferredFeatureError
from parallax.snapshot.handle import WriteEvidenceError


def _rows(row: Row | None, key: str) -> list[Row]:
    """A graph leaf's relationship-attached rows, typed for test-side assertions
    (`then.graph`'s wire shape is intentionally a plain ``dict[str, object]``)."""
    assert row is not None
    return cast("list[Row]", row[key])


def _node(nodes: list[Row | None], index: int) -> Row:
    """One published graph position that carries a value.

    A position whose stored state contradicted the model carries ``null``, so a
    test asserting about the node itself states that it expected one.
    """
    node = nodes[index]
    assert node is not None
    return node


def _entry(entry: dict[str, object], key: str) -> Row:
    """A milestone-set `{pin, graph}` entry's own member, typed for test-side
    assertions (`then.graphs`' wire shape is a plain ``dict[str, object]``)."""
    return cast("Row", entry[key])


class FakeDbPort:
    """An in-memory port that records executed SQL and returns canned rows."""

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, list[object]]] = []

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return fold_mapping_rows(self.rows, document_reads)

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
    assert emissions[0].case_pointer == "/objectQuery"
    assert emissions[0].sql == (
        "select t0.id, t0.name from customer t0 where jsonb_extract_path_text(t0.address, ?) = ?"
    )
    assert emissions[0].binds == ("city", "Oslo")
    assert emissions[0].to_json()["casePointer"] == "/objectQuery"


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
    query = dict(cast("Mapping[str, object]", when["objectQuery"]))
    query["target"] = "parallax.compatibility.NoSuchEntity"
    when["objectQuery"] = query
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


def test_the_compile_lane_refuses_a_deferred_execution_feature() -> None:
    # The compile lane runs production's own read gate, Deferred Execution Feature
    # classification included: an adapter whose compile lane accepted a query its
    # own executor would refuse would claim two different supported surfaces. No
    # corpus case authors the combination, so the witness is synthetic — and it
    # never reaches SQL generation, which is the whole point.
    case = case_format.Case(
        path=Path("m-snapshot-read-999-synthetic.yaml"),
        case_id="m-snapshot-read-999",
        shape="read",
        tags=("m-snapshot-read", "slice-snapshot-1"),
        model="models/policy.yaml",
        document={
            "model": "models/policy.yaml",
            "when": {
                "objectQuery": {
                    "target": "parallax.compatibility.Policy",
                    "predicate": {"all": {}},
                    "temporal": {
                        "valid-time": {"asOf": "latest"},
                        "transaction-time": {"history": {}},
                    },
                    "includes": [
                        {"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}
                    ],
                }
            },
        },
    )
    with pytest.raises(DeferredFeatureError) as caught:
        engine.compile_read_case(case, "postgres")
    assert caught.value.features == ("snapshot-history-includes",)


def test_compile_rejects_non_read_shape() -> None:
    write_seq = next(c for c in case_format.load_cases() if c.shape == "writeSequence")
    with pytest.raises(engine.EngineError, match="only `read`-shape compile"):
        engine.compile_read_case(write_seq, "postgres")


def _synthetic(document: dict[str, object]) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path("m-predicate-999-synthetic.yaml"),
        case_id="m-predicate-999",
        shape="read",
        tags=("m-predicate", "slice-snapshot-1"),
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
        ({"model": "models/orders.yaml", "when": {}}, "no `objectQuery`"),
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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        self.reads.append((sql, list(binds)))
        return fold_mapping_rows(self.find_rows, document_reads)

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


# The rows a fake port answers the RESOLVING READ a keyed write owes
# (`m-case-format` *Resolving reads a write owes*). A write against existing
# state is addressed and licensed by a value a read published, so a fake driving
# one of these lanes has to publish that value — the canned run stands in for the
# one current milestone the real database holds, keyed by the projection's own
# physical column names.
_OPEN_MILESTONE: Final[dt.datetime] = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)


def _ledger_row(row_id: int, value: str, *, in_z: str) -> Row:
    return {
        "led_id": row_id,
        "acct_num": "B",
        "val": decimal.Decimal(value),
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
    }


def _balance_row(row_id: int, value: str, *, in_z: str) -> Row:
    return {
        "bal_id": row_id,
        "acct_num": "A",
        "val": decimal.Decimal(value),
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
    }


def _position_row(row_id: int, value: str, *, from_z: str, in_z: str) -> Row:
    return {
        "pos_id": row_id,
        "acct_num": "A",
        "val": decimal.Decimal(value),
        "from_z": dt.datetime.fromisoformat(from_z),
        "thru_z": _OPEN_MILESTONE,
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
    }


def _voyage_row(row_id: int, payload: dict[str, object], *, in_z: str) -> Row:
    return {
        "id": row_id,
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
        "payload": payload,
    }


# The milestone `m-txtime-write-010`'s own insert entry leaves current, as its
# update entry's resolving read publishes it: one Structured Column carrying
# every member, which is what a document-mapped chain carries forward.
_VOYAGE_MILESTONE: Final[Row] = _voyage_row(
    1,
    {"title": "Northern Run", "crew": 4, "manifest": {"cargo": "timber"}, "legs": []},
    in_z="2026-01-01T00:00:00+00:00",
)


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


def _ledger_update(
    value: str, at: str, *, uow: str | None = None, rollback: bool = False
) -> dict[str, object]:
    """One scenario write step updating the Transaction-Time-Only Ledger id 2 —
    the fixture key holding exactly ONE current milestone (acct B, 200.00, known
    from 2024-02-01), so a step naming no observed edge resolves unambiguously."""
    step: dict[str, object] = {
        "write": [
            {
                "mutation": "update",
                "entity": "parallax.compatibility.Ledger",
                "rows": [{"id": 2, "value": decimal.Decimal(value)}],
                "at": at,
            }
        ],
        "roundTrips": 2,
    }
    if uow is not None:
        step["uow"] = uow
    if rollback:
        step["rollback"] = True
    return step


def _synthetic_ledger_scenario(steps: list[dict[str, object]]) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path("m-unit-work-998-synthetic.yaml"),
        case_id="m-unit-work-998",
        shape="scenario",
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/ledger.yaml",
        document={
            "model": "models/ledger.yaml",
            "shape": "scenario",
            "when": {"uow": {"concurrency": "optimistic"}, "scenario": steps},
        },
    )


def test_run_scenario_case_commits_writes_and_reads_committed_state() -> None:
    port = FakeWritePort(find_rows=[{"id": 7}])
    run = engine.run_scenario_case(_case("m-unit-work-001"), "postgres", port)
    assert run.round_trips == 2
    assert run.errors == []  # a keyed unit-of-work scenario reports no error observation
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/write",
        "/scenario/1/objectQuery",
    ]
    assert run.emissions[0].sql.startswith("insert into account")
    # Account is versioned, so the case's default preference resolves it to the
    # Optimistic strategy and the participating find renders no lock suffix.
    assert not run.emissions[1].sql.endswith("for share of t0")
    assert len(port.writes) == 1 and len(port.reads) == 1
    # An UNGROUPED find runs in its OWN transaction, exactly as `run_read_case`
    # does: every scenario resolves a Concurrency Preference (declared or the
    # default), and a participating read needs a boundary to demarcate whatever
    # lock its target Entity's own strategy calls for — so the find commits one.
    assert port.commits == 2 and port.rollbacks == 0


def test_run_scenario_case_rollback_step_aborts_but_counts_the_round_trip() -> None:
    port = FakeWritePort(find_rows=[])
    run = engine.run_scenario_case(_case("m-unit-work-011"), "postgres", port)
    assert run.round_trips == 2  # the aborted insert still counts one round trip
    assert len(port.writes) == 1  # the DML executed before the abort
    # An UNGROUPED find runs in its OWN transaction, exactly as `run_read_case`
    # does: every scenario resolves a Concurrency Preference (declared or the
    # default), and a participating read needs a boundary to demarcate whatever
    # lock its target Entity's own strategy calls for — so the find commits one.
    assert port.rollbacks == 1 and port.commits == 1
    assert run.emissions[0].case_pointer == "/scenario/0/write"


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
    run = engine.run_scenario_case(_case("m-unit-work-005"), "postgres", port)
    assert run.round_trips == 3
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
        "/scenario/2/objectQuery",
    ]
    # The write's SET version bind is the OBSERVED version (1) advanced to 2 —
    # a genuine transaction-scoped observation this SAME group's own find
    # recorded, never an authored value — and the same observed 1 binds the
    # gate the default preference renders (`update ... set balance = ?,
    # version = ? where id = ? and version = ?`).
    assert run.emissions[1].sql.startswith("update account set")
    assert run.emissions[1].binds == (175.00, 2, 1, 1)
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
    run = engine.run_scenario_case(_case("m-unit-work-002"), "postgres", port)
    assert run.round_trips == 3
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
        "/scenario/2/objectQuery",
    ]
    assert len(port.writes) == 1  # the doomed write's DML still executed (and counted)
    assert len(port.reads) == 2  # the grouped observe find + the ungrouped post-abort find
    # An UNGROUPED find runs in its OWN transaction, exactly as `run_read_case`
    # does: every scenario resolves a Concurrency Preference (declared or the
    # default), and a participating read needs a boundary to demarcate whatever
    # lock its target Entity's own strategy calls for — so the find commits one.
    assert port.commits == 1 and port.rollbacks == 1


def test_run_scenario_case_discards_an_aborted_ungrouped_temporal_writes_case_state() -> None:
    # `m-case-format` "a later find MUST re-resolve and observe the ORIGINAL
    # rows, never the aborted write" applies to the milestone case state holds
    # as much as to the rows: the aborted step's close retires the fixture
    # milestone and its successor is tracked as the new current one, and the
    # abort then erases the successor the database never kept. A later keyed
    # temporal write must therefore consume the ORIGINAL milestone again —
    # gating its own close on the fixture's Transaction-Time start (2024-02-01),
    # not on the aborted successor's (2026-01-01), which would match zero rows.
    #
    # The canned row is the fixture milestone each step's own resolving read
    # publishes — the value a keyed write is addressed by — so what this asserts
    # is the observation the PURE re-lowering oracle plans with, which is where
    # the tracked case state lives.
    port = FakeWritePort(find_rows=[_ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")])
    case = _synthetic_ledger_scenario(
        [
            _ledger_update("999.00", "2026-01-01T00:00:00+00:00", rollback=True),
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    run = engine.run_scenario_case(case, "postgres", port)
    assert port.rollbacks == 1 and port.commits == 1
    aborted_close, _aborted_successor, close, successor = run.emissions
    assert aborted_close.binds[3] == "2024-02-01T00:00:00+00:00"
    assert close.case_pointer == "/scenario/1/write"
    assert close.binds[3] == "2024-02-01T00:00:00+00:00"
    # The successor is chained off the ORIGINAL row too — `acct_num` is the
    # fixture's own B, never the aborted write's carried-forward value.
    assert successor.binds[1] == "B"


def test_scenario_compile_lane_closes_the_fixture_milestone_the_run_lane_closes() -> None:
    # A keyed unit-of-work scenario whose only temporal write settles against
    # PERSISTED history: the milestone it closes was declared by the model's
    # fixtures, never opened by a step of this case. Both lanes owe the same DML
    # for the same case, so the compile lane starts from the same fixture-declared
    # history the run lane's database is provisioned with — otherwise the close
    # has no Temporal Observation to address and the case is refused at compile
    # while the run lane executes it.
    case = _synthetic_ledger_scenario([_ledger_update("300.00", "2024-05-01T00:00:00+00:00")])
    port = FakeWritePort(find_rows=[_ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")])

    compiled, _round_trips = engine.compile_scenario_case(case, "postgres")
    run = engine.run_scenario_case(case, "postgres", port)

    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]
    close, successor = compiled
    # The fixture milestone's OWN edge is what the close gates on, and the
    # successor carries the fixture's acct_num forward: facts only a seeded
    # tracker holds.
    assert close.binds[3] == "2024-02-01T00:00:00+00:00"
    assert successor.binds[:3] == (2, "B", decimal.Decimal("300.00"))


def _ledger_insert(at: str) -> dict[str, object]:
    """One scenario write step inserting Ledger id 9 — a key NO fixture holds, so
    every milestone a later step of these cases closes is one this case's own
    steps opened. That is what isolates the tracker's in-scenario advance and its
    staged restore from the fixture history both lanes seed themselves with: an
    assertion about which milestone a later step gates on can only be answering
    for a milestone an earlier step put there."""
    return {
        "write": [
            {
                "mutation": "insert",
                "entity": "parallax.compatibility.Ledger",
                "rows": [{"id": 9, "acctNum": "D", "value": decimal.Decimal("100.00")}],
                "at": at,
            }
        ],
        "roundTrips": 1,
    }


def _ledger_chain_update(
    value: str, at: str, *, uow: str | None = None, rollback: bool = False
) -> dict[str, object]:
    """The sibling of :func:`_ledger_update` retargeted at the inserted id 9."""
    step = _ledger_update(value, at, uow=uow, rollback=rollback)
    cast("list[dict[str, object]]", step["write"])[0]["rows"] = [
        {"id": 9, "value": decimal.Decimal(value)}
    ]
    return step


def test_scenario_compile_lane_discards_an_aborted_ungrouped_writes_case_state() -> None:
    # The compile lane owes the SAME DML the run lane executes for a
    # compile-eligible case, and `m-case-format`'s abort contract is not
    # declared run-only: after a rolled-back temporal update, the next keyed
    # write closes the milestone the database KEPT (the insert's own
    # 2025-01-01 Transaction-Time start), never the aborted successor's
    # 2026-01-01, which no transaction ever stored.
    case = _synthetic_ledger_scenario(
        [
            _ledger_insert("2025-01-01T00:00:00+00:00"),
            _ledger_chain_update("300.00", "2026-01-01T00:00:00+00:00", rollback=True),
            _ledger_chain_update("400.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    compiled, _round_trips = engine.compile_scenario_case(case, "postgres")
    _insert, aborted_close, _aborted_successor, close, successor = compiled
    assert aborted_close.binds[3] == "2025-01-01T00:00:00+00:00"
    assert close.case_pointer == "/scenario/2/write"
    assert close.binds[3] == "2025-01-01T00:00:00+00:00"
    assert successor.binds[2] == decimal.Decimal("400.00")
    # Each update step is its own transaction, so each owes a resolving read of
    # the milestone the insert left current — the value its keyed verb is
    # addressed by.
    port = FakeWritePort(find_rows=[_ledger_row(9, "100.00", in_z="2025-01-01T00:00:00+00:00")])
    run = engine.run_scenario_case(case, "postgres", port)
    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]


def test_scenario_compile_lane_stages_a_doomed_uow_groups_case_state() -> None:
    # Staging, not simply "do not advance", in the compile lane too: step 2
    # closes step 1's own successor because both belong to the SAME doomed
    # group (gating on 2026-01-01), while the ungrouped step 3 that follows the
    # group's rollback is back on the insert's milestone (2025-01-01).
    #
    # The compile lane is where a chained pair like this can be stated at all:
    # the run lane writes through the public keyed verbs, where two writes
    # settling against one observed state COALESCE rather than chain
    # (`m-unit-work-025`), so a later write settling against an earlier write's
    # own successor is not something a caller can express. Both lanes stage a
    # doomed group by the same rule, which is what this asserts.
    case = _synthetic_ledger_scenario(
        [
            _ledger_insert("2025-01-01T00:00:00+00:00"),
            _ledger_chain_update(
                "999.00", "2026-01-01T00:00:00+00:00", uow="doomed", rollback=True
            ),
            _ledger_chain_update("888.00", "2026-01-01T00:00:00+00:00", uow="doomed"),
            _ledger_chain_update("300.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    compiled, _round_trips = engine.compile_scenario_case(case, "postgres")
    _insert, doomed_close, _doomed_successor, own_close, _own_successor, close, _successor = (
        compiled
    )
    assert doomed_close.binds[3] == "2025-01-01T00:00:00+00:00"
    assert own_close.binds[3] == "2026-01-01T00:00:00+00:00"
    assert close.case_pointer == "/scenario/3/write"
    assert close.binds[3] == "2025-01-01T00:00:00+00:00"


def _two_group_interleave_steps() -> list[dict[str, object]]:
    return [
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
            "roundTrips": 1,
            "statements": [{"sql": {"postgres": "select ... where t0.id = ?"}, "binds": [1]}],
        },
        {
            "uow": "b",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 2}},
            },
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


def test_scenario_compile_lane_stages_nothing_for_a_doomed_interleaved_group() -> None:
    # A doomed group that INTERLEAVES with another is the one shape the compile
    # lane's staging cannot represent — two concurrent units advance one tracker
    # there, so restoring the whole tracker would discard the committed group's
    # advances too. Every case carrying the shape is `compileEligibility:
    # run-only`, so the lane lowers the steps in authored order and stages
    # nothing rather than refusing.
    steps = _two_group_interleave_steps()
    steps[2]["rollback"] = True
    case = _synthetic_write("scenario", {"when": {"scenario": steps}, "then": {"roundTrips": 3}})
    emissions, _round_trips = engine.compile_scenario_case(case, "postgres")
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/objectQuery",
    ]


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
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
        },
        {
            "uow": "b",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 2}},
            },
        },
        {
            "uow": "c",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 3}},
            },
        },
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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
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


def _wire_row(row: Row) -> dict[str, object]:
    """One authored row as the Wire spelling a find step's own rows carry."""
    return {key: engine.wire_value(value) for key, value in row.items()}


def test_run_interleaved_scenario_case_renders_the_conflict_and_discards_the_abort() -> None:
    # `m-opt-lock-012` end to end over two SCRIPTED fake connections (never a
    # real database): the `ours` group's own observing find (step 0) is stale
    # by the time it flushes (step 3) — the `concurrent` group (steps 1-2)
    # committed its own gated update first — so the doomed group's SECOND
    # write (the version-gated update) affects 0 rows, and the group's own
    # buffered insert (account 9) is discarded with it. The trailing
    # ungrouped verify find (step 4) observes no rows for it.
    case = _load_case("m-opt-lock-012")
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
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
        "/scenario/0/objectQuery",
        "/scenario/1/objectQuery",
        "/scenario/2/write",
        "/scenario/3/write",
        "/scenario/3/write",
        "/scenario/4/objectQuery",
    ]
    assert emissions[3].sql.startswith("insert into account")
    assert emissions[4].sql.startswith("update account set")
    assert len(main_port.writes) == 2  # the doomed group's insert + gated update
    assert len(peer_port.writes) == 1  # the concurrent group's own gated update
    # Every find step's own observed rows, in
    # scenario step order (0, 1, then the trailing ungrouped verify at 4) —
    # the doomed group's discarded insert leaves account 9 absent. The rows are
    # the Wire result re-keyed by column, so a `decimal` reads as its canonical
    # string exactly as the grader's own wire space compares it.
    assert find_rows == [[_wire_row(row_v1)], [_wire_row(row_v1)], []]


def test_run_interleaved_scenario_case_applies_out_of_band_statements_before_the_groups() -> None:
    # The interleaved executor owes the same `given.apply` setup the other scenario
    # executors do: applied on the caller's own port after the fixtures and before
    # either worker starts, so both groups race against the state it left. Its own
    # first write lands after it in `writes` order, which is what pins the ordering.
    case = _load_case("m-opt-lock-012")
    with_apply = dataclasses.replace(
        case,
        document={
            **case.document,
            "given": {"fixtures": True, "apply": [{"sql": "update account set balance = ?"}]},
        },
    )
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    main_port = _ScriptedPort(read_rows=[[row_v1], []], write_affected=[1, 0, 0])
    peer_port = _ScriptedPort(read_rows=[[row_v1]], write_affected=[1])

    engine.run_interleaved_scenario_case(with_apply, "postgres", main_port, lambda: peer_port)

    assert main_port.writes[0][0] == "update account set balance = %s"
    assert len(main_port.writes) == 3  # the statement, then the doomed group's two


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
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                        },
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
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                        },
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
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
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
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                        },
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
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 3}},
                        },
                    },
                ],
            },
            "then": {"roundTrips": 4},
        },
    )
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    row3: Row = {
        "id": 3,
        "owner": "Ada",
        "balance": decimal.Decimal("10.00"),
        "version": 1,
    }
    main_port = _ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 1])
    peer_port = _ScriptedPort(read_rows=[[row3]])

    emissions, round_trips, conflict_actual, find_rows = engine.run_interleaved_scenario_case(
        case, "postgres", main_port, lambda: peer_port
    )

    assert conflict_actual is None
    assert round_trips == 4
    assert len(main_port.writes) == 2  # buffered together, flushed once at the group's last step
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
        "/scenario/2/write",
        "/scenario/3/objectQuery",
    ]
    assert find_rows == [[_wire_row(row_v1)], [_wire_row(row3)]]


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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:  # pragma: no cover
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

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:  # pragma: no cover
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
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
        },
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
        },
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
    own identity and Observed State Key for it, beside the milestone it is."""
    members: dict[str, object] = {
        "id": 1,
        "name": name,
        "validStart": valid_start,
        "validEnd": valid_end,
        "txStart": _APR,
        "txEnd": INFINITY,
    }
    return RetainedObservation(
        TemporalStateKey(_POLICY, Edge(valid_time=valid_start, tx_time=_APR)),
        TemporalObservation(predecessor=PredecessorRow(members=members)),
        None,
    )


def _settled(source: Any) -> Any:
    return engine._settled_against_source(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        "Policy", _POLICY, source
    )


def test_a_settled_write_settles_against_the_node_the_named_find_observed() -> None:
    # A milestone chain holds more than one row per primary key, so one find may
    # return several and each is evidence about the milestone it actually is. The
    # pure oracle plans with the ONE the write step's own `on` reference named —
    # production's own retained record rather than a coordinate this engine
    # re-derived.
    head = _policy_node(_JAN, _JUN, "head")
    tail = _policy_node(_JUN, INFINITY, "tail")
    for node, expected in ((head, "head"), (tail, "tail")):
        observation = _settled((node,))
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
        engine._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": []}, 2, {}
        )
        is None
    )


def test_a_source_find_reference_names_one_index() -> None:
    with pytest.raises(engine.EngineError, match="settles against ONE find step"):
        engine._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": [], "on": [0, 1]}, 2, {}
        )


def test_a_source_find_reference_answers_what_that_find_published() -> None:
    # A find of the same group that published no row still answers, with an empty
    # record: the reference resolved, and it is the WRITE's own source resolution
    # that then finds no value to be addressed by.
    assert (
        engine._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": [], "on": 1}, 2, {1: ()}
        )
        == ()
    )


def test_a_source_find_reference_names_a_find_of_its_own_group() -> None:
    # A reference the group's own recorded finds cannot satisfy names a step
    # outside the group, one that is not a find, or one that has not run yet —
    # refused rather than resolved to "the find observed nothing".
    with pytest.raises(engine.EngineError, match="not an EARLIER find step"):
        engine._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"write": [], "on": 0}, 2, {}
        )


def _account_node(version: int) -> Any:
    """One node a grouped find of the versioned `Account` published."""
    key = ObjectKey(EntityIdentity("parallax.compatibility", "Account"), (("id", 1),))
    return RetainedObservation(
        VersionedStateKey(key, version), VersionObservation(observed_version=version), None
    )


def test_a_settled_write_names_a_versioned_targets_own_read_generation() -> None:
    # A versioned Non-Temporal target holds one ROW per primary key, but a unit of
    # work holds one observed GENERATION of it per read: a group that observes the
    # row, writes it, and reads it again holds two, and the reference is what says
    # which of them a write settles against. A store keyed by identity alone
    # answers only the latest, so the earlier generation would be unreachable.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))

    def settle(node: Any) -> object:
        write = engine._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": 5.00}]},
            meta,
            TemporalShadow(),
            set(),
            [],
            (node,),
        )[0]
        return write.oracle_observation

    assert settle(_account_node(1)) == _account_node(1).evidence
    assert settle(_account_node(4)) == _account_node(4).evidence


def test_a_settled_write_is_refused_when_its_named_find_observed_no_such_row() -> None:
    # The reference names evidence that does not exist, and a write with no
    # evidence at all is refused where every unobserved keyed write is.
    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    with pytest.raises(engine.EngineError, match="observed 0 rows"):
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
    return RetainedObservation(
        TemporalStateKey(key, Edge(tx_time=start)),
        TemporalObservation(predecessor=PredecessorRow(members=members)),
        None,
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
        observation = write.oracle_observation
        assert isinstance(observation, TemporalObservation)
        return observation.predecessor.members["txStart"]

    assert settle(current) == current.evidence.predecessor.members["txStart"]
    assert settle(historical) == historical.evidence.predecessor.members["txStart"]


def test_run_scenario_case_settles_a_grouped_temporal_close_against_the_find_it_names() -> None:
    # m-unit-work-015: two finds of ONE bitemporal key observe two rectangles both
    # current on Transaction Time, and the write step names the first with `on`.
    # The evidence the write settles by is the Observed State Key the claim that
    # node carries is addressed by, and the golden the oracle renders comes from
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
    run = engine.run_scenario_case(_load_case("m-unit-work-015"), "postgres", port)
    assert run.round_trips == 5
    assert run.log is not None and run.log.round_trips == 5
    # The close plus the two rectangles the split chains, all under the write
    # step's own pointer.
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/objectQuery",
        *["/scenario/2/write"] * 3,
    ]
    close = run.emissions[2]
    assert close.sql.startswith("update position set out_z = ?")
    # The close's address is the OBSERVED rectangle's own `thru_z`, derived from
    # the node the named find published — never the primary key alone.
    assert close.binds[2] == dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def test_a_tracked_milestone_of_a_document_target_is_refused_after_out_of_band_statements() -> None:
    # m-txtime-write-011 seeds a Structured Column key no member declares with
    # out-of-band SQL and then updates that milestone by key. The tracker never
    # saw the seeded document and the framework issues no resolving read for a
    # keyed write, so the successor would be patched from declared members alone
    # and lose the key. The engine names the shape instead of chaining it.
    port = FakeWritePort()
    with pytest.raises(engine.EngineError, match="out-of-band statements may have overtaken"):
        engine.run_write_sequence_case(_load_case("m-txtime-write-011"), "postgres", port)


def test_a_tracked_milestone_under_columns_survives_out_of_band_statements() -> None:
    # The refusal is scoped to Relational Document Layout, where the tracked
    # members cannot even account for the row's SLOTS. Under `Columns` the tracker
    # holds every column, so out-of-band state leaves the observation STALE — the
    # very thing a conflict case authors on purpose — never unrepresentable.
    meta = engine.load_case_metamodel(_load_case("m-txtime-write-002"))
    model = meta
    shadow = TemporalShadow()
    shadow.note_out_of_band_write()
    engine._refuse_unaccounted_document_milestone(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        model,
        engine.case_entity(model, "parallax.compatibility.Balance"),
        {"id": 1},
        shadow,
    )


def test_a_tracked_milestone_of_a_document_target_chains_when_the_case_authored_it() -> None:
    # m-txtime-write-010 is the same document-mapped chain with no out-of-band
    # statement: every key in the stored document came from the case's own insert,
    # so the tracked milestone IS the whole stored row and the successor chains.
    # This is what keeps the refusal above narrow enough to leave the corpus alone.
    port = FakeWritePort(find_rows=[_VOYAGE_MILESTONE])
    emissions, _table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-txtime-write-010"), "postgres", port
    )
    # Three DML statements plus the update entry's own resolving read.
    assert round_trips == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]


def test_a_document_milestone_opened_after_out_of_band_statements_still_chains() -> None:
    # The same chain with an out-of-band statement in front of it. The insert
    # opens the milestone the update addresses AFTER those statements ran, and a
    # Planned Insert's entry row is the whole row the flush writes, so the tracker
    # accounts for that milestone whole again. Refusing here would refuse the very
    # state `m-case-format` requires a keyed write to consume — the milestone the
    # case's own earlier entries left current — which is why the refusal is keyed
    # to the addressed milestone rather than to the case.
    case = _load_case("m-txtime-write-010")
    with_apply = dataclasses.replace(
        case,
        document={
            **case.document,
            "given": {"apply": [{"sql": "insert into unrelated(id) values (1)"}]},
        },
    )
    port = FakeWritePort(find_rows=[_VOYAGE_MILESTONE])
    emissions, _table_state, round_trips = engine.run_write_sequence_case(
        with_apply, "postgres", port
    )
    assert round_trips == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert port.writes[0][0].startswith("insert into unrelated")


def test_a_read_step_names_its_own_object_query() -> None:
    with pytest.raises(engine.EngineError, match="needs `objectQuery`"):
        engine._step_query({"roundTrips": 1})  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly


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


def test_run_write_sequence_case_settles_a_temporal_write_against_its_resolving_read() -> None:
    # m-txtime-write-002: the update entry is its own choreography unit, so the
    # milestone it closes comes from the read that unit issues for it — the value
    # `tx.wire.update` is addressed and licensed by — and the round trips count
    # that read beside the three DML statements.
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    emissions, table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-txtime-write-002"), "postgres", port
    )
    assert round_trips == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert len(port.writes) == 3 and port.commits == 2
    assert table_state is not None and "balance" in table_state


def test_run_write_sequence_case_buffers_a_bounded_bitemporal_valid_time_window() -> None:
    # m-bitemp-write-001: the updateUntil entry's canonical instruction carries
    # BOTH `validFrom` and `until` (its bounded rectangle-split window), which
    # `_execute_write_unit` hands `tx.wire.update_until` unchanged.
    port = FakeWritePort(
        find_rows=[
            _position_row(
                1, "100.00", from_z="2024-01-01T00:00:00+00:00", in_z="2024-01-01T00:00:00+00:00"
            )
        ]
    )
    _emissions, table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-bitemp-write-001"), "postgres", port
    )
    assert round_trips == 6
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
    # too — the discriminator does not consult it either way). `Account` is
    # versioned, so the default `optimistic` preference gates each key on its
    # own observed version.
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
        ("delete from account where id = ? and version = ?", (1, 1)),
        ("delete from account where id = ? and version = ?", (2, 1)),
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
    # wire-spelled floats, and the engine decodes each row to its native carrier
    # before handing it to `tx.wire.insert` — the collapse into one statement
    # happens afterwards, in the planner.
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
        "update account set balance = ?, version = ? where id = ? and version = ?"
    ]
    assert emissions[0].binds == (5.00, 2, 2, 1)


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
    # unversioned, non-temporal target's predicate delete is stated through
    # `tx.wire.delete_where` and lowers to ONE readless statement —
    # `_run_readless_predicate_write`'s own production seam.
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
    run = engine.run_scenario_case(case, "postgres", port)
    assert run.round_trips == 1
    assert run.emissions[0].case_pointer == "/scenario/0/write"
    assert run.emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1 and port.commits == 1


def test_run_scenario_case_executes_a_materializing_predicate_write_pair() -> None:
    # A VERSIONED target's predicate delete MATERIALIZES (ADR 0014): the
    # scenario's own preceding find step pairs with it
    # (`_run_materializing_pair`), resolving through the SAME `FakeWritePort`
    # connection the subsequent per-row delete commits on — no Docker. The case
    # declares no `when.uow`, so it runs under the resolved `optimistic`
    # preference, which a versioned target turns into the Optimistic strategy:
    # each materialized key is gated.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"lessThan": {"attr": "Account.balance", "value": 200.00}},
                        },
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
    run = engine.run_scenario_case(case, "postgres", port)
    assert run.round_trips == 2
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
    ]
    assert run.emissions[1].sql == "delete from account where id = ? and version = ?"
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
    run = engine.run_scenario_case(case, "postgres", port)
    assert run.round_trips == 1
    assert run.emissions[0].sql == "delete from wallet where balance < ?"
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
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"lessThan": {"attr": "Account.balance", "value": 200.00}},
                        },
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
    run = engine.run_scenario_case(case, "postgres", port)
    assert run.round_trips == 2
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
    ]
    assert run.emissions[1].sql == "delete from account where id = ? and version = ?"
    assert len(port.writes) == 1 and len(port.reads) == 1
    assert port.commits == 0 and port.rollbacks == 1


def _ledger_predicate() -> dict[str, object]:
    return {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}}


def _ledger_materializing_pair(at: str, *, rollback: bool = False) -> list[dict[str, object]]:
    """The resolving find + materializing predicate update over the fixture-held
    Ledger id 2 that `m-case-format` "Materializing cases" runs as ONE
    transaction: production resolves the predicate itself and plans a close plus a
    successor per resolved row."""
    write: dict[str, object] = {
        "write": {
            "mutation": "update",
            "target": {
                "entity": "parallax.compatibility.Ledger",
                "predicate": _ledger_predicate(),
            },
            "assignments": [{"attr": "parallax.compatibility.Ledger.value", "value": 777.00}],
            "at": at,
        },
        "roundTrips": 3,
    }
    if rollback:
        write["rollback"] = True
    return [
        {
            "objectQuery": {
                "target": "parallax.compatibility.Ledger",
                "predicate": _ledger_predicate(),
            },
            "roundTrips": 1,
        },
        write,
    ]


def _ledger_resolve_port(*rows: Row) -> FakeWritePort:
    fixture: Row = {
        "led_id": 2,
        "acct_num": "B",
        "val": decimal.Decimal("200.00"),
        "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }
    return FakeWritePort(find_rows=[fixture, *rows])


def test_run_scenario_case_refuses_a_keyed_temporal_write_after_a_materializing_pair() -> None:
    # The materializing pair resolves its rows and plans their closes and
    # successors INSIDE production, which returns neither, so this lane cannot
    # advance case state to the milestone that transaction opened. A later keyed
    # temporal write would gate its own close on the milestone the pair retired
    # (the fixture's 2024-02-01) and quietly affect zero rows, while a real
    # caller — who could only have reached the step by reading the row — gates on
    # the successor and gets a stale write. The composition is refused rather
    # than graded, so the two answers can never be mistaken for one.
    case = _synthetic_ledger_scenario(
        [
            *_ledger_materializing_pair("2025-05-01T00:00:00+00:00"),
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    with pytest.raises(engine.EngineError, match="materializing predicate write already moved"):
        engine.run_scenario_case(case, "postgres", _ledger_resolve_port())


def test_run_scenario_case_keeps_case_state_when_a_materializing_pair_aborts() -> None:
    # An ABORTED pair moved nothing: its close and successor were rolled back with
    # the rest of its transaction, so the milestone the fixture left current is
    # still current and the next keyed write settles against it. The record of
    # what materialization displaced is staged on the pair's own outcome, exactly
    # as every other unit's case-state advances are.
    case = _synthetic_ledger_scenario(
        [
            *_ledger_materializing_pair("2025-05-01T00:00:00+00:00", rollback=True),
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    port = _ledger_resolve_port()
    run = engine.run_scenario_case(case, "postgres", port)
    assert port.rollbacks == 1 and port.commits == 1
    close, _successor = run.emissions[-2:]
    assert close.case_pointer == "/scenario/2/write"
    assert close.binds[3] == "2024-02-01T00:00:00+00:00"


def test_run_scenario_case_chains_a_key_inserted_after_a_materializing_pair() -> None:
    # The refusal is scoped to the milestones the pair displaced, never to the
    # case: a milestone this case's own later write OPENS is a complete account of
    # its row again, so an insert-then-update chain over a key the pair never held
    # stays legal and closes the milestone the insert opened (2025-06-01).
    case = _synthetic_ledger_scenario(
        [
            *_ledger_materializing_pair("2025-05-01T00:00:00+00:00"),
            _ledger_insert("2025-06-01T00:00:00+00:00"),
            _ledger_chain_update("300.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    run = engine.run_scenario_case(
        case,
        "postgres",
        _ledger_resolve_port(_ledger_row(9, "100.00", in_z="2025-06-01T00:00:00+00:00")),
    )
    close = run.emissions[-2]
    assert close.case_pointer == "/scenario/3/write"
    assert close.binds[3] == "2025-06-01T00:00:00+00:00"


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
    # the find step's own query `target` against `pairing.target.entity` before ever
    # calling this function, so the guard is unreachable through the public
    # entry point — a genuine caller-contract defense, pinned here by
    # calling the function directly with a manufactured mismatch.
    from parallax.core.dialect import POSTGRES

    meta = engine.load_case_metamodel(_case("m-unit-work-001"))
    steps: list[Mapping[str, object]] = [
        {
            "objectQuery": {
                "target": "Wallet",
                "predicate": {"eq": {"attr": "Wallet.id", "value": 1}},
            }
        },
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
            FakeWritePort(), meta, POSTGRES, "locking", steps, 0, TemporalShadow()
        )


def test_run_scenario_case_rejects_a_materializing_pair_whose_find_predicate_differs() -> None:
    # (`m-case-format.md`, "Predicate-selected write instruction": "model-aware
    # validation MUST require that prior read to use the same concrete query
    # `target` and canonical predicate"): the preceding find must share
    # the write's own target predicate, not merely its entity — unlike the
    # entity-mismatch guard above, this IS reachable through the public
    # `run_scenario_case` entry point: the look-ahead pairing decision
    # (`run_scenario_case`) checks only the query's `target`, so a same-entity,
    # DIFFERENT-predicate pair still routes into `_run_materializing_pair`,
    # whose own canonical-predicate comparison is what catches it.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.balance", "value": 100.00}},
                        },
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
    with pytest.raises(engine.EngineError, match="SAME canonical predicate"):
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
#                                                                             #
# Every attempt takes a REAL source read, so each port here answers the rows   #
# the attempt writes against; the fake serves one canned result to every read, #
# which is enough because a conflict attempt reads exactly once.               #
# --------------------------------------------------------------------------- #
_ACCOUNT_ROW_2: Final[Row] = {
    "id": 2,
    "owner": "Linus",
    "balance": decimal.Decimal("250.00"),
    "version": 1,
}


def test_run_conflict_case_single_attempt() -> None:
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-006"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "account" in table_state


def test_run_conflict_case_reads_its_source_before_applying_given_apply() -> None:
    # The concurrent writer commits BETWEEN the source read and the write it
    # invalidates: a read taken after it would observe the state it left, and
    # the stale gate the case grades would never be reachable.
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-005"), "postgres", port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert port.reads[0][0].startswith("select")  # the source read ran first
    # given.apply's naive out-of-band bump, THEN the gated update.
    assert [sql for sql, _binds in port.writes] == [
        "update account set balance = 999.00, version = 2 where id = 2",
        "update account set balance = %s, version = %s where id = %s and version = %s",
    ]
    assert affected == 1  # the fake port always reports 1; the real 0-row
    # conflict proof runs against a reset database (test_conflict_run_sweep).
    assert table_state is not None


class _ZeroAffectedPort(FakeWritePort):
    """A port whose golden write reports a zero-row shortfall (a concurrent
    writer already moved or removed the row)."""

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        super().execute_write(sql, binds)
        return (
            0 if sql.startswith(("update account set balance = %s", "delete from account")) else 1
        )


def test_run_conflict_case_renders_a_gated_zero_row_update_as_a_conflict() -> None:
    port = _ZeroAffectedPort(find_rows=[_ACCOUNT_ROW_2])
    _emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-opt-lock-005"), "postgres", port
    )
    assert affected == 0


def test_a_conflict_attempt_whose_source_read_finds_no_row_is_refused() -> None:
    # A target `given.apply` already removed leaves the attempt with no value to
    # write, so a case authoring that state is unauthorable through the public
    # verbs rather than merely unpleasant.
    port = FakeWritePort(find_rows=[])
    with pytest.raises(engine.EngineError, match="found no row for"):
        engine.run_conflict_case(_load_case("m-opt-lock-006"), "postgres", port)


def test_a_conflict_attempt_declaring_a_version_its_read_did_not_observe_is_refused() -> None:
    # The declared `observedVersion` renders the golden's gate bind while the
    # real write settles against what the read saw, so the two must name one
    # state or the case grades a statement no read of this lane produced.
    port = FakeWritePort(find_rows=[{**_ACCOUNT_ROW_2, "version": 7}])
    with pytest.raises(engine.EngineError, match="its own source read observed 7"):
        engine.run_conflict_case(_load_case("m-opt-lock-006"), "postgres", port)


def test_a_conflict_attempt_writes_through_the_public_keyed_delete_verb() -> None:
    # `when.mutation: delete` reaches `tx.wire.delete`, keyed off the node the
    # source read published — the destructive arm of the same one ingress the
    # update arm takes.
    case = _synthetic_write(
        "conflict",
        {
            "when": {
                "uow": {"concurrency": "optimistic"},
                "mutation": "delete",
                "write": {"id": 2, "observedVersion": 1},
            }
        },
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        case, "postgres", port
    )
    assert [e.sql for e in emissions] == ["delete from account where id = ? and version = ?"]
    assert affected == 1


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
    # so its shortfall is the non-retriable stale write. The close lane settles
    # against a coordinate the case names rather than a source a read published,
    # which is why a Locking-mode conflict is expressible here and nowhere else
    # in this lane.
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
    # vocabulary a writeSequence entry does, so the licensing rule that entitles
    # exactly a versioned Non-Temporal update or delete to name an observed
    # version is the same one, and it is refused before any read runs.
    case = _unversioned_conflict_case(
        [
            {"id": 1, "balance": 500.00, "observedVersion": 1},
            {"id": 2, "balance": 500.00, "observedVersion": 1},
        ]
    )
    with pytest.raises(engine.EngineError, match="an unversioned row authors no `observedVersion`"):
        engine.run_conflict_case(case, "postgres", FakeWritePort())


def test_an_unversioned_conflict_target_is_refused_for_want_of_a_participating_read() -> None:
    # An unversioned Non-Temporal target resolves to the Locking strategy under
    # either preference, and Locking licenses a keyed write only through a read
    # of the writing transaction. This lane's source read is standalone — it has
    # to be, because the concurrent writer commits after it — so an unversioned
    # conflict case is inexpressible, whatever state it would assert.
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00")}]
    )
    with pytest.raises(WriteEvidenceError, match="write-evidence-unavailable"):
        engine.run_conflict_case(
            _unversioned_conflict_case([{"id": 1, "balance": 500.00}]), "postgres", port
        )


def test_run_conflict_case_renders_a_gated_zero_row_close_as_a_conflict() -> None:
    _emissions, affected, _table_state, _log, _round_trips = engine.run_conflict_case(
        _load_case("m-temporal-read-010"), "postgres", _ZeroAffectedClosePort()
    )
    assert affected == 0


def _always_implying(
    error_cls: type[WriteEffectError],
) -> Callable[[bool, Concurrency, AcceptedMetamodel, str], type[WriteEffectError]]:
    """An ``_implied_shortfall_error`` stand-in that ignores the case's own
    declared facts — a lane admitting the wrong shortfall class."""

    def implied(
        _observation_requiring: bool,
        _concurrency: Concurrency,
        _model: AcceptedMetamodel,
        _target: str,
    ) -> type[WriteEffectError]:
        return error_cls

    return implied


_ACCOUNT: Final[str] = "parallax.compatibility.Account"


class TestConflictShortfallClassification:
    """The shortfall class a conflict case's declared facts imply, and the lane's
    refusal to absorb any other one.

    Every member of the Write Effect Error family carries the same ``actual``
    count, so a lane catching the whole family would render `then.affectedRows: 0`
    identically whichever class the write raised, and a zero-row case would assert
    nothing about the classification (`m-opt-lock` "Classification follows the
    gate").
    """

    def test_an_optimistic_strategy_implies_the_retriable_conflict(self) -> None:
        from parallax.conformance import models

        assert (
            engine._implied_shortfall_error(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                True, "optimistic", models.load_models()["account"], _ACCOUNT
            )
            is OptimisticLockConflictError
        )

    def test_a_locking_strategy_implies_the_non_retriable_stale_write(self) -> None:
        from parallax.conformance import models

        assert (
            engine._implied_shortfall_error(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                True, "locking", models.load_models()["account"], _ACCOUNT
            )
            is StaleWriteError
        )

    @pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
    def test_an_observation_free_write_implies_a_missing_target_under_either_preference(
        self, concurrency: Concurrency
    ) -> None:
        # A write that observed nothing has no gate to classify by, so its
        # shortfall says only that the addressed rows are not there.
        from parallax.conformance import models

        assert (
            engine._implied_shortfall_error(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                False, concurrency, models.load_models()["account"], _ACCOUNT
            )
            is MissingTargetError
        )

    def test_a_locking_shortfall_admitted_as_a_conflict_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The regression this pins: a lane admitting the retriable conflict where
        # the ungated locking-mode close's shortfall is the stale write. The real
        # failure must NOT be swallowed into the same `affectedRows: 0`
        # observation m-temporal-read-012 asserts.
        monkeypatch.setattr(
            engine, "_implied_shortfall_error", _always_implying(OptimisticLockConflictError)
        )
        with pytest.raises(StaleWriteError):
            engine.run_conflict_case(
                _load_case("m-temporal-read-012"), "postgres", _ZeroAffectedClosePort()
            )

    def test_a_gated_shortfall_admitted_as_a_stale_write_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(engine, "_implied_shortfall_error", _always_implying(StaleWriteError))
        with pytest.raises(OptimisticLockConflictError):
            engine.run_conflict_case(
                _load_case("m-opt-lock-005"), "postgres", _ZeroAffectedPort([_ACCOUNT_ROW_2])
            )


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


class _ScriptedReadPort(FakeWritePort):
    """A port answering each read from an ordered script rather than one constant
    result, so a retry sequence's successive source reads can observe successive
    generations of one row."""

    def __init__(self, results: list[list[Row]]) -> None:
        super().__init__()
        self._results = list(results)

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        self.reads.append((sql, list(binds)))
        return self._results.pop(0) if self._results else []


def test_run_conflict_case_attempts_form_scripts_each_attempt_independently() -> None:
    # Each attempt takes its OWN source read, so the retry observes the generation
    # the concurrent writer left rather than reusing the stale one the first
    # attempt settled against.
    port = _ScriptedReadPort(
        [[_ACCOUNT_ROW_2], [{**_ACCOUNT_ROW_2, "balance": decimal.Decimal("999.00"), "version": 2}]]
    )
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
    shadow = TemporalShadow()
    meta = engine.load_case_metamodel(_load_case("m-txtime-write-002"))
    model = meta
    engine._apply_given_apply(case, POSTGRES, port, shadow)  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert port.writes == []
    # A case that applies nothing leaves the tracker's account of the stored rows
    # whole — including for a key it tracks no milestone of — which is what a keyed
    # temporal write over a document-mapped target depends on.
    assert shadow.accounts_for(
        model, engine.case_entity(model, "parallax.compatibility.Balance"), {"id": 1}
    )


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


def test_scenario_read_step_missing_its_query_is_rejected() -> None:
    bad = _synthetic_write("scenario", {"when": {"scenario": [{"roundTrips": 1}]}})
    with pytest.raises(engine.EngineError, match="objectQuery"):
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
        path=Path("m-predicate-998-synthetic-rejected.yaml"),
        case_id="m-predicate-998",
        shape="rejected",
        tags=("m-predicate", "rejected", "slice-snapshot-1"),
        model="models/animal.yaml",
        document={"model": "models/animal.yaml", "when": when, "then": {"rejectedRule": "x"}},
    )


def test_run_rejected_case_query_dispatch_classifies_the_rule() -> None:
    case = _rejected_case("m-inheritance-040")
    assert engine.run_rejected_case(case) == "narrow-outside-position"


def test_run_rejected_case_query_dispatch_over_a_value_object_model() -> None:
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


def test_run_rejected_case_raises_when_the_query_is_unexpectedly_accepted() -> None:
    valid: dict[str, object] = {"objectQuery": {"target": "Animal", "predicate": {"all": {}}}}
    with pytest.raises(engine.EngineError, match="accepted an Object Query"):
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


def test_run_rejected_case_raises_for_a_malformed_query() -> None:
    malformed_query: dict[str, object] = {
        "objectQuery": {"target": "Animal", "predicate": {"eq": {}}}
    }
    with pytest.raises(engine.EngineError, match="missing required key"):
        engine.run_rejected_case(_synthetic_rejected(malformed_query))


def test_run_rejected_case_raises_for_a_malformed_inline_model() -> None:
    # The family door parses shape only, so a document that is not a descriptor
    # at all is ITS refusal — reported against the case rather than graded as a
    # family rule, because no rule was violated by a model that never parsed.
    malformed_model: dict[str, object] = {"model": {"entities": [{"attributes": []}]}}
    with pytest.raises(engine.EngineError, match="`name` must be a string"):
        engine.run_rejected_case(_synthetic_rejected(malformed_model))


def test_run_rejected_case_raises_for_an_inline_model_the_schema_refuses() -> None:
    # The second door's own refusal, which the first cannot reach: a document
    # whose families are well formed but whose canonical schema they are not.
    # The family validator has no schema phase and returns, so this arrives at
    # `domain_model_from_document` and is a `DescriptorSchemaError` — an engine
    # report, never a graded rule, since a rejected case names a model rule.
    schema_invalid: dict[str, object] = {
        "model": {
            "entities": [
                {
                    "name": "Widget",
                    "table": "widget",
                    "attributes": [
                        {"name": "id", "type": "int64", "primaryKey": True},
                        {"name": "x", "type": "notatype"},
                    ],
                }
            ]
        }
    }
    with pytest.raises(engine.EngineError, match="schema violation"):
        engine.run_rejected_case(_synthetic_rejected(schema_invalid))


def test_run_rejected_case_raises_when_when_carries_none_of_the_three_inputs() -> None:
    with pytest.raises(engine.EngineError, match="EXACTLY ONE"):
        engine.run_rejected_case(_synthetic_rejected({}))


def test_run_rejected_case_raises_when_when_carries_a_query_and_a_model() -> None:
    # The schema `oneOf` cannot protect a caller that reaches the engine without
    # schema validation (a hand-built synthetic case, here) — the engine's own
    # mirror guard must still refuse a multi-input `when`.
    when: dict[str, object] = {"objectQuery": {}, "model": {"entities": []}}
    with pytest.raises(engine.EngineError, match="EXACTLY ONE"):
        engine.run_rejected_case(_synthetic_rejected(when))


def test_run_rejected_case_raises_when_when_carries_a_query_and_a_write() -> None:
    when: dict[str, object] = {"objectQuery": {}, "write": {}}
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
# `run_graph_case` / `run_graphs_case` envelope lane and the scenario          #
# `mutate` action. What a root LOOKS like is the wire materializer's own       #
# contract (`test_wire_reads.py`); what is left here is the envelope.          #
# --------------------------------------------------------------------------- #
class QueueDbPort:
    """A fake `m-db-port` returning one canned response per `execute()` call."""

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
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
    emissions, graph, round_trips, stored_data_issues = engine.run_graph_case(
        _case("m-snapshot-read-001"), "postgres", port
    )
    assert round_trips == 3
    assert len(emissions) == 3
    assert stored_data_issues is None
    assert [item["id"] for item in _rows(graph["Order"][0], "items")] == [12, 11]
    assert _rows(graph["Order"][0], "itemsByShipDate")[0]["shippedOn"] == "2024-02-15"


def test_run_graph_case_unwinds_a_back_reference_finitely() -> None:
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
    _emissions, graph, round_trips, stored_data_issues = engine.run_graph_case(
        _case("m-snapshot-read-011"), "postgres", port
    )
    assert round_trips == 2
    assert stored_data_issues is None
    # The back-reference renders its target ONCE, in full, and terminates: the
    # include tree — not a cycle detector — is what bounds the value, so the
    # position carries the ancestor's own members rather than a primary-key stub.
    back = _rows(graph["Order"][0], "items")[0]["order"]
    assert isinstance(back, Mapping)
    assert back["id"] == 1
    assert back["name"] == "Ada"
    assert "items" not in back


def test_run_graph_case_reports_the_records_a_classified_root_published() -> None:
    # A `then.graph` position whose stored state contradicted the model carries the
    # collapsed node the classification hydrated, and the diagnosis rides the
    # separate `storedDataIssues` observation — one entry per invalid position, in
    # result order, naming the concrete Entity, the member path inside the
    # occurrence, and the affected object's own key.
    port = QueueDbPort(
        [
            [
                {"id": 1, "profile": PresentDocument({"street": "1 Main", "city": None})},
                {"id": 2, "profile": PresentDocument({"city": "Oslo"})},
            ],
            [{"id": 12, "item_id": 2, "profile": PresentDocument({"street": "12 Main"})}],
        ]
    )
    _emissions, graph, _round_trips, stored_data_issues = engine.run_graph_case(
        _load_case("m-storage-layout-027"), "postgres", port
    )
    assert _node(graph["ClassificationTwinItem"], 0)["profile"] == {
        "street": "1 Main",
        "city": None,
    }
    assert _node(graph["ClassificationTwinItem"], 1)["profile"] == {"city": "Oslo"}
    assert stored_data_issues == [
        {
            "ordinal": 1,
            "hydrated": True,
            "issues": [
                {
                    "code": "stored-data-required-member-absent",
                    "entity": "parallax.compatibility.ClassificationTwinItem",
                    "member": "parallax.compatibility.ClassificationTwinItem.profile.street",
                    "objectKey": {
                        "entity": "parallax.compatibility.ClassificationTwinItem",
                        "key": {"id": 2},
                    },
                }
            ],
        }
    ]


def test_run_graph_case_publishes_null_where_nothing_could_be_hydrated() -> None:
    # The other arm of the same observation: a leaf no declared decoding admits
    # leaves the position with no value at all, so the graph carries `null` and
    # `hydrated` is what says the null means "unhydrated" rather than "collapsed".
    port = QueueDbPort(
        [
            [{"id": 1, "profile": PresentDocument({"street": "1 Main", "city": 7})}],
            [],
        ]
    )
    _emissions, graph, _round_trips, stored_data_issues = engine.run_graph_case(
        _load_case("m-storage-layout-027"), "postgres", port
    )
    assert graph["ClassificationTwinItem"] == [None]
    assert stored_data_issues is not None
    (record,) = stored_data_issues
    assert record["hydrated"] is False
    assert [issue["code"] for issue in cast("list[Row]", record["issues"])] == [
        "stored-data-leaf-undecodable"
    ]


def test_a_diagnosis_names_its_member_by_the_path_the_corpus_addresses_one_by() -> None:
    # The three member arms a diagnosis can name, in the one dotted spelling a
    # nested predicate already authors: a top-level Attribute, a Value Object
    # occurrence at any containment depth, and a scalar inside one.
    entity = EntityIdentity("parallax.compatibility", "Customer")
    occurrence = ValueObjectIdentity(entity, ("address", "geo"))
    assert engine._member_path(AttributeIdentity(entity, "name")) == (  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        "parallax.compatibility.Customer.name"
    )
    assert engine._member_path(occurrence) == (  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        "parallax.compatibility.Customer.address.geo"
    )
    assert engine._member_path(ValueObjectAttributeIdentity(occurrence, "country")) == (  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        "parallax.compatibility.Customer.address.geo.country"
    )


def test_run_read_case_refuses_a_row_form_position_the_read_classified() -> None:
    # The row-form observation has no place to carry a record, so the lane names
    # the shape rather than grading a classification as though it were a row.
    port = FakeDbPort([{"id": 4, "name": None}])
    with pytest.raises(engine.EngineError, match="published an InvalidData record"):
        engine.run_read_case(_load_case("m-value-object-007"), "postgres", port)


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
    _emissions, graph, _round_trips, _stored_data_issues = engine.run_graph_case(
        _case("m-descriptor-002"), "postgres", port
    )
    row = _node(graph["MemberColumnDefaults"], 0)
    assert row["mailingAddress"] == {"city": "Oslo"}
    assert "mailing_address" not in row


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


_ATTACH_OWNER = EntityIdentity("catalog", "Owner")
_ATTACH_TARGET = EntityIdentity("catalog", "Target")

# One Entity whose Value Object storage column is spelled exactly like a
# relationship it also carries: the two namespaces must not overwrite each other
# on the wire.
_ATTACH_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_ATTACH_OWNER,
            container=Table("owner"),
            attributes=(key(_ATTACH_OWNER), attribute(_ATTACH_OWNER, "targetId")),
            value_objects=(_rendering_value_object("profile", "details"),),
        ),
        Declaration(
            identity=_ATTACH_TARGET,
            container=Table("target"),
            attributes=(key(_ATTACH_TARGET),),
        ),
    )
)


def _scenario_result(
    *roots: dict[str, object], pin: Pin | None = None, identity: EntityIdentity | None = None
) -> Any:
    return engine._ScenarioStepResult(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        roots=tuple(roots), pin=pin, identity=identity
    )


_ORDERS_MODEL = engine.load_case_metamodel(_case("m-snapshot-read-010"))
_ORDER_IDENTITY = engine.case_entity(_ORDERS_MODEL, "parallax.compatibility.Order").identity


def _edited_copy(step: Mapping[str, object], on: int, source: Any) -> Any:
    return engine._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _case("m-snapshot-read-010"), _ORDERS_MODEL, step, on, source
    )


def _order_view(**members: object) -> Any:
    return _scenario_result(dict(members), identity=_ORDER_IDENTITY)


def test_edited_copy_raises_when_the_target_step_holds_zero_nodes() -> None:
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="expected exactly one"):
        _edited_copy(step, 0, _scenario_result(identity=_ORDER_IDENTITY))


def test_edited_copy_raises_when_the_target_step_holds_many_nodes() -> None:
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    source = _scenario_result(
        {"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}, identity=_ORDER_IDENTITY
    )
    with pytest.raises(engine.EngineError, match="expected exactly one"):
        _edited_copy(step, 0, source)


def test_edited_copy_raises_when_set_is_not_a_mapping() -> None:
    step = {"action": "mutate", "on": 0, "set": "not-a-mapping"}
    with pytest.raises(engine.EngineError, match="`set` is a mapping"):
        _edited_copy(step, 0, _order_view(id=1, name="Ada"))


def test_edited_copy_carries_every_named_member_and_leaves_its_source_alone() -> None:
    # An edit DERIVES: the copy carries the assignment and the node it was
    # derived from still holds what the read materialized, which is the whole
    # difference between an authored edit and an in-place assignment.
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant", "qty": 9}}
    source = _order_view(id=1, name="Ada", qty=5)
    copy = _edited_copy(step, 0, source)
    assert copy.roots[0] == {"id": 1, "name": "Mutant", "qty": 9}
    assert source.roots[0] == {"id": 1, "name": "Ada", "qty": 5}


def test_edited_copy_carries_the_sources_pin_and_identity() -> None:
    # What lets a chain of edits keep answering the pin question the same way,
    # and a later step name the copy exactly as it names the read.
    pin = Pin(tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC), valid_time=None)
    source = _scenario_result({"id": 1, "name": "Ada"}, pin=pin, identity=_ORDER_IDENTITY)
    copy = _edited_copy({"action": "mutate", "on": 0, "set": {"name": "Mutant"}}, 0, source)
    assert (copy.pin, copy.identity) == (pin, _ORDER_IDENTITY)


def test_edited_copy_with_no_set_restates_the_sources_own_state() -> None:
    # The change-free edit (`test_edit.py`'s `_BRANCHES` second branch): legal,
    # and a copy rather than the source itself.
    source = _order_view(id=1, name="Ada")
    copy = _edited_copy({"action": "mutate", "on": 0}, 0, source)
    assert copy.roots[0] == {"id": 1, "name": "Ada"}
    assert copy.roots[0] is not source.roots[0]


def test_edited_copy_refuses_a_set_naming_a_relationship_member() -> None:
    # No edit changes a relationship member: a carried view describes what a read
    # observed, so authoring `items` would state a fetch that never happened.
    step: dict[str, object] = {"action": "mutate", "on": 0, "set": {"items": []}}
    source = _order_view(id=1, name="Ada", items=())
    with pytest.raises(engine.EngineError, match="name relationship members"):
        _edited_copy(step, 0, source)


def test_edited_copy_refuses_the_whole_set_when_one_name_is_unassignable() -> None:
    # The assignable name is authored FIRST, so a per-name copy-then-check would
    # carry `name` past the refusal: the whole `set` is rejected and the source
    # still holds the state the find step materialized.
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant", "nickname": "Nick"}}
    source = _order_view(id=1, name="Ada")
    with pytest.raises(engine.EngineError, match="has no assignable member of"):
        _edited_copy(step, 0, source)
    assert source.roots[0] == {"id": 1, "name": "Ada"}


def test_edited_copy_refuses_an_assignment_to_the_primary_key() -> None:
    # `python.md`'s edit contract: a primary-key target may not be assigned. The
    # engine reaches the SAME verdict the typed `edit(**changes)` does rather
    # than merging whatever the case authored.
    step = {"action": "mutate", "on": 0, "set": {"id": 2}}
    source = _order_view(id=1, name="Ada")
    with pytest.raises(engine.EngineError, match="primary-key fields may not be assigned"):
        _edited_copy(step, 0, source)


def test_edited_copy_refuses_an_ill_typed_assignment() -> None:
    # The other half of the same verdict: a value that does not match the
    # member's declared type is refused at edit time, never carried into a copy
    # a later step names.
    step = {"action": "mutate", "on": 0, "set": {"qty": "five"}}
    source = _order_view(id=1, name="Ada", qty=5)
    with pytest.raises(engine.EngineError, match="does not match the declared type"):
        _edited_copy(step, 0, source)


def test_edited_copy_carries_the_decoded_value_a_member_would_hold() -> None:
    # A case authors wire literals (`10.50` parses as a float-shaped
    # `AuthoredNumber`); the read's own member state holds native carriers, so
    # the copy's does too rather than mixing the two vocabularies.
    step = {"action": "mutate", "on": 0, "set": {"price": AuthoredNumber("12.75")}}
    copy = _edited_copy(step, 0, _order_view(id=1, price=decimal.Decimal("10.50")))
    assert copy.roots[0]["price"] == decimal.Decimal("12.75")
    assert isinstance(copy.roots[0]["price"], decimal.Decimal)


def test_an_edit_chain_carries_the_sources_relationship_arm_at_every_hop() -> None:
    # What `m-snapshot-read-022`'s access cannot ask on this lane, because it
    # names the read: EVERY copy the chain derives answers the SAME materialized
    # children — not equal ones, and not none at all. An implementation that
    # carried views on the first derivation but rebuilt a copy of a copy from its
    # declared members fails here.
    items = ({"id": 11, "sku": "A-100"}, {"id": 12, "sku": "B-200"})
    source = _order_view(id=1, name="Ada", items=items)
    renamed = _edited_copy({"action": "mutate", "on": 0, "set": {"name": "Mutant"}}, 0, source)
    restated = _edited_copy({"action": "mutate", "on": 1}, 1, renamed)
    assert renamed.roots[0]["items"] is items
    assert restated.roots[0]["items"] is items
    assert source.roots[0]["items"] is items


_ANIMAL_CASE = _case("m-inheritance-004")
_ANIMAL_MODEL = engine.load_case_metamodel(_ANIMAL_CASE)
_ANIMAL_IDENTITY = engine.case_entity(_ANIMAL_MODEL, "parallax.compatibility.Animal").identity


def _abstract_read_of_a_dog(**overrides: object) -> Any:
    # What an ABSTRACT-target read publishes: one complete concrete instance —
    # Dog's own `barkVolume` beside the root's members — plus the framework's
    # `familyVariant` provenance key, all under the query's abstract target.
    node: dict[str, object] = {
        "id": 1,
        "name": "Rex",
        "ownerId": 10,
        "licenseId": "L-100",
        "barkVolume": 7,
        "familyVariant": "Dog",
    }
    return _scenario_result(node | overrides, identity=_ANIMAL_IDENTITY)


def _edited_animal(authored: Mapping[str, object], source: Any) -> Any:
    step = {"action": "mutate", "on": 0, "set": dict(authored)}
    return engine._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _ANIMAL_CASE, _ANIMAL_MODEL, step, 0, source
    )


def test_edited_copy_judges_a_subtype_member_against_the_node_it_edits() -> None:
    # The read's target is the ABSTRACT `Animal`, which declares no `barkVolume`
    # at all; the node is a `Dog`, which declares it as an `int32`. Judging
    # against the target would wave the string through, because a name the
    # position does not declare is nobody's assignment to refuse.
    with pytest.raises(engine.EngineError, match="does not match the declared type"):
        _edited_animal({"barkVolume": "loud"}, _abstract_read_of_a_dog())


def test_edited_copy_refuses_an_assignment_to_read_time_provenance() -> None:
    # `familyVariant` is a key the read publishes, not a member anything on the
    # node's ancestry declares, so a gate asking the materialized mapping would
    # accept it and carry a node claiming to be a `Cat`. The gate asks the model.
    with pytest.raises(engine.EngineError, match="Dog has no assignable member of"):
        _edited_animal({"familyVariant": "Cat"}, _abstract_read_of_a_dog())


def test_edited_copy_refuses_a_sibling_branchs_member() -> None:
    # `indoor` is declared on `Cat`, the sibling concrete branch: it is no more
    # assignable on a `Dog` node than a name the family declares nowhere.
    with pytest.raises(engine.EngineError, match="Dog has no assignable member of"):
        _edited_animal({"indoor": True}, _abstract_read_of_a_dog())


def test_edited_copy_carries_the_concrete_identity_its_node_resolves_to() -> None:
    # The accepted half: a member the node's own concrete Entity declares lands,
    # and the copy states the Entity it IS rather than the abstract target that
    # published it — so a chain of edits keeps judging against `Dog`.
    copy = _edited_animal({"barkVolume": 9}, _abstract_read_of_a_dog())
    assert copy.identity == engine.case_entity(_ANIMAL_MODEL, "parallax.compatibility.Dog").identity
    assert copy.roots[0]["barkVolume"] == 9
    assert _edited_animal({"barkVolume": 3}, copy).identity == copy.identity


def test_edited_copy_refuses_a_variant_naming_no_concrete_subtype() -> None:
    # An unresolvable variant is refused rather than fallen back on: judging
    # against the abstract target instead is exactly the hole the resolution
    # closes, so it may not be the failure mode when resolution fails.
    with pytest.raises(engine.EngineError, match="no concrete subtype of Animal"):
        _edited_animal({"name": "Rexy"}, _abstract_read_of_a_dog(familyVariant="Unicorn"))


def test_edited_copy_judges_a_concrete_target_read_against_that_target() -> None:
    # A CONCRETE-target read carries no `familyVariant` at all (`m-case-format`):
    # the caller already knows the variant, so a node states no provenance to
    # resolve and the target it was published under is the Entity it is.
    dog = engine.case_entity(_ANIMAL_MODEL, "parallax.compatibility.Dog").identity
    step = {"action": "mutate", "on": 0, "set": {"barkVolume": 9}}
    source = _scenario_result({"id": 1, "name": "Rex", "barkVolume": 7}, identity=dog)
    copy = engine._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _ANIMAL_CASE, _ANIMAL_MODEL, step, 0, source
    )
    assert (copy.identity, copy.roots[0]["barkVolume"]) == (dog, 9)


_TICKET = EntityIdentity("catalog", "Ticket")

# A STANDALONE Entity declaring an ordinary Attribute spelled `familyVariant`,
# which `m-inheritance` reserves from declared members on an inheritance
# PARTICIPANT alone. A read of one publishes that key holding domain data.
_TICKET_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_TICKET,
            container=Table("ticket"),
            attributes=(key(_TICKET), attribute(_TICKET, "familyVariant", type=STRING)),
        )
    )
)


def _edited_ticket(authored: Mapping[str, object]) -> Any:
    step = {"action": "mutate", "on": 0, "set": dict(authored)}
    source_result = _scenario_result({"id": 1, "familyVariant": "premium"}, identity=_TICKET)
    return engine._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
        _case("m-snapshot-read-010"), _TICKET_MODEL, step, 0, source_result
    )


def test_edited_copy_reads_a_standalone_entitys_family_variant_as_domain_state() -> None:
    # Provenance is what that key means on a family, and nothing more: a
    # standalone Entity may declare a member of its own by that name, and
    # resolving its value as a variant spelling would refuse every edit of such a
    # node — even one touching another member entirely. It stays ordinary domain
    # state here: assignable, judged against its own declared type, and carried
    # by a copy that is still the Entity the read named.
    copy = _edited_ticket({"familyVariant": "standard"})
    assert copy.roots[0] == {"id": 1, "familyVariant": "standard"}
    assert copy.identity == _TICKET
    with pytest.raises(engine.EngineError, match="does not match the declared type"):
        _edited_ticket({"familyVariant": 7})


def test_grade_mutate_step_rejects_an_on_index_naming_no_view() -> None:
    step = {"action": "mutate", "on": 5, "set": {"name": "Mutant"}}
    with pytest.raises(engine.EngineError, match="holds no view to edit"):
        engine._grade_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-010"), _ORDERS_MODEL, step, [_scenario_result({"id": 1})]
        )


def test_grade_mutate_step_publishes_no_copy_when_the_pin_rule_refuses() -> None:
    # A refused mutation derives nothing, so its slot stays empty and a later
    # step naming it is told so rather than handed a copy the verb never made.
    case = _case("m-bitemp-write-016")
    model = engine.load_case_metamodel(case)
    identity = engine.case_entity(model, "parallax.compatibility.Position").identity
    source = _scenario_result(
        {"id": 1, "value": decimal.Decimal("90.00")},
        pin=Pin(tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC), valid_time=None),
        identity=identity,
    )
    step = {
        "action": "mutate",
        "on": 0,
        "set": {"value": 999},
        "expectError": "transaction-time-pin-read-only",
    }
    error_class, result = engine._grade_mutate_step(case, model, step, [source])  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    assert (error_class, result.roots, result.identity) == (
        "transaction-time-pin-read-only",
        (),
        None,
    )


# --------------------------------------------------------------------------- #
# Docker-free error paths (m-conformance-adapter's lane-honest ``EngineError``  #
# wrapping): a compiled/found query that fails inside `m-sql` / `m-navigate`  #
# / `m-temporal-read` is caught and re-raised as one `EngineError`, never a     #
# leaked lower-layer exception type.                                           #
# --------------------------------------------------------------------------- #
def test_compile_read_case_wraps_a_sql_gen_error() -> None:
    case = _synthetic(
        {
            "model": "models/orders.yaml",
            "when": {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.doesNotExist", "value": 1}},
                },
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
                "objectQuery": {
                    "target": "Balance",
                    "predicate": {"all": {}},
                    "temporal": {"valid-time": {"asOf": "latest"}},
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(engine.EngineError, match="undeclared"):
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
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"all": {}},
                    "temporal": {"valid-time": {"history": {}}},
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(engine.EngineError, match="undeclared"):
        engine.run_graphs_case(case, "postgres", QueueDbPort([]))


def test_run_graph_case_refuses_a_case_whose_read_answers_a_milestone_set() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"all": {}},
                    "temporal": {"transaction-time": {"history": {}}},
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(engine.EngineError, match=r"asserts `then\.graphs`"):
        engine.run_graph_case(case, "postgres", QueueDbPort([[]]))


def test_run_graphs_case_refuses_a_case_whose_read_answers_one_graph() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"all": {}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(engine.EngineError, match=r"asserts `then\.graph`"):
        engine.run_graphs_case(case, "postgres", QueueDbPort([[]]))


def test_render_value_recurses_into_a_nested_value_object_document() -> None:
    port = FakeDbPort(
        [
            {
                "id": 1,
                "name": "Ada",
                "address": {"street": "x", "city": "Oslo", "geo": {"country": "NO"}},
            }
        ]
    )
    _emissions, graph, _round_trips, _stored_data_issues = engine.run_graph_case(
        _case("m-value-object-024"), "postgres", port
    )
    rendered = _node(graph["Customer"], 0)
    assert rendered["address"] == {
        "street": "x",
        "city": "Oslo",
        "geo": {"country": "NO"},
        "phones": [],
    }


def test_check_action_step_rejects_a_managed_lifecycle_verb() -> None:
    # `detachCopy` is a managed-object surfacing this lane holds no state for; the
    # two verbs it does grade over a snapshot graph (`mutate`, `access`) pass.
    with pytest.raises(engine.EngineError, match="graded by the API"):
        engine._check_action_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
            _case("m-snapshot-read-010"), {"action": "detachCopy"}
        )
    engine._check_action_step(_case("m-snapshot-read-010"), {"action": "mutate"})  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly
    engine._check_action_step(_case("m-snapshot-read-010"), {"action": "access"})  # pyright: ignore[reportPrivateUsage] - unit test drives the conformance engine's private helper directly


def test_compile_scenario_case_snapshot_lane_requires_an_object_query() -> None:
    when = {
        "scenario": [
            {"action": "mutate", "on": 0, "set": {"x": 1}},
            {"roundTrips": 1},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="needs `objectQuery`"):
        engine.compile_scenario_case(case, "postgres")


def test_compile_scenario_case_snapshot_lane_wraps_a_sql_gen_error() -> None:
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.nope", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="names no attribute"):
        engine.compile_scenario_case(case, "postgres")


def test_run_scenario_case_snapshot_lane_requires_an_object_query() -> None:
    when = {
        "scenario": [
            {"roundTrips": 1},
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="needs `objectQuery`"):
        engine.run_scenario_case(case, "postgres", QueueDbPort([]))


def test_run_scenario_case_snapshot_lane_wraps_an_error_from_the_find_executor() -> None:
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.nope", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="names no attribute"):
        engine.run_scenario_case(case, "postgres", QueueDbPort([]))


_ORDER_ROW: dict[str, object] = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": decimal.Decimal("10.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 5),
}


def test_run_scenario_case_snapshot_lane_mutates_in_memory_with_no_writeback() -> None:
    port = FakeWritePort(find_rows=[dict(_ORDER_ROW)])
    run = engine.run_scenario_case(_case("m-snapshot-read-010"), "postgres", port)
    assert run.round_trips == 2
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/2/objectQuery",
    ]
    assert len(port.reads) == 2
    assert len(port.writes) == 0
    assert run.errors == []  # an unpinned mutate is accepted: no error observation


def test_run_scenario_case_snapshot_lane_refuses_a_set_the_read_cannot_assign() -> None:
    # The end-to-end half of the assignment: the `set` resolves against the
    # members the retained node's own Entity declares, so a name it declares none
    # of is refused at the verb rather than silently dropped.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"nickname": "Mutant"}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = FakeWritePort(find_rows=[dict(_ORDER_ROW)])
    with pytest.raises(engine.EngineError, match="Order has no assignable member of"):
        engine.run_scenario_case(case, "postgres", port)
    assert len(port.writes) == 0


def test_run_scenario_case_snapshot_lane_applies_out_of_band_statements() -> None:
    # `m-case-format` admits `given.apply` on a scenario without excluding the
    # action-bearing shape, so this lane owes the same setup every other executor
    # does: applied on the caller's own port before the first step, so each find
    # observes the state those statements left rather than the state they replaced.
    case = _case("m-snapshot-read-010")
    with_apply = dataclasses.replace(
        case,
        document={
            **case.document,
            "given": {"apply": [{"sql": "update orders set qty = ?", "binds": [9]}]},
        },
    )
    port = FakeWritePort(find_rows=[dict(_ORDER_ROW)])
    engine.run_scenario_case(with_apply, "postgres", port)
    assert port.writes == [("update orders set qty = %s", [9])]


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
    run = engine.run_scenario_case(_case("m-bitemp-write-016"), "postgres", port)
    assert run.round_trips == 1
    assert [e.case_pointer for e in run.emissions] == ["/scenario/0/objectQuery"]
    assert run.errors == [{"at": "/scenario/1", "errorClass": "transaction-time-pin-read-only"}]


def test_run_scenario_case_accepts_a_finite_valid_time_pin_mutate() -> None:
    # The writable half of the finite-pin contrast: a finite Valid-Time pin
    # (Transaction Time defaulted Latest) passes the SAME validator, so the
    # mutate applies in-memory and no error observation is reported.
    row = dict(_POSITION_R1_ROW, val=decimal.Decimal("100.00"))
    port = FakeDbPort([row])
    run = engine.run_scenario_case(_case("m-bitemp-write-015"), "postgres", port)
    assert run.round_trips == 1
    assert run.errors == []


def test_run_scenario_case_reports_an_undeclared_pin_refusal_loudly() -> None:
    # The mutate verb raised, but the step declares no expectError — a corpus/
    # implementation mismatch this lane names loudly, never a silently dropped
    # error observation.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Position",
                    "predicate": {"eq": {"attr": "Position.id", "value": 1}},
                    "temporal": {
                        "transaction-time": {"asOf": "2024-02-01T00:00:00+00:00"},
                        "valid-time": {"asOf": "latest"},
                    },
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
    # index the earlier steps' own recorded state), before any copy is derived.
    # One guard answers every way `on` can fail to name a step holding a view —
    # out of range, absent, or naming a write step, which holds none.
    when = {"scenario": [{"action": "mutate", "on": 5, "set": {"name": "Mutant"}}]}
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="holds no view to edit"):
        engine.run_scenario_case(case, "postgres", FakeDbPort([]))


def test_run_scenario_case_reports_an_unraised_expect_error_loudly() -> None:
    # The step declares expectError but the mutation was accepted (the find
    # carries no finite Transaction-Time pin) — the same loud mismatch, the
    # other direction.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                }
            },
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

    model = _models.load_models()[model_name]
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


# --------------------------------------------------------------------------- #
# The write lanes' own verb dispatch, driven database-free against the fake     #
# port. Every keyed and predicate mutation the corpus authors reaches its own   #
# `tx.wire` verb, and the value each write is addressed by is resolved from     #
# what this unit's own reads published — the two questions this engine answers  #
# for itself, since production only ever sees the verb call it makes.           #
# --------------------------------------------------------------------------- #


def test_a_unit_reads_each_entity_it_writes_once_however_many_entries_address_it() -> None:
    # m-unit-work-026 updates then deletes ONE OrderItem in one step, so the two
    # entries share a single membership read. Reading per entry would put the
    # update on the wire before the delete could supersede it.
    port = FakeWritePort(
        find_rows=[{"id": 21, "order_id": 2, "sku": "A-300", "quantity": 4, "shipped_on": None}]
    )
    run = engine.run_scenario_case(_case("m-unit-work-026"), "postgres", port)
    assert run.round_trips == 3  # the step's own read + its one DELETE + the dependent find
    assert next(sql for sql, _binds in port.reads) == (
        "select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on"
        " from order_item t0 where t0.id in (%s) for share of t0"
    )
    assert [sql for sql, _binds in port.writes] == ["delete from order_item where id = %s"]


def test_a_temporal_terminate_entry_reaches_its_own_wire_verb() -> None:
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    _emissions, _table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-txtime-write-003"), "postgres", port
    )
    assert round_trips == 3  # insert, then the terminate entry's own read + its close
    assert port.writes[-1][0].startswith("update balance set out_z")


def test_a_bounded_bitemporal_terminate_entry_reaches_its_own_wire_verb() -> None:
    port = FakeWritePort(
        find_rows=[
            _position_row(
                1, "100.00", from_z="2024-01-01T00:00:00+00:00", in_z="2024-01-01T00:00:00+00:00"
            )
        ]
    )
    _emissions, _table_state, round_trips = engine.run_write_sequence_case(
        _load_case("m-bitemp-write-002"), "postgres", port
    )
    assert round_trips == 5  # four statements plus the terminateUntil entry's own read
    assert port.writes[1][0].startswith("update position set out_z")


@pytest.mark.parametrize(
    "case_id",
    [
        "m-bitemp-write-010",
        "m-bitemp-write-011",
        "m-bitemp-write-012",
        "m-bitemp-write-013",
    ],
)
def test_every_materializing_predicate_mutation_reaches_its_own_wire_verb(case_id: str) -> None:
    # The four bitemporal predicate shapes — plain update, plain terminate, and
    # the bounded pair — each dispatch to the `tx.wire.*_where` verb their own
    # mutation names. The canned row is what the pair's resolving find publishes.
    port = FakeWritePort(
        find_rows=[
            _position_row(
                1, "200.00", from_z="2024-06-01T00:00:00+00:00", in_z="2024-04-01T00:00:00+00:00"
            )
        ]
    )
    run = engine.run_scenario_case(_load_case(case_id), "postgres", port)
    assert run.errors == []
    assert any(e.sql.startswith("update position set out_z") for e in run.emissions)


def test_a_write_settles_against_a_row_its_own_unit_opened() -> None:
    # Read-your-own-writes inside ONE step: no read could return the inserted row,
    # so the node `tx.wire.insert` answered is what the update is addressed by.
    case = _synthetic_ledger_scenario(
        [
            {
                "write": [
                    {
                        "mutation": "insert",
                        "entity": "parallax.compatibility.Ledger",
                        "rows": [{"id": 9, "acctNum": "D", "value": decimal.Decimal("100.00")}],
                        "at": "2025-01-01T00:00:00+00:00",
                    },
                    {
                        "mutation": "update",
                        "entity": "parallax.compatibility.Ledger",
                        "rows": [{"id": 9, "value": decimal.Decimal("150.00")}],
                        "at": "2025-01-01T00:00:00+00:00",
                    },
                ],
                "roundTrips": 1,
            }
        ]
    )
    port = FakeWritePort()
    engine.run_scenario_case(case, "postgres", port)
    # The pair coalesces in place: one INSERT carrying the final value, no read.
    assert port.reads == []
    assert [sql for sql, _binds in port.writes] == [
        "insert into ledger(led_id, acct_num, val, in_z, out_z) values (%s, %s, %s, %s, %s)"
    ]


def test_a_grouped_write_addressing_a_key_no_read_published_is_refused() -> None:
    # The group's find answered nothing, so the write it precedes is addressed by
    # no value at all — refused where the diagnosis can name the key rather than
    # issued as a blind statement.
    case = _synthetic_ledger_scenario(
        [
            {
                "uow": "g",
                "objectQuery": {
                    "target": "parallax.compatibility.Ledger",
                    "predicate": {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
                "roundTrips": 1,
            },
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00", uow="g"),
        ]
    )
    with pytest.raises(engine.EngineError, match="which no read of its own choreography unit"):
        engine.run_scenario_case(case, "postgres", FakeWritePort())


def test_a_named_find_publishing_no_row_of_a_writes_key_settles_nothing() -> None:
    # The row states its own `observedVersion`, so the entry needs no evidence
    # from the named find and reaches the ADDRESSING question with a reference
    # that resolved to no value. A write addressed by nothing is an authoring
    # defect, refused where the diagnosis can name the step.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "uow": "g",
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 1}},
                        },
                        "roundTrips": 1,
                    },
                    {
                        "uow": "g",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 1, "balance": 5.00, "observedVersion": 1}],
                            }
                        ],
                        "on": 0,
                        "roundTrips": 1,
                    },
                ]
            }
        },
    )
    with pytest.raises(engine.EngineError, match="published 0 rows"):
        engine.run_scenario_case(case, "postgres", FakeWritePort())


def test_a_transaction_time_past_reading_is_skipped_as_a_write_source() -> None:
    # A group may publish several milestones of one key. Only the current one is
    # writable — the Transaction-Time past records what the system knew — so the
    # unreferenced scan steps over the pinned reading rather than reaching for the
    # refusal the verb would raise.
    case = _synthetic_ledger_scenario(
        [
            {
                "uow": "g",
                "objectQuery": {
                    "target": "parallax.compatibility.Ledger",
                    "predicate": {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
                "roundTrips": 1,
            },
            {
                "uow": "g",
                "objectQuery": {
                    "target": "parallax.compatibility.Ledger",
                    "predicate": {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {
                        "transaction-time": {"asOf": "2024-03-01T00:00:00+00:00"},
                    },
                },
                "roundTrips": 1,
            },
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00", uow="g"),
        ]
    )
    port = FakeWritePort(find_rows=[_ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")])
    engine.run_scenario_case(case, "postgres", port)
    assert next(sql for sql, _binds in port.writes).startswith("update ledger set out_z")


def _synthetic_scenario(
    model: str, case_id: str, steps: list[dict[str, object]]
) -> case_format.Case:
    from pathlib import Path

    return case_format.Case(
        path=Path(f"{case_id}-synthetic.yaml"),
        case_id=case_id,
        shape="scenario",
        tags=(case_id.rsplit("-", 1)[0], "slice-snapshot-1"),
        model=model,
        document={"model": model, "shape": "scenario", "when": {"scenario": steps}},
    )


def test_one_entity_spelled_two_ways_owes_one_membership_read() -> None:
    # A bare local name and its canonical form name ONE Entity, so a unit writing
    # both spellings reads that Entity once — the same rule the object identity
    # itself resolves by. Counting the authored string would issue two reads and
    # put the first write on the wire before the second could be buffered.
    port = FakeWritePort(
        find_rows=[
            {"id": 21, "order_id": 2, "sku": "A-300", "quantity": 4, "shipped_on": None},
            {"id": 22, "order_id": 2, "sku": "A-400", "quantity": 1, "shipped_on": None},
        ]
    )
    case = _synthetic_scenario(
        "models/orders.yaml",
        "m-unit-work-997",
        [
            {
                "write": [
                    {
                        "mutation": "update",
                        "entity": "OrderItem",
                        "rows": [{"id": 21, "quantity": 9}],
                    },
                    {
                        "mutation": "delete",
                        "entity": "parallax.compatibility.OrderItem",
                        "rows": [{"id": 22}],
                    },
                ],
                "roundTrips": 3,
            }
        ],
    )
    engine.run_scenario_case(case, "postgres", port)
    assert len(port.reads) == 1
    assert port.reads[0][0].endswith("where t0.id in (%s, %s) for share of t0")


def _registry_advance(sequence: str) -> dict[str, object]:
    return {
        "mutation": "update",
        "entity": "parallax.compatibility.PkSequence",
        "rows": [{"name": sequence, "nextVal": {"increment": 1}}],
    }


def test_a_unit_mixing_a_framework_marker_with_a_public_verb_write_is_refused() -> None:
    # A pk-gen registry advance has no verb to be stated through and an ordinary
    # insert has nothing else, so a unit holding both would put half its DML
    # through the public surface and half around it. Refused rather than routed
    # by whichever entry was looked at first.
    case = _synthetic_scenario(
        "models/pk-sequence.yaml",
        "m-pk-gen-999",
        [
            {
                "write": [
                    _registry_advance("badge_seq"),
                    {
                        "mutation": "insert",
                        "entity": "parallax.compatibility.Badge",
                        "rows": [{"id": 1, "holder": "Bo"}],
                    },
                ],
                "roundTrips": 2,
            }
        ],
    )
    with pytest.raises(engine.EngineError, match="never both"):
        engine.run_scenario_case(case, "postgres", FakeWritePort())


def test_a_unit_holding_two_framework_markers_is_refused() -> None:
    # Two registry advances are two of the framework's own units, and a marker
    # entry is the buffer's only entry — so a buffer holding both is a form no
    # case may author even though nothing in it is caller-authored. The mixed
    # refusal cannot see this shape: every entry is the framework's.
    case = _synthetic_scenario(
        "models/pk-sequence.yaml",
        "m-pk-gen-996",
        [
            {
                "write": [_registry_advance("badge_seq"), _registry_advance("ticket_seq")],
                "roundTrips": 2,
            }
        ],
    )
    with pytest.raises(engine.EngineError, match="buffer's only entry"):
        engine.run_scenario_case(case, "postgres", FakeWritePort())


def _pk_sequence_advance(**step: object) -> dict[str, object]:
    return {"write": [_registry_advance("badge_seq")], "roundTrips": 1, **step}


def test_an_aborted_framework_write_step_executes_its_dml_and_rolls_back() -> None:
    # A registry advance runs through the planner rather than a verb, but it is
    # still a whole choreography unit and answers to the same abort contract: the
    # statement reaches the wire and counts its round trip, and the provider then
    # rolls it back. Committing it would leave a `rollback: true` step's DML
    # durable, which is the one thing the step declares it is not.
    port = FakeWritePort()
    run = engine.run_scenario_case(
        _synthetic_scenario(
            "models/pk-sequence.yaml", "m-pk-gen-998", [_pk_sequence_advance(rollback=True)]
        ),
        "postgres",
        port,
    )
    assert run.round_trips == 1
    assert len(port.writes) == 1
    assert port.rollbacks == 1 and port.commits == 0


def test_a_framework_write_step_inside_a_uow_group_is_refused() -> None:
    # A group's held unit of work buffers each entry through the public verb its
    # mutation names, and no verb accepts a DB-computed write marker. Refused by
    # name here rather than left to the verb, whose value-type diagnosis would
    # describe the marker as a malformed value instead of a misplaced unit.
    case = _synthetic_scenario(
        "models/pk-sequence.yaml", "m-pk-gen-997", [_pk_sequence_advance(uow="g")]
    )
    with pytest.raises(engine.EngineError, match="choreography unit of its own"):
        engine.run_scenario_case(case, "postgres", FakeWritePort())


def test_a_write_settles_against_a_hydratable_invalid_published_root() -> None:
    # The stored `geo` is a scalar where a `one` occurrence is declared, so the
    # read classifies the row while collapsing the occurrence to null — a
    # hydratable violation, whose collapse left every member value legal. The
    # node inside that record is an ordinary observed source: the group's write
    # settles against it exactly as it would against a conforming row, while the
    # record itself is never what the verb is handed.
    port = FakeWritePort(
        find_rows=[
            {
                "id": 6,
                "name": "Rin",
                "address": {"street": "6 Kastanien Allee", "city": "Berlin", "geo": "unknown"},
            }
        ]
    )
    case = _synthetic_scenario(
        "models/customer.yaml",
        "m-value-object-999",
        [
            {
                "uow": "g",
                "objectQuery": {
                    "target": "parallax.compatibility.Customer",
                    "predicate": {"eq": {"attr": "parallax.compatibility.Customer.id", "value": 6}},
                },
                "roundTrips": 1,
            },
            {
                "uow": "g",
                "write": [
                    {
                        "mutation": "update",
                        "entity": "parallax.compatibility.Customer",
                        "rows": [{"id": 6, "name": "Rin II"}],
                    }
                ],
                "roundTrips": 1,
            },
        ],
    )
    engine.run_scenario_case(case, "postgres", port)
    assert [sql for sql, _binds in port.writes] == ["update customer set name = %s where id = %s"]


# --------------------------------------------------------------------------- #
# The scenario `expectGraph` grading (m-conformance-adapter `stepGraphs`): an   #
# `access` step over a relationship an earlier find step's own Include Paths    #
# materialized reads its contents off the RETAINED view — nothing at the port,  #
# which is what makes the observation about survival rather than about the      #
# database (m-snapshot-read *Closed world*, composition).                       #
# --------------------------------------------------------------------------- #
_ORDER_1_ITEM_ROWS: list[dict[str, object]] = [
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": dt.date(2024, 2, 15)},
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
]


def _include_scenario_port() -> QueueDbPort:
    return QueueDbPort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])


def test_run_scenario_case_reports_an_access_step_graph_from_the_retained_view() -> None:
    run = engine.run_scenario_case(
        _case("m-snapshot-read-016"), "postgres", _include_scenario_port()
    )
    # The find's two levels are the only calls; the mutate and the access cost none.
    assert run.round_trips == 2
    assert run.errors == []
    assert [entry["at"] for entry in run.step_graphs] == ["/scenario/2"]
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert sorted(node["id"] for node in graph["OrderItem"]) == [11, 12]  # pyright: ignore[reportArgumentType]


def test_run_scenario_case_lets_an_edit_chain_name_the_copy_before_it() -> None:
    # The chain the corpus authors (`m-snapshot-read-022`) in its DB-free form: a
    # second `mutate` names the FIRST one's copy rather than the read, which
    # resolves only because an accepted edit publishes what it derived. Each hop
    # carries its predecessor's assignment, and the source the chain hangs off
    # still holds the read's own state and the SAME loaded items.
    when: dict[str, object] = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    "includes": [{"segments": [{"rel": "Order.items"}]}],
                }
            },
            {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
            {"action": "mutate", "on": 1},
            {"action": "access", "on": 0, "path": "items", "expectGraph": {"OrderItem": []}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    run = engine.run_scenario_case(case, "postgres", _include_scenario_port())
    assert run.round_trips == 2  # the find's two levels; no hop of the chain costs one
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert sorted(node["id"] for node in graph["OrderItem"]) == [11, 12]  # pyright: ignore[reportArgumentType]


def _orders_access_scenario(access: dict[str, object], *, includes: bool) -> case_format.Case:
    query: dict[str, object] = {
        "target": "Order",
        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
    }
    if includes:
        query["includes"] = [{"segments": [{"rel": "Order.items"}]}]
    when = {"scenario": [{"objectQuery": query}, access]}
    return _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})


def test_run_scenario_case_access_without_expect_graph_reports_no_step_graph() -> None:
    # The observation is the case's own oracle answered: a step asserting no
    # contents reports none, exactly as a step raising no error reports none.
    case = _orders_access_scenario({"action": "access", "on": 0, "path": "items"}, includes=True)
    run = engine.run_scenario_case(case, "postgres", _include_scenario_port())
    assert run.step_graphs == []


def test_run_scenario_case_access_step_graph_rejects_an_on_naming_no_view() -> None:
    case = _orders_access_scenario(
        {"action": "access", "on": 5, "path": "items", "expectGraph": {"OrderItem": []}},
        includes=True,
    )
    with pytest.raises(engine.EngineError, match="holds no view to navigate"):
        engine.run_scenario_case(case, "postgres", _include_scenario_port())


def test_run_scenario_case_access_step_graph_refuses_an_on_naming_a_derived_copy() -> None:
    # An accepted `mutate` publishes a copy so a LATER EDIT can name it, and a
    # copy does carry its source's loaded arms — but it materialized nothing, and
    # `m-case-format` has an access stating contents name the read that did. The
    # reference harness holds no copy at all and refuses this shape, so accepting
    # it here would make one authored `expectGraph` grade in one lane and be
    # refused in the other.
    when: dict[str, object] = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    "includes": [{"segments": [{"rel": "Order.items"}]}],
                }
            },
            {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
            {"action": "access", "on": 1, "path": "items", "expectGraph": {"OrderItem": []}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(engine.EngineError, match="derived its view rather than materializing it"):
        engine.run_scenario_case(case, "postgres", _include_scenario_port())


def test_run_scenario_case_access_step_graph_refuses_a_multi_source_on() -> None:
    # The `on` ARRAY form spans sources at different lowered coordinates, so no one
    # view holds contents gathered across them: a step stating contents names the
    # single read that materialized them, and the set is refused rather than read
    # as its first element.
    case = _orders_access_scenario(
        {"action": "access", "on": [0], "path": "items", "expectGraph": {"OrderItem": []}},
        includes=True,
    )
    with pytest.raises(engine.EngineError, match="names ONE materializing read"):
        engine.run_scenario_case(case, "postgres", _include_scenario_port())


def test_run_scenario_case_access_step_graph_needs_a_navigated_path() -> None:
    case = _orders_access_scenario(
        {"action": "access", "on": 0, "expectGraph": {"OrderItem": []}}, includes=True
    )
    with pytest.raises(engine.EngineError, match="needs a `path`"):
        engine.run_scenario_case(case, "postgres", _include_scenario_port())


def test_run_scenario_case_access_step_graph_refuses_an_unincluded_relationship() -> None:
    # `items` is a real relationship the find never included, so the view carries
    # no loaded arm for it — the unloaded state itself, which an access asserting
    # contents cannot be authored over.
    case = _orders_access_scenario(
        {"action": "access", "on": 0, "path": "items", "expectGraph": {"OrderItem": []}},
        includes=False,
    )
    with pytest.raises(engine.EngineError, match="carries no loaded 'items'"):
        engine.run_scenario_case(case, "postgres", QueueDbPort([[dict(_ORDER_ROW)]]))


def test_run_scenario_case_access_step_graph_refuses_an_undeclared_relationship() -> None:
    case = _orders_access_scenario(
        {"action": "access", "on": 0, "path": "nope", "expectGraph": {"OrderItem": []}},
        includes=True,
    )
    with pytest.raises(engine.EngineError, match="declares no relationship 'nope'"):
        engine.run_scenario_case(case, "postgres", _include_scenario_port())


def test_run_scenario_case_access_step_graph_walks_a_to_one_arm() -> None:
    # The to-one arm: the loaded view carries a single nested node rather than a
    # sequence, so the traversal appends instead of extending.
    query = {
        "target": "OrderItem",
        "predicate": {"eq": {"attr": "OrderItem.id", "value": 11}},
        "includes": [{"segments": [{"rel": "OrderItem.order"}]}],
    }
    when = {
        "scenario": [
            {"objectQuery": query},
            {
                "action": "access",
                "on": 0,
                "path": "order",
                "expectGraph": {"Order": [{"id": 1}]},
            },
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = QueueDbPort([[dict(_ORDER_1_ITEM_ROWS[1])], [dict(_ORDER_ROW)]])

    run = engine.run_scenario_case(case, "postgres", port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert [node["id"] for node in graph["Order"]] == [1]


# `OrderStatus.orderItemId` is nullable, so one status belongs to a line item and
# the other to the order alone — the loaded-NULL to-one branch a deeper hop must
# tell apart from an unloaded view.
_STATUS_ON_ITEM: dict[str, object] = {
    "id": 201,
    "order_id": 1,
    "order_item_id": 11,
    "code": "PICKED",
}
_STATUS_ON_ORDER_ALONE: dict[str, object] = {
    "id": 204,
    "order_id": 1,
    "order_item_id": None,
    "code": "OPEN",
}
_ITEM_11_STATUS_ROWS: list[dict[str, object]] = [
    {"id": 202, "order_id": 1, "order_item_id": 11, "code": "PACKED"},
    dict(_STATUS_ON_ITEM),
]


def _status_root_access(includes: list[dict[str, object]], access: dict[str, object]):
    query = {
        "target": "OrderStatus",
        "predicate": {"eq": {"attr": "OrderStatus.orderId", "value": 1}},
        "includes": includes,
    }
    when = {"scenario": [{"objectQuery": query}, access]}
    return _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})


def test_run_scenario_case_access_step_graph_drops_a_null_branch_before_a_deeper_hop() -> None:
    # A loaded-null to-one branch is not an unloaded view: its own deeper level saw
    # an EMPTY parent set, so it contributes no terminal node to a path that fans
    # out. Carrying the null into the next hop would report the whole access as an
    # access over a relationship the read never included.
    case = _status_root_access(
        [{"segments": [{"rel": "OrderStatus.orderItem"}, {"rel": "OrderItem.statuses"}]}],
        {
            "action": "access",
            "on": 0,
            "path": "orderItem.statuses",
            "expectGraph": {"OrderStatus": [{"id": 202}, {"id": 201}]},
        },
    )
    port = QueueDbPort(
        [
            [dict(_STATUS_ON_ITEM), dict(_STATUS_ON_ORDER_ALONE)],
            [dict(_ORDER_1_ITEM_ROWS[1])],
            [dict(row) for row in _ITEM_11_STATUS_ROWS],
        ]
    )

    run = engine.run_scenario_case(case, "postgres", port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert [node["id"] for node in graph["OrderStatus"]] == [202, 201]


def test_run_scenario_case_access_step_graph_omits_a_terminal_null_after_a_fan_out() -> None:
    # The other side of the same rule at the LAST hop: a fanned-out path answers
    # its non-null terminals, so the status belonging to no line item contributes
    # nothing rather than a null node beside the real one.
    query = {
        "target": "Order",
        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
        "includes": [{"segments": [{"rel": "Order.statuses"}, {"rel": "OrderStatus.orderItem"}]}],
    }
    when = {
        "scenario": [
            {"objectQuery": query},
            {
                "action": "access",
                "on": 0,
                "path": "statuses.orderItem",
                "expectGraph": {"OrderItem": [{"id": 11}]},
            },
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = QueueDbPort(
        [
            [dict(_ORDER_ROW)],
            [dict(_STATUS_ON_ITEM), dict(_STATUS_ON_ORDER_ALONE)],
            [dict(_ORDER_1_ITEM_ROWS[1])],
        ]
    )

    run = engine.run_scenario_case(case, "postgres", port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert [node["id"] for node in graph["OrderItem"]] == [11]


class _QueueWritePort(QueueDbPort):
    """A queue-backed read port that also takes DML.

    The shape a snapshot scenario needs once a `write:` step sits between the
    find that materializes a view and the access that states its contents: the
    reads are still answered in order, and the writes are recorded rather than
    refused.
    """

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        super().__init__(responses)
        self.writes: list[tuple[str, list[object]]] = []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, list(binds)))
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(self)


def _write_between_find_and_access(write: object) -> case_format.Case:
    query = {
        "target": "Order",
        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
        "includes": [{"segments": [{"rel": "Order.items"}]}],
    }
    when = {
        "scenario": [
            {"objectQuery": query},
            {"write": write, "roundTrips": 2},
            {
                "action": "access",
                "on": 0,
                "path": "items",
                "expectGraph": {"OrderItem": [{"id": 12}, {"id": 11}]},
            },
        ]
    }
    return _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})


_ORDER_NAME_UPDATE: list[dict[str, object]] = [
    {
        "mutation": "update",
        "entity": "parallax.compatibility.Order",
        "rows": [{"id": 1, "name": "Rewritten"}],
    }
]


def _ledger_write_after_find_and_mutate(write: object) -> case_format.Case:
    """A snapshot-lane scenario over the Transaction-Time-Only Ledger: the find
    materializes the one CURRENT milestone of id 2 (the fixture key holding
    exactly one, so a write naming no observed edge resolves unambiguously), a
    `mutate` puts the scenario on this lane, and the write step is whatever the
    caller states."""
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "parallax.compatibility.Ledger",
                    "predicate": {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"acctNum": "Z"}},
            {"write": write, "roundTrips": 2},
        ]
    }
    return _synthetic_write(
        "scenario",
        {
            "model": "models/ledger.yaml",
            "when": {"uow": {"concurrency": "optimistic"}, **when},
        },
    )


_LEDGER_2_ROW: dict[str, object] = {
    "led_id": 2,
    "acct_num": "B",
    "val": decimal.Decimal("200.00"),
    "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    "out_z": INFINITY,
}

_LEDGER_VALUE_UPDATE: list[dict[str, object]] = [
    {
        "mutation": "update",
        "entity": "parallax.compatibility.Ledger",
        "rows": [{"id": 2, "value": decimal.Decimal("300.00")}],
        "at": "2024-05-01T00:00:00+00:00",
    }
]


def test_run_scenario_case_write_step_commits_and_leaves_the_retained_view_standing() -> None:
    # The composition the closed-world clause is about: the write is its own unit
    # of work — a resolving read and then its DML — and the view the find
    # materialized stands across it, so the access still answers what THAT read
    # fetched with nothing at the port of its own.
    port = _QueueWritePort(
        [
            [dict(_ORDER_ROW)],
            [dict(row) for row in _ORDER_1_ITEM_ROWS],
            [dict(_ORDER_ROW)],
        ]
    )

    run = engine.run_scenario_case(
        _write_between_find_and_access(_ORDER_NAME_UPDATE), "postgres", port
    )

    assert [emission.case_pointer for emission in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/0/objectQuery",
        "/scenario/1/write",
    ]
    assert [sql for sql, _binds in port.writes] == ["update orders set name = %s where id = %s"]
    assert run.round_trips == 4  # the find's two levels, the write's resolve and its DML
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert sorted(node["id"] for node in graph["OrderItem"]) == [11, 12]  # pyright: ignore[reportArgumentType]


def test_run_scenario_case_refuses_a_non_keyed_write_step_on_the_snapshot_lane() -> None:
    # A legacy string label states no instruction at all, so there is nothing to
    # lower as the keyed buffer this lane executes and no question about the
    # lane's own shape behind the refusal — which is what keeps it apart from the
    # two predicate forms below, each refused for a reason of its own.
    port = _QueueWritePort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])
    with pytest.raises(engine.EngineError, match="BUFFERED KEYED instruction list"):
        engine.run_scenario_case(_write_between_find_and_access("insert"), "postgres", port)
    assert port.writes == []


def test_run_scenario_case_names_the_case_when_a_snapshot_lane_write_will_not_lower() -> None:
    # A write step this lane cannot lower fails as a case-named EngineError rather
    # than as a raw planner exception crossing the conformance seam — the same
    # posture the unit-of-work lane takes for its own ungrouped write step.
    mis_authored = [
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Order",
            "rows": [{"id": 1, "nope": 3}],
        }
    ]
    port = _QueueWritePort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])
    with pytest.raises(engine.EngineError, match="undeclared member"):
        engine.run_scenario_case(_write_between_find_and_access(mis_authored), "postgres", port)
    assert port.writes == []


def test_compile_scenario_case_lowers_a_snapshot_lane_write_step() -> None:
    # The compile peer of the run lane above: a scenario carrying an action step
    # compiles through the snapshot path, whose find is instance-form and unlocked
    # and whose write step is lowered by the SAME planner the unit-of-work lane's
    # ungrouped write step uses.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
            {"write": _ORDER_NAME_UPDATE, "roundTrips": 2},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})

    emissions, round_trips = engine.compile_scenario_case(case, "postgres")

    assert [emission.case_pointer for emission in emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/2/write",
    ]
    assert emissions[1].sql == "update orders set name = ? where id = ?"
    assert round_trips == 2


def test_run_scenario_case_refuses_a_materializing_predicate_write_on_the_snapshot_lane() -> None:
    # A predicate write over a TEMPORAL target materializes: it resolves through
    # the find before it. A find on this lane materializes the view a later access
    # states, so the two step roles genuinely conflict and the refusal says so —
    # never the readless diagnosis below.
    value = "parallax.compatibility.Ledger.value"
    write = {
        "mutation": "update",
        "target": {
            "entity": "parallax.compatibility.Ledger",
            "predicate": {"lessThan": {"attr": value, "value": 500.00}},
        },
        "assignments": [{"attr": value, "value": 5.00}],
        "at": "2024-05-01T00:00:00+00:00",
    }
    port = _QueueWritePort([[dict(_LEDGER_2_ROW)]])
    with pytest.raises(engine.EngineError, match="MATERIALIZING predicate write"):
        engine.run_scenario_case(_ledger_write_after_find_and_mutate(write), "postgres", port)
    assert port.writes == []


def test_run_scenario_case_refuses_a_readless_predicate_write_on_the_snapshot_lane() -> None:
    # An UNVERSIONED, non-temporal target owes no resolving read, so nothing about
    # the shape conflicts with this lane: it is refused as unwired, which is a
    # different fact about a different form than the materializing refusal above.
    write = {
        "mutation": "delete",
        "target": {
            "entity": "parallax.compatibility.OrderItem",
            "predicate": {
                "lessThan": {"attr": "parallax.compatibility.OrderItem.quantity", "value": 5}
            },
        },
    }
    port = _QueueWritePort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])
    with pytest.raises(engine.EngineError, match="READLESS predicate write"):
        engine.run_scenario_case(_write_between_find_and_access(write), "postgres", port)
    assert port.writes == []


def test_snapshot_lane_compile_and_run_reach_the_same_temporal_dml() -> None:
    # Compile seeds the same fixture milestones the run lane does, so a temporal
    # close on this lane resolves the milestone persisted history holds instead of
    # refusing for want of an observation. The two lanes must reach the SAME DML
    # for the same case, which is the whole reason this lane has a compile path —
    # so the run's own emissions ARE the compile oracle here, not a transcription
    # of one.
    case = _ledger_write_after_find_and_mutate(_LEDGER_VALUE_UPDATE)
    # The find, then the resolving read the keyed write's own unit of work owes.
    port = _QueueWritePort([[dict(_LEDGER_2_ROW)], [dict(_LEDGER_2_ROW)]])

    compiled, _round_trips = engine.compile_scenario_case(case, "postgres")
    run = engine.run_scenario_case(case, "postgres", port)

    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]
    assert [e.sql for e in compiled[1:]] == [
        "update ledger set out_z = ? where led_id = ? and out_z = ? and in_z = ?",
        "insert into ledger(led_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
    ]
    # The close addresses the FIXTURE milestone's own edge and the successor
    # carries its acct_num forward: both are facts only a seeded tracker holds.
    assert compiled[1].binds[3] == "2024-02-01T00:00:00+00:00"
    assert compiled[2].binds[:3] == (2, "B", decimal.Decimal("300.00"))


def test_run_scenario_case_access_step_graph_keeps_an_all_to_one_terminal_null() -> None:
    # An all-to-one path fans out nowhere, so it answers one terminal per root and
    # a branch that reached no row IS that terminal: `null`, the state a case
    # authors as a to-one member and grades distinctly from a node.
    case = _status_root_access(
        [{"segments": [{"rel": "OrderStatus.orderItem"}, {"rel": "OrderItem.order"}]}],
        {
            "action": "access",
            "on": 0,
            "path": "orderItem.order",
            "expectGraph": {"Order": [None]},
        },
    )
    port = QueueDbPort([[dict(_STATUS_ON_ORDER_ALONE)]])

    run = engine.run_scenario_case(case, "postgres", port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert graph["Order"] == [None]
