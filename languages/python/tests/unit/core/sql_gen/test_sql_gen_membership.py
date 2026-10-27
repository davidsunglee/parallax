# pyright: reportPrivateUsage=false

"""Authored memberships as one execution value: Postgres binds one cast array,
another dialect expands one placeholder per element, and a template compiled at
one width renders every other width exactly as direct compilation does."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Final, cast

import pytest

from parallax.core import continuation, deep_fetch
from parallax.core import object_query as oq
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.base import INT64, STRING
from parallax.core.dialect import POSTGRES, Dialect, LockMode
from parallax.core.metamodel import Metamodel
from parallax.core.object_query._resolved import ContinuationCoordinate, ResolvedObjectQuery
from parallax.core.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_template,
)
from parallax.core.sql_gen._context import (
    MembershipForm,
    _TypedBindSpan,
)
from tests.unit._corpus_model_support import model

ORDERS: Final = model("orders")
ANIMAL: Final = model("animal")
DOCUMENT: Final = model("document")
DOCUMENT_LAYOUT: Final = model("document-layout")
CUSTOMER: Final = model("customer")
COLLECTIONS: Final = model("predicate-collections")
_MARIADB: Final = dataclasses.replace(POSTGRES, name="mariadb")
_DIALECTS: Final = pytest.mark.parametrize(
    "dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"]
)
_PROJECTION: Final = deep_fetch.ReadProjectionRequest("none", False)


def _query(
    meta: Metamodel, target: str, predicate: Mapping[str, object], **clauses: object
) -> ResolvedObjectQuery:
    document = {"target": target, "predicate": dict(predicate)} | clauses
    return resolve_read_query(oq.deserialize(document), model=meta, form="rows")


def _membership(op: str, path: str, values: Sequence[object]) -> dict[str, object]:
    return {op: {"path": path, "values": list(values)}}


def _template(
    cold: ResolvedObjectQuery, meta: Metamodel, dialect: Dialect, lock: LockMode | None = None
) -> CompiledTemplate:
    planned = deep_fetch.plan(cold, meta, projection=_PROJECTION, defer_execution_values=True)
    return compile_template(planned.root, meta, dialect, lock=lock)


def _direct(
    query: ResolvedObjectQuery, meta: Metamodel, dialect: Dialect, lock: LockMode | None = None
) -> CompiledRead:
    return compile_read(
        deep_fetch.plan(query, meta, projection=_PROJECTION).root, meta, dialect, lock=lock
    )


def _carriers(binds: Sequence[object]) -> list[object]:
    return [
        (list, _carriers(cast("list[object]", bind)))
        if isinstance(bind, list)
        else (type(bind), bind, bind.as_tuple())
        if isinstance(bind, Decimal)
        else (type(bind), bind)
        for bind in binds
    ]


def _assert_renders_as_direct(
    cold: ResolvedObjectQuery,
    currents: Sequence[ResolvedObjectQuery],
    meta: Metamodel,
    dialect: Dialect,
    lock: LockMode | None = None,
) -> CompiledTemplate:
    """Every query of ``currents``, rendered from the template ``cold`` compiled,
    is what direct compilation of it produces, carrier for carrier."""
    template = _template(cold, meta, dialect, lock)
    for current in (cold, *currents):
        rendered = template.render(query=current).statement
        direct = _direct(current, meta, dialect, lock).statement
        assert rendered == direct
        assert _carriers(rendered.binds) == _carriers(direct.binds)
        assert rendered.wire_binds() == direct.wire_binds()
        assert rendered.execution_value_positions() == ()
    return template


def _orders_page(
    ids: Sequence[int], quantities: Sequence[int], coordinate: tuple[object, ...], limit: int
) -> ResolvedObjectQuery:
    query = _query(
        ORDERS,
        "Order",
        {
            "and": {
                "operands": [
                    _membership("in", "Order.id", ids),
                    _membership("notIn", "Order.qty", quantities),
                    {"greaterThan": {"path": "Order.price", "value": "1.50"}},
                ]
            }
        },
    )
    return continuation.plan(query, ORDERS).after(ContinuationCoordinate(coordinate), limit=limit)


@_DIALECTS
def test_two_memberships_of_different_widths_render_before_a_comparison_seek_and_cap(
    dialect: Dialect,
) -> None:
    template = _assert_renders_as_direct(
        _orders_page([1, 2], [5], (1,), 2),
        [
            _orders_page([4], [5, 6, 7], (9,), 5),
            _orders_page(range(1, 41), [1, 2], (3,), 3),
        ],
        ORDERS,
        dialect,
    )

    memberships = [group for group in template._positions if isinstance(group.form, MembershipForm)]
    assert [group.source for group in memberships] == [("predicate", 0), ("predicate", 1)]
    rendered = template.render(query=_orders_page([4], [5, 6, 7], (9,), 5)).statement
    if dialect is POSTGRES:
        assert "t0.id = any(cast(? as bigint[]))" in rendered.sql
        assert "not t0.qty = any(cast(? as int[]))" in rendered.sql
        assert rendered.binds[:2] == ([4], [5, 6, 7])
    else:
        assert "t0.id in (?) and not t0.qty in (?, ?, ?)" in rendered.sql
        assert rendered.binds[:4] == (4, 5, 6, 7)


@_DIALECTS
def test_a_null_tail_page_renders_its_membership_in_both_arms(dialect: Dialect) -> None:
    def page(ids: Sequence[int], coordinate: tuple[object, ...]) -> ResolvedObjectQuery:
        query = _query(
            ORDERS,
            "Order",
            _membership("in", "Order.id", ids),
            orderBy=[{"attr": "parallax.compatibility.Order.active"}],
        )
        return continuation.plan(query, ORDERS).after(ContinuationCoordinate(coordinate), limit=2)

    template = _assert_renders_as_direct(
        page([1, 2], (True, 1)),
        [page([1, 2, 3, 4, 5], (False, 2)), page([7], (True, 3))],
        ORDERS,
        dialect,
        lock="locking",
    )

    (membership,) = (
        group for group in template._positions if isinstance(group.form, MembershipForm)
    )
    sql = template.render(query=page([1, 2, 3], (False, 2))).statement.sql
    if dialect is POSTGRES:
        assert len(membership.indices) == 2
        assert sql.count("t0.id = any(cast(? as bigint[]))") == 2
    else:
        assert sql.count("t0.id in (?, ?, ?)") == len(membership.indices)


@_DIALECTS
@pytest.mark.parametrize(
    ("meta", "target", "path"),
    [
        pytest.param(DOCUMENT, "Document", "Document.id", id="tpcs-branches"),
        pytest.param(ANIMAL, "Animal", "Animal.id", id="tph-family"),
        pytest.param(ANIMAL, "Dog", "Dog.id", id="tph-concrete"),
    ],
)
def test_an_inheritance_read_renders_its_membership_in_every_branch(
    dialect: Dialect, meta: Metamodel, target: str, path: str
) -> None:
    def read(op: str, ids: Sequence[int]) -> ResolvedObjectQuery:
        return _query(meta, target, _membership(op, path, ids))

    for op in ("in", "notIn"):
        _assert_renders_as_direct(
            read(op, [1, 2]), [read(op, [3]), read(op, range(9))], meta, dialect
        )


def _traveler_names(values: list[object]) -> Mapping[str, object]:
    return _membership("in", "Traveler.displayName", values)


def _trip_nights(values: list[object]) -> Mapping[str, object]:
    return _membership("notIn", "Trip.nights", values)


def _customer_cities(values: list[object]) -> Mapping[str, object]:
    return _membership("in", "Customer.address.city", values)


def _phone_types(values: list[object]) -> Mapping[str, object]:
    where = _membership("notIn", "type", values)
    return {"any": {"path": "Customer.address.phones", "where": where}}


def _basket_tags(values: list[object]) -> Mapping[str, object]:
    return {"any": {"path": "Basket.tags", "where": {"in": {"values": values}}}}


def _basket_scores(values: list[object]) -> Mapping[str, object]:
    return {"none": {"path": "Basket.scores", "where": {"notIn": {"values": values}}}}


def _basket_prices(values: list[object]) -> Mapping[str, object]:
    return {"any": {"path": "Basket.prices", "where": {"in": {"values": values}}}}


@_DIALECTS
@pytest.mark.parametrize(
    ("meta", "target", "predicate", "cold", "currents", "compared"),
    [
        pytest.param(
            DOCUMENT_LAYOUT,
            "Traveler",
            _traveler_names,
            ["Ada"],
            [["Bo", "Cy", "Di"]],
            "jsonb_extract_path_text(t0.payload, ?) = any(cast(? as text[]))",
            id="text-compared-document-attribute",
        ),
        pytest.param(
            DOCUMENT_LAYOUT,
            "Trip",
            _trip_nights,
            [1],
            [[2, 3], list(range(50))],
            "not cast(jsonb_extract_path_text(t0.payload, ?) as bigint) = any(cast(? as bigint[]))",
            id="int32-document-attribute-compares-as-bigint",
        ),
        pytest.param(
            CUSTOMER,
            "Customer",
            _customer_cities,
            ["Oslo"],
            [["Boston", "Lima"]],
            "jsonb_extract_path_text(t0.address, ?) = any(cast(? as text[]))",
            id="value-object-leaf",
        ),
        pytest.param(
            CUSTOMER,
            "Customer",
            _phone_types,
            ["work"],
            [["home", "cell"]],
            "not jsonb_extract_path_text(t1.value, ?) = any(cast(? as text[]))",
            id="value-object-quantifier",
        ),
        pytest.param(
            COLLECTIONS,
            "Basket",
            _basket_tags,
            ["gift"],
            [["x", "y", "z"]],
            "end = any(cast(? as text[]))",
            id="scalar-string-element-quantifier",
        ),
        pytest.param(
            COLLECTIONS,
            "Basket",
            _basket_scores,
            [5],
            [[25, 26]],
            "as bigint) end = any(cast(? as bigint[]))",
            id="scalar-int-element-quantifier",
        ),
        pytest.param(
            COLLECTIONS,
            "Basket",
            _basket_prices,
            ["1.50"],
            [["2.25", "3.00"]],
            "as decimal(8, 2)) end = any(cast(? as decimal[]))",
            id="scalar-decimal-element-quantifier",
        ),
    ],
)
def test_a_document_or_element_membership_casts_its_array_to_the_compared_type(
    dialect: Dialect,
    meta: Metamodel,
    target: str,
    predicate: Callable[[list[object]], Mapping[str, object]],
    cold: list[object],
    currents: list[list[object]],
    compared: str,
) -> None:
    def read(values: list[object]) -> ResolvedObjectQuery:
        return _query(meta, target, predicate(values))

    template = _assert_renders_as_direct(
        read(cold), [read(values) for values in currents], meta, dialect
    )

    sql = template.compiled.statement.sql
    assert compared in sql if dialect is POSTGRES else "any(" not in sql


def test_a_text_compared_document_membership_binds_and_projects_comparison_texts() -> None:
    def read(dates: Sequence[str]) -> ResolvedObjectQuery:
        return _query(DOCUMENT_LAYOUT, "Traveler", _membership("in", "Traveler.joinedOn", dates))

    template = _assert_renders_as_direct(
        read(["2024-01-05"]), [read(["2024-02-01", "2024-03-09"])], DOCUMENT_LAYOUT, POSTGRES
    )

    statement = template.render(query=read(["2024-02-01", "2024-03-09"])).statement
    assert statement.binds[-1] == ["2024-02-01", "2024-03-09"]
    assert statement.typed_bind_spans[-1].form == "COMPARISON_TEXT_ARRAY"
    assert statement.wire_binds()[-1] == ["2024-02-01", "2024-03-09"]


def test_a_managed_array_membership_projects_each_element_to_its_wire_value() -> None:
    def read(prices: Sequence[str]) -> ResolvedObjectQuery:
        return _query(ORDERS, "Order", _membership("in", "Order.price", prices))

    statement = _template(read(["1.50"]), ORDERS, POSTGRES).render(query=read(["2.50", "10.00"]))
    assert statement.statement.binds == ([Decimal("2.50"), Decimal("10.00")],)
    assert statement.statement.typed_bind_spans[-1].form == "MANAGED_ARRAY"
    assert statement.statement.wire_binds() == (["2.50", "10.00"],)


def test_typed_spans_merge_across_adjacent_expanded_memberships() -> None:
    def read(first: Sequence[int], second: Sequence[int]) -> ResolvedObjectQuery:
        return _query(
            ORDERS,
            "Order",
            {
                "and": {
                    "operands": [
                        _membership("in", "Order.id", first),
                        _membership("notIn", "Order.id", second),
                        {"eq": {"path": "Order.id", "value": 9}},
                        {"eq": {"path": "Order.name", "value": "Ada"}},
                    ]
                }
            },
        )

    template = _assert_renders_as_direct(
        read([1], [2]), [read([1, 2, 3], [4, 5]), read([6], [7, 8, 9, 10])], ORDERS, _MARIADB
    )

    statement = template.render(query=read([1, 2, 3], [4, 5])).statement
    assert statement.typed_bind_spans == (
        _TypedBindSpan(0, 6, INT64, "MANAGED"),
        _TypedBindSpan(6, 7, STRING, "MANAGED"),
    )


def test_a_width_one_membership_renders_one_placeholder_where_it_expands() -> None:
    def read(ids: Sequence[int]) -> ResolvedObjectQuery:
        return _query(ORDERS, "Order", _membership("in", "Order.id", ids))

    template = _assert_renders_as_direct(read([1, 2, 3]), [read([7])], ORDERS, _MARIADB)

    assert template.render(query=read([7])).statement.sql.endswith("where t0.id in (?)")


@_DIALECTS
def test_a_membership_beside_temporal_and_dated_operands_renders_each_its_own_value(
    dialect: Dialect,
) -> None:
    def read(dates: Sequence[dt.date], qty: int) -> ResolvedObjectQuery:
        return _query(
            ORDERS,
            "Order",
            {
                "or": {
                    "operands": [
                        {"eq": {"path": "Order.qty", "value": qty}},
                        _membership("in", "Order.orderedOn", [day.isoformat() for day in dates]),
                    ]
                }
            },
        )

    _assert_renders_as_direct(
        read([dt.date(2024, 1, 5)], 1),
        [read([dt.date(2024, 2, 1), dt.date(2024, 3, 1)], 2)],
        ORDERS,
        dialect,
    )
