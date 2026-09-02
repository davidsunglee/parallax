"""The m-sql half of continuation: capture cells, carrier binds, and the seam's refusals.

`test_continuation.py` grades the branch tree a Continuation Order composes,
whole clause by whole clause, because the page statement is a cross-language
golden. What is graded here is what only this side can answer: the FORM a
carrier crosses the bind seam in, and the two disagreements between the order a
page was composed against and the order it is being lowered under — neither of
which any composed clause can show.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target as entity_of

from parallax.core import continuation, deep_fetch
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import OrderKey, object_query, validate_object_query
from parallax.core.object_query._validated import (
    ContinuationCoordinate,
    ContinuationTerm,
    Paging,
    ValidatedObjectQuery,
    ValidatedSeek,
)
from parallax.core.predicate import All
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._compile import LoweredStatement
from parallax.core.sql_gen._compile import compile_read as compile_entity_query

DOCUMENT_LAYOUT = accepted_model("document-layout")
ORDERS = accepted_model("orders")

_TRAVELER_JOINED = "parallax.compatibility.Traveler.joinedOn"
_ORDER_NAME = "parallax.compatibility.Order.name"

_PROJECTION = deep_fetch.ReadProjectionRequest("none", False)


def _planned(model: Metamodel, target: str, *keys: OrderKey) -> continuation.ContinuationPlan:
    entity = entity_of(model, target)
    query = object_query(entity.identity, All(), order_by=keys)
    return continuation.plan(validate_object_query(entity, query, model), model)


def _lowered(model: Metamodel, node: ValidatedObjectQuery) -> LoweredStatement:
    return compile_entity_query(
        deep_fetch.plan(node, model, projection=_PROJECTION).root, model, POSTGRES
    ).statement


def test_a_text_compared_resident_carrier_crosses_as_the_text_it_already_is() -> None:
    # `joinedOn` is a `date`, one of the six types whose canonical document
    # spelling already orders as text, so its extraction compares WITHOUT a cast
    # and what the database evaluated for it is that text. The carrier therefore
    # crosses as comparison text and is not converted on the way: re-deriving the
    # text from it would decode a value the coordinate exists precisely to avoid
    # decoding, and a corrupt one has no managed form to decode into at all.
    plan = _planned(DOCUMENT_LAYOUT, "Traveler", OrderKey(attr=_TRAVELER_JOINED))
    node = plan.after(ContinuationCoordinate(("2024-01-05", 1)), limit=2)
    statement = _lowered(DOCUMENT_LAYOUT, node)
    assert statement.sql.endswith(
        "where (jsonb_extract_path_text(t0.payload, ?) > ? "
        "or jsonb_extract_path_text(t0.payload, ?) is null "
        "or (jsonb_extract_path_text(t0.payload, ?) = ? and t0.id > ?)) "
        "order by jsonb_extract_path_text(t0.payload, ?) asc, t0.id asc limit ?"
    )
    assert statement.binds == (
        "joinedOn",
        "joinedOn",
        "2024-01-05",
        "joinedOn",
        "joinedOn",
        "2024-01-05",
        1,
        "joinedOn",
        2,
    )
    assert statement.wire_binds()[2] == "2024-01-05"


def _crossed(node: ValidatedObjectQuery, terms: tuple[ContinuationTerm, ...]) -> object:
    coordinate = ContinuationCoordinate(tuple(range(len(terms))))
    return replace(node, paging=Paging(seek=ValidatedSeek(terms, coordinate)))


def test_a_seek_over_more_terms_than_the_page_orders_by_is_refused_by_count() -> None:
    # The seek and the ordering clause are two halves of ONE Continuation Order,
    # aligned positionally. A width they do not share means the page was composed
    # against a different order than it is lowered under, and lowering it anyway
    # would seek past comparisons the statement never evaluated.
    plan = _planned(ORDERS, "Order")
    node = plan.after(ContinuationCoordinate((1,)), limit=2)
    key = node.order_by[0]
    crossed = _crossed(
        node,
        (
            ContinuationTerm(key.member.identity, "asc", "last", False),
            ContinuationTerm(key.member.identity, "asc", "last", False),
        ),
    )
    with pytest.raises(SqlGenError, match="cannot be lowered against 1 ordering term"):
        _lowered(ORDERS, crossed)  # pyright: ignore[reportArgumentType] - a deliberately crossed node


def test_a_seek_naming_another_member_at_a_position_is_refused_by_name() -> None:
    # The same disagreement one width down: matching counts still leave the two
    # halves able to name different members at the same depth, which the page
    # would then compare in one member's ordering against another's coordinate.
    plan = _planned(ORDERS, "Order")
    node = plan.after(ContinuationCoordinate((1,)), limit=2)
    other = entity_of(ORDERS, "Order").attribute("name")
    assert other is not None
    crossed = _crossed(node, (ContinuationTerm(other.identity, "asc", "last", False),))
    with pytest.raises(SqlGenError, match="'name' is not the ordering term 'id'"):
        _lowered(ORDERS, crossed)  # pyright: ignore[reportArgumentType] - a deliberately crossed node


def test_a_coordinate_the_ordering_placed_last_admits_no_root() -> None:
    # Nothing follows a coordinate the emitted clause itself placed last, so every
    # branch of the tree is vacuous. The page is still an ordinary statement — it
    # runs, returns no root, and the delivery exhausts on the short page — rather
    # than a refusal or a statement the loop skips.
    plan = _planned(ORDERS, "Order", OrderKey(attr=_ORDER_NAME))
    node = plan.after(ContinuationCoordinate((None, None)), limit=2)
    statement = _lowered(ORDERS, node)
    assert statement.sql.endswith("where 1 = 0 order by t0.name asc, t0.id asc limit ?")
    assert statement.binds == (2,)


def test_the_appended_key_still_captures_a_cell_of_its_own() -> None:
    # A projected cell is never reused as a coordinate even where it would be
    # identical: `t0.id` is projected AND captured, because proving one cell is
    # both the same expression and the same carrier as the ordering term holds
    # for too thin a slice to be worth being wrong about.
    compiled = compile_entity_query(
        deep_fetch.plan(
            _planned(ORDERS, "Order").first(limit=2), ORDERS, projection=_PROJECTION
        ).root,
        ORDERS,
        POSTGRES,
    )
    assert compiled.coordinate_reads == ("parallax_seek_0",)
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on, "
        "t0.id parallax_seek_0 from orders t0"
    )
