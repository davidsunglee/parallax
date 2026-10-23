"""The scenario, writeSequence, and conflict lanes, driven database-free.

The compile path is proven pure and golden-matching over a representative
exercised case; the run path is proven against a fake in-memory ``m-db-port``
(no Docker) so the port-execution seam, the `?` -> `%s` translation, and the
observation recording are covered in the unit lane.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import decimal
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import _case_ingress, case_format, models
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._lanes import scenario
from parallax.conformance._lifecycle_observation import (
    LifecycleRun,
    execution_lifecycle_observation,
)
from parallax.conformance._mechanism import case_document, model_facts
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance.simulated_temporal_store import (
    SimulatedStoreError,
    SimulatedTemporalStore,
)
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
)
from parallax.core._execution._unit_work.write_items import (
    InsertionAuthorizedWrite,
    ObjectLockedWrite,
    StateObservedWrite,
)
from parallax.core.base import (
    INFINITY,
    TemporalBound,
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    JsonDocument,
    MappingRow,
)
from parallax.core.dialect import POSTGRES
from parallax.core.execution import (
    TransactionTimePinReadOnlyError,
    TxnOptions,
)
from parallax.core.execution_lifecycle import DatabaseCallStarted
from parallax.core.metamodel import (
    EntityIdentity,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.temporal_read import Edge
from parallax.core.unit_work import (
    AdmittedWrite,
    Concurrency,
    MissingTargetError,
    OptimisticLockConflictError,
    RetainedObservation,
    StaleWriteError,
    WriteEffectError,
    WriteEvidenceError,
    WriteRejectedError,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
)
from parallax.core.write_plan.keys import TemporalObjectStateKey, VersionedObjectStateKey
from tests._support.case_corpus import case as corpus_case
from tests._support.db_port import ScriptedAdapter, Transact, Write
from tests._support.sweep_goldens import write_golden_statements
from tests.unit.conformance._lanes._scripted_port import ScriptedPort
from tests.unit.conformance._recording_ports import FakeWritePort


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these engine-function-level tests
    # exercise `run_conflict_case` on its own terms, never gated on whether
    # the case has ALSO been flipped visible in the sweep.
    return corpus_case(case_id)


def _own_copy(case: case_format.Case) -> case_format.Case:
    return dataclasses.replace(case, document=copy.deepcopy(case.document))


# --------------------------------------------------------------------------- #
# Scenario / writeSequence — the unit-of-work write lanes (Docker-free).       #
# --------------------------------------------------------------------------- #
# The rows a fake port answers the RESOLVING READ a keyed write owes
# (`m-case-format` *Resolving reads a write owes*). A write against existing
# state is stated against a value a read published, so a fake driving one of
# these lanes has to publish that value — the canned run stands in for the one
# current milestone the real database holds, keyed by the projection's own
# physical column names.
_OPEN_MILESTONE: Final[TemporalBound] = INFINITY


def _ledger_row(row_id: int, value: str, *, in_z: str, acct_num: str = "B") -> MappingRow:
    """One current Ledger milestone a fake port publishes.

    ``acct_num`` is the account the row's own history left there — the fixture's
    ``B`` for a fixture-held key, and the inserting step's own value for a key
    this case opened, because a write settles against what its resolving read
    published and a canned row that disagreed would license DML no state implies.
    """
    return {
        "led_id": row_id,
        "acct_num": acct_num,
        "val": decimal.Decimal(value),
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
    }


def _instant(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def _balance_row(row_id: int, value: str, *, in_z: str) -> MappingRow:
    return {
        "bal_id": row_id,
        "acct_num": "A",
        "val": decimal.Decimal(value),
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
    }


def _position_row(row_id: int, value: str, *, from_z: str, in_z: str) -> MappingRow:
    return {
        "pos_id": row_id,
        "acct_num": "A",
        "val": decimal.Decimal(value),
        "from_z": dt.datetime.fromisoformat(from_z),
        "thru_z": _OPEN_MILESTONE,
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
    }


def _voyage_row(row_id: int, payload: dict[str, object], *, in_z: str) -> MappingRow:
    return {
        "id": row_id,
        "in_z": dt.datetime.fromisoformat(in_z),
        "out_z": _OPEN_MILESTONE,
        "payload": payload,
    }


# The milestone `m-temporal-write-010`'s own insert entry leaves current, as its
# update entry's resolving read publishes it: one Structured Column carrying
# every member, which is what a document-mapped chain carries forward.
_VOYAGE_MILESTONE: Final[MappingRow] = _voyage_row(
    1,
    {"title": "Northern Run", "crew": 4, "manifest": {"cargo": "timber"}, "legs": []},
    in_z="2026-01-01T00:00:00+00:00",
)


def _synthetic_write(shape: str, document: dict[str, object]) -> case_format.Case:
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
                "mutation": "amend",
                "entity": "parallax.compatibility.Ledger",
                "rows": [{"id": 2, "value": value}],
                "at": at,
            }
        ],
        "databaseCalls": 2,
    }
    if uow is not None:
        step["uow"] = uow
    if rollback:
        step["rollback"] = True
    return step


def _synthetic_ledger_scenario(
    steps: list[dict[str, object]], units: dict[str, object] | None = None
) -> case_format.Case:
    document: dict[str, object] = {
        "model": "models/ledger.yaml",
        "shape": "scenario",
        "when": {"uow": {"concurrency": "optimistic"}, "scenario": steps},
    }
    if units is not None:
        document["then"] = {"units": units}
    return case_format.Case(
        path=Path("m-unit-work-998-synthetic.yaml"),
        case_id="m-unit-work-998",
        shape="scenario",
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/ledger.yaml",
        document=document,
    )


def test_run_scenario_case_commits_writes_and_reads_committed_state() -> None:
    port = FakeWritePort(
        find_rows=[{"id": 7, "owner": "Newton", "balance": decimal.Decimal("5.00"), "version": 1}]
    )
    run = scenario.run_scenario_case(_case("m-unit-work-001"), port)
    assert run.database_calls == 2
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


def test_run_scenario_case_rollback_step_aborts_but_counts_the_database_call() -> None:
    port = FakeWritePort(find_rows=[])
    run = scenario.run_scenario_case(_case("m-unit-work-011"), port)
    assert run.database_calls == 2  # the aborted insert still counts one Database Call
    assert len(port.writes) == 1  # the DML executed before the abort
    # An UNGROUPED find runs in its OWN transaction, exactly as `run_read_case`
    # does: every scenario resolves a Concurrency Preference (declared or the
    # default), and a participating read needs a boundary to demarcate whatever
    # lock its target Entity's own strategy calls for — so the find commits one.
    assert port.rollbacks == 1 and port.commits == 1
    assert run.emissions[0].case_pointer == "/scenario/0/write"


@pytest.mark.parametrize("row", [{"balance": "5.00"}, {"id": None, "balance": "5.00"}])
def test_an_unaddressed_write_neither_reads_nor_submits_dml(row: dict[str, object]) -> None:
    case = _synthetic_write(
        "writeSequence",
        {"when": {"writeSequence": [{"mutation": "amend", "entity": "Account", "rows": [row]}]}},
    )
    port = FakeWritePort()

    with pytest.raises(EngineError, match="a keyed write addresses None"):
        scenario.run_write_sequence_case(case, port)

    assert port.reads == []
    assert port.writes == []
    assert port.commits == 0 and port.rollbacks == 1


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
    run = scenario.run_scenario_case(_case("m-unit-work-005"), port)
    assert run.database_calls == 3
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


def test_run_scenario_case_runs_a_grouped_predicate_write_after_what_its_group_buffered() -> None:
    # m-batch-write-011: the predicate write runs at its own step, inside the
    # group's transaction rather than as a unit of its own, in the flush that
    # first delivers the delete its group buffered before it. The run reports
    # that flush under the predicate's step, the inserts buffered after it
    # under the step that buffered them, and the count the verb returned.
    port = FakeWritePort(
        find_rows=[
            {
                "id": 12,
                "order_id": 1,
                "sku": "B-200",
                "quantity": 1,
                "shipped_on": dt.date(2024, 2, 15),
            }
        ]
    )
    run = scenario.run_scenario_case(_case("m-batch-write-011"), port)
    assert run.database_calls == 5
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/2/write",
        "/scenario/2/write",
        "/scenario/3/write",
        "/scenario/3/write",
    ]
    assert run.step_affected_rows == [{"at": "/scenario/2", "affectedRows": 1}]
    # What is reported is what the port executed, in the order it executed it.
    assert [e.sql.replace("?", "%s") for e in run.emissions[1:]] == [sql for sql, _ in port.writes]
    assert [sql.split("(")[0] for sql, _ in port.writes] == [
        "delete from order_item where id = %s",
        "update order_item set sku = %s where quantity < %s",
        "insert into orders",
        "insert into order_item",
    ]
    # One participating read, then the case's own tables read back once it ran.
    assert len(port.reads) == 1 + len(run.table_state or {})
    assert port.commits == 1 and port.rollbacks == 0


def test_a_group_opening_with_a_predicate_write_runs_at_that_writes_own_instant() -> None:
    steps: list[Mapping[str, object]] = [
        {"uow": "g", "write": {"mutation": "delete", "at": "2024-05-01T00:00:00+00:00"}},
        {"uow": "g", "write": [{"mutation": "delete", "at": "2025-01-01T00:00:00+00:00"}]},
    ]
    assert scenario.group_tx_instant(steps, range(2)) == "2024-05-01T00:00:00+00:00"


def _account(identifier: int, owner: str, balance: str, version: int) -> MappingRow:
    return {
        "id": identifier,
        "owner": owner,
        "balance": decimal.Decimal(balance),
        "version": version,
    }


def _two_delivery_port() -> ScriptedPort:
    """The four pages `m-unit-work-030`'s two deliveries read at `batchSize: 2`.

    Each page asks for THREE accounts and delivers two, so each delivery reads
    {1, 2, 3} and keeps {1, 2}, then reads {3} and ends on that short page. The
    second delivery reads account 1 at the version the first write left, which
    is what makes the two deliveries' own observations of that key
    distinguishable at all.
    """
    first = _account(1, "Ada", "100.00", 1)
    written = _account(1, "Ada", "125.00", 2)
    second = _account(2, "Linus", "250.00", 1)
    third = _account(3, "Grace", "10.00", 1)
    return ScriptedPort(
        read_rows=[
            [first, second, third],
            [third],
            [written, second, third],
            [third],
        ]
    )


def test_run_scenario_case_settles_a_write_against_the_delivery_that_published_its_root() -> None:
    # `m-unit-work-030`: a grouped read step carrying `stream` runs through
    # `tx.wire.stream` at its declared page size, and each write settles against
    # the generation the DELIVERY it names published. The scripted port answers
    # the four pages the two deliveries read — {1, 2, 3} kept down to {1, 2},
    # then {3}, twice, with account 1 at version 2 the second time round, which
    # is the state the first write left. Both writes address account 1 and neither
    # is resolved from case
    # state: the first gates on the version delivery one published for a root it
    # handed over on a page since released, the second on the version delivery
    # two published for the same key. Each write here names the delivery that ran
    # most recently before it, so what this pins is that a delivery's roots ARE
    # evidence and that a second reading of a delivered key files a second
    # observed state; the test below moves `on` alone, where reading the group's
    # latest observation and reading the named delivery's diverge.
    port = _two_delivery_port()

    run = scenario.run_scenario_case(_case("m-unit-work-030"), port)

    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/0/objectQuery",
        "/scenario/1/write",
        "/scenario/2/objectQuery",
        "/scenario/2/objectQuery",
        "/scenario/3/write",
    ]
    assert [binds for _sql, binds in port.reads] == [
        (3,),
        (2, 2, 3, 3, 3),
        (3,),
        (2, 2, 3, 3, 3),
    ]
    assert [e.binds for e in run.emissions if e.case_pointer.endswith("write")] == [
        (125.00, 2, 1, 1),
        (175.00, 3, 1, 2),
    ]
    assert run.database_calls == 6
    assert len(port.writes) == 2


def test_run_scenario_case_continues_a_named_delivery_past_its_flushed_write() -> None:
    # With `m-unit-work-030`'s second write moved onto the FIRST delivery, the
    # source it names observed the version the first write advanced from, and
    # that write's completion carries the source's authority on to the version
    # it produced: the second write gates on version 2 exactly as it does
    # through the second delivery, reading nothing more to do so.
    source = _case("m-unit-work-030")
    document = cast(
        "dict[str, Any]",
        case_format.safe_load_yaml(source.path.read_text(encoding="utf-8")),
    )
    steps = cast("list[dict[str, Any]]", cast("dict[str, Any]", document["when"])["scenario"])
    for entry in cast("list[dict[str, Any]]", steps[3]["write"]):
        entry["on"] = 0
    port = _two_delivery_port()

    scenario.run_scenario_case(
        dataclasses.replace(_case("m-unit-work-030"), document=document), port
    )
    assert [tuple(binds) for _sql, binds in port.writes] == [
        (decimal.Decimal("125.00"), 2, 1, 1),
        (decimal.Decimal("175.00"), 3, 1, 2),
    ]


def test_run_scenario_case_reports_each_streamed_steps_own_delivered_roots() -> None:
    # A streamed step's `stepRows` observation (m-conformance-adapter) is the roots
    # ITS OWN delivery published, concatenated across every page in delivery order.
    # `m-unit-work-030`'s two deliveries read the same three accounts either side of
    # a write that moves account 1, so the two entries differ by exactly what that
    # write did: an observation read off the group's accumulated published values,
    # or off one page, could not tell them apart.
    run = scenario.run_scenario_case(_case("m-unit-work-030"), _two_delivery_port())

    assert run.step_rows == [
        {
            "at": "/scenario/0",
            "rows": [
                {"id": 1, "owner": "Ada", "balance": "100.00", "version": 1},
                {"id": 2, "owner": "Linus", "balance": "250.00", "version": 1},
                {"id": 3, "owner": "Grace", "balance": "10.00", "version": 1},
            ],
        },
        {
            "at": "/scenario/2",
            "rows": [
                {"id": 1, "owner": "Ada", "balance": "125.00", "version": 2},
                {"id": 2, "owner": "Linus", "balance": "250.00", "version": 1},
                {"id": 3, "owner": "Grace", "balance": "10.00", "version": 1},
            ],
        },
    ]


def _abstract_step_query(case_id: str) -> ObjectQueryNode:
    """The first scenario step's query of ``case_id`` — an abstract-position read."""
    case = _case(case_id)
    steps = cast("list[dict[str, Any]]", cast("dict[str, Any]", case.document)["when"])
    return scenario.step_query(
        cast("list[dict[str, Any]]", cast("dict[str, Any]", steps)["scenario"])[0],
        model_facts.load_case_metamodel(case),
    )


# `m-inheritance-130`'s step 0 reads the abstract root `Vehicle` and is handed the
# concrete `Car` that row resolves to: id 1, `Sedan`, version 5, four doors, and no
# `axles` key at all, a materialized node carrying only its own branch's members.
_PUBLISHED_CAR: MappingRow = {
    "id": 1,
    "name": "Sedan",
    "version": 5,
    "doors": 4,
    "familyVariant": "Car",
}


def test_graph_rows_renders_an_abstract_positions_whole_projection() -> None:
    # What an abstract step's `expectRows` state is the projection the published
    # node OCCUPIES (m-case-format "Read targeting"): every column the position's
    # superset places, `null` where the row's own branch contributes none, and the
    # `familyVariant` the node carries. Rendering the ADDRESSED position's
    # applicable members instead drops `doors` — a value the read published — and
    # reports no variant, which is a node no case could state.
    case = _case("m-inheritance-130")

    rows = scenario.graph_rows(
        model_facts.load_case_metamodel(case),
        _abstract_step_query("m-inheritance-130"),
        [dict(_PUBLISHED_CAR)],
    )

    assert rows == [
        {
            "id": 1,
            "name": "Sedan",
            "version": 5,
            "doors": 4,
            "axles": None,
            "familyVariant": "Car",
        }
    ]


def test_graph_rows_narrows_an_abstract_positions_projection_to_its_selection() -> None:
    # Narrowing shrinks the superset the position projects without making the read
    # concrete: over `[Car]` alone the sibling `axles` is no column of the
    # projection at all, and the node still states the variant it resolved to.
    case = _case("m-inheritance-130")
    query = dataclasses.replace(
        _abstract_step_query("m-inheritance-130"), narrow_to=("parallax.compatibility.Car",)
    )

    rows = scenario.graph_rows(model_facts.load_case_metamodel(case), query, [dict(_PUBLISHED_CAR)])

    assert rows == [{"id": 1, "name": "Sedan", "version": 5, "doors": 4, "familyVariant": "Car"}]


def test_graph_rows_selects_reused_member_names_from_each_published_variant() -> None:
    case = _case("m-inheritance-124")
    when = cast("Mapping[str, object]", case.document["when"])
    query = deserialize_query(when["objectQuery"])

    rows = scenario.graph_rows(
        model_facts.load_case_metamodel(case),
        query,
        [
            {
                "id": 1,
                "detail": "visa-4242",
                "authorizationCode": "AUTH-7",
                "familyVariant": "CardPayment",
            },
            {"id": 2, "detail": "12.50", "familyVariant": "CashPayment"},
        ],
    )

    assert rows == [
        {
            "id": 1,
            "detail": "visa-4242",
            "authorization_code": "AUTH-7",
            "familyVariant": "CardPayment",
        },
        {
            "id": 2,
            "detail": "12.50",
            "authorization_code": None,
            "familyVariant": "CashPayment",
        },
    ]


def test_graph_rows_refuses_an_abstract_read_that_published_no_variant() -> None:
    # An abstract position publishes concrete nodes, so a node arriving without the
    # variant is a lane that resolved nothing rather than a row to render: which
    # branch its columns belong to would have to be guessed.
    case = _case("m-inheritance-130")
    node = {key: value for key, value in _PUBLISHED_CAR.items() if key != "familyVariant"}

    with pytest.raises(EngineError, match="familyVariant"):
        scenario.graph_rows(
            model_facts.load_case_metamodel(case), _abstract_step_query("m-inheritance-130"), [node]
        )


_ORDER_1_ROW: MappingRow = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": decimal.Decimal("10.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 5),
}

_ORDER_ITEM_11_ROW: MappingRow = {
    "id": 11,
    "order_id": 1,
    "sku": "A-100",
    "quantity": 2,
    "shipped_on": None,
}

_ORDER_ITEM_13_ROW: MappingRow = {
    "id": 13,
    "order_id": 1,
    "sku": "D-130",
    "quantity": 6,
    "shipped_on": None,
}


def _ryow_relationship_port() -> ScriptedPort:
    """The four level reads `m-unit-work-029`'s two grouped finds issue.

    The second find's item level answers what the group's own writes left: the
    inserted row beside the rewritten one. A scripted port is what makes the
    difference between the two finds authorable at all here — `FakeWritePort`
    answers one canned row set to every read, so both finds would state one graph.
    """
    return ScriptedPort(
        read_rows=[
            [dict(_ORDER_1_ROW)],
            [dict(_ORDER_ITEM_11_ROW)],
            [dict(_ORDER_1_ROW)],
            [dict(_ORDER_ITEM_13_ROW), dict(_ORDER_ITEM_11_ROW) | {"sku": "Rewritten"}],
        ]
    )


def test_run_scenario_case_reports_a_grouped_finds_own_materialized_graph() -> None:
    # `m-unit-work-029`: the READ placement of `expectGraph`. Each find reports
    # what IT materialized — roots plus the relationship its own Include Path
    # populated — at its own step pointer, so the two graphs differ by exactly
    # what the group's write did between them.
    run = scenario.run_scenario_case(_case("m-unit-work-029"), _ryow_relationship_port())

    assert [entry["at"] for entry in run.step_graphs] == ["/scenario/0", "/scenario/2"]
    graphs = [cast("dict[str, list[Any]]", entry["graph"]) for entry in run.step_graphs]
    assert [
        sorted(item["id"] for item in root["items"]) for graph in graphs for root in graph["Order"]
    ] == [
        [11],
        [11, 13],
    ]
    assert [root["items"][-1]["sku"] for graph in graphs for root in graph["Order"]] == [
        "A-100",
        "Rewritten",
    ]


def test_run_scenario_case_reports_an_ungrouped_finds_own_materialized_graph() -> None:
    # The read placement carries no `uow` requirement: an ungrouped read-back
    # states what the committed database answered, which is a legitimate claim in
    # its own right — just not the survival one an `access` step makes.
    when: dict[str, object] = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"path": "Order.id", "value": 1}},
                    "includes": [{"segments": [{"rel": "Order.items"}]}],
                },
                "expectGraph": {"Order": [{"id": 1}]},
            }
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    run = scenario.run_scenario_case(
        case,
        ScriptedPort(read_rows=[[dict(_ORDER_1_ROW)], [dict(_ORDER_ITEM_11_ROW)]]),
    )
    assert [entry["at"] for entry in run.step_graphs] == ["/scenario/0"]
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    (root,) = graph["Order"]
    assert [item["id"] for item in cast("list[dict[str, object]]", root["items"])] == [11]


def test_run_scenario_case_refuses_a_read_step_graph_over_no_include_path() -> None:
    # The read placement states the relationships that read materialized, and a
    # read declaring no Include Path materialized none. The schema refuses the
    # shape; the lane refuses it too rather than reporting an empty graph.
    case = _own_copy(_load_case("m-unit-work-029"))
    when = cast("dict[str, Any]", case.document["when"])
    steps = cast("list[dict[str, Any]]", when["scenario"])
    del steps[0]["objectQuery"]["includes"]

    with pytest.raises(EngineError, match="declares no `includes`"):
        scenario.run_scenario_case(case, _ryow_relationship_port())


def test_run_scenario_case_doomed_uow_span_rolls_back_as_one_unit() -> None:
    # m-unit-work-002: steps 0-1 share the doomed `doomed-update` group (its
    # write declares `rollback: true`); step 2 is an UNGROUPED post-abort find.
    # The GROUP rolls back as ONE unit (one port-level rollback, zero commits)
    # — never a separate transaction per step.
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    run = scenario.run_scenario_case(_case("m-unit-work-002"), port)
    assert run.database_calls == 3
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


def test_run_scenario_case_rereads_the_original_milestone_after_an_ungrouped_abort() -> None:
    port = FakeWritePort(find_rows=[_ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")])
    case = _synthetic_ledger_scenario(
        [
            _ledger_update("999.00", "2026-01-01T00:00:00+00:00", rollback=True),
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00"),
        ]
    )
    run = scenario.run_scenario_case(case, port)
    assert port.rollbacks == 1 and port.commits == 1
    aborted_close, _aborted_successor, close, successor = run.emissions
    assert aborted_close.binds[3] == _instant("2024-02-01T00:00:00+00:00")
    assert close.case_pointer == "/scenario/1/write"
    assert close.binds[3] == _instant("2024-02-01T00:00:00+00:00")
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

    compiled, _database_calls = scenario.compile_scenario_case(case, "postgres")
    run = scenario.run_scenario_case(case, port)

    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]
    close, successor = compiled
    assert close.binds[3] == _instant("2024-02-01T00:00:00+00:00")
    assert successor.binds[:3] == (2, "B", decimal.Decimal("300.00"))


def _ledger_insert(at: str) -> dict[str, object]:
    return {
        "write": [
            {
                "mutation": "insert",
                "entity": "parallax.compatibility.Ledger",
                "rows": [{"id": 9, "acctNum": "D", "value": decimal.Decimal("100.00")}],
                "at": at,
            }
        ],
        "databaseCalls": 1,
    }


def _ledger_chain_update(
    value: str, at: str, *, uow: str | None = None, rollback: bool = False
) -> dict[str, object]:
    """The sibling of :func:`_ledger_update` retargeted at the inserted id 9."""
    step = _ledger_update(value, at, uow=uow, rollback=rollback)
    cast("list[dict[str, object]]", step["write"])[0]["rows"] = [{"id": 9, "value": value}]
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
    compiled, _database_calls = scenario.compile_scenario_case(case, "postgres")
    _insert, aborted_close, _aborted_successor, close, successor = compiled
    assert aborted_close.binds[3] == _instant("2025-01-01T00:00:00+00:00")
    assert close.case_pointer == "/scenario/2/write"
    assert close.binds[3] == _instant("2025-01-01T00:00:00+00:00")
    assert successor.binds[2] == decimal.Decimal("400.00")
    # Each update step is its own transaction, so each owes a resolving read of
    # the milestone the insert left current — the value its keyed verb is
    # addressed by.
    port = FakeWritePort(
        find_rows=[_ledger_row(9, "100.00", in_z="2025-01-01T00:00:00+00:00", acct_num="D")]
    )
    run = scenario.run_scenario_case(case, port)
    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]


def test_scenario_compile_lane_runs_a_doomed_uow_group_as_one_transaction_it_restores() -> None:
    # The doomed group's two updates of key 9 share one transaction, so both
    # settle against the milestone the insert left (2025-01-01) and COALESCE,
    # as two writes settling against one observed state do through the public
    # keyed verbs (`m-unit-work-025`): one close and one successor carrying the
    # later value, delivered by the group's pre-commit flush under its last
    # write step. The group then rolls back, so the ungrouped step 3 after it is
    # back on the insert's milestone too.
    case = _synthetic_ledger_scenario(
        [
            _ledger_insert("2025-01-01T00:00:00+00:00"),
            _ledger_chain_update("999.00", "2026-01-01T00:00:00+00:00", uow="doomed"),
            _ledger_chain_update("888.00", "2026-01-01T00:00:00+00:00", uow="doomed"),
            _ledger_chain_update("300.00", "2026-02-01T00:00:00+00:00"),
        ],
        {"doomed": {"outcome": "rolledBack"}},
    )
    compiled, _database_calls = scenario.compile_scenario_case(case, "postgres")
    _insert, doomed_close, doomed_successor, close, successor = compiled
    assert [doomed_close.case_pointer, doomed_successor.case_pointer] == ["/scenario/2/write"] * 2
    assert doomed_close.binds[3] == _instant("2025-01-01T00:00:00+00:00")
    assert doomed_successor.binds[2] == decimal.Decimal("888.00")
    assert close.case_pointer == "/scenario/3/write"
    assert close.binds[3] == _instant("2025-01-01T00:00:00+00:00")
    assert successor.binds[2] == decimal.Decimal("300.00")


def _two_group_interleave_steps() -> list[dict[str, object]]:
    return [
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"path": "Account.id", "value": 1}},
            },
            "databaseCalls": 1,
            "statements": [{"sql": {"postgres": "select ... where t0.id = ?"}, "binds": [1]}],
        },
        {
            "uow": "b",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"path": "Account.id", "value": 2}},
            },
            "databaseCalls": 1,
            "statements": [{"sql": {"postgres": "select ... where t0.id = ?"}, "binds": [2]}],
        },
        {
            "uow": "a",
            "write": [{"mutation": "amend", "entity": "Account", "rows": [{"id": 1}]}],
            "databaseCalls": 1,
            "statements": [
                {
                    "sql": {"postgres": "update account set balance = ? where id = ?"},
                    "binds": [1.0, 1],
                }
            ],
        },
    ]


def test_scenario_uow_spans_signals_the_two_group_interleave_with_none() -> None:
    # The interleaved shape (two `uow` groups whose steps interleave):
    # `_scenario_uow_spans` returns `None` rather than raising — the caller
    # routes to `run_interleaved_scenario_case` instead, which needs a
    # second, peer-backed connection this
    # function does not construct.
    assert (
        scenario._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
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
    case = _synthetic_write(
        "scenario",
        {
            "when": {"scenario": steps},
            "then": {"databaseCalls": 3, "units": {"a": {"outcome": "rolledBack"}}},
        },
    )
    emissions, _database_calls = scenario.compile_scenario_case(case, "postgres")
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
            "then": {"databaseCalls": 3},
        },
    )
    with pytest.raises(EngineError, match="run_interleaved_scenario_case"):
        scenario.run_scenario_case(case, FakeWritePort())


def test_scenario_uow_spans_rejects_interleaving_beyond_the_two_group_shape() -> None:
    # Three `uow` groups, one of them non-contiguous: a TWO-group interleave is
    # the ONLY shape `run_interleaved_scenario_case` supports: it opens exactly
    # ONE peer connection beside the caller's port — anything beyond it raises
    # loudly rather than silently mis-executing a THIRD concurrent session no
    # seam here provides.
    steps: list[dict[str, object]] = [
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"path": "Account.id", "value": 1}},
            },
        },
        {
            "uow": "b",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"path": "Account.id", "value": 2}},
            },
        },
        {
            "uow": "c",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"path": "Account.id", "value": 3}},
            },
        },
        {
            "uow": "a",
            "write": [{"mutation": "amend", "entity": "Account", "rows": [{"id": 1}]}],
        },
    ]
    with pytest.raises(EngineError, match="interleave beyond the witnessed"):
        scenario._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            "m-unit-work-999-synthetic.yaml", steps
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
                "predicate": {"eq": {"path": "Account.id", "value": 1}},
            },
        },
        {
            "uow": "a",
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"path": "Account.id", "value": 1}},
            },
        },
    ]
    assert scenario.group_tx_instant(steps, range(2)) == scenario.INERT_CLOCK_INSTANT


def test_versioned_non_temporal_version_attribute_is_none_for_a_temporal_entity() -> None:
    # A temporal entity observes a whole milestone rather than a version, so it has
    # no version attribute to resolve — `m-opt-lock`'s version column is a
    # non-temporal-only concept.
    meta = model_facts.load_case_metamodel(_load_case("m-navigate-012"))
    assert (
        scenario._versioned_non_temporal_version_attribute(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
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
    own identity and Object State Key for it, beside the milestone it is."""
    members: dict[str, object] = {
        "id": 1,
        "name": name,
        "validStart": valid_start,
        "validEnd": valid_end,
        "txStart": _APR,
        "txEnd": INFINITY,
    }
    return RetainedObservation(
        TemporalObjectStateKey(_POLICY, Edge(valid_time=valid_start, tx_time=_APR)),
        TemporalObservation(predecessor=PredecessorRow(members=members)),
        None,
    )


def _settled(source: Any) -> Any:
    return scenario._observation_from_source(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
        "Policy", _POLICY, source
    )


def test_a_settled_write_settles_against_the_node_the_named_find_observed() -> None:
    # A milestone chain holds more than one row per primary key, so one find may
    # return several and each is evidence about the milestone it actually is. The
    # write is supplied the ONE the write step's own `on` reference named —
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
    with pytest.raises(EngineError, match="settles against observed 0 rows"):
        _settled(())


def test_a_settled_write_refuses_a_find_that_observed_several_rows_of_its_key() -> None:
    # No single value could have come from two milestones, so a reference that
    # resolves to both names nothing a write could have been handed.
    with pytest.raises(EngineError, match="settles against observed 2 rows"):
        _settled((_policy_node(_JAN, _JUN, "head"), _policy_node(_JUN, INFINITY, "tail")))


def _account_node(version: int) -> Any:
    """One node a grouped find of the versioned `Account` published."""
    key = ObjectKey(EntityIdentity("parallax.compatibility", "Account"), (("id", 1),))
    return RetainedObservation(
        VersionedObjectStateKey(key, version), VersionObservation(observed_version=version), None
    )


def test_a_settled_write_names_a_versioned_targets_own_read_generation() -> None:
    # A versioned Non-Temporal target holds one ROW per primary key, but a unit of
    # work holds one observed GENERATION of it per read: a group that observes the
    # row, writes it, and reads it again holds two, and the reference is what says
    # which of them a write settles against. A store keyed by identity alone
    # answers only the latest, so the earlier generation would be unreachable.
    meta = model_facts.load_case_metamodel(_case("m-unit-work-001"))

    def settle(node: Any) -> object:
        write = scenario._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"mutation": "amend", "entity": "Account", "rows": [{"id": 1, "balance": "5.00"}]},
            meta,
            SimulatedTemporalStore(),
            set(),
            [],
            (node,),
        )[0]
        return write.supplied_observation

    assert settle(_account_node(1)) == _account_node(1).evidence
    assert settle(_account_node(4)) == _account_node(4).evidence


def test_a_settled_write_is_refused_when_its_named_find_observed_no_such_row() -> None:
    # The reference names evidence that does not exist, and a write with no
    # evidence at all is refused where every unobserved keyed write is.
    meta = model_facts.load_case_metamodel(_case("m-unit-work-001"))
    with pytest.raises(EngineError, match="observed 0 rows"):
        scenario._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"mutation": "amend", "entity": "Account", "rows": [{"id": 1, "balance": "5.00"}]},
            meta,
            SimulatedTemporalStore(),
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
        TemporalObjectStateKey(key, Edge(tx_time=start)),
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
    meta = model_facts.load_case_metamodel(_case("m-temporal-write-001"))
    current = _balance_node("2024-04-01T00:00:00+00:00", "100.00")
    historical = _balance_node("2024-01-01T00:00:00+00:00", "90.00")

    def settle(node: Any) -> object:
        write = scenario._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {
                "mutation": "amend",
                "entity": "Balance",
                "rows": [{"id": 1, "value": "5.00"}],
            },
            meta,
            SimulatedTemporalStore(),
            set(),
            [],
            (node,),
        )[0]
        observation = write.supplied_observation
        assert isinstance(observation, TemporalObservation)
        return observation.predecessor.members["txStart"]

    assert settle(current) == current.evidence.predecessor.members["txStart"]
    assert settle(historical) == historical.evidence.predecessor.members["txStart"]


def test_run_scenario_case_settles_a_grouped_temporal_close_against_the_find_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # m-unit-work-015: two finds of ONE bitemporal key observe two rectangles both
    # current on Transaction Time, and the write step names the first with `on`.
    # The evidence the write settles by is the Object State Key the claim that
    # node carries is addressed by, and the golden the oracle renders comes from
    # the same node's own milestone — so the close addresses R2's `thru_z`, which
    # a store keyed by identity alone could not have chosen between. The write
    # runs from its source's pin through infinity, so the flush reads the
    # coverage beyond R2 and closes R3 too; R2's changed part and R3's are one
    # row, which one insert opens beside R2's head.
    counts = _counting_case_state_reads(monkeypatch)
    r2 = {
        "pos_id": 1,
        "acct_num": "A",
        "val": decimal.Decimal("100.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }
    r3 = {
        **r2,
        "val": decimal.Decimal("200.00"),
        "from_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "thru_z": INFINITY,
    }
    port = FakeWritePort(read_script=[[r2], [r3], [r2, r3]])
    run = scenario.run_scenario_case(_load_case("m-unit-work-015"), port)
    assert run.database_calls == 6
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
    assert run.emissions[3].binds[2] == "infinity"
    assert counts == {"target": 0, "coverage": 0}


@pytest.mark.parametrize("state_graded", [False, True])
def test_a_grouped_write_starting_away_from_its_finds_pin_is_an_engine_error(
    state_graded: bool,
) -> None:
    case = _own_copy(_load_case("m-unit-work-015"))
    document = cast("dict[str, Any]", case.document)
    steps = cast("list[dict[str, Any]]", document["when"]["scenario"])
    steps[2]["write"][0]["validFrom"] = "2024-04-01T00:00:00.000000Z"
    row = {
        "pos_id": 1,
        "acct_num": "A",
        "val": decimal.Decimal("100.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }
    with pytest.raises(EngineError, match="starts at"):
        scenario.run_scenario_case(
            _with_grading(case, state_graded), FakeWritePort(read_script=[[row], [row]])
        )


def test_a_document_milestone_after_setup_uses_the_production_read() -> None:
    port = FakeWritePort(find_rows=[{**_VOYAGE_MILESTONE, "id": 7}])
    emissions, _state, calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-011"), port
    )
    assert calls == 3
    assert len(emissions) == 2
    assert emissions[0].sql.endswith("and in_z = ?")


def test_a_tracked_milestone_under_columns_survives_out_of_band_statements() -> None:
    # The refusal is scoped to Relational Document Layout, where the tracked
    # members cannot even account for the row's SLOTS. Under `Columns` the tracker
    # holds every column, so out-of-band state leaves the observation STALE — the
    # very thing a conflict case authors on purpose — never unrepresentable.
    meta = model_facts.load_case_metamodel(_load_case("m-temporal-write-002"))
    model = meta
    store = SimulatedTemporalStore()
    store.note_out_of_band_write()
    scenario._refuse_unaccounted_document_milestone(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
        model,
        model_facts.case_entity(model, "parallax.compatibility.Balance"),
        {"id": 1},
        store,
    )


def test_a_document_chain_reads_the_milestone_its_prior_entry_stored() -> None:
    port = FakeWritePort(find_rows=[_VOYAGE_MILESTONE])
    emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-010"), port
    )
    # Three DML statements plus the update entry's own resolving read.
    assert database_calls == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]


def test_a_document_milestone_opened_after_out_of_band_statements_still_chains() -> None:
    case = _load_case("m-temporal-write-010")
    with_apply = dataclasses.replace(
        case,
        document={
            **case.document,
            "given": {"apply": [{"sql": "insert into unrelated(id) values (1)"}]},
        },
    )
    port = FakeWritePort(find_rows=[_VOYAGE_MILESTONE])
    emissions, _table_state, database_calls = scenario.run_write_sequence_case(with_apply, port)
    assert database_calls == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert port.writes[0][0].startswith("insert into unrelated")


def test_a_later_group_step_composes_onto_a_pending_document_insert() -> None:
    # The insert is still pending in the group's buffer when the next step
    # amends its key, so the amendment composes onto it as an entry of the
    # same step would, and out-of-band statements raise no stored-milestone
    # refusal for a row the store has not yet been handed.
    def voyage(mutation: str, title: str) -> dict[str, object]:
        return {
            "uow": "g",
            "write": [
                {
                    "mutation": mutation,
                    "entity": "parallax.compatibility.Voyage",
                    "rows": [
                        {
                            "id": 1,
                            "title": title,
                            "crew": 4,
                            "manifest": {"cargo": "timber"},
                            "legs": [],
                        }
                    ],
                    "at": "2026-01-01T00:00:00.000000Z",
                }
            ],
        }

    case = _synthetic_write(
        "scenario",
        {
            "model": "models/document-layout.yaml",
            "given": {"apply": [{"sql": "insert into unrelated(id) values (1)"}]},
            "when": {
                "uow": {"concurrency": "locking"},
                "scenario": [voyage("insert", "Northern Run"), voyage("amend", "Southern Run")],
            },
            "then": {"units": {"g": {"outcome": "committed"}}},
        },
    )
    port = FakeWritePort()
    run = scenario.run_scenario_case(case, port)
    assert [
        (emission.case_pointer, emission.sql.split(" ", 1)[0]) for emission in run.emissions
    ] == [("/scenario/1/write", "insert")]
    (document,) = (bind.value for bind in run.emissions[0].binds if isinstance(bind, JsonDocument))
    assert cast("Mapping[str, object]", document)["title"] == "Southern Run"


def test_a_restated_occurrence_is_assigned_literally_beside_the_stored_keys_it_leaves() -> None:
    # A row restating `manifest` exactly as the milestone's declared members hold
    # it still assigns it: the occurrence is replaced whole, so the unknown key
    # stored inside it is gone, while every position the row does not assign —
    # declared or not — is carried from the document the write's source read.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/document-layout.yaml",
            "when": {
                "uow": {"concurrency": "locking"},
                "writeSequence": [
                    {
                        "mutation": "amend",
                        "entity": "parallax.compatibility.Voyage",
                        "rows": [{"id": 7, "title": "Southbound", "manifest": {"cargo": "grain"}}],
                        "at": "2026-06-01T00:00:00.000000Z",
                    }
                ],
            },
        },
    )
    stored = _voyage_row(
        7,
        {
            "title": "Northbound",
            "crew": 12,
            "charterCode": "NB-204",
            "manifest": {"cargo": "grain", "sealNumber": "S-4021"},
            "legs": [{"port": "Oslo"}],
        },
        in_z="2026-01-01T00:00:00+00:00",
    )
    emissions, _table_state, _database_calls = scenario.run_write_sequence_case(
        case, FakeWritePort(find_rows=[stored])
    )
    _close, successor = emissions

    (document,) = (bind.value for bind in successor.binds if isinstance(bind, JsonDocument))
    assert dict(cast("Mapping[str, object]", document)) == {
        "title": "Southbound",
        "crew": 12,
        "charterCode": "NB-204",
        "manifest": {"cargo": "grain"},
        "legs": ({"port": "Oslo"},),
    }


def test_a_flushes_statements_are_reported_under_the_last_write_buffered_before_it() -> None:
    # The group buffers every write before one pre-commit flush, so everything
    # that flush emits belongs to the group's last write step — the rule the run
    # lane reports a held group's delivered writes by.
    compiled, database_calls = scenario.compile_scenario_case(
        _load_case("m-execution-lifecycle-002"), "postgres"
    )
    assert [emission.case_pointer for emission in compiled] == ["/scenario/1/write"] * 2
    assert database_calls == 2


def test_a_predicate_writes_flush_is_reported_under_the_predicates_own_step() -> None:
    # The predicate's flush delivers the delete its group buffered before it,
    # then its own statement; the inserts buffered after it reach the
    # pre-commit flush under the step that buffered them.
    compiled, database_calls = scenario.compile_scenario_case(
        _load_case("m-batch-write-011"), "postgres"
    )
    assert [emission.case_pointer for emission in compiled] == [
        "/scenario/0/objectQuery",
        "/scenario/2/write",
        "/scenario/2/write",
        "/scenario/3/write",
        "/scenario/3/write",
    ]
    assert database_calls == 5


def _account_insert(account_id: int) -> dict[str, object]:
    return {
        "mutation": "insert",
        "entity": "Account",
        "rows": [{"id": account_id, "owner": "Noether", "balance": "5.00", "version": 1}],
    }


def _account_insert_step(account_id: int, *, uow: str = "g") -> dict[str, object]:
    return {"uow": uow, "write": [_account_insert(account_id)]}


def _account_find_step(account_id: int, *, uow: str = "g") -> dict[str, object]:
    return {
        "uow": uow,
        "objectQuery": {
            "target": "Account",
            "predicate": {"eq": {"path": "Account.id", "value": account_id}},
        },
    }


def test_a_committing_groups_read_flushes_what_its_earlier_steps_buffered() -> None:
    # One transaction for the whole committing group: a find step's read
    # flushes the insert buffered before it, and the group's end flushes the
    # one after it; each flush's statements belong to the last write step
    # buffered before it.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    _account_insert_step(90),
                    _account_find_step(90),
                    _account_insert_step(91),
                ]
            }
        },
    )
    compiled, _database_calls = scenario.compile_scenario_case(case, "postgres")
    assert [(emission.case_pointer, emission.sql.split(" ", 1)[0]) for emission in compiled] == [
        ("/scenario/0/write", "insert"),
        ("/scenario/1/objectQuery", "select"),
        ("/scenario/2/write", "insert"),
    ]
    assert [emission.binds[0] for emission in compiled if emission.sql.startswith("insert")] == [
        90,
        91,
    ]


def test_a_groups_writes_buffered_before_one_flush_compose_in_its_one_buffer() -> None:
    compiled, _database_calls = scenario.compile_scenario_case(
        _synthetic_write(
            "scenario",
            {"when": {"scenario": [_account_insert_step(90), _account_insert_step(91)]}},
        ),
        "postgres",
    )
    ungrouped, _ = scenario.compile_scenario_case(
        _synthetic_write(
            "scenario",
            {"when": {"scenario": [{"write": [_account_insert(90), _account_insert(91)]}]}},
        ),
        "postgres",
    )
    # Two steps of one group compose exactly as two entries of one step do.
    assert [(emission.sql, emission.binds) for emission in compiled] == [
        (emission.sql, emission.binds) for emission in ungrouped
    ]
    assert {emission.case_pointer for emission in compiled} == {"/scenario/1/write"}


def _counting_case_state_reads(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"target": 0, "coverage": 0}

    def counted(kind: str, read: Callable[..., list[tuple[object, ...]]]) -> Any:
        def counting(*arguments: object) -> list[tuple[object, ...]]:
            counts[kind] += 1
            return read(*arguments)

        return counting

    monkeypatch.setattr(
        SimulatedTemporalStore,
        "target_rows",
        counted("target", SimulatedTemporalStore.target_rows),
    )
    monkeypatch.setattr(
        SimulatedTemporalStore,
        "coverage_rows",
        counted("coverage", SimulatedTemporalStore.coverage_rows),
    )
    return counts


@pytest.mark.parametrize(
    ("case_id", "reads"),
    [
        pytest.param("m-opt-lock-027", {"target": 0, "coverage": 0}, id="optimistic-version"),
        pytest.param("m-temporal-write-042", {"target": 0, "coverage": 1}, id="optimistic-window"),
        pytest.param("m-opt-lock-029", {"target": 1, "coverage": 0}, id="locking-amend"),
        pytest.param("m-opt-lock-040", {"target": 1, "coverage": 0}, id="locking-delete"),
        pytest.param("m-temporal-write-043", {"target": 1, "coverage": 0}, id="locking-replace"),
    ],
)
def test_a_target_entry_compiles_through_target_admission(
    case_id: str, reads: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    # An authored `ifVersion` or `ifTxStart` is the caller's condition, never
    # proof of stored state: under Locking the attempt's own admission confirms
    # it against the row the case state holds, and a temporal row it read
    # whole is the flush's coverage, so no other read follows. Optimistic
    # admission reads nothing.
    counts = _counting_case_state_reads(monkeypatch)
    case = _load_case(case_id)
    compiled, _database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert [emission.sql for emission in compiled] == [
        sql for sql, _binds in write_golden_statements(case)
    ]
    assert counts == reads


def test_a_locking_target_entry_whose_stored_row_moved_is_refused_rather_than_compiled() -> None:
    # The case state knows a Non-Temporal row only as its fixtures stored it, so
    # once an earlier entry may have changed it a Locking confirmation has no
    # row to answer with.
    case = _synthetic_write(
        "writeSequence",
        {
            "given": {"fixtures": True},
            "when": {
                "uow": {"concurrency": "locking"},
                "writeSequence": [
                    {
                        "mutation": "amend",
                        "entity": "parallax.compatibility.Account",
                        "statements": 1,
                        "row": {"id": 1, "balance": "90.00"},
                        "ifVersion": 1,
                    },
                    {
                        "mutation": "amend",
                        "entity": "parallax.compatibility.Account",
                        "statements": 1,
                        "row": {"id": 1, "balance": "80.00"},
                        "ifVersion": 2,
                    },
                ],
            },
        },
    )
    with pytest.raises(EngineError, match="no current account of the row"):
        scenario.compile_write_sequence_case(case, "postgres")


def test_a_write_its_simulated_unit_of_work_refuses_to_admit_is_an_engine_error() -> None:
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/orders.yaml",
            "when": {
                "scenario": [
                    {
                        "write": [
                            {"mutation": "delete", "entity": "OrderItem", "rows": [{"id": 12}]},
                            {
                                "mutation": "amend",
                                "entity": "OrderItem",
                                "rows": [{"id": 12, "sku": "Z"}],
                            },
                        ]
                    }
                ]
            },
        },
    )
    with pytest.raises(EngineError, match="cannot admit this write") as raised:
        scenario.compile_scenario_case(case, "postgres")
    refusal = raised.value.__cause__
    assert isinstance(refusal, WriteEvidenceError)
    assert refusal.code == "write-evidence-already-claimed"


@pytest.mark.parametrize(
    ("failure", "translated"),
    [
        pytest.param(SimulatedStoreError("no one stored row"), True, id="store-diagnostic"),
        pytest.param(RuntimeError("a defect"), False, id="defect"),
        pytest.param(KeyboardInterrupt(), False, id="interruption"),
    ],
)
def test_only_a_simulated_store_diagnostic_becomes_an_engine_error(
    failure: BaseException, translated: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(store: SimulatedTemporalStore, model: object, step: object) -> None:
        raise failure

    monkeypatch.setattr(SimulatedTemporalStore, "apply", failing)
    case = _load_case("m-temporal-write-002")
    if translated:
        with pytest.raises(EngineError, match="no one stored row") as engine_error:
            scenario.compile_write_sequence_case(case, "postgres")
        assert engine_error.value.__cause__ is failure
        return
    with pytest.raises(type(failure)) as raised:
        scenario.compile_write_sequence_case(case, "postgres")
    assert raised.value is failure


def _ledger_unit(port: FakeWritePort) -> tuple[tuple[object, ...], int]:
    case = _synthetic_ledger_scenario([])
    serving = model_facts.case_serving_model(case)
    meta = models.accepted_model_of(serving.current().model)
    context = scenario.CaseContext(serving, meta, "optimistic", {}, TxnOptions())
    entries = cast(
        "list[dict[str, object]]", _ledger_update("300.00", "2024-05-01T00:00:00+00:00")["write"]
    )
    return scenario.execute_keyed_unit(port, context, entries, LifecycleRun(), rollback=False)


def test_a_replayed_ungrouped_write_uses_the_new_attempt_source() -> None:
    first = _ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")
    second = _ledger_row(2, "250.00", in_z="2024-03-01T00:00:00+00:00")
    port = FakeWritePort(read_script=[[first], [second]], affected_script=[0, 1, 1])
    emissions, calls = _ledger_unit(port)
    assert calls == 5
    assert len(emissions) == 3
    assert port.rollbacks == port.commits == 1
    assert port.writes[0][1][-1] == first["in_z"]
    assert port.writes[1][1][-1] == second["in_z"]


def _ledger_find(*, uow: str = "g") -> dict[str, object]:
    return {
        "uow": uow,
        "objectQuery": {
            "target": "parallax.compatibility.Ledger",
            "predicate": {"eq": {"path": "parallax.compatibility.Ledger.id", "value": 2}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        },
    }


def test_a_write_its_public_verb_refuses_never_reaches_the_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The delete and the amendment are both addressed by the one value the
    # group's find published, so production refuses the amendment as already
    # claimed, before either buffered operation reaches the port.
    find = _account_find_step(1)
    write = {
        "uow": "g",
        "write": [
            {"mutation": "delete", "entity": "Account", "rows": [{"id": 1}]},
            {"mutation": "amend", "entity": "Account", "rows": [{"id": 1, "balance": "5.00"}]},
        ],
    }
    case = _synthetic_write(
        "scenario",
        {"when": {"scenario": [find, write]}, "then": {"units": {"g": {"outcome": "committed"}}}},
    )
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    with pytest.raises(WriteEvidenceError) as refused:
        scenario.run_scenario_case(case, port)
    assert refused.value.code == "write-evidence-already-claimed"
    assert port.writes == []


def test_an_amendment_its_public_verb_drops_as_empty_emits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    find = _account_find_step(1)
    write = {
        "uow": "g",
        "write": [
            {"mutation": "delete", "entity": "Account", "rows": [{"id": 1}]},
            {"mutation": "amend", "entity": "Account", "rows": [{"id": 1}]},
        ],
    }
    case = _synthetic_write(
        "scenario",
        {"when": {"scenario": [find, write]}, "then": {"units": {"g": {"outcome": "committed"}}}},
    )
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    run = scenario.run_scenario_case(case, port)
    assert run.database_calls == 2
    assert len(port.writes) == 1 and port.commits == 1
    assert port.writes[0][0].startswith("delete from account")


def test_a_read_step_names_its_own_object_query() -> None:
    with pytest.raises(EngineError, match="needs `objectQuery`"):
        scenario.step_query({"databaseCalls": 1}, models.load_models()["account"])


def test_run_write_sequence_case_executes_each_entry_as_its_own_transaction() -> None:
    # Each writeSequence entry is its
    # OWN `db.transact` unit, never the whole sequence in one transaction.
    port = FakeWritePort()
    emissions, table_state, database_calls = scenario.run_write_sequence_case(
        _case("m-unit-work-003"), port
    )
    assert database_calls == 2
    assert [e.case_pointer for e in emissions] == ["/writeSequence/0", "/writeSequence/1"]
    assert len(port.writes) == 2 and port.commits == 2
    # The committed table state is read back for every model table (the
    # m-conformance-adapter write-sequence observation); the read-back is an
    # observation, so it never counts toward the case's Database Calls.
    assert set(table_state) == {
        "orders",
        "order_item",
        "order_status",
        "order_tag",
        "order_note",
    }


def test_a_run_reports_the_statements_its_database_calls_borrowed() -> None:
    # The run lane plans no second copy of a unit's DML to report: each emission
    # is the very Lowered Statement the delivered Database Call borrowed.
    lifecycle = LifecycleRun()
    emissions, _table_state, _database_calls = scenario.run_write_sequence_case(
        _case("m-unit-work-003"), FakeWritePort(), lifecycle
    )
    delivered = [
        event.statement
        for root in lifecycle.roots
        for event in root.events
        if isinstance(event, DatabaseCallStarted)
    ]
    assert len(emissions) == len(delivered) == 2
    assert all(
        emission.statement is statement
        for emission, statement in zip(emissions, delivered, strict=True)
    )


def test_a_run_grades_an_authored_statement_count_against_what_it_delivered() -> None:
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Account",
                        "statements": 2,
                        "rows": [{"id": 90, "owner": "Noether", "balance": "5.00", "version": 1}],
                    }
                ]
            }
        },
    )
    port = FakeWritePort()
    with pytest.raises(EngineError, match="does not match the 1 statement"):
        scenario.run_write_sequence_case(case, port)
    assert len(port.writes) == 1


def test_run_write_sequence_case_settles_a_temporal_write_against_its_resolving_read() -> None:
    # m-temporal-write-002: the update entry is its own choreography unit, so the
    # milestone it closes comes from the read that unit issues for it — the value
    # `tx.wire.update` is addressed and licensed by — and the Database Calls count
    # that read beside the three DML statements.
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    emissions, table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-002"), port
    )
    assert database_calls == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert len(port.writes) == 3 and port.commits == 2
    assert table_state is not None and "balance" in table_state


def test_a_units_resolving_read_names_no_statement_in_the_lifecycle_observation() -> None:
    """The one call inside a write unit that the emissions do not hold.

    m-temporal-write-002 costs four Database Calls for three golden statements: the
    update entry reads the milestone it closes before writing it. A case counts
    that read and authors no golden for it, so the delivered stream carries a
    Database Call the emission order has no entry for — and the remaining calls
    still name that order in full, which is what makes the omission readable as
    the resolving read rather than as a lost index.
    """
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    run = LifecycleRun()
    emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-002"), port, run
    )
    observed = execution_lifecycle_observation(
        run.roots, [emission.sql for emission in emissions], run.resolving_read_calls
    )
    calls = [
        event["databaseCallStarted"]
        for root in cast("list[dict[str, Any]]", observed["roots"])
        for event in cast("list[dict[str, Any]]", root["events"])
        if "databaseCallStarted" in event
    ]
    assert [(call["kind"], call.get("statement")) for call in calls] == [
        ("write", 0),
        ("read", None),
        ("write", 1),
        ("write", 2),
    ]
    assert database_calls == len(calls)


def test_run_write_sequence_case_buffers_a_bounded_bitemporal_valid_time_window() -> None:
    # m-temporal-write-017: the updateUntil entry's canonical instruction carries
    # BOTH `validFrom` and `until` (its bounded rectangle-split window), which
    # the run lane buffers with that window unchanged.
    port = FakeWritePort(
        find_rows=[
            _position_row(
                1, "100.00", from_z="2024-01-01T00:00:00+00:00", in_z="2024-01-01T00:00:00+00:00"
            )
        ]
    )
    _emissions, table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-017"), port
    )
    assert database_calls == 4
    assert len(port.writes) == 3 and port.commits == 2
    assert table_state is not None and "position" in table_state


def test_compile_write_sequence_case_lowers_each_entry_without_cross_entry_coalescing() -> None:
    # m-unit-work-007 inserts then deletes the same rows across four entries; each entry is
    # its own flush, so it emits FOUR statements (never coalesced to a net-zero cancel).
    emissions, database_calls = scenario.compile_write_sequence_case(
        _case("m-unit-work-007"), "postgres"
    )
    assert database_calls == 4
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
    with pytest.raises(EngineError, match="undeclared member"):
        scenario.compile_scenario_case(bad, "postgres")


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
    with pytest.raises(EngineError, match="undeclared member"):
        scenario.compile_write_sequence_case(bad, "postgres")


# --------------------------------------------------------------------------- #
# The observation-binding discriminator (`scenario._binds_row_observations`) is #
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
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 2
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
    # not the structural guarantee — the observed write itself refuses an insert too.
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
    with pytest.raises(EngineError, match="an insert row authors no `observedVersion`"):
        scenario.compile_write_sequence_case(case, "postgres")


def test_a_write_row_authoring_an_observed_tx_start_is_refused_even_when_versioned() -> None:
    # `observedTxStart` is not a write-row key in any shape: the case schema's
    # `writeRow` reserves `observedVersion` alone, because a temporal write
    # observes a whole predecessor milestone no row cell can name. A versioned
    # target is the case that hides the defect: it HAS an observation, so a
    # refusal that only asks whether the target is observable at all admits the
    # token and then discards it, letting the write advance its version while the
    # Transaction-Time gate the author wrote is silently ignored.
    case = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {
                        "mutation": "amend",
                        "entity": "Account",
                        "statements": 1,
                        "rows": [
                            {
                                "id": 1,
                                "balance": "10.00",
                                "observedVersion": 7,
                                "observedTxStart": "2024-01-01T00:00:00+00:00",
                            }
                        ],
                    }
                ]
            }
        },
    )
    with pytest.raises(EngineError, match="a write row authors no `observedTxStart`"):
        scenario.compile_write_sequence_case(case, "postgres")


def test_an_unversioned_row_authoring_an_observation_control_key_is_refused() -> None:
    # `m-unit-work`: unversioned Non-Temporal writes have no observation, and the
    # case schema's `writeRow` says the same ("absent on ... a non-versioned
    # write") without being able to express it. Accepted, the key would wrap an
    # unversioned Wallet update in an observed write: the planner ignores it
    # (there is no version attribute to advance) but batching still excludes the
    # observed write, so these UNIFORM rows would emit two statements where the same
    # rows without the key collapse to one `IN`-list statement.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "amend",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": "500.00", "observedVersion": 1},
                            {"id": 2, "balance": "500.00", "observedVersion": 1},
                        ],
                    }
                ]
            },
        },
    )
    with pytest.raises(EngineError, match="an unversioned row authors no `observedVersion`"):
        scenario.compile_write_sequence_case(case, "postgres")


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
                        "mutation": "amend",
                        "entity": "Wallet",
                        "statements": 1,
                        "rows": [
                            {"id": 10, "balance": "500.00"},
                            {"id": 11, "balance": "500.00"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 1
    assert [e.sql for e in emissions] == ["update wallet set balance = ? where id in (?, ?)"]
    assert emissions[0].binds == (decimal.Decimal("500.00"), 10, 11)


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
                            {"id": 10, "owner": "Mira", "balance": "100.00"},
                            {"id": 11, "owner": "Omar", "balance": "20.00"},
                        ],
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(case, port)
    assert database_calls == 1
    assert len(port.writes) == 1
    sql, binds = port.writes[0]
    assert sql == "insert into wallet(id, owner, balance) values (%s, %s, %s), (%s, %s, %s)"
    assert binds == [10, "Mira", decimal.Decimal("100.0"), 11, "Omar", decimal.Decimal("20.0")]
    assert isinstance(binds[2], decimal.Decimal) and isinstance(binds[5], decimal.Decimal)


def test_insert_entry_refuses_a_row_missing_a_required_attribute() -> None:
    # Compatibility case preparation delegates insert completeness to the core
    # producer before planning, so an invalid short row never becomes a
    # mixed-shape batch.
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
                            {"id": 10, "owner": "Mira", "balance": "100.00"},
                            {"id": 11, "owner": "Omar"},
                        ],
                    }
                ]
            },
        },
    )
    with pytest.raises(WriteRejectedError, match=r"Wallet\.balance: required attribute"):
        scenario.compile_write_sequence_case(case, "postgres")


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
                        "mutation": "amend",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": "500.00"},
                            {"id": 2, "balance": "500.00"},
                            {"id": 3, "owner": "Zed"},
                            {"id": 4, "owner": "Zed"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 2
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
                        "mutation": "amend",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": "111.00"},
                            {"id": 2, "balance": "222.00"},
                            {"id": 3, "owner": "Zed"},
                            {"id": 4, "owner": "Ada"},
                        ],
                    }
                ]
            },
        },
    )
    with pytest.raises(EngineError, match="does not match the 4 statement"):
        scenario.compile_write_sequence_case(case, "postgres")


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
                        "mutation": "amend",
                        "entity": "Wallet",
                        "statements": 2,
                        "rows": [
                            {"id": 1, "balance": "111.00"},
                            {"id": 2, "balance": "222.00"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 2
    assert [e.sql for e in emissions] == [
        "update wallet set balance = ? where id = ?",
        "update wallet set balance = ? where id = ?",
    ]


def test_pk_gen_managed_insert_rows_stay_their_own_steps_in_one_grouped_insert() -> None:
    # m-pk-gen-008's own shape: a `sequence`-strategy target's rows already
    # carry LITERAL, pre-resolved ids (no `{computed: ...}` marker — the
    # registry-read block reservation resolved them upstream). The ENTITY's
    # own pk-generator strategy, not the row's shape, keeps each row its own
    # single-entry Planned Insert; execution then inserts the rows of distinct
    # objects with one grouped statement.
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/pk-sequence.yaml",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Pass",
                        "statements": 1,
                        "rows": [
                            {"id": 1, "zone": "north"},
                            {"id": 2, "zone": "south"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 1
    assert [e.sql for e in emissions] == ["insert into pass(id, zone) values (?, ?), (?, ?)"]


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
                        "mutation": "amend",
                        "entity": "Account",
                        "statements": 1,
                        "rows": [
                            {"id": 1, "observedVersion": 1},
                            {"id": 2, "balance": "5.00", "observedVersion": 1},
                        ],
                    }
                ]
            }
        },
    )
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 1
    assert [e.sql for e in emissions] == [
        "update account set balance = ?, version = ? where id = ? and version = ?"
    ]
    assert emissions[0].binds == (decimal.Decimal("5.00"), 2, 2, 1)


def test_an_entry_whose_every_row_elides_emits_no_statement() -> None:
    # Every row of the entry is a versioned primary-key-only no-op, so the whole
    # entry elides to NO DML. The derived count is 0, which no authored count can
    # match (`statements` is constrained to at least 1), so an authored count
    # still refuses loudly rather than silently passing on an empty flush.
    rows = [{"id": 1, "observedVersion": 1}, {"id": 2, "observedVersion": 1}]
    silent = _synthetic_write(
        "writeSequence",
        {"when": {"writeSequence": [{"mutation": "amend", "entity": "Account", "rows": rows}]}},
    )
    emissions, database_calls = scenario.compile_write_sequence_case(silent, "postgres")
    assert database_calls == 0
    assert emissions == []
    counted = _synthetic_write(
        "writeSequence",
        {
            "when": {
                "writeSequence": [
                    {"mutation": "amend", "entity": "Account", "statements": 1, "rows": rows}
                ]
            }
        },
    )
    with pytest.raises(EngineError, match="does not match the 0 statement"):
        scenario.compile_write_sequence_case(counted, "postgres")


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
    with pytest.raises(EngineError, match="does not match"):
        scenario.compile_write_sequence_case(case, "postgres")


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
                                    "lessThan": {"path": "Wallet.balance", "value": "200.00"}
                                },
                            },
                        }
                    }
                ]
            },
        },
    )
    emissions, database_calls = scenario.compile_scenario_case(case, "postgres")
    assert database_calls == 1
    assert [e.sql for e in emissions] == ["delete from wallet where balance < ?"]
    assert emissions[0].binds == (decimal.Decimal("200.00"),)


@pytest.mark.parametrize("lane", ["compile", "run"])
def test_predicate_shaped_write_sequence_entry_refuses_loudly(lane: str) -> None:
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
                            "predicate": {
                                "lessThan": {"path": "Wallet.balance", "value": "200.00"}
                            },
                        },
                    }
                ]
            },
        },
    )
    with pytest.raises(EngineError, match=r"scenario-write-only"):
        if lane == "compile":
            scenario.compile_write_sequence_case(case, "postgres")
        else:
            scenario.run_write_sequence_case(case, FakeWritePort())


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
                                    "lessThan": {"path": "Wallet.balance", "value": "200.00"}
                                },
                            },
                        }
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    run = scenario.run_scenario_case(case, port)
    assert run.database_calls == 1
    assert run.emissions[0].case_pointer == "/scenario/0/write"
    assert run.emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1 and port.commits == 1


def test_run_scenario_case_executes_a_readless_predicate_replacement() -> None:
    # The case's own row reaches `tx.wire.replace_where`, which completes it and
    # never writes the key it states.
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/wallet.yaml",
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "replace",
                            "target": {
                                "entity": "Wallet",
                                "predicate": {
                                    "lessThan": {"path": "Wallet.balance", "value": "200.00"}
                                },
                            },
                            "row": {"id": 9, "balance": "1.00", "owner": "Ada"},
                        }
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    run = scenario.run_scenario_case(case, port)
    assert run.database_calls == 1
    assert run.emissions[0].sql == "update wallet set owner = ?, balance = ? where balance < ?"
    assert len(port.writes) == 1 and port.commits == 1


def test_run_scenario_case_readless_predicate_write_rollback_aborts_but_counts_the_call() -> None:
    # `_run_readless_predicate_write`'s own abort contract mirrors the keyed-
    # write one (`test_run_scenario_case_rollback_step_aborts_but_counts_the_
    # database_call`): the golden DML still executes (and counts its Database Call)
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
                                    "lessThan": {"path": "Wallet.balance", "value": "200.00"}
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
    run = scenario.run_scenario_case(case, port)
    assert run.database_calls == 1
    assert run.emissions[0].sql == "delete from wallet where balance < ?"
    assert len(port.writes) == 1
    assert port.commits == 0 and port.rollbacks == 1


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
    with pytest.raises(EngineError, match="Ghost"):
        scenario.run_write_sequence_case(case, port)


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
_ACCOUNT_ROW_2: Final[MappingRow] = {
    "id": 2,
    "owner": "Linus",
    "balance": decimal.Decimal("250.00"),
    "version": 1,
}


def test_run_conflict_case_single_attempt() -> None:
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, table_state, _database_calls = scenario.run_conflict_case(
        _load_case("m-opt-lock-006"), port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "account" in table_state


@pytest.mark.parametrize(
    ("case_id", "mutation", "attempt"),
    [
        ("m-opt-lock-006", "amend", None),
        ("m-opt-lock-006", "delete", None),
        ("m-opt-lock-009", "amend", 1),
    ],
    ids=["amend", "delete", "later-retry"],
)
def test_a_versioned_conflict_attempt_requires_its_declared_version(
    case_id: str, mutation: str, attempt: int | None
) -> None:
    case = _own_copy(_load_case(case_id))
    when = cast("dict[str, Any]", case.document["when"])
    when["mutation"] = mutation
    row = when["write"] if attempt is None else when["attempts"][attempt]["write"]
    del row["observedVersion"]
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(EngineError, match=r"every versioned conflict write.*`observedVersion`"):
        scenario.run_conflict_case(case, port)
    assert port.reads == port.writes == []


@pytest.mark.parametrize("mutation", ["amend", "delete"])
def test_every_row_of_a_versioned_conflict_attempt_requires_its_declared_version(
    mutation: str,
) -> None:
    case = _own_copy(_load_case("m-opt-lock-006"))
    when = cast("dict[str, Any]", case.document["when"])
    when["mutation"] = mutation
    when["write"] = [when["write"], {"id": 3, "balance": "20.00"}]
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(EngineError, match=r"every versioned conflict write.*`observedVersion`"):
        scenario.run_conflict_case(case, port)
    assert port.reads == port.writes == []


def test_conflict_submissions_never_prepare_or_simulate_a_peer_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("conflict submission entered compile machinery")

    monkeypatch.setattr(SimulatedTemporalStore, "__init__", refuse)
    monkeypatch.setattr(_case_ingress, "prepare_case_write", refuse)
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, _table_state, database_calls = scenario.run_conflict_case(
        _load_case("m-opt-lock-006"), port
    )
    assert affected == 1 and database_calls == 2
    assert len(port.reads) == 2 and len(port.writes) == 1
    assert emissions[0].sql == (
        "update account set balance = ?, version = ? where id = ? and version = ?"
    )


def test_a_conflict_attempt_counts_duplicate_addressed_keys_once() -> None:
    case = _synthetic_write(
        "conflict",
        {
            "when": {
                "uow": {"concurrency": "optimistic", "maxRetries": 0},
                "write": [
                    {"id": 2, "owner": "Ada", "observedVersion": 1},
                    {"id": 2, "balance": "500.00", "observedVersion": 1},
                ],
            }
        },
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, _table_state, database_calls = scenario.run_conflict_case(case, port)
    assert affected == 1 and database_calls == 2
    assert len(emissions) == len(port.reads) == len(port.writes) == 1
    assert port.writes[0][1] == ["Ada", decimal.Decimal("500.00"), 2, 2, 1]


def test_run_conflict_case_reads_its_source_before_applying_given_apply() -> None:
    # The concurrent writer commits BETWEEN the source read and the write it
    # invalidates: a read taken after it would observe the state it left, and
    # the stale gate the case grades would never be reachable.
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, table_state, _database_calls = scenario.run_conflict_case(
        _load_case("m-opt-lock-005"), port
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


# The DRIVER spellings of the golden writes a fake port reports a zero-row
# shortfall for: a concurrent writer already moved or removed the row.
_ACCOUNT_WRITE_SHORTFALL: Final[tuple[str, ...]] = (
    "update account set balance = %s",
    "delete from account",
)


def test_run_conflict_case_renders_a_gated_zero_row_update_as_a_conflict() -> None:
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2], zero_affected_for=_ACCOUNT_WRITE_SHORTFALL)
    _emissions, affected, _table_state, _database_calls = scenario.run_conflict_case(
        _load_case("m-opt-lock-005"), port
    )
    assert affected == 0


def test_a_conflict_attempt_whose_source_read_finds_no_row_is_refused() -> None:
    # A target `given.apply` already removed leaves the attempt with no value to
    # write, so a case authoring that state is unauthorable through the public
    # verbs rather than merely unpleasant.
    port = FakeWritePort(find_rows=[])
    with pytest.raises(EngineError, match="which no read of its own choreography unit published"):
        scenario.run_conflict_case(_load_case("m-opt-lock-006"), port)


def test_a_conflict_attempt_declaring_a_version_its_read_did_not_observe_is_refused() -> None:
    # The declared `observedVersion` renders the golden's gate bind while the
    # real write settles against what the read saw, so the two must name one
    # state or the case grades a statement no read of this lane produced.
    port = FakeWritePort(find_rows=[{**_ACCOUNT_ROW_2, "version": 7}])
    with pytest.raises(EngineError, match="its resolved source observed 7"):
        scenario.run_conflict_case(_load_case("m-opt-lock-005"), port)
    assert len(port.reads) == 1 and port.writes == []


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
    emissions, affected, _table_state, _database_calls = scenario.run_conflict_case(case, port)
    assert [e.sql for e in emissions] == ["delete from account where id = ? and version = ?"]
    assert affected == 1


def _unversioned_conflict_case(rows: list[dict[str, object]]) -> case_format.Case:
    return _synthetic_write(
        "conflict",
        {
            "model": "models/wallet.yaml",
            "when": {"uow": {"concurrency": "optimistic"}, "mutation": "amend", "write": rows},
        },
    )


def test_a_conflict_attempt_row_authoring_an_unobservable_observed_version_is_refused() -> None:
    # A conflict attempt authors its `write` rows in the same `writeRow`
    # vocabulary a writeSequence entry does, so the licensing rule that entitles
    # exactly a versioned Non-Temporal update or delete to name an observed
    # version is the same one, and it is refused before any read runs.
    case = _unversioned_conflict_case(
        [
            {"id": 1, "balance": "500.00", "observedVersion": 1},
            {"id": 2, "balance": "500.00", "observedVersion": 1},
        ]
    )
    with pytest.raises(EngineError, match="an unversioned row authors no `observedVersion`"):
        scenario.run_conflict_case(case, FakeWritePort())


@pytest.mark.parametrize(
    "case",
    [
        _unversioned_conflict_case([{"id": 1, "balance": "500.00"}]),
        _synthetic_write(
            "conflict",
            {
                "when": {
                    "uow": {"concurrency": "locking"},
                    "write": {"id": 2, "balance": "500.00", "observedVersion": 1},
                }
            },
        ),
    ],
    ids=["unversioned", "locking-preference"],
)
def test_a_locking_conflict_target_is_refused_before_any_read(case: case_format.Case) -> None:
    # The lane reads its source inside the attempt, and under the Locking strategy
    # that read holds the shared row lock the staged concurrent writer would wait
    # on, so a Locking conflict case describes interference no client can meet. An
    # unversioned Non-Temporal target is Locking under either preference.
    port = FakeWritePort()
    with pytest.raises(EngineError, match="only the Optimistic strategy leaves room for"):
        scenario.run_conflict_case(case, port)
    assert port.reads == []
    assert port.writes == []


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
            scenario._implied_shortfall_error(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                True, "optimistic", models.load_models()["account"], _ACCOUNT
            )
            is OptimisticLockConflictError
        )

    def test_a_locking_strategy_implies_the_non_retriable_stale_write(self) -> None:
        from parallax.conformance import models

        assert (
            scenario._implied_shortfall_error(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
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
            scenario._implied_shortfall_error(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                False, concurrency, models.load_models()["account"], _ACCOUNT
            )
            is MissingTargetError
        )

    def test_a_gated_shortfall_admitted_as_a_stale_write_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(scenario, "_implied_shortfall_error", _always_implying(StaleWriteError))
        with pytest.raises(OptimisticLockConflictError):
            scenario.run_conflict_case(
                _load_case("m-opt-lock-005"),
                FakeWritePort([_ACCOUNT_ROW_2], zero_affected_for=_ACCOUNT_WRITE_SHORTFALL),
            )


def test_run_conflict_case_refuses_a_temporal_target_before_any_read() -> None:
    # The conflict shape is non-temporal: a temporal write's race is an
    # interleaved scenario, graded on what each group's own reads observed. A
    # temporal target is refused before the lane's source read or `given.apply`
    # touches the database.
    case = case_format.Case(
        path=Path("m-unit-work-999-synthetic.yaml"),
        case_id="m-unit-work-999",
        shape="conflict",
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/balance.yaml",
        document={"model": "models/balance.yaml", "when": {"write": {"id": 1}}},
    )
    port = FakeWritePort()
    with pytest.raises(EngineError, match="targets a non-temporal Entity"):
        scenario.run_conflict_case(case, port)
    assert port.reads == []
    assert port.writes == []


_ACCOUNT_ROW_2_REVISED: Final[MappingRow] = {
    **_ACCOUNT_ROW_2,
    "balance": decimal.Decimal("999.00"),
    "version": 2,
}


def test_run_conflict_case_attempts_form_is_productions_own_replay() -> None:
    # One invocation runs every authored attempt: the first attempt's gated
    # write comes up short, production replays the callback, and the replay
    # takes its OWN source read, observing the generation the concurrent writer
    # left rather than reusing the stale one the first attempt settled against.
    port = FakeWritePort(
        read_script=[[_ACCOUNT_ROW_2], [_ACCOUNT_ROW_2_REVISED]], affected_script=[0, 1]
    )
    emissions, affected, table_state, database_calls = scenario.run_conflict_case(
        _load_case("m-opt-lock-009"), port
    )
    assert [e.case_pointer for e in emissions] == [
        "/when/attempts/0/write",
        "/when/attempts/1/write",
    ]
    assert [binds for _sql, binds in port.writes[1:]] == [
        [decimal.Decimal("275.00"), 2, 2, 1],
        [decimal.Decimal("275.00"), 3, 2, 2],
    ]
    assert len(port.writes) == 3  # given.apply + the gated write of each attempt
    assert (port.rollbacks, port.commits) == (1, 1)
    assert affected == 1
    assert database_calls == 4
    assert table_state is not None


def test_a_conflict_case_production_replays_past_its_last_attempt_is_refused() -> None:
    # Under a positive bound production replays the single authored attempt's
    # conflict, which the case never described: the replay is refused inside
    # the callback rather than graded against the first attempt's statements.
    case = _rooted(_load_case("m-opt-lock-005"), uow={"concurrency": "optimistic"}, root={})
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2], zero_affected_for=_ACCOUNT_WRITE_SHORTFALL)
    with pytest.raises(EngineError, match="replayed the conflict case's last authored attempt"):
        scenario.run_conflict_case(case, port)
    assert len(port.levels) == 2


def test_a_conflict_case_whose_invocation_ends_before_its_last_attempt_is_refused() -> None:
    port = FakeWritePort(read_script=[[_ACCOUNT_ROW_2]], affected_script=[1])
    with pytest.raises(EngineError, match=r"after 1 attempt\(s\), and the case authors 2"):
        scenario.run_conflict_case(_load_case("m-opt-lock-009"), port)


@pytest.mark.parametrize(
    ("uow", "root"),
    [
        ({"concurrency": "optimistic", "maxRetries": 0}, {}),
        ({"concurrency": "optimistic"}, {"maxRetries": 0}),
    ],
    ids=["requested", "root"],
)
def test_a_conflict_case_whose_bound_admits_fewer_attempts_than_it_authors_is_refused(
    uow: dict[str, object], root: dict[str, object]
) -> None:
    case = _rooted(_load_case("m-opt-lock-009"), uow=uow, root=root)
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(EngineError, match=r"authors 2 attempts and its transaction resolves"):
        scenario.run_conflict_case(case, port)
    assert port.levels == []


def test_run_conflict_case_wraps_a_lowering_failure_as_engine_error() -> None:
    case = _synthetic_write(
        "conflict", {"when": {"write": {"id": 2, "bogus": True, "observedVersion": 1}}}
    )
    with pytest.raises(EngineError, match="undeclared member"):
        scenario.run_conflict_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW_2]))


def test_a_projected_row_rejects_an_ambiguous_member() -> None:
    model = models.load_models()["document-codec"]
    entity = model.entities[0]
    first, second = entity.declared_attributes[:2]
    columns = {"ambiguous": (("first", first), ("second", second))}

    with pytest.raises(EngineError, match="does not select one declaration"):
        scenario._projected_row(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            model,
            ActualWireProjection(model),
            columns,
            None,
            {"ambiguous": 1},
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
                        "mutation": "amend",
                        "entity": "Balance",
                        "statements": 2,
                        "rows": [{"id": 2, "value": 100.00, "observedVersion": 7}],
                    }
                ]
            },
        },
    )
    with pytest.raises(EngineError, match=re.escape("a temporal row authors no")):
        scenario.compile_write_sequence_case(case, "postgres")


def test_a_multi_row_temporal_write_sequence_entry_is_refused() -> None:
    # The row-count axis of the same seam. `rows` is a schema-valid array of one
    # or more at every authoring location, and a temporal entity's row count is
    # not something the shared definition can constrain (it depends on the
    # model), so a plural temporal entry reaches this scenario. It settles one
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
                        "mutation": "amend",
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
    with pytest.raises(EngineError, match=re.escape("a temporal write entry carries ONE")):
        scenario.compile_write_sequence_case(case, "postgres")


def test_a_multi_row_temporal_scenario_write_entry_is_refused() -> None:
    # The same refusal for the other shape that reaches the temporal producer: a
    # buffered scenario write entry, whose rows a unit of work would hold rather
    # than a writeSequence's ordered DML.
    when = {
        "scenario": [
            {
                "write": [
                    {
                        "mutation": "amend",
                        "entity": "Balance",
                        "rows": [
                            {"id": 1, "acctNum": "A", "value": 175.00},
                            {"id": 2, "acctNum": "B", "value": 999.00},
                        ],
                        "at": "2024-09-01T00:00:00+00:00",
                    }
                ],
                "databaseCalls": 2,
            }
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/balance.yaml", "when": when})
    with pytest.raises(EngineError, match=re.escape("a temporal write entry carries ONE")):
        scenario.compile_scenario_case(case, "postgres")


def test_scenario_case_without_when_is_rejected() -> None:
    with pytest.raises(EngineError, match="has no `when`"):
        scenario.compile_scenario_case(_synthetic_write("scenario", {}), "postgres")


def test_scenario_case_without_a_scenario_list_is_rejected() -> None:
    with pytest.raises(EngineError, match=r"when\.scenario"):
        scenario.compile_scenario_case(_synthetic_write("scenario", {"when": {}}), "postgres")


def test_scenario_read_step_missing_its_query_is_rejected() -> None:
    bad = _synthetic_write("scenario", {"when": {"scenario": [{"databaseCalls": 1}]}})
    with pytest.raises(EngineError, match="objectQuery"):
        scenario.compile_scenario_case(bad, "postgres")


def test_write_sequence_case_without_a_sequence_list_is_rejected() -> None:
    with pytest.raises(EngineError, match="writeSequence"):
        scenario.compile_write_sequence_case(
            _synthetic_write("writeSequence", {"when": {}}), "postgres"
        )


def test_read_table_state_reads_each_physical_table_once_over_every_slot() -> None:
    # Payment's abstract root owns the shared table; descendants carry no local
    # table. The one read projects the layout's complete slot sequence, so a
    # CardPayment row still reports the sibling-only `tendered` column.
    from parallax.conformance import models

    port = FakeWritePort()
    meta = models.load_models()["payment"]
    state = scenario.read_table_state(port, meta)
    assert set(state) == {"payment"}
    assert len(port.reads) == 1
    sql, _ = port.reads[0]
    assert sql == "select id, kind, amount, card_network, tendered from payment"


def test_read_table_state_reads_each_tpcs_concrete_table() -> None:
    from parallax.conformance import models

    port = FakeWritePort()
    meta = models.load_models()["document"]
    state = scenario.read_table_state(port, meta)
    assert set(state) == {"invoice", "receipt", "memo", "folder"}
    assert len(port.reads) == 4


def test_read_table_state_projects_value_object_document_columns_last() -> None:
    # A document slot follows every scalar tier (m-storage-layout), even for a
    # plain non-inheritance entity — the customer model's `address`.
    from parallax.conformance import models

    port = FakeWritePort()
    meta = models.load_models()["customer"]
    state = scenario.read_table_state(port, meta)
    assert "customer" in state
    sql, _ = port.reads[0]
    assert sql == "select id, name, address from customer"


def test_table_state_projects_sibling_document_paths_from_the_row_variant() -> None:
    from parallax.core import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.view(meta).tables
        if candidate.table.name == "payment_document"
    )
    projection = ActualWireProjection(meta)

    card = projection.table_row(
        layout,
        {"id": 1, "kind": "card", "payload": {"detail": "visa-4242"}},
    )
    cash = projection.table_row(
        layout,
        {
            "id": 2,
            "kind": "cash",
            "payload": {"detail": "12.50", "future": None},
        },
    )

    assert card["payload"] == {"detail": "visa-4242"}
    assert cash["payload"] == {"detail": "12.50", "future": None}


def test_table_state_preserves_non_document_relational_payloads() -> None:
    from parallax.core import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.view(meta).tables
        if candidate.table.name == "payment_document"
    )

    projected = ActualWireProjection(meta).table_row(
        layout, {"id": 1, "kind": "card", "payload": "corrupt"}
    )

    assert projected["payload"] == "corrupt"
    assert (
        ActualWireProjection(meta).table_row(layout, {"id": 1, "kind": "card", "payload": None})[
            "payload"
        ]
        is None
    )


def test_table_state_requires_a_known_variant_for_ambiguous_document_members() -> None:
    from parallax.core import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.view(meta).tables
        if candidate.table.name == "payment_document"
    )

    with pytest.raises(ValueError, match="row does not identify"):
        ActualWireProjection(meta).table_row(
            layout,
            {"id": 1, "kind": "unknown", "payload": {"detail": "ambiguous"}},
        )

    projected = ActualWireProjection(meta).table_row(
        layout,
        {"id": 2, "kind": "cash", "payload": {"detail": None}},
    )
    assert projected["payload"] == {"detail": None}


def test_table_state_preserves_malformed_declared_relational_document_leaves() -> None:
    from parallax.core import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.view(meta).tables
        if candidate.table.name == "payment_document"
    )

    projected = ActualWireProjection(meta).table_row(
        layout,
        {
            "id": 2,
            "kind": "cash",
            "payload": {"detail": "12.5", "future": None},
        },
    )

    assert projected["payload"] == {"detail": "12.5", "future": None}


def test_table_state_validates_direct_value_objects_as_stored_wire_documents() -> None:
    from parallax.core import storage_layout

    meta = models.load_models()["document-codec"]
    (layout,) = storage_layout.view(meta).tables

    projected = ActualWireProjection(meta).table_row(
        layout,
        {
            "id": 1,
            "label": "sample",
            "profile": {"amount": "12.50", "future": None},
        },
    )

    assert projected["profile"] == {"amount": "12.50", "future": None}


def test_table_state_preserves_malformed_direct_value_object_leaves() -> None:
    from parallax.core import storage_layout

    meta = models.load_models()["document-codec"]
    (layout,) = storage_layout.view(meta).tables

    projected = ActualWireProjection(meta).table_row(
        layout,
        {
            "id": 1,
            "label": "sample",
            "profile": {"amount": "12.5", "future": None},
        },
    )

    assert projected["profile"] == {"amount": "12.5", "future": None}


def test_read_table_state_normalizes_values_without_changing_the_projection() -> None:
    # Value normalization is the wire encoder's own concern; the projection is the
    # layout's slot sequence and nothing re-resolves a physical column to reach it.
    import datetime as dt

    from parallax.conformance import models

    instant = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = FakeWritePort(
        find_rows=[{"bal_id": 1, "acct_num": "A", "val": decimal.Decimal("1.00"), "in_z": instant}]
    )
    meta = models.load_models()["balance"]
    state = scenario.read_table_state(port, meta)
    (row,) = state["balance"]
    assert row["in_z"] == "2024-01-01T00:00:00.000000Z"
    sql, _ = port.reads[0]
    assert sql == "select bal_id, acct_num, val, in_z, out_z from balance"


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
    run = scenario.run_scenario_case(_case("m-unit-work-026"), port)
    assert run.database_calls == 3  # the step's own read + its one DELETE + the dependent find
    assert next(sql for sql, _binds in port.reads) == (
        "select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on"
        " from order_item t0 where t0.id in (%s) for share of t0"
    )
    assert [sql for sql, _binds in port.writes] == ["delete from order_item where id = %s"]


def test_a_temporal_terminate_entry_reaches_its_own_wire_verb() -> None:
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-003"), port
    )
    assert database_calls == 3  # insert, then the terminate entry's own read + its close
    assert port.writes[-1][0].startswith("update balance set out_z")


def test_a_bounded_bitemporal_terminate_entry_reaches_its_own_wire_verb() -> None:
    port = FakeWritePort(
        find_rows=[
            _position_row(
                1, "100.00", from_z="2024-01-01T00:00:00+00:00", in_z="2024-01-01T00:00:00+00:00"
            )
        ]
    )
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-018"), port
    )
    assert database_calls == 4  # three statements plus the terminateUntil entry's own read
    assert port.writes[1][0].startswith("update position set out_z")


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
                        "mutation": "amend",
                        "entity": "parallax.compatibility.Ledger",
                        "rows": [{"id": 9, "value": decimal.Decimal("150.00")}],
                        "at": "2025-01-01T00:00:00+00:00",
                    },
                ],
                "databaseCalls": 1,
            }
        ]
    )
    port = FakeWritePort()
    scenario.run_scenario_case(case, port)
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
                    "predicate": {"eq": {"path": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
                "databaseCalls": 1,
            },
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00", uow="g"),
        ]
    )
    with pytest.raises(EngineError, match="which no read of its own choreography unit"):
        scenario.run_scenario_case(case, FakeWritePort())


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
                            "predicate": {"eq": {"path": "Account.id", "value": 1}},
                        },
                        "databaseCalls": 1,
                    },
                    {
                        "uow": "g",
                        "write": [
                            {
                                "on": 0,
                                "mutation": "amend",
                                "entity": "Account",
                                "rows": [{"id": 1, "balance": "5.00", "observedVersion": 1}],
                            }
                        ],
                        "databaseCalls": 1,
                    },
                ]
            }
        },
    )
    with pytest.raises(EngineError, match="published 0 rows"):
        scenario.run_scenario_case(case, FakeWritePort())


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
                    "predicate": {"eq": {"path": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
                "databaseCalls": 1,
            },
            {
                "uow": "g",
                "objectQuery": {
                    "target": "parallax.compatibility.Ledger",
                    "predicate": {"eq": {"path": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {
                        "transaction-time": {"asOf": "2024-03-01T00:00:00.000000Z"},
                    },
                },
                "databaseCalls": 1,
            },
            _ledger_update("300.00", "2026-02-01T00:00:00+00:00", uow="g"),
        ]
    )
    port = FakeWritePort(find_rows=[_ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")])
    scenario.run_scenario_case(case, port)
    assert next(sql for sql, _binds in port.writes).startswith("update ledger set out_z")


def _synthetic_scenario(
    model: str, case_id: str, steps: list[dict[str, object]]
) -> case_format.Case:
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
                        "mutation": "amend",
                        "entity": "OrderItem",
                        "rows": [{"id": 21, "quantity": 9}],
                    },
                    {
                        "mutation": "delete",
                        "entity": "parallax.compatibility.OrderItem",
                        "rows": [{"id": 22}],
                    },
                ],
                "databaseCalls": 3,
            }
        ],
    )
    scenario.run_scenario_case(case, port)
    assert len(port.reads) == 1
    assert port.reads[0][0].endswith("where t0.id in (%s, %s) for share of t0")


def _registry_advance(sequence: str) -> dict[str, object]:
    return {
        "mutation": "amend",
        "entity": "parallax.compatibility.PkSequence",
        "rows": [{"name": sequence, "nextVal": {"increment": 1}}],
    }


@pytest.mark.parametrize("rollback", [False, True])
def test_marker_generation_and_execution_do_not_access_case_state(
    monkeypatch: pytest.MonkeyPatch, rollback: bool
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("marker lowering accessed simulated state")

    monkeypatch.setattr(scenario, "_resolve_entries", refuse)
    for name in ("transaction", "acquisition", "predecessor_for", "apply"):
        monkeypatch.setattr(SimulatedTemporalStore, name, refuse)
    case = _synthetic_scenario(
        "models/pk-sequence.yaml", "m-pk-gen-998", [_pk_sequence_advance(rollback=rollback)]
    )
    compiled, compile_calls = scenario.compile_scenario_case(case, "postgres")
    port = FakeWritePort()
    run = scenario.run_scenario_case(case, port)

    assert compiled == run.emissions
    assert port.writes == [(item.sql.replace("?", "%s"), list(item.binds)) for item in compiled]
    assert compile_calls == run.database_calls == 1
    assert port.reads == []
    assert (port.commits, port.rollbacks) == ((0, 1) if rollback else (1, 0))


def test_max_marker_compile_and_run_share_store_free_lowering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("max marker accessed simulated state")

    monkeypatch.setattr(scenario, "_resolve_entries", refuse)
    for name in ("transaction", "acquisition", "predecessor_for", "apply"):
        monkeypatch.setattr(SimulatedTemporalStore, name, refuse)
    case = _case("m-pk-gen-001")
    compiled, compile_calls = scenario.compile_write_sequence_case(case, "postgres")
    port = FakeWritePort()
    ran, _table_state, run_calls = scenario.run_write_sequence_case(case, port)

    assert compiled == ran
    assert port.writes == [(item.sql.replace("?", "%s"), list(item.binds)) for item in compiled]
    assert compile_calls == run_calls == 1


def test_store_free_composition_refuses_actual_row_acquisition() -> None:
    model = models.load_models()["account"]
    target = instructions.deserialize(
        {
            "mutation": "amend",
            "entity": "parallax.compatibility.Account",
            "row": {"id": 7, "balance": "5.00"},
            "ifVersion": 1,
        }
    )

    with pytest.raises(
        EngineError, match="store-free framework marker lowering cannot acquire rows"
    ):
        scenario._lower_marker_unit(  # pyright: ignore[reportPrivateUsage] - exercise the no-store composition
            target, model, POSTGRES, "locking", scenario.INERT_CLOCK_INSTANT
        )


@pytest.mark.parametrize("kind", ["mixed", "multiple", "grouped", "multiple-rows"])
def test_marker_composition_is_refused_before_resolution_or_execution(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("invalid marker composition reached predecessor resolution")

    monkeypatch.setattr(scenario, "_resolve_entries", refuse)
    marker = _registry_advance("badge_seq")
    writes = [marker]
    if kind == "mixed":
        writes.append(
            {"mutation": "insert", "entity": "Badge", "rows": [{"id": 1, "holder": "Bo"}]}
        )
    elif kind == "multiple":
        writes.append(_registry_advance("ticket_seq"))
    elif kind == "multiple-rows":
        marker["rows"] = [
            {"name": "badge_seq", "nextVal": {"increment": 1}},
            {"name": "ticket_seq", "nextVal": {"increment": 1}},
        ]
    step: dict[str, object] = {"write": writes, "databaseCalls": 2}
    if kind == "grouped":
        step["uow"] = "g"
    case = _synthetic_scenario("models/pk-sequence.yaml", "m-pk-gen-999", [step])
    refusal = "never both|buffer's only entry|choreography unit of its own"
    with pytest.raises(EngineError, match=refusal):
        scenario.compile_scenario_case(case, "postgres")
    port = FakeWritePort()
    with pytest.raises(EngineError, match=refusal):
        scenario.run_scenario_case(case, port)
    assert port.writes == []
    assert port.reads == []


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
                "databaseCalls": 2,
            }
        ],
    )
    with pytest.raises(EngineError, match="never both"):
        scenario.run_scenario_case(case, FakeWritePort())


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
                "databaseCalls": 2,
            }
        ],
    )
    with pytest.raises(EngineError, match="buffer's only entry"):
        scenario.run_scenario_case(case, FakeWritePort())


def _pk_sequence_advance(**step: object) -> dict[str, object]:
    return {"write": [_registry_advance("badge_seq")], "databaseCalls": 1, **step}


def test_an_aborted_framework_write_step_executes_its_dml_and_rolls_back() -> None:
    # A registry advance runs through the planner rather than a verb, but it is
    # still a whole choreography unit and answers to the same abort contract: the
    # statement reaches the wire and counts its Database Call, and the provider then
    # rolls it back. Committing it would leave a `rollback: true` step's DML
    # durable, which is the one thing the step declares it is not.
    port = FakeWritePort()
    run = scenario.run_scenario_case(
        _synthetic_scenario(
            "models/pk-sequence.yaml", "m-pk-gen-998", [_pk_sequence_advance(rollback=True)]
        ),
        port,
    )
    assert run.database_calls == 1
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
    with pytest.raises(EngineError, match="choreography unit of its own"):
        scenario.run_scenario_case(case, FakeWritePort())


# --------------------------------------------------------------------------- #
# Root configuration (m-case-format *Root configuration*): every Handle a      #
# scenario lane composes for the case's own units of work is connected with    #
# the record `given.databaseOptions` states, and every transaction it opens     #
# resolves what the request omits against that record — the held `uow` group,  #
# the ungrouped keyed unit, the ungrouped find, the readless predicate write,  #
# and the writeSequence entry alike.                                           #
# --------------------------------------------------------------------------- #
_CONSPICUOUS_ROOT: Final[dict[str, object]] = {
    "maxRetries": 0,
    "concurrency": "locking",
    "isolation": "serializable",
}


def _rooted(
    case: case_format.Case,
    *,
    uow: dict[str, object] | None = None,
    root: Mapping[str, object] = _CONSPICUOUS_ROOT,
) -> case_format.Case:
    """``case`` under ``root`` — by default the conspicuous root, every field
    away from its built-in — with `when.uow` replaced by ``uow`` (dropped when
    ``None``)."""
    document = dict(case.document)
    given = cast("Mapping[str, Any]", document.get("given") or {})
    document["given"] = {**given, "databaseOptions": dict(root)}
    when = {k: v for k, v in cast("Mapping[str, Any]", document["when"]).items() if k != "uow"}
    document["when"] = when if uow is None else {**when, "uow": uow}
    return dataclasses.replace(case, document=document)


def test_a_held_uow_group_opens_at_the_roots_level_and_plans_under_the_roots_preference() -> None:
    # m-unit-work-005's three-step group is ONE transaction; under a locking,
    # Serializable root that requests nothing it opens at Serializable, and the
    # find inside it renders the shared-lock suffix the resolved preference
    # calls for, while the versioned update is ungated — the planning value and
    # the executed request agree because both come from the same root.
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    run = scenario.run_scenario_case(_rooted(_case("m-unit-work-005")), port)
    assert port.levels == ["serializable"]
    assert run.emissions[0].sql.endswith("for share of t0")
    assert run.emissions[1].sql == "update account set balance = ?, version = ? where id = ?"


def test_an_authored_request_overrides_the_root_for_the_group_it_names() -> None:
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    run = scenario.run_scenario_case(
        _rooted(
            _case("m-unit-work-005"),
            uow={"concurrency": "optimistic", "isolation": "read-committed"},
        ),
        port,
    )
    assert port.levels == ["read_committed"]
    assert not run.emissions[0].sql.endswith("for share of t0")


def test_an_ungrouped_keyed_unit_and_an_ungrouped_find_each_open_at_the_roots_level() -> None:
    # m-unit-work-001: an ungrouped insert unit and an ungrouped dependent find,
    # each its own transaction, each resolved against the root this lane
    # connected — two boundaries, both at the root's Serializable, and the find
    # locking under the root's preference.
    port = FakeWritePort(
        find_rows=[{"id": 7, "owner": "Newton", "balance": decimal.Decimal("5.00"), "version": 1}]
    )
    run = scenario.run_scenario_case(_rooted(_case("m-unit-work-001")), port)
    assert port.levels == ["serializable", "serializable"]
    assert run.emissions[1].sql.endswith("for share of t0")


def test_a_readless_predicate_write_opens_at_the_roots_level() -> None:
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/wallet.yaml",
            "given": {"databaseOptions": dict(_CONSPICUOUS_ROOT)},
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Wallet",
                                "predicate": {
                                    "lessThan": {"path": "Wallet.balance", "value": "200.00"}
                                },
                            },
                        }
                    }
                ]
            },
        },
    )
    port = FakeWritePort()
    scenario.run_scenario_case(case, port)
    assert port.levels == ["serializable"]


def test_a_write_sequence_entry_opens_at_the_roots_level() -> None:
    port = FakeWritePort()
    scenario.run_write_sequence_case(_rooted(_case("m-unit-work-003")), port)
    assert port.levels
    assert set(port.levels) == {"serializable"}


def test_the_case_context_carries_the_root_record_beside_the_sparse_request() -> None:
    # The two travel apart: the record is the whole root, the request only what
    # `when.uow` authored, and the planning preference is what the two resolve
    # to — so neither seam can be fed the other's value.
    case = _rooted(_case("m-unit-work-001"), uow={"maxRetries": 3})
    serving = model_facts.case_serving_model(case)
    context = scenario.CaseContext(
        serving,
        models.accepted_model_of(serving.current().model),
        case_document.concurrency(case),
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    assert context.options == TxnOptions(
        max_retries=0,
        concurrency="locking",
        isolation="serializable",
    )
    assert context.requests == {"max_retries": 3}
    assert context.concurrency == "locking"


def test_a_conflict_attempt_opens_at_the_roots_level_and_runs_under_its_bound() -> None:
    # The conflict lane connects its Handle with the case's root, so a root
    # level and bound govern the attempts exactly as authored ones do: one
    # production attempt at the root's level under the optimistic preference
    # the request authors.
    case = _rooted(_load_case("m-opt-lock-006"), uow={"concurrency": "optimistic"})
    assert case_format.database_options(case) == TxnOptions(
        max_retries=0,
        concurrency="locking",
        isolation="serializable",
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    scenario.run_conflict_case(case, port)
    assert port.levels == ["serializable"]
    assert len(port.writes) == 1


@pytest.mark.parametrize(
    ("uow", "root", "level"),
    [
        ({"concurrency": "optimistic", "isolation": "repeatable-read"}, {}, "repeatable-read"),
        ({"concurrency": "optimistic"}, {"isolation": "serializable"}, "serializable"),
    ],
    ids=["requested", "root"],
)
def test_a_staged_writer_under_a_snapshot_level_is_refused_before_any_read(
    uow: dict[str, object], root: dict[str, object], level: str
) -> None:
    # Above Read Committed the attempt's source read fixes its snapshot, so the
    # `given.apply` writer committing after it turns the write into a
    # serialization failure, never the zero-row shortfall the case grades.
    case = _rooted(_load_case("m-opt-lock-005"), uow=uow, root=root)
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(EngineError, match=f"at `{level}` that read fixes the snapshot"):
        scenario.run_conflict_case(case, port)
    assert port.levels == []
    assert port.reads == []
    assert port.writes == []


def test_a_staged_writer_runs_at_a_requested_read_committed_over_a_snapshot_root() -> None:
    case = _rooted(
        _load_case("m-opt-lock-005"),
        uow={"concurrency": "optimistic", "isolation": "read-committed"},
        root={"isolation": "serializable"},
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    scenario.run_conflict_case(case, port)
    assert port.levels == ["read_committed"]
    assert len(port.writes) == 2


def _admitted(monkeypatch: pytest.MonkeyPatch) -> list[AdmittedWrite | PreparedTargetInstruction]:
    admitted: list[AdmittedWrite | PreparedTargetInstruction] = []
    admit = scenario._SimulatedUnit._admit  # pyright: ignore[reportPrivateUsage] - observes what the lane hands its simulated unit of work

    def recorded(unit: Any, item: AdmittedWrite | PreparedTargetInstruction) -> None:
        admitted.append(item)
        admit(unit, item)

    monkeypatch.setattr(
        scenario._SimulatedUnit,  # pyright: ignore[reportPrivateUsage] - observes what the lane hands its simulated unit of work
        "_admit",
        recorded,
    )
    return admitted


def _compiled(case: case_format.Case) -> list[str]:
    compile_case = (
        scenario.compile_write_sequence_case
        if case.shape == "writeSequence"
        else scenario.compile_scenario_case
    )
    emissions, _database_calls = compile_case(case, "postgres")
    return [emission.sql for emission in emissions]


@pytest.mark.parametrize(
    ("case_id", "write_types"),
    [
        pytest.param(
            "m-batch-write-004", [StateObservedWrite, StateObservedWrite], id="versioned-deletes"
        ),
        pytest.param("m-opt-lock-026", [StateObservedWrite], id="restated-amendment"),
        pytest.param("m-temporal-write-005", [StateObservedWrite], id="fixture-history"),
        pytest.param(
            "m-temporal-write-002",
            [PreparedKeyedInstruction, StateObservedWrite],
            id="earlier-entry",
        ),
        pytest.param(
            "m-temporal-write-017",
            [PreparedKeyedInstruction, StateObservedWrite],
            id="bounded-window",
        ),
    ],
)
def test_a_compiled_observed_write_settles_against_a_detached_retained_observation(
    case_id: str, write_types: list[type], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The authored or case-state observation is retained by the simulated
    # transaction itself, with no read's participation, and composes and
    # settles as an application's retained evidence does.
    admitted = _admitted(monkeypatch)
    case = _load_case(case_id)
    assert _compiled(case) == [sql for sql, _binds in write_golden_statements(case)]
    assert [type(item) for item in admitted] == write_types
    for write in admitted:
        if isinstance(write, StateObservedWrite):
            assert write.retained_observation.participation is None


@pytest.mark.parametrize(
    ("case_id", "key", "emitted"),
    [
        pytest.param("m-unit-work-008", 8, ["insert"], id="folded-amendment"),
        pytest.param("m-unit-work-010", 9, [], id="cancelled-deletion"),
    ],
)
def test_a_compiled_write_of_an_object_its_transaction_inserted_is_insertion_authorized(
    case_id: str, key: int, emitted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    admitted = _admitted(monkeypatch)
    sql = _compiled(_load_case(case_id))
    assert [statement.split(" ", 1)[0] for statement in sql] == [*emitted, "select"]
    insert, authorized = admitted
    assert isinstance(insert, PreparedKeyedInstruction)
    assert isinstance(authorized, InsertionAuthorizedWrite)
    assert authorized.identity.object_key.primary_key == (("id", key),)


@pytest.mark.parametrize("case_id", ["m-unit-work-026", "m-unit-work-027"])
def test_a_compiled_observation_free_write_carries_simulated_evidence_of_its_object(
    case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    admitted = _admitted(monkeypatch)
    _compiled(_load_case(case_id))
    first, second = admitted
    assert isinstance(first, ObjectLockedWrite)
    assert isinstance(second, ObjectLockedWrite)
    ((one,), (two,)) = (first.source_evidence, second.source_evidence)
    assert one is not two and one.participation is two.participation
    assert (one.observation, two.observation) == (None, None)
    assert one.object_key == two.object_key


def test_each_compiled_write_of_a_group_carries_evidence_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = _admitted(monkeypatch)
    find = {
        "uow": "g",
        "objectQuery": {
            "target": "OrderItem",
            "predicate": {"eq": {"path": "OrderItem.id", "value": 21}},
        },
    }
    case = _synthetic_write(
        "scenario",
        {
            "model": "models/orders.yaml",
            "when": {
                "scenario": [
                    {
                        "uow": "g",
                        "write": [
                            {
                                "mutation": "amend",
                                "entity": "OrderItem",
                                "rows": [{"id": 21, "quantity": 9}],
                            }
                        ],
                    },
                    find,
                    {
                        "uow": "g",
                        "write": [
                            {"mutation": "delete", "entity": "OrderItem", "rows": [{"id": 21}]}
                        ],
                    },
                ]
            },
            "then": {"units": {"g": {"outcome": "committed"}}},
        },
    )
    scenario.compile_scenario_case(case, "postgres")
    first, second = admitted
    assert isinstance(first, ObjectLockedWrite)
    assert isinstance(second, ObjectLockedWrite)
    ((one,), (two,)) = (first.source_evidence, second.source_evidence)
    assert one is not two


def test_a_target_step_is_written_from_its_callers_revision_with_no_source_read() -> None:
    port = FakeWritePort()
    emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-opt-lock-028"), port
    )
    assert database_calls == 1
    assert not any(" where " in sql for sql, _ in port.reads)
    assert [sql for sql, _ in port.writes] == [
        POSTGRES.to_driver_sql(
            "update account set owner = ?, balance = ?, version = ? where id = ? and version = ?"
        )
    ]
    assert [e.case_pointer for e in emissions] == ["/writeSequence/0"]


def test_a_target_deletion_step_is_written_through_its_target_verb() -> None:
    port = FakeWritePort()
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-opt-lock-039"), port
    )
    assert database_calls == 1
    assert port.writes == [
        (POSTGRES.to_driver_sql("delete from account where id = ? and version = ?"), [2, 1])
    ]


def test_a_target_termination_step_reads_its_row_then_closes_it_and_chains_nothing() -> None:
    jan = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = FakeWritePort(
        find_rows=[
            {
                "bal_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("100.00"),
                "in_z": jan,
                "out_z": INFINITY,
            }
        ]
    )
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-069"), port
    )
    assert database_calls == 3
    insert, close = port.writes
    assert insert[0].startswith("insert into balance")
    assert close == (
        POSTGRES.to_driver_sql(
            "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
        ),
        [dt.datetime(2024, 6, 1, tzinfo=dt.UTC), 1, "infinity", jan],
    )


def test_a_target_replacement_step_completes_what_its_row_omits() -> None:
    since = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    port = FakeWritePort(
        find_rows=[
            {
                "id": 5,
                "label": "voyager",
                "spec": {"title": "Ore Run", "origin": {"country": "NO"}},
                "marks": [{"code": "X"}],
                "in_z": since,
                "out_z": INFINITY,
            }
        ]
    )
    scenario.run_write_sequence_case(_load_case("m-unit-work-043"), port)
    _close, successor = port.writes
    assert successor[1][-2:] == [JsonDocument(None), JsonDocument(())]


@pytest.mark.parametrize(
    ("case_id", "written"),
    [
        ("m-opt-lock-029", "update account set balance = ?, version = ? where id = ?"),
        ("m-opt-lock-040", "delete from account where id = ?"),
    ],
)
def test_a_locking_target_step_acquires_its_row_before_it_writes(
    case_id: str, written: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = _counting_case_state_reads(monkeypatch)
    port = FakeWritePort(
        find_rows=[{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}]
    )
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case(case_id), port
    )
    assert database_calls == 2
    assert [sql for sql, _ in port.writes] == [POSTGRES.to_driver_sql(written)]
    assert counts == {"target": 0, "coverage": 0}


def test_a_locking_target_replacement_step_reuses_the_row_it_acquired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _counting_case_state_reads(monkeypatch)
    jan = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = FakeWritePort(
        find_rows=[
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("100.00"),
                "from_z": jan,
                "thru_z": INFINITY,
                "in_z": jan,
                "out_z": INFINITY,
            }
        ]
    )
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-043"), port
    )
    assert database_calls == 4
    assert [sql.split(" ", 1)[0] for sql, _ in port.writes] == ["insert", "update", "insert"]
    assert counts == {"target": 0, "coverage": 0}


def test_a_bounded_temporal_target_step_reads_its_coverage_then_writes_its_window() -> None:
    jan = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = FakeWritePort(
        find_rows=[
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("100.00"),
                "from_z": jan,
                "thru_z": INFINITY,
                "in_z": jan,
                "out_z": INFINITY,
            }
        ]
    )
    _emissions, _table_state, database_calls = scenario.run_write_sequence_case(
        _load_case("m-temporal-write-042"), port
    )
    assert database_calls == 4
    (coverage,) = (binds for sql, binds in port.reads if "t0.thru_z > " in sql)
    assert coverage == [
        1,
        dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        INFINITY,
    ]
    assert [sql.split(" ", 1)[0] for sql, _ in port.writes] == ["insert", "update", "insert"]
    assert port.writes[2][0].count("), (") == 2


@pytest.mark.parametrize("state_graded", [False, True])
def test_a_replayed_contiguous_group_replaces_sources_and_reports(
    state_graded: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("ordinary group entered compile machinery")

    monkeypatch.setattr(SimulatedTemporalStore, "__init__", refuse)
    monkeypatch.setattr(_case_ingress, "prepare_case_write", refuse)
    instant = "2024-05-01T00:00:00+00:00"
    first = _ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")
    second = _ledger_row(2, "250.00", in_z="2024-03-01T00:00:00+00:00")
    insert = {**_ledger_insert(instant), "uow": "g"}
    final_find = _ledger_find()
    inserted_update = _ledger_chain_update("150.00", instant, uow="g")
    cast("list[dict[str, object]]", inserted_update["write"])[0]["on"] = "/scenario/1/write/0"
    steps = [
        _ledger_find(),
        insert,
        inserted_update,
        _ledger_update("300.00", instant, uow="g"),
        final_find,
    ]
    case = _synthetic_ledger_scenario(steps, {"g": {"outcome": "committed"}})
    if state_graded:
        case = dataclasses.replace(
            case,
            document={
                **case.document,
                "grading": "state",
                "then": {"units": {"g": {"outcome": "committed"}}},
            },
        )
    port = FakeWritePort(read_script=[[first], [second], [second]], affected_script=[1, 0, 1, 1, 1])
    run = scenario.run_scenario_case(case, port)
    assert port.rollbacks == port.commits == 1
    assert run.database_calls == 8
    assert len(run.step_rows) == 2
    assert all(
        cast("list[dict[str, object]]", item["rows"])[0]["val"] == "250.00"
        for item in run.step_rows
    )
    closes = [binds for sql, binds in port.writes if sql.startswith("update")]
    assert [binds[-1] for binds in closes] == [first["in_z"], second["in_z"]]
    inserts = [binds for sql, binds in port.writes if sql.startswith("insert") and binds[0] == 9]
    assert len(inserts) == 2 and all(binds[2] == decimal.Decimal("150.00") for binds in inserts)
    if state_graded:
        assert run.units == {"g": {"outcome": "committed"}}
        assert run.errors == []
    else:
        assert run.step_graphs == []
        assert (
            len([item for item in run.emissions if item.sql.startswith(("insert", "update"))]) == 5
        )


def test_a_replayed_predicate_reports_only_the_selected_attempts_affected_count() -> None:
    target = {"entity": "Wallet", "predicate": {"eq": {"path": "Wallet.id", "value": 1}}}
    case = _synthetic_scenario(
        "models/wallet.yaml",
        "m-unit-work-999",
        [
            {"write": {"mutation": "delete", "target": target}, "databaseCalls": 2},
        ],
    )
    with ScriptedAdapter(
        Transact(
            Write(affected=2),
            commit=DatabaseError(category="deadlock", native_code="40001", message="retry"),
        ),
        Transact(Write(affected=3)),
    ) as port:
        run = scenario.run_scenario_case(case, port)
    assert run.step_affected_rows == [{"at": "/scenario/0", "affectedRows": 3}]
    assert run.database_calls == 2
    assert len(run.emissions) == 2


def test_a_state_graded_replay_replaces_refusals_and_failure_location() -> None:
    row = {"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}
    steps = [
        _account_find_step(1),
        {
            "uow": "g",
            "write": [
                {"mutation": "delete", "entity": "Account", "rows": [{"id": 1}], "on": 0},
                {
                    "mutation": "amend",
                    "entity": "Account",
                    "rows": [{"id": 1, "owner": "Bo"}],
                    "on": 0,
                    "expectError": "write-evidence-already-claimed",
                },
            ],
        },
        _account_find_step(1),
    ]
    case = _synthetic_write(
        "scenario",
        {
            "grading": "state",
            "when": {"uow": {"maxRetries": 1}, "scenario": steps},
            "then": {"units": {"g": {"outcome": "committed"}}},
        },
    )
    port = FakeWritePort(read_script=[[row], [{**row, "version": 2}]], affected_script=[0, 0])
    run = scenario.run_scenario_case(case, port)
    assert run.database_calls == 4
    assert len(run.step_rows) == 1
    assert run.errors == [
        {"at": "/scenario/1/write/1", "errorClass": "write-evidence-already-claimed"}
    ]
    assert run.units == {
        "g": {
            "outcome": "rolledBack",
            "flushFailure": {
                "at": 2,
                "entity": "parallax.compatibility.Account",
                "key": {"id": 1},
                "shortfall": "optimisticConflict",
            },
        }
    }
    assert port.rollbacks == 2 and port.commits == 0


def _with_grading(case: case_format.Case, state_graded: bool) -> case_format.Case:
    return (
        dataclasses.replace(case, document={**case.document, "grading": "state"})
        if state_graded
        else case
    )


@pytest.mark.parametrize("account_id", [90, 91])
def test_an_insertion_pointer_retains_every_row_of_its_submission(account_id: int) -> None:
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "scenario": [
                    {
                        "uow": "g",
                        "write": [
                            {
                                "mutation": "insert",
                                "entity": "Account",
                                "rows": [
                                    {"id": key, "owner": "Noether", "balance": "5.00"}
                                    for key in (90, 91)
                                ],
                            }
                        ],
                    },
                    {
                        "uow": "g",
                        "write": [
                            {
                                "mutation": "amend",
                                "entity": "Account",
                                "rows": [{"id": account_id, "owner": "Ada"}],
                                "on": "/scenario/0/write/0",
                            }
                        ],
                    },
                ]
            }
        },
    )
    port = FakeWritePort(affected_script=[2])

    run = scenario.run_scenario_case(case, port)

    assert run.errors == [] and run.units == {"g": {"outcome": "committed"}}
    assert run.database_calls == 1 and port.reads == []
    assert port.commits == 1 and port.rollbacks == 0
    assert port.writes == [
        (
            "insert into account(id, owner, balance, version) values (%s, %s, %s, %s), "
            "(%s, %s, %s, %s)",
            [
                90,
                "Ada" if account_id == 90 else "Noether",
                decimal.Decimal("5.00"),
                1,
                91,
                "Ada" if account_id == 91 else "Noether",
                decimal.Decimal("5.00"),
                1,
            ],
        )
    ]
    assert len(run.emissions) == 1
    assert run.emissions[0].sql.replace("?", "%s") == port.writes[0][0]


@pytest.mark.parametrize("state_graded", [False, True])
@pytest.mark.parametrize("delivery", [None, "eager", "stream"])
def test_an_insertion_pointer_survives_composition_and_production_flushes(
    state_graded: bool, delivery: str | None
) -> None:
    update = {
        "uow": "g",
        "write": [
            {
                "mutation": "amend",
                "entity": "Account",
                "rows": [{"id": 90, "balance": "9.00"}],
                "on": "/scenario/0/write/0",
            }
        ],
    }
    steps = [_account_insert_step(90), update]
    if delivery is not None:
        find = _account_find_step(90)
        if delivery == "stream":
            find["stream"] = {"batchSize": 2}
        steps.append(find)
    steps.append(
        {
            "uow": "g",
            "write": [
                {
                    **cast("list[dict[str, object]]", update["write"])[0],
                    "rows": [{"id": 90, "owner": "Ada"}],
                }
            ],
        }
    )
    case = _with_grading(_synthetic_write("scenario", {"when": {"scenario": steps}}), state_graded)
    port = FakeWritePort(find_rows=[_account(90, "Noether", "9.00", 1)])

    run = scenario.run_scenario_case(case, port)

    assert run.errors == [] and run.units == {"g": {"outcome": "committed"}}
    assert port.commits == 1 and port.rollbacks == 0
    if delivery is None:
        assert run.database_calls == 1 and run.step_rows == []
        assert port.writes[0][1] == [90, "Ada", decimal.Decimal("9.00"), 1]
        assert len(port.writes) == 1
    else:
        assert run.database_calls == 3
        assert [item["at"] for item in run.step_rows] == ["/scenario/2"]
        assert port.writes[0][1] == [90, "Noether", decimal.Decimal("9.00"), 1]
        assert port.writes[1][1] == ["Ada", 2, 90, 1]
        assert len(port.writes) == 2
    if not state_graded:
        assert [
            e.sql.replace("?", "%s")
            for e in run.emissions
            if e.sql.startswith(("insert", "update"))
        ] == [sql for sql, _ in port.writes]


@pytest.mark.parametrize("state_graded", [False, True])
@pytest.mark.parametrize(
    "source", ["/scenario/99/write/0", "/scenario/1/write/0", "/scenario/2/write/0"]
)
def test_a_missing_self_or_forward_insertion_pointer_never_uses_a_same_key_read(
    state_graded: bool, source: str
) -> None:
    steps = [
        _account_find_step(90),
        {
            "uow": "g",
            "write": [
                {
                    "mutation": "amend",
                    "entity": "Account",
                    "rows": [{"id": 90, "owner": "Ada"}],
                    "on": source,
                }
            ],
        },
        _account_insert_step(90),
    ]
    case = _with_grading(_synthetic_write("scenario", {"when": {"scenario": steps}}), state_graded)
    port = FakeWritePort(find_rows=[_account(90, "Noether", "5.00", 1)])

    with pytest.raises(EngineError, match="opened no value"):
        scenario.run_scenario_case(case, port)

    assert port.writes == [] and port.rollbacks == 1 and port.commits == 0


@pytest.mark.parametrize("state_graded", [False, True])
def test_an_insertion_pointer_cannot_cross_a_group_boundary(state_graded: bool) -> None:
    steps = [
        _account_insert_step(90),
        _account_find_step(90, uow="h"),
        {
            "uow": "h",
            "write": [
                {
                    "mutation": "amend",
                    "entity": "Account",
                    "rows": [{"id": 90, "owner": "Ada"}],
                    "on": "/scenario/0/write/0",
                }
            ],
        },
    ]
    case = _with_grading(_synthetic_write("scenario", {"when": {"scenario": steps}}), state_graded)
    port = FakeWritePort(find_rows=[_account(90, "Noether", "5.00", 1)])

    with pytest.raises(EngineError, match="opened no value"):
        scenario.run_scenario_case(case, port)

    assert len(port.writes) == 1 and port.writes[0][0].startswith("insert")
    assert port.commits == 1 and port.rollbacks == 1


@pytest.mark.parametrize("state_graded", [False, True])
def test_an_insertion_pointer_must_name_the_writes_own_object(state_graded: bool) -> None:
    steps = [
        _account_insert_step(90),
        _account_find_step(91),
        {
            "uow": "g",
            "write": [
                {
                    "mutation": "amend",
                    "entity": "Account",
                    "rows": [{"id": 91, "owner": "Ada"}],
                    "on": "/scenario/0/write/0",
                }
            ],
        },
    ]
    case = _with_grading(_synthetic_write("scenario", {"when": {"scenario": steps}}), state_graded)
    port = FakeWritePort(find_rows=[_account(91, "Noether", "5.00", 1)])

    with pytest.raises(EngineError, match="published 0 rows"):
        scenario.run_scenario_case(case, port)

    assert len(port.writes) == 1 and port.writes[0][0].startswith("insert")
    assert port.rollbacks == 1 and port.commits == 0


@pytest.mark.parametrize("state_graded", [False, True])
@pytest.mark.parametrize("on", [0, 1, None])
def test_named_finds_preserve_distinct_read_generations(state_graded: bool, on: int | None) -> None:
    entry: dict[str, object] = {
        "mutation": "amend",
        "entity": "Account",
        "rows": [{"id": 1, "owner": "Bo"}],
    }
    if on is not None:
        entry["on"] = on
    steps = [_account_find_step(1), _account_find_step(1), {"uow": "g", "write": [entry]}]
    case = _with_grading(_synthetic_write("scenario", {"when": {"scenario": steps}}), state_graded)
    port = FakeWritePort(
        read_script=[[_account(1, "Ada", "5.00", 1)], [_account(1, "Ada", "5.00", 4)]]
    )

    run = scenario.run_scenario_case(case, port)

    assert port.writes[0][1] == ["Bo", 2 if on == 0 else 5, 1, 1 if on == 0 else 4]
    assert run.database_calls == 3 and len(run.step_rows) == 2
    assert port.commits == 1 and port.rollbacks == 0


@pytest.mark.parametrize("state_graded", [False, True])
@pytest.mark.parametrize("on", [0, 1, None])
def test_a_historical_read_never_replaces_a_current_source(
    state_graded: bool, on: int | None
) -> None:
    current = _ledger_find()
    historical = _ledger_find()
    cast("dict[str, Any]", historical["objectQuery"])["temporal"] = {
        "transaction-time": {"asOf": "2024-01-15T00:00:00.000000Z"}
    }
    update = _ledger_update("300.00", "2024-05-01T00:00:00+00:00", uow="g")
    if on is not None:
        cast("list[dict[str, object]]", update["write"])[0]["on"] = on
    case = _with_grading(_synthetic_ledger_scenario([current, historical, update]), state_graded)
    row = _ledger_row(2, "200.00", in_z="2024-02-01T00:00:00+00:00")
    old = {
        **_ledger_row(2, "150.00", in_z="2024-01-01T00:00:00+00:00"),
        "out_z": row["in_z"],
    }
    port = FakeWritePort(read_script=[[row], [old]])

    if on == 1:
        with pytest.raises(TransactionTimePinReadOnlyError):
            scenario.run_scenario_case(case, port)
        assert port.writes == [] and port.rollbacks == 1 and port.commits == 0
    else:
        run = scenario.run_scenario_case(case, port)
        assert port.writes[0][1][-1] == row["in_z"]
        assert len(port.writes) == 2 and run.database_calls == 4
        assert [item["at"] for item in run.step_rows] == ["/scenario/0", "/scenario/1"]
        assert port.commits == 1 and port.rollbacks == 0


@pytest.mark.parametrize("state_graded", [False, True])
def test_a_named_bitemporal_insertion_composes_without_a_read_pin(state_graded: bool) -> None:
    instant = "2024-05-01T00:00:00+00:00"
    start = "2024-01-01T00:00:00.000000Z"
    case = _with_grading(
        _synthetic_write(
            "scenario",
            {
                "model": "models/position.yaml",
                "when": {
                    "scenario": [
                        {
                            "uow": "g",
                            "write": [
                                {
                                    "mutation": "insert",
                                    "entity": "Position",
                                    "rows": [{"id": 9, "acctNum": "D", "value": "100.00"}],
                                    "validFrom": start,
                                    "at": instant,
                                },
                                {
                                    "mutation": "amend",
                                    "entity": "Position",
                                    "rows": [{"id": 9, "value": "150.00"}],
                                    "validFrom": start,
                                    "at": instant,
                                    "on": "/scenario/0/write/0",
                                },
                            ],
                        }
                    ]
                },
            },
        ),
        state_graded,
    )
    port = FakeWritePort()

    run = scenario.run_scenario_case(case, port)

    assert run.database_calls == 1 and run.errors == []
    assert len(port.writes) == 1
    assert len(port.reads) == (1 if state_graded else 0)
    assert all(sql.endswith("from position") for sql, _ in port.reads)
    assert port.writes[0][1][:4] == [9, "D", decimal.Decimal("150.00"), _instant(start)]
    assert port.commits == 1 and port.rollbacks == 0
