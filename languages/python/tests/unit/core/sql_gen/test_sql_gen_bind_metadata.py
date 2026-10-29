from __future__ import annotations

import dataclasses
import datetime as dt
import math
from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from parallax.core import deep_fetch, inheritance, storage_layout
from parallax.core import predicate as oa
from parallax.core.base import (
    DATE,
    FLOAT32,
    INFINITY,
    INFINITY_LITERAL,
    INT64,
    STRING,
    TIMESTAMP,
    ManagedValue,
)
from parallax.core.base import Decimal as DecimalType
from parallax.core.db_port import ArrayBind, JsonDocument
from parallax.core.deep_fetch import PlannedEntityQuery, ResolvedReadProjection
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.predicate._execution_values import ExecutionValueSource
from parallax.core.predicate._resolved import ResolvedAnd, ResolvedConstant, ResolvedMembership
from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen._compile import CompiledTemplate, compile_read
from parallax.core.sql_gen._context import (
    EXPANDING_PLACEHOLDER,
    PAGE_CAP,
    AffixForm,
    ComparisonTextForm,
    ContinuationCarrierForm,
    ExecutionValueForm,
    ExecutionValuePositions,
    GatheredKeysForm,
    LoweredStatement,
    ManagedOperandForm,
    MembershipForm,
    SqlGenError,
    StatementBuilder,
    _ExecutionValueMarker,  # pyright: ignore[reportPrivateUsage]
    _RepeatedTypedBindSpan,  # pyright: ignore[reportPrivateUsage]
    _TypedBindSlot,  # pyright: ignore[reportPrivateUsage]
    _TypedBindSpan,  # pyright: ignore[reportPrivateUsage]
    _WireBindOverride,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.sql_gen._inheritance import TpcsUnionReadPlan, plan_read_shape
from parallax.core.sql_gen._planning import (
    EvaluationContext,
    OwnerResultsRef,
    SharedSourceRef,
    StatementPlan,
    plan_statement,
)
from parallax.core.sql_gen._predicate import EntityRowScope, render_shared_sources
from parallax.core.unit_work import KeyedWriteInstruction
from parallax.core.wire import loads
from tests._support.lowering_probes import lower_instruction
from tests._support.sql import read_position, resolved_as_stated
from tests.unit._corpus_model_support import model as corpus_model

WALLET = corpus_model("wallet")


def _builder() -> StatementBuilder:
    return StatementBuilder(
        WALLET,
        inheritance.view(WALLET),
        storage_layout.view(WALLET),
        POSTGRES,
    )


def _template(statement: LoweredStatement) -> CompiledTemplate:
    entity = WALLET.entities[0]
    compiled = compile_read(
        deep_fetch.PlannedEntityQuery(
            target=entity.identity,
            entity=entity,
            position=read_position(WALLET, entity),
            predicate=resolved_as_stated(ResolvedConstant(True), WALLET, entity),
            projection=deep_fetch.ResolvedReadProjection((), False),
        ),
        WALLET,
        POSTGRES,
    )
    return sql_compile._template(  # pyright: ignore[reportPrivateUsage]
        dataclasses.replace(compiled, statement=statement)
    )


def test_statement_builder_rejects_a_bind_that_bypassed_role_classification() -> None:
    builder = _builder()
    builder._binds.append(1)  # pyright: ignore[reportPrivateUsage] - malformed compiler-product probe

    with pytest.raises(SqlGenError, match="role-specific API"):
        builder.finish("select ?")


def test_entity_row_scope_reference_front_doors_resolve_direct_members() -> None:
    entity = WALLET.entities[0]
    view = storage_layout.view(WALLET).entity(entity.identity)
    assert view is not None
    builder: StatementBuilder[EntityRowScope] = StatementBuilder(
        WALLET, inheritance.view(WALLET), storage_layout.view(WALLET), POSTGRES
    )
    scope = EntityRowScope(builder, entity, view.layout)

    assert scope.column_of(f"{entity.identity.canonical}.id") == "t0.id"
    assert scope.subject_for(
        scope.entity_attribute(f"{entity.identity.canonical}.id")
    ).compared == ("t0.id")


COLLECTIONS = corpus_model("predicate-collections")
TRAVERSAL = corpus_model("predicate-traversal")


def _planned_read(family: Metamodel, entity: EntityMetadata) -> PlannedEntityQuery:
    return PlannedEntityQuery(
        target=entity.identity,
        entity=entity,
        position=read_position(family, entity),
        predicate=resolved_as_stated(ResolvedConstant(True), family, entity),
        projection=ResolvedReadProjection((), False),
    )


def _row_builder(family: Metamodel) -> StatementBuilder[EntityRowScope]:
    return StatementBuilder(family, inheritance.view(family), storage_layout.view(family), POSTGRES)


def _statement_plan(family: Metamodel, root: str, node: oa.PredicateNode) -> StatementPlan:
    entity = next(entity for entity in family.entities if entity.identity.name == root)
    facet, storage = inheritance.view(family), storage_layout.view(family)
    read = plan_read_shape(_planned_read(family, entity), facet, storage, False, None)
    return plan_statement(
        resolved_as_stated(oa.validate_predicate(entity, node, family), family, entity),
        evaluation_context=EvaluationContext.SHARING_ALLOWED,
        entity=entity,
        meta=family,
        facet=facet,
        storage=storage,
        read_shape=read,
    )


_OWNER_TAGGED = oa.And(
    operands=(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Basket.owner.name"), value="Ada"),
        oa.Quantifier(
            "any",
            "Basket.owner.tags",
            oa.StringMatch(op="startsWith", subject=oa.CURRENT_SCALAR_ELEMENT, value="n"),
        ),
    )
)


def _basket_row(builder: StatementBuilder[EntityRowScope]) -> EntityRowScope:
    basket = next(entity for entity in COLLECTIONS.entities if entity.identity.name == "Basket")
    view = storage_layout.view(COLLECTIONS).entity(basket.identity)
    assert view is not None
    return EntityRowScope(builder, basket, view.layout)


def test_rendered_sources_retain_their_actual_target_and_origin_rows() -> None:
    plan = _statement_plan(COLLECTIONS, "Basket", _OWNER_TAGGED)
    root = plan.root_scopes[None]
    builder = _row_builder(COLLECTIONS)
    row = _basket_row(builder)
    joins = render_shared_sources(plan, root, row)
    binding = builder.source_binding(SharedSourceRef(root, 0))
    assert binding.origin is row
    assert binding.target.alias == "t1"
    assert f"left join basket_owner {binding.target.alias} " in joins
    results = builder.owner_results_binding(OwnerResultsRef(root, 0))
    assert (results.alias, results.columns) == ("r0", ("q0",))
    builder.finish(joins)


def test_selecting_a_scope_plan_is_idempotent_but_one_builder_renders_one_plan() -> None:
    plan = _statement_plan(COLLECTIONS, "Basket", _OWNER_TAGGED)
    root = plan.root_scopes[None]
    builder = _row_builder(COLLECTIONS)
    builder.select_scope_plan(plan, root)
    builder.select_scope_plan(plan, root)
    other = _statement_plan(COLLECTIONS, "Basket", _OWNER_TAGGED)
    unselected = next(scope.scope_id for scope in other.lexical_scopes if scope.scope_id != root)
    for scope_id in (root, unselected):
        with pytest.raises(SqlGenError, match="one statement plan"):
            builder.select_scope_plan(other, scope_id)


def test_a_source_reference_never_addresses_an_owner_result_binding() -> None:
    plan = _statement_plan(COLLECTIONS, "Basket", _OWNER_TAGGED)
    root = plan.root_scopes[None]
    builder = _row_builder(COLLECTIONS)
    render_shared_sources(plan, root, _basket_row(builder))
    with pytest.raises(SqlGenError, match="owner_results reference addresses no source"):
        builder.source_binding(OwnerResultsRef(root, 0))  # pyright: ignore[reportArgumentType]
    with pytest.raises(SqlGenError, match="source reference addresses no owner_results"):
        builder.owner_results_binding(SharedSourceRef(root, 0))  # pyright: ignore[reportArgumentType]


def test_a_selected_plan_s_missing_bindings_fail_early_and_at_finish() -> None:
    plan = _statement_plan(COLLECTIONS, "Basket", _OWNER_TAGGED)
    root = plan.root_scopes[None]
    builder = _row_builder(COLLECTIONS)
    with pytest.raises(SqlGenError, match="no selected lexical plan"):
        builder.source_binding(SharedSourceRef(root, 0))
    builder.select_scope_plan(plan, root)
    with pytest.raises(SqlGenError, match="read before its join renders"):
        builder.source_binding(SharedSourceRef(root, 0))
    with pytest.raises(SqlGenError, match="shared source was never rendered"):
        builder.finish("")
    partial = _row_builder(COLLECTIONS)
    partial.select_scope_plan(plan, root)
    owner = _basket_row(partial)
    partial.record_source_binding(SharedSourceRef(root, 0), target=owner, origin=owner)
    with pytest.raises(SqlGenError, match="owner-results relation was never rendered"):
        partial.finish("")


def test_each_planned_entry_renders_once_per_statement() -> None:
    plan = _statement_plan(COLLECTIONS, "Basket", _OWNER_TAGGED)
    root = plan.root_scopes[None]
    builder = _row_builder(COLLECTIONS)
    builder.select_scope_plan(plan, root)
    with pytest.raises(SqlGenError, match="read before their relation renders"):
        builder.owner_results_binding(OwnerResultsRef(root, 0))
    row = _basket_row(builder)
    builder.record_source_binding(SharedSourceRef(root, 0), target=row, origin=row)
    with pytest.raises(SqlGenError, match="renders once per statement"):
        builder.record_source_binding(SharedSourceRef(root, 0), target=row, origin=row)
    builder.record_owner_results_binding(OwnerResultsRef(root, 0), alias="r0", columns=("q0",))
    with pytest.raises(SqlGenError, match="renders once per statement"):
        builder.record_owner_results_binding(OwnerResultsRef(root, 0), alias="r1", columns=("q0",))
    builder.finish("")


def test_each_union_branch_builder_finishes_its_own_root_alone() -> None:
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Vehicle.dealer.name"), value="x")
    plan = _statement_plan(TRAVERSAL, "Vehicle", op)
    vehicle = next(entity for entity in TRAVERSAL.entities if entity.identity.name == "Vehicle")
    facet, storage = inheritance.view(TRAVERSAL), storage_layout.view(TRAVERSAL)
    read = plan_read_shape(_planned_read(TRAVERSAL, vehicle), facet, storage, False, None)
    assert isinstance(read, TpcsUnionReadPlan)
    assert list(plan.root_scopes) == [branch.identity for branch in read.branches]
    union = _row_builder(TRAVERSAL)
    for branch in read.branches:
        builder = _row_builder(TRAVERSAL)
        layout = storage.entity(branch.identity)
        assert layout is not None
        row = EntityRowScope(builder, vehicle, layout.layout)
        joins = render_shared_sources(plan, plan.root_scopes[branch.identity], row)
        builder.bind_managed(7, INT64)
        union.append_fragment(builder.finish(f"select 1 {joins} where ?"))
    assert union.finish("").binds == (7, 7)


def test_statement_metadata_preserves_ranges_gaps_forms_offsets_and_overrides() -> None:
    decimal_type = DecimalType(8, 2)
    statement = _builder()
    statement.bind_managed(Decimal("1.20"), decimal_type)
    statement.bind_managed(Decimal("2.30"), decimal_type)
    statement.bind_framework("framework")
    statement.bind_comparison_text("alpha", STRING)

    fragment = _builder()
    fragment.bind_managed(dt.date(2024, 1, 2), DATE)
    fragment.bind_framework("driver-infinity", wire_value="infinity")
    statement.append_fragment(fragment.finish(""))

    lowered = statement.finish("select ?, ?, ?, ?, ?, ?")
    spans = lowered.typed_bind_spans
    assert [
        (span.start, span.stop, span.neutral_type, span.form)
        for span in spans
        if isinstance(span, _TypedBindSpan)
    ] == [
        (0, 2, decimal_type, "MANAGED"),
        (3, 4, STRING, "COMPARISON_TEXT"),
        (4, 5, DATE, "MANAGED"),
    ]
    assert [(override.index, override.value) for override in lowered.wire_bind_overrides] == [
        (5, "infinity")
    ]
    assert lowered.wire_binds() == (
        "1.20",
        "2.30",
        "framework",
        "alpha",
        "2024-01-02",
        "infinity",
    )
    assert lowered.binds == (
        Decimal("1.20"),
        Decimal("2.30"),
        "framework",
        "alpha",
        dt.date(2024, 1, 2),
        "driver-infinity",
    )
    assert isinstance(lowered.binds[0], Decimal)
    assert isinstance(lowered.binds[4], dt.date)


def test_an_array_bind_projects_each_element_under_its_own_element_type() -> None:
    builder = _builder()
    instant = dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.UTC)
    array = ArrayBind(TIMESTAMP, [instant, INFINITY, None])
    builder.bind_concrete(array, MembershipForm(TIMESTAMP, False, True))
    builder.bind_managed(7, INT64)

    statement = builder.finish("select ?, ?")

    assert statement.binds == (array, 7)
    assert statement.typed_bind_spans == (_TypedBindSpan(1, 2, INT64, "MANAGED"),)
    assert statement.wire_bind_overrides == ()
    assert statement.wire_binds() == (["2024-01-02T03:04:05.000000Z", INFINITY_LITERAL, None], 7)


def test_comparison_text_projection_retains_the_owned_text_without_codec_work() -> None:
    builder = _builder()
    builder.bind_comparison_text("12.340", DecimalType(8, 2))
    assert builder.finish("select ?").wire_binds() == ("12.340",)


def test_framework_bind_can_report_an_explicit_wire_null() -> None:
    builder = _builder()
    builder.bind_framework("null", wire_value=None)

    statement = builder.finish("select ?")

    assert statement.binds == ("null",)
    assert statement.wire_binds() == (None,)
    assert statement.wire_bind_overrides == (_WireBindOverride(0, None),)


@pytest.mark.parametrize("postgres_array", [False, True], ids=["mariadb", "postgres"])
def test_multiple_key_occurrences_transform_surrounding_metadata_once(
    postgres_array: bool,
) -> None:
    builder = _builder()
    keys_form = GatheredKeysForm(INT64, postgres_array)
    builder.bind_framework("leading-driver", wire_value="leading-wire")
    builder.bind_managed(100, INT64)
    builder.bind_deferred(("keys",), keys_form)
    builder.bind_managed(200, INT64)
    builder.bind_framework("middle-driver", wire_value=None)
    builder.bind_deferred(("keys",), keys_form)
    builder.bind_deferred(("keys",), keys_form)
    builder.bind_comparison_text("tail", STRING)
    builder.bind_framework("trailing-driver", wire_value="trailing-wire")
    builder.bind_managed_rows((("a",), ("b",)), ((STRING, "MANAGED"),))
    member = "any(?)" if postgres_array else f"({EXPANDING_PLACEHOLDER})"
    statement = builder.finish(f"select ?, ?, {member}, ?, ?, {member}, {member}, ?, ?, ?, ?")
    template = _template(statement)
    indexes = (2, 5, 6)
    keys: list[ManagedValue] = [10, 20, 30]
    rendered = template.render(keys).statement
    array = ArrayBind(INT64, cast("list[object]", keys))
    values: tuple[object, ...] = (array,) if postgres_array else tuple(keys)
    wire: tuple[object, ...] = ([10, 20, 30],) if postgres_array else tuple(keys)
    assert rendered.binds == (
        "leading-driver",
        100,
        *values,
        200,
        "middle-driver",
        *values,
        *values,
        "tail",
        "trailing-driver",
        "a",
        "b",
    )
    assert rendered.wire_binds() == (
        "leading-wire",
        100,
        *wire,
        200,
        None,
        *wire,
        *wire,
        "tail",
        "trailing-wire",
        "a",
        "b",
    )
    assert rendered.is_compiler_proven
    if postgres_array:
        assert rendered.sql == statement.sql
        assert rendered.typed_bind_spans is statement.typed_bind_spans
        assert rendered.wire_bind_overrides is statement.wire_bind_overrides
        assert all(cast("ArrayBind", rendered.binds[index]).values is keys for index in indexes)
    else:
        assert rendered.sql == "select ?, ?, (?, ?, ?), ?, ?, (?, ?, ?), (?, ?, ?), ?, ?, ?, ?"
        assert rendered.typed_bind_spans == (
            _TypedBindSpan(1, 6, INT64, "MANAGED"),
            _TypedBindSpan(7, 13, INT64, "MANAGED"),
            _TypedBindSpan(13, 14, STRING, "COMPARISON_TEXT"),
            _RepeatedTypedBindSpan(15, 1, 1, 2, STRING, "MANAGED"),
        )
        assert rendered.wire_bind_overrides == (
            _WireBindOverride(0, "leading-wire"),
            _WireBindOverride(6, None),
            _WireBindOverride(14, "trailing-wire"),
        )
    assert keys == [10, 20, 30]
    (group,) = statement.execution_value_positions()
    assert (group.source, group.form, group.indices) == (("keys",), keys_form, indexes)
    again = template.render([40]).statement
    assert again.typed_bind_spans is statement.typed_bind_spans
    assert again.wire_bind_overrides is statement.wire_bind_overrides
    assert rendered.binds != again.binds


_CARRIER = ContinuationCarrierForm(INT64, "MANAGED")
_TEXT_CARRIER = ContinuationCarrierForm(STRING, "COMPARISON_TEXT")


def test_groups_follow_canonical_source_order_and_substitute_in_any_stream_order() -> None:
    builder = _builder()
    builder.bind_deferred(("limit",), PAGE_CAP)
    builder.bind_deferred(("paging", 1), _TEXT_CARRIER)
    builder.bind_managed(7, INT64)
    builder.bind_deferred(("paging", 0), _CARRIER)
    builder.bind_deferred(("keys",), GatheredKeysForm(INT64, False))
    builder.bind_deferred(("paging", 1), _TEXT_CARRIER)
    builder.bind_deferred(("paging", 0), _CARRIER)
    statement = builder.finish(f"select ?, ?, ?, ?, ({EXPANDING_PLACEHOLDER}), ?, ?")

    groups = statement.execution_value_positions()

    assert [(group.source, group.indices) for group in groups] == [
        (("paging", 0), (3, 6)),
        (("paging", 1), (1, 5)),
        (("limit",), (0,)),
        (("keys",), (4,)),
    ]
    values: dict[object, object] = {
        ("paging", 0): 42,
        ("paging", 1): "b",
        ("limit",): 3,
        ("keys",): [8, 9],
    }
    streams = (groups, tuple(reversed(groups)))
    rendered = [
        statement.with_execution_values(
            ((group, values[group.source]) for group in stream), sql="rendered"
        )
        for stream in streams
    ]
    assert rendered[0] == rendered[1]
    assert rendered[0].binds == (3, "b", 7, 42, 8, 9, "b", 42)
    assert rendered[0].typed_bind_spans == (
        _TypedBindSpan(1, 2, STRING, "COMPARISON_TEXT"),
        _TypedBindSpan(2, 6, INT64, "MANAGED"),
        _TypedBindSpan(6, 7, STRING, "COMPARISON_TEXT"),
        _TypedBindSpan(7, 8, INT64, "MANAGED"),
    )
    assert rendered[0].wire_binds() == (3, "b", 7, 42, 8, 9, "b", 42)


def test_expanding_groups_of_different_widths_move_the_metadata_after_each() -> None:
    builder = _builder()
    first = MembershipForm(INT64, False, False)
    second = MembershipForm(STRING, True, False)
    builder.bind_managed(7, INT64)
    builder.bind_deferred(("predicate", 0), first)
    builder.bind_framework(INFINITY)
    builder.bind_deferred(("predicate", 1), second)
    builder.bind_deferred(("predicate", 0), first)
    builder.bind_managed(8, INT64)
    builder.bind_framework(INFINITY)
    statement = builder.finish(
        f"?, ({EXPANDING_PLACEHOLDER}), ?, ({EXPANDING_PLACEHOLDER}), "
        f"({EXPANDING_PLACEHOLDER}), ?, ?"
    )
    template = _template(statement)
    groups = template._positions  # pyright: ignore[reportPrivateUsage]
    assert [(group.source, group.indices) for group in groups] == [
        (("predicate", 0), (1, 4)),
        (("predicate", 1), (3,)),
    ]
    assert template._placeholders == (0, 1, 0)  # pyright: ignore[reportPrivateUsage]

    values: dict[ExecutionValueSource, list[object]] = {
        ("predicate", 0): [1, 2, 3],
        ("predicate", 1): ["a", "b"],
    }
    for stream in (groups, tuple(reversed(groups))):
        rendered = statement.with_execution_values(
            ((group, values[group.source]) for group in stream), sql="rendered"
        )
        assert rendered.binds == (7, 1, 2, 3, INFINITY, "a", "b", 1, 2, 3, 8, INFINITY)
        assert rendered.typed_bind_spans == (
            _TypedBindSpan(0, 4, INT64, "MANAGED"),
            _TypedBindSpan(5, 7, STRING, "COMPARISON_TEXT"),
            _TypedBindSpan(7, 11, INT64, "MANAGED"),
        )
        assert [override.index for override in rendered.wire_bind_overrides] == [4, 11]
        assert rendered.wire_binds() == (
            7, 1, 2, 3, INFINITY_LITERAL, "a", "b", 1, 2, 3, 8, INFINITY_LITERAL,
        )  # fmt: skip

    widths_of_one = statement.with_execution_values(
        ((group, values[group.source][:1]) for group in groups), sql="rendered"
    )
    assert widths_of_one.typed_bind_spans is statement.typed_bind_spans
    assert widths_of_one.wire_bind_overrides is statement.wire_bind_overrides


def test_a_template_fills_each_expanding_placeholder_from_its_own_group() -> None:
    builder = _builder()
    builder.bind_deferred(("predicate", 1), MembershipForm(INT64, False, False))
    builder.bind_deferred(("predicate", 0), MembershipForm(INT64, False, False))
    statement = builder.finish(f"a in ({EXPANDING_PLACEHOLDER}) and b in ({EXPANDING_PLACEHOLDER})")
    member = WALLET.entities[0].declared_attributes[0]
    predicate = ResolvedAnd(
        (ResolvedMembership("in", member, (5,)), ResolvedMembership("in", member, (1, 2, 3)))
    )
    query = cast("ResolvedObjectQuery", SimpleNamespace(predicate=predicate))

    rendered = _template(statement).render(query=query).statement

    assert rendered.sql == "a in (?, ?, ?) and b in (?)"
    assert rendered.binds == (1, 2, 3, 5)


def test_a_marker_fills_repeated_row_metadata_unless_it_expands() -> None:
    carrier = _ExecutionValueMarker(("paging", 0), ContinuationCarrierForm(STRING, "MANAGED"))
    statement = LoweredStatement(
        "",
        (carrier, "a", carrier, "b"),
        (_RepeatedTypedBindSpan(0, 2, 2, 2, STRING, "MANAGED"),),
    )
    (group,) = statement.execution_value_positions()
    rendered = statement.with_execution_values(((group, "z"),), sql="")
    assert rendered.binds == ("z", "a", "z", "b")
    assert rendered.typed_bind_spans is statement.typed_bind_spans

    keys = _ExecutionValueMarker(("keys",), GatheredKeysForm(STRING, False))
    expanding = LoweredStatement(
        "",
        (keys, "a"),
        (_RepeatedTypedBindSpan(0, 1, 1, 2, STRING, "MANAGED"),),
    )
    with pytest.raises(SqlGenError, match="repeated row-bind metadata"):
        _template(expanding)


def _untyped(builder: StatementBuilder) -> None:
    builder.bind_structural(_ExecutionValueMarker(("paging", 0), _CARRIER))


def _typed_structure(builder: StatementBuilder) -> None:
    builder.bind_managed(_ExecutionValueMarker(("limit",), PAGE_CAP), INT64)


def _other_type(builder: StatementBuilder) -> None:
    builder.bind_managed(_ExecutionValueMarker(("paging", 0), _CARRIER), STRING)


def _overridden(builder: StatementBuilder) -> None:
    builder.bind_framework(_ExecutionValueMarker(("limit",), PAGE_CAP), wire_value=1)


def _managed_as_text(builder: StatementBuilder) -> None:
    builder.bind_comparison_text(
        _ExecutionValueMarker(("predicate", 0), ManagedOperandForm(DATE)), DATE
    )


def _text_as_managed(builder: StatementBuilder) -> None:
    builder.bind_managed(_ExecutionValueMarker(("predicate", 0), ComparisonTextForm(DATE)), DATE)


def _affix_as_managed(builder: StatementBuilder) -> None:
    builder.bind_managed(
        _ExecutionValueMarker(("predicate", 0), AffixForm("contains", False)), STRING
    )


@pytest.mark.parametrize(
    "bind",
    [
        _untyped,
        _typed_structure,
        _other_type,
        _overridden,
        _managed_as_text,
        _text_as_managed,
        _affix_as_managed,
    ],
    ids=[
        "untyped",
        "typed-structure",
        "other-type",
        "overridden",
        "managed-as-text",
        "text-as-managed",
        "affix-as-managed",
    ],
)
def test_discovery_refuses_a_marker_bound_outside_its_form(
    bind: Callable[[StatementBuilder], None],
) -> None:
    builder = _builder()
    bind(builder)
    with pytest.raises(SqlGenError, match="classification its form selects"):
        builder.finish("select ?").execution_value_positions()


def test_discovery_keeps_two_forms_of_one_authored_operand_adjacent_in_source_order() -> None:
    builder = _builder()
    managed = ManagedOperandForm(DATE)
    text = ComparisonTextForm(DATE)
    builder.bind_deferred(("predicate", 1), managed)
    builder.bind_deferred(("predicate", 0), AffixForm("startsWith", True))
    builder.bind_deferred(("predicate", 1), text)
    builder.bind_deferred(("predicate", 1), managed)

    positions = builder.finish("select ?, ?, ?, ?").execution_value_positions()

    assert [(group.source, group.form, group.indices) for group in positions] == [
        (("predicate", 0), AffixForm("startsWith", True), (1,)),
        (("predicate", 1), managed, (0, 3)),
        (("predicate", 1), text, (2,)),
    ]


def test_discovery_refuses_gathered_keys_in_two_forms() -> None:
    builder = _builder()
    builder.bind_deferred(("keys",), GatheredKeysForm(INT64, True))
    builder.bind_deferred(("keys",), GatheredKeysForm(STRING, True))
    with pytest.raises(SqlGenError, match="exactly one bind form"):
        builder.finish("select ?, ?").execution_value_positions()


def test_a_template_refuses_placeholders_that_disagree_with_its_key_positions() -> None:
    builder = _builder()
    builder.bind_deferred(("keys",), GatheredKeysForm(INT64, False))
    with pytest.raises(SqlGenError, match="disagree with its positions"):
        _template(builder.finish("select ?"))
    with pytest.raises(SqlGenError, match="disagree with its positions"):
        _template(_builder().finish(f"select {EXPANDING_PLACEHOLDER}"))


def test_substitution_refuses_an_empty_expansion() -> None:
    builder = _builder()
    builder.bind_deferred(("keys",), GatheredKeysForm(INT64, False))
    statement = builder.finish("select ?")
    (group,) = statement.execution_value_positions()
    with pytest.raises(SqlGenError, match="at least one element"):
        statement.with_execution_values(((group, []),), sql="select")


def test_a_statement_without_markers_retains_no_positions() -> None:
    builder = _builder()
    builder.bind_managed(1, INT64)
    statement = builder.finish("select ?")
    template = _template(statement)
    assert statement.execution_value_positions() == ()
    assert template.render() is template.compiled


@pytest.mark.parametrize(
    ("source", "form"),
    [
        (("keys",), GatheredKeysForm(FLOAT32, False)),
        (("keys",), GatheredKeysForm(FLOAT32, True)),
        (("limit",), PAGE_CAP),
        (("paging", 0), _CARRIER),
    ],
    ids=["keys", "key-array", "page-cap", "carrier"],
)
def test_an_unrendered_marker_has_no_wire_projection(
    source: ExecutionValueSource, form: ExecutionValueForm
) -> None:
    builder = _builder()
    builder.bind_deferred(source, form)

    with pytest.raises(SqlGenError, match="until its template renders"):
        builder.finish("select ?").wire_binds()


def test_positions_name_their_marker_s_source_and_form() -> None:
    marker = _ExecutionValueMarker(("limit",), PAGE_CAP)
    positions = ExecutionValuePositions(marker, (0, 2))
    assert (positions.source, positions.form) == (("limit",), PAGE_CAP)


def test_multirow_write_uses_one_repeated_descriptor_per_typed_row_run() -> None:
    statement = lower_instruction(
        KeyedWriteInstruction(
            "insert",
            "Wallet",
            (
                {"id": 1, "owner": "A", "balance": Decimal("10.00")},
                {"id": 2, "owner": "B", "balance": Decimal("20.00")},
                {"id": 3, "owner": "C", "balance": Decimal("30.00")},
            ),
        ),
        WALLET,
        POSTGRES,
        "locking",
    )[0]

    spans = statement.typed_bind_spans
    assert len(spans) == 3
    assert [
        (span.start, span.width, span.stride, span.repetitions, span.form)
        for span in spans
        if isinstance(span, _RepeatedTypedBindSpan)
    ] == [
        (0, 1, 3, 3, "MANAGED"),
        (1, 1, 3, 3, "MANAGED"),
        (2, 1, 3, 3, "MANAGED"),
    ]
    assert statement.wire_binds() == (
        1,
        "A",
        "10.00",
        2,
        "B",
        "20.00",
        3,
        "C",
        "30.00",
    )


def test_same_type_bind_growth_retains_one_descriptor() -> None:
    bind_count = 4_096
    builder = _builder()
    for _ in range(bind_count):
        builder.bind_managed("value", STRING)

    statement = builder.finish("")

    assert statement.typed_bind_spans == (_TypedBindSpan(0, bind_count, STRING, "MANAGED"),)


def test_heterogeneous_row_growth_retains_one_descriptor_per_column() -> None:
    row_count = 4_096
    builder = _builder()
    builder.bind_managed_rows(
        (("managed", "comparison"),) * row_count,
        ((STRING, "MANAGED"), (STRING, "COMPARISON_TEXT")),
    )

    statement = builder.finish("")

    assert statement.typed_bind_spans == (
        _RepeatedTypedBindSpan(0, 1, 2, row_count, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(1, 1, 2, row_count, STRING, "COMPARISON_TEXT"),
    )


def test_repeated_typed_rows_leave_nullable_none_positions_unannotated() -> None:
    builder = _builder()
    builder.bind_managed_rows(
        (("a", None, "c"), ("d", None, "f"), ("g", "h", "i"), ("j", "k", "l")),
        ((STRING, "MANAGED"), (STRING, "MANAGED"), (STRING, "MANAGED")),
    )

    statement = builder.finish("values (?, ?, ?), (?, ?, ?), (?, ?, ?), (?, ?, ?)")
    repeated = [
        span for span in statement.typed_bind_spans if isinstance(span, _RepeatedTypedBindSpan)
    ]
    assert [(span.start, span.width, span.stride, span.repetitions) for span in repeated] == [
        (0, 1, 3, 2),
        (2, 1, 3, 2),
        (6, 3, 3, 2),
    ]
    assert 1 not in {index for span in statement.typed_bind_spans for index in span.indexes()}
    assert 4 not in {index for span in statement.typed_bind_spans for index in span.indexes()}


def test_append_fragment_coalesces_touching_ordinary_spans_with_equal_type_and_form() -> None:
    statement = _builder()
    statement.bind_managed("a", STRING)
    fragment = _builder()
    fragment.bind_managed("b", STRING)

    statement.append_fragment(fragment.finish(""))

    assert statement.finish("select ?, ?").typed_bind_spans == (
        _TypedBindSpan(0, 2, STRING, "MANAGED"),
    )


def test_repeated_managed_rows_retain_each_slots_form() -> None:
    builder = _builder()
    builder.bind_managed_rows(
        (("a", "b"), ("c", "d")),
        ((STRING, "MANAGED"), (STRING, "COMPARISON_TEXT")),
    )
    statement = builder.finish("values (?, ?), (?, ?)")
    assert [
        (span.start, span.width, span.stride, span.repetitions, span.form)
        for span in statement.typed_bind_spans
        if isinstance(span, _RepeatedTypedBindSpan)
    ] == [
        (0, 1, 2, 2, "MANAGED"),
        (1, 1, 2, 2, "COMPARISON_TEXT"),
    ]


def test_a_managed_row_binds_the_cells_its_write_admitted_without_judging_them() -> None:
    # Each cell crossed its write's admission, so its slot spans it whatever it
    # holds; only null and the open bound bind outside the span.
    builder = _builder()
    builder.bind_managed_rows((("not-a-date",), ("still-not-a-date",)), ((DATE, "MANAGED"),))

    statement = builder.finish("values (?), (?)")

    assert statement.binds == ("not-a-date", "still-not-a-date")
    assert statement.typed_bind_spans == (_RepeatedTypedBindSpan(0, 1, 1, 2, DATE, "MANAGED"),)


@pytest.mark.parametrize(
    "value",
    [
        math.inf,
        pytest.param(10**5000, id="oversized-int"),
        "\ud800",
        loads("1e9999"),
        [math.inf],
        {"nested": "\ud800"},
    ],
)
def test_untyped_bind_projection_rejects_invalid_wire_scalars(value: object) -> None:
    builder = _builder()
    builder.bind_structural(value)
    with pytest.raises(SqlGenError, match="not an ordinary Wire value"):
        builder.finish("select ?").wire_binds()


@pytest.mark.parametrize(
    "span",
    [
        _TypedBindSpan(-1, 1, STRING, "MANAGED"),
        _TypedBindSpan(0, 0, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(0, 0, 1, 1, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(0, 1, 0, 1, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(0, 2, 1, 1, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(0, 1, 1, 0, STRING, "MANAGED"),
    ],
)
def test_finish_rejects_invalid_typed_descriptor_dimensions(
    span: _TypedBindSpan | _RepeatedTypedBindSpan,
) -> None:
    fragment = LoweredStatement(
        "",
        ("a", "b"),
        (span,),
        (),
        True,
    )
    builder = _builder()
    builder.append_fragment(fragment)
    with pytest.raises(SqlGenError, match="invalid dimensions or stride"):
        builder.finish("select ?, ?")


def test_managed_row_binding_handles_empty_single_and_changing_patterns() -> None:
    empty = _builder()
    empty.bind_managed_rows((), ((STRING, "MANAGED"),))
    assert empty.finish("").binds == ()

    single = _builder()
    single.bind_managed_rows((("one",),), ((STRING, "MANAGED"),))
    assert single.finish("select ?").wire_binds() == ("one",)

    changing = _builder()
    changing.bind_managed_rows(
        (("one", INFINITY), (None, INFINITY)),
        ((STRING, "MANAGED"), None),
    )
    lowered = changing.finish("values (?, ?), (?, ?)")
    assert lowered.wire_binds() == ("one", "infinity", None, "infinity")
    assert lowered.typed_bind_spans == (_TypedBindSpan(0, 1, STRING, "MANAGED"),)


def test_managed_infinity_binds_outside_typed_spans_and_observes_its_canonical_literal() -> None:
    builder = _builder()
    builder.bind_framework(INFINITY)
    builder.bind_framework(INFINITY, wire_value="explicit")
    builder.bind_framework("infinity")
    builder.bind_framework(7)
    builder.bind_managed_rows(((INFINITY,),), ((TIMESTAMP, "MANAGED"),))
    builder.bind_managed_rows(((INFINITY,), (INFINITY,)), ((TIMESTAMP, "MANAGED"),))

    lowered = builder.finish("select ?, ?, ?, ?, ?, ?, ?")

    assert lowered.binds == (INFINITY, INFINITY, "infinity", 7, INFINITY, INFINITY, INFINITY)
    assert lowered.typed_bind_spans == ()
    assert lowered.wire_bind_overrides == (
        _WireBindOverride(0, "infinity"),
        _WireBindOverride(1, "explicit"),
        _WireBindOverride(4, "infinity"),
        _WireBindOverride(5, "infinity"),
        _WireBindOverride(6, "infinity"),
    )
    assert lowered.wire_binds() == (
        "infinity",
        "explicit",
        "infinity",
        7,
        "infinity",
        "infinity",
        "infinity",
    )


def test_managed_row_binding_rejects_inconsistent_widths() -> None:
    with pytest.raises(SqlGenError, match="inconsistent row widths"):
        _builder().bind_managed_rows((("one",), ("two", "extra")), ((STRING, "MANAGED"),))


_MIXED_ROW: tuple[_TypedBindSlot | None, ...] = (
    (INT64, "MANAGED"),
    None,
    (TIMESTAMP, "MANAGED"),
    (DATE, "MANAGED"),
)


def _mixed_row(key: int, day: object) -> tuple[object, ...]:
    return (key, JsonDocument({"key": key}), INFINITY, day)


def test_a_refused_managed_row_binds_nothing_after_valid_scalar_document_and_open_cells() -> None:
    prefix = _builder()
    refused = _builder()
    for builder in (prefix, refused):
        builder.bind_managed_row(_mixed_row(1, dt.date(2024, 1, 1)), _MIXED_ROW)
        builder.bind_managed_row(_mixed_row(2, dt.date(2024, 1, 2)), _MIXED_ROW)

    with pytest.raises(SqlGenError, match="inconsistent row widths"):
        refused.bind_managed_row(_mixed_row(4, dt.date(2024, 1, 4))[:-1], _MIXED_ROW)

    expected = prefix.finish("values (?, ?, ?, ?), (?, ?, ?, ?)")
    actual = refused.finish("values (?, ?, ?, ?), (?, ?, ?, ?)")
    assert actual == expected
    assert actual.typed_bind_spans == (
        _RepeatedTypedBindSpan(0, 1, 4, 2, INT64, "MANAGED"),
        _RepeatedTypedBindSpan(3, 1, 4, 2, DATE, "MANAGED"),
    )
    assert actual.wire_bind_overrides == (
        _WireBindOverride(2, "infinity"),
        _WireBindOverride(6, "infinity"),
    )


def test_each_signature_change_seals_the_group_of_rows_before_it() -> None:
    # A nullable cell bound as None has no typed span, so the row holding it
    # starts its own group, and the next full row starts another.
    builder = _builder()
    pattern: tuple[_TypedBindSlot, ...] = ((STRING, "MANAGED"), (STRING, "MANAGED"))
    for row in (("a", "b"), ("c", "d"), (None, "e"), ("f", "g"), ("h", "i")):
        builder.bind_managed_row(row, pattern)

    statement = builder.finish("")

    assert statement.typed_bind_spans == (
        _RepeatedTypedBindSpan(0, 2, 2, 2, STRING, "MANAGED"),
        _TypedBindSpan(5, 6, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(6, 2, 2, 2, STRING, "MANAGED"),
    )


def test_an_open_row_run_seals_before_any_other_bind_or_fragment() -> None:
    builder = _builder()
    builder.bind_managed("lead", STRING)
    builder.bind_managed_row(("a", "b"), ((STRING, "MANAGED"), (STRING, "MANAGED")))
    builder.bind_framework(INFINITY)
    builder.bind_managed_row(("c",), ((STRING, "MANAGED"),))
    builder.bind_managed_row(("d",), ((STRING, "MANAGED"),))
    fragment = _builder()
    fragment.bind_managed("tail", STRING)
    builder.append_fragment(fragment.finish(""))
    builder.bind_managed_row(("e",), ((STRING, "MANAGED"),))

    statement = builder.finish("")

    assert statement.binds == ("lead", "a", "b", INFINITY, "c", "d", "tail", "e")
    assert statement.typed_bind_spans == (
        _TypedBindSpan(0, 3, STRING, "MANAGED"),
        _RepeatedTypedBindSpan(4, 1, 1, 2, STRING, "MANAGED"),
        _TypedBindSpan(6, 8, STRING, "MANAGED"),
    )
    assert statement.wire_bind_overrides == (_WireBindOverride(3, "infinity"),)


def test_wide_homogeneous_rows_share_one_repeated_descriptor() -> None:
    width, row_count = 256, 64
    builder = _builder()
    slot: _TypedBindSlot = (STRING, "MANAGED")
    pattern = (slot,) * width
    for _ in range(row_count):
        builder.bind_managed_row(("value",) * width, pattern)

    statement = builder.finish("")

    assert statement.typed_bind_spans == (
        _RepeatedTypedBindSpan(0, width, width, row_count, STRING, "MANAGED"),
    )


def test_wide_heterogeneous_rows_compact_each_slot_run_within_each_group() -> None:
    width = 64
    pattern: tuple[_TypedBindSlot, ...] = tuple(
        (INT64, "MANAGED") if offset % 2 == 0 else (STRING, "MANAGED") for offset in range(width)
    )
    full = tuple(offset if offset % 2 == 0 else str(offset) for offset in range(width))
    holed = tuple(None if offset == 5 else value for offset, value in enumerate(full))
    builder = _builder()
    for row in (full, full, full, holed, full, full):
        builder.bind_managed_row(row, pattern)

    spans = builder.finish("").typed_bind_spans

    leading, holed_spans, trailing = spans[:width], spans[width:-width], spans[-width:]
    assert leading == tuple(
        _RepeatedTypedBindSpan(offset, 1, width, 3, *pattern[offset]) for offset in range(width)
    )
    holed_start = 3 * width
    assert holed_spans == tuple(
        _TypedBindSpan(holed_start + offset, holed_start + offset + 1, *pattern[offset])
        for offset in range(width)
        if offset != 5
    )
    assert trailing == tuple(
        _RepeatedTypedBindSpan(4 * width + offset, 1, width, 2, *pattern[offset])
        for offset in range(width)
    )


def test_statement_builder_rejects_unproven_or_invalid_fragment_metadata() -> None:
    with pytest.raises(SqlGenError, match="compiler fragment"):
        _builder().append_fragment(LoweredStatement("", (), (), (), False))

    for spans, overrides, message in (
        ((_TypedBindSpan(1, 2, STRING, "MANAGED"),), (), "out of range"),
        (
            (
                _TypedBindSpan(0, 1, STRING, "MANAGED"),
                _TypedBindSpan(0, 1, STRING, "COMPARISON_TEXT"),
            ),
            (),
            "overlaps",
        ),
        ((), (_WireBindOverride(1, "wire"),), "override metadata"),
    ):
        builder = _builder()
        builder.append_fragment(LoweredStatement("", ("value",), spans, overrides, True))
        with pytest.raises(SqlGenError, match=message):
            builder.finish("select ?")
