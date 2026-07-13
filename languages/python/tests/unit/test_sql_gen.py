"""SQL read-compiler unit tests (m-sql lowering).

Direct lowering of representative nodes plus every refusal branch this phase
draws: unbound attribute references, inheritance-family reads, the deferred
navigation/narrow/temporal/array-traversal nodes, and malformed value-object
paths — each a loud :class:`SqlGenError`, never a silent wrong emission.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import SqlGenError, Statement, compile_read

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
CUSTOMER = _MODELS["customer"]
PAYMENT = _MODELS["payment"]


def test_all_projects_scalar_columns() -> None:
    statement = compile_read(oa.All(), ORDERS, POSTGRES, "Order")
    assert statement.sql == (
        "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0"
    )
    assert statement.binds == ()


def test_none_lowers_to_unsatisfiable() -> None:
    statement = compile_read(oa.NoneOp(), ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith("where 1 = 0")


def test_nested_null_check_and_membership() -> None:
    is_null = compile_read(
        oa.NestedNullCheck(op="nestedIsNull", path="Customer.address.city"),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert "jsonb_extract_path_text(t0.address, ?) is null" in is_null.sql
    membership = compile_read(
        oa.NestedMembership(path="Customer.address.city", values=("Oslo", "Boston")),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert membership.sql.endswith("in (?, ?)")
    assert membership.binds == ("city", "Oslo", "Boston")


def test_unbound_attribute_is_refused() -> None:
    with pytest.raises(SqlGenError, match="names no attribute"):
        compile_read(
            oa.Comparison(op="eq", attr="Order.mystery", value=1), ORDERS, POSTGRES, "Order"
        )


def test_inheritance_read_is_refused() -> None:
    with pytest.raises(SqlGenError, match="inheritance-family read lowering"):
        compile_read(oa.All(), PAYMENT, POSTGRES, "CardPayment")


@pytest.mark.parametrize(
    "op, message",
    [
        (oa.Narrow(entity="Order", to=("A",), operand=oa.All()), "navigation / narrow"),
        (oa.Navigate(rel="Order.items"), "navigation / narrow"),
        (oa.Exists(rel="Order.items"), "navigation / narrow"),
        (oa.AsOf(operand=oa.All(), as_of_attr="Order.p", date="now"), "temporal-read lowering"),
        (oa.NestedExists(path="Customer.address.phones"), "array traversal"),
    ],
)
def test_deferred_nodes_are_refused(op: oa.Operation, message: str) -> None:
    meta = CUSTOMER if "Customer" in str(op) else ORDERS
    with pytest.raises(SqlGenError, match=message):
        compile_read(op, meta, POSTGRES, "Customer" if meta is CUSTOMER else "Order")


def test_malformed_value_object_paths() -> None:
    with pytest.raises(SqlGenError, match=r"needs Class\.valueObject\.attribute"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )
    with pytest.raises(SqlGenError, match="not a declared value object"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.mystery.city", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )
    with pytest.raises(SqlGenError, match="undeclared"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.mystery", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_directive_nested_in_predicate_is_refused() -> None:
    op = oa.Not(operand=oa.Distinct(operand=oa.All()))
    with pytest.raises(SqlGenError, match="result-shaping directive nested"):
        compile_read(op, ORDERS, POSTGRES, "Order")


def test_nested_path_continuing_past_a_scalar_is_refused() -> None:
    with pytest.raises(SqlGenError, match="continues past scalar"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.city.extra", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_nested_path_ending_on_a_value_object_is_refused() -> None:
    with pytest.raises(SqlGenError, match="does not reach a scalar leaf"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.geo", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_top_level_many_value_object_is_refused() -> None:
    from parallax.core.descriptor import (
        Attribute,
        Entity,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    doc = Entity(
        name="Doc",
        table="doc",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="tags",
                column="tags",
                cardinality="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    meta = Metamodel(entities=(doc,))
    with pytest.raises(SqlGenError, match="crosses a `many` member"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Doc.tags.label", value="x"),
            meta,
            POSTGRES,
            "Doc",
        )


def test_statement_is_frozen_value() -> None:
    statement = Statement("select 1", (1,))
    assert statement.sql == "select 1"
    assert statement.binds == (1,)
