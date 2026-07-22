"""Statement-half unit tests (entity/statement + expression surface).

Every predicate operator, the boolean combinators and their canonical grouping,
the value-object nested access path, the result-shaping directives, and the
statement lowering/serialization are exercised in the unit lane so the developer
surface is covered independently of the Docker-gated API suite.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from parallax.core import (
    LATEST,
    TX_TIME,
    VALID_TIME,
    Attr,
    AttributeExpr,
    Entity,
    EntityConfig,
    Field,
    Predicate,
    Statement,
)
from parallax.core.descriptor import AsOfAxisMetadata
from parallax.core.op_algebra import All

pytestmark = pytest.mark.unit

_NS = "parallax.compatibility"


class Widget(Entity, frozen=True):
    """A local scalar entity for exercising the statement surface."""

    __parallax__ = EntityConfig(table="widget", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    qty: Attr[int] = Field(type="int32")
    price: Attr[Decimal] = Field(type="decimal(18,2)")
    active: Attr[bool]
    sku: Attr[str] = Field(max_length=32, nullable=True)
    made_on: Attr[dt.date] = Field(column="made_on")


def _op(pred: Predicate) -> dict[str, object]:
    from parallax.core.op_algebra import serialize

    return serialize(pred.op)


def test_scalar_comparison_operators() -> None:
    assert _op(Widget.id == 42) == {"eq": {"attr": "Widget.id", "value": 42}}
    assert _op(Widget.id != 42) == {"notEq": {"attr": "Widget.id", "value": 42}}
    assert _op(Widget.qty > 1) == {"greaterThan": {"attr": "Widget.qty", "value": 1}}
    assert _op(Widget.qty >= 1) == {"greaterThanEquals": {"attr": "Widget.qty", "value": 1}}
    assert _op(Widget.qty < 9) == {"lessThan": {"attr": "Widget.qty", "value": 9}}
    assert _op(Widget.qty <= 9) == {"lessThanEquals": {"attr": "Widget.qty", "value": 9}}
    assert _op(Widget.active.is_(True)) == {"eq": {"attr": "Widget.active", "value": True}}


def test_membership_between_null_and_string_operators() -> None:
    assert _op(Widget.id.in_([1, 2])) == {"in": {"attr": "Widget.id", "values": [1, 2]}}
    assert _op(Widget.id.not_in([1, 2])) == {"notIn": {"attr": "Widget.id", "values": [1, 2]}}
    assert _op(Widget.qty.between(1, 9)) == {
        "between": {"attr": "Widget.qty", "lower": 1, "upper": 9}
    }
    assert _op(Widget.sku.is_null()) == {"isNull": {"attr": "Widget.sku"}}
    assert _op(Widget.sku.is_not_null()) == {"isNotNull": {"attr": "Widget.sku"}}
    assert _op(Widget.sku.like("A%")) == {"like": {"attr": "Widget.sku", "value": "A%"}}
    assert _op(Widget.sku.not_like("A%")) == {"notLike": {"attr": "Widget.sku", "value": "A%"}}
    assert _op(Widget.sku.starts_with("A")) == {"startsWith": {"attr": "Widget.sku", "value": "A"}}
    assert _op(Widget.sku.ends_with("Z")) == {"endsWith": {"attr": "Widget.sku", "value": "Z"}}
    assert _op(Widget.sku.contains("m")) == {"contains": {"attr": "Widget.sku", "value": "m"}}
    ci = _op(Widget.name.like("a", case_insensitive=True))
    assert ci["like"]["caseInsensitive"] is True  # type: ignore[index]


def test_boolean_combinators_and_grouping() -> None:
    conj = _op((Widget.qty > 1) & (Widget.qty < 9))
    assert conj == {
        "and": {
            "operands": [
                {"greaterThan": {"attr": "Widget.qty", "value": 1}},
                {"lessThan": {"attr": "Widget.qty", "value": 9}},
            ]
        }
    }
    disj = _op((Widget.qty < 1) | (Widget.qty > 9))
    assert set(disj) == {"or"}
    negated = _op(~(Widget.qty > 1))
    assert set(negated) == {"not"}
    # An `or` under an `and` is wrapped in a canonical `group`; an `and` under an
    # `or` is not.
    grouped = _op(((Widget.qty >= 9) | (Widget.qty <= 1)) & Widget.active.is_(True))
    assert grouped["and"]["operands"][0] == {  # type: ignore[index]
        "group": {
            "operand": {
                "or": {
                    "operands": [
                        {"greaterThanEquals": {"attr": "Widget.qty", "value": 9}},
                        {"lessThanEquals": {"attr": "Widget.qty", "value": 1}},
                    ]
                }
            }
        }
    }


def test_where_conjoins_and_flattens() -> None:
    stmt = Widget.where(Widget.active.is_(True), Widget.qty > 1)
    assert stmt.serialize() == {
        "and": {
            "operands": [
                {"eq": {"attr": "Widget.active", "value": True}},
                {"greaterThan": {"attr": "Widget.qty", "value": 1}},
            ]
        }
    }
    assert Widget.where().serialize() == {"all": {}}
    assert Widget.where(Widget.id == 1).serialize() == {"eq": {"attr": "Widget.id", "value": 1}}


def test_result_shaping_directives() -> None:
    stmt = Widget.where().order_by(Widget.qty.desc(), Widget.name.asc()).limit(5).distinct()
    assert stmt.serialize() == {
        "limit": {
            "count": 5,
            "operand": {
                "orderBy": {
                    "operand": {"distinct": {"operand": {"all": {}}}},
                    "keys": [
                        {"attr": "Widget.qty", "direction": "desc"},
                        {"attr": "Widget.name", "direction": "asc"},
                    ],
                }
            },
        }
    }


def test_directive_guards() -> None:
    with pytest.raises(ValueError, match="at least one key"):
        Widget.where().order_by()
    with pytest.raises(ValueError, match="positive count"):
        Widget.where().limit(0)


def test_nested_value_object_expression_paths() -> None:
    address = AttributeExpr("Customer", "address")
    assert _op(address.city == "Oslo") == {
        "nestedEq": {"path": "Customer.address.city", "value": "Oslo"}
    }
    assert _op(address.geo.country != "US") == {
        "nestedNotEq": {"path": "Customer.address.geo.country", "value": "US"}
    }
    assert _op(address.geo.elevation > 5) == {
        "nestedGt": {"path": "Customer.address.geo.elevation", "value": 5}
    }
    assert _op(address.geo.elevation >= 5) == {
        "nestedGte": {"path": "Customer.address.geo.elevation", "value": 5}
    }
    assert _op(address.geo.elevation < 5) == {
        "nestedLt": {"path": "Customer.address.geo.elevation", "value": 5}
    }
    assert _op(address.geo.elevation <= 5) == {
        "nestedLte": {"path": "Customer.address.geo.elevation", "value": 5}
    }
    assert _op(address.city.in_(["Oslo", "Berlin"])) == {
        "nestedIn": {"path": "Customer.address.city", "values": ["Oslo", "Berlin"]}
    }
    assert _op(address.city.is_null()) == {"nestedIsNull": {"path": "Customer.address.city"}}
    assert _op(address.city.is_not_null()) == {"nestedIsNotNull": {"path": "Customer.address.city"}}


def test_expression_bool_and_scalar_guards() -> None:
    with pytest.raises(TypeError, match="no truth value"):
        bool(Widget.id)
    with pytest.raises(TypeError, match="no truth value"):
        bool(Widget.id == 1)
    with pytest.raises(TypeError, match="scalar literal"):
        _ = Widget.id == object()
    with pytest.raises(AttributeError):
        _ = Widget.id._private  # dunder/private access is not a value-object hop


def test_attribute_expr_ref_and_str() -> None:
    expr = Widget.name
    assert str(expr.ref) == "Widget.name"


def test_statement_is_a_frozen_value() -> None:
    stmt = Widget.where(Widget.id == 1)
    assert isinstance(stmt, Statement)
    assert stmt.target == "Widget"


# --------------------------------------------------------------------------- #
# Axis-keyed temporal-read clauses (m-temporal-read). The idiomatic entity     #
# class cannot yet DECLARE as-of dimensions (deferred, ledger D-7), so the     #
# statement's temporal builders are exercised over a Statement carrying the    #
# corpus-ingested dimensions directly — proving the wrapper-node construction  #
# (Valid-Time outer/Transaction-Time inner, LATEST -> latest, single-shot).    #
# --------------------------------------------------------------------------- #
_TRANSACTION_TIME = AsOfAxisMetadata(
    dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
)
_VALID_TIME = AsOfAxisMetadata(
    dimension="validTime", start_attribute="valid_start", end_attribute="valid_end"
)


def _balance_stmt() -> Statement:
    return Statement(target="Balance", predicate=All(), as_of_axes=(_TRANSACTION_TIME,))


def _position_stmt() -> Statement:
    return Statement(
        target="Position", predicate=All(), as_of_axes=(_VALID_TIME, _TRANSACTION_TIME)
    )


def test_as_of_latest_serializes_the_current_pin_wrapper() -> None:
    assert _balance_stmt().as_of(tx_time=LATEST).serialize() == {
        "asOf": {"operand": {"all": {}}, "dimension": "transactionTime", "coordinate": "latest"}
    }


def test_as_of_past_instant_normalizes_to_utc_iso() -> None:
    d = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    assert _balance_stmt().as_of(tx_time=d).serialize() == {
        "asOf": {
            "operand": {"all": {}},
            "dimension": "transactionTime",
            "coordinate": "2024-04-01T00:00:00+00:00",
        }
    }


def test_bitemporal_as_of_nests_valid_time_outside_tx_time() -> None:
    stmt = _position_stmt().as_of(valid_time=LATEST, tx_time=LATEST)
    assert stmt.serialize() == {
        "asOf": {
            "operand": {
                "asOf": {
                    "operand": {"all": {}},
                    "dimension": "transactionTime",
                    "coordinate": "latest",
                }
            },
            "dimension": "validTime",
            "coordinate": "latest",
        }
    }


def test_as_of_range_scans_the_window() -> None:
    frm = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)
    to = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    assert _balance_stmt().as_of_range(tx_time=(frm, to)).serialize() == {
        "asOfRange": {
            "operand": {"all": {}},
            "dimension": "transactionTime",
            "start": "2024-06-15T00:00:00+00:00",
            "end": "2024-07-01T00:00:00+00:00",
        }
    }


def test_as_of_range_on_valid_time() -> None:
    frm = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    to = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert _position_stmt().as_of_range(valid_time=(frm, to)).serialize() == {
        "asOfRange": {
            "operand": {"all": {}},
            "dimension": "validTime",
            "start": "2024-01-01T00:00:00+00:00",
            "end": "2024-06-01T00:00:00+00:00",
        }
    }


def test_history_wraps_the_predicate() -> None:
    assert _balance_stmt().history(TX_TIME).serialize() == {
        "history": {"operand": {"all": {}}, "dimension": "transactionTime"}
    }


def test_history_on_valid_time() -> None:
    assert _position_stmt().history(VALID_TIME).serialize() == {
        "history": {"operand": {"all": {}}, "dimension": "validTime"}
    }


def test_history_rejects_a_string_dimension() -> None:
    with pytest.raises(ValueError, match="VALID_TIME / TX_TIME"):
        _balance_stmt().history("tx_time")  # type: ignore[arg-type]


def test_temporal_clause_is_single_shot() -> None:
    with pytest.raises(ValueError, match="single-shot"):
        _balance_stmt().as_of(tx_time=LATEST).as_of(tx_time=LATEST)


def test_temporal_clause_requires_an_axis() -> None:
    with pytest.raises(ValueError, match="at least one dimension"):
        _balance_stmt().as_of()


def test_undeclared_axis_is_rejected_at_build() -> None:
    with pytest.raises(ValueError, match="no valid_time dimension"):
        _balance_stmt().as_of(valid_time=LATEST)


def test_naive_datetime_is_rejected_at_build() -> None:
    with pytest.raises(ValueError, match="naive"):
        _balance_stmt().as_of(tx_time=dt.datetime(2024, 4, 1))
