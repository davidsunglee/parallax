from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pytest

from parallax.conformance import models
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.write_collapse import collapse_writes
from parallax.core._execution._unit_work.write_items import (
    InsertBatch,
    ObjectLockedBatch,
    ObjectLockedWrite,
)
from parallax.core.internal import inheritance
from parallax.core.internal.base import INT64, UsageError
from parallax.core.internal.db_port import ArrayBind
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    CompiledEntity,
    EntityIdentity,
    Metamodel,
)
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.core.internal.unit_work import (
    AdmittedWrite,
    KeyedWriteInstruction,
    WritePlanningRequest,
    object_key,
)
from parallax.core.internal.write_payload import LayoutPayloadPreparer
from parallax.core.internal.write_plan import ObjectKey, StateObservation, VersionObservation
from parallax.core.internal.write_plan.payload import AssignmentPayload, WritePayloadPreparer
from parallax.core.internal.write_plan.steps import (
    MISSING_TARGET,
    ExactCount,
    KeyTarget,
    PlannedAssignments,
    PlannedDelete,
    PlannedStep,
    PlannedUpdate,
)
from parallax.descriptor import _records
from tests._support.clock_probes import inert_instant
from tests._support.lowering_probes import lowered_steps
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer, plan_steps
from tests.unit._corpus_model_support import formed
from tests.unit._document_layout_support import PERSON, columns_model, document_model

_MODELS = models.load_models()


def _target(stem: str, name: str) -> tuple[Metamodel, CompiledEntity]:
    """One corpus model and one of its Entities, both accepted."""
    model = _MODELS[stem]
    entity = model.entity(EntityIdentity("parallax.compatibility", name))
    assert entity is not None
    return model, entity


ACCOUNT = _target("account", "Account")
WALLET = _target("wallet", "Wallet")
BALANCE = _target("balance", "Balance")
POSITION = _target("position", "Position")
DOG = _target("animal", "Dog")
FRIDGE = _target("appliance", "Fridge")
DEPOSIT_RATE = _target("rate", "DepositRate")


def _generated_key_leaf() -> tuple[Metamodel, CompiledEntity]:
    """A concrete subtype whose family root's key the framework allocates.

    No corpus family generates its key, so this one is formed by hand.
    """
    root = _records.Entity(
        name="Ticket",
        inheritance=_records.Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            _records.Attribute(
                name="id",
                type="int64",
                column="id",
                primary_key=True,
                pk_generator=_records.PkGenerator(strategy="max"),
            ),
            _records.Attribute(name="title", type="string", column="title"),
        ),
    )
    leaf = _records.Entity(
        name="Bug",
        table="bug",
        inheritance=_records.Inheritance(role="concrete-subtype", parent="Ticket"),
        attributes=(_records.Attribute(name="severity", type="int32", column="severity"),),
    )
    model = formed(_records.Metamodel(entities=(root, leaf)))
    (bug,) = (entity for entity in model.entities if entity.identity.name == "Bug")
    return model, bug


GENERATED_KEY_LEAF = _generated_key_leaf()


def _flush_and_lower(
    buffer: list[AdmittedWrite | KeyedWriteInstruction], model: Metamodel
) -> list[LoweredStatement]:
    """Plan ``buffer`` with the production wiring, then lower the plan."""
    return [
        statement
        for _step, statement in _flush_and_lower_steps(buffer, model, LayoutPayloadPreparer(model))
    ]


class _CountingPreparer(LayoutPayloadPreparer):
    """The layout preparer, counting the Assignment Payloads it prepares."""

    def __init__(self, model: Metamodel) -> None:
        super().__init__(model)
        self.assignments_prepared = 0

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        self.assignments_prepared += 1
        return super().assignments(entity, assignments)


def _flush_and_lower_steps(
    buffer: list[AdmittedWrite | KeyedWriteInstruction],
    model: Metamodel,
    payloads: WritePayloadPreparer,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    """Plan ``buffer`` with the production wiring, then lower each planned step
    through ``payloads``."""
    instant = inert_instant()
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant,
            preference="locking",
            composed_writes=observed_buffer(buffer, model, None),
        )
    )
    return list(lowered_steps(plan_steps(plan), payloads, model, POSTGRES))


def test_insert_preparation_refuses_a_missing_required_slot_before_grouping() -> None:
    model, _ = WALLET
    buffer: list[AdmittedWrite | KeyedWriteInstruction] = [
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWriteInstruction("insert", "Wallet", ({"id": 11, "owner": "Omar"},)),
    ]
    with pytest.raises(UsageError, match=r"Wallet\.balance: required attribute"):
        _flush_and_lower(buffer, model)


def test_delete_grouping_ignores_members_the_statement_never_uses() -> None:
    # A DELETE's emitted statement selects the key columns alone, so two rows
    # carrying different non-key payload members are the SAME physical shape and
    # must reach one key-membership statement.
    model, _ = WALLET
    buffer: list[AdmittedWrite | KeyedWriteInstruction] = [
        KeyedWriteInstruction(
            "delete", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWriteInstruction("delete", "Wallet", ({"id": 11},)),
    ]
    statements = _flush_and_lower(buffer, model)
    assert [statement.sql for statement in statements] == [
        "delete from wallet where id = any(cast(? as bigint[]))"
    ]
    assert [statement.binds for statement in statements] == [(ArrayBind(INT64, [10, 11]),)]


def test_update_grouping_still_splits_on_a_differing_set_clause() -> None:
    # An UPDATE's emitted statement DOES select the assignable members (its `set`
    # clause), so a differing assignable selection stays a differing group —
    # each side then collapses on its own uniform values.
    model, _ = WALLET
    buffer: list[AdmittedWrite | KeyedWriteInstruction] = [
        KeyedWriteInstruction("amend", "Wallet", ({"id": 10, "balance": Decimal("5.00")},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 11, "balance": Decimal("5.00")},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 12, "owner": "Omar"},)),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 13, "owner": "Omar"},)),
    ]
    statements = _flush_and_lower(buffer, model)
    assert [statement.sql for statement in statements] == [
        "update wallet set balance = ? where id = any(cast(? as bigint[]))",
        "update wallet set owner = ? where id = any(cast(? as bigint[]))",
    ]
    assert [statement.binds for statement in statements] == [
        (Decimal("5.00"), ArrayBind(INT64, [10, 11])),
        ("Omar", ArrayBind(INT64, [12, 13])),
    ]


@pytest.mark.parametrize("mutation", ["amend", "delete"])
def test_a_collapse_wider_than_the_parameter_limit_stays_one_step_and_one_statement(
    mutation: Literal["amend", "delete"],
) -> None:
    # Array-bound keys change only how the target binds: the uniform run still
    # plans as one step over every key, unsplit and uncapped, with one aggregate
    # expectation and one Assignment Payload shared by every addressed row.
    model, _ = WALLET
    keys = range(1, 70_002)
    buffer: list[AdmittedWrite | KeyedWriteInstruction] = [
        KeyedWriteInstruction(
            mutation,
            "Wallet",
            ({"id": key} if mutation == "delete" else {"id": key, "balance": Decimal("5.00")},),
        )
        for key in keys
    ]
    payloads = _CountingPreparer(model)
    ((step, statement),) = _flush_and_lower_steps(buffer, model, payloads)
    assert isinstance(step, PlannedUpdate | PlannedDelete)
    assert isinstance(step.target, KeyTarget)
    assert step.target.key_values == tuple((key,) for key in keys)
    assert step.affected_rows == ExactCount(expected=len(keys), on_shortfall=MISSING_TARGET)
    assert payloads.assignments_prepared == (1 if mutation == "amend" else 0)
    assert statement.binds[-1] == ArrayBind(INT64, list(keys))
    assert len(statement.binds) == (2 if mutation == "amend" else 1)


def test_row_member_order_alone_never_splits_a_batch_group() -> None:
    # The grouping key is the TABLE-ordered slot selection, so two rows naming
    # the same members in different payload order stay one group.
    model, _ = WALLET
    buffer: list[AdmittedWrite | KeyedWriteInstruction] = [
        KeyedWriteInstruction(
            "insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWriteInstruction(
            "insert", "Wallet", ({"balance": Decimal("20.00"), "id": 11, "owner": "Omar"},)
        ),
    ]
    assert [statement.sql for statement in _flush_and_lower(buffer, model)] == [
        "insert into wallet(id, owner, balance) select * from "
        "unnest(cast(? as bigint[]), cast(? as text[]), cast(? as decimal[]))"
    ]


@pytest.mark.parametrize(
    ("target", "values", "collapses"),
    [
        (WALLET, {"owner": "Ada", "balance": Decimal("5.00")}, True),
        (ACCOUNT, {"owner": "Ada", "balance": Decimal("5.00"), "version": 1}, True),
        (BALANCE, {"acctNum": "A", "value": Decimal("5.00")}, False),
        (DOG, {"name": "Rex"}, True),
        (FRIDGE, {"name": "Chill"}, True),
        (GENERATED_KEY_LEAF, {"title": "Crash", "severity": 1}, False),
    ],
    ids=["plain", "versioned", "temporal", "inherited", "inherited-version", "generated-key"],
)
def test_insert_runs_use_the_admitted_target_and_preserve_row_order(
    target: tuple[Metamodel, CompiledEntity], values: dict[str, object], collapses: bool
) -> None:
    model, entity = target
    writes = [
        KeyedWriteInstruction("insert", entity.identity.canonical, ({"id": key, **values},))
        for key in (3, 1, 2)
    ]
    admitted = observed_buffer(writes, model, None)
    result = collapse_writes(model, admitted)
    assert len(result) == (1 if collapses else 3)
    if collapses:
        (batch,) = result
        assert isinstance(batch, InsertBatch)
        position = inheritance.inheritance_facet_of(model).entity(entity.identity)
        assert position is not None
        assert tuple(row.cell(position.primary_key.identity) for row in batch.instruction.rows) == (
            3,
            1,
            2,
        )
    else:
        assert all(actual is expected for actual, expected in zip(result, admitted, strict=True))


@pytest.mark.parametrize(
    ("mutation", "rows", "sizes"),
    [
        ("amend", ({"id": 3, "balance": Decimal("5")},), (1,)),
        ("amend", ({"id": 3, "balance": Decimal("5")}, {"id": 1, "balance": Decimal("5")}), (2,)),
        (
            "amend",
            (
                {"id": 3, "balance": Decimal("5")},
                {"id": 1, "balance": Decimal("5")},
                {"id": 2, "balance": Decimal("6")},
            ),
            (1, 1, 1),
        ),
        ("amend", ({"id": 3, "balance": Decimal("5")}, {"id": 1, "owner": "Ada"}), (1, 1)),
        ("delete", ({"id": 3, "balance": Decimal("5")}, {"id": 1}), (2,)),
    ],
    ids=["singleton", "uniform", "whole-run-nonuniform", "presence", "delete-payload"],
)
def test_object_locked_runs_preserve_whole_run_membership(
    mutation: Literal["amend", "delete"],
    rows: tuple[dict[str, object], ...],
    sizes: tuple[int, ...],
) -> None:
    model, entity = WALLET
    admitted = observed_buffer(
        [KeyedWriteInstruction(mutation, entity.identity.canonical, (row,)) for row in rows],
        model,
        None,
    )
    result = collapse_writes(model, admitted)
    assert (
        tuple(
            len(item.instruction.rows)
            for item in result
            if isinstance(item, ObjectLockedWrite | ObjectLockedBatch)
        )
        == sizes
    )
    assert tuple(
        row.cell(AttributeIdentity(entity.identity, "id"))
        for item in result
        if isinstance(item, ObjectLockedWrite | ObjectLockedBatch)
        for row in item.instruction.rows
    ) == tuple(row["id"] for row in rows)


@pytest.mark.parametrize("layout", ["columns", "document"])
def test_presence_shapes_split_even_when_members_share_one_document(layout: str) -> None:
    model = document_model() if layout == "document" else columns_model()
    rows = ({"id": 3, "score": None}, {"id": 1, "displayName": None}, {"id": 2, "score": None})
    admitted = observed_buffer(
        [KeyedWriteInstruction("amend", PERSON.canonical, (row,)) for row in rows], model, None
    )
    result = collapse_writes(model, admitted)
    assert len(result) == 3
    assert all(actual is expected for actual, expected in zip(result, admitted, strict=True))


@pytest.mark.parametrize("model", [columns_model(), document_model()], ids=["columns", "document"])
def test_delete_runs_ignore_nonkey_presence(model: Metamodel) -> None:
    rows = ({"id": 3, "score": 5}, {"id": 1, "displayName": "Ada"}, {"id": 2})
    admitted = observed_buffer(
        [KeyedWriteInstruction("delete", PERSON.canonical, (row,)) for row in rows], model, None
    )
    result = collapse_writes(model, admitted)
    assert len(result) == 1
    (batch,) = result
    assert isinstance(batch, ObjectLockedBatch)
    assert tuple(row.cell(AttributeIdentity(PERSON, "id")) for row in batch.instruction.rows) == (
        3,
        1,
        2,
    )


@pytest.mark.parametrize("target", [DOG, GENERATED_KEY_LEAF], ids=["inherited", "generated-key"])
def test_uniform_updates_exclude_the_inherited_addressing_key(
    target: tuple[Metamodel, CompiledEntity],
) -> None:
    model, entity = target
    member = "name" if entity.identity.name == "Dog" else "title"
    writes = [
        KeyedWriteInstruction("amend", entity.identity.canonical, ({"id": key, member: "same"},))
        for key in (3, 1)
    ]
    (batch,) = collapse_writes(model, observed_buffer(writes, model, None))
    assert isinstance(batch, ObjectLockedBatch)
    assert tuple(key.primary_key for key in batch.object_keys) == ((("id", 3),), (("id", 1),))


@pytest.mark.parametrize("target", [ACCOUNT, FRIDGE], ids=["versioned", "inherited-version"])
@pytest.mark.parametrize("mutation", ["amend", "delete"])
def test_observed_writes_remain_separate_despite_uniform_values(
    target: tuple[Metamodel, CompiledEntity], mutation: Literal["amend", "delete"]
) -> None:
    model, entity = target
    member = "owner" if entity.identity.name == "Account" else "name"
    writes = [
        KeyedWriteInstruction(mutation, entity.identity.canonical, ({"id": key, member: "same"},))
        for key in (3, 1)
    ]
    observations: dict[ObjectKey, StateObservation] = {}
    for write in writes:
        key = object_key(write, model)
        assert key is not None
        observations[key] = VersionObservation(observed_version=1)
    admitted = observed_buffer(writes, model, observations)
    result = collapse_writes(model, admitted)
    assert len(result) == 2
    assert all(actual is expected for actual, expected in zip(result, admitted, strict=True))
