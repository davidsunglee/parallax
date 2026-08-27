"""Continuation pure page-plan unit tests (`m-snapshot-read` streaming).

Exercises `parallax.core.continuation.plan` with no port and no database, the
way `test_deep_fetch.py` exercises its neighbour: the Continuation Order a page
node carries, the seek `after` composes onto the caller's own predicate, and the
two query shapes a page plan refuses outright. Every assertion here is over the
returned `ObjectQueryNode` alone.

The Continuation Order is one Attribute wherever it is graded, because formation
refuses a second primary-key Attribute by either route it could arrive — locally
(`m-metamodel`) or through an inheritance family's ancestry chain
(`m-inheritance`). That is what makes a cursor one bindable value here rather
than a lexicographic tuple, and both routes are asserted against formation
itself rather than against what the corpus happens to declare.
"""

from __future__ import annotations

import pytest
from _corpus_model_support import corpus, formed
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target as entity_of

from parallax.core import continuation
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.object_query import (
    AsOfRange,
    History,
    ObjectQueryNode,
    OrderKey,
    TemporalDimension,
    TemporalSelection,
    object_query,
)
from parallax.core.predicate import All, And, Comparison, Group, Or, PredicateNode
from parallax.descriptor import _records

ORDERS = accepted_model("orders")
ANIMAL = accepted_model("animal")
BALANCE = accepted_model("balance")

_ORDER_ID = "parallax.compatibility.Order.id"
_ANIMAL_ID = "parallax.compatibility.Animal.id"


def _planned(
    model: Metamodel,
    target: str,
    *,
    predicate: PredicateNode | None = None,
    temporal: dict[TemporalDimension, TemporalSelection] | None = None,
    **clauses: object,
) -> continuation.ContinuationPlan:
    entity = entity_of(model, target)
    query = object_query(
        entity.identity,
        predicate if predicate is not None else All(),
        temporal=temporal,
        **clauses,  # pyright: ignore[reportArgumentType] - the caller names real clauses
    )
    return continuation.plan(entity, query, model)


def _key(entity: EntityMetadata) -> AttributeIdentity:
    return next(
        attribute.identity
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


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
    assert node.order_by == (OrderKey(attr=_ORDER_ID, direction="asc"),)
    assert node.limit == 50


def test_the_first_page_carries_the_callers_query_unchanged_but_ordered_and_capped() -> None:
    # A page node is the caller's own query plus a result shape. Nothing about
    # the target, the predicate, or any other clause is rewritten, which is what
    # keeps a page's rows the same rows the eager read would have matched.
    predicate = _active(ORDERS, "Order")
    plan = _planned(ORDERS, "Order", predicate=predicate)
    node = plan.first(limit=2)
    assert node.target == entity_of(ORDERS, "Order").identity
    assert node.predicate == predicate
    assert node.includes == ()


def test_the_page_size_is_the_nodes_limit_rather_than_a_clause_of_its_own() -> None:
    # `batch_size` reaches SQL as the ordinary `limit` clause of one page's own
    # query: there is no second capping concept anywhere below the page loop.
    plan = _planned(ORDERS, "Order")
    assert plan.first(limit=1).limit == 1
    assert plan.first(limit=1000).limit == 1000


def test_the_continuation_order_is_not_readable_off_the_plan() -> None:
    # Deliberate: a caller hands over a whole root and the plan selects its own
    # terms, so there is no way to assemble a cursor the plan would then disagree
    # with. Where the order is observable is where it is graded — the `orderBy`
    # of the node `first` returns.
    plan = _planned(ORDERS, "Order")
    assert not hasattr(plan, "order")
    assert not hasattr(plan, "key")


# --------------------------------------------------------------------------- #
# The seek every later page carries.                                           #
# --------------------------------------------------------------------------- #
def test_a_later_page_seeks_strictly_past_the_last_delivered_root() -> None:
    # "Where I left off", as the one term a single-Attribute Continuation Order
    # needs: strictly greater than the last root's own key.
    plan = _planned(ORDERS, "Order")
    order = entity_of(ORDERS, "Order")
    node = plan.after({_key(order): 7}, limit=3)
    assert node.predicate == Comparison(op="greaterThan", attr=_ORDER_ID, value=7)
    assert node.order_by == (OrderKey(attr=_ORDER_ID, direction="asc"),)
    assert node.limit == 3


def test_the_seek_is_a_top_level_conjunct_and_the_callers_terms_bind_first() -> None:
    # A top-level AND-qual over the leading ordering column is what a planner
    # reaches an index range through, so the seek is never nested inside the
    # caller's predicate. The caller's terms come first, which keeps bind order
    # caller-first exactly as an injected as-of term leaves it.
    predicate = _active(ORDERS, "Order")
    plan = _planned(ORDERS, "Order", predicate=predicate)
    node = plan.after({_key(entity_of(ORDERS, "Order")): 4}, limit=3)
    assert node.predicate == And(
        operands=(predicate, Comparison(op="greaterThan", attr=_ORDER_ID, value=4))
    )


def test_a_callers_disjunction_is_grouped_before_the_seek_is_conjoined_to_it() -> None:
    # An `or` binds looser than the enclosing `and`, so conjoining a seek onto
    # one without grouping it would silently re-associate the caller's own
    # predicate into the seek's disjunct.
    left = _active(ORDERS, "Order")
    right = Comparison(op="eq", attr="parallax.compatibility.Order.qty", value=1)
    plan = _planned(ORDERS, "Order", predicate=Or(operands=(left, right)))
    node = plan.after({_key(entity_of(ORDERS, "Order")): 1}, limit=3)
    assert node.predicate == And(
        operands=(
            Group(operand=Or(operands=(left, right))),
            Comparison(op="greaterThan", attr=_ORDER_ID, value=1),
        )
    )


def test_a_later_page_of_an_unfiltered_query_carries_the_seek_alone() -> None:
    # An unfiltered query's predicate contributes no conjunct at all, so the
    # page's own predicate is the seek rather than a conjunction with an empty
    # left operand — which would lower to a dangling `and`.
    plan = _planned(ORDERS, "Order")
    node = plan.after({_key(entity_of(ORDERS, "Order")): 2}, limit=3)
    assert node.predicate == Comparison(op="greaterThan", attr=_ORDER_ID, value=2)


def test_advancing_from_a_root_that_carries_no_key_is_refused_by_name() -> None:
    # Only decoded values are bindable. A mapping missing the Continuation
    # Order's own member names a caller defect rather than an empty page, so it
    # is refused rather than silently paging from nothing.
    plan = _planned(ORDERS, "Order")
    with pytest.raises(continuation.ContinuationError, match="does not carry"):
        plan.after({}, limit=3)


# --------------------------------------------------------------------------- #
# Inheritance: the key is family-wide and root-owned.                          #
# --------------------------------------------------------------------------- #
def test_a_subtype_position_pages_by_its_family_roots_key() -> None:
    # The physical primary key is family-wide, so a concrete subtype declares
    # none of its own and a stream of one still has a total order to advance by.
    dog = entity_of(ANIMAL, "Dog")
    assert not [
        attribute
        for attribute in dog.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    node = continuation.plan(dog, object_query(dog.identity, All()), ANIMAL).first(limit=5)
    assert node.order_by == (OrderKey(attr=_ANIMAL_ID, direction="asc"),)


# --------------------------------------------------------------------------- #
# The two query shapes a page plan refuses.                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "selection",
    [History(), AsOfRange(start="2024-01-01T00:00:00Z", end="2024-06-01T00:00:00Z")],
    ids=["history", "asOfRange"],
)
def test_a_milestone_set_read_has_no_page_order(selection: TemporalSelection) -> None:
    # One primary key stands behind several result roots of a milestone-set read,
    # so paging on the key alone would skip or duplicate at a page boundary.
    with pytest.raises(continuation.ContinuationError, match="milestone-set"):
        _planned(BALANCE, "Balance", temporal={"transaction-time": selection})


def test_an_authored_ordering_has_no_page_order() -> None:
    # The order a caller asked for is not the order this plan advances by, and
    # delivering roots in a different one would answer a query nobody wrote.
    with pytest.raises(continuation.ContinuationError, match="orderBy"):
        _planned(ORDERS, "Order", order_by=(OrderKey(attr=_ORDER_ID),))


# --------------------------------------------------------------------------- #
# The model rule the single-term cursor rests on.                              #
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
    # The premise the single-term seek rests on, asserted where it is decided: a
    # second local primary-key Attribute is a formation defect, so no accepted
    # model presents a Continuation Order of two members and the seek is one
    # comparison rather than a lexicographic disjunction. The day that contract
    # widens, this fails before anything downstream silently skips a root.
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
    plan = continuation.plan(entity, query, ORDERS)
    first = plan.first(limit=2)
    later = plan.after({_key(entity): 9}, limit=2)
    assert query.order_by == ()
    assert query.limit is None
    assert first is not later
    assert first.predicate == All()
