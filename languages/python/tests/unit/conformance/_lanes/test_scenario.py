"""The scenario, writeSequence, and conflict lanes, driven database-free.

The compile lane runs with no port at all; the run lanes run against fake
in-memory ports, which state what a real database cannot be made to answer on
demand: refusals no corpus case reaches, port-only observations, and the
compositions only a synthetic case spells.
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

from parallax.conformance import _case_ingress, _simulated_write_steps, case_format, models
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._lanes import scenario
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    LifecycleRun,
    execution_lifecycle_observation,
)
from parallax.conformance._mechanism import case_document, model_facts
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.core import ConflictError
from parallax.core._execution._unit_work._write_ownership import KeyedWriteRefusalAdvice
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
)
from parallax.core._execution._unit_work.write_items import (
    InsertionAuthorizedWrite,
    KeyedInsert,
)
from parallax.core.execution_lifecycle import DatabaseCallStarted
from parallax.core.internal.base import (
    INFINITY,
    INT64,
    InternalError,
    Numeric,
    String,
    TemporalBound,
    UsageError,
)
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    ArrayBind,
    MappingRow,
    StructuredDocument,
)
from parallax.core.internal.execution import (
    RetryPolicy,
    TxnOptions,
)
from parallax.core.internal.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.internal.sql_gen._context import SQL_GENERATION_FAILED
from parallax.core.internal.unit_work import (
    MISSING_TARGET,
    OPTIMISTIC_LOCK_CONFLICT,
    STALE_WRITE,
    AdmittedWrite,
    InsertionIdentity,
    ReadAuthorizedWrite,
    UnitOfWork,
    WriteEffectCode,
)
from parallax.core.internal.write_plan.managed_row import named_members
from parallax.core.internal.write_plan.planned_rows import WRITE_PLANNING_FAILED
from tests._support.case_corpus import case as corpus_case
from tests._support.db_port import ScriptedAdapter, Transact, Write
from tests._support.errors import raises_code
from tests.unit.conformance._lanes._scripted_port import ScriptedPort
from tests.unit.conformance._recording_ports import FakeWritePort


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of sweep
    # reachability: these engine-function-level tests
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


def _balance_row(row_id: int, value: str, *, in_z: str) -> MappingRow:
    return {
        "bal_id": row_id,
        "acct_num": "A",
        "val": decimal.Decimal(value),
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


@pytest.mark.parametrize("row", [{"balance": "5.00"}, {"id": None, "balance": "5.00"}])
def test_an_unaddressed_write_neither_reads_nor_submits_dml(row: dict[str, object]) -> None:
    case = _synthetic_write(
        "writeSequence",
        {"when": {"writeSequence": [{"mutation": "amend", "entity": "Account", "rows": [row]}]}},
    )
    port = FakeWritePort()

    with pytest.raises(UnclassifiedEngineError, match="a keyed write addresses None"):
        scenario.run_write_sequence_case(case, port)

    assert port.reads == []
    assert port.writes == []
    assert port.commits == 0 and port.rollbacks == 1


# --- `uow`-grouped scenario spans --------------------------------------------
#
# A whole `uow` span runs in ONE `db.transact` call, never the ungrouped
# per-step path. A fake port that answers every read the same canned rows is
# enough to state the mechanics; the observed values themselves are graded
# against a real database by the run sweep.


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
    assert [e.sql for e in run.emissions[1:]] == [sql for sql, _ in port.writes]
    assert [sql.split("(")[0] for sql, _ in port.writes] == [
        "delete from px.order_item where id = ?",
        "update px.order_item set sku = ? where quantity < ?",
        "insert into px.orders",
        "insert into px.order_item",
    ]
    # One participating read, then the case's own tables read back once it ran.
    assert len(port.reads) == 1 + len((run.table_state or {}).get("px", {}))
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

    with pytest.raises(UnclassifiedEngineError, match="declares no `includes`"):
        scenario.run_scenario_case(case, ScriptedPort(read_rows=[[dict(_ORDER_1_ROW)]]))


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
            "write": [
                {
                    "mutation": "amend",
                    "entity": "Account",
                    "rows": [{"id": 1, "observedVersion": 1}],
                }
            ],
            "databaseCalls": 1,
            "statements": [
                {
                    "sql": {"postgres": "update px.account set balance = ? where id = ?"},
                    "binds": [1.0, 1],
                }
            ],
        },
    ]


def test_scenario_compile_lane_refuses_two_interleaved_groups() -> None:
    # Two concurrent units are what a simulated transaction cannot model, so the
    # compile lane refuses the shape rather than lowering its steps as ungrouped.
    case = _synthetic_write(
        "scenario",
        {"when": {"scenario": _two_group_interleave_steps()}, "then": {"databaseCalls": 3}},
    )
    with pytest.raises(UnclassifiedEngineError, match="compileEligibility: run-only"):
        scenario.compile_scenario_case(case, "postgres")


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
    with pytest.raises(UnclassifiedEngineError, match="run_interleaved_scenario_case"):
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
    with pytest.raises(UnclassifiedEngineError, match="interleave beyond the witnessed"):
        scenario._scenario_uow_spans(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            "m-unit-work-999-synthetic.yaml", steps
        )


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

    (document,) = (
        bind.document for bind in successor.binds if isinstance(bind, StructuredDocument)
    )
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


@pytest.mark.parametrize(
    ("case_id", "refusal"),
    [
        pytest.param("m-temporal-write-042", "reads no stored row", id="target-range"),
        pytest.param("m-concurrency-029", "reads no stored row", id="locking-amend"),
        pytest.param("m-concurrency-040", "reads no stored row", id="locking-delete"),
        pytest.param("m-temporal-write-043", "reads no stored row", id="locking-replace"),
        pytest.param("m-temporal-write-002", "insertion's authority", id="earlier-entry"),
        pytest.param("m-temporal-write-005", "insertion's authority", id="fixtures"),
    ],
)
def test_a_write_against_stored_state_is_refused_rather_than_compiled(
    case_id: str, refusal: str
) -> None:
    # Compile reads nothing, so what such a case declares run-only for is what
    # exposes it were it declared eligible.
    with pytest.raises(UnclassifiedEngineError, match=refusal):
        scenario.compile_write_sequence_case(_load_case(case_id), "postgres")


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
    with pytest.raises(UnclassifiedEngineError, match="cannot admit this write") as raised:
        scenario.compile_scenario_case(case, "postgres")
    refusal = raised.value.__cause__
    assert isinstance(refusal, UsageError)
    assert refusal.code == "write-evidence-already-claimed"


@pytest.mark.parametrize(
    ("raised_failure", "translated"),
    [
        pytest.param(
            lambda: InternalError(SQL_GENERATION_FAILED, "no such lowering"),
            True,
            id="lowering-diagnostic",
        ),
        pytest.param(lambda: RuntimeError("a defect"), False, id="defect"),
        pytest.param(KeyboardInterrupt, False, id="interruption"),
    ],
)
def test_only_a_lowering_diagnostic_becomes_an_engine_error(
    raised_failure: Callable[[], BaseException],
    translated: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Built per run: raising attaches a traceback, through which a parameter
    # instance would keep this run's frames alive for the rest of the session.
    failure = raised_failure()

    def failing(*_arguments: object, **_keywords: object) -> None:
        raise failure

    monkeypatch.setattr(_simulated_write_steps, "stream_physical", failing)
    case = _load_case("m-temporal-write-001")
    if translated:
        with pytest.raises(UnclassifiedEngineError, match="no such lowering") as engine_error:
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
    context = scenario.CaseContext(
        serving, meta, model_facts.case_binding(case), "optimistic", {}, TxnOptions()
    )
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
    assert set(table_state) == {"px"}
    assert set(table_state["px"]) == {
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
    with pytest.raises(UnclassifiedEngineError, match="does not match the 1 statement"):
        scenario.run_write_sequence_case(case, port)
    assert len(port.writes) == 1


def test_a_units_resolving_read_names_no_statement_in_the_lifecycle_observation() -> None:
    """The one call inside a write unit that the emissions do not hold.

    m-temporal-write-002 costs four Database Calls for three golden statements: the
    update px.entry reads the milestone it closes before writing it. A case counts
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


def test_a_compiled_write_sequence_reports_each_emission_under_its_own_entry() -> None:
    # m-unit-work-007's four entries each emit one statement.
    emissions, _database_calls = scenario.compile_write_sequence_case(
        _case("m-unit-work-007"), "postgres"
    )
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
    with pytest.raises(UnclassifiedEngineError, match="undeclared member"):
        scenario.compile_scenario_case(bad, "postgres")


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
    with pytest.raises(UnclassifiedEngineError, match="an insert row authors no `observedVersion`"):
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
    with pytest.raises(UnclassifiedEngineError, match="a write row authors no `observedTxStart`"):
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
    with pytest.raises(
        UnclassifiedEngineError, match="an unversioned row authors no `observedVersion`"
    ):
        scenario.compile_write_sequence_case(case, "postgres")


def test_a_collapsed_multi_row_insert_decodes_its_wire_floats_before_real_execution() -> None:
    # m-batch-write-001's own insert shape, run for real: the case authors
    # `decimal` balances as wire-spelled floats, and the engine decodes each row
    # to its native carrier before handing it to `tx.wire.insert` — the collapse
    # into one statement happens afterwards, in the planner.
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
    assert sql == (
        "insert into px.wallet(id, owner, balance) select * from "
        "unnest(cast(? as bigint[]), cast(? as text[]), cast(? as decimal[]))"
    )
    columns = [cast("ArrayBind", bind).values for bind in binds]
    assert columns == [
        [10, 11],
        ["Mira", "Omar"],
        [decimal.Decimal("100.0"), decimal.Decimal("20.0")],
    ]
    assert all(isinstance(balance, decimal.Decimal) for balance in columns[2])


def test_update_entry_uniform_within_each_physical_group_collapses_per_group() -> None:
    # An entry whose rows are non-uniform TAKEN AS A WHOLE, yet uniform WITHIN
    # each physical group: the first two rows assign only `balance`, the last
    # two only `owner`. Batch grouping partitions them into two runs before
    # collapse eligibility is asked of either (m-sql "Physical DML ordering"),
    # and each run's own rows ARE uniform, so both collapse into one
    # key-membership UPDATE (m-batch-write "Set-based flush"). The authored `statements: 2`
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
        "update px.wallet set balance = ? where id = any(cast(? as bigint[]))",
        "update px.wallet set owner = ? where id = any(cast(? as bigint[]))",
    ]
    assert [e.binds for e in emissions] == [
        (500.00, ArrayBind(INT64, [1, 2])),
        ("Zed", ArrayBind(INT64, [3, 4])),
    ]


def test_update_entry_non_uniform_within_a_physical_group_rejects_a_per_row_count() -> None:
    # The same two physical groups as above, but each group's own rows assign
    # DIFFERENT values, so neither collapses: each row stays its own keyed
    # update, and execution applies each assigned-member set's updates as one
    # grouped effect. `statements` stays a real assertion: an authored count of
    # 4 (the row count, not the statement count) is an authoring error and
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
                        "statements": 4,
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
    with pytest.raises(UnclassifiedEngineError, match="does not match the 2 statement"):
        scenario.compile_write_sequence_case(case, "postgres")


def test_non_uniform_multi_row_update_applies_one_grouped_effect_per_member_set() -> None:
    # m-batch-write-002's own shape: non-uniform per-key values stay one keyed
    # update per key, and execution presents updates assigning the same members
    # as one grouped effect binding one array per source column.
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
                            {"id": 3, "owner": "Zed"},
                            {"id": 2, "balance": "222.00"},
                            {"id": 4, "owner": "Ada"},
                        ],
                    }
                ]
            },
        },
    )
    emissions, database_calls = scenario.compile_write_sequence_case(case, "postgres")
    assert database_calls == 2
    assert [e.sql for e in emissions] == [
        "update px.wallet t set balance = v.c2 from unnest(cast(? as bigint[]), "
        "cast(? as decimal[])) with ordinality v(c1, c2, ord) where t.id = v.c1 "
        "returning v.ord",
        "update px.wallet t set owner = v.c2 from unnest(cast(? as bigint[]), "
        "cast(? as text[])) with ordinality v(c1, c2, ord) where t.id = v.c1 "
        "returning v.ord",
    ]
    arrays = [[cast("ArrayBind", bind) for bind in e.binds] for e in emissions]
    assert [[(bind.element_type, bind.values) for bind in binds] for binds in arrays] == [
        [(INT64, [1, 2]), (Numeric(18, 2), [111.00, 222.00])],
        [(INT64, [3, 4]), (String(), ["Zed", "Ada"])],
    ]


def test_elided_no_op_row_is_not_counted_as_a_statement() -> None:
    # A versioned UPDATE row that assigns nothing but its own primary key has an
    # EMPTY effective change set, so the planner's elision stage drops it
    # (m-concurrency: a versioned update that changes no attribute issues no DML).
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
        "update px.account set balance = ?, version = ? where id = ? and version = ?"
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
    with pytest.raises(UnclassifiedEngineError, match="does not match the 0 statement"):
        scenario.compile_write_sequence_case(counted, "postgres")


def test_authored_statement_count_mismatch_is_rejected() -> None:
    # `statements` is a count-consistency ASSERTION
    # (`compatibility-case.schema.json`), verified independently of the
    # derived instruction count — never the discriminator itself. Two rows of a
    # versioned delete (one step each, applied as one grouped effect), each
    # carrying its own `observedVersion`, authored with a WRONG `statements: 2`.
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
    with pytest.raises(UnclassifiedEngineError, match="does not match"):
        scenario.compile_write_sequence_case(case, "postgres")


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
    with pytest.raises(UnclassifiedEngineError, match=r"scenario-write-only"):
        if lane == "compile":
            scenario.compile_write_sequence_case(case, "postgres")
        else:
            scenario.run_write_sequence_case(case, FakeWritePort())


def test_run_scenario_case_readless_predicate_write_rollback_aborts_but_counts_the_call() -> None:
    # `_run_readless_predicate_write`'s own abort contract mirrors the keyed-
    # write one: the golden DML still executes (and counts its Database Call)
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
    assert run.emissions[0].sql == "delete from px.wallet where balance < ?"
    assert len(port.writes) == 1
    assert port.commits == 0 and port.rollbacks == 1


def test_run_write_sequence_case_wraps_a_lowering_error() -> None:
    # Defensive coverage: a `_LOWERING_ERRORS` member raised anywhere inside
    # the per-entry loop (here, `instructions.deserialize`'s own unknown-
    # entity `KeyError`) surfaces as this seam's own `UnclassifiedEngineError`, never
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
    with pytest.raises(UnclassifiedEngineError, match="Ghost"):
        scenario.run_write_sequence_case(case, port)


# --------------------------------------------------------------------------- #
# Conflict — the optimistic-lock run lane (m-concurrency):                        #
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
        _load_case("m-concurrency-006"), port
    )
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "account" in table_state["px"]


@pytest.mark.parametrize(
    ("case_id", "mutation", "attempt"),
    [
        ("m-concurrency-006", "amend", None),
        ("m-concurrency-006", "delete", None),
        ("m-concurrency-009", "amend", 1),
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
    with pytest.raises(
        UnclassifiedEngineError, match=r"every versioned conflict write.*`observedVersion`"
    ):
        scenario.run_conflict_case(case, port)
    assert port.reads == port.writes == []


@pytest.mark.parametrize("mutation", ["amend", "delete"])
def test_every_row_of_a_versioned_conflict_attempt_requires_its_declared_version(
    mutation: str,
) -> None:
    case = _own_copy(_load_case("m-concurrency-006"))
    when = cast("dict[str, Any]", case.document["when"])
    when["mutation"] = mutation
    when["write"] = [when["write"], {"id": 3, "balance": "20.00"}]
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(
        UnclassifiedEngineError, match=r"every versioned conflict write.*`observedVersion`"
    ):
        scenario.run_conflict_case(case, port)
    assert port.reads == port.writes == []


def test_conflict_submissions_never_prepare_or_simulate_a_peer_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("conflict submission entered compile machinery")

    monkeypatch.setattr(SimulatedWriteSteps, "__init__", refuse)
    monkeypatch.setattr(_case_ingress, "prepare_case_write", refuse)
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, _table_state, database_calls = scenario.run_conflict_case(
        _load_case("m-concurrency-006"), port
    )
    assert affected == 1 and database_calls == 2
    assert len(port.reads) == 2 and len(port.writes) == 1
    assert emissions[0].sql == (
        "update px.account set balance = ?, version = ? where id = ? and version = ?"
    )


def test_a_conflict_attempt_counts_duplicate_addressed_keys_once() -> None:
    case = _synthetic_write(
        "conflict",
        {
            "when": {
                "uow": {"concurrency": "optimistic", "retry": {"maxRetries": 0}},
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


# The canonical spellings of the golden writes a fake port reports a zero-row
# shortfall for: a concurrent writer already moved or removed the row.
_ACCOUNT_WRITE_SHORTFALL: Final[tuple[str, ...]] = (
    "update px.account set balance = ?",
    "delete from px.account",
)


def test_a_conflict_attempt_whose_source_read_finds_no_row_is_refused() -> None:
    # A target `given.apply` already removed leaves the attempt with no value to
    # write, so a case authoring that state is unauthorable through the public
    # verbs rather than merely unpleasant.
    port = FakeWritePort(find_rows=[])
    with pytest.raises(
        UnclassifiedEngineError, match="which no read of its own choreography unit published"
    ):
        scenario.run_conflict_case(_load_case("m-concurrency-006"), port)


def test_a_conflict_attempt_writes_through_the_public_keyed_delete_verb() -> None:
    # `when.mutation: delete` reaches `tx.wire.delete`, keyed off the node the
    # source read published — the destructive case of the same one ingress the
    # update case takes.
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
    assert [e.sql for e in emissions] == ["delete from px.account where id = ? and version = ?"]
    assert affected == 1


def _unversioned_conflict_case(rows: list[dict[str, object]]) -> case_format.Case:
    return _synthetic_write(
        "conflict",
        {
            "model": "models/wallet.yaml",
            "when": {"uow": {"concurrency": "optimistic"}, "mutation": "amend", "write": rows},
        },
    )


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
    with pytest.raises(
        UnclassifiedEngineError, match="only the Optimistic strategy leaves room for"
    ):
        scenario.run_conflict_case(case, port)
    assert port.reads == []
    assert port.writes == []


def _always_implying(
    code: WriteEffectCode,
) -> Callable[[bool, ConcurrencyPreference, AcceptedMetamodel, str], WriteEffectCode]:
    """An ``_implied_shortfall_code`` stand-in that ignores the case's own
    declared facts — a lane admitting the wrong shortfall code."""

    def implied(
        _observation_requiring: bool,
        _concurrency: ConcurrencyPreference,
        _model: AcceptedMetamodel,
        _target: str,
    ) -> WriteEffectCode:
        return code

    return implied


_ACCOUNT: Final[str] = "parallax.compatibility.Account"


class TestConflictShortfallClassification:
    """The shortfall code a conflict case's declared facts imply, and the lane's
    refusal to absorb any other one.

    Every shortfall reports the same count, so a lane admitting every shortfall
    code would render `then.affectedRows: 0` identically whichever the write
    raised, and a zero-row case would assert nothing about the classification
    (`m-concurrency` "Classification follows the gate").
    """

    def test_an_optimistic_strategy_implies_the_retriable_conflict(self) -> None:
        from parallax.conformance import models

        assert (
            scenario._implied_shortfall_code(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                True, "optimistic", models.load_models()["account"], _ACCOUNT
            )
            == OPTIMISTIC_LOCK_CONFLICT
        )

    def test_a_locking_strategy_implies_the_non_retriable_stale_write(self) -> None:
        from parallax.conformance import models

        assert (
            scenario._implied_shortfall_code(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                True, "locking", models.load_models()["account"], _ACCOUNT
            )
            == STALE_WRITE
        )

    @pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
    def test_an_observation_free_write_implies_a_missing_target_under_either_preference(
        self, concurrency: ConcurrencyPreference
    ) -> None:
        # A write that observed nothing has no gate to classify by, so its
        # shortfall says only that the addressed rows are not there.
        from parallax.conformance import models

        assert (
            scenario._implied_shortfall_code(  # pyright: ignore[reportPrivateUsage] - the lane's own classification seam
                False, concurrency, models.load_models()["account"], _ACCOUNT
            )
            == MISSING_TARGET
        )

    def test_a_gated_shortfall_admitted_as_a_stale_write_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(scenario, "_implied_shortfall_code", _always_implying(STALE_WRITE))
        with raises_code(ConflictError, OPTIMISTIC_LOCK_CONFLICT):
            scenario.run_conflict_case(
                _load_case("m-concurrency-005"),
                FakeWritePort([_ACCOUNT_ROW_2], zero_affected_for=_ACCOUNT_WRITE_SHORTFALL),
            )

    def test_a_refusal_no_failed_flush_attributes_to_a_completed_write_is_unreadable(
        self,
    ) -> None:
        with pytest.raises(UnclassifiedEngineError, match="names no completed write call"):
            scenario._final_flush_failure_count(LifecycleObservation())  # pyright: ignore[reportPrivateUsage] - the lane's own count seam


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
    with pytest.raises(UnclassifiedEngineError, match="targets a non-temporal Entity"):
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
        _load_case("m-concurrency-009"), port
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
    case = _rooted(_load_case("m-concurrency-005"), uow={"concurrency": "optimistic"}, root={})
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2], zero_affected_for=_ACCOUNT_WRITE_SHORTFALL)
    with pytest.raises(
        UnclassifiedEngineError, match="replayed the conflict case's last authored attempt"
    ):
        scenario.run_conflict_case(case, port)
    assert len(port.levels) == 2


def test_a_conflict_case_whose_invocation_ends_before_its_last_attempt_is_refused() -> None:
    port = FakeWritePort(read_script=[[_ACCOUNT_ROW_2]], affected_script=[1])
    with pytest.raises(
        UnclassifiedEngineError, match=r"after 1 attempt\(s\), and the case authors 2"
    ):
        scenario.run_conflict_case(_load_case("m-concurrency-009"), port)


@pytest.mark.parametrize(
    ("uow", "root"),
    [
        ({"concurrency": "optimistic", "retry": {"maxRetries": 0}}, {}),
        ({"concurrency": "optimistic"}, {"retry": {"maxRetries": 0}}),
    ],
    ids=["requested", "root"],
)
def test_a_conflict_case_whose_bound_admits_fewer_attempts_than_it_authors_is_refused(
    uow: dict[str, object], root: dict[str, object]
) -> None:
    case = _rooted(_load_case("m-concurrency-009"), uow=uow, root=root)
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(
        UnclassifiedEngineError, match=r"authors 2 attempts and its transaction resolves"
    ):
        scenario.run_conflict_case(case, port)
    assert port.levels == []


def test_run_conflict_case_wraps_a_lowering_failure_as_engine_error() -> None:
    case = _synthetic_write(
        "conflict", {"when": {"write": {"id": 2, "bogus": True, "observedVersion": 1}}}
    )
    with pytest.raises(UnclassifiedEngineError, match="undeclared member"):
        scenario.run_conflict_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW_2]))


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
    with pytest.raises(UnclassifiedEngineError, match=re.escape("a temporal row authors no")):
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
    with pytest.raises(
        UnclassifiedEngineError, match=re.escape("a temporal write entry carries ONE")
    ):
        scenario.compile_write_sequence_case(case, "postgres")


def test_table_state_projects_sibling_document_paths_from_the_row_variant() -> None:
    from parallax.core.internal import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.storage_layout_facet_of(meta).tables
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
    from parallax.core.internal import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.storage_layout_facet_of(meta).tables
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
    from parallax.core.internal import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.storage_layout_facet_of(meta).tables
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
    from parallax.core.internal import storage_layout

    meta = models.load_models()["document-layout"]
    layout = next(
        candidate
        for candidate in storage_layout.storage_layout_facet_of(meta).tables
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
    from parallax.core.internal import storage_layout

    meta = models.load_models()["document-codec"]
    (layout,) = storage_layout.storage_layout_facet_of(meta).tables

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
    from parallax.core.internal import storage_layout

    meta = models.load_models()["document-codec"]
    (layout,) = storage_layout.storage_layout_facet_of(meta).tables

    projected = ActualWireProjection(meta).table_row(
        layout,
        {
            "id": 1,
            "label": "sample",
            "profile": {"amount": "12.5", "future": None},
        },
    )

    assert projected["profile"] == {"amount": "12.5", "future": None}


# --------------------------------------------------------------------------- #
# The value each keyed write is addressed by, resolved from what its own unit's  #
# reads published — a question this engine answers for itself, since           #
# production only ever sees the verb call it makes.                             #
# --------------------------------------------------------------------------- #


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
    with pytest.raises(UnclassifiedEngineError, match="which no read of its own choreography unit"):
        scenario.run_scenario_case(case, FakeWritePort())


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
    assert port.reads[0][0].endswith("where t0.id = any(cast(? as bigint[])) for share of t0")
    assert sorted(cast("list[int]", cast("ArrayBind", port.reads[0][1][0]).values)) == [21, 22]


def _registry_advance(sequence: str) -> dict[str, object]:
    return {
        "mutation": "amend",
        "entity": "parallax.compatibility.PkSequence",
        "rows": [{"name": sequence, "nextVal": {"increment": 1}}],
    }


@pytest.mark.parametrize("rollback", [False, True])
def test_marker_generation_and_execution_resolve_no_entries(
    monkeypatch: pytest.MonkeyPatch, rollback: bool
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("marker lowering resolved its entries")

    monkeypatch.setattr(scenario, "_resolve_entries", refuse)
    case = _synthetic_scenario(
        "models/pk-sequence.yaml", "m-pk-gen-998", [_pk_sequence_advance(rollback=rollback)]
    )
    compiled, compile_calls = scenario.compile_scenario_case(case, "postgres")
    port = FakeWritePort()
    run = scenario.run_scenario_case(case, port)

    assert compiled == run.emissions
    assert port.writes == [(item.sql, list(item.binds)) for item in compiled]
    assert compile_calls == run.database_calls == 1
    assert port.reads == []
    assert (port.commits, port.rollbacks) == ((0, 1) if rollback else (1, 0))


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
    refusal = {
        "mixed": "never both",
        "multiple": "buffer's only entry",
        "grouped": "is a choreography unit of its own; a `uow` group's held transaction",
        "multiple-rows": "buffer's only entry",
    }[kind]
    with pytest.raises(UnclassifiedEngineError, match=refusal):
        scenario.compile_scenario_case(case, "postgres")
    port = FakeWritePort()
    with pytest.raises(UnclassifiedEngineError, match=refusal):
        scenario.run_scenario_case(case, port)
    assert port.writes == []
    assert port.reads == []


def _pk_sequence_advance(**step: object) -> dict[str, object]:
    return {"write": [_registry_advance("badge_seq")], "databaseCalls": 1, **step}


# --------------------------------------------------------------------------- #
# Root configuration (m-case-format *Root configuration*): every Handle a      #
# scenario lane composes for the case's own units of work is connected with    #
# the record `given.databaseOptions` states, and every transaction it opens     #
# resolves what the request omits against that record — the held `uow` group,  #
# the ungrouped keyed unit, the ungrouped find, the readless predicate write,  #
# and the writeSequence entry alike.                                           #
# --------------------------------------------------------------------------- #
_CONSPICUOUS_ROOT: Final[dict[str, object]] = {
    "retry": {"maxRetries": 0},
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
    assert run.emissions[1].sql == "update px.account set balance = ?, version = ? where id = ?"


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


def test_only_the_ungrouped_write_opens_at_the_roots_level() -> None:
    port = FakeWritePort(
        find_rows=[{"id": 7, "owner": "Newton", "balance": decimal.Decimal("5.00"), "version": 1}]
    )
    case = _rooted(_case("m-unit-work-001"))
    run = scenario.run_scenario_case(case, port)
    compiled, _database_calls = scenario.compile_scenario_case(case, "postgres")
    assert port.levels == ["serializable"]
    assert port.commits == 1
    assert not run.emissions[1].sql.endswith("for share of t0")
    assert compiled[1].sql == run.emissions[1].sql


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
    case = _rooted(_case("m-unit-work-001"), uow={"retry": {"maxRetries": 3}})
    serving = model_facts.case_serving_model(case)
    context = scenario.CaseContext(
        serving,
        models.accepted_model_of(serving.current().model),
        model_facts.case_binding(case),
        case_document.concurrency(case),
        case_format.transaction_keywords(case),
        case_format.database_options(case),
    )
    assert context.options == TxnOptions(
        retry=RetryPolicy(max_retries=0),
        concurrency="locking",
        isolation="serializable",
    )
    assert context.requests == {"retry": RetryPolicy(max_retries=3)}
    assert context.concurrency == "locking"


def test_a_conflict_attempt_opens_at_the_roots_level_and_runs_under_its_bound() -> None:
    # The conflict lane connects its Handle with the case's root, so a root
    # level and bound govern the attempts exactly as authored ones do: one
    # production attempt at the root's level under the optimistic preference
    # the request authors.
    case = _rooted(_load_case("m-concurrency-006"), uow={"concurrency": "optimistic"})
    assert case_format.database_options(case) == TxnOptions(
        retry=RetryPolicy(max_retries=0),
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
    case = _rooted(_load_case("m-concurrency-005"), uow=uow, root=root)
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    with pytest.raises(UnclassifiedEngineError, match=f"at `{level}` that read fixes the snapshot"):
        scenario.run_conflict_case(case, port)
    assert port.levels == []
    assert port.reads == []
    assert port.writes == []


def test_a_staged_writer_runs_at_a_requested_read_committed_over_a_snapshot_root() -> None:
    case = _rooted(
        _load_case("m-concurrency-005"),
        uow={"concurrency": "optimistic", "isolation": "read-committed"},
        root={"isolation": "serializable"},
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    scenario.run_conflict_case(case, port)
    assert port.levels == ["read_committed"]
    assert len(port.writes) == 2


def _admitted(monkeypatch: pytest.MonkeyPatch) -> list[AdmittedWrite | PreparedTargetInstruction]:
    """Every write the lane hands a unit of work to buffer, in order, recorded
    before buffering judges it."""
    admitted: list[AdmittedWrite | PreparedTargetInstruction] = []
    buffer, buffer_insert, buffer_target = (
        UnitOfWork.buffer,
        UnitOfWork.buffer_insert,
        UnitOfWork.buffer_target,
    )

    def recorded(uow: UnitOfWork, item: ReadAuthorizedWrite | InsertionAuthorizedWrite) -> object:
        admitted.append(item)
        return buffer(uow, item)

    def recorded_insert(
        uow: UnitOfWork, insert: KeyedInsert, *, insertion_advice: KeyedWriteRefusalAdvice | None
    ) -> InsertionIdentity | None:
        admitted.append(insert)
        return buffer_insert(uow, insert, insertion_advice=insertion_advice)

    def recorded_target(uow: UnitOfWork, prepared: PreparedTargetInstruction) -> None:
        admitted.append(prepared)
        buffer_target(uow, prepared)

    monkeypatch.setattr(UnitOfWork, "buffer", recorded)
    monkeypatch.setattr(UnitOfWork, "buffer_insert", recorded_insert)
    monkeypatch.setattr(UnitOfWork, "buffer_target", recorded_target)
    return admitted


def test_a_compiled_group_writes_through_its_latest_insertion_across_flushes() -> None:
    # Each write of the object its group inserted is licensed by the insertion that
    # opened it, across the flushes its finds force: the amendment gates on the
    # inserted version, the deletion on the version that amendment produced, and
    # the amendment after the reinsertion on the reinsertion's own version.
    def write(mutation: str, **row: object) -> dict[str, object]:
        return {
            "uow": "g",
            "write": [{"mutation": mutation, "entity": "Account", "rows": [{"id": 9, **row}]}],
        }

    find = _account_find_step(9)
    steps = [
        write("insert", owner="N", balance="5.00"),
        find,
        write("amend", owner="Ada"),
        find,
        write("delete"),
        write("insert", owner="M", balance="1.00"),
        find,
        write("amend", owner="Bo"),
    ]
    compiled, _database_calls = scenario.compile_scenario_case(
        _synthetic_write("scenario", {"when": {"scenario": steps}}), "postgres"
    )
    assert [
        (emission.case_pointer, emission.sql.split(" ", 1)[0], emission.binds[-2:])
        for emission in compiled
        if not emission.sql.startswith("select")
    ] == [
        ("/scenario/0/write", "insert", (decimal.Decimal("5.00"), 1)),
        ("/scenario/2/write", "update", (9, 1)),
        ("/scenario/5/write", "delete", (9, 2)),
        ("/scenario/5/write", "insert", (decimal.Decimal("1.00"), 1)),
        ("/scenario/7/write", "update", (9, 1)),
    ]


def test_each_write_of_a_compiled_group_is_admitted_on_its_own_evidence() -> None:
    # An unversioned row's writes each carry evidence of their own object, so the
    # assignment flushed by the find and the deletion buffered after it are two
    # admitted writes rather than one claim spent twice.
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
    compiled, _database_calls = scenario.compile_scenario_case(case, "postgres")
    assert [(emission.case_pointer, emission.sql, emission.binds) for emission in compiled] == [
        ("/scenario/0/write", "update px.order_item set quantity = ? where id = ?", (9, 21)),
        (
            "/scenario/1/objectQuery",
            "select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on from px.order_item t0 "
            "where t0.id = ? for share of t0",
            (21,),
        ),
        ("/scenario/2/write", "delete from px.order_item where id = ?", (21,)),
    ]


def _account_amend(account_id: int, **members: object) -> dict[str, object]:
    return {"mutation": "amend", "entity": "Account", "rows": [{"id": account_id, **members}]}


def _submitted(monkeypatch: pytest.MonkeyPatch) -> list[PreparedKeyedInstruction]:
    """Every keyed write the simulated unit of work is asked to admit through
    the evidence it was given, recorded before admission judges it."""
    submitted: list[PreparedKeyedInstruction] = []
    admit = scenario._SimulatedUnit._admit_with_evidence  # pyright: ignore[reportPrivateUsage] - observes what the lane submits to its simulated unit of work

    def recorded(unit: Any, instruction: PreparedKeyedInstruction, *args: Any) -> None:
        submitted.append(instruction)
        admit(unit, instruction, *args)

    monkeypatch.setattr(
        scenario._SimulatedUnit,  # pyright: ignore[reportPrivateUsage] - observes what the lane submits to its simulated unit of work
        "_admit_with_evidence",
        recorded,
    )
    return submitted


@pytest.mark.parametrize(
    "writes",
    [
        pytest.param([_account_amend(1, balance="2.00")], id="assignment"),
        pytest.param([_account_amend(1)], id="no-op-amendment"),
        pytest.param([_account_amend(1), _account_amend(2, balance="2.00")], id="first-of-two"),
    ],
)
def test_a_compiled_versioned_write_no_evidence_licenses_is_refused_when_submitted(
    writes: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Neither an insertion of the simulated transaction nor an observed
    # version licenses the write, so it is refused as settling it would be,
    # before it is admitted, a later write is submitted, or anything flushes.
    submitted = _submitted(monkeypatch)
    admitted = _admitted(monkeypatch)
    case = _synthetic_write("writeSequence", {"when": {"writeSequence": writes}})
    with pytest.raises(
        UnclassifiedEngineError, match="requires the version its source observed"
    ) as raised:
        scenario.compile_write_sequence_case(case, "postgres")
    assert isinstance(raised.value.__cause__, UsageError)
    assert [named_members(instruction.rows[0])["id"] for instruction in submitted] == [1]
    assert admitted == []


@pytest.mark.parametrize(
    ("mutation", "row"),
    [
        ("amend", {"balance": "2.00"}),
        ("delete", {}),
        ("replace", {"owner": "Mira", "balance": "2.00"}),
    ],
)
def test_a_compiled_unversioned_write_naming_no_key_is_refused_for_its_missing_key(
    mutation: str, row: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    admitted = _admitted(monkeypatch)
    case = _synthetic_write(
        "writeSequence",
        {
            "model": "models/wallet.yaml",
            "when": {"writeSequence": [{"mutation": mutation, "entity": "Wallet", "rows": [row]}]},
        },
    )
    with pytest.raises(
        UnclassifiedEngineError, match="omits the primary-key member 'id'"
    ) as raised:
        scenario.compile_write_sequence_case(case, "postgres")
    cause = raised.value.__cause__
    assert isinstance(cause, InternalError) and cause.code == WRITE_PLANNING_FAILED
    assert admitted == []


@pytest.mark.parametrize("state_graded", [False, True])
def test_a_replayed_contiguous_group_replaces_sources_and_reports(
    state_graded: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("ordinary group entered compile machinery")

    monkeypatch.setattr(SimulatedWriteSteps, "__init__", refuse)
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
            "when": {"uow": {"retry": {"maxRetries": 1}}, "scenario": steps},
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
        assert [e.sql for e in run.emissions if e.sql.startswith(("insert", "update"))] == [
            sql for sql, _ in port.writes
        ]


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

    with pytest.raises(UnclassifiedEngineError, match="opened no value"):
        scenario.run_scenario_case(case, port)

    assert len(port.writes) == 1 and port.writes[0][0].startswith("insert")
    assert port.commits == 1 and port.rollbacks == 1


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
        with pytest.raises(UnclassifiedEngineError) as raised:
            scenario.run_scenario_case(case, port)
        refusal = raised.value.__cause__
        assert isinstance(refusal, UsageError)
        assert refusal.code == "transaction-time-pin-read-only"
        assert port.writes == [] and port.rollbacks == 1 and port.commits == 0
    else:
        run = scenario.run_scenario_case(case, port)
        assert port.writes[0][1][-1] == row["in_z"]
        assert len(port.writes) == 2 and run.database_calls == 4
        assert [item["at"] for item in run.step_rows] == ["/scenario/0", "/scenario/1"]
        assert port.commits == 1 and port.rollbacks == 0
