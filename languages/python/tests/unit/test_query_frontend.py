"""Typed query-frontend unit tests (Entity.where + the expression surface).

Every predicate operator, the boolean combinators and their canonical grouping,
the value-object nested access path, and the Object Query's own clauses are
exercised in the unit lane so the developer surface is covered independently of
the Docker-gated API suite.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import fields
from decimal import Decimal
from typing import Any

import pytest

from _support.query_probes import canonical_document, predicate_document
from parallax.core import (
    LATEST,
    TX_TIME,
    VALID_TIME,
    Attr,
    AttributeExpr,
    Bitemporal,
    DomainModel,
    Entity,
    Int32,
    ObjectQuery,
    Predicate,
    QueryDefinitionError,
    TxTemporal,
    attr,
)
from parallax.core.entity._entity import build_object_query
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query._fluent import object_query_node

_NS = "parallax.compatibility"


class Widget(Entity, table="widget", namespace=_NS):
    """A local scalar entity for exercising the Object Query surface."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    qty: Attr[int] = attr(type=Int32)
    price: Attr[Decimal] = attr(precision=18, scale=2)
    active: Attr[bool]
    sku: Attr[str | None] = attr(max_length=32)
    made_on: Attr[dt.date]


_WIDGETS = DomainModel(Widget)


def _op(pred: Predicate[Any]) -> dict[str, object]:
    from parallax.core.predicate import serialize

    return serialize(pred.node)


def test_scalar_comparison_operators() -> None:
    assert _op(Widget.id == 42) == {"eq": {"attr": "parallax.compatibility.Widget.id", "value": 42}}
    assert _op(Widget.id != 42) == {
        "notEq": {"attr": "parallax.compatibility.Widget.id", "value": 42}
    }
    assert _op(Widget.qty > 1) == {
        "greaterThan": {"attr": "parallax.compatibility.Widget.qty", "value": 1}
    }
    assert _op(Widget.qty >= 1) == {
        "greaterThanEquals": {"attr": "parallax.compatibility.Widget.qty", "value": 1}
    }
    assert _op(Widget.qty < 9) == {
        "lessThan": {"attr": "parallax.compatibility.Widget.qty", "value": 9}
    }
    assert _op(Widget.qty <= 9) == {
        "lessThanEquals": {"attr": "parallax.compatibility.Widget.qty", "value": 9}
    }
    assert _op(Widget.active.is_(True)) == {
        "eq": {"attr": "parallax.compatibility.Widget.active", "value": True}
    }


def test_membership_between_null_and_string_operators() -> None:
    assert _op(Widget.id.in_([1, 2])) == {
        "in": {"attr": "parallax.compatibility.Widget.id", "values": [1, 2]}
    }
    assert _op(Widget.id.not_in([1, 2])) == {
        "notIn": {"attr": "parallax.compatibility.Widget.id", "values": [1, 2]}
    }
    assert _op(Widget.qty.between(1, 9)) == {
        "between": {"attr": "parallax.compatibility.Widget.qty", "lower": 1, "upper": 9}
    }
    assert _op(Widget.sku.is_null()) == {"isNull": {"attr": "parallax.compatibility.Widget.sku"}}
    assert _op(Widget.sku.is_not_null()) == {
        "isNotNull": {"attr": "parallax.compatibility.Widget.sku"}
    }
    assert _op(Widget.sku.like("A%")) == {
        "like": {"attr": "parallax.compatibility.Widget.sku", "value": "A%"}
    }
    assert _op(Widget.sku.not_like("A%")) == {
        "notLike": {"attr": "parallax.compatibility.Widget.sku", "value": "A%"}
    }
    assert _op(Widget.sku.starts_with("A")) == {
        "startsWith": {"attr": "parallax.compatibility.Widget.sku", "value": "A"}
    }
    assert _op(Widget.sku.ends_with("Z")) == {
        "endsWith": {"attr": "parallax.compatibility.Widget.sku", "value": "Z"}
    }
    assert _op(Widget.sku.contains("m")) == {
        "contains": {"attr": "parallax.compatibility.Widget.sku", "value": "m"}
    }
    ci = _op(Widget.name.like("a", case_insensitive=True))
    assert ci["like"]["caseInsensitive"] is True  # type: ignore[index] - indexes the JSON-union operand at its known serialized shape


def test_boolean_combinators_and_grouping() -> None:
    conj = _op((Widget.qty > 1) & (Widget.qty < 9))
    assert conj == {
        "and": {
            "operands": [
                {"greaterThan": {"attr": "parallax.compatibility.Widget.qty", "value": 1}},
                {"lessThan": {"attr": "parallax.compatibility.Widget.qty", "value": 9}},
            ]
        }
    }
    disj = _op((Widget.qty < 1) | (Widget.qty > 9))
    assert set(disj) == {"or"}
    flattened_conj = _op(((Widget.qty > 1) & (Widget.qty < 9)) & Widget.active.is_(True))
    assert len(flattened_conj["and"]["operands"]) == 3  # type: ignore[index] - indexes the known serialized And body
    flattened_disj = _op(((Widget.qty < 1) | (Widget.qty > 9)) | Widget.active.is_(True))
    assert len(flattened_disj["or"]["operands"]) == 3  # type: ignore[index] - indexes the known serialized Or body
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
                        {
                            "greaterThanEquals": {
                                "attr": "parallax.compatibility.Widget.qty",
                                "value": 9,
                            }
                        },
                        {
                            "lessThanEquals": {
                                "attr": "parallax.compatibility.Widget.qty",
                                "value": 1,
                            }
                        },
                    ]
                }
            }
        }
    }


def test_where_conjoins_and_flattens() -> None:
    query = Widget.where(Widget.active.is_(True), Widget.qty > 1)
    assert predicate_document(query) == {
        "and": {
            "operands": [
                {"eq": {"attr": "parallax.compatibility.Widget.active", "value": True}},
                {"greaterThan": {"attr": "parallax.compatibility.Widget.qty", "value": 1}},
            ]
        }
    }
    assert predicate_document(Widget.where(Widget.all)) == {"all": {}}
    assert predicate_document(Widget.where(Widget.id == 1)) == {
        "eq": {"attr": "parallax.compatibility.Widget.id", "value": 1}
    }


def test_where_requires_at_least_one_predicate() -> None:
    # `where`'s first predicate is a required positional, so `Widget.where()` is
    # a static error and Python's own call binding refuses it before the body.
    # A dynamic expansion is no different: expansion precedes binding, so an
    # empty sequence binds no first argument and raises the same TypeError.
    with pytest.raises(TypeError, match="required positional argument"):
        Widget.where()  # pyright: ignore[reportCallIssue] - where() takes at least one predicate
    empty: tuple[Predicate[Widget], ...] = ()
    with pytest.raises(TypeError, match="required positional argument"):
        Widget.where(*empty)  # pyright: ignore[reportCallIssue] - an unpacked sequence of unknown length satisfies no required positional either
    # The coded refusal is the internal builder's own precondition, reachable
    # only by calling it directly — `Entity.where` cannot deliver it an empty
    # tuple.
    with pytest.raises(QueryDefinitionError) as caught:
        build_object_query(Widget.identity, ())
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
    document = canonical_document(query)
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Widget.qty", "direction": "desc"},
        {"attr": "parallax.compatibility.Widget.name", "direction": "asc"},
    ]
    assert document["limit"] == 5


def test_clause_invocation_order_never_reaches_the_wire() -> None:
    # An Object Query fills clauses rather than wrapping them as they arrive, so
    # no call sequence can reach the canonical document.
    ordered_first = Widget.where(Widget.all).order_by(Widget.qty.asc()).limit(2)
    limited_first = Widget.where(Widget.all).limit(2).order_by(Widget.qty.asc())
    assert canonical_document(ordered_first) == canonical_document(limited_first)


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
    # A non-literal is a frontend refusal like every other one it judges, so it
    # carries the coded family rather than a bare `TypeError`; `__eq__` / `__ne__`
    # keep `object` for Liskov, which is what lets it be reached at all.
    with pytest.raises(QueryDefinitionError) as scalar:
        _ = Widget.id == object()
    assert scalar.value.code == "query-expression-invalid"
    with pytest.raises(QueryDefinitionError) as not_scalar:
        _ = Widget.id != object()
    assert not_scalar.value.code == "query-expression-invalid"
    with pytest.raises(AttributeError):
        _ = Widget.id._private  # dunder/private access is not a value-object hop


def test_attribute_expr_ref_and_str() -> None:
    expr = Widget.name
    assert str(expr.ref) == "parallax.compatibility.Widget.name"


def test_an_object_query_is_an_opaque_value_with_no_truth_and_no_structural_equality() -> None:
    query = Widget.where(Widget.id == 1)
    assert isinstance(query, ObjectQuery)
    with pytest.raises(TypeError, match="no truth value"):
        bool(query)
    # Two independently authored queries carry one canonical node and are still
    # two objects: identity equality applies, and conformance code compares
    # canonical nodes rather than queries.
    twin = Widget.where(Widget.id == 1)
    assert query != twin
    assert canonical_document(query) == canonical_document(twin)


def test_every_clause_answers_a_new_query_and_leaves_its_receiver_alone() -> None:
    base = Widget.where(Widget.all)
    limited = base.limit(3)
    assert limited is not base
    assert predicate_document(base) == {"all": {}}


def test_the_canonical_node_carries_the_query_clauses_and_nothing_else() -> None:
    node = object_query_node(Widget.where(Widget.id == 1))
    assert node.target == EntityIdentity(_NS, "Widget")
    assert node.predicate == (Widget.id == 1).node
    # The exact shape: the queried position and the seven clause fields, with no
    # model, class index, feature tag, provider state, SQL, or serialization.
    assert [field.name for field in fields(node)] == [
        "target",
        "predicate",
        "narrow_to",
        "temporal",
        "order_by",
        "limit",
        "includes",
    ]


def test_the_canonical_node_is_the_querys_own_value() -> None:
    # Nothing derives a second representation to memoize: reading the node twice
    # answers the same frozen value the query has held since it was built.
    query = Widget.where(Widget.id == 1)
    first, second = object_query_node(query), object_query_node(query)
    assert first == second


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


class _WindowSubclass(tuple[dt.datetime, ...]):
    """A `tuple` subclass, which a scan window is required NOT to be."""


def test_as_of_latest_serializes_the_current_pin() -> None:
    assert _temporal(Balance.where(Balance.all).as_of(tx_time=LATEST)) == {
        "transaction-time": {"asOf": "latest"}
    }


def _temporal(query: ObjectQuery[Any, Any]) -> object:
    return canonical_document(query)["temporal"]


def test_omitted_transaction_time_normalizes_to_explicit_latest() -> None:
    assert _temporal(Balance.where(Balance.all)) == {"transaction-time": {"asOf": "latest"}}


def test_as_of_past_instant_normalizes_to_utc_iso() -> None:
    d = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    assert _temporal(Balance.where(Balance.all).as_of(tx_time=d)) == {
        "transaction-time": {"asOf": "2024-04-01T00:00:00+00:00"}
    }


def test_bitemporal_as_of_selects_each_dimension_independently() -> None:
    query = Position.where(Position.all).as_of(valid_time=LATEST, tx_time=LATEST)
    assert _temporal(query) == {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"asOf": "latest"},
    }


def test_as_of_range_scans_the_window() -> None:
    frm = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)
    to = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    assert _temporal(Balance.where(Balance.all).as_of_range(tx_time=(frm, to))) == {
        "transaction-time": {
            "asOfRange": {
                "start": "2024-06-15T00:00:00+00:00",
                "end": "2024-07-01T00:00:00+00:00",
            }
        }
    }


def test_as_of_range_on_valid_time() -> None:
    frm = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    to = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    assert _temporal(Position.where(Position.all).as_of_range(valid_time=(frm, to))) == {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {
            "asOfRange": {
                "start": "2024-01-01T00:00:00+00:00",
                "end": "2024-06-01T00:00:00+00:00",
            }
        },
    }


def test_as_of_range_refuses_a_window_that_does_not_advance() -> None:
    # A scan is the half-open `[start, end)`, so a reversed pair names the
    # window's complement and an equal pair names nothing at all. Both are
    # refused where the clause is authored: neither ever becomes an `asOfRange`,
    # because the overlap predicate `in_z < end and out_z > start` compiles from
    # either without complaint and answers the wrong rows.
    earlier = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    later = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    for window in ((later, earlier), (earlier, earlier)):
        with pytest.raises(QueryDefinitionError, match="start < end") as caught:
            Balance.where(Balance.all).as_of_range(tx_time=window)
        assert caught.value.code == "query-clause-invalid"


def test_as_of_range_refuses_a_latest_endpoint() -> None:
    # LATEST PINS an axis; an `asOfRange` bound is a finite instant
    # (`predicate.schema.json`), so the sentinel is refused rather than lowered
    # as the literal `"latest"` — which would reach SQL as a text bind against a
    # timestamp column.
    earlier = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    for window in ((LATEST, earlier), (earlier, LATEST)):
        with pytest.raises(QueryDefinitionError, match="finite instants") as caught:
            Balance.where(Balance.all).as_of_range(tx_time=window)  # type: ignore[arg-type] - a deliberate LATEST endpoint drives the finiteness rule
        assert caught.value.code == "query-clause-invalid"


@pytest.mark.parametrize(
    "window",
    [
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC)],
        _WindowSubclass(
            (dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
        ),
        (dt.datetime(2024, 1, 1, tzinfo=dt.UTC),),
        (
            dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
        ),
        ("2024-01-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00"),
    ],
    ids=["list", "tuple-subclass", "one-item", "three-item", "strings"],
)
def test_as_of_range_refuses_a_window_that_is_not_an_exact_instant_pair(window: Any) -> None:
    # The window is judged as a SHAPE and nothing is coerced into it, so a
    # dynamically composed argument meets the same rule a literal one does
    # rather than unpacking into whatever two values it happens to yield.
    with pytest.raises(QueryDefinitionError) as caught:
        Balance.where(Balance.all).as_of_range(tx_time=window)
    assert caught.value.code == "query-clause-invalid"


def test_history_selects_the_whole_milestone_set() -> None:
    assert _temporal(Balance.where(Balance.all).history(TX_TIME)) == {
        "transaction-time": {"history": {}}
    }


def test_history_on_valid_time() -> None:
    assert _temporal(Position.where(Position.all).history(VALID_TIME)) == {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"history": {}},
    }


def test_mixed_bitemporal_variants_compose_in_both_call_orders() -> None:
    history_first = Position.where(Position.all).history(VALID_TIME).as_of(tx_time=LATEST)
    pin_first = Position.where(Position.all).as_of(tx_time=LATEST).history(VALID_TIME)
    expected: dict[str, object] = {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"history": {}},
    }
    assert _temporal(history_first) == expected
    assert _temporal(pin_first) == expected


def test_bitemporal_query_requires_a_valid_time_selection_when_it_is_read() -> None:
    with pytest.raises(QueryDefinitionError, match="requires an explicit Valid-Time selection"):
        object_query_node(Position.where(Position.all))


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
            constant._dimension = "valid-time"  # pyright: ignore[reportPrivateUsage] - frozen dimension constant: reassignment must raise
        with pytest.raises(AttributeError, match="frozen"):
            del constant._dimension  # pyright: ignore[reportPrivateUsage] - frozen dimension constant: deletion must raise
    assert _temporal(Balance.where(Balance.all).history(TX_TIME)) == {
        "transaction-time": {"history": {}}
    }
    assert _temporal(Position.where(Position.all).history(VALID_TIME)) == {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"history": {}},
    }


def test_temporal_clause_is_single_shot() -> None:
    with pytest.raises(QueryDefinitionError, match="single-shot"):
        Balance.where(Balance.all).as_of(tx_time=LATEST).as_of(tx_time=LATEST)


def test_temporal_dimension_is_single_shot_across_variants() -> None:
    with pytest.raises(QueryDefinitionError, match=r"transaction-time.*single-shot"):
        Balance.where(Balance.all).history(TX_TIME).as_of(tx_time=LATEST)


def test_temporal_clause_requires_an_axis() -> None:
    with pytest.raises(QueryDefinitionError, match="at least one dimension"):
        Balance.where(Balance.all).as_of()


def test_undeclared_axis_is_rejected_at_build() -> None:
    with pytest.raises(QueryDefinitionError, match="no valid_time dimension"):
        Balance.where(Balance.all).as_of(valid_time=LATEST)


def test_naive_datetime_is_rejected_at_build() -> None:
    with pytest.raises(ValueError, match="naive"):
        Balance.where(Balance.all).as_of(tx_time=dt.datetime(2024, 4, 1))
