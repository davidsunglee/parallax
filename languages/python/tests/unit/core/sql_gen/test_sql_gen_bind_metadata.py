from __future__ import annotations

import dataclasses
import datetime as dt
import math
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.core import deep_fetch, inheritance, storage_layout
from parallax.core import predicate as predicate_algebra
from parallax.core.base import DATE, FLOAT32, INFINITY, INT64, STRING, TIMESTAMP, ManagedValue
from parallax.core.base import Decimal as DecimalType
from parallax.core.dialect import POSTGRES
from parallax.core.predicate._validated import DeferredKeySet, ValidatedPredicate
from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen import _predicate as sql_predicate
from parallax.core.sql_gen._compile import CompiledTemplate, compile_read
from parallax.core.sql_gen._context import (
    LoweredStatement,
    SqlGenError,
    StatementBuilder,
    _RepeatedTypedBindSpan,  # pyright: ignore[reportPrivateUsage]
    _TypedBindSpan,  # pyright: ignore[reportPrivateUsage]
    _WireBindOverride,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.sql_gen._predicate import EntityScope
from parallax.core.unit_work import KeyedWrite
from parallax.core.wire import loads
from tests._support.lowering_probes import lower_instruction
from tests.unit._corpus_model_support import model as corpus_model

WALLET = corpus_model("wallet")


def _builder() -> StatementBuilder:
    return StatementBuilder(
        WALLET,
        inheritance.view(WALLET),
        storage_layout.view(WALLET),
        POSTGRES,
    )


def _template(statement: LoweredStatement, *, postgres_array: bool) -> CompiledTemplate:
    entity = WALLET.entities[0]
    compiled = compile_read(
        deep_fetch.ValidatedEntityQuery(
            target=entity.identity,
            entity=entity,
            validated_predicate=ValidatedPredicate(predicate_algebra.All()),
            projection=deep_fetch.ResolvedReadProjection((), False),
        ),
        WALLET,
        POSTGRES,
    )
    return sql_compile._template(  # pyright: ignore[reportPrivateUsage]
        dataclasses.replace(compiled, statement=statement), postgres_array=postgres_array
    )


def test_statement_builder_rejects_a_bind_that_bypassed_role_classification() -> None:
    builder = _builder()
    builder._binds.append(1)  # pyright: ignore[reportPrivateUsage] - malformed compiler-product probe

    with pytest.raises(SqlGenError, match="role-specific API"):
        builder.finish("select ?")


def test_entity_scope_reference_front_doors_resolve_direct_members() -> None:
    entity = WALLET.entities[0]
    view = storage_layout.view(WALLET).entity(entity.identity)
    assert view is not None
    scope = EntityScope(_builder(), entity, view.layout)

    assert scope.column_of(f"{entity.identity.canonical}.id") == "t0.id"
    assert scope.subject_for(
        scope.entity_attribute(f"{entity.identity.canonical}.id")
    ).compared == ("t0.id")


def test_nested_lowering_helpers_reject_the_wrong_validated_node_family() -> None:
    product = ValidatedPredicate(predicate_algebra.All())
    entity = WALLET.entities[0]
    view = storage_layout.view(WALLET).entity(entity.identity)
    assert view is not None
    scope = EntityScope(_builder(), entity, view.layout)

    with pytest.raises(AssertionError, match="wrong authored node"):
        sql_predicate._lower_nested(product, scope)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(AssertionError, match="wrong authored node"):
        sql_predicate._lower_element_nested(  # pyright: ignore[reportPrivateUsage]
            product, cast("Any", object())
        )


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
    marker = DeferredKeySet(INT64)
    builder.bind_framework("leading-driver", wire_value="leading-wire")
    builder.bind_managed(100, INT64)
    bind_keys = builder.bind_managed_array if postgres_array else builder.bind_managed
    bind_keys(marker, INT64)
    builder.bind_managed(200, INT64)
    builder.bind_framework("middle-driver", wire_value=None)
    bind_keys(marker, INT64)
    bind_keys(marker, INT64)
    builder.bind_comparison_text("tail", STRING)
    builder.bind_framework("trailing-driver", wire_value="trailing-wire")
    builder.bind_typed_rows((("a",), ("b",)), ((STRING, "MANAGED"),))
    member = "any(?)" if postgres_array else "(__parallax_deferred_keys__)"
    statement = builder.finish(f"select ?, ?, {member}, ?, ?, {member}, {member}, ?, ?, ?, ?")
    template = _template(statement, postgres_array=postgres_array)
    indexes = (2, 5, 6)
    keys: list[ManagedValue] = [10, 20, 30]
    rendered = template.render(keys).statement
    values: tuple[object, ...] = (keys,) if postgres_array else tuple(keys)
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
        *values,
        200,
        None,
        *values,
        *values,
        "tail",
        "trailing-wire",
        "a",
        "b",
    )
    assert rendered.is_compiler_proven
    if postgres_array:
        assert rendered.typed_bind_spans is statement.typed_bind_spans
        assert rendered.wire_bind_overrides is statement.wire_bind_overrides
        assert all(rendered.binds[index] is keys for index in indexes)
    else:
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
    assert statement.binds[2] is statement.binds[5] is statement.binds[6] is marker
    again = template.render([40]).statement
    assert again.typed_bind_spans is statement.typed_bind_spans
    assert again.wire_bind_overrides is statement.wire_bind_overrides
    assert rendered.binds != again.binds


def test_a_deferred_set_cannot_be_inserted_into_repeated_write_row_metadata() -> None:
    marker = DeferredKeySet(STRING)
    statement = LoweredStatement(
        "",
        (marker, "a"),
        (_RepeatedTypedBindSpan(0, 1, 1, 2, STRING, "MANAGED"),),
    )
    with pytest.raises(SqlGenError, match="repeated row-bind metadata"):
        _template(statement, postgres_array=False)


@pytest.mark.parametrize("form", ["MANAGED", "MANAGED_ARRAY"])
def test_an_unrendered_key_set_has_no_wire_projection(form: str) -> None:
    builder = _builder()
    if form == "MANAGED":
        builder.bind_managed(DeferredKeySet(FLOAT32), FLOAT32)
    else:
        builder.bind_managed_array(DeferredKeySet(FLOAT32), FLOAT32)

    with pytest.raises(SqlGenError, match="until its keys are rendered"):
        builder.finish("select ?").wire_binds()


def test_multirow_write_uses_one_repeated_descriptor_per_typed_row_run() -> None:
    statement = lower_instruction(
        KeyedWrite(
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
    builder.bind_typed_rows(
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
    builder.bind_typed_rows(
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


def test_repeated_typed_rows_retain_form_and_reject_mismatched_carriers() -> None:
    builder = _builder()
    builder.bind_typed_rows(
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

    with pytest.raises(SqlGenError, match="does not match MANAGED slot"):
        _builder().bind_typed_rows(
            (("not-a-date",), ("still-not-a-date",)),
            ((DATE, "MANAGED"),),
        )


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


def test_typed_row_binding_handles_empty_single_and_changing_patterns() -> None:
    empty = _builder()
    empty.bind_typed_rows((), ((STRING, "MANAGED"),))
    assert empty.finish("").binds == ()

    single = _builder()
    single.bind_typed_rows((("one",),), ((STRING, "MANAGED"),))
    assert single.finish("select ?").wire_binds() == ("one",)

    changing = _builder()
    changing.bind_typed_rows(
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
    builder.bind_typed_rows(((INFINITY,),), ((TIMESTAMP, "MANAGED"),))
    builder.bind_typed_rows(((INFINITY,), (INFINITY,)), ((TIMESTAMP, "MANAGED"),))

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


@pytest.mark.parametrize("rows", [(("infinity",),), (("infinity",), ("infinity",))])
def test_typed_row_binding_rejects_the_literal_open_bound_at_a_timestamp_slot(
    rows: tuple[tuple[object, ...], ...],
) -> None:
    # A row cell holds the managed open bound; its spelling is an observation
    # this builder supplies, never a cell value it admits.
    with pytest.raises(SqlGenError, match="does not match MANAGED slot"):
        _builder().bind_typed_rows(rows, ((TIMESTAMP, "MANAGED"),))


def test_typed_row_binding_rejects_inconsistent_widths() -> None:
    with pytest.raises(SqlGenError, match="inconsistent row widths"):
        _builder().bind_typed_rows((("one",), ("two", "extra")), ((STRING, "MANAGED"),))


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
