"""Grouped effects as lowering presents them (`m-sql` *Grouped effects*).

Updates of one key each that a Write Group lays out in one effect span lower as
one statement whose `unnest(…) with ordinality` source binds one typed array per
source column and returns each changed row's source ordinal. Every expectation
here is authored from the grammar, not read back from production.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from decimal import Decimal

import pytest

from parallax.core._execution._write_lowering import LoweringCursor, stream_physical
from parallax.core.base import INT32, INT64, JSON, STRING
from parallax.core.base import Decimal as DecimalType
from parallax.core.db_port import ArrayBind
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import GroupedEffectBuilder
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_payload._storage import ROW_SLOTS_PER_ENTITY, EffectShape
from parallax.core.write_plan.payload import AssignmentPayload
from parallax.core.write_plan.plan import EffectSpan, SettledWrite, WriteGroup
from parallax.core.write_plan.planned_rows import WritePlanningError
from parallax.core.write_plan.steps import (
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
from tests.unit._corpus_model_support import model
from tests.unit.core._execution._grouped_effect_support import (
    ACCOUNT,
    WALLET,
    attribute_identity,
    entity_identity,
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
    preparer = LayoutPayloadPreparer(meta) if payloads is None else payloads
    group = WriteGroup.from_members(
        ((SettledWrite(), (step,)) for step in steps), effect_shape=preparer.effect_shape
    )
    statements = list(
        stream_physical(group.steps, preparer, meta, dialect, effect_spans=group.effect_spans)
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
        "update wallet t set balance = v.c2 from unnest(cast(? as bigint[]), "
        "cast(? as decimal[])) with ordinality v(c1, c2, ord) where t.id = v.c1 "
        "returning v.ord"
    )
    assert arrays(statement) == [
        (INT64, [1, 2, 3]),
        (DecimalType(18, 2), [Decimal("111.00"), Decimal("222.00"), None]),
    ]


def test_versioned_updates_bind_each_gate_and_planned_advance_per_row() -> None:
    steps = [
        update(ACCOUNT, "Account", 1, {"balance": Decimal("50.00")}, observed=3),
        update(ACCOUNT, "Account", 2, {"balance": Decimal("60.00")}, observed=7),
    ]
    _, (statement,) = grouped(ACCOUNT, steps)
    assert statement.sql == (
        "update account t set balance = v.c3, version = v.c4 from unnest("
        "cast(? as bigint[]), cast(? as int[]), cast(? as decimal[]), cast(? as int[])) "
        "with ordinality v(c1, c2, c3, c4, ord) where t.id = v.c1 and t.version = v.c2 "
        "returning v.ord"
    )
    assert arrays(statement) == [
        (INT64, [1, 2]),
        (INT32, [3, 7]),
        (DecimalType(18, 2), [Decimal("50.00"), Decimal("60.00")]),
        (INT32, [4, 8]),
    ]


def test_a_table_per_hierarchy_tag_guard_binds_once_after_the_arrays() -> None:
    steps = [
        update(PAYMENT, "CardPayment", 1, {"amount": Decimal("5.00")}),
        update(PAYMENT, "CardPayment", 2, {"amount": Decimal("6.00")}),
    ]
    _, (statement,) = grouped(PAYMENT, steps)
    assert statement.sql == (
        "update payment t set amount = v.c2 from unnest(cast(? as bigint[]), "
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
        "update wallet t set balance = v.c3 from unnest(cast(? as bigint[]), "
        "cast(? as text[]), cast(? as decimal[])) with ordinality v(c1, c2, c3, ord) "
        "where t.id = v.c1 and t.owner = v.c2 returning v.ord"
    )
    assert arrays(statement)[:2] == [(INT64, [1, 2]), (STRING, ["Ada", "Bo"])]


def test_document_paths_bind_once_and_their_values_one_jsonb_array_each() -> None:
    steps = [
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
    _, (statement,) = grouped(LEDGER_DOCUMENT, steps)
    assert statement.sql == (
        "update tag_ledger t set payload = jsonb_set(jsonb_set(jsonb_set(t.payload, ?, v.c4), "
        "?, v.c5), ?, v.c6), version = v.c3 from unnest(cast(? as bigint[]), "
        "cast(? as int[]), cast(? as int[]), cast(? as jsonb[]), cast(? as jsonb[]), "
        "cast(? as jsonb[])) with ordinality v(c1, c2, c3, c4, c5, c6, ord) "
        "where t.id = v.c1 and t.version = v.c2 returning v.ord"
    )
    assert [element for element, _ in arrays(statement)[3:]] == [INT64, INT32, INT32] + [JSON] * 3
    assert statement.wire_binds() == (
        "{label}",
        "{tags}",
        "{route}",
        [1, 2],
        [1, 4],
        [2, 5],
        ["a", None],
        [["c", "c"], []],
        [None, {"stops": ["x"]}],
    )


def test_a_value_object_column_and_a_collection_column_bind_whole_documents() -> None:
    # A null Value Object crosses as the document carrier's own null element; how
    # an adapter stores it is the shared carrier's decision, not this one's.
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
        "update tag_ledger t set tags = v.c4, route = v.c5, version = v.c3 from unnest("
        "cast(? as bigint[]), cast(? as int[]), cast(? as int[]), cast(? as jsonb[]), "
        "cast(? as jsonb[])) with ordinality v(c1, c2, c3, c4, c5, ord) "
        "where t.id = v.c1 and t.version = v.c2 returning v.ord"
    )
    assert [element for element, _ in arrays(statement)[3:]] == [JSON, JSON]
    assert statement.wire_binds()[3:] == ([["c"], []], [None, {"stops": ["y"]}])


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
        "update wallet t set balance = v.c2",
        "update wallet t set owner = v.c2",
    ]


def test_a_lone_effect_of_its_shape_lowers_as_it_would_alone() -> None:
    steps = [
        update(WALLET, "Wallet", 1, {"balance": Decimal("1.00")}),
        update(WALLET, "Wallet", 2, {"owner": "Bo"}),
        update(WALLET, "Wallet", 3, {"balance": Decimal("3.00")}),
    ]
    group, statements = grouped(WALLET, steps)
    assert len(group.effect_spans) == 1
    assert statements[1].sql == "update wallet set owner = ? where id = ?"


def test_a_registry_advance_runs_alone_beside_grouped_updates() -> None:
    preparer = LayoutPayloadPreparer(WALLET)
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
    assert [statement.sql.startswith("update wallet t") for statement in statements] == [
        False,
        False,
        True,
    ]
    assert statements[1].sql == "update wallet set balance = balance + ? where id = ?"
    assert group.effect_spans == (EffectSpan(2, 4, group.effect_spans[0].shape),)


def test_assigning_a_unique_key_member_is_a_barrier_in_authored_order() -> None:
    preparer = LayoutPayloadPreparer(PERSON)
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
        "update passport set number = ? where id = ?",
        "update passport set person_id = ? where id = ?",
        "update passport set number = ? where id = ?",
    ]


@pytest.mark.parametrize(
    "step",
    [
        PlannedDelete(
            entity=entity_identity(WALLET, "Wallet"),
            target=KeyTarget(
                key_attributes=(attribute_identity(WALLET, "Wallet", "id"),), key_values=((1,),)
            ),
            concurrency=UNVERSIONED,
            affected_rows=ExactCount(1, MISSING_TARGET),
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
    ids=["delete", "multi-key"],
)
def test_effects_outside_the_grouped_kinds_have_no_shape(step: PlannedStep) -> None:
    assert LayoutPayloadPreparer(WALLET).effect_shape(step) is None


def test_shapes_compare_by_value_past_the_retained_slots() -> None:
    preparer = LayoutPayloadPreparer(PAYMENT)
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
        "update wallet set balance = ? where id = ?"
    ] * 2


def test_a_shape_wider_than_the_bind_limit_lowers_every_effect_alone() -> None:
    steps = [
        update(PAYMENT, "CardPayment", 1, {"amount": Decimal("5.00")}),
        update(PAYMENT, "CardPayment", 2, {"amount": Decimal("6.00")}),
    ]
    narrow = dataclasses.replace(POSTGRES, max_bind_parameters=2)
    _, statements = grouped(PAYMENT, steps, dialect=narrow)
    assert [statement.sql for statement in statements] == [
        "update payment set amount = ? where id = ? and kind = ?"
    ] * 2


class _Refused(Exception):
    pass


class _FailingPreparer(LayoutPayloadPreparer):
    """The model's preparer refusing ``failing``'s assignments with ``failure``."""

    __slots__ = ("failing", "failure", "prepared")

    def __init__(self, meta: Metamodel, failing: PlannedUpdate, failure: BaseException) -> None:
        super().__init__(meta)
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
    cursor = LoweringCursor(tuple(steps), preparer, WALLET, POSTGRES, effect_spans=(span,))
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


def test_the_first_effect_failing_presents_nothing() -> None:
    steps = _three()
    failure = _Refused()
    preparer = _FailingPreparer(WALLET, steps[0], failure)
    cursor, span = _span_cursor(steps, preparer)
    with pytest.raises(_Refused) as raised:
        cursor.lowered_grouped_effect(steps[0], span)
    assert raised.value is failure


def test_a_control_flow_exception_preparing_a_later_effect_presents_none_of_the_span() -> None:
    steps = _three()
    preparer = _FailingPreparer(WALLET, steps[2], KeyboardInterrupt())
    cursor, span = _span_cursor(steps, preparer)
    with pytest.raises(KeyboardInterrupt):
        cursor.lowered_grouped_effect(steps[0], span)


def test_the_dry_traversal_answers_the_prefix_then_raises_the_held_failure() -> None:
    steps = _three()
    failure = _Refused()
    preparer = _FailingPreparer(WALLET, steps[2], failure)
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    traversal = stream_physical(
        tuple(steps), preparer, WALLET, POSTGRES, effect_spans=(EffectSpan(0, 3, shape),)
    )
    assert arrays(next(traversal))[0] == (INT64, [1, 2])
    with pytest.raises(_Refused):
        next(traversal)


def test_a_grouped_effect_refuses_a_dialect_binding_no_arrays() -> None:
    preparer = LayoutPayloadPreparer(WALLET)
    step = update(WALLET, "Wallet", 1, {"balance": Decimal(1)})
    shape = preparer.effect_shape(step)
    assert shape is not None
    slots = preparer.effect_slots(step.entity, shape)
    arrayless = dataclasses.replace(POSTGRES, binds_arrays=False)
    with pytest.raises(SqlGenError, match="binds no arrays"):
        GroupedEffectBuilder(slots, WALLET, arrayless)


def test_a_grouped_effect_refuses_an_effect_its_shape_does_not_place() -> None:
    preparer = LayoutPayloadPreparer(WALLET)
    balance = update(WALLET, "Wallet", 1, {"balance": Decimal(1)})
    owner = update(WALLET, "Wallet", 2, {"owner": "Bo", "balance": Decimal(2)})
    shape = preparer.effect_shape(balance)
    assert shape is not None
    builder = GroupedEffectBuilder(preparer.effect_slots(balance.entity, shape), WALLET, POSTGRES)
    builder.append(balance, preparer.assignments(balance.entity, balance.assignments))
    with pytest.raises(SqlGenError, match="does not place"):
        builder.append(owner, preparer.assignments(owner.entity, owner.assignments))
    deletion = PlannedDelete(
        entity=balance.entity,
        target=balance.target,
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )
    with pytest.raises(SqlGenError, match="holds updates of its own Entity"):
        builder.append(deletion, None)
    assert arrays(builder.finish())[0] == (INT64, [1])


def test_effect_slots_answer_only_a_shape_of_their_own_entity() -> None:
    preparer = LayoutPayloadPreparer(PAYMENT)
    with pytest.raises(WritePlanningError, match="Effect Slots of its own Entity"):
        preparer.effect_slots(entity_identity(PAYMENT, "CardPayment"), "not a shape")


def test_a_grouped_effect_opens_only_at_its_own_span() -> None:
    preparer = LayoutPayloadPreparer(WALLET)
    steps = _three()
    shape = preparer.effect_shape(steps[0])
    assert shape is not None
    cursor = LoweringCursor(tuple(steps), preparer, WALLET, POSTGRES)
    first = cursor.take()
    assert first is not None
    with pytest.raises(SqlGenError, match="opens at its own span"):
        cursor.lowered_grouped_effect(first, EffectSpan(0, 3, shape))
