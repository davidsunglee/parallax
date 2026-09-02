"""Continuation pure page-plan unit tests (`m-snapshot-read` streaming).

Exercises `parallax.core.continuation.plan` with no port and no database, the
way `test_deep_fetch.py` exercises its neighbour: the Continuation Order a page
node carries, the seek `after` composes onto the caller's own predicate, and the
query shape a page plan refuses outright. Most assertions here are over the
returned `ObjectQueryNode` alone.

The algebra is graded as a table, because that is what it is: direction, Null
Placement, term count, whether an authored key already named the primary key, and
the position the keys resolve at all vary independently, and each combination has
one composed order and one exact seek. Beside the table sits a property test —
paging a generated dataset at three page sizes must reproduce the whole result in
the order the first page declares — which is what says the seek is EXACT rather
than merely plausible: every wrong boundary either drops a root or delivers one
twice.

The primary key contributes exactly one term wherever it is graded, because
formation refuses a second primary-key Attribute by either route it could arrive
— locally (`m-metamodel`) or through an inheritance family's ancestry chain
(`m-inheritance`). Both routes are asserted against formation itself rather than
against what the corpus happens to declare.
"""

from __future__ import annotations

import datetime as dt
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cmp_to_key
from typing import Any, Final, cast

import pytest
from _corpus_model_support import corpus, formed
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target as entity_of

from parallax.core import continuation, deep_fetch
from parallax.core.dialect import INFINITY, POSTGRES
from parallax.core.metamodel import (
    AttributeIdentity,
    Metamodel,
    PrimaryKey,
    entity_by_name,
)
from parallax.core.metamodel import TemporalDimension as AxisKind
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.object_query import (
    AsOf,
    AsOfRange,
    History,
    ObjectQueryNode,
    OrderKey,
    TemporalDimension,
    TemporalSelection,
    object_query,
    validate_object_query,
)
from parallax.core.object_query._validated import (
    ContinuationCoordinate,
    ValidatedObjectQuery,
)
from parallax.core.predicate import All, Comparison, Or, PredicateNode
from parallax.core.sql_gen._compile import LoweredStatement
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from parallax.descriptor import _records

ORDERS = accepted_model("orders")
ANIMAL = accepted_model("animal")
BALANCE = accepted_model("balance")
POSITION = accepted_model("position")
DOCUMENT_LAYOUT = accepted_model("document-layout")

_ORDER_ID = "parallax.compatibility.Order.id"
_ORDER_NAME = "parallax.compatibility.Order.name"
_ORDER_QTY = "parallax.compatibility.Order.qty"
_ORDER_SKU = "parallax.compatibility.Order.sku"
_ORDER_ACTIVE = "parallax.compatibility.Order.active"
_ANIMAL_ID = "parallax.compatibility.Animal.id"
_DOG_BARK = "parallax.compatibility.Dog.barkVolume"
_TRAVELER_ID = "parallax.compatibility.Traveler.id"
_TRAVELER_SCORE = "parallax.compatibility.Traveler.score"
_BALANCE_ID = "parallax.compatibility.Balance.id"
_BALANCE_TX_START = "parallax.compatibility.Balance.txStart"
_POSITION_ID = "parallax.compatibility.Position.id"
_POSITION_VALID_START = "parallax.compatibility.Position.validStart"
_POSITION_TX_START = "parallax.compatibility.Position.txStart"
_POSITION_VALID_END = "parallax.compatibility.Position.validEnd"

type _Row = Mapping[AttributeIdentity, object]


def _planned(
    model: Metamodel,
    target: str,
    *,
    predicate: PredicateNode | None = None,
    temporal: dict[TemporalDimension, TemporalSelection] | None = None,
    **clauses: object,
) -> continuation.ContinuationPlan:
    entity = entity_of(model, target)
    selections = dict(temporal or {})
    for axis in entity.declared_as_of_axes:
        dimension: TemporalDimension = (
            "valid-time" if axis.dimension is AxisKind.VALID_TIME else "transaction-time"
        )
        selections.setdefault(dimension, AsOf("latest"))
    query = object_query(
        entity.identity,
        predicate if predicate is not None else All(),
        temporal=selections,
        **clauses,  # pyright: ignore[reportArgumentType] - the caller names real clauses
    )
    return continuation.plan(validate_object_query(entity, query, model), model)


def _identity(model: Metamodel, reference: str) -> AttributeIdentity:
    class_name, _, name = reference.rpartition(".")
    entity = entity_by_name(model, class_name)
    attribute = None if entity is None else entity.attribute(name)
    if attribute is None:
        raise KeyError(reference)
    return attribute.identity


def _active(model: Metamodel, target: str) -> Comparison:
    canonical = entity_of(model, target).identity.canonical
    return Comparison(op="eq", attr=f"{canonical}.name", value="A")


# --------------------------------------------------------------------------- #
# The Continuation Order a page node carries.                                  #
# --------------------------------------------------------------------------- #
def test_an_undeclared_ordering_pages_by_the_primary_key_ascending() -> None:
    # The whole of the order a stream advances by when the caller declared none:
    # the primary key, ascending, which is total, immutable, and non-nullable, so
    # every page seeks and no write moves a root across a page boundary.
    node = _planned(ORDERS, "Order").first(limit=50)
    assert node.authored.order_by == (OrderKey(attr=_ORDER_ID, direction="asc"),)
    assert node.limit == 50


def test_the_first_page_carries_the_callers_query_unchanged_but_ordered_and_capped() -> None:
    # A page node is the caller's own query plus a result shape. Nothing about
    # the target, the predicate, or any other clause is rewritten, which is what
    # keeps a page's rows the same rows the eager read would have matched.
    predicate = _active(ORDERS, "Order")
    plan = _planned(ORDERS, "Order", predicate=predicate)
    node = plan.first(limit=2)
    assert node.root.identity == entity_of(ORDERS, "Order").identity
    assert node.predicate.authored == predicate
    assert node.includes == ()


def test_the_page_size_is_the_nodes_limit_rather_than_a_clause_of_its_own() -> None:
    # `batch_size` reaches SQL as the ordinary `limit` clause of one page's own
    # query: there is no second capping concept anywhere below the page loop.
    plan = _planned(ORDERS, "Order")
    assert plan.first(limit=1).limit == 1
    assert plan.first(limit=1000).limit == 1000


def test_the_continuation_order_is_not_readable_off_the_plan() -> None:
    # Deliberate: a caller hands over one opaque coordinate and the plan states
    # which terms it is measured against, so there is no way to assemble a cursor
    # the plan would then disagree with. Where the order is observable is where it
    # is graded — the `orderBy` of the node `first` returns.
    plan = _planned(ORDERS, "Order")
    assert not hasattr(plan, "order")
    assert not hasattr(plan, "key")


def test_an_authored_ordering_is_carried_verbatim_with_the_key_appended() -> None:
    # The composition rule, on the shape that shows both halves: the authored
    # keys keep their own spelling — an omitted direction stays omitted, which
    # round-trips distinctly from an authored `asc` — and the key is appended
    # after them, ascending, because nothing else makes the order total.
    plan = _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_SKU, nulls="first"),))
    assert plan.first(limit=2).authored.order_by == (
        OrderKey(attr=_ORDER_SKU, nulls="first"),
        OrderKey(attr=_ORDER_ID, direction="asc"),
    )


def test_an_authored_key_naming_the_primary_key_is_not_appended_a_second_time() -> None:
    # The key is in the order once however it got there. An unconditional append
    # would order by it twice and seek a coordinate no page binds, and the second
    # term could not break a tie the first already resolved.
    order = (
        OrderKey(attr=_ORDER_ACTIVE, direction="asc"),
        OrderKey(attr=_ORDER_ID, direction="desc"),
    )
    plan = _planned(ORDERS, "Order", order_by=order)
    assert plan.first(limit=2).authored.order_by == order


def test_an_authored_key_naming_the_primary_key_keeps_the_authors_direction() -> None:
    # Appending is a default rather than a rule: where the author named the key
    # themselves, the order ends in THEIR direction and the seek's last branch
    # follows it.
    plan = _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_ID, direction="desc"),))
    node = plan.after(ContinuationCoordinate((5,)), limit=3)
    assert node.authored.order_by == (OrderKey(attr=_ORDER_ID, direction="desc"),)
    assert _where(_lowered(ORDERS, node).sql) == "t0.id < ?"


def test_a_subtype_position_pages_by_its_family_roots_key() -> None:
    # The physical primary key is family-wide, so a concrete subtype declares
    # none of its own and a stream of one still has a total order to advance by.
    dog = entity_of(ANIMAL, "Dog")
    assert not [
        attribute
        for attribute in dog.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    query = validate_object_query(dog, object_query(dog.identity, All()), ANIMAL)
    node = continuation.plan(query, ANIMAL).first(limit=5)
    assert node.authored.order_by == (OrderKey(attr=_ANIMAL_ID, direction="asc"),)


def test_a_narrowed_reads_sort_key_is_measured_at_the_narrowed_position() -> None:
    # A Sort Key addresses the RESULT position, which `narrowTo` moves, while the
    # primary key stays the family root's. One Continuation Order therefore spans
    # two positions: the narrowed subtype's own member, then the root's key.
    animal = entity_of(ANIMAL, "Animal")
    query = object_query(
        animal.identity,
        All(),
        narrow_to=("parallax.compatibility.Dog",),
        order_by=(OrderKey(attr=_DOG_BARK, direction="desc"),),
    )
    plan = continuation.plan(validate_object_query(animal, query, ANIMAL), ANIMAL)
    node = plan.first(limit=1)
    assert node.authored.order_by == (
        OrderKey(attr=_DOG_BARK, direction="desc"),
        OrderKey(attr=_ANIMAL_ID, direction="asc"),
    )
    assert tuple(entity.identity.canonical for entity in node.narrow_to or ()) == (
        "parallax.compatibility.Dog",
    )


# --------------------------------------------------------------------------- #
# The seek every later page carries: the algebra, as a table.                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _SeekCase:
    """One combination of the algebra, with the SQL m-sql lowers it to.

    ``coordinate`` is positional over the composed ``order``, exactly as the
    carriers a page captures are.
    """

    id: str
    order_by: tuple[OrderKey, ...]
    coordinate: tuple[object, ...]
    order: tuple[OrderKey, ...]
    where: str
    binds: tuple[object, ...]


_APPENDED = OrderKey(attr=_ORDER_ID, direction="asc")

_SEEK_MATRIX: tuple[_SeekCase, ...] = (
    _SeekCase(
        id="undeclared-key-only",
        order_by=(),
        coordinate=(7,),
        order=(_APPENDED,),
        where="t0.id > ?",
        binds=(7,),
    ),
    _SeekCase(
        id="ascending-non-nullable",
        order_by=(OrderKey(attr=_ORDER_NAME),),
        coordinate=("Ada", 1),
        order=(OrderKey(attr=_ORDER_NAME), _APPENDED),
        where="t0.name >= ? and (t0.name > ? or (t0.name = ? and t0.id > ?))",
        binds=("Ada", "Ada", "Ada", 1),
    ),
    _SeekCase(
        id="descending-non-nullable",
        order_by=(OrderKey(attr=_ORDER_NAME, direction="desc"),),
        coordinate=("Ada", 1),
        order=(OrderKey(attr=_ORDER_NAME, direction="desc"), _APPENDED),
        where="t0.name <= ? and (t0.name < ? or (t0.name = ? and t0.id > ?))",
        binds=("Ada", "Ada", "Ada", 1),
    ),
    _SeekCase(
        id="mixed-directions-three-terms",
        order_by=(
            OrderKey(attr=_ORDER_ACTIVE, direction="desc"),
            OrderKey(attr=_ORDER_QTY, direction="asc"),
        ),
        coordinate=(True, 10, 2),
        order=(
            OrderKey(attr=_ORDER_ACTIVE, direction="desc"),
            OrderKey(attr=_ORDER_QTY, direction="asc"),
            _APPENDED,
        ),
        where=(
            "t0.active <= ? and (t0.active < ? or (t0.active = ? and t0.qty > ?) "
            "or (t0.active = ? and t0.qty = ? and t0.id > ?))"
        ),
        binds=(True, True, True, 10, True, 10, 2),
    ),
    _SeekCase(
        id="nullable-placement-omitted-value-coordinate",
        order_by=(OrderKey(attr=_ORDER_SKU),),
        coordinate=("A-100", 1),
        order=(OrderKey(attr=_ORDER_SKU), _APPENDED),
        where="(t0.sku > ? or t0.sku is null or (t0.sku = ? and t0.id > ?))",
        binds=("A-100", "A-100", 1),
    ),
    _SeekCase(
        id="nullable-last-null-coordinate",
        order_by=(OrderKey(attr=_ORDER_SKU, nulls="last"),),
        coordinate=(None, 4),
        order=(OrderKey(attr=_ORDER_SKU, nulls="last"), _APPENDED),
        where="(t0.sku is null and t0.id > ?)",
        binds=(4,),
    ),
    _SeekCase(
        id="nullable-first-value-coordinate",
        order_by=(OrderKey(attr=_ORDER_SKU, nulls="first"),),
        coordinate=("A-100", 1),
        order=(OrderKey(attr=_ORDER_SKU, nulls="first"), _APPENDED),
        where="(t0.sku > ? or (t0.sku = ? and t0.id > ?))",
        binds=("A-100", "A-100", 1),
    ),
    _SeekCase(
        id="nullable-first-null-coordinate",
        order_by=(OrderKey(attr=_ORDER_SKU, nulls="first"),),
        coordinate=(None, 4),
        order=(OrderKey(attr=_ORDER_SKU, nulls="first"), _APPENDED),
        where="(t0.sku is not null or (t0.sku is null and t0.id > ?))",
        binds=(4,),
    ),
    _SeekCase(
        id="nullable-descending-last-value-coordinate",
        order_by=(OrderKey(attr=_ORDER_SKU, direction="desc"),),
        coordinate=("B-200", 2),
        order=(OrderKey(attr=_ORDER_SKU, direction="desc"), _APPENDED),
        where="(t0.sku < ? or t0.sku is null or (t0.sku = ? and t0.id > ?))",
        binds=("B-200", "B-200", 2),
    ),
    _SeekCase(
        id="nullable-term-BELOW-the-leading-one",
        order_by=(OrderKey(attr=_ORDER_NAME), OrderKey(attr=_ORDER_SKU)),
        coordinate=("Ada", "A-100", 1),
        order=(OrderKey(attr=_ORDER_NAME), OrderKey(attr=_ORDER_SKU), _APPENDED),
        where=(
            "t0.name >= ? and (t0.name > ? "
            "or (t0.name = ? and (t0.sku > ? or t0.sku is null)) "
            "or (t0.name = ? and t0.sku = ? and t0.id > ?))"
        ),
        binds=("Ada", "Ada", "Ada", "A-100", "Ada", "A-100", 1),
    ),
    _SeekCase(
        id="authored-key-descending",
        order_by=(
            OrderKey(attr=_ORDER_ACTIVE, direction="asc"),
            OrderKey(attr=_ORDER_ID, direction="desc"),
        ),
        coordinate=(False, 3),
        order=(
            OrderKey(attr=_ORDER_ACTIVE, direction="asc"),
            OrderKey(attr=_ORDER_ID, direction="desc"),
        ),
        where="t0.active >= ? and (t0.active > ? or (t0.active = ? and t0.id < ?))",
        binds=(False, False, False, 3),
    ),
)

_PROJECTION: Final = deep_fetch.ReadProjectionRequest("none", False)


def _lowered(model: Metamodel, node: ValidatedObjectQuery) -> LoweredStatement:
    """One page node as m-sql lowers it: the statement, and its binds in order."""
    return compile_entity_query(
        deep_fetch.plan(node, model, projection=_PROJECTION).root, model, POSTGRES
    ).statement


def _where(sql: str) -> str:
    """A lowered page statement's `where` clause, or "" where it carries none."""
    if " where " not in sql:
        return ""
    return sql.split(" where ", 1)[1].split(" order by ", 1)[0]


def _seek_binds(statement: LoweredStatement) -> tuple[object, ...]:
    """The binds a page statement's `where` clause and everything after it take.

    Binds are positional, so what precedes the clause is skipped by counting the
    holes ahead of it rather than by assuming the projection contributed none.
    """
    ahead = statement.sql.split(" where ", 1)[0].count("?")
    return statement.binds[ahead:]


@pytest.mark.parametrize("case", _SEEK_MATRIX, ids=[case.id for case in _SEEK_MATRIX])
def test_the_seek_matrix(case: _SeekCase) -> None:
    # One composed order and one exact seek per combination of direction, Null
    # Placement, term count, and whether an authored key already named the key.
    # Asserted as whole clauses rather than by shape, because the page statement
    # is a cross-language golden: two targets that lowered different SQL would
    # admit different roots for the same page.
    plan = _planned(ORDERS, "Order", order_by=case.order_by)
    assert plan.first(limit=2).authored.order_by == case.order
    node = plan.after(ContinuationCoordinate(case.coordinate), limit=3)
    assert node.authored.order_by == case.order
    assert node.limit == 3
    statement = _lowered(ORDERS, node)
    assert _where(statement.sql) == case.where
    assert _seek_binds(statement) == (*case.binds, 3)


def test_a_page_captures_one_hidden_cell_per_continuation_order_term() -> None:
    # The coordinate a later page advances by is read back off a cell of the
    # page's own select list, emitted from the same expression the `order by`
    # term is — one per term, positionally, so capture and rebinding address the
    # order the same way. No projected cell is reused, even where it would be
    # identical: `t0.id` is both projected and captured.
    plan = _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_SKU),))
    compiled = compile_entity_query(
        deep_fetch.plan(plan.first(limit=2), ORDERS, projection=_PROJECTION).root, ORDERS, POSTGRES
    )
    assert compiled.coordinate_reads == ("parallax_seek_0", "parallax_seek_1")
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on, "
        "t0.sku parallax_seek_0, t0.id parallax_seek_1 from orders t0"
    )


def test_an_eager_read_of_the_same_query_captures_nothing() -> None:
    # Capture is what paging costs, and nothing else pays it: a query with the
    # very same ordering but no paging emits no hidden cell and lifts no
    # coordinate off its rows.
    entity = entity_of(ORDERS, "Order")
    query = object_query(entity.identity, All(), order_by=(OrderKey(attr=_ORDER_SKU),), limit=2)
    compiled = compile_entity_query(
        deep_fetch.plan(
            validate_object_query(entity, query, ORDERS), ORDERS, projection=_PROJECTION
        ).root,
        ORDERS,
        POSTGRES,
    )
    assert compiled.coordinate_reads == ()
    assert "parallax_seek" not in compiled.statement.sql


def test_null_placement_over_a_non_nullable_key_changes_no_seek() -> None:
    # Placement is observable only on a nullable key (m-dialect), so the two
    # spellings over `Order.name` order the same rows AND seek the same way —
    # while the page node still carries each one as authored.
    coordinate = ContinuationCoordinate(("Ada", 1))
    seeks = {
        placement: _where(
            _lowered(
                ORDERS,
                _planned(
                    ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_NAME, nulls=placement),)
                ).after(coordinate, limit=2),
            ).sql
        )
        for placement in ("first", "last")
    }
    assert seeks["first"] == seeks["last"]
    assert seeks["first"] == _SEEK_MATRIX[1].where


def test_a_nullable_leading_term_carries_no_hoisted_range() -> None:
    # The negative half of the hoist rule. With the nulls placed after a non-null
    # coordinate "after" is two disjoint ranges of the index, so there is no
    # single comparison to hoist and the seek is the branch tree alone.
    plan = _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_SKU),))
    seek = _where(_lowered(ORDERS, plan.after(ContinuationCoordinate(("A-100", 1)), limit=2)).sql)
    assert seek.startswith("(")
    hoisted = _where(
        _lowered(
            ORDERS,
            _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_NAME),)).after(
                ContinuationCoordinate(("Ada", 1)), limit=2
            ),
        ).sql
    )
    assert hoisted.startswith("t0.name >= ? and (")


def test_a_nullable_terms_own_two_way_branch_stays_inside_the_ties_above_it() -> None:
    # The seek is a cross-language golden, so a branch's grouping is part of what
    # it says rather than a rendering choice. A nullable term under Nulls Last is
    # strictly after its coordinate OR null; below the leading term that pair sits
    # beside the ties it advances within, and `and` binds tighter than `or`, so an
    # ungrouped pair would leave `sku is null` a disjunct of the WHOLE seek —
    # admitting every null-`sku` order whatever its name, which is a root the
    # delivery has published already or will publish again.
    plan = _planned(
        ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_NAME), OrderKey(attr=_ORDER_SKU))
    )
    node = plan.after(ContinuationCoordinate(("Ada", "A-100", 1)), limit=2)
    assert _lowered(ORDERS, node).sql.endswith(
        "where t0.name >= ? and (t0.name > ? "
        "or (t0.name = ? and (t0.sku > ? or t0.sku is null)) "
        "or (t0.name = ? and t0.sku = ? and t0.id > ?)) "
        "order by t0.name asc, t0.sku asc, t0.id asc limit ?"
    )


def test_a_document_resident_sort_key_seeks_through_the_extraction_seam() -> None:
    # Residence is a physical fact the Continuation Order never learns: the seek
    # is m-sql's own expansion over the member, and `m-sql` lowers the capture
    # cell, the ordering term, and every seek comparison through one derivation
    # of the dialect's extraction and typed cast — each in its own spelling: a
    # comparison against the typed cast, a null check against the bare
    # extraction, and one path bind ahead of every one of them.
    plan = _planned(DOCUMENT_LAYOUT, "Traveler", order_by=(OrderKey(attr=_TRAVELER_SCORE),))
    node = plan.after(ContinuationCoordinate((7, 1)), limit=2)
    statement = _lowered(DOCUMENT_LAYOUT, node)
    assert statement.sql.endswith(
        "cast(jsonb_extract_path_text(t0.payload, ?) as bigint) parallax_seek_0, "
        "t0.id parallax_seek_1 from traveler t0 "
        "where (cast(jsonb_extract_path_text(t0.payload, ?) as bigint) > ? "
        "or jsonb_extract_path_text(t0.payload, ?) is null "
        "or (cast(jsonb_extract_path_text(t0.payload, ?) as bigint) = ? and t0.id > ?)) "
        "order by cast(jsonb_extract_path_text(t0.payload, ?) as bigint) asc, t0.id asc limit ?"
    )
    assert statement.binds == ("score", "score", 7, "score", "score", 7, 1, "score", 2)


# --------------------------------------------------------------------------- #
# Where the seek attaches, and what it refuses.                                #
# --------------------------------------------------------------------------- #
def test_the_seek_is_a_top_level_conjunct_and_the_callers_terms_bind_first() -> None:
    # A top-level AND-qual over the leading ordering column is what a planner
    # reaches an index range through, so the seek is never nested inside the
    # caller's predicate. The caller's terms come first, which keeps bind order
    # caller-first exactly as an injected as-of term leaves it.
    plan = _planned(ORDERS, "Order", predicate=_active(ORDERS, "Order"))
    statement = _lowered(ORDERS, plan.after(ContinuationCoordinate((4,)), limit=3))
    assert _where(statement.sql) == "t0.name = ? and t0.id > ?"
    assert _seek_binds(statement) == ("A", 4, 3)


def test_a_multi_term_seek_conjoins_both_of_its_parts_beside_the_caller() -> None:
    # The hoisted range and the branch tree are two conjuncts rather than one
    # nested value, so a caller's own predicate, the hoist, and the tree are
    # peers of one conjunction and the planner sees the range at the top level.
    plan = _planned(
        ORDERS,
        "Order",
        predicate=_active(ORDERS, "Order"),
        order_by=(OrderKey(attr=_ORDER_NAME),),
    )
    statement = _lowered(ORDERS, plan.after(ContinuationCoordinate(("Ada", 1)), limit=3))
    assert _where(statement.sql) == (
        "t0.name = ? and t0.name >= ? and (t0.name > ? or (t0.name = ? and t0.id > ?))"
    )


def test_a_callers_disjunction_is_grouped_before_the_seek_is_conjoined_to_it() -> None:
    # An `or` binds looser than the enclosing `and`, so conjoining a seek onto
    # one without grouping it would silently re-associate the caller's own
    # predicate into the seek's first branch.
    left = _active(ORDERS, "Order")
    right = Comparison(op="eq", attr=_ORDER_QTY, value=1)
    plan = _planned(ORDERS, "Order", predicate=Or(operands=(left, right)))
    statement = _lowered(ORDERS, plan.after(ContinuationCoordinate((1,)), limit=3))
    assert _where(statement.sql) == "(t0.name = ? or t0.qty = ?) and t0.id > ?"


def test_a_later_page_of_an_unfiltered_query_carries_the_seek_alone() -> None:
    # An unfiltered query contributes no conjunct at all, so the page's `where`
    # clause is the seek rather than a conjunction with an empty left operand —
    # which would lower to a dangling `and`.
    plan = _planned(ORDERS, "Order")
    statement = _lowered(ORDERS, plan.after(ContinuationCoordinate((2,)), limit=3))
    assert _where(statement.sql) == "t0.id > ?"


def test_a_coordinate_of_the_wrong_width_is_refused_by_name() -> None:
    # A coordinate is positional over the WHOLE Continuation Order, so one of
    # another width was captured under a different order than this plan composes
    # — and lowering it would seek past comparisons the page never evaluated.
    plan = _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_NAME),))
    with pytest.raises(continuation.ContinuationError, match="carries 1"):
        plan.after(ContinuationCoordinate((1,)), limit=3)


def test_a_page_seeks_past_a_null_carrier_rather_than_refusing_it() -> None:
    # The rule a checked delivery rests on: whatever a root's stored data turned
    # out to be, its ordering expressions evaluated to something, and a null one
    # is an ordinary coordinate the next page advances from. Nothing here asks
    # whether a member decoded.
    plan = _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_SKU),))
    statement = _lowered(ORDERS, plan.after(ContinuationCoordinate((None, 4)), limit=3))
    assert _where(statement.sql) == "(t0.sku is null and t0.id > ?)"


def test_a_coordinates_snapshot_is_an_inert_copy_rather_than_a_second_cursor() -> None:
    # What a diagnosis may be handed is a plain tuple of carriers: readable,
    # comparable, and with no public route back to a coordinate — handing over
    # the coordinate itself would hand over the authority to resume a delivery.
    # A carrier may arrive as a buffer the provider still owns, so byte-likes are
    # copied and every other scalar passes through as itself.
    provider_buffer = bytearray(b"\x0a\x1b")
    coordinate = ContinuationCoordinate((provider_buffer, 7, None))
    snapshot = coordinate.snapshot()
    assert snapshot == (b"\x0a\x1b", 7, None)
    provider_buffer.clear()
    assert snapshot[0] == b"\x0a\x1b"
    assert not isinstance(snapshot, ContinuationCoordinate)


def test_a_sort_key_naming_no_declared_attribute_is_refused_by_name() -> None:
    # The plan resolves its own references rather than trusting the caller's:
    # every term needs the member's identity to read a coordinate under and its
    # nullability to decide the seek, so a reference that resolves to nothing has
    # no term to contribute and is refused where it is read.
    with pytest.raises(ValueError, match="no declared ordering attribute"):
        _planned(ORDERS, "Order", order_by=(OrderKey(attr="parallax.compatibility.Order.missing"),))


# --------------------------------------------------------------------------- #
# The milestone edge: a scan's own third component.                            #
# --------------------------------------------------------------------------- #
_SCANS: tuple[tuple[str, TemporalSelection], ...] = (
    ("history", History()),
    ("asOfRange", AsOfRange(start="2024-01-01T00:00:00Z", end="2024-06-01T00:00:00Z")),
)


@pytest.mark.parametrize(
    "selection", [selection for _, selection in _SCANS], ids=[id for id, _ in _SCANS]
)
def test_a_milestone_set_read_orders_by_the_key_then_its_one_axis_start(
    selection: TemporalSelection,
) -> None:
    # One primary key stands behind several result roots of a milestone-set read,
    # so the key alone is not total there. What separates two milestones of one
    # key is the milestone each stands at, which is the axis's own start.
    plan = _planned(BALANCE, "Balance", temporal={"transaction-time": selection})
    assert plan.first(limit=2).authored.order_by == (
        OrderKey(attr=_BALANCE_ID, direction="asc"),
        OrderKey(attr=_BALANCE_TX_START, direction="asc"),
    )


@pytest.mark.parametrize(
    "selection", [selection for _, selection in _SCANS], ids=[id for id, _ in _SCANS]
)
def test_a_bitemporal_scan_appends_both_axis_starts_valid_time_first(
    selection: TemporalSelection,
) -> None:
    # The edge is every declared axis in canonical rank (`m-metamodel`: Valid
    # Time precedes Transaction Time wherever axes are ordered), which is the
    # order a whole-result milestone read already ranks its graphs in. Scanning
    # ONE axis still appends both: a milestone is a rectangle, and two rectangles
    # of one key may differ on the axis the read pinned.
    plan = _planned(POSITION, "Position", temporal={"transaction-time": selection})
    assert plan.first(limit=2).authored.order_by == (
        OrderKey(attr=_POSITION_ID, direction="asc"),
        OrderKey(attr=_POSITION_VALID_START, direction="asc"),
        OrderKey(attr=_POSITION_TX_START, direction="asc"),
    )


def test_a_single_instant_temporal_read_appends_no_edge() -> None:
    # A pin is not a scan: one milestone per key reaches the result, so the key
    # is total by itself and the order is what every non-temporal read's is.
    plan = _planned(POSITION, "Position", temporal={"transaction-time": AsOf("latest")})
    assert plan.first(limit=2).authored.order_by == (OrderKey(attr=_POSITION_ID, direction="asc"),)


def test_an_authored_sort_key_naming_an_axis_start_is_not_appended_twice() -> None:
    # The appended terms are the ones the author did NOT name, edge included —
    # and an authored one is carried exactly as authored, its `desc` included,
    # rather than respelled ascending behind it.
    plan = _planned(
        POSITION,
        "Position",
        temporal={"transaction-time": History()},
        order_by=(OrderKey(attr=_POSITION_TX_START, direction="desc"),),
    )
    assert plan.first(limit=2).authored.order_by == (
        OrderKey(attr=_POSITION_TX_START, direction="desc"),
        OrderKey(attr=_POSITION_ID, direction="asc"),
        OrderKey(attr=_POSITION_VALID_START, direction="asc"),
    )


def test_a_milestone_page_seeks_past_the_edge_the_database_evaluated() -> None:
    # A milestone's coordinate is its axis starts exactly as the ordering
    # expressions produced them, so the seek binds those carriers rather than
    # any spelling of them — and it is the same lexicographic tree an authored
    # Sort Key gets, over one key term and two edge terms.
    plan = _planned(POSITION, "Position", temporal={"transaction-time": History()})
    valid_start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    tx_start = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    statement = _lowered(
        POSITION, plan.after(ContinuationCoordinate((1, valid_start, tx_start)), limit=2)
    )
    assert _where(statement.sql) == (
        "t0.thru_z = ? and t0.pos_id >= ? and (t0.pos_id > ? "
        "or (t0.pos_id = ? and t0.from_z > ?) "
        "or (t0.pos_id = ? and t0.from_z = ? and t0.in_z > ?))"
    )
    assert _seek_binds(statement) == (
        INFINITY,
        1,
        1,
        1,
        valid_start,
        1,
        valid_start,
        tx_start,
        2,
    )


def _milestones() -> list[_Row]:
    """Every rectangle of two keys, tying on each axis and on neither."""
    starts = [
        (dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 1, 1, tzinfo=dt.UTC)),
        (dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 4, 1, tzinfo=dt.UTC)),
        (dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2024, 4, 1, tzinfo=dt.UTC)),
        (dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2024, 9, 1, tzinfo=dt.UTC)),
    ]
    return [
        {
            _identity(POSITION, _POSITION_ID): key,
            _identity(POSITION, _POSITION_VALID_START): valid_start,
            _identity(POSITION, _POSITION_TX_START): tx_start,
            _identity(POSITION, _POSITION_VALID_END): INFINITY,
        }
        for key in (1, 2)
        for valid_start, tx_start in starts
    ]


@pytest.mark.parametrize("batch_size", [1, 2, 3, 4, 5, 8, 9], ids=lambda size: f"batch-{size}")
def test_a_milestone_delivery_pages_through_every_boundary_offset_without_skip_or_duplicate(
    batch_size: int,
) -> None:
    # The property the edge exists for, asserted at every boundary offset a page
    # size can land on: eight milestones over two keys, so a page boundary falls
    # inside one key's own history at every size below eight. Ordering by the key
    # alone would end each of those deliveries early — the next page seeks past
    # the whole key — and this is the same paging evaluation the Column orderings
    # above are graded by, over instants rather than scalars.
    plan = _planned(POSITION, "Position", temporal={"transaction-time": History()})
    delivered = _delivered(POSITION, "Position", plan, _milestones(), batch_size=batch_size)
    ranked = _ranked(POSITION, plan.first(limit=1).authored.order_by)
    assert delivered == sorted(_milestones(), key=ranked)


# --------------------------------------------------------------------------- #
# The property the whole algebra exists for: paging reproduces the order.      #
# --------------------------------------------------------------------------- #
def _dataset() -> list[_Row]:
    """Rows whose values tie at every depth an ordering can tie at."""
    rows: list[_Row] = []
    skus: list[object] = ["A-100", "B-200", None, "A-100", None, "C-300", "B-200", "A-100", None]
    quantities = [5, 5, 10, 10, 5, 20, 20, 5, 10]
    flags = [True, True, False, True, False, True, False, False, True]
    for position, (sku, qty, active) in enumerate(zip(skus, quantities, flags, strict=True)):
        rows.append(
            {
                _identity(ORDERS, _ORDER_ID): position + 1,
                _identity(ORDERS, _ORDER_NAME): f"name-{position % 3}",
                _identity(ORDERS, _ORDER_SKU): sku,
                _identity(ORDERS, _ORDER_QTY): qty,
                _identity(ORDERS, _ORDER_ACTIVE): active,
            }
        )
    return rows


def _columns(model: Metamodel, target: str) -> Mapping[str, AttributeIdentity]:
    """Every column a page statement over ``target`` can name, by identity."""
    return {
        f"t0.{attribute.storage.name}": attribute.identity
        for attribute in entity_of(model, target).declared_attributes
    }


def _admits(
    statement: LoweredStatement, columns: Mapping[str, AttributeIdentity], row: _Row
) -> bool:
    """Whether one lowered page statement's `where` clause selects ``row``.

    The emitted SQL is read the way a database reads it — `and` binding tighter
    than `or`, parentheses meaning what they say, and a comparison against a
    null column selecting nothing — so what a replay exercises is the statement
    the page actually issues rather than a second model of it.

    Binds are positional, so the holes ahead of the clause are skipped rather
    than assumed absent.
    """
    where = _where(statement.sql)
    if not where:
        return True
    ahead = statement.sql.split(" where ", 1)[0].count("?")
    reader = _Clause(where, statement.binds[ahead:], columns, row)
    return reader.disjunction()


class _Clause:
    """A recursive-descent reader over one emitted `where` clause."""

    def __init__(
        self,
        text: str,
        binds: Sequence[object],
        columns: Mapping[str, AttributeIdentity],
        row: _Row,
    ) -> None:
        self._tokens = deque(text.replace("(", " ( ").replace(")", " ) ").split())
        self._binds = iter(binds)
        self._columns = columns
        self._row = row

    def disjunction(self) -> bool:
        value = self._conjunction()
        while self._tokens and self._tokens[0] == "or":
            self._tokens.popleft()
            branch = self._conjunction()
            value = value or branch
        return value

    def _conjunction(self) -> bool:
        value = self._atom()
        while self._tokens and self._tokens[0] == "and":
            self._tokens.popleft()
            term = self._atom()
            value = value and term
        return value

    def _atom(self) -> bool:
        if self._tokens[0] == "(":
            self._tokens.popleft()
            value = self.disjunction()
            self._tokens.popleft()
            return value
        held = self._row[self._columns[self._tokens.popleft()]]
        operator = self._tokens.popleft()
        if operator == "is":
            negated = self._tokens.popleft() == "not"
            if negated:
                self._tokens.popleft()
            return (held is not None) if negated else (held is None)
        self._tokens.popleft()
        bound = next(self._binds)
        return False if held is None else _compares(operator, held, bound)


def _compares(operator: str, held: object, bound: object) -> bool:
    """One emitted SQL comparison, evaluated over the carriers it names."""
    here = cast("Any", held)
    there = cast("Any", bound)
    match operator:
        case "=":
            return bool(here == there)
        case ">":
            return bool(here > there)
        case ">=":
            return bool(here >= there)
        case "<":
            return bool(here < there)
        case _:
            return bool(here <= there)


def _delivered(
    model: Metamodel,
    target: str,
    plan: continuation.ContinuationPlan,
    rows: Sequence[_Row],
    *,
    batch_size: int,
) -> list[_Row]:
    """Page ``rows`` through ``plan``, advancing on the coordinates it captured.

    The production loop's own shape: each page issues its statement, keeps at
    most ``batch_size`` of what the statement admits in the composed order, and
    the next page seeks past the LAST kept root's coordinate — the carriers that
    root's ordering expressions evaluated to, read straight off its stored
    values.
    """
    columns = _columns(model, target)
    order = plan.first(limit=1).authored.order_by
    ranked = _ranked(model, order)
    terms = [_identity(model, key.attr) for key in order]
    delivered: list[_Row] = []
    coordinate: ContinuationCoordinate | None = None
    while True:
        node = (
            plan.first(limit=batch_size)
            if coordinate is None
            else plan.after(coordinate, limit=batch_size)
        )
        statement = _lowered(model, node)
        page = sorted((row for row in rows if _admits(statement, columns, row)), key=ranked)[
            :batch_size
        ]
        delivered.extend(page)
        if len(page) < batch_size:
            return delivered
        coordinate = ContinuationCoordinate(tuple(page[-1][term] for term in terms))


def _ranked(model: Metamodel, order: Sequence[OrderKey]) -> Callable[[_Row], Any]:
    """A total comparator over the Continuation Order the page node declares.

    Ranks nulls by the term's own Null Placement first, then compares the values,
    which is the ordering a dialect's own `NULL` placement produces whichever
    spelling it reaches it through.
    """

    def compare(left: _Row, right: _Row) -> int:
        for term in order:
            identity = _identity(model, term.attr)
            here, there = left[identity], right[identity]
            nulls_first = (term.nulls or "last") == "first"
            here_rank = (0 if nulls_first else 1) if here is None else (1 if nulls_first else 0)
            there_rank = (0 if nulls_first else 1) if there is None else (1 if nulls_first else 0)
            if here_rank != there_rank:
                return -1 if here_rank < there_rank else 1
            if here is None or here == there:
                continue
            ascending = (term.direction or "asc") == "asc"
            ahead = _compares("<" if ascending else ">", here, there)
            return -1 if ahead else 1
        return 0

    return cmp_to_key(compare)


_PAGED_ORDERINGS: tuple[tuple[str, tuple[OrderKey, ...]], ...] = tuple(
    (case.id, case.order_by) for case in _SEEK_MATRIX
)


@pytest.mark.parametrize("batch_size", [1, 2, 3], ids=lambda size: f"batch-{size}")
@pytest.mark.parametrize(
    "order_by", [order for _, order in _PAGED_ORDERINGS], ids=[id for id, _ in _PAGED_ORDERINGS]
)
def test_paging_reproduces_the_whole_result_in_the_order_the_first_page_declares(
    order_by: tuple[OrderKey, ...], batch_size: int
) -> None:
    # The property every branch of the seek exists to satisfy, and the one that
    # catches an off-by-one no node-shape assertion would: evaluating the pages
    # against a dataset that ties at every depth must deliver each root exactly
    # once, in the order the FIRST page declares, at every page size. A seek one
    # comparison too strict drops the tie group's remainder; one too loose
    # delivers it twice.
    rows = _dataset()
    plan = _planned(ORDERS, "Order", order_by=order_by)
    ranked = _ranked(ORDERS, plan.first(limit=1).authored.order_by)
    assert _delivered(ORDERS, "Order", plan, rows, batch_size=batch_size) == sorted(
        rows, key=ranked
    )


# --------------------------------------------------------------------------- #
# Stability: what a write to an ordered-by member does to a delivery.          #
# --------------------------------------------------------------------------- #
# The dataset names every root `name-0` / `name-1` / `name-2`, so `name-2` is
# ahead of every root a delivery has already passed and `name-` is behind every
# root it has not reached yet — one write of each is all the two mutable-key
# rows of the stability table need.
_AT_THE_FRONT = "name-0"
_AHEAD_OF_EVERY_ROOT = "name-2"
_BEHIND_EVERY_ROOT = "name-"

type _MutableRow = dict[AttributeIdentity, object]
type _Writer = Callable[[Sequence[_MutableRow], Sequence[_MutableRow]], None]


def _delivered_under_writes(
    order_by: tuple[OrderKey, ...], *, batch_size: int, write: _Writer
) -> list[object]:
    """The root ids a delivery yields while ``write`` mutates the dataset.

    The page loop with the one ordering the production loop has: a page seeks
    past the coordinate its last root stood at WHEN IT WAS DELIVERED, and the
    write that follows reaches the database before the next page's own statement
    runs. That gap is the whole subject — a coordinate the row has since left.
    """
    rows = [dict(row) for row in _dataset()]
    plan = _planned(ORDERS, "Order", order_by=order_by)
    columns = _columns(ORDERS, "Order")
    order = plan.first(limit=1).authored.order_by
    ranked = _ranked(ORDERS, order)
    terms = [_identity(ORDERS, key.attr) for key in order]
    identity = _identity(ORDERS, _ORDER_ID)
    delivered: list[object] = []
    coordinate: ContinuationCoordinate | None = None
    for _page in range(len(rows) * 2 + 2):
        node = (
            plan.first(limit=batch_size)
            if coordinate is None
            else plan.after(coordinate, limit=batch_size)
        )
        statement = _lowered(ORDERS, node)
        page = sorted((row for row in rows if _admits(statement, columns, row)), key=ranked)[
            :batch_size
        ]
        delivered.extend(row[identity] for row in page)
        if len(page) < batch_size:
            return delivered
        coordinate = ContinuationCoordinate(tuple(page[-1][term] for term in terms))
        write(page, rows)
    raise AssertionError("the delivery did not end")


def _moves_a_delivered_root_ahead(
    page: Sequence[_MutableRow], _rows: Sequence[_MutableRow]
) -> None:
    """The loop's own write: every root it is handed at the front of the order
    is moved to the back of it, which is the shape of a loop marking what it
    processed in the column it asked to be ordered by."""
    for row in page:
        if row[_identity(ORDERS, _ORDER_NAME)] == _AT_THE_FRONT:
            row[_identity(ORDERS, _ORDER_NAME)] = _AHEAD_OF_EVERY_ROOT


def _moves_an_undelivered_root_behind(
    _page: Sequence[_MutableRow], rows: Sequence[_MutableRow]
) -> None:
    """A writer the delivery is not the source of: it moves the LAST root of the
    order behind every root, which no page size has reached by the time the
    first page ends."""
    for row in rows:
        if row[_identity(ORDERS, _ORDER_ID)] == 9:
            row[_identity(ORDERS, _ORDER_NAME)] = _BEHIND_EVERY_ROOT


@pytest.mark.parametrize("batch_size", [1, 2, 3], ids=lambda size: f"batch-{size}")
def test_a_root_whose_ordered_by_member_moves_ahead_of_the_cursor_is_delivered_twice(
    batch_size: int,
) -> None:
    # The duplicate row of the stability table, and the one a writing loop
    # reaches by itself: the cursor names the coordinate the root stood at when
    # it was delivered, so a root moved past that coordinate satisfies the next
    # page's seek all over again. Nothing de-duplicates across a delivery.
    delivered = _delivered_under_writes(
        (OrderKey(attr=_ORDER_NAME),), batch_size=batch_size, write=_moves_a_delivered_root_ahead
    )
    assert len(delivered) > len(set(delivered))


@pytest.mark.parametrize("batch_size", [1, 2, 3], ids=lambda size: f"batch-{size}")
def test_a_root_whose_ordered_by_member_moves_behind_the_cursor_is_skipped(
    batch_size: int,
) -> None:
    # The skip row, which needs a root the delivery has not reached yet: moved
    # behind the position the delivery already passed, it satisfies no later
    # page's seek and nothing ever sees it.
    delivered = _delivered_under_writes(
        (OrderKey(attr=_ORDER_NAME),),
        batch_size=batch_size,
        write=_moves_an_undelivered_root_behind,
    )
    assert 9 not in delivered


@pytest.mark.parametrize("batch_size", [1, 2, 3], ids=lambda size: f"batch-{size}")
@pytest.mark.parametrize(
    "write",
    [_moves_a_delivered_root_ahead, _moves_an_undelivered_root_behind],
    ids=["moved-ahead", "moved-behind"],
)
def test_the_undeclared_order_is_immune_to_both_because_no_write_moves_a_key(
    write: _Writer, batch_size: int
) -> None:
    # The immunity the same two writers meet against the default order: with no
    # authored `orderBy` the Continuation Order is the primary key alone, and a
    # keyed write ADDRESSES a row by that key rather than changing it — so
    # neither writer can move a root across the position, and every root arrives
    # exactly once at every page size.
    delivered = _delivered_under_writes((), batch_size=batch_size, write=write)
    assert delivered == list(range(1, len(_dataset()) + 1))


# --------------------------------------------------------------------------- #
# The model rule the appended term rests on.                                   #
# --------------------------------------------------------------------------- #
_TWO_LOCAL_KEYS = _records.Metamodel(
    entities=(
        _records.Entity(
            name="LedgerEntry",
            table="ledger_entry",
            attributes=(
                _records.Attribute(name="bookId", type="int64", column="book_id", primary_key=True),
                _records.Attribute(name="lineNo", type="int64", column="line_no", primary_key=True),
            ),
        ),
    )
)

_TWO_FAMILY_KEYS = _records.Metamodel(
    entities=(
        _records.Entity(
            name="Ledger",
            inheritance=_records.Inheritance(role="root", strategy="table-per-concrete-subtype"),
            attributes=(
                _records.Attribute(name="bookId", type="int64", column="book_id", primary_key=True),
            ),
        ),
        _records.Entity(
            name="LedgerLine",
            table="ledger_line",
            inheritance=_records.Inheritance(role="concrete-subtype", parent="Ledger"),
            attributes=(
                _records.Attribute(name="lineNo", type="int64", column="line_no", primary_key=True),
            ),
        ),
    )
)


def test_a_composite_primary_key_does_not_form() -> None:
    # The premise the appended term rests on, asserted where it is decided: a
    # second local primary-key Attribute is a formation defect, so no accepted
    # model presents a Continuation Order whose key half is two members and the
    # last branch of every seek is one comparison. The day that contract widens,
    # this fails before anything downstream silently skips a root.
    with pytest.raises(MetamodelValidationError, match="metamodel-primary-key-multiple"):
        formed(_TWO_LOCAL_KEYS)


def test_a_family_whose_ancestry_chain_declares_a_second_key_does_not_form() -> None:
    # The other route to a composite key, and the one a stream reaches through:
    # `_family_key` resolves a subtype's order through its family root, so a
    # subtype adding a key of its own would widen the order without touching the
    # root. The applicable ancestry chain admits exactly one primary-key
    # Attribute (`m-inheritance`), so that model does not form either.
    with pytest.raises(MetamodelValidationError, match="inheritance-primary-key-multiple"):
        formed(_TWO_FAMILY_KEYS)


def test_no_corpus_model_declares_a_composite_primary_key() -> None:
    # The inventory beside the rule: every shipped model the streaming lane
    # plans against carries a single-Attribute key today, so the seek's premise
    # holds of the corpus and not only of formation.
    for stem, model in corpus().items():
        for entity in model.entities:
            keys = [
                attribute.identity.name
                for attribute in entity.declared_attributes
                if isinstance(attribute.primary_key, PrimaryKey)
            ]
            assert len(keys) <= 1, (stem, entity.identity.canonical, keys)


def test_the_page_node_is_a_fresh_value_rather_than_a_mutated_query() -> None:
    # A plan answers nodes and holds no state, so two pages of one plan are two
    # values and the query it was planned from is untouched.
    entity = entity_of(ORDERS, "Order")
    query: ObjectQueryNode = object_query(entity.identity, All())
    plan = continuation.plan(validate_object_query(entity, query, ORDERS), ORDERS)
    first = plan.first(limit=2)
    later = plan.after(ContinuationCoordinate((9,)), limit=2)
    assert query.order_by == ()
    assert query.limit is None
    assert first is not later
    assert first.predicate.authored == All()
    assert first.paging is not None
    assert first.paging.seek is None
