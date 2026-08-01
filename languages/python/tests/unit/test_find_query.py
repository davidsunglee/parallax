"""Find Query unit tests (entity/_query + the expression surface).

Every predicate operator, the boolean combinators and their canonical grouping,
the value-object nested access path, the result-shaping clauses, and the query
lowering are exercised in the unit lane so the developer surface is covered
independently of the Docker-gated API suite.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest

from _support.query_probes import lowered_document
from parallax.core import (
    LATEST,
    TX_TIME,
    VALID_TIME,
    Attr,
    AttributeExpr,
    Bitemporal,
    DomainModel,
    Entity,
    FindQuery,
    Int32,
    Predicate,
    QueryDefinitionError,
    TxTemporal,
    attr,
)
from parallax.core.entity._query import build_find_query

_NS = "parallax.compatibility"


class Widget(Entity, table="widget", namespace=_NS):
    """A local scalar entity for exercising the Find Query surface."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    qty: Attr[int] = attr(type=Int32)
    price: Attr[Decimal] = attr(precision=18, scale=2)
    active: Attr[bool]
    sku: Attr[str | None] = attr(max_length=32)
    made_on: Attr[dt.date]


_WIDGETS = DomainModel(Widget)


def _op(pred: Predicate[Any]) -> dict[str, object]:
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
    assert ci["like"]["caseInsensitive"] is True  # type: ignore[index] - indexes the JSON-union operand at its known serialized shape


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
    assert grouped["and"]["operands"][0] == {  # type: ignore[index] - indexes the JSON-union operand at its known serialized shape
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
    query = Widget.where(Widget.active.is_(True), Widget.qty > 1)
    assert lowered_document(query) == {
        "and": {
            "operands": [
                {"eq": {"attr": "Widget.active", "value": True}},
                {"greaterThan": {"attr": "Widget.qty", "value": 1}},
            ]
        }
    }
    assert lowered_document(Widget.where(Widget.all)) == {"all": {}}
    assert lowered_document(Widget.where(Widget.id == 1)) == {
        "eq": {"attr": "Widget.id", "value": 1}
    }


def test_where_requires_at_least_one_predicate() -> None:
    # `where`'s first predicate is a required positional, so `Widget.where()` is
    # a static error and Python's own call binding refuses it before the body.
    # The coded rule is the seam's, where a dynamically composed argument list
    # can still arrive empty.
    with pytest.raises(TypeError, match="required positional argument"):
        Widget.where()  # pyright: ignore[reportCallIssue] - where() takes at least one predicate
    with pytest.raises(QueryDefinitionError) as caught:
        build_find_query(Widget.identity, ())
    assert caught.value.code == "query-clause-invalid"


def test_the_unfiltered_spelling_is_the_whole_filter_or_none_of_it() -> None:
    # `Entity.all` is not a Predicate, so only `where`'s first parameter admits
    # it and a trailing one is a static error too. The runtime rule refuses both
    # orders, which is what an untyped caller reaches.
    with pytest.raises(QueryDefinitionError) as leading:
        Widget.where(Widget.all, Widget.id == 1)
    assert leading.value.code == "query-expression-invalid"
    with pytest.raises(QueryDefinitionError) as trailing:
        Widget.where(Widget.id == 1, Widget.all)  # pyright: ignore[reportArgumentType] - Entity.all is not a Predicate, so it never joins one
    assert trailing.value.code == "query-expression-invalid"


def test_result_shaping_clauses() -> None:
    query = Widget.where(Widget.all).order_by(Widget.qty.desc(), Widget.name.asc()).limit(5)
    assert lowered_document(query) == {
        "limit": {
            "count": 5,
            "operand": {
                "orderBy": {
                    "operand": {"all": {}},
                    "keys": [
                        {"attr": "Widget.qty", "direction": "desc"},
                        {"attr": "Widget.name", "direction": "asc"},
                    ],
                }
            },
        }
    }


def test_clause_invocation_order_never_reaches_the_lowering() -> None:
    # A Find Query retains clauses rather than wrapping them as they arrive, so
    # the canonical inner-to-outer order is lowering's alone.
    ordered_first = Widget.where(Widget.all).order_by(Widget.qty.asc()).limit(2)
    limited_first = Widget.where(Widget.all).limit(2).order_by(Widget.qty.asc())
    assert lowered_document(ordered_first) == lowered_document(limited_first)


def test_clause_guards() -> None:
    with pytest.raises(QueryDefinitionError) as no_key:
        Widget.where(Widget.all).order_by()
    assert no_key.value.code == "query-clause-invalid"
    with pytest.raises(QueryDefinitionError) as not_positive:
        Widget.where(Widget.all).limit(0)
    assert not_positive.value.code == "query-clause-invalid"


def test_a_limit_is_single_shot_and_takes_a_positive_builtin_int() -> None:
    # `True` is not the limit 1: `bool` is a subtype of `int`, so no parameter
    # refuses it and only the runtime rule can — a coercible value is refused
    # rather than coerced, and a second limit derives from the unbounded base.
    with pytest.raises(QueryDefinitionError, match="single-shot"):
        Widget.where(Widget.all).limit(2).limit(3)
    with pytest.raises(QueryDefinitionError, match="positive built-in int"):
        Widget.where(Widget.all).limit(True)
    with pytest.raises(QueryDefinitionError, match="positive built-in int"):
        Widget.where(Widget.all).limit(-1)


def test_one_attribute_orders_a_query_once() -> None:
    # Across one call and across successive calls alike, and whatever direction
    # each occurrence carries.
    with pytest.raises(QueryDefinitionError, match="already orders"):
        Widget.where(Widget.all).order_by(Widget.qty.asc(), Widget.qty.desc())
    with pytest.raises(QueryDefinitionError, match="already orders"):
        Widget.where(Widget.all).order_by(Widget.qty.asc()).order_by(Widget.qty.desc())


def test_nested_value_object_expression_paths() -> None:
    # Built directly rather than through class access, so it names no Entity
    # Class and its parameters carry nothing.
    address: AttributeExpr[Any, Any] = AttributeExpr("Customer", "address")
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


def test_a_find_query_is_an_opaque_value_with_no_truth_and_no_structural_equality() -> None:
    query = Widget.where(Widget.id == 1)
    assert isinstance(query, FindQuery)
    with pytest.raises(TypeError, match="no truth value"):
        bool(query)
    # Two independently authored queries lower to one operation and are still
    # two objects: identity equality applies, and conformance code compares
    # lowerings rather than queries.
    twin = Widget.where(Widget.id == 1)
    assert query != twin
    assert lowered_document(query) == lowered_document(twin)


def test_every_clause_answers_a_new_query_and_leaves_its_receiver_alone() -> None:
    base = Widget.where(Widget.all)
    limited = base.limit(3)
    assert limited is not base
    assert lowered_document(base) == {"all": {}}


# --------------------------------------------------------------------------- #
# Axis-keyed temporal-read clauses (m-temporal-read) over two locally declared #
# framework-base entities — proving the wrapper-node construction (Valid-Time  #
# outer / Transaction-Time inner, LATEST -> latest, single-shot) with no whole #
# model behind it, since authoring reaches none.                               #
# --------------------------------------------------------------------------- #
class Balance(TxTemporal, table="balance", namespace=_NS):
    """A Transaction-Time-Only entity: the one axis a temporal clause may pin."""

    id: Attr[int] = attr(primary_key=True)


class Position(Bitemporal, table="position", namespace=_NS):
    """A Bitemporal entity: both axes, nested Valid-Time outside Transaction-Time."""

    id: Attr[int] = attr(primary_key=True)


def test_as_of_latest_serializes_the_current_pin_wrapper() -> None:
    assert lowered_document(Balance.where(Balance.all).as_of(tx_time=LATEST)) == {
        "asOf": {"operand": {"all": {}}, "dimension": "transactionTime", "coordinate": "latest"}
    }


def test_as_of_past_instant_normalizes_to_utc_iso() -> None:
    d = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    assert lowered_document(Balance.where(Balance.all).as_of(tx_time=d)) == {
        "asOf": {
            "operand": {"all": {}},
            "dimension": "transactionTime",
            "coordinate": "2024-04-01T00:00:00+00:00",
        }
    }


def test_bitemporal_as_of_nests_valid_time_outside_tx_time() -> None:
    query = Position.where(Position.all).as_of(valid_time=LATEST, tx_time=LATEST)
    assert lowered_document(query) == {
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
    assert lowered_document(Balance.where(Balance.all).as_of_range(tx_time=(frm, to))) == {
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
    assert lowered_document(Position.where(Position.all).as_of_range(valid_time=(frm, to))) == {
        "asOfRange": {
            "operand": {"all": {}},
            "dimension": "validTime",
            "start": "2024-01-01T00:00:00+00:00",
            "end": "2024-06-01T00:00:00+00:00",
        }
    }


def test_history_wraps_the_predicate() -> None:
    assert lowered_document(Balance.where(Balance.all).history(TX_TIME)) == {
        "history": {"operand": {"all": {}}, "dimension": "transactionTime"}
    }


def test_history_on_valid_time() -> None:
    assert lowered_document(Position.where(Position.all).history(VALID_TIME)) == {
        "history": {"operand": {"all": {}}, "dimension": "validTime"}
    }


def test_history_rejects_a_string_dimension() -> None:
    with pytest.raises(QueryDefinitionError, match="VALID_TIME / TX_TIME") as caught:
        Balance.where(Balance.all).history("tx_time")  # type: ignore[arg-type] - deliberate string dimension drives history's constant-only validation
    assert caught.value.code == "query-clause-invalid"


def test_dimension_constants_are_frozen() -> None:
    # `history()` accepts the constants by identity and lowers through their
    # dimension value, so a mutable singleton could silently flip what an
    # accepted constant lowers to; both mutation forms are refused and the
    # lowering stays pinned afterwards.
    for constant in (TX_TIME, VALID_TIME):
        with pytest.raises(AttributeError, match="frozen"):
            constant._dimension = "validTime"  # pyright: ignore[reportPrivateUsage] - frozen dimension constant: reassignment must raise
        with pytest.raises(AttributeError, match="frozen"):
            del constant._dimension  # pyright: ignore[reportPrivateUsage] - frozen dimension constant: deletion must raise
    assert lowered_document(Balance.where(Balance.all).history(TX_TIME)) == {
        "history": {"operand": {"all": {}}, "dimension": "transactionTime"}
    }
    assert lowered_document(Position.where(Position.all).history(VALID_TIME)) == {
        "history": {"operand": {"all": {}}, "dimension": "validTime"}
    }


def test_temporal_clause_is_single_shot() -> None:
    with pytest.raises(QueryDefinitionError, match="single-shot"):
        Balance.where(Balance.all).as_of(tx_time=LATEST).as_of(tx_time=LATEST)


def test_temporal_clause_requires_an_axis() -> None:
    with pytest.raises(QueryDefinitionError, match="at least one dimension"):
        Balance.where(Balance.all).as_of()


def test_undeclared_axis_is_rejected_at_build() -> None:
    with pytest.raises(QueryDefinitionError, match="no valid_time dimension"):
        Balance.where(Balance.all).as_of(valid_time=LATEST)


def test_naive_datetime_is_rejected_at_build() -> None:
    with pytest.raises(ValueError, match="naive"):
        Balance.where(Balance.all).as_of(tx_time=dt.datetime(2024, 4, 1))
