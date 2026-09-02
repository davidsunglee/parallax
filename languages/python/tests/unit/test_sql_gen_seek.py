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
from typing import Final

import pytest
from _corpus_model_support import formed
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target as entity_of

from parallax.core import continuation, deep_fetch
from parallax.core.base import INFINITY, INFINITY_LITERAL, PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.metamodel import TemporalDimension as AxisKind
from parallax.core.object_query import AsOf, OrderKey, object_query, validate_object_query
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
from parallax.core.sql_gen._seek import lowered_terms
from parallax.descriptor import _records

DOCUMENT_LAYOUT = accepted_model("document-layout")
ORDERS = accepted_model("orders")
POSITIONS = accepted_model("position")

_TRAVELER_JOINED = "parallax.compatibility.Traveler.joinedOn"
_ORDER_NAME = "parallax.compatibility.Order.name"
_POSITION_VALID_END = "parallax.compatibility.Position.validEnd"
_ORDER_ACTIVE = "parallax.compatibility.Order.active"

_PROJECTION = deep_fetch.ReadProjectionRequest("none", False)


def _planned(model: Metamodel, target: str, *keys: OrderKey) -> continuation.ContinuationPlan:
    entity = entity_of(model, target)
    query = object_query(
        entity.identity,
        All(),
        order_by=keys,
        temporal={
            "valid-time" if axis.dimension is AxisKind.VALID_TIME else "transaction-time": AsOf(
                "latest"
            )
            for axis in entity.declared_as_of_axes
        },
    )
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
        "or (jsonb_extract_path_text(t0.payload, ?) = ? and (t0.id > ? or t0.id is null))) "
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
    with pytest.raises(SqlGenError, match=r"the seek's term 'name' .* the ordering term 'id'"):
        _lowered(ORDERS, crossed)  # pyright: ignore[reportArgumentType] - a deliberately crossed node


def test_a_seek_agreeing_on_the_member_but_not_its_ordering_is_refused() -> None:
    # Identity is not the whole term. The order clause reads direction, Null
    # Placement, and nullability off the query while every branch of the seek
    # reads them off the portable term, so a pair agreeing only on the member
    # would emit `t0.id > ?` under a clause that ordered descending — a seek
    # running back over roots the delivery had already published.
    plan = _planned(ORDERS, "Order")
    node = plan.after(ContinuationCoordinate((1,)), limit=2)
    key = node.order_by[0]
    crossed = _crossed(node, (ContinuationTerm(key.member.identity, "desc", "last", False),))
    with pytest.raises(SqlGenError, match=r"'id' \(desc, .*'id' \(asc, "):
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


def test_a_coordinate_carried_at_another_width_than_the_order_is_refused() -> None:
    # The seek's terms and its coordinate are two halves of one value, and the
    # branch tree indexes the carriers by the term's own depth. A coordinate
    # narrower than the order would raise at that subscript instead of naming
    # the disagreement, and a wider one would seek past a term the page never
    # ordered by.
    plan = _planned(ORDERS, "Order")
    node = plan.after(ContinuationCoordinate((1,)), limit=2)
    key = node.order_by[0]
    crossed = replace(
        node,
        paging=Paging(
            seek=ValidatedSeek(
                (ContinuationTerm(key.member.identity, "asc", "last", False),),
                ContinuationCoordinate((1, 2)),
            )
        ),
    )
    with pytest.raises(SqlGenError, match="carrying 2 value"):
        _lowered(ORDERS, crossed)


def test_an_open_temporal_bound_carrier_reports_the_canonical_infinity_literal() -> None:
    # `validEnd` is an ordinary Attribute a Sort Key may name, and the open upper
    # bound of a live interval reads back through the port as the `m-core`
    # sentinel rather than as an instant. It is a member of no declared value
    # space, so it crosses as a framework bind whose reported form is the
    # canonical `infinity` literal — the same treatment a written temporal row
    # already takes — instead of being re-encoded as a `timestamp`.
    plan = _planned(POSITIONS, "Position", OrderKey(attr=_POSITION_VALID_END))
    node = plan.after(ContinuationCoordinate((INFINITY, 1)), limit=2)
    statement = _lowered(POSITIONS, node)
    assert statement.sql.endswith(
        "where t0.thru_z = ? and t0.out_z = ? and t0.thru_z >= ? "
        "and (t0.thru_z > ? or t0.thru_z is null "
        "or (t0.thru_z = ? and (t0.pos_id > ? or t0.pos_id is null))) "
        "order by t0.thru_z asc, t0.pos_id asc limit ?"
    )
    assert statement.binds[2:5] == (INFINITY, INFINITY, INFINITY)
    assert statement.wire_binds()[2:5] == (INFINITY_LITERAL,) * 3


def test_a_capture_alias_an_authored_column_already_spells_is_allocated_past() -> None:
    # Two cells under one result key collapse into one driver-row entry, and
    # lifting the coordinate off would then take the authored member's value or
    # delete the member outright. Allocation therefore skips every spelling the
    # model's own Columns reserve, exactly as a wrapped union's result aliases
    # are allocated (`m-sql`).
    order = _planned(ORDERS, "Order").first(limit=2).order_by
    assert lowered_terms(order, {"parallax_seek_0", "parallax_seek_2"})[0].alias == (
        "parallax_seek_1"
    )
    assert [term.alias for term in lowered_terms((*order, *order), {"parallax_seek_1"})] == [
        "parallax_seek_0",
        "parallax_seek_2",
    ]


def test_a_non_nullable_terms_branch_follows_the_emitted_placement_not_the_declaration() -> None:
    # Two terms the model declares equally non-nullable, differing only in the
    # placement their own direction gives them under this dialect: Postgres
    # trails NULLs on `asc` and leads them on `desc`. The ascending term's branch
    # therefore admits its NULLs and the descending one's does not — which is the
    # rule a delivery over storage that lost a `NOT NULL` constraint depends on,
    # since such a NULL is ranked by the clause whatever the declaration says.
    ascending = _lowered(
        ORDERS,
        _planned(ORDERS, "Order", OrderKey(attr=_ORDER_ACTIVE)).after(
            ContinuationCoordinate((True, 1)), limit=2
        ),
    )
    descending = _lowered(
        ORDERS,
        _planned(ORDERS, "Order", OrderKey(attr=_ORDER_ACTIVE, direction="desc")).after(
            ContinuationCoordinate((True, 1)), limit=2
        ),
    )
    assert "t0.active > ? or t0.active is null" in ascending.sql
    assert "t0.active < ? or t0.active is null" not in descending.sql
    assert "t0.active < ?" in descending.sql


def test_the_hoisted_leading_range_re_excludes_the_null_its_own_branch_admits() -> None:
    # The one deliberate exception, graded so removing it is a decision rather
    # than an edit. The leading term is declared non-nullable, so the page hoists
    # `t0.active >= ?` for the planner; the branch beneath it still admits the
    # NULLs the emitted clause placed after the coordinate, and the hoist then
    # excludes them again. A stored NULL in that column is therefore skipped —
    # the price `m-snapshot-read` *Streamed delivery* records for the leading
    # index range.
    statement = _lowered(
        ORDERS,
        _planned(ORDERS, "Order", OrderKey(attr=_ORDER_ACTIVE)).after(
            ContinuationCoordinate((True, 1)), limit=2
        ),
    )
    seek = statement.sql.partition(" where ")[2].partition(" order by ")[0]
    assert seek.startswith("t0.active >= ? and (t0.active > ? or t0.active is null or ")


_RESIDENT_KEY: Final = _records.Metamodel(
    entities=(
        _records.Entity(
            name="Beacon",
            table="beacon",
            layout=_records.DocumentLayout(column="payload"),
            attributes=(
                _records.Attribute(name="id", type="int64", column="id", primary_key=True),
                _records.Attribute(name="rank", type="int64", column="rank"),
            ),
        ),
    )
)

_SEEK_SPELLED_MEMBER: Final = _records.Metamodel(
    entities=(
        _records.Entity(
            name="Beacon",
            table="beacon",
            layout=_records.DocumentLayout(column="payload"),
            attributes=(
                _records.Attribute(name="id", type="int64", column="id", primary_key=True),
                _records.Attribute(
                    name="parallax_seek_0", type="int64", column="parallax_seek_0", nullable=True
                ),
            ),
        ),
    )
)


def test_a_document_resident_leading_term_hoists_no_range() -> None:
    # `rank` is declared non-nullable and lives at a Document Path, so its
    # extraction reads NULL for a missing member, a JSON null, or a wrong-kind
    # parent — invalid stored data `m-snapshot-read` guarantees a checked
    # delivery publishes, not the dropped `NOT NULL` constraint the hoist's
    # accepted skip is scoped to. The seek is therefore the branch tree alone,
    # which admits the NULLs Postgres ranked after this ascending coordinate.
    model = formed(_RESIDENT_KEY)
    statement = _lowered(
        model,
        _planned(model, "Beacon", OrderKey(attr="Beacon.rank")).after(
            ContinuationCoordinate((7, 1)), limit=2
        ),
    )
    seek = statement.sql.partition(" where ")[2].partition(" order by ")[0]
    assert seek == (
        "(cast(jsonb_extract_path_text(t0.payload, ?) as bigint) > ? "
        "or jsonb_extract_path_text(t0.payload, ?) is null "
        "or (cast(jsonb_extract_path_text(t0.payload, ?) as bigint) = ? "
        "and (t0.id > ? or t0.id is null)))"
    )


def test_a_capture_alias_a_resident_member_spelling_claims_is_allocated_past() -> None:
    # A document-resident member claims no Column, so its own spelling reaches
    # the row only through the fan-out — which writes it AFTER the driver row
    # arrives. An alias colliding with it would be overwritten by the decoded
    # member before the coordinate is lifted off, taking the ordering
    # expression's answer with it and deleting the member. The reservation set
    # therefore covers every result key an authored name reaches, not the
    # Column spellings alone.
    model = formed(_SEEK_SPELLED_MEMBER)
    compiled = compile_entity_query(
        deep_fetch.plan(
            _planned(model, "Beacon", OrderKey(attr="Beacon.parallax_seek_0")).first(limit=2),
            model,
            projection=_PROJECTION,
        ).root,
        model,
        POSTGRES,
    )
    assert compiled.coordinate_reads == ("parallax_seek_1", "parallax_seek_2")
    row = compiled.materialize_row(
        {
            "id": 1,
            "payload": PresentDocument({"parallax_seek_0": 3}),
            "parallax_seek_1": 3,
            "parallax_seek_2": 1,
        }
    )
    assert row.values["parallax_seek_0"] == 3
    assert row.coordinate == ContinuationCoordinate((3, 1))
