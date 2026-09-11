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
import functools
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import case_format, models, sweep
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._lanes import scenario
from parallax.conformance._lifecycle_observation import (
    LifecycleRun,
    execution_lifecycle_observation,
)
from parallax.conformance._mechanism import model_facts
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import predicate
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import (
    INFINITY,
    TIMESTAMP,
    TemporalBound,
)
from parallax.core.base import (
    Decimal as DecimalType,
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    Row,
)
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    EntityIdentity,
    PrimaryKey,
    Table,
    TemporalDimension,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.temporal_read import Edge
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
    WriteRejectedError,
    instructions,
)
from parallax.snapshot.handle import WriteEvidenceError
from tests.unit._metamodel_support import Declaration, attribute, source
from tests.unit.conformance._lanes._scripted_port import ScriptedPort
from tests.unit.conformance._recording_ports import FakeWritePort


# One corpus read serves the whole module, and both indexes project it: what
# they answer is shared between tests, so a test that edits a document takes
# `_own_copy` first.
@functools.cache
def _corpus() -> tuple[case_format.Case, ...]:
    return tuple(case_format.load_cases())


def _by_id(cases: Sequence[case_format.Case]) -> Mapping[str, case_format.Case]:
    # A case id is unique within its module, so a collision here means two case
    # files claim one id; keying them into a dict would silently resolve every
    # lookup to whichever file sorts last.
    index: dict[str, case_format.Case] = {}
    for case in cases:
        claimed = index.setdefault(case.case_id, case)
        if claimed is not case:
            raise ValueError(
                f"case id {case.case_id!r} is claimed by both "
                f"{claimed.path.name} and {case.path.name}"
            )
    return index


@functools.cache
def _reachable_by_id() -> Mapping[str, case_format.Case]:
    return _by_id(sweep.reachable_cases(cases=list(_corpus())))


@functools.cache
def _corpus_by_id() -> Mapping[str, case_format.Case]:
    return _by_id(_corpus())


def _case(case_id: str) -> case_format.Case:
    return _reachable_by_id()[case_id]


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these engine-function-level tests
    # exercise `run_conflict_case` on its own terms, never gated on whether
    # the case has ALSO been flipped visible in the sweep.
    return _corpus_by_id()[case_id]


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


def _ledger_row(row_id: int, value: str, *, in_z: str, acct_num: str = "B") -> Row:
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
                "rows": [{"id": 2, "value": value}],
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
    run = scenario.run_scenario_case(_case("m-unit-work-001"), port)
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
    run = scenario.run_scenario_case(_case("m-unit-work-011"), port)
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
    run = scenario.run_scenario_case(_case("m-unit-work-005"), port)
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


def _account(identifier: int, owner: str, balance: str, version: int) -> Row:
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
    assert [binds for _sql, binds in port.reads] == [(3,), (2, 3), (3,), (2, 3)]
    assert [e.binds for e in run.emissions if e.case_pointer.endswith("write")] == [
        (125.00, 2, 1, 1),
        (175.00, 3, 1, 2),
    ]
    assert run.round_trips == 6
    assert len(port.writes) == 2


def test_run_scenario_case_settles_on_the_named_delivery_rather_than_the_latest_one() -> None:
    # The observation a write settles against is the one the delivery it NAMES
    # recorded, never the group's most recent reading of the key: with
    # `m-unit-work-030`'s second write moved onto the FIRST delivery, the state it
    # reaches for is the one that delivery published — and the first write already
    # spent it, so this write is refused rather than gated on the version the
    # SECOND delivery observed. An implementation holding one observation per key,
    # or resolving a write from the group's latest reading, emits a `version = 2`
    # gate here and commits.
    source = _case("m-unit-work-030")
    document = cast(
        "dict[str, Any]",
        case_format.safe_load_yaml(source.path.read_text(encoding="utf-8")),
    )
    cast("list[dict[str, Any]]", cast("dict[str, Any]", document["when"])["scenario"])[3]["on"] = 0
    port = _two_delivery_port()

    with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
        scenario.run_scenario_case(
            dataclasses.replace(_case("m-unit-work-030"), document=document), port
        )


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
_PUBLISHED_CAR: Row = {"id": 1, "name": "Sedan", "version": 5, "doors": 4, "familyVariant": "Car"}


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


_ORDER_1_ROW: Row = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": decimal.Decimal("10.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 5),
}

_ORDER_ITEM_11_ROW: Row = {
    "id": 11,
    "order_id": 1,
    "sku": "A-100",
    "quantity": 2,
    "shipped_on": None,
}

_ORDER_ITEM_13_ROW: Row = {
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
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
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

    compiled, _round_trips = scenario.compile_scenario_case(case, "postgres")
    run = scenario.run_scenario_case(case, port)

    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]
    close, successor = compiled
    # The fixture milestone's OWN edge is what the close gates on, and the
    # successor carries the fixture's acct_num forward: facts only a seeded
    # tracker holds.
    assert close.binds[3] == _instant("2024-02-01T00:00:00+00:00")
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
    compiled, _round_trips = scenario.compile_scenario_case(case, "postgres")
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
    compiled, _round_trips = scenario.compile_scenario_case(case, "postgres")
    _insert, doomed_close, _doomed_successor, own_close, _own_successor, close, _successor = (
        compiled
    )
    assert doomed_close.binds[3] == _instant("2025-01-01T00:00:00+00:00")
    assert own_close.binds[3] == _instant("2026-01-01T00:00:00+00:00")
    assert close.case_pointer == "/scenario/3/write"
    assert close.binds[3] == _instant("2025-01-01T00:00:00+00:00")


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
    steps[2]["rollback"] = True
    case = _synthetic_write("scenario", {"when": {"scenario": steps}, "then": {"roundTrips": 3}})
    emissions, _round_trips = scenario.compile_scenario_case(case, "postgres")
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
        scenario._group_tx_instant(steps, 0, 1)  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
        == scenario.INERT_CLOCK_INSTANT
    )


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
    return scenario._settled_against_source(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
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
    with pytest.raises(EngineError, match="settles against observed 0 rows"):
        _settled(())


def test_a_settled_write_refuses_a_find_that_observed_several_rows_of_its_key() -> None:
    # No single value could have come from two milestones, so a reference that
    # resolves to both names nothing a write could have been handed.
    with pytest.raises(EngineError, match="settles against observed 2 rows"):
        _settled((_policy_node(_JAN, _JUN, "head"), _policy_node(_JUN, INFINITY, "tail")))


def test_a_write_step_naming_no_find_settles_against_tracked_state() -> None:
    assert (
        scenario._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"write": []}, 2, {}
        )
        is None
    )


def test_a_source_find_reference_names_one_index() -> None:
    with pytest.raises(EngineError, match="settles against ONE find step"):
        scenario._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"write": [], "on": [0, 1]}, 2, {}
        )


def test_a_source_find_reference_answers_what_that_find_published() -> None:
    # A find of the same group that published no row still answers, with an empty
    # record: the reference resolved, and it is the WRITE's own source resolution
    # that then finds no value to be addressed by.
    assert (
        scenario._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"write": [], "on": 1}, 2, {1: ()}
        )
        == ()
    )


def test_a_source_find_reference_names_a_find_of_its_own_group() -> None:
    # A reference the group's own recorded finds cannot satisfy names a step
    # outside the group, one that is not a find, or one that has not run yet —
    # refused rather than resolved to "the find observed nothing".
    with pytest.raises(EngineError, match="not an EARLIER find step"):
        scenario._source_find_nodes(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
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
    meta = model_facts.load_case_metamodel(_case("m-unit-work-001"))

    def settle(node: Any) -> object:
        write = scenario._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": "5.00"}]},
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
    meta = model_facts.load_case_metamodel(_case("m-unit-work-001"))
    with pytest.raises(EngineError, match="observed 0 rows"):
        scenario._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": "5.00"}]},
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
    meta = model_facts.load_case_metamodel(_case("m-txtime-write-001"))
    current = _balance_node("2024-04-01T00:00:00+00:00", "100.00")
    historical = _balance_node("2024-01-01T00:00:00+00:00", "90.00")

    def settle(node: Any) -> object:
        write = scenario._build_instructions(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            {
                "mutation": "update",
                "entity": "Balance",
                "rows": [{"id": 1, "value": "5.00"}],
            },
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
    run = scenario.run_scenario_case(_load_case("m-unit-work-015"), port)
    assert run.round_trips == 5
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
    with pytest.raises(EngineError, match="out-of-band statements may have overtaken"):
        scenario.run_write_sequence_case(_load_case("m-txtime-write-011"), port)


def test_a_tracked_milestone_under_columns_survives_out_of_band_statements() -> None:
    # The refusal is scoped to Relational Document Layout, where the tracked
    # members cannot even account for the row's SLOTS. Under `Columns` the tracker
    # holds every column, so out-of-band state leaves the observation STALE — the
    # very thing a conflict case authors on purpose — never unrepresentable.
    meta = model_facts.load_case_metamodel(_load_case("m-txtime-write-002"))
    model = meta
    shadow = TemporalShadow()
    shadow.note_out_of_band_write()
    scenario._refuse_unaccounted_document_milestone(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
        model,
        model_facts.case_entity(model, "parallax.compatibility.Balance"),
        {"id": 1},
        shadow,
    )


def test_a_tracked_milestone_of_a_document_target_chains_when_the_case_authored_it() -> None:
    # m-txtime-write-010 is the same document-mapped chain with no out-of-band
    # statement: every key in the stored document came from the case's own insert,
    # so the tracked milestone IS the whole stored row and the successor chains.
    # This is what keeps the refusal above narrow enough to leave the corpus alone.
    port = FakeWritePort(find_rows=[_VOYAGE_MILESTONE])
    emissions, _table_state, round_trips = scenario.run_write_sequence_case(
        _load_case("m-txtime-write-010"), port
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
    emissions, _table_state, round_trips = scenario.run_write_sequence_case(with_apply, port)
    assert round_trips == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert port.writes[0][0].startswith("insert into unrelated")


def test_a_read_step_names_its_own_object_query() -> None:
    with pytest.raises(EngineError, match="needs `objectQuery`"):
        scenario.step_query({"roundTrips": 1}, models.load_models()["account"])


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
        scenario._admitted_affected(MissingTargetError, raises)  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly


def test_run_conflict_case_temporal_close_propagates_a_failed_call() -> None:
    # A close the port could not complete is recorded as a FAILED Database Call
    # and then propagates: the lane admits only the shortfall class the case's own
    # facts imply, and a transient database failure is not one.
    with pytest.raises(DatabaseError):
        scenario.run_conflict_case(
            _load_case("m-temporal-read-010"),
            FakeWritePort(
                parameterized_write_failure=DatabaseError(
                    category="deadlock", native_code="40P01", message="deadlock detected"
                )
            ),
        )


def test_run_write_sequence_case_executes_each_entry_as_its_own_transaction() -> None:
    # Each writeSequence entry is its
    # OWN `db.transact` unit, never the whole sequence in one transaction.
    port = FakeWritePort()
    emissions, table_state, round_trips = scenario.run_write_sequence_case(
        _case("m-unit-work-003"), port
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
    emissions, table_state, round_trips = scenario.run_write_sequence_case(
        _load_case("m-txtime-write-002"), port
    )
    assert round_trips == 4
    assert [e.case_pointer for e in emissions] == [
        "/writeSequence/0",
        "/writeSequence/1",
        "/writeSequence/1",
    ]
    assert len(port.writes) == 3 and port.commits == 2
    assert table_state is not None and "balance" in table_state


def test_a_units_resolving_read_names_no_statement_in_the_lifecycle_observation() -> None:
    """The one call inside a write unit that the emissions do not hold.

    m-txtime-write-002 costs four round trips for three golden statements: the
    update entry reads the milestone it closes before writing it. A case counts
    that read and authors no golden for it, so the delivered stream carries a
    Database Call the emission order has no entry for — and the remaining calls
    still name that order in full, which is what makes the omission readable as
    the resolving read rather than as a lost index.
    """
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    run = LifecycleRun()
    emissions, _table_state, round_trips = scenario.run_write_sequence_case(
        _load_case("m-txtime-write-002"), port, run
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
    assert round_trips == len(calls)


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
    _emissions, table_state, round_trips = scenario.run_write_sequence_case(
        _load_case("m-bitemp-write-001"), port
    )
    assert round_trips == 6
    assert len(port.writes) == 5 and port.commits == 2
    assert table_state is not None and "position" in table_state


def test_compile_write_sequence_case_lowers_each_entry_without_cross_entry_coalescing() -> None:
    # m-unit-work-007 inserts then deletes the same rows across four entries; each entry is
    # its own flush, so it emits FOUR statements (never coalesced to a net-zero cancel).
    emissions, round_trips = scenario.compile_write_sequence_case(
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
    emissions, round_trips = scenario.compile_write_sequence_case(case, "postgres")
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
    with pytest.raises(EngineError, match="an insert row authors no `observedVersion`"):
        scenario.compile_write_sequence_case(case, "postgres")


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
                        "mutation": "update",
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
    emissions, round_trips = scenario.compile_write_sequence_case(case, "postgres")
    assert round_trips == 1
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
    _emissions, _table_state, round_trips = scenario.run_write_sequence_case(case, port)
    assert round_trips == 1
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
                        "mutation": "update",
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
    emissions, round_trips = scenario.compile_write_sequence_case(case, "postgres")
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
                        "mutation": "update",
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
    emissions, round_trips = scenario.compile_write_sequence_case(case, "postgres")
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
    emissions, round_trips = scenario.compile_write_sequence_case(case, "postgres")
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
                            {"id": 2, "balance": "5.00", "observedVersion": 1},
                        ],
                    }
                ]
            }
        },
    )
    emissions, round_trips = scenario.compile_write_sequence_case(case, "postgres")
    assert round_trips == 1
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
        {"when": {"writeSequence": [{"mutation": "update", "entity": "Account", "rows": rows}]}},
    )
    emissions, round_trips = scenario.compile_write_sequence_case(silent, "postgres")
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
                                    "lessThan": {"attr": "Wallet.balance", "value": "200.00"}
                                },
                            },
                        }
                    }
                ]
            },
        },
    )
    emissions, round_trips = scenario.compile_scenario_case(case, "postgres")
    assert round_trips == 1
    assert [e.sql for e in emissions] == ["delete from wallet where balance < ?"]
    assert emissions[0].binds == (decimal.Decimal("200.00"),)


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
                            "predicate": {
                                "lessThan": {"attr": "Wallet.balance", "value": "200.00"}
                            },
                        },
                    }
                ]
            },
        },
    )
    with pytest.raises(EngineError, match=r"scenario-write-only"):
        scenario.compile_write_sequence_case(case, "postgres")


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
                                    "lessThan": {"attr": "Wallet.balance", "value": "200.00"}
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
                            "predicate": {
                                "lessThan": {"attr": "Account.balance", "value": "200.00"}
                            },
                        },
                    },
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Account",
                                "predicate": {
                                    "lessThan": {"attr": "Account.balance", "value": "200.00"}
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
    run = scenario.run_scenario_case(case, port)
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
                                    "lessThan": {"attr": "Wallet.balance", "value": "200.00"}
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
                            "predicate": {
                                "lessThan": {"attr": "Account.balance", "value": "200.00"}
                            },
                        },
                    },
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Account",
                                "predicate": {
                                    "lessThan": {"attr": "Account.balance", "value": "200.00"}
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
    run = scenario.run_scenario_case(case, port)
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
            "assignments": [{"attr": "parallax.compatibility.Ledger.value", "value": "777.00"}],
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
    with pytest.raises(EngineError, match="materializing predicate write already moved"):
        scenario.run_scenario_case(case, _ledger_resolve_port())


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
    run = scenario.run_scenario_case(case, port)
    assert port.rollbacks == 1 and port.commits == 1
    close, _successor = run.emissions[-2:]
    assert close.case_pointer == "/scenario/2/write"
    assert close.binds[3] == _instant("2024-02-01T00:00:00+00:00")


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
    run = scenario.run_scenario_case(
        case,
        _ledger_resolve_port(
            _ledger_row(9, "100.00", in_z="2025-06-01T00:00:00+00:00", acct_num="D")
        ),
    )
    close = run.emissions[-2]
    assert close.case_pointer == "/scenario/3/write"
    assert close.binds[3] == _instant("2025-06-01T00:00:00+00:00")


def test_is_materializing_write_step_returns_none_for_a_keyed_write_shape() -> None:
    # `_is_materializing_write_step`'s SHAPE guard: a keyed-write step's
    # `write` field is the buffered-entry LIST (`m-case-format`'s
    # `bufferedWriteSequence` shape) — never a `PredicateWrite` pairing
    # candidate. Peeked by the scenario run lane's own one-step look-ahead
    # (`run_scenario_case`); no reachable corpus scenario puts an ungrouped
    # find immediately before an ungrouped keyed write (every such adjacency
    # is either `uow`-grouped or predicate-shaped), so this pins the guard
    # directly at the function level.
    meta = model_facts.load_case_metamodel(_case("m-unit-work-001"))
    step: Mapping[str, object] = {
        "write": [{"mutation": "insert", "entity": "Account", "rows": [{"id": 1}]}]
    }
    assert scenario.is_materializing_write_step(step, meta) is None


def test_is_materializing_write_step_returns_none_for_a_non_predicate_mapping() -> None:
    # Defensive coverage: a `write` field that IS a mapping but deserializes
    # to something other than a `PredicateWrite` (never schema-legal — the
    # mapping `write` shape is `predicateWrite`-only, `m-case-format`) still
    # falls through to `None` rather than an assertion failure.
    meta = model_facts.load_case_metamodel(_case("m-unit-work-001"))
    step: Mapping[str, object] = {
        "write": {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": 1.0}]}
    }
    assert scenario.is_materializing_write_step(step, meta) is None


def test_run_materializing_pair_rejects_a_mismatched_preceding_find_target() -> None:
    # `_run_materializing_pair`'s own internal target-match guard: its SOLE
    # production caller (`run_scenario_case`'s look-ahead) already verifies
    # the find step's own query `target` against `pairing.target.entity` before ever
    # calling this function, so the guard is unreachable through the public
    # entry point — a genuine caller-contract defense, pinned here by
    # calling the function directly with a manufactured mismatch.
    case = _case("m-unit-work-001")
    serving = model_facts.case_serving_model(case)
    meta = models.accepted_model_of(serving.current().model)
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
                    "predicate": {"lessThan": {"attr": "Account.balance", "value": "200.00"}},
                },
            }
        },
    ]
    context = scenario.CaseContext(serving, meta, "locking", TemporalShadow(), None)
    with pytest.raises(EngineError, match="not preceded by"):
        scenario._run_materializing_pair(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            FakeWritePort(),
            context,
            steps,
            0,
            LifecycleRun(),
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
                            "predicate": {"eq": {"attr": "Account.balance", "value": "100.00"}},
                        },
                    },
                    {
                        "write": {
                            "mutation": "delete",
                            "target": {
                                "entity": "Account",
                                "predicate": {
                                    "lessThan": {"attr": "Account.balance", "value": "200.00"}
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
    with pytest.raises(EngineError, match="SAME canonical predicate"):
        scenario.run_scenario_case(case, port)


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
_ACCOUNT_ROW_2: Final[Row] = {
    "id": 2,
    "owner": "Linus",
    "balance": decimal.Decimal("250.00"),
    "version": 1,
}


def test_run_conflict_case_single_attempt() -> None:
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW_2])
    emissions, affected, table_state, _round_trips = scenario.run_conflict_case(
        _load_case("m-opt-lock-006"), port
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
    emissions, affected, table_state, _round_trips = scenario.run_conflict_case(
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
    _emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
        _load_case("m-opt-lock-005"), port
    )
    assert affected == 0


def test_a_conflict_attempt_whose_source_read_finds_no_row_is_refused() -> None:
    # A target `given.apply` already removed leaves the attempt with no value to
    # write, so a case authoring that state is unauthorable through the public
    # verbs rather than merely unpleasant.
    port = FakeWritePort(find_rows=[])
    with pytest.raises(EngineError, match="found no row for"):
        scenario.run_conflict_case(_load_case("m-opt-lock-006"), port)


def test_a_conflict_attempt_declaring_a_version_its_read_did_not_observe_is_refused() -> None:
    # The declared `observedVersion` renders the golden's gate bind while the
    # real write settles against what the read saw, so the two must name one
    # state or the case grades a statement no read of this lane produced.
    port = FakeWritePort(find_rows=[{**_ACCOUNT_ROW_2, "version": 7}])
    with pytest.raises(EngineError, match="its own source read observed 7"):
        scenario.run_conflict_case(_load_case("m-opt-lock-006"), port)


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
    emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(case, port)
    assert [e.sql for e in emissions] == ["delete from account where id = ? and version = ?"]
    assert affected == 1


# The DRIVER spelling of the golden milestone close a fake port reports a
# zero-row shortfall for (the case's own `given.apply` already closed the current
# row out of band), so the naive literal `given.apply` statements the same lane
# applies first still report a row.
_BALANCE_CLOSE_SHORTFALL: Final[tuple[str, ...]] = ("update balance set out_z = %s",)


def test_run_conflict_case_renders_an_ungated_zero_row_close_as_a_stale_write() -> None:
    # m-temporal-read-012: the locking-mode close renders its address and no gate,
    # so its shortfall is the non-retriable stale write. The close lane settles
    # against a coordinate the case names rather than a source a read published,
    # which is why a Locking-mode conflict is expressible here and nowhere else
    # in this lane.
    _emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
        _load_case("m-temporal-read-012"),
        FakeWritePort(zero_affected_for=_BALANCE_CLOSE_SHORTFALL),
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
            {"id": 1, "balance": "500.00", "observedVersion": 1},
            {"id": 2, "balance": "500.00", "observedVersion": 1},
        ]
    )
    with pytest.raises(EngineError, match="an unversioned row authors no `observedVersion`"):
        scenario.run_conflict_case(case, FakeWritePort())


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
        scenario.run_conflict_case(
            _unversioned_conflict_case([{"id": 1, "balance": "500.00"}]), port
        )


def test_run_conflict_case_renders_a_gated_zero_row_close_as_a_conflict() -> None:
    _emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
        _load_case("m-temporal-read-010"),
        FakeWritePort(zero_affected_for=_BALANCE_CLOSE_SHORTFALL),
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

    def test_a_locking_shortfall_admitted_as_a_conflict_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The regression this pins: a lane admitting the retriable conflict where
        # the ungated locking-mode close's shortfall is the stale write. The real
        # failure must NOT be swallowed into the same `affectedRows: 0`
        # observation m-temporal-read-012 asserts.
        monkeypatch.setattr(
            scenario, "_implied_shortfall_error", _always_implying(OptimisticLockConflictError)
        )
        with pytest.raises(StaleWriteError):
            scenario.run_conflict_case(
                _load_case("m-temporal-read-012"),
                FakeWritePort(zero_affected_for=_BALANCE_CLOSE_SHORTFALL),
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


def test_run_conflict_case_refuses_a_multi_key_write_against_a_temporal_target() -> None:
    # A temporal target's write expands into a close plus its successors per key
    # and never collapses into one set-based statement, so the multi-key `write`
    # array — keyed and non-temporal — names no single milestone for the close to
    # address. It is refused rather than reduced to a row the case never chose.
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
    with pytest.raises(EngineError, match="closes one milestone row"):
        scenario.run_conflict_case(case, FakeWritePort())


def test_run_conflict_case_attempts_form_scripts_each_attempt_independently() -> None:
    # Each attempt takes its OWN source read, so the retry observes the generation
    # the concurrent writer left rather than reusing the stale one the first
    # attempt settled against.
    port = FakeWritePort(
        read_script=[
            [_ACCOUNT_ROW_2],
            [{**_ACCOUNT_ROW_2, "balance": decimal.Decimal("999.00"), "version": 2}],
        ]
    )
    emissions, affected, table_state, _round_trips = scenario.run_conflict_case(
        _load_case("m-opt-lock-007"), port
    )
    assert [e.case_pointer for e in emissions] == [
        "/when/attempts/0/write",
        "/when/attempts/1/write",
    ]
    assert len(port.writes) == 3  # given.apply + two independent scripted attempts
    assert affected == 1
    assert table_state is not None


def test_run_conflict_case_wraps_a_lowering_failure_as_engine_error() -> None:
    case = _synthetic_write("conflict", {"when": {"write": {"id": 1, "bogus": True}}})
    with pytest.raises(EngineError, match="undeclared member"):
        scenario.run_conflict_case(case, FakeWritePort())


def test_run_conflict_case_temporal_close_form_composes_plan_temporal_close() -> None:
    # m-txtime-write-006: a temporal optimistic-lock CLOSE conflict (`when.at` /
    # `when.observedTxStart`, no `observedVersion`) is driven through
    # `handle.plan_temporal_close`, not the non-temporal versioned-UPDATE path.
    case = _load_case("m-txtime-write-006")
    port = FakeWritePort()
    emissions, affected, table_state, _round_trips = scenario.run_conflict_case(case, port)
    assert [e.case_pointer for e in emissions] == ["/when/write"]
    assert emissions[0].sql == (
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert affected == 1
    assert len(port.writes) == 1
    assert table_state is not None and "balance" in table_state


def test_a_temporal_close_decodes_case_carriers_before_the_probe() -> None:
    # Compatibility's close-only form authors an integral JSON number and broad
    # ISO timestamps, but the probe and its SQL binds must receive the declared
    # Int64 and Timestamp managed values rather than those authored carriers.
    case = _synthetic_write(
        "conflict",
        {
            "model": "models/balance.yaml",
            "when": {
                "uow": {"concurrency": "optimistic"},
                "write": {"id": 2.0},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-02-01T00:00:00+00:00",
            },
        },
    )
    emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
        case, FakeWritePort()
    )
    binds = emissions[0].binds
    assert affected == 1
    assert type(binds[1]) is int and binds[1] == 2
    assert isinstance(binds[0], dt.datetime)
    assert isinstance(binds[3], dt.datetime)


def test_a_decimal_temporal_key_requires_its_canonical_wire_string() -> None:
    # Compatibility's standalone close has no generic prepared-write ingress, so
    # its local declared-type preparation must accept canonical Decimal Wire and
    # reject a JSON number before either value can become a planned key or bind.
    entity = EntityIdentity("parallax.test", "DecimalTemporal")
    model = form_metamodel(
        source(
            Declaration(
                identity=entity,
                container=Table("decimal_temporal"),
                attributes=(
                    attribute(
                        entity,
                        "id",
                        type=DecimalType(6, 2),
                        primary_key=PrimaryKey(),
                    ),
                    attribute(entity, "txStart", type=TIMESTAMP),
                    attribute(entity, "txEnd", type=TIMESTAMP),
                ),
                as_of_axes=(
                    AsOfAxisMetadata(
                        TemporalDimension.TRANSACTION_TIME,
                        AttributeIdentity(entity, "txStart"),
                        AttributeIdentity(entity, "txEnd"),
                    ),
                ),
            )
        )
    )
    accepted = scenario._conflict_close_inputs(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
        model,
        entity.canonical,
        {"id": "12.30"},
        "2024-10-01T00:00:00+00:00",
        "2024-02-01T00:00:00+00:00",
        None,
        None,
    )
    assert accepted.identity == (("id", decimal.Decimal("12.30")),)
    with pytest.raises(EngineError, match="neutral-literal-type-mismatch"):
        scenario._conflict_close_inputs(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            model,
            entity.canonical,
            {"id": 12.30},
            "2024-10-01T00:00:00+00:00",
            "2024-02-01T00:00:00+00:00",
            None,
            None,
        )
    with pytest.raises(EngineError, match="neutral-literal-noncanonical"):
        scenario._conflict_close_inputs(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            model,
            entity.canonical,
            {"id": "12.3"},
            "2024-10-01T00:00:00+00:00",
            "2024-02-01T00:00:00+00:00",
            None,
            None,
        )


def test_conflict_close_rejects_axis_specific_inputs_on_a_transaction_time_target() -> None:
    model = models.load_models()["balance"]
    target_name = "parallax.compatibility.Balance"
    common = (model, target_name, {"id": 2}, "2024-10-01T00:00:00+00:00")

    with pytest.raises(EngineError, match="exactly its primary-key members"):
        scenario._conflict_close_inputs(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            model,
            target_name,
            {"id": 2, "extra": 3},
            "2024-10-01T00:00:00+00:00",
            None,
            None,
            None,
        )
    with pytest.raises(EngineError, match="axis the target does not declare"):
        scenario._conflict_close_inputs(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            *common, None, "2024-01-01T00:00:00+00:00", None
        )
    for bound in ("infinity", "2024-06-01T00:00:00+00:00"):
        with pytest.raises(EngineError, match="axis the target does not declare"):
            scenario._conflict_close_inputs(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
                *common, None, None, bound
            )
    assert (
        scenario._decode_observed_conflict_bound(  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
            None, TemporalBound.INFINITY, position="validEnd"
        )
        is TemporalBound.INFINITY
    )


def test_predicate_writes_require_no_keyed_unit_source_read_or_framework_classification() -> None:
    model = models.load_models()["account"]
    instruction = instructions.PredicateWrite(
        "update",
        instructions.PredicateSelection("parallax.compatibility.Account", predicate.All()),
        (instructions.WriteAssignment("parallax.compatibility.Account.owner", "Ada"),),
    )
    prepared = instructions.prepare_typed_write(instruction, model)
    assert isinstance(prepared, instructions.PreparedPredicateWrite)
    resolved = scenario._ResolvedWrite(prepared, None)  # pyright: ignore[reportPrivateUsage] - unit test builds the scenario lane's private record directly

    assert scenario._unit_source_reads(model, (resolved,)) == []  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly
    assert scenario._is_framework_write(prepared, model) is False  # pyright: ignore[reportPrivateUsage] - unit test drives the scenario lane's private helper directly


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
            False,
            {"ambiguous": 1},
        )


@pytest.mark.parametrize("bad_key", ["2", True, 2.5])
def test_a_temporal_close_rejects_a_malformed_primary_key_before_planning(
    bad_key: object,
) -> None:
    # Compatibility's close-only row must satisfy its family-effective primary
    # key's declared Int64 Wire contract, so string, boolean, and fractional
    # carriers all stop before the close probe can turn one into an SQL bind.
    case = _synthetic_write(
        "conflict",
        {
            "model": "models/balance.yaml",
            "when": {
                "uow": {"concurrency": "optimistic"},
                "write": {"id": bad_key},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-02-01T00:00:00+00:00",
            },
        },
    )
    with pytest.raises(EngineError, match="primary key `id` is neutral-literal"):
        scenario.run_conflict_case(case, FakeWritePort())


@pytest.mark.parametrize(
    ("model", "when", "position"),
    [
        (
            "models/balance.yaml",
            {
                "write": {"id": 2},
                "at": "not-an-instant",
                "observedTxStart": "2024-02-01T00:00:00+00:00",
            },
            "at",
        ),
        (
            "models/balance.yaml",
            {
                "write": {"id": 2},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "not-an-instant",
            },
            "observedTxStart",
        ),
        (
            "models/position.yaml",
            {
                "write": {"id": 1},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-04-01T00:00:00+00:00",
                "observedValidStart": "not-an-instant",
            },
            "observedValidStart",
        ),
        (
            "models/position.yaml",
            {
                "write": {"id": 1, "validEnd": "not-an-instant"},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-04-01T00:00:00+00:00",
            },
            "validEnd",
        ),
    ],
)
def test_a_temporal_close_rejects_each_malformed_coordinate_before_planning(
    model: str, when: dict[str, object], position: str
) -> None:
    # Compatibility's temporary close form carries four independently authored
    # coordinates; each must fail at its resolved Timestamp boundary rather than
    # reaching milestone selection, close planning, execution, or driver binds.
    when["uow"] = {"concurrency": "optimistic"}
    case = _synthetic_write("conflict", {"model": model, "when": when})
    with pytest.raises(EngineError, match=position):
        scenario.run_conflict_case(case, FakeWritePort())


def test_a_bitemporal_close_preserves_only_the_authored_wire_open_bound() -> None:
    # Compatibility's address form may author the exact `infinity` Wire sentinel
    # for Valid-Time, which remains the framework open bound while every finite
    # coordinate is decoded to datetime; a pre-managed sentinel is not an
    # alternative serialized spelling and is refused before planning.
    case = _edge_named_close(
        {
            "uow": {"concurrency": "optimistic"},
            "write": {"id": 1, "validEnd": "infinity"},
            "at": "2024-10-01T00:00:00+00:00",
            "observedTxStart": "2024-04-01T00:00:00+00:00",
        }
    )
    emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
        case, FakeWritePort()
    )
    assert affected == 1
    assert emissions[0].binds[2] == "infinity"
    managed_bound = _edge_named_close(
        {
            "uow": {"concurrency": "optimistic"},
            "write": {"id": 1, "validEnd": TemporalBound.INFINITY},
            "at": "2024-10-01T00:00:00+00:00",
            "observedTxStart": "2024-04-01T00:00:00+00:00",
        }
    )
    with pytest.raises(EngineError, match="neutral-literal-type-mismatch"):
        scenario.run_conflict_case(managed_bound, FakeWritePort())


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
    with pytest.raises(EngineError, match=re.escape(refusal)):
        scenario.run_conflict_case(case, FakeWritePort())


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
        emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "write": {"id": 1},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "observedValidStart": valid_start,
                }
            ),
            port,
        )
        assert affected == 1
        assert emissions[0].sql == (
            "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ? "
            "and in_z = ?"
        )
        heads.append(list(emissions[0].binds))
    assert heads[0] == [
        _instant("2024-10-01T00:00:00+00:00"),
        1,
        _instant("2024-06-01T00:00:00+00:00"),
        "infinity",
        _instant("2024-04-01T00:00:00+00:00"),
    ]
    assert heads[1] == [
        _instant("2024-10-01T00:00:00+00:00"),
        1,
        "infinity",
        "infinity",
        _instant("2024-04-01T00:00:00+00:00"),
    ]


def test_a_close_naming_both_an_observed_edge_and_an_authored_address_is_refused() -> None:
    # The two spell the same fact from opposite ends. Agreeing, the authored
    # address proves nothing the derivation does not; disagreeing, one of them
    # would silently win — and whichever won, the case would be asserting the
    # other one's claim.
    with pytest.raises(EngineError, match=re.escape("never both")):
        scenario.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "write": {"id": 1, "validEnd": "2024-06-01T00:00:00+00:00"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "observedValidStart": "2024-01-01T00:00:00+00:00",
                }
            ),
            FakeWritePort(),
        )


def test_a_non_temporal_conflict_target_may_not_name_an_observed_milestone() -> None:
    # A versioned target has one row per key and no milestone to observe, so the
    # coordinates would be read by nothing: the versioned conflict path never
    # looks at them, and a case authoring one would silently grade the shape it
    # did not mean to.
    with pytest.raises(EngineError, match=re.escape("no milestone to observe")):
        scenario.run_conflict_case(
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
            FakeWritePort(),
        )


def test_a_non_temporal_retry_attempt_may_not_name_an_observed_milestone_either() -> None:
    # The target's entitlement holds wherever the coordinate is spelled. Checking
    # only the root `when` would let the same unentitled coordinate through on
    # the retry form, where the versioned path reads it exactly as little.
    with pytest.raises(EngineError, match=re.escape("no milestone to observe")):
        scenario.run_conflict_case(
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
            FakeWritePort(),
        )


def test_a_retry_attempt_may_not_name_its_observed_milestones_edge() -> None:
    # An edge selects among the milestones the case's own fixtures hold, while a
    # retry re-reads what the concurrent `given.apply` writer left behind. No
    # lane performs the resolving read that would reconcile the two, so the
    # observation form is single-attempt only rather than resolving against
    # state the retry has already superseded.
    with pytest.raises(EngineError, match=re.escape("names its observed milestone")):
        scenario.run_conflict_case(
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
            FakeWritePort(),
        )


def test_a_retry_sequence_may_not_leave_an_observation_coordinate_on_the_root() -> None:
    # The retry lane reads each attempt's own `at` / `observedTxStart` and never
    # the root `when`'s, so a root coordinate beside `attempts` is consumed by no
    # attempt and would sit in the document grading nothing. The two authoring
    # locations are alternatives, not a default and an override.
    with pytest.raises(EngineError, match=re.escape("consumed by no attempt")):
        scenario.run_conflict_case(
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
            FakeWritePort(),
        )


def test_a_locking_close_may_not_author_a_lone_observed_gate() -> None:
    # Locking mode renders no gate at all, so the address form's gate candidate
    # reaches nothing: `plan_temporal_close` takes the coordinate and drops it,
    # and the case would claim a gate its own golden cannot carry.
    with pytest.raises(EngineError, match=re.escape("renders no gate")):
        scenario.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "locking"},
                    "write": {"id": 1, "validEnd": "2024-06-01T00:00:00+00:00"},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                }
            ),
            FakeWritePort(),
        )


def test_a_locking_retry_attempt_may_not_author_an_observed_gate() -> None:
    # A retry attempt never names an edge, so its `observedTxStart` is always the
    # gate candidate — checking only the root would let the same unentitled
    # coordinate through per attempt.
    with pytest.raises(EngineError, match=re.escape("renders no gate")):
        scenario.run_conflict_case(
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
            FakeWritePort(),
        )


def test_a_locking_close_may_still_name_its_observed_milestones_edge() -> None:
    # Beside `observedValidStart` the Transaction-Time coordinate is the edge's
    # own half, which SELECTS the milestone whose `thru_z` the address binds.
    # That selection happens in either mode; only the gate is optimistic-only,
    # so the locking golden carries the derived address and no `in_z` predicate.
    emissions, affected, _table_state, _round_trips = scenario.run_conflict_case(
        _edge_named_close(
            {
                "uow": {"concurrency": "locking"},
                "write": {"id": 1},
                "at": "2024-10-01T00:00:00+00:00",
                "observedTxStart": "2024-04-01T00:00:00+00:00",
                "observedValidStart": "2024-01-01T00:00:00+00:00",
            }
        ),
        FakeWritePort(),
    )
    assert affected == 1
    assert emissions[0].sql == (
        "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?"
    )
    assert list(emissions[0].binds) == [
        _instant("2024-10-01T00:00:00+00:00"),
        1,
        _instant("2024-06-01T00:00:00+00:00"),
        "infinity",
    ]


def test_a_close_naming_an_edge_no_current_milestone_carries_is_refused() -> None:
    # A named milestone that the case's own state does not hold is an authoring
    # defect, not a stale gate: falling back to whichever rectangle the key
    # happens to hold is the misresolution the naming exists to remove.
    with pytest.raises(EngineError, match=re.escape("no current milestone of this key")):
        scenario.run_conflict_case(
            _edge_named_close(
                {
                    "uow": {"concurrency": "optimistic"},
                    "write": {"id": 1},
                    "at": "2024-10-01T00:00:00+00:00",
                    "observedTxStart": "2024-04-01T00:00:00+00:00",
                    "observedValidStart": "2023-01-01T00:00:00+00:00",
                }
            ),
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
    with pytest.raises(EngineError, match=re.escape("a temporal write entry carries ONE")):
        scenario.compile_scenario_case(case, "postgres")


def test_run_conflict_case_resolves_target_from_the_inheritance_family() -> None:
    # m-inheritance-105: `when.write` names no entity of its own; for an
    # inheritance-participant model `_conflict_target` resolves to the family's
    # SOLE concrete subtype (MeterReading, tag `meter`) — never the abstract
    # root the REJECTED lane's own default-target convention resolves to.
    case = _load_case("m-inheritance-105")
    port = FakeWritePort()
    emissions, affected, table_state, _round_trips = scenario.run_conflict_case(case, port)
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
    case = _load_case("m-temporal-read-011")
    port = FakeWritePort()
    emissions, affected, table_state, _round_trips = scenario.run_conflict_case(case, port)
    assert [e.case_pointer for e in emissions] == [
        "/when/attempts/0/write",
        "/when/attempts/1/write",
    ]
    assert len(port.writes) == 4  # given.apply's two out-of-band statements + two attempts
    assert affected == 1
    assert table_state is not None and "balance" in table_state


def test_scenario_case_without_when_is_rejected() -> None:
    with pytest.raises(EngineError, match="has no `when`"):
        scenario.compile_scenario_case(_synthetic_write("scenario", {}), "postgres")


def test_scenario_case_without_a_scenario_list_is_rejected() -> None:
    with pytest.raises(EngineError, match=r"when\.scenario"):
        scenario.compile_scenario_case(_synthetic_write("scenario", {"when": {}}), "postgres")


def test_scenario_read_step_missing_its_query_is_rejected() -> None:
    bad = _synthetic_write("scenario", {"when": {"scenario": [{"roundTrips": 1}]}})
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
    assert run.round_trips == 3  # the step's own read + its one DELETE + the dependent find
    assert next(sql for sql, _binds in port.reads) == (
        "select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on"
        " from order_item t0 where t0.id in (%s) for share of t0"
    )
    assert [sql for sql, _binds in port.writes] == ["delete from order_item where id = %s"]


def test_a_temporal_terminate_entry_reaches_its_own_wire_verb() -> None:
    port = FakeWritePort(find_rows=[_balance_row(1, "100.00", in_z="2024-01-01T00:00:00+00:00")])
    _emissions, _table_state, round_trips = scenario.run_write_sequence_case(
        _load_case("m-txtime-write-003"), port
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
    _emissions, _table_state, round_trips = scenario.run_write_sequence_case(
        _load_case("m-bitemp-write-002"), port
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
    run = scenario.run_scenario_case(_load_case(case_id), port)
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
                    "predicate": {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
                "roundTrips": 1,
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
                                "rows": [{"id": 1, "balance": "5.00", "observedVersion": 1}],
                            }
                        ],
                        "on": 0,
                        "roundTrips": 1,
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
                        "transaction-time": {"asOf": "2024-03-01T00:00:00.000000Z"},
                    },
                },
                "roundTrips": 1,
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
    scenario.run_scenario_case(case, port)
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
                "roundTrips": 2,
            }
        ],
    )
    with pytest.raises(EngineError, match="buffer's only entry"):
        scenario.run_scenario_case(case, FakeWritePort())


def _pk_sequence_advance(**step: object) -> dict[str, object]:
    return {"write": [_registry_advance("badge_seq")], "roundTrips": 1, **step}


def test_an_aborted_framework_write_step_executes_its_dml_and_rolls_back() -> None:
    # A registry advance runs through the planner rather than a verb, but it is
    # still a whole choreography unit and answers to the same abort contract: the
    # statement reaches the wire and counts its round trip, and the provider then
    # rolls it back. Committing it would leave a `rollback: true` step's DML
    # durable, which is the one thing the step declares it is not.
    port = FakeWritePort()
    run = scenario.run_scenario_case(
        _synthetic_scenario(
            "models/pk-sequence.yaml", "m-pk-gen-998", [_pk_sequence_advance(rollback=True)]
        ),
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
    with pytest.raises(EngineError, match="choreography unit of its own"):
        scenario.run_scenario_case(case, FakeWritePort())


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
    scenario.run_scenario_case(case, port)
    assert [sql for sql, _binds in port.writes] == ["update customer set name = %s where id = %s"]
