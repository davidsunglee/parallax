"""Grouped effects as lowering presents them (`m-sql` *Grouped effects*).

Effects of one key or milestone each that a Write Group lays out in one effect
span lower as one statement whose `unnest(…) with ordinality` source binds one
typed array per source column and returns each changed or removed row's source
ordinal. Every expected statement here is authored from the grammar.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import cast

import pytest

from parallax.core._execution._write_lowering import (
    STORED_DOCUMENT_NOT_OBJECT,
    LoweringCursor,
    stream_physical,
)
from parallax.core.internal.base import (
    INFINITY,
    INT32,
    INT64,
    JSON,
    STRING,
    TIMESTAMP,
    InternalError,
    Numeric,
)
from parallax.core.internal.db_port import ArrayBind
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.metamodel import EntityIdentity, Metamodel
from parallax.core.internal.read_delivery import InvalidDataError
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.core.internal.sql_gen._context import SQL_GENERATION_FAILED
from parallax.core.internal.sql_gen._write import GroupedEffectBuilder
from parallax.core.internal.write_payload import LayoutPayloadPreparer
from parallax.core.internal.write_payload._storage import ROW_SLOTS_PER_ENTITY, EffectShape
from parallax.core.internal.write_plan.payload import AssignmentPayload, DocumentPatches
from parallax.core.internal.write_plan.plan import EffectSpan, SettledWrite, WriteGroup
from parallax.core.internal.write_plan.planned_rows import WRITE_PLANNING_FAILED
from parallax.core.internal.write_plan.steps import (
    MISSING_TARGET,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedAssignments,
    PlannedDelete,
    PlannedStep,
    PlannedUpdate,
    SelfIncrement,
)
from tests._support.bindings import bound_model
from tests._support.errors import raises_code
from tests.unit._corpus_model_support import model
from tests.unit.core._execution._grouped_effect_support import (
    ACCOUNT,
    BALANCE,
    CLOSED_AT,
    COVERAGE_DOCUMENT,
    INSTRUMENT,
    POSITION,
    WALLET,
    attribute_identity,
    close,
    delete,
    entity_identity,
    guard,
    instant,
    milestone,
    removal,
    revision,
    update,
)

PAYMENT = model("payment")
PERSON = model("person")
LEDGER_COLUMNS = model("scalar-collection-lifecycle-layout-twin-columns")
LEDGER_DOCUMENT = model("scalar-collection-lifecycle-layout-twin-document")


def grouped(
    meta: Metamodel,
    steps: Sequence[PlannedStep],
    *,
    dialect: Dialect = POSTGRES,
    payloads: LayoutPayloadPreparer | None = None,
) -> tuple[WriteGroup, list[LoweredStatement]]:
    """``steps``, one per settled write, laid out as one Write Group by the
    model's own shapes, and the statements a dry traversal of it lowers to."""
    preparer = LayoutPayloadPreparer(bound_model(meta)) if payloads is None else payloads
    group = WriteGroup.from_members(
        ((SettledWrite(), (step,)) for step in steps), effect_shape=preparer.effect_shape
    )
    statements = list(
        stream_physical(
            group.steps,
            preparer,
            bound_model(meta),
            dialect,
            effect_spans=group.effect_spans,
        )
    )
    return group, statements


def arrays(statement: LoweredStatement) -> list[tuple[object, list[object]]]:
    return [
        (bind.element_type, bind.values) if isinstance(bind, ArrayBind) else ("scalar", [bind])
        for bind in statement.binds
    ]


def test_distinct_values_of_unversioned_updates_bind_one_array_per_source_column() -> None:
    steps = [
        update(WALLET, "Wallet", 1, {"balance": Decimal("111.00")}),
        update(WALLET, "Wallet", 2, {"balance": Decimal("222.00")}),
        update(WALLET, "Wallet", 3, {"balance": None}),
    ]
    group, (statement,) = grouped(WALLET, steps)
    assert group.effect_spans == (EffectSpan(0, 3, group.effect_spans[0].shape),)
    assert statement.sql == (
        "update px.wallet t set balance = v.c2 from unnest(cast(? as bigint[]), "
        "cast(? as decimal[])) with ordinality v(c1, c2, ord) where t.id = v.c1 "
        "returning v.ord"
    )
    assert arrays(statement) == [
        (INT64, [1, 2, 3]),
        (Numeric(18, 2), [Decimal("111.00"), Decimal("222.00"), None]),
    ]


def test_versioned_updates_bind_each_gate_and_planned_advance_per_row() -> None:
    steps = [
        update(ACCOUNT, "Account", 1, {"balance": Decimal("50.00")}, observed=3),
        update(ACCOUNT, "Account", 2, {"balance": Decimal("60.00")}, observed=7),
    ]
    _, (statement,) = grouped(ACCOUNT, steps)
    assert statement.sql == (
        "update px.account t set balance = v.c3, version = v.c4 from unnest("
        "cast(? as bigint[]), cast(? as int[]), cast(? as decimal[]), cast(? as int[])) "
        "with ordinality v(c1, c2, c3, c4, ord) where t.id = v.c1 and t.version = v.c2 "
        "returning v.ord"
    )
    assert arrays(statement) == [
        (INT64, [1, 2]),
        (INT32, [3, 7]),
        (Numeric(18, 2), [Decimal("50.00"), Decimal("60.00")]),
        (INT32, [4, 8]),
    ]


def test_a_table_per_hierarchy_tag_guard_binds_once_after_the_arrays() -> None:
    steps = [
        update(PAYMENT, "CardPayment", 1, {"amount": Decimal("5.00")}),
        update(PAYMENT, "CardPayment", 2, {"amount": Decimal("6.00")}),
    ]
    _, (statement,) = grouped(PAYMENT, steps)
    assert statement.sql == (
        "update px.payment t set amount = v.c2 from unnest(cast(? as bigint[]), "
        "cast(? as decimal[])) with ordinality v(c1, c2, ord) where t.id = v.c1 "
        "and t.kind = ? returning v.ord"
    )
    assert arrays(statement)[-1] == ("scalar", ["card"])


def test_a_composite_key_binds_one_array_per_key_column() -> None:
    steps = [
        update(
            WALLET, "Wallet", (1, "Ada"), {"balance": Decimal("1.00")}, key_members=("id", "owner")
        ),
        update(
            WALLET, "Wallet", (2, "Bo"), {"balance": Decimal("2.00")}, key_members=("id", "owner")
        ),
    ]
    _, (statement,) = grouped(WALLET, steps)
    assert statement.sql == (
        "update px.wallet t set balance = v.c3 from unnest(cast(? as bigint[]), "
        "cast(? as text[]), cast(? as decimal[])) with ordinality v(c1, c2, c3, ord) "
        "where t.id = v.c1 and t.owner = v.c2 returning v.ord"
    )
    assert arrays(statement)[:2] == [(INT64, [1, 2]), (STRING, ["Ada", "Bo"])]


def _ledger_document_updates() -> list[PlannedUpdate]:
    return [
        update(
            LEDGER_DOCUMENT,
            "TagLedger",
            1,
            {"label": "a", "tags": ("c", "c")},
            value_objects={"route": None},
            observed=1,
        ),
        update(
            LEDGER_DOCUMENT,
            "TagLedger",
            2,
            {"label": None, "tags": ()},
            value_objects={"route": {"stops": ("x",)}},
            observed=4,
        ),
    ]


def test_document_members_bind_as_one_jsonb_array_of_each_rows_assigned_members() -> None:
    steps = _ledger_document_updates()
    _, (statement,) = grouped(LEDGER_DOCUMENT, steps)
    assert statement.sql == (
        "update px.tag_ledger t set payload = t.payload || v.c4, version = v.c3 from unnest("
        "cast(? as bigint[]), cast(? as int[]), cast(? as int[]), cast(? as jsonb[])) "
        "with ordinality v(c1, c2, c3, c4, ord) where t.id = v.c1 and t.version = v.c2 "
        "returning v.ord"
    )
    assert [element for element, _ in arrays(statement)] == [INT64, INT32, INT32, JSON]
    assert statement.wire_binds() == (
        [1, 2],
        [1, 4],
        [2, 5],
        [
            {"label": "a", "tags": ["c", "c"], "route": None},
            {"label": None, "tags": [], "route": {"stops": ["x"]}},
        ],
    )
    first, second = arrays(statement)[3][1]
    assert list(cast("dict[str, object]", first)) == ["label", "tags", "route"]
    assert cast("dict[str, object]", second)["label"] is None


def test_a_document_effects_parameters_are_its_source_arrays() -> None:
    preparer = LayoutPayloadPreparer(bound_model(LEDGER_DOCUMENT))
    step = _ledger_document_updates()[0]
    shape = preparer.effect_shape(step)
    assert shape is not None
    slots = preparer.effect_slots(step.entity, shape)
    assert slots.assignment_sources == (2, 3)
    assert slots.element_types == (INT64, INT32, INT32, JSON)
    assert slots.parameter_count == 4


def test_a_document_effect_whose_patches_have_no_merged_form_gathers_nothing() -> None:
    preparer = LayoutPayloadPreparer(bound_model(LEDGER_DOCUMENT))
    steps = _ledger_document_updates()
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    builder = GroupedEffectBuilder(
        preparer.effect_slots(steps[0].entity, shape), bound_model(LEDGER_DOCUMENT), POSTGRES
    )
    builder.append(steps[0], preparer.assignments(steps[0].entity, steps[0].assignments))
    payload = preparer.assignments(steps[1].entity, steps[1].assignments)
    removing = tuple(
        DocumentPatches((dataclasses.replace(value.patches[0], removes=True), *value.patches[1:]))
        if isinstance(value, DocumentPatches)
        else value
        for value in payload.values
    )
    with pytest.raises(ValueError, match="top-level and remove no key"):
        builder.append(steps[1], dataclasses.replace(payload, values=removing))
    assert [len(values) for _, values in arrays(builder.finish())] == [1, 1, 1, 1]


def test_a_value_object_column_and_a_collection_column_bind_whole_documents() -> None:
    steps = [
        update(
            LEDGER_COLUMNS,
            "TagLedger",
            1,
            {"tags": ("c",)},
            value_objects={"route": None},
            observed=1,
        ),
        update(
            LEDGER_COLUMNS,
            "TagLedger",
            2,
            {"tags": ()},
            value_objects={"route": {"stops": ("y",)}},
            observed=4,
        ),
    ]
    _, (statement,) = grouped(LEDGER_COLUMNS, steps)
    assert statement.sql == (
        "update px.tag_ledger t set tags = v.c4, route = v.c5, version = v.c3 from unnest("
        "cast(? as bigint[]), cast(? as int[]), cast(? as int[]), cast(? as jsonb[]), "
        "cast(? as jsonb[])) with ordinality v(c1, c2, c3, c4, c5, ord) "
        "where t.id = v.c1 and t.version = v.c2 returning v.ord"
    )
    assert [element for element, _ in arrays(statement)[3:]] == [JSON, JSON]
    assert statement.wire_binds()[3:] == ([["c"], []], [None, {"stops": ["y"]}])
    assert arrays(statement)[4][1][0] is None


def test_differing_member_sets_form_one_grouped_effect_each_in_first_appearance_order() -> None:
    steps = [
        update(WALLET, "Wallet", 1, {"balance": Decimal("1.00")}),
        update(WALLET, "Wallet", 2, {"owner": "Bo"}),
        update(WALLET, "Wallet", 3, {"balance": Decimal("3.00")}),
        update(WALLET, "Wallet", 4, {"owner": "Di"}),
    ]
    group, statements = grouped(WALLET, steps)
    assert group.steps == tuple(steps[i] for i in (0, 2, 1, 3))
    assert [statement.sql.split(" from ")[0] for statement in statements] == [
        "update px.wallet t set balance = v.c2",
        "update px.wallet t set owner = v.c2",
    ]


def test_a_lone_effect_of_its_shape_lowers_as_it_would_alone() -> None:
    steps = [
        update(WALLET, "Wallet", 1, {"balance": Decimal("1.00")}),
        update(WALLET, "Wallet", 2, {"owner": "Bo"}),
        update(WALLET, "Wallet", 3, {"balance": Decimal("3.00")}),
    ]
    group, statements = grouped(WALLET, steps)
    assert len(group.effect_spans) == 1
    assert statements[1].sql == "update px.wallet set owner = ? where id = ?"


def test_a_registry_advance_runs_alone_beside_grouped_updates() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    advance = dataclasses.replace(
        update(WALLET, "Wallet", 2, {"balance": Decimal("2.00")}),
        assignments=PlannedAssignments(
            attributes={attribute_identity(WALLET, "Wallet", "balance"): SelfIncrement(5)}
        ),
    )
    assert preparer.effect_shape(advance) is None
    steps = [
        update(WALLET, "Wallet", 1, {"balance": Decimal("1.00")}),
        advance,
        update(WALLET, "Wallet", 3, {"balance": Decimal("3.00")}),
        update(WALLET, "Wallet", 4, {"balance": Decimal("4.00")}),
    ]
    group, statements = grouped(WALLET, steps, payloads=preparer)
    assert [statement.sql.startswith("update px.wallet t") for statement in statements] == [
        False,
        False,
        True,
    ]
    assert statements[1].sql == "update px.wallet set balance = balance + ? where id = ?"
    assert group.effect_spans == (EffectSpan(2, 4, group.effect_spans[0].shape),)


def test_assigning_a_unique_key_member_is_a_barrier_in_authored_order() -> None:
    preparer = LayoutPayloadPreparer(bound_model(PERSON))
    handoff = [
        update(PERSON, "Passport", 1, {"number": "A"}),
        update(PERSON, "Passport", 2, {"personId": 7}),
        update(PERSON, "Passport", 3, {"number": "C"}),
    ]
    assert preparer.effect_shape(handoff[1]) is None
    group, statements = grouped(PERSON, handoff, payloads=preparer)
    assert group.steps == tuple(handoff)
    assert group.effect_spans == ()
    assert [statement.sql for statement in statements] == [
        "update px.passport set number = ? where id = ?",
        "update px.passport set person_id = ? where id = ?",
        "update px.passport set number = ? where id = ?",
    ]


@pytest.mark.parametrize(
    "step",
    [
        PlannedDelete(
            entity=entity_identity(WALLET, "Wallet"),
            target=KeyTarget(
                key_attributes=(attribute_identity(WALLET, "Wallet", "id"),),
                key_values=((1,), (2,)),
            ),
            concurrency=UNVERSIONED,
            affected_rows=ExactCount(2, MISSING_TARGET),
        ),
        PlannedUpdate(
            entity=entity_identity(WALLET, "Wallet"),
            target=KeyTarget(
                key_attributes=(attribute_identity(WALLET, "Wallet", "id"),),
                key_values=((1,), (2,)),
            ),
            assignments=PlannedAssignments(
                attributes={attribute_identity(WALLET, "Wallet", "balance"): Decimal("1.00")}
            ),
            concurrency=UNVERSIONED,
            affected_rows=ExactCount(2, MISSING_TARGET),
        ),
    ],
    ids=["multi-key-delete", "multi-key-update"],
)
def test_effects_outside_the_grouped_kinds_have_no_shape(step: PlannedStep) -> None:
    assert LayoutPayloadPreparer(bound_model(WALLET)).effect_shape(step) is None


def test_shapes_compare_by_value_past_the_retained_slots() -> None:
    preparer = LayoutPayloadPreparer(bound_model(PAYMENT))
    entity = entity_identity(PAYMENT, "CardPayment")
    for presence in range(ROW_SLOTS_PER_ENTITY + 2):
        preparer.effect_slots(entity, EffectShape(PlannedUpdate, entity, (), presence + 64, None))
    steps = [
        update(PAYMENT, "CardPayment", 1, {"amount": Decimal("5.00")}),
        update(PAYMENT, "CardPayment", 2, {"amount": Decimal("6.00")}),
    ]
    first, second = (preparer.effect_shape(step) for step in steps)
    assert first == second and first is not second and hash(first) == hash(second)
    group, statements = grouped(PAYMENT, steps, payloads=preparer)
    assert len(group.effect_spans) == 1 and len(statements) == 1


def test_an_array_less_dialect_lowers_every_effect_alone() -> None:
    steps = [
        update(WALLET, "Wallet", 1, {"balance": Decimal("1.00")}),
        update(WALLET, "Wallet", 2, {"balance": Decimal("2.00")}),
    ]
    arrayless = dataclasses.replace(POSTGRES, name="mariadb", binds_arrays=False)
    group, statements = grouped(WALLET, steps, dialect=arrayless)
    assert len(group.effect_spans) == 1
    assert [statement.sql for statement in statements] == [
        "update px.wallet set balance = ? where id = ?"
    ] * 2


def test_a_shape_wider_than_the_bind_limit_lowers_every_effect_alone() -> None:
    steps = [
        update(PAYMENT, "CardPayment", 1, {"amount": Decimal("5.00")}),
        update(PAYMENT, "CardPayment", 2, {"amount": Decimal("6.00")}),
    ]
    narrow = dataclasses.replace(POSTGRES, max_bind_parameters=2)
    _, statements = grouped(PAYMENT, steps, dialect=narrow)
    assert [statement.sql for statement in statements] == [
        "update px.payment set amount = ? where id = ? and kind = ?"
    ] * 2


class _Refused(Exception):
    pass


class _FailingPreparer(LayoutPayloadPreparer):
    """The model's preparer refusing ``failing``'s assignments with ``failure``."""

    __slots__ = ("failing", "failure", "prepared")

    def __init__(self, meta: Metamodel, failing: PlannedUpdate, failure: BaseException) -> None:
        super().__init__(bound_model(meta))
        self.failing = failing
        self.failure = failure
        self.prepared: list[object] = []

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        self.prepared.append(assignments)
        if assignments is self.failing.assignments:
            raise self.failure
        return super().assignments(entity, assignments)


def _three() -> list[PlannedUpdate]:
    return [update(WALLET, "Wallet", key, {"balance": Decimal(key)}) for key in (1, 2, 3)]


def _span_cursor(
    steps: Sequence[PlannedStep], preparer: LayoutPayloadPreparer
) -> tuple[LoweringCursor, EffectSpan]:
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    span = EffectSpan(0, len(steps), shape)
    cursor = LoweringCursor(
        tuple(steps), preparer, bound_model(WALLET), POSTGRES, effect_spans=(span,)
    )
    first = cursor.take()
    assert first is not None and cursor.grouped_effect_start(first) is span
    return cursor, span


def test_a_later_preparation_failure_ends_the_statement_at_its_valid_prefix() -> None:
    steps = _three()
    failure = _Refused()
    preparer = _FailingPreparer(WALLET, steps[2], failure)
    cursor, span = _span_cursor(steps, preparer)
    statement, held, raised = cursor.lowered_grouped_effect(steps[0], span)
    assert held == tuple(steps[:2])
    assert raised is failure
    assert arrays(statement)[0] == (INT64, [1, 2])


def test_a_second_effect_failing_still_presents_the_first_alone() -> None:
    steps = _three()
    failure = _Refused()
    preparer = _FailingPreparer(WALLET, steps[1], failure)
    cursor, span = _span_cursor(steps, preparer)
    statement, held, raised = cursor.lowered_grouped_effect(steps[0], span)
    assert held == (steps[0],)
    assert raised is failure
    assert arrays(statement)[0] == (INT64, [1])


def test_the_dry_traversal_answers_the_prefix_then_raises_the_held_failure() -> None:
    steps = _three()
    failure = _Refused()
    preparer = _FailingPreparer(WALLET, steps[2], failure)
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    traversal = stream_physical(
        tuple(steps),
        preparer,
        bound_model(WALLET),
        POSTGRES,
        effect_spans=(EffectSpan(0, 3, shape),),
    )
    assert arrays(next(traversal))[0] == (INT64, [1, 2])
    with pytest.raises(_Refused):
        next(traversal)


def test_a_grouped_effect_refuses_a_dialect_binding_no_arrays() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    step = update(WALLET, "Wallet", 1, {"balance": Decimal(1)})
    shape = preparer.effect_shape(step)
    assert shape is not None
    slots = preparer.effect_slots(step.entity, shape)
    arrayless = dataclasses.replace(POSTGRES, binds_arrays=False)
    with raises_code(InternalError, SQL_GENERATION_FAILED, match="binds no arrays"):
        GroupedEffectBuilder(slots, bound_model(WALLET), arrayless)


def test_a_grouped_effect_refuses_an_effect_its_shape_does_not_place() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    balance = update(WALLET, "Wallet", 1, {"balance": Decimal(1)})
    owner = update(WALLET, "Wallet", 2, {"owner": "Bo", "balance": Decimal(2)})
    shape = preparer.effect_shape(balance)
    assert shape is not None
    builder = GroupedEffectBuilder(
        preparer.effect_slots(balance.entity, shape), bound_model(WALLET), POSTGRES
    )
    builder.append(balance, preparer.assignments(balance.entity, balance.assignments))
    with raises_code(InternalError, SQL_GENERATION_FAILED, match="does not place"):
        builder.append(owner, preparer.assignments(owner.entity, owner.assignments))
    deletion = PlannedDelete(
        entity=balance.entity,
        target=balance.target,
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )
    with raises_code(
        InternalError, SQL_GENERATION_FAILED, match="holds effects of its shape's kind"
    ):
        builder.append(deletion, None)
    assert arrays(builder.finish())[0] == (INT64, [1])


def test_a_grouped_effect_refuses_an_effect_gated_otherwise_than_its_shape() -> None:
    preparer = LayoutPayloadPreparer(bound_model(ACCOUNT))
    ungated = delete(ACCOUNT, "Account", 1, versioned=True)
    shape = preparer.effect_shape(ungated)
    assert shape is not None
    builder = GroupedEffectBuilder(
        preparer.effect_slots(ungated.entity, shape), bound_model(ACCOUNT), POSTGRES
    )
    builder.append(ungated, None)
    with raises_code(
        InternalError,
        SQL_GENERATION_FAILED,
        match="addresses or gates its row otherwise than its shape",
    ):
        builder.append(delete(ACCOUNT, "Account", 2, observed=1), None)
    assert arrays(builder.finish()) == [(INT64, [1])]


def test_a_grouped_effect_keeps_no_payload_but_its_first_past_its_append() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    steps = _three()
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    builder = GroupedEffectBuilder(
        preparer.effect_slots(steps[0].entity, shape), bound_model(WALLET), POSTGRES
    )
    payloads = [preparer.assignments(step.entity, step.assignments) for step in steps]
    unheld = [sys.getrefcount(payload) for payload in payloads]
    for index, step in enumerate(steps):
        builder.append(step, payloads[index])
    # The first effect's placement renders the statement; every later one's
    # cells are already in its source columns.
    held = [sys.getrefcount(payload) for payload in payloads]
    assert [now - before for now, before in zip(held, unheld, strict=True)] == [1, 0, 0]
    del payloads
    assert arrays(builder.finish())[0] == (INT64, [1, 2, 3])


def test_effect_slots_gather_a_whole_row_or_nothing() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    step = _three()[0]
    shape = preparer.effect_shape(step)
    assert shape is not None
    slots = preparer.effect_slots(step.entity, shape)
    payload = preparer.assignments(step.entity, step.assignments)
    narrow: list[list[object]] = [[] for _ in slots.element_types[:-1]]
    with raises_code(InternalError, WRITE_PLANNING_FAILED, match="one cell per source column"):
        slots.gather(narrow, step, payload)
    assert narrow == [[] for _ in narrow]
    columns: list[list[object]] = [[] for _ in slots.element_types]
    slots.gather(columns, step, payload)
    assert [len(column) for column in columns] == [1] * len(columns)


def test_a_grouped_effect_holding_no_effect_has_no_statement() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    step = _three()[0]
    shape = preparer.effect_shape(step)
    assert shape is not None
    builder = GroupedEffectBuilder(
        preparer.effect_slots(step.entity, shape), bound_model(WALLET), POSTGRES
    )
    with raises_code(InternalError, SQL_GENERATION_FAILED, match="holds an effect"):
        builder.finish()


def test_effect_slots_answer_only_a_shape_of_their_own_entity() -> None:
    preparer = LayoutPayloadPreparer(bound_model(PAYMENT))
    with raises_code(InternalError, WRITE_PLANNING_FAILED, match="Effect Slots of its own Entity"):
        preparer.effect_slots(entity_identity(PAYMENT, "CardPayment"), "not a shape")


def test_a_grouped_effect_opens_only_at_its_own_span() -> None:
    preparer = LayoutPayloadPreparer(bound_model(WALLET))
    steps = _three()
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    cursor = LoweringCursor(tuple(steps), preparer, bound_model(WALLET), POSTGRES)
    first = cursor.take()
    assert first is not None
    with raises_code(InternalError, SQL_GENERATION_FAILED, match="opens at its own span"):
        cursor.lowered_grouped_effect(first, EffectSpan(0, 3, shape))


# --------------------------------------------------------------------------- #
# Deletes and milestone effects.                                               #
# --------------------------------------------------------------------------- #
def test_unversioned_deletes_bind_one_key_array_and_return_each_removed_ordinal() -> None:
    _, (statement,) = grouped(WALLET, [delete(WALLET, "Wallet", key) for key in (1, 2, 3)])
    assert statement.sql == (
        "delete from px.wallet t using unnest(cast(? as bigint[])) with ordinality "
        "v(c1, ord) where t.id = v.c1 returning v.ord"
    )
    assert arrays(statement) == [(INT64, [1, 2, 3])]


def test_gated_deletes_bind_each_rows_observed_version() -> None:
    steps = [delete(ACCOUNT, "Account", 1, observed=3), delete(ACCOUNT, "Account", 2, observed=7)]
    _, (statement,) = grouped(ACCOUNT, steps)
    assert statement.sql == (
        "delete from px.account t using unnest(cast(? as bigint[]), cast(? as int[])) with "
        "ordinality v(c1, c2, ord) where t.id = v.c1 and t.version = v.c2 returning v.ord"
    )
    assert arrays(statement) == [(INT64, [1, 2]), (INT32, [3, 7])]


def test_gated_and_ungated_deletes_of_one_entity_are_distinct_shapes() -> None:
    steps = [
        delete(ACCOUNT, "Account", 1, versioned=True),
        delete(ACCOUNT, "Account", 2, observed=1),
        delete(ACCOUNT, "Account", 3, versioned=True),
    ]
    group, statements = grouped(ACCOUNT, steps)
    assert group.steps == (steps[0], steps[2], steps[1])
    assert [statement.sql for statement in statements] == [
        "delete from px.account t using unnest(cast(? as bigint[])) with ordinality v(c1, ord) "
        "where t.id = v.c1 returning v.ord",
        "delete from px.account where id = ? and version = ?",
    ]


def test_table_per_hierarchy_and_composite_key_deletes_keep_the_lone_address() -> None:
    _, (tagged,) = grouped(PAYMENT, [delete(PAYMENT, "CardPayment", key) for key in (1, 2)])
    assert tagged.sql == (
        "delete from px.payment t using unnest(cast(? as bigint[])) with ordinality v(c1, ord) "
        "where t.id = v.c1 and t.kind = ? returning v.ord"
    )
    assert arrays(tagged)[-1] == ("scalar", ["card"])
    composite = [
        delete(WALLET, "Wallet", key, key_members=("id", "owner"))
        for key in ((1, "Ada"), (2, "Bo"))
    ]
    _, (statement,) = grouped(WALLET, composite)
    assert statement.sql == (
        "delete from px.wallet t using unnest(cast(? as bigint[]), cast(? as text[])) with "
        "ordinality v(c1, c2, ord) where t.id = v.c1 and t.owner = v.c2 returning v.ord"
    )


def test_transaction_time_closes_bind_their_gate_and_instant_and_share_the_open_end() -> None:
    steps = [
        close(BALANCE, "Balance", milestone(BALANCE, "Balance", key, bitemporal=False), observed=at)
        for key, at in ((1, instant(1)), (2, instant(2)))
    ]
    _, (statement,) = grouped(BALANCE, steps)
    assert statement.sql == (
        "update px.balance t set out_z = v.c3 from unnest(cast(? as bigint[]), "
        "cast(? as timestamptz[]), cast(? as timestamptz[])) with ordinality "
        "v(c1, c2, c3, ord) where t.bal_id = v.c1 and t.out_z = ? and t.in_z = v.c2 "
        "returning v.ord"
    )
    assert arrays(statement) == [
        (INT64, [1, 2]),
        (TIMESTAMP, [instant(1), instant(2)]),
        (TIMESTAMP, [CLOSED_AT, CLOSED_AT]),
        ("scalar", ["infinity"]),
    ]


def test_bitemporal_closes_bind_each_finite_or_open_valid_end_per_row() -> None:
    steps = [
        close(POSITION, "Position", milestone(POSITION, "Position", 1, valid_end=instant(6))),
        close(POSITION, "Position", milestone(POSITION, "Position", 2)),
    ]
    _, (statement,) = grouped(POSITION, steps)
    assert statement.sql == (
        "update px.position t set out_z = v.c3 from unnest(cast(? as bigint[]), "
        "cast(? as timestamptz[]), cast(? as timestamptz[])) with ordinality "
        "v(c1, c2, c3, ord) where t.pos_id = v.c1 and t.thru_z = v.c2 and t.out_z = ? "
        "returning v.ord"
    )
    assert arrays(statement)[1] == (TIMESTAMP, [instant(6), INFINITY])
    assert statement.wire_binds()[1] == ["2024-06-01T00:00:00.000000Z", "infinity"]


def test_a_table_per_hierarchy_milestone_guards_its_tag_before_its_axis_ends() -> None:
    steps = [
        close(INSTRUMENT, "Bond", milestone(INSTRUMENT, "Bond", key), observed=instant(1))
        for key in (1, 2)
    ]
    _, (statement,) = grouped(INSTRUMENT, steps)
    assert statement.sql.split(" where ")[1] == (
        "t.id = v.c1 and t.kind = ? and t.thru_z = v.c2 and t.out_z = ? and t.in_z = v.c3 "
        "returning v.ord"
    )
    assert arrays(statement)[-2:] == [("scalar", ["bond"]), ("scalar", ["infinity"])]


def test_a_composite_milestone_key_binds_one_array_per_key_column() -> None:
    steps = [
        close(
            BALANCE,
            "Balance",
            milestone(BALANCE, "Balance", key, bitemporal=False, key_members=("id", "acctNum")),
        )
        for key in ((1, "A"), (2, "B"))
    ]
    _, (statement,) = grouped(BALANCE, steps)
    assert statement.sql.split(" where ")[1] == (
        "t.bal_id = v.c1 and t.acct_num = v.c2 and t.out_z = ? returning v.ord"
    )
    assert arrays(statement)[:2] == [(INT64, [1, 2]), (STRING, ["A", "B"])]


def test_guards_assign_their_start_to_itself_and_gate_each_rows_observed_start() -> None:
    steps = [
        guard(BALANCE, "Balance", milestone(BALANCE, "Balance", key, bitemporal=False), observed=at)
        for key, at in ((1, instant(1)), (2, instant(2)))
    ]
    _, (statement,) = grouped(BALANCE, steps)
    assert statement.sql == (
        "update px.balance t set in_z = t.in_z from unnest(cast(? as bigint[]), "
        "cast(? as timestamptz[])) with ordinality v(c1, c2, ord) where t.bal_id = v.c1 "
        "and t.out_z = ? and t.in_z = v.c2 returning v.ord"
    )


@pytest.mark.parametrize("observed", [None, instant(1)], ids=["ungated", "gated"])
def test_removals_delete_each_addressed_milestone(observed: dt.datetime | None) -> None:
    steps = [
        removal(POSITION, "Position", milestone(POSITION, "Position", key), observed=observed)
        for key in (1, 2)
    ]
    _, (statement,) = grouped(POSITION, steps)
    gate = " and t.in_z = v.c3" if observed is not None else ""
    sources = ", cast(? as timestamptz[])" if observed is not None else ""
    names = "c1, c2, c3" if observed is not None else "c1, c2"
    assert statement.sql == (
        "delete from px.position t using unnest(cast(? as bigint[]), cast(? as timestamptz[])"
        f"{sources}) with ordinality v({names}, ord) where t.pos_id = v.c1 and "
        f"t.thru_z = v.c2 and t.out_z = ?{gate} returning v.ord"
    )


def test_revisions_assign_payload_and_valid_start_per_row() -> None:
    steps = [
        revision(
            POSITION,
            "Position",
            milestone(POSITION, "Position", key),
            {"value": Decimal(value), "validStart": instant(month)},
        )
        for key, value, month in ((1, "1.00", 3), (2, "2.00", 4))
    ]
    _, (statement,) = grouped(POSITION, steps)
    assert statement.sql == (
        "update px.position t set val = v.c3, from_z = v.c4 from unnest(cast(? as bigint[]), "
        "cast(? as timestamptz[]), cast(? as decimal[]), cast(? as timestamptz[])) with "
        "ordinality v(c1, c2, c3, c4, ord) where t.pos_id = v.c1 and t.thru_z = v.c2 and "
        "t.out_z = ? returning v.ord"
    )
    assert arrays(statement)[2:4] == [
        (Numeric(18, 2), [Decimal("1.00"), Decimal("2.00")]),
        (TIMESTAMP, [instant(3), instant(4)]),
    ]


def test_document_revisions_merge_each_rows_assigned_members_from_the_source() -> None:
    steps = [
        revision(
            COVERAGE_DOCUMENT,
            "CoverageSpan",
            milestone(COVERAGE_DOCUMENT, "CoverageSpan", key),
            {"amount": amount},
        )
        for key, amount in ((1, 150), (2, 250))
    ]
    _, (statement,) = grouped(COVERAGE_DOCUMENT, steps)
    assert statement.sql == (
        "update px.coverage_span t set payload = t.payload || v.c3 from unnest("
        "cast(? as bigint[]), cast(? as timestamptz[]), cast(? as jsonb[])) with ordinality "
        "v(c1, c2, c3, ord) where t.id = v.c1 and t.thru_z = v.c2 and t.out_z = ? "
        "returning v.ord"
    )
    assert statement.wire_binds()[2] == [{"amount": 150}, {"amount": 250}]


def test_a_revision_patching_a_document_not_known_to_be_an_object_ends_the_prefix() -> None:
    preparer = LayoutPayloadPreparer(bound_model(COVERAGE_DOCUMENT))
    steps = [
        revision(
            COVERAGE_DOCUMENT,
            "CoverageSpan",
            milestone(COVERAGE_DOCUMENT, "CoverageSpan", key),
            {"amount": key},
            document_is_object=key != 3,
        )
        for key in (1, 2, 3)
    ]
    shape = preparer.effect_shape(steps[0])
    assert shape is not None and preparer.effect_shape(steps[2]) == shape
    span = EffectSpan(0, 3, shape)
    cursor = LoweringCursor(
        tuple(steps),
        preparer,
        bound_model(COVERAGE_DOCUMENT),
        POSTGRES,
        effect_spans=(span,),
    )
    first = cursor.take()
    assert first is not None and cursor.grouped_effect_start(first) is span
    statement, held, raised = cursor.lowered_grouped_effect(first, span)
    assert held == tuple(steps[:2])
    assert isinstance(raised, InvalidDataError) and raised.code == STORED_DOCUMENT_NOT_OBJECT
    assert "not known to be an object" in str(raised)
    assert arrays(statement)[0] == (INT64, [1, 2])


def test_each_milestone_kind_and_gate_is_its_own_shape() -> None:
    preparer = LayoutPayloadPreparer(bound_model(POSITION))
    target = milestone(POSITION, "Position", 1)
    shapes = [
        preparer.effect_shape(step)
        for step in (
            close(POSITION, "Position", target),
            close(POSITION, "Position", target, observed=instant(1)),
            removal(POSITION, "Position", target),
            guard(POSITION, "Position", target, observed=instant(1)),
            revision(POSITION, "Position", target, {"value": Decimal(1)}),
        )
    ]
    assert None not in shapes
    assert len(set(shapes)) == len(shapes)
    finite = close(POSITION, "Position", milestone(POSITION, "Position", 2, valid_end=instant(6)))
    assert preparer.effect_shape(finite) == shapes[0]


def test_one_writes_closes_of_distinct_milestones_share_its_shapes_statement() -> None:
    preparer = LayoutPayloadPreparer(bound_model(POSITION))
    first = [
        close(POSITION, "Position", milestone(POSITION, "Position", 1, valid_end=instant(6))),
        close(POSITION, "Position", milestone(POSITION, "Position", 1)),
    ]
    second = [close(POSITION, "Position", milestone(POSITION, "Position", 2))]
    group = WriteGroup.from_members(
        [(SettledWrite(), tuple(first)), (SettledWrite(), tuple(second))],
        effect_shape=preparer.effect_shape,
    )
    (statement,) = stream_physical(
        group.steps,
        preparer,
        bound_model(POSITION),
        POSTGRES,
        effect_spans=group.effect_spans,
    )
    assert group.steps == (*first, *second)
    assert arrays(statement)[0] == (INT64, [1, 1, 2])
    assert arrays(statement)[1] == (TIMESTAMP, [instant(6), INFINITY, INFINITY])


def test_a_writes_later_close_waits_behind_its_own_revision() -> None:
    preparer = LayoutPayloadPreparer(bound_model(POSITION))
    own = [
        close(POSITION, "Position", milestone(POSITION, "Position", 1, valid_end=instant(6))),
        revision(POSITION, "Position", milestone(POSITION, "Position", 1), {"value": Decimal(1)}),
        close(POSITION, "Position", milestone(POSITION, "Position", 1)),
    ]
    other = [close(POSITION, "Position", milestone(POSITION, "Position", 2))]
    group = WriteGroup.from_members(
        [(SettledWrite(), tuple(own)), (SettledWrite(), tuple(other))],
        effect_shape=preparer.effect_shape,
    )
    # The later close cannot join the block before its own write's revision, so
    # it opens a later block, which the other write's close then joins.
    assert group.steps == (own[0], own[1], own[2], other[0])
    (span,) = group.effect_spans
    assert (span.start, span.stop) == (2, 4)
