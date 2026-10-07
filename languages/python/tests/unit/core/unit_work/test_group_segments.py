"""A Materialized Write Group's temporal segment (`m-unit-work` *Materialized
Write Groups*, `m-temporal-write` *Temporal expansion*), settled through the
production planner: one step built per index from the group's evidence and its
settled backing, rows the attempt opened revised or removed at their address,
the effective members a surviving row overlays, and agreement with the same
row written by a keyed write."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import FunctionType, MethodType
from typing import Any, Final, cast

import pytest

from parallax.core import predicate as predicate_algebra
from parallax.core.base import INFINITY, FrozenMap
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import (
    PreparedEffectiveChange,
    prepare_effective_change,
)
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
)
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write import expansion as expansion_module
from parallax.core.temporal_write.coverage import Successor
from parallax.core.temporal_write.expansion import PredecessorExpander, PredecessorExpansion
from parallax.core.unit_work import (
    BufferItem,
    Concurrency,
    KeyedWrite,
    MaterializedWriteGroup,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    TransactionInstant,
    VersionedEvidenceBuilder,
    WriteAssignment,
    WritePlanningRequest,
    buffered_write,
    object_key,
)
from parallax.core.unit_work import group_segments as group_segments_module
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    prepare_typed_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    PredecessorRows,
    PredecessorRowsBuilder,
    TemporalObservation,
    VersionObservation,
    WriteObservation,
    WritePlan,
    WritePlanningError,
)
from parallax.core.write_plan.columns import ColumnSlice
from parallax.core.write_plan.keys import ObservedStateKey
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    Derivation,
    Descent,
    ExecutionUnit,
    OwnedEndpoint,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    CarriedFrom,
    ChangedFrom,
    Finite,
    InsertEntry,
    PlannedRow,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    PlannedWrite,
    TemporalUpperBound,
)
from tests._support.clock_probes import inert_instant, instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._gc_reachability import reachable_objects
from tests.unit._positional_row_support import positional_row
from tests.unit._temporal_group_support import temporal_group
from tests.unit.core.unit_work._ownership_support import OpenedRows

_ACCOUNT = corpus_model("account")
_BALANCE = corpus_model("balance")
_POSITION = corpus_model("position")
_WALLET = corpus_model("wallet")


# The planner threads its Transaction Instant through untouched to whichever
# stage first needs it, so every non-temporal test below shares one uncaptured
# holder rather than pinning an instant it would never read.
_INSTANT = inert_instant()


type _TestBufferItem = BufferItem | KeyedWrite | PredicateWrite


def _plan(
    buffer: Sequence[_TestBufferItem],
    model: Metamodel,
    *,
    observations: dict[ObjectKey, WriteObservation] | None = None,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> WritePlan:
    return build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=tx_instant if tx_instant is not None else _INSTANT,
            concurrency=concurrency,
            buffered_writes=observed_buffer(buffer, model, observations),
        )
    )


def _row_values(row: PlannedRow) -> dict[str, object]:
    values: dict[str, object] = {ident.name: value for ident, value in row.attributes.items()}
    for ident, value in row.value_objects.items():
        values[ident.path[-1]] = value
    return values


def _insert_rows(step: PlannedWrite) -> list[dict[str, object]]:
    assert isinstance(step, PlannedInsert)
    return [_row_values(entry.row) for entry in step.entries]


def _step_entity(step: PlannedWrite) -> str:
    return step.entity.name


def _step_mutation(step: PlannedWrite) -> str:
    if isinstance(step, PlannedInsert):
        return "insert"
    if isinstance(step, PlannedUpdate):
        return "update"
    if isinstance(step, PlannedClose):
        return "close"
    return "delete"


def _prepared_keyed(write: KeyedWrite, model: Metamodel) -> PreparedKeyedWrite:
    prepared = prepare_typed_write(write, model)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _version_group(
    entity: str,
    mutation: PredicateMutation,
    key_name: str,
    rows: Sequence[tuple[object, int]],
    assignments: Sequence[WriteAssignment] = (),
    model: Metamodel | None = None,
) -> MaterializedWriteGroup:
    """A minimal Materialized Write Group for planner-seam tests.

    ``rows`` is ``(key value, observed version)`` per resolved row; every row
    shares ``assignments`` uniformly, the real shape a materializing predicate
    write settles to (`m-unit-work` "Materialized Write Groups") — a
    Materialized Write Group carries no per-row assigned value, only per-row
    key and observation columns.
    """
    del key_name
    evidence = VersionedEvidenceBuilder(key_position=0, version_position=1)
    for key_value, version in rows:
        evidence.append((key_value, version))
    sealed = evidence.seal()
    assert sealed is not None
    predicate = PredicateWrite(
        mutation,
        PredicateSelection(
            entity, predicate_algebra.Comparison("lessThan", f"{entity}.balance", "1000000.00")
        ),
        assignments=tuple(
            WriteAssignment(
                assignment.attr,
                Decimal(str(assignment.value))
                if assignment.attr.endswith(".balance") and isinstance(assignment.value, float)
                else assignment.value,
            )
            for assignment in assignments
        ),
    )
    prepared = prepare_typed_write(
        predicate, model if model is not None else (_WALLET if entity == "Wallet" else _ACCOUNT)
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return MaterializedWriteGroup(mutation=prepared, evidence=sealed)


def _shape(plan: WritePlan) -> list[tuple[str, str]]:
    return [(_step_mutation(step), _step_entity(step)) for step in plan.steps]


# --------------------------------------------------------------------------- #
# One temporal settlement for both representations: the eagerly settled        #
# instruction and the Materialized Write Group decide the same facts and emit  #
# from them the same way, so the two cannot drift.                             #
# --------------------------------------------------------------------------- #
_BALANCE_PREDECESSOR: dict[str, object] = {
    "id": 1,
    "acctNum": "A",
    "value": Decimal("1.00"),
    "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "txEnd": INFINITY,
}


def _one_row_temporal_group(assigned: Decimal) -> MaterializedWriteGroup:
    """A Materialized Write Group resolving the one row
    :data:`_BALANCE_PREDECESSOR` describes, under the same update."""
    return temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "1000000.00")
            ),
            assignments=(WriteAssignment("Balance.value", assigned),),
        ),
        _BALANCE,
        [_BALANCE_PREDECESSOR],
    )


def test_one_temporal_row_settles_identically_addressed_and_materialized() -> None:
    # The same observed row, the same authored change, the same instant, and
    # the same concurrency mode, reaching settlement through its two
    # representations: an addressed keyed write settled eagerly, and a
    # one-row Materialized Write Group settled into a segment that emits on
    # demand. Every temporal fact — the topology's close cause, the axis the
    # gate binds, the successors and their represented state, the resolved
    # instant — is decided in one place for both, so the two plans must be
    # equal step for step. A drift between the arms is precisely what a
    # second derivation site would produce.
    assigned = Decimal("9.00")
    addressed = KeyedWrite("update", "Balance", ({"id": 1, "value": assigned},))
    key_ = object_key(addressed, _BALANCE)
    assert key_ is not None
    eager = _plan(
        [addressed],
        _BALANCE,
        observations={
            key_: TemporalObservation(predecessor=PredecessorRow(members=_BALANCE_PREDECESSOR))
        },
        concurrency="optimistic",
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    materialized = _plan(
        [_one_row_temporal_group(assigned)],
        _BALANCE,
        concurrency="optimistic",
        tx_instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    assert _shape(eager) == [("close", "Balance"), ("insert", "Balance")]
    assert list(materialized.steps) == list(eager.steps)


def test_one_versioned_row_settles_identically_addressed_and_materialized() -> None:
    # The non-temporal counterpart. The same observed row, the same authored
    # value, and the same concurrency mode, reaching settlement through its two
    # representations: an addressed keyed update settled eagerly, and a one-row
    # Materialized Write Group settled into a segment that emits on demand. Every
    # non-temporal fact — the family-effective key the target addresses by, the
    # version Attribute, the gate the observation binds, the advanced version the
    # update assigns, and how a shortfall classifies — is decided in one place for
    # both, so a single addressed row and a single resolved row must agree
    # exactly. Their CARDINALITY is the one thing they do not share, and it is
    # not in evidence here: both plans carry one step over one key.
    assigned = Decimal("5.00")
    addressed = KeyedWrite("update", "Account", ({"id": 9, "balance": assigned},))
    key_ = object_key(addressed, _ACCOUNT)
    assert key_ is not None
    eager = _plan(
        [addressed],
        _ACCOUNT,
        observations={key_: VersionObservation(observed_version=1)},
        concurrency="optimistic",
    )
    materialized = _plan(
        [
            _version_group(
                "Account", "update", "id", [(9, 1)], [WriteAssignment("Account.balance", assigned)]
            )
        ],
        _ACCOUNT,
        concurrency="optimistic",
    )
    (settled,) = eager.steps
    assert isinstance(settled, PlannedUpdate)
    assert list(materialized.steps) == [settled]


# --------------------------------------------------------------------------- #
# A temporal group's step access builds exactly the one step it names, and    #
# only a carried or changed successor reads a Predecessor Row.                 #
# --------------------------------------------------------------------------- #
_OPENED_AT = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_WINDOW_FROM = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_WINDOW_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _temporal_topology_group(
    model: Metamodel, entity: str, mutation: PredicateMutation, rows: int = 3
) -> MaterializedWriteGroup:
    bitemporal = entity == "Position"
    bounded = mutation.endswith("Until")
    bounds: tuple[dt.datetime, ...] = (
        (_WINDOW_FROM, _WINDOW_UNTIL) if bounded else (_WINDOW_FROM,) if bitemporal else ()
    )
    axes: dict[str, object] = {"validStart": _OPENED_AT, "validEnd": INFINITY} if bitemporal else {}
    return temporal_group(
        PredicateWrite(
            mutation,
            PredicateSelection(
                entity, predicate_algebra.Comparison("lessThan", f"{entity}.value", "100.00")
            ),
            (WriteAssignment(f"{entity}.value", Decimal("9.00")),)
            if mutation.startswith("update")
            else (),
            *bounds,
        ),
        model,
        [
            {
                "id": key,
                "acctNum": "A",
                "value": Decimal("1.00"),
                **axes,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
            for key in range(1, rows + 1)
        ],
    )


class _Constructions:
    """Counts the planned steps and Predecessor Rows built from now on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.steps = 0
        self.predecessors = 0
        for step_type in (PlannedClose, PlannedInsert):
            original = step_type.__init__

            def counting(
                step: object, *args: object, _original: Any = original, **kwargs: object
            ) -> None:
                self.steps += 1
                _original(step, *args, **kwargs)

            monkeypatch.setattr(step_type, "__init__", counting)
        over_row = PredecessorRow.over_row

        def adopted(*args: Any) -> PredecessorRow:
            self.predecessors += 1
            return over_row(*args)

        monkeypatch.setattr(PredecessorRow, "over_row", adopted)


@pytest.mark.parametrize(
    ("entity", "mutation", "steps_per_row"),
    [
        ("Balance", "update", 2),
        ("Balance", "terminate", 1),
        ("Position", "update", 3),
        ("Position", "terminate", 2),
        ("Position", "updateUntil", 4),
        ("Position", "terminateUntil", 3),
    ],
)
def test_indexing_a_temporal_group_constructs_only_the_requested_step(
    monkeypatch: pytest.MonkeyPatch, entity: str, mutation: PredicateMutation, steps_per_row: int
) -> None:
    model = _BALANCE if entity == "Balance" else _POSITION
    plan = _plan([_temporal_topology_group(model, entity, mutation)], model)
    settled = list(plan.steps)
    assert len(settled) == 3 * steps_per_row
    constructed = _Constructions(monkeypatch)

    for index in range(len(settled)):
        assert plan.steps[index] == settled[index]
    assert constructed.steps == len(settled)
    # A row's successors, asked for in turn, share one Predecessor Row.
    opens_successors = steps_per_row > 1
    assert constructed.predecessors == 3 * opens_successors

    constructed.steps = constructed.predecessors = 0
    last, first = len(settled) - 1, 0
    for index in (last, first, last):
        assert plan.steps[index] == settled[index]
    assert constructed.steps == 3
    # A row's Predecessor Row is kept only while more of its successors follow:
    # its last successor lets go of it, so asking for that step again builds
    # an equal one.
    assert constructed.predecessors == 2 * opens_successors


def test_a_temporal_groups_marker_no_opened_row_expresses_is_refused_while_planning() -> None:
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "100.00")
            ),
            (WriteAssignment("Balance.acctNum", {"increment": 1}),),
        ),
        _BALANCE,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": Decimal("1.00"),
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
        ],
    )
    with pytest.raises(WritePlanningError, match="not recognized for insert planning"):
        _plan([group], _BALANCE)


def test_a_bitemporal_close_refuses_a_row_that_holds_no_valid_time_end() -> None:
    group = temporal_group(
        PredicateWrite(
            "terminate",
            PredicateSelection(
                "Position", predicate_algebra.Comparison("lessThan", "Position.value", "100.00")
            ),
            valid_from=_WINDOW_FROM,
        ),
        _POSITION,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": Decimal("1.00"),
                "validStart": _OPENED_AT,
                "validEnd": None,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
        ],
    )
    # A close addresses one exclusive upper bound per As-Of Axis, and this row
    # supplies none on Valid Time, which settling the group refuses before any
    # step exists to be asked for.
    with pytest.raises(WritePlanningError, match="no observed Valid-Time end"):
        _plan([group], _POSITION)


# --------------------------------------------------------------------------- #
# Effective change is established by the producer: a surviving row of a       #
# multi-assignment group carries the members it restores.                     #
# --------------------------------------------------------------------------- #
def _comparisons(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"prepared": 0, "compared": 0}
    prepare = prepare_effective_change
    effective_positions = PreparedEffectiveChange.effective_positions

    def preparing(*args: Any, **kwargs: Any) -> PreparedEffectiveChange:
        calls["prepared"] += 1
        return prepare(*args, **kwargs)

    def comparing(change: PreparedEffectiveChange, row: tuple[object, ...]) -> Any:
        calls["compared"] += 1
        return effective_positions(change, row)

    monkeypatch.setattr(expansion_module, "prepare_effective_change", preparing)
    monkeypatch.setattr(PreparedEffectiveChange, "effective_positions", comparing)
    return calls


def _position_update(*assignments: WriteAssignment, account: str) -> MaterializedWriteGroup:
    return temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Position", predicate_algebra.Comparison("lessThan", "Position.value", "100.00")
            ),
            assignments,
            _WINDOW_FROM,
        ),
        _POSITION,
        [
            {
                "id": key,
                "acctNum": account,
                "value": Decimal("1.00"),
                "validStart": _OPENED_AT,
                "validEnd": INFINITY,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
            for key in (1, 2)
        ],
    )


def test_a_surviving_multi_assignment_row_carries_the_member_it_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _comparisons(monkeypatch)
    stored_account = "".join(("ACC", "-1"))
    group = _position_update(
        WriteAssignment("Position.acctNum", "ACC-1"),
        WriteAssignment("Position.value", Decimal("9.00")),
        account=stored_account,
    )
    assert isinstance(group.evidence, PredecessorRows)
    plan = _plan([group], _POSITION)
    assert calls == {"prepared": 1, "compared": 0}

    changed = [
        entry
        for step in plan.steps
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    ]
    assert len(changed) == 2
    assert calls == {"prepared": 1, "compared": 2}
    for entry in changed:
        values = _row_values(entry.row)
        account = next(ident for ident in entry.row.attributes if ident.name == "acctNum")
        assert entry.row.attributes[account] is stored_account
        origin = cast("ChangedFrom", entry.origin)
        assert origin.predecessor.carries(account, entry.row.attributes[account])
        assert values["value"] == Decimal("9.00")


def test_single_assignment_groups_and_literal_keyed_writes_are_never_compared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _comparisons(monkeypatch)
    group = _position_update(WriteAssignment("Position.value", Decimal("9.00")), account="A")
    list(_plan([group], _POSITION).steps)
    assert calls == {"prepared": 0, "compared": 0}

    prepared = _prepared_keyed(
        KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "B", "value": Decimal("9.00")},)),
        _BALANCE,
    )
    observation = TemporalObservation(predecessor=PredecessorRow(members=_BALANCE_PREDECESSOR))
    literal = buffered_write(prepared, observation)
    (_close, successor) = _plan([literal], _BALANCE).steps
    assert calls == {"prepared": 0, "compared": 0}
    # The successor overlays every member the row assigns, whatever it equals.
    assert _insert_rows(successor)[0]["acctNum"] == "B"
    assert _insert_rows(successor)[0]["value"] == Decimal("9.00")


def _acquisition_update_until(model: Metamodel) -> PreparedPredicateWrite:
    """The acquisition workload's interior ``updateUntil`` over its Relational
    Document family, assigning the workload's changed title to every row."""
    entity = acquisition_support.case_named("acquisition.rows-8.document").entity.identity.canonical
    prepared = prepare_typed_write(
        PredicateWrite(
            "updateUntil",
            PredicateSelection(
                entity, predicate_algebra.Comparison("greaterThanEquals", f"{entity}.id", 1)
            ),
            (WriteAssignment(f"{entity}.title", acquisition_support.ASSIGNED_TITLE),),
            acquisition_support.INTERIOR_FROM,
            acquisition_support.INTERIOR_UNTIL,
        ),
        model,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


def test_a_keyed_and_a_materialized_successor_lower_to_the_same_statements() -> None:
    # One retained Relational Document row changed through each producer: a
    # keyed `updateUntil` carrying its effective member alone, and a
    # materializing one over the same judged row and raw document. Both
    # successors patch the member they change and carry everything else,
    # unknown keys included, so they lower to identical statements. Each
    # producer freezes the raw document once for the row: the head and tail
    # bind that one immutable copy, and the changed successor's patch reuses
    # its subtrees.
    model = model_of(acquisition_support.MODEL)
    mutation = _acquisition_update_until(model)
    target = mutation.selection.target
    layout = LayoutCatalog(model).entity(target.identity)
    selection = layout.member_selection
    row = positional_row(
        selection.shape,
        {
            "id": 1,
            "title": "title-1",
            "address": {"city": "Oslo", "geo": {"country": "NO"}},
            "tags": [{"label": "a"}],
            "validStart": acquisition_support.VALID_START,
            "validEnd": INFINITY,
            "txStart": acquisition_support.TX_START,
            "txEnd": INFINITY,
        },
        absent=ABSENT,
    )
    stored: dict[str, object] = {
        "title": "title-1",
        "charterCode": "NB-118",
        "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": "S-4021"},
        "tags": [{"label": "a"}],
    }
    evidence = PredecessorRowsBuilder(
        selection, key_position=layout.primary_key[0], absent=ABSENT, documents=True
    )
    evidence.append(row, stored)
    sealed = evidence.seal()
    assert sealed is not None
    keyed = KeyedWrite(
        "updateUntil",
        target.identity.canonical,
        ({"id": 1, "title": acquisition_support.ASSIGNED_TITLE},),
        acquisition_support.INTERIOR_FROM,
        acquisition_support.INTERIOR_UNTIL,
    )
    key_ = object_key(keyed, model)
    assert key_ is not None
    observation = TemporalObservation(
        predecessor=PredecessorRow.over_row(selection, row, stored, ABSENT)
    )

    def lowered(plan: WritePlan) -> list[tuple[str, tuple[object, ...]]]:
        return [
            (statement.sql, tuple(statement.binds))
            for statement in (compile_write_step(step, model, POSTGRES) for step in plan.steps)
        ]

    eager = lowered(_plan([keyed], model, observations={key_: observation}))
    materialized = lowered(
        _plan([MaterializedWriteGroup(mutation=mutation, evidence=sealed)], model)
    )
    assert materialized == eager
    for statements in (eager, materialized):
        head, changed, tail = (
            cast("Mapping[str, object]", bind.value)
            for _sql, binds in statements
            for bind in binds
            if isinstance(bind, JsonDocument)
        )
        assert [head["title"], changed["title"], tail["title"]] == [
            "title-1",
            acquisition_support.ASSIGNED_TITLE,
            "title-1",
        ]
        assert all(document["charterCode"] == "NB-118" for document in (head, changed, tail))
        assert type(head) is FrozenMap
        assert head == stored
        assert tail is head
        assert changed["address"] is head["address"]
    assert observation.predecessor.document is stored
    assert sealed.document(0) is stored


@pytest.mark.parametrize("positional", [False, True], ids=["mapping", "positional"])
def test_a_restated_occurrence_is_assigned_whole_and_keeps_no_key_its_value_omits(
    positional: bool,
) -> None:
    # An update's row is its literal assignment set: `address`, restated as an
    # equal but distinct value, is assigned whole like any other occurrence, so
    # the changed successor writes the stated subtree — not the stored one, and
    # not the stored key no member declares — beside the patched `title`, while
    # every member the row does not name is carried.
    model = model_of(acquisition_support.MODEL)
    target = _acquisition_update_until(model).selection.target
    selection = LayoutCatalog(model).entity(target.identity).member_selection
    members: dict[str, object] = {
        "id": 1,
        "title": "title-1",
        "address": {"city": "Oslo", "geo": {"country": "NO"}},
        "tags": [{"label": "a"}],
        "validStart": acquisition_support.VALID_START,
        "validEnd": INFINITY,
        "txStart": acquisition_support.TX_START,
        "txEnd": INFINITY,
    }
    stored: dict[str, object] = {
        "title": "title-1",
        "address": {"city": "Oslo", "geo": {"country": "NO"}, "legacyDiscount": 5},
        "tags": [{"label": "a"}],
    }
    predecessor = (
        PredecessorRow.over_row(
            selection, positional_row(selection.shape, members, absent=ABSENT), stored, ABSENT
        )
        if positional
        else PredecessorRow(members, document=stored)
    )
    prepared = _prepared_keyed(
        KeyedWrite(
            "updateUntil",
            target.identity.canonical,
            (
                {
                    "id": 1,
                    "title": acquisition_support.ASSIGNED_TITLE,
                    "address": {"city": "Oslo", "geo": {"country": "NO"}},
                },
            ),
            acquisition_support.INTERIOR_FROM,
            acquisition_support.INTERIOR_UNTIL,
        ),
        model,
    )
    plan = _plan([buffered_write(prepared, TemporalObservation(predecessor))], model)

    (changed,) = (
        step
        for step in plan.steps
        if isinstance(step, PlannedInsert) and isinstance(step.entries[0].origin, ChangedFrom)
    )
    documents = [
        cast("Mapping[str, Any]", bind.value)
        for bind in compile_write_step(changed, model, POSTGRES).binds
        if isinstance(bind, JsonDocument)
    ]
    assert documents == [
        {
            **stored,
            "title": acquisition_support.ASSIGNED_TITLE,
            "address": {"city": "Oslo", "geo": {"country": "NO"}},
        }
    ]
    (entry,) = changed.entries
    (address,) = (
        identity for identity in entry.row.value_objects if identity.path[-1] == "address"
    )
    assert not cast("ChangedFrom", entry.origin).predecessor.carries(
        address, entry.row.value_objects[address]
    )


def test_a_surviving_row_overlays_an_effective_value_object_and_carries_a_restored_leaf() -> None:
    branch = corpus_model("branch")
    stored_name = "".join(("Central", " Branch"))
    address = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [{"type": "mobile", "number": "111"}],
    }
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection("Branch", predicate_algebra.Comparison("eq", "Branch.id", 1)),
            (
                WriteAssignment("Branch.name", "Central Branch"),
                WriteAssignment("Branch.address", {**address, "city": "Tampere"}),
            ),
            _WINDOW_FROM,
        ),
        branch,
        [
            {
                "id": 1,
                "name": stored_name,
                "validStart": _OPENED_AT,
                "validEnd": INFINITY,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
                "address": address,
            }
        ],
    )
    assert len(group) == 1
    (changed,) = (
        entry
        for step in _plan([group], branch).steps
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        if isinstance(entry.origin, ChangedFrom)
    )
    name = next(ident for ident in changed.row.attributes if ident.name == "name")
    (address_identity,) = changed.row.value_objects
    assert changed.row.attributes[name] is stored_name
    assert changed.row.value_objects[address_identity] is next(
        assignment.value
        for assignment in group.mutation.managed_assignments
        if not isinstance(assignment.member, AttributeMetadata)
    )


# --------------------------------------------------------------------------- #
# A Materialized Write Group over rows the attempt opened revises or removes   #
# each such row at its address, and never opens an empty successor.          #
# --------------------------------------------------------------------------- #
def _endpoint(entity: str, key: int, *ends: TemporalUpperBound) -> OwnedEndpoint:
    return OwnedEndpoint(corpus_object_key(entity, ("id", key)).entity, (key,), ends)


def _open_ends(entity: str) -> tuple[TemporalUpperBound, ...]:
    return (OPEN_END, OPEN_END) if entity == "Position" else (OPEN_END,)


def _planned_group(
    entity: str,
    mutation: PredicateMutation,
    *,
    owned: tuple[int, ...] = (),
    inserted: tuple[int, ...] = (),
) -> WritePlan:
    model = _POSITION if entity == "Position" else _BALANCE
    ownership = OpenedRows(
        frozenset(_endpoint(entity, key, *_open_ends(entity)) for key in owned),
        frozenset(_endpoint(entity, key, *_open_ends(entity)) for key in inserted),
    )
    return build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="locking",
            buffered_writes=[_temporal_topology_group(model, entity, mutation)],
            ownership=ownership,
        )
    )


@pytest.mark.parametrize(
    ("entity", "mutation", "row_two"),
    [
        ("Balance", "terminate", ["PlannedTemporalRemoval"]),
        ("Balance", "update", ["PlannedTemporalRevision"]),
        ("Position", "update", ["PlannedTemporalRevision", "PlannedInsert"]),
        ("Position", "terminate", ["PlannedTemporalRemoval", "PlannedInsert"]),
        ("Position", "updateUntil", ["PlannedTemporalRevision", "PlannedInsert", "PlannedInsert"]),
        ("Position", "terminateUntil", ["PlannedTemporalRevision", "PlannedInsert"]),
    ],
)
def test_a_group_rewrites_only_the_selected_rows_the_attempt_opened(
    entity: str, mutation: PredicateMutation, row_two: list[str]
) -> None:
    uniform = [type(step).__name__ for step in _planned_group(entity, mutation).steps]
    per_row = len(uniform) // 3
    plan = _planned_group(entity, mutation, owned=(2,))
    assert [type(step).__name__ for step in plan.steps] == [
        *uniform[:per_row],
        *row_two,
        *uniform[2 * per_row :],
    ]
    for index in range(len(plan.steps)):
        assert plan.steps[index] == list(plan.steps)[index]


def test_a_group_unit_records_what_its_rows_remove_and_open() -> None:
    (unit,) = _planned_group("Position", "terminate", owned=(2,)).units
    head_end = Finite(instant=_WINDOW_FROM)
    assert list(unit.removed) == [_endpoint("Position", 2, OPEN_END, OPEN_END)]
    assert list(unit.opened.fresh) == [
        _endpoint("Position", key, head_end, OPEN_END) for key in (1, 2, 3)
    ]
    assert list(unit.opened.continued) == []
    assert [state.object for state in unit.changed] == [
        corpus_object_key("Position", ("id", key)) for key in (1, 2, 3)
    ]


def test_a_group_continues_an_insertion_only_from_the_rows_that_insertion_opened() -> None:
    (unit,) = _planned_group("Position", "terminate", owned=(1, 2), inserted=(2,)).units
    head_end = Finite(instant=_WINDOW_FROM)
    assert list(unit.opened.continued) == [_endpoint("Position", 2, head_end, OPEN_END)]
    assert list(unit.opened.fresh) == [
        _endpoint("Position", key, head_end, OPEN_END) for key in (1, 3)
    ]


def test_a_transaction_time_group_unit_opens_one_current_row_per_rewritten_row() -> None:
    (unit,) = _planned_group("Balance", "update", owned=(2,)).units
    assert list(unit.removed) == []
    assert list(unit.opened.fresh) == [_endpoint("Balance", key, OPEN_END) for key in (1, 3)]


def test_a_group_of_rows_the_attempt_never_opened_keeps_its_uniform_layout() -> None:
    (unit,) = _planned_group("Position", "update").units
    assert list(unit.removed) == []
    assert len(list(unit.opened.fresh)) == 6


def test_a_group_never_opens_a_successor_that_covers_no_valid_time() -> None:
    model = _POSITION
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Position", predicate_algebra.Comparison("lessThan", "Position.value", "100.00")
            ),
            (WriteAssignment("Position.value", Decimal("9.00")),),
            _OPENED_AT,
        ),
        model,
        [
            {
                "id": key,
                "acctNum": "A",
                "value": Decimal("1.00"),
                "validStart": start,
                "validEnd": INFINITY,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
            for key, start in ((1, _OPENED_AT), (2, dt.datetime(2023, 1, 1, tzinfo=dt.UTC)))
        ],
    )
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="locking",
            buffered_writes=[group],
        )
    )
    # Row 1 starts where the update does, so it has no head; row 2 keeps one.
    assert [type(step).__name__ for step in plan.steps] == [
        "PlannedClose",
        "PlannedInsert",
        "PlannedClose",
        "PlannedInsert",
        "PlannedInsert",
    ]


# --------------------------------------------------------------------------- #
# Settled dispositions: each selected row's own steps, found by index, and    #
# the effects read from the same dispositions.                                 #
# --------------------------------------------------------------------------- #
_MAY = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_OCT = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)


def _position_rows(*starts: dt.datetime) -> list[dict[str, object]]:
    return [
        {
            "id": key,
            "acctNum": "A",
            "value": Decimal("1.00"),
            "validStart": start,
            "validEnd": INFINITY,
            "txStart": _OPENED_AT,
            "txEnd": INFINITY,
        }
        for key, start in enumerate(starts, start=1)
    ]


def _position_group(mutation: PredicateMutation, *starts: dt.datetime) -> MaterializedWriteGroup:
    bounded = mutation.endswith("Until")
    return temporal_group(
        PredicateWrite(
            mutation,
            PredicateSelection(
                "Position", predicate_algebra.Comparison("lessThan", "Position.value", "100.00")
            ),
            (WriteAssignment("Position.value", Decimal("9.00")),)
            if mutation.startswith("update")
            else (),
            *((_WINDOW_FROM, _WINDOW_UNTIL) if bounded else (_WINDOW_FROM,)),
        ),
        _POSITION,
        _position_rows(*starts),
    )


def _finalized(
    model: Metamodel,
    *groups: MaterializedWriteGroup,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> WritePlan:
    return build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="locking",
            buffered_writes=groups,
            ownership=ownership,
        )
    )


def _windows(steps: Iterable[PlannedWrite]) -> list[tuple[str, object, object]]:
    windows: list[tuple[str, object, object]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = _row_values(entry.row)
            windows.append((type(entry.origin).__name__, cells["validStart"], cells["validEnd"]))
        else:
            windows.append((type(step).__name__, None, None))
    return windows


def test_each_selected_row_is_clipped_to_its_own_coverage() -> None:
    # One `updateUntil` over [Mar, Sep): a row starting before the window keeps a
    # head, one starting at or inside it opens none and its changed successor
    # starts where the row does, and one starting past the window's end is not
    # reached at all — no step, and no change to its state.
    plan = _finalized(
        _POSITION, _position_group("updateUntil", _OPENED_AT, _WINDOW_FROM, _MAY, _OCT)
    )
    assert _windows(plan.steps) == [
        ("PlannedClose", None, None),
        ("CarriedFrom", _OPENED_AT, _WINDOW_FROM),
        ("ChangedFrom", _WINDOW_FROM, _WINDOW_UNTIL),
        ("CarriedFrom", _WINDOW_UNTIL, INFINITY),
        ("PlannedClose", None, None),
        ("ChangedFrom", _WINDOW_FROM, _WINDOW_UNTIL),
        ("CarriedFrom", _WINDOW_UNTIL, INFINITY),
        ("PlannedClose", None, None),
        ("ChangedFrom", _MAY, _WINDOW_UNTIL),
        ("CarriedFrom", _WINDOW_UNTIL, INFINITY),
    ]
    (unit,) = plan.units
    assert [state.object for state in unit.changed] == [
        corpus_object_key("Position", ("id", key)) for key in (1, 2, 3)
    ]
    head, tail = Finite(instant=_WINDOW_FROM), Finite(instant=_WINDOW_UNTIL)
    assert list(unit.opened.fresh) == [
        _endpoint("Position", 1, head, OPEN_END),
        _endpoint("Position", 1, tail, OPEN_END),
        _endpoint("Position", 1, OPEN_END, OPEN_END),
        _endpoint("Position", 2, tail, OPEN_END),
        _endpoint("Position", 2, OPEN_END, OPEN_END),
        _endpoint("Position", 3, tail, OPEN_END),
        _endpoint("Position", 3, OPEN_END, OPEN_END),
    ]
    assert list(unit.removed) == []


def test_a_selected_row_the_attempt_opened_is_clipped_to_its_own_coverage() -> None:
    # The same window over rows the attempt opened: the one starting inside it
    # is revised in place into its carried tail and opens only the changed part
    # from its own start, and the one starting at the window's end is not reached.
    plan = _finalized(
        _POSITION,
        _position_group("updateUntil", _MAY, _WINDOW_UNTIL),
        ownership=OpenedRows(
            frozenset(_endpoint("Position", key, OPEN_END, OPEN_END) for key in (1, 2))
        ),
    )
    assert _windows(plan.steps) == [
        ("PlannedTemporalRevision", None, None),
        ("ChangedFrom", _MAY, _WINDOW_UNTIL),
    ]
    revision = plan.steps[0]
    assert isinstance(revision, PlannedTemporalRevision)
    assert {
        identity.name: value for identity, value in revision.assignments.attributes.items()
    } == {"validStart": _WINDOW_UNTIL}
    (unit,) = plan.units
    assert [state.object for state in unit.changed] == [corpus_object_key("Position", ("id", 1))]
    assert list(unit.removed) == []


@pytest.mark.parametrize(
    ("group", "uniform"),
    [
        (_position_group("updateUntil", _OPENED_AT, _OPENED_AT, _OPENED_AT), True),
        (_position_group("updateUntil", _OPENED_AT, _WINDOW_FROM, _OPENED_AT), False),
    ],
    ids=["uniform", "clipped"],
)
def test_any_index_finds_the_step_iteration_builds_there(
    group: MaterializedWriteGroup, uniform: bool
) -> None:
    # Every row of a uniform group takes the one disposition its mutation
    # decides, found arithmetically; a clipped group keeps one per row and the
    # offsets its steps start at. Either way an index — in order, reversed,
    # repeated, or counted from the end — finds the step iteration builds.
    plan = _finalized(_POSITION, group)
    (segment,) = plan.steps.segments
    backing = cast("Any", segment).backing
    assert (backing.dispositions is None) is uniform
    assert (backing.offsets is None) is uniform
    settled = list(plan.steps)
    assert len(settled) == len(plan.steps) == len(segment)
    assert [plan.steps[index] for index in reversed(range(len(settled)))] == settled[::-1]
    assert [plan.steps[index] for index in (3, 3, 0, 3)] == [settled[i] for i in (3, 3, 0, 3)]
    assert [plan.steps[-index] for index in range(1, len(settled) + 1)] == settled[::-1]
    with pytest.raises(IndexError):
        _ = plan.steps[len(settled)]


def test_an_owned_row_its_group_leaves_as_it_was_takes_no_step_and_changes_no_state() -> None:
    # Row 2 is the attempt's own and already holds the assigned cell itself, so
    # revising it in place would assign nothing: it keeps its address with no
    # statement, names no changed state, and the rows around it are found by
    # index past it.
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "100.00")
            ),
            (WriteAssignment("Balance.acctNum", "A"),),
        ),
        _BALANCE,
        [
            {
                "id": key,
                "acctNum": account,
                "value": Decimal("1.00"),
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
            for key, account in ((1, "B"), (2, "A"), (3, "B"))
        ],
    )
    plan = _finalized(
        _BALANCE, group, ownership=OpenedRows(frozenset({_endpoint("Balance", 2, OPEN_END)}))
    )
    settled = list(plan.steps)
    assert [type(step).__name__ for step in settled] == [
        "PlannedClose",
        "PlannedInsert",
        "PlannedClose",
        "PlannedInsert",
    ]
    assert [_insert_rows(step)[0]["id"] for step in settled if isinstance(step, PlannedInsert)] == [
        1,
        3,
    ]
    assert [plan.steps[index] for index in range(len(settled))] == settled
    (unit,) = plan.units
    assert [state.object for state in unit.changed] == [
        corpus_object_key("Balance", ("id", key)) for key in (1, 3)
    ]
    assert list(unit.opened.fresh) == [_endpoint("Balance", key, OPEN_END) for key in (1, 3)]
    assert list(unit.opened.continued) == []
    assert list(unit.removed) == []


def test_a_group_no_row_of_which_takes_a_step_adds_no_segment_but_still_completes() -> None:
    plan = _finalized(_POSITION, _position_group("updateUntil", _OCT, _OCT))
    assert len(plan.steps) == 0
    assert plan.steps.segments == ()
    (unit,) = plan.units
    assert unit.end == 0
    assert list(unit.changed) == []
    assert list(unit.opened.fresh) == []


def test_a_bitemporal_group_refuses_a_row_that_holds_no_valid_time_start() -> None:
    group = temporal_group(
        PredicateWrite(
            "terminate",
            PredicateSelection(
                "Position", predicate_algebra.Comparison("lessThan", "Position.value", "100.00")
            ),
            valid_from=_WINDOW_FROM,
        ),
        _POSITION,
        [{**_position_rows(_OPENED_AT)[0], "validStart": None}],
    )
    with pytest.raises(WritePlanningError, match="no observed Valid-Time start"):
        _finalized(_POSITION, group)


# --------------------------------------------------------------------------- #
# Frozen disposition: what planning read of the attempt's ownership is fixed  #
# in the settled backing, which retains neither the ownership nor its reader. #
# --------------------------------------------------------------------------- #
@dataclass
class _LiveOwnership:
    """The attempt's ownership record as it changes while the plan is held."""

    endpoints: set[OwnedEndpoint]
    inserted: set[OwnedEndpoint]

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.endpoints

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        return any(endpoint.entity == entity for endpoint in self.endpoints)

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self.inserted

    def proven(self, original: ObservedStateKey, /) -> Derivation | None:
        del original
        return None

    def descendants(
        self, original: ObservedStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterator[tuple[OwnedEndpoint, Descent]]:
        del original, valid_time_window
        return iter(())

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        del endpoint
        return None


def _effects(unit: ExecutionUnit) -> tuple[list[object], ...]:
    return (
        list(unit.changed),
        list(unit.removed),
        list(unit.opened.fresh),
        list(unit.opened.continued),
    )


@pytest.mark.parametrize("mutation", ["terminate", "updateUntil"])
def test_steps_and_effects_stay_as_settled_when_the_attempts_ownership_changes(
    mutation: PredicateMutation,
) -> None:
    owned = _endpoint("Position", 2, OPEN_END, OPEN_END)
    ownership = _LiveOwnership({owned}, {owned})
    plan = _finalized(
        _POSITION,
        _position_group(mutation, _OPENED_AT, _OPENED_AT, _OPENED_AT),
        ownership=ownership,
    )
    (unit,) = plan.units
    ownership.endpoints.clear()
    ownership.inserted.clear()
    ownership.endpoints.add(_endpoint("Position", 1, OPEN_END, OPEN_END))
    settled = list(plan.steps)
    effects = _effects(unit)
    assert any(
        isinstance(step, PlannedTemporalRemoval | PlannedTemporalRevision) for step in settled
    )
    assert effects[3]  # the owned row's successors continue its insertion
    ownership.endpoints.clear()
    assert list(plan.steps) == settled
    assert _effects(unit) == effects
    walked = [
        value for held in (*plan.steps.segments, *plan.units) for value in reachable_objects(held)
    ]
    assert not [
        value
        for value in walked
        if isinstance(value, _LiveOwnership | PredecessorExpander | MethodType | FunctionType)
    ]


@pytest.mark.parametrize(
    ("entity", "mutation", "start"),
    [
        ("Balance", "terminate", None),
        ("Balance", "update", None),
        ("Position", "terminate", _OPENED_AT),
        ("Position", "updateUntil", _OPENED_AT),
        ("Position", "update", _WINDOW_FROM),
    ],
)
def test_an_owned_row_settles_identically_through_a_keyed_write_and_a_group(
    entity: str, mutation: PredicateMutation, start: dt.datetime | None
) -> None:
    # One row the attempt opened, written once by an observed keyed write and
    # once by a one-row group of the same mutation: its revision or removal and
    # the successors it opens are the same steps, and their success publishes
    # the same removal and openings. A row starting where the write does keeps
    # its own Valid-Time start, so only the assigned member revises it.
    model = _POSITION if entity == "Position" else _BALANCE
    ownership = OpenedRows(frozenset({_endpoint(entity, 1, *_open_ends(entity))}))
    (row,) = (
        _position_rows(start)
        if start is not None
        else [
            {
                "id": 1,
                "acctNum": "A",
                "value": Decimal("1.00"),
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
            }
        ]
    )
    bounds = (
        ()
        if entity == "Balance"
        else (_WINDOW_FROM, _WINDOW_UNTIL)
        if mutation.endswith("Until")
        else (_WINDOW_FROM,)
    )
    assigned = {"value": Decimal("9.00")} if mutation.startswith("update") else {}
    keyed = KeyedWrite(mutation, entity, ({"id": 1, **assigned},), *bounds)
    key_ = object_key(keyed, model)
    assert key_ is not None
    eager = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="locking",
            buffered_writes=observed_buffer(
                [keyed],
                model,
                {key_: TemporalObservation(predecessor=PredecessorRow(members=row))},
            ),
            ownership=ownership,
        )
    )
    group = temporal_group(
        PredicateWrite(
            mutation,
            PredicateSelection(
                entity, predicate_algebra.Comparison("lessThan", f"{entity}.value", "100.00")
            ),
            tuple(WriteAssignment(f"{entity}.{name}", value) for name, value in assigned.items()),
            *bounds,
        ),
        model,
        [row],
    )
    materialized = _finalized(model, group, ownership=ownership)
    assert list(materialized.steps) == list(eager.steps)
    (eager_unit,) = eager.units
    (group_unit,) = materialized.units
    assert _effects(group_unit)[1:] == _effects(eager_unit)[1:]


# --------------------------------------------------------------------------- #
# Allocation shape: settling a group sizes it from scalar cells and builds    #
# none of its steps; an unowned Transaction-Time-Only group reads no row.     #
# --------------------------------------------------------------------------- #
class _Built:
    """Counts constructions of each watched type from now on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *types: type) -> None:
        self.counts: dict[str, int] = {}
        for watched in types:
            original = watched.__init__
            name = watched.__name__

            def counting(
                self_: object,
                *args: object,
                _original: Any = original,
                _name: str = name,
                **kwargs: object,
            ) -> None:
                self.counts[_name] = self.counts.get(_name, 0) + 1
                _original(self_, *args, **kwargs)

            monkeypatch.setattr(watched, "__init__", counting)
        over_row = PredecessorRow.over_row

        def adopted(*args: Any) -> PredecessorRow:
            self.counts["PredecessorRow"] = self.counts.get("PredecessorRow", 0) + 1
            return over_row(*args)

        monkeypatch.setattr(PredecessorRow, "over_row", adopted)

    def reset(self) -> dict[str, int]:
        counts, self.counts = self.counts, {}
        return counts


_SIZING_FORBIDDEN: Final = (
    TimeInterval,
    Successor,
    PredecessorExpansion,
    PlannedClose,
    PlannedInsert,
    InsertEntry,
    PlannedTemporalRevision,
    PlannedTemporalRemoval,
)


@pytest.mark.parametrize("owned", [(), (2, 4, 6)], ids=["clipped", "owned"])
def test_settling_a_bitemporal_group_builds_none_of_its_steps(
    monkeypatch: pytest.MonkeyPatch, owned: tuple[int, ...]
) -> None:
    # A clipped group reads each row's Valid-Time cells and an owned one checks
    # each row's address and whether revising it would assign anything, but
    # neither builds an interval, a successor, an expansion result, a planned
    # row, or a predecessor to find out. The group's one window is the only
    # interval, whatever the row count; the steps arise when they are asked for.
    small = _position_group("updateUntil", *(_OPENED_AT, _WINDOW_FROM) * 2)
    large = _position_group("updateUntil", *(_OPENED_AT, _WINDOW_FROM) * 8)
    ownership = OpenedRows(
        frozenset(_endpoint("Position", key, OPEN_END, OPEN_END) for key in owned)
    )
    built = _Built(monkeypatch, *_SIZING_FORBIDDEN)
    _finalized(_POSITION, small, ownership=ownership)
    small_counts = built.reset()
    plan = _finalized(_POSITION, large, ownership=ownership)
    large_counts = built.reset()
    assert small_counts == large_counts
    assert set(large_counts) <= {"TimeInterval"}
    settled = list(plan.steps)
    accessed = built.reset()
    # A revision is read off the one successor that keeps the row's address,
    # built for it from the row's member cells alone.
    revisions = sum(isinstance(step, PlannedTemporalRevision) for step in settled)
    assert revisions == len(owned)
    inserts = sum(isinstance(step, PlannedInsert) for step in settled)
    assert accessed["PlannedInsert"] == inserts + revisions
    assert accessed["PredecessorRow"] == 16 + revisions


def test_an_unowned_transaction_time_group_reads_no_row_while_it_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = _temporal_topology_group(_BALANCE, "Balance", "update", rows=5)
    reads: list[str] = []
    column: Any = ColumnSlice
    get, walk = column.__getitem__, column.__iter__

    def reading(self: ColumnSlice[object], index: int) -> object:
        reads.append("get")
        return get(self, index)

    def walking(self: ColumnSlice[object]) -> Iterator[object]:
        reads.append("walk")
        return walk(self)

    monkeypatch.setattr(ColumnSlice, "__getitem__", reading)
    monkeypatch.setattr(ColumnSlice, "__iter__", walking)
    plan = _finalized(_BALANCE, group)
    assert reads == []
    assert len(plan.steps) == 10
    _ = plan.steps[3]
    assert reads


# --------------------------------------------------------------------------- #
# Documents: one immutable view per row, shared by its sibling successors and #
# released after the last; effects and cell-only steps freeze none.           #
# --------------------------------------------------------------------------- #
def _document_group(
    *titles: str,
) -> tuple[Metamodel, MaterializedWriteGroup, list[dict[str, object]]]:
    model = model_of(acquisition_support.MODEL)
    mutation = _acquisition_update_until(model)
    layout = LayoutCatalog(model).entity(mutation.selection.target.identity)
    selection = layout.member_selection
    evidence = PredecessorRowsBuilder(
        selection, key_position=layout.primary_key[0], absent=ABSENT, documents=True
    )
    stored: list[dict[str, object]] = []
    for key, title in enumerate(titles, start=1):
        document: dict[str, object] = {
            "title": title,
            "charterCode": f"NB-{key}",
            "address": {"city": "Oslo", "geo": {"country": "NO"}, "sealNumber": f"S-{key}"},
            "tags": [{"label": label} for label in "abcdefgh"],
        }
        stored.append(document)
        evidence.append(
            positional_row(
                selection.shape,
                {
                    "id": key,
                    "title": title,
                    "address": {"city": "Oslo", "geo": {"country": "NO"}},
                    "tags": [{"label": label} for label in "abcdefgh"],
                    "validStart": acquisition_support.VALID_START,
                    "validEnd": INFINITY,
                    "txStart": acquisition_support.TX_START,
                    "txEnd": INFINITY,
                },
                absent=ABSENT,
            ),
            document,
        )
    sealed = evidence.seal()
    assert sealed is not None
    return model, MaterializedWriteGroup(mutation=mutation, evidence=sealed), stored


def _bound_document(step: PlannedWrite) -> object:
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    origin = entry.origin
    assert isinstance(origin, CarriedFrom | ChangedFrom)
    return origin.predecessor.document


def test_a_rows_successors_share_one_view_of_its_document_released_after_the_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, group, stored = _document_group("title-1", "title-2")
    plan = _finalized(model, group)
    (segment,) = plan.steps.segments
    frozen: list[object] = []
    retain = group_segments_module.retain_document_value  # pyright: ignore[reportPrivateImportUsage]

    def freezing(value: object) -> object:
        frozen.append(value)
        return retain(value)

    monkeypatch.setattr(group_segments_module, "retain_document_value", freezing)
    # The completion effects and every close read cells alone.
    (unit,) = plan.units
    _effects(unit)
    closes = [plan.steps[index] for index in (0, 4)]
    assert all(isinstance(close, PlannedClose) for close in closes)
    assert frozen == []
    # In order: one frozen view per row, shared by its head, middle and tail,
    # and let go once the row's tail is built.
    first = [plan.steps[index] for index in range(1, 4)]
    assert frozen == [stored[0]]
    assert cast("Any", segment)._bindable is None
    head, middle, tail = (_bound_document(step) for step in first)
    assert head is middle is tail
    assert type(head) is FrozenMap
    assert head == stored[0]  # an undeclared raw key rides through unchanged
    second = [plan.steps[index] for index in range(5, 8)]
    assert frozen == stored
    assert _bound_document(second[0]) is not head
    # Out of order: an equal step, though its row's view is prepared again.
    assert plan.steps[3] == first[2]
    assert plan.steps[1] == first[0]
    assert frozen == [*stored, stored[0], stored[0]]


def test_many_small_groups_each_keep_their_own_view() -> None:
    model, one, _stored = _document_group("title-1")
    _model, two, _other = _document_group("title-2")
    plan = _finalized(model, one, two)
    assert [len(segment) for segment in plan.steps.segments] == [4, 4]
    settled = list(plan.steps)
    assert _bound_document(settled[1]) is not _bound_document(settled[5])
    assert all(cast("Any", segment)._bindable is None for segment in plan.steps.segments)
    assert [plan.steps[index] for index in range(len(settled))] == settled


@pytest.mark.parametrize(
    ("restored", "changed"),
    [("acctNum", "value"), ("value", "acctNum")],
)
def test_an_owned_row_revised_by_a_multi_assignment_group_assigns_only_what_changes(
    restored: str, changed: str
) -> None:
    # The row is the attempt's own, so it is revised in place; of the group's
    # two assignments the row already holds one, which the revision carries
    # rather than restating, and the other is what it assigns.
    stored: dict[str, object] = {"acctNum": "".join(("A", "-1")), "value": Decimal("1.00")}
    assigned: dict[str, object] = {"acctNum": "B-1", "value": Decimal("9.00")}
    assigned[restored] = stored[restored]
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "100.00")
            ),
            tuple(WriteAssignment(f"Balance.{name}", value) for name, value in assigned.items()),
        ),
        _BALANCE,
        [{"id": 1, **stored, "txStart": _OPENED_AT, "txEnd": INFINITY}],
    )
    plan = _finalized(
        _BALANCE, group, ownership=OpenedRows(frozenset({_endpoint("Balance", 1, OPEN_END)}))
    )
    (revision,) = plan.steps
    assert isinstance(revision, PlannedTemporalRevision)
    assert {
        identity.name: value for identity, value in revision.assignments.attributes.items()
    } == {changed: assigned[changed]}


def test_an_owned_row_revised_by_a_group_assigns_the_occurrence_it_changes() -> None:
    branch = corpus_model("branch")
    address = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [{"type": "mobile", "number": "111"}],
    }
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection("Branch", predicate_algebra.Comparison("eq", "Branch.id", 1)),
            (
                WriteAssignment("Branch.name", "Central Branch"),
                WriteAssignment("Branch.address", {**address, "city": "Tampere"}),
            ),
            _WINDOW_FROM,
        ),
        branch,
        [
            {
                "id": 1,
                "name": "".join(("Central", " Branch")),
                "validStart": _WINDOW_FROM,
                "validEnd": INFINITY,
                "txStart": _OPENED_AT,
                "txEnd": INFINITY,
                "address": address,
            }
        ],
    )
    plan = _finalized(
        branch,
        group,
        ownership=OpenedRows(frozenset({_endpoint("Branch", 1, OPEN_END, OPEN_END)})),
    )
    (revision,) = plan.steps
    assert isinstance(revision, PlannedTemporalRevision)
    assert revision.assignments.attributes == {}
    (assigned,) = revision.assignments.value_objects.values()
    assert cast("Mapping[str, object]", assigned)["city"] == "Tampere"
