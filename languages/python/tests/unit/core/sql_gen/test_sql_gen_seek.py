"""The m-sql half of continuation: capture cells, carrier binds, and page templates.

`test_continuation.py` grades the branch tree a Continuation Order composes,
whole clause by whole clause, because the page statement is a cross-language
golden. What is graded here is what only this side can answer: the FORM a
carrier crosses the bind seam in, the capture cells and their aliases, the
statement shapes a continuing page takes under a lock or a null tail, and the
templates a page renders from.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Final

import pytest

from parallax.core import UnsupportedError
from parallax.core.internal import continuation, read_planning
from parallax.core.internal.base import (
    INFINITY,
    INFINITY_LITERAL,
    InternalError,
    StructuredDocument,
    UsageError,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.metamodel import TemporalDimension as AxisKind
from parallax.core.internal.object_query import AsOf, OrderKey, object_query, validate_object_query
from parallax.core.internal.object_query._resolved import (
    ContinuationCoordinate,
    ResolvedObjectQuery,
)
from parallax.core.internal.predicate import Comparison, FieldSubject, Or, PredicateNode, TrueNode
from parallax.core.internal.read_delivery._row_decoding import row_coordinates
from parallax.core.internal.sql_gen._context import SQL_GENERATION_FAILED, LoweredStatement
from parallax.core.internal.sql_gen._inheritance import (
    INHERITANCE_LOCKING_READ_UNSUPPORTED,
    SingleTableReadPlan,
    TpcsUnionReadPlan,
)
from parallax.core.internal.sql_gen._planning import SharedSourceRef
from parallax.descriptor import _records
from tests._support.errors import raises_code
from tests._support.sql import compile_nonempty_read as compile_entity_query
from tests._support.sql import compile_nonempty_template as compile_template
from tests.unit import _read_projection_support as projection_support
from tests.unit._corpus_model_support import formed
from tests.unit._corpus_model_support import model as accepted_model
from tests.unit._corpus_model_support import target as entity_of
from tests.unit._prepared_read_support import result_row
from tests.unit.core.sql_gen._delivery_support import deliver
from tests.unit.core.sql_gen._plan_reuse_support import (
    assert_planned_once,
    reaches_compilation_state,
    record_plan_reuse,
)

DOCUMENT_LAYOUT = accepted_model("document-layout")
ORDERS = accepted_model("orders")
PAYMENT = accepted_model("payment")
POSITIONS = accepted_model("position")
TRAVERSAL = accepted_model("predicate-traversal")

_TRAVELER_JOINED = "parallax.compatibility.Traveler.joinedOn"
_ORDER_NAME = "parallax.compatibility.Order.name"
_ORDER_SKU = "parallax.compatibility.Order.sku"
_POSITION_VALID_END = "parallax.compatibility.Position.validEnd"
_ORDER_ACTIVE = "parallax.compatibility.Order.active"

_PROJECTION = read_planning.ReadProjectionRequest("none", False)


def _planned(model: Metamodel, target: str, *keys: OrderKey) -> continuation.ContinuationPlan:
    entity = entity_of(model, target)
    query = object_query(
        entity.identity,
        TrueNode(),
        order_by=keys,
        temporal={
            "valid-time" if axis.dimension is AxisKind.VALID_TIME else "transaction-time": AsOf(
                "latest"
            )
            for axis in entity.declared_as_of_axes
        },
    )
    return continuation.plan(validate_object_query(entity, query, model), model)


def _lowered(
    model: Metamodel,
    node: ResolvedObjectQuery,
    *,
    shared_lock: bool = False,
    dialect: Dialect = POSTGRES,
) -> LoweredStatement:
    return compile_entity_query(
        read_planning.plan(node, model, projection=_PROJECTION).root,
        model,
        dialect,
        shared_lock=shared_lock,
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
        read_planning.plan(
            _planned(ORDERS, "Order").first(limit=2), ORDERS, projection=_PROJECTION
        ).root,
        ORDERS,
        POSTGRES,
    )
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on, "
        "t0.id parallax_seek_0 from orders t0"
    )
    assert compiled.result_contract.coordinate_ordinals == (7,)
    (row,) = deliver(
        ORDERS,
        compiled,
        [
            {
                "id": 1,
                "name": "Ada",
                "sku": None,
                "qty": 2,
                "price": Decimal("1.50"),
                "active": True,
                "ordered_on": None,
                "parallax_seek_0": 1,
            }
        ],
    )
    assert list(row.members) == ["id", "name", "sku", "qty", "price", "active", "orderedOn"]


def test_an_open_temporal_bound_carrier_reports_the_canonical_infinity_literal() -> None:
    # `validEnd` is an ordinary Attribute a Sort Key may name, and the open upper
    # bound of a live interval reads back through the port as the `m-core`
    # sentinel rather than as an instant. It is a member of no declared value
    # space, so it crosses as a framework bind whose reported form is the
    # canonical `infinity` literal — the same treatment a written temporal row
    # already takes — instead of being re-encoded as a `timestamp`. The Latest
    # terms ahead of the seek bind the same managed sentinel.
    plan = _planned(POSITIONS, "Position", OrderKey(attr=_POSITION_VALID_END))
    node = plan.after(ContinuationCoordinate((INFINITY, 1)), limit=2)
    statement = _lowered(POSITIONS, node)
    assert statement.sql.startswith("select u.")
    assert (
        "where t0.thru_z = ? and t0.out_z = ? and t0.thru_z >= ? "
        "and (t0.thru_z > ? or t0.thru_z is null "
        "or (t0.thru_z = ? and (t0.pos_id > ? or t0.pos_id is null))) "
        "order by t0.thru_z asc, t0.pos_id asc limit ?"
    ) in statement.sql
    assert ") union all (select " in statement.sql
    assert "where t0.thru_z = ? and t0.out_z = ? and t0.thru_z is null" in statement.sql
    assert statement.sql.endswith("order by u.parallax_seek_0 asc, u.parallax_seek_1 asc limit ?")
    assert statement.binds[:5] == (INFINITY,) * 5
    assert statement.wire_binds()[:5] == (INFINITY_LITERAL,) * 5
    typed = {index for span in statement.typed_bind_spans for index in span.indices()}
    assert typed.isdisjoint(range(5))


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


def test_the_hoisted_leading_range_keeps_its_null_tail_in_a_second_branch() -> None:
    # The range branch stays seekable without omitting a NULL the emitted order put
    # after the coordinate: the disjoint second branch admits the whole NULL tail,
    # and the outer order and cap merge the two into one continuing page.
    statement = _lowered(
        ORDERS,
        _planned(ORDERS, "Order", OrderKey(attr=_ORDER_ACTIVE)).after(
            ContinuationCoordinate((True, 1)), limit=2
        ),
    )
    assert "where t0.active >= ? and (t0.active > ? or t0.active is null or " in statement.sql
    assert ") union all (select " in statement.sql
    assert "where t0.active is null order by t0.active asc, t0.id asc limit ?" in statement.sql
    assert statement.sql.endswith("order by u.parallax_seek_0 asc, u.parallax_seek_1 asc limit ?")


def test_a_single_term_continuation_order_hoists_its_direct_range() -> None:
    statement = _lowered(
        ORDERS,
        _planned(ORDERS, "Order").after(ContinuationCoordinate((1,)), limit=2),
    )

    assert "where t0.id >= ? and (t0.id > ? or t0.id is null)" in statement.sql
    assert ") union all (select " in statement.sql
    assert "where t0.id is null order by t0.id asc limit ?" in statement.sql
    assert statement.binds == (1, 1, 2, 2, 2)


def test_a_null_tail_wrapper_preserves_structured_document_presence() -> None:
    # Compatibility case: a continuing Document-layout read wraps two NULL-tail
    # branches; the outer projection must reproduce the presence boolean immediately
    # before the document so adapter folding observes the first page's ordinals
    # and payload, rather than mistaking the document itself for its presence flag.
    plan = _planned(DOCUMENT_LAYOUT, "Charter")
    node = plan.after(ContinuationCoordinate((1,)), limit=2)
    compiled = compile_entity_query(
        read_planning.plan(
            node,
            DOCUMENT_LAYOUT,
            projection=read_planning.ReadProjectionRequest("all", True),
        ).root,
        DOCUMENT_LAYOUT,
        POSTGRES,
        result_form="instance",
    )

    assert "select u.id, u.from_z, u.thru_z, u.in_z, u.out_z, not u.payload is null, u.payload" in (
        compiled.statement.sql
    )
    assert compiled.document_reads == ((5, 6),)


def test_a_postgres_locking_continuation_joins_the_ordinary_physical_identity() -> None:
    # A participating ordinary stream that reaches page two keeps one SQL statement
    # and one pessimistic authority boundary: neither union branch carries an illegal
    # lock, while the outer query joins the complete one-column physical identity
    # back to the base row, whose protected state supplies the returned payload.
    statement = _lowered(
        ORDERS,
        _planned(ORDERS, "Order").after(ContinuationCoordinate((1,)), limit=2),
        shared_lock=True,
    )

    assert statement.sql.count("for share") == 1
    assert (
        ")) u join orders t0 on u.id = t0.id order by t0.id asc limit ? for share of t0"
    ) in statement.sql
    assert statement.binds == (1, 1, 2, 2, 2)


def test_seek_null_tail_shared_lock_uses_the_dialects_placement() -> None:
    node = _planned(ORDERS, "Order").after(ContinuationCoordinate((1,)), limit=2)
    postgres = _lowered(ORDERS, node, shared_lock=True)
    mariadb = _lowered(ORDERS, node, shared_lock=True, dialect=_MARIADB)

    assert postgres.sql.count("for share of t0") == 1
    assert ")) u join orders t0" in postgres.sql
    assert mariadb.sql.count("for share of t0") == 2
    assert ")) u join orders t0" not in mariadb.sql
    assert mariadb.sql.endswith("order by u.parallax_seek_0 asc limit ?")


def test_a_postgres_locking_continuation_joins_the_inheritance_physical_identity() -> None:
    # A concrete TPH stream repeats its tag bind inside each disjoint continuation
    # branch, then joins the shared table by its family-owned physical key before the
    # outer cap and lock; this distinguishes inheritance predicate binds from both
    # seek binds and the cap while preserving their textual order.
    statement = _lowered(
        PAYMENT,
        _planned(PAYMENT, "CardPayment").after(ContinuationCoordinate((1,)), limit=2),
        shared_lock=True,
    )

    assert statement.sql.count("for share") == 1
    assert ")) u join payment t0 on u.id = t0.id order by t0.id asc" in statement.sql
    assert statement.binds == (1, 1, "card", 2, "card", 2, 2)


def test_a_postgres_locking_continuation_refuses_multiple_concrete_tables() -> None:
    page = _planned(
        TRAVERSAL, "Vehicle", OrderKey(attr="parallax.compatibility.Vehicle.dealerId")
    ).after(ContinuationCoordinate((3, 1)), limit=2)
    with raises_code(UnsupportedError, INHERITANCE_LOCKING_READ_UNSUPPORTED):
        _lowered(TRAVERSAL, page, shared_lock=True)


@pytest.mark.parametrize("target", ["Vehicle", "Car"])
def test_a_postgres_locking_single_concrete_continuation_keeps_its_result_contract(
    target: str,
) -> None:
    entity = entity_of(TRAVERSAL, target)
    car = entity_of(TRAVERSAL, "Car").identity
    query = object_query(
        entity.identity,
        TrueNode(),
        narrow_to=(car.canonical,) if target == "Vehicle" else None,
        order_by=(OrderKey(attr="parallax.compatibility.Vehicle.dealerId"),),
    )
    node = continuation.plan(validate_object_query(entity, query, TRAVERSAL), TRAVERSAL).after(
        ContinuationCoordinate((3, 1)), limit=2
    )
    planned = read_planning.plan(node, TRAVERSAL, projection=_PROJECTION).root
    compiled = compile_entity_query(planned, TRAVERSAL, POSTGRES, shared_lock=True)
    unlocked = compile_entity_query(planned, TRAVERSAL, POSTGRES)
    statement = compiled.statement
    branch = (
        "select t0.id, t0.maker, t0.dealer_id, t0.seats, "
        "t0.dealer_id parallax_seek_0, t0.id parallax_seek_1 from traversal_car t0 where "
    )
    assert statement.sql == (
        "select t0.id, t0.maker, t0.dealer_id, t0.seats, "
        "t0.dealer_id parallax_seek_0, t0.id parallax_seek_1 "
        f"from (({branch}t0.dealer_id >= ? and (t0.dealer_id > ? or t0.dealer_id is null "
        "or (t0.dealer_id = ? and (t0.id > ? or t0.id is null))) "
        "order by t0.dealer_id asc, t0.id asc limit ?) union all ("
        f"{branch}t0.dealer_id is null order by t0.dealer_id asc, t0.id asc limit ?)) "
        "u join traversal_car t0 on u.id = t0.id "
        "order by t0.dealer_id asc, t0.id asc limit ? for share of t0"
    )
    assert statement.sql.count("for share") == 1
    assert statement.binds == (3, 3, 3, 1, 2, 2, 2)
    assert compiled.result_contract == unlocked.result_contract
    assert compiled.resolved_position == (car,)
    assert compiled.result_contract.coordinate_ordinals == (4, 5)
    cells = {
        "id": 7,
        "maker": "Ada",
        "dealer_id": None,
        "seats": 4,
        "parallax_seek_0": None,
        "parallax_seek_1": 7,
    }
    (delivered,) = deliver(TRAVERSAL, compiled, [cells])
    assert delivered.members == {"id": 7, "maker": "Ada", "dealerId": None, "seats": 4}
    assert row_coordinates(compiled.result_contract, (result_row(compiled, cells),)) == (
        ContinuationCoordinate((None, 7)),
    )


def test_a_postgres_locking_history_joins_every_temporal_identity_column() -> None:
    # A history stream's physical row identity is wider than its logical key:
    # both temporal upper edges participate in the primary key, so the outer join
    # names all three components and cannot multiply milestones or lock a sibling
    # milestone while the branch and outer cap binds retain their established order.
    statement = _lowered(
        POSITIONS,
        _planned(POSITIONS, "Position", OrderKey(attr=_POSITION_VALID_END)).after(
            ContinuationCoordinate((INFINITY, 1)), limit=2
        ),
        shared_lock=True,
    )

    assert statement.sql.count("for share") == 1
    assert (
        ")) u join position t0 on u.pos_id = t0.pos_id and u.thru_z = t0.thru_z "
        "and u.out_z = t0.out_z order by t0.thru_z asc, "
        "t0.pos_id asc limit ? for share of t0"
    ) in statement.sql
    assert statement.binds == (
        INFINITY,
        INFINITY,
        INFINITY,
        INFINITY,
        INFINITY,
        1,
        2,
        INFINITY,
        INFINITY,
        2,
        2,
    )
    assert statement.wire_binds() == (
        *(INFINITY_LITERAL,) * 5,
        1,
        2,
        *(INFINITY_LITERAL,) * 2,
        2,
        2,
    )


_MATRIX_ROOT = projection_support.matrix_entity("tph", "columns", "Root")
_MATRIX_HOLDER = "read.projection.matrix.tph.columns.Root.holderId"
# Spelled by the wrapper's own select list; each branch's capture cells repeat the
# ordering members, which the structural fake reads through the first branch.
_NULL_TAIL_ROWS: tuple[dict[str, object], ...] = (
    {
        "id": 2,
        "kind": "plain",
        "holder_id": 12,
        "digest_hex": None,
        "note": "memo",
        "tags": ["a"],
        "origin": {"city": "Bern"},
    },
    {"id": 3, "kind": "right", "digest_hex": "ff", "right_home": {"city": "Oslo"}},
    {"id": 7, "kind": "ghost", "digest_hex": "00"},
)


def _null_tail_delivery(instance: bool) -> list[tuple[object, ...]]:
    """(Entity, members, issues) for every row."""
    return [
        (
            "Plain",
            {
                "id": 2,
                "holderId": 12,
                "digest": None,
                "note": "memo",
                "tags": ("a",),
                **({"origin": {"city": "Bern"}} if instance else {}),
            },
            (),
        ),
        (
            "Right",
            {
                "id": 3,
                "holderId": None,
                "digest": b"\xff",
                **({"origin": None, "home": {"city": "Oslo"}} if instance else {}),
            },
            (),
        ),
        (
            # An unclaimed tag resolves to the family root, which reads its
            # encoded Column by storage spelling and so carries none.
            "Root",
            {"id": 7, "holderId": None, **({"origin": None} if instance else {})},
            (("stored-data-family-tag-unknown", "ghost"),),
        ),
    ]


@pytest.mark.parametrize("instance", [False, True], ids=["row", "instance"])
@pytest.mark.parametrize("shared_lock", [False, True])
def test_a_null_tail_wrapper_delivers_its_rows_with_or_without_the_base_row_lock(
    shared_lock: bool, instance: bool
) -> None:
    plan = continuation.plan(
        validate_object_query(
            _MATRIX_ROOT,
            object_query(
                _MATRIX_ROOT.identity, TrueNode(), order_by=(OrderKey(attr=_MATRIX_HOLDER),)
            ),
            projection_support.MATRIX_META,
        ),
        projection_support.MATRIX_META,
    )
    compiled = compile_entity_query(
        read_planning.plan(
            plan.after(ContinuationCoordinate((10, 1)), limit=3),
            projection_support.MATRIX_META,
            projection=read_planning.ReadProjectionRequest("all" if instance else "none", False),
        ).root,
        projection_support.MATRIX_META,
        POSTGRES,
        shared_lock=shared_lock,
        result_form="instance" if instance else "row",
    )
    alias = "t0" if shared_lock else "u"
    occurrences = (
        f", not {alias}.origin is null, {alias}.origin, not {alias}.home is null, {alias}.home, "
        f"not {alias}.right_home is null, {alias}.right_home"
        if instance
        else ""
    )
    digest = "encode(t0.digest, ?) digest_hex" if shared_lock else "u.digest_hex"
    coordinates = (
        "t0.holder_id parallax_seek_0, t0.id parallax_seek_1"
        if shared_lock
        else "u.parallax_seek_0, u.parallax_seek_1"
    )
    assert compiled.statement.sql.startswith(
        f"select {alias}.id, {alias}.kind, {alias}.holder_id, {digest}, {alias}.note, "
        f"not {alias}.tags is null, {alias}.tags{occurrences}, {coordinates} from ((select "
    )
    assert compiled.statement.sql.endswith(
        (") u join mx_tph_columns t0 on u.id = t0.id" if shared_lock else ") u")
        + (
            " order by t0.holder_id asc, t0.id asc limit ?"
            if shared_lock
            else " order by u.parallax_seek_0 asc, u.parallax_seek_1 asc limit ?"
        )
        + (" for share of t0" if shared_lock else "")
    )
    assert compiled.statement.binds == (
        *(("hex",) if shared_lock else ()),
        "hex",
        10,
        10,
        10,
        1,
        3,
        "hex",
        3,
        3,
    )
    assert compiled.document_reads == (
        ((5, 6), (7, 8), (9, 10), (11, 12)) if instance else ((5, 6),)
    )

    rows = [
        {
            key: value
            for key, value in row.items()
            if instance or key not in {"origin", "home", "right_home"}
        }
        for row in _NULL_TAIL_ROWS
    ]
    delivered = deliver(projection_support.MATRIX_META, compiled, rows)

    assert [(row.entity, row.members, row.issues) for row in delivered] == (
        _null_tail_delivery(instance)
    )


def test_a_nullable_direct_leading_term_uses_the_same_seekable_two_branch_shape() -> None:
    statement = _lowered(
        ORDERS,
        _planned(ORDERS, "Order", OrderKey(attr=_ORDER_SKU, nulls="last")).after(
            ContinuationCoordinate(("A-100", 1)), limit=2
        ),
    )

    assert "where t0.sku >= ? and (t0.sku > ? or t0.sku is null or " in statement.sql
    assert "where t0.sku is null order by t0.sku asc, t0.id asc limit ?" in statement.sql
    assert statement.sql.endswith("order by u.parallax_seek_0 asc, u.parallax_seek_1 asc limit ?")


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
    # A document-resident member claims no Column, so no projected Column
    # reserves its spelling. An alias colliding with it would make one result key
    # name both the member and the ordering expression's answer, and publication
    # lifting the coordinate off would take the member with it. The reservation
    # set therefore covers every result key an authored name reaches, not the
    # Column spellings alone.
    model = formed(_SEEK_SPELLED_MEMBER)
    compiled = compile_entity_query(
        read_planning.plan(
            _planned(model, "Beacon", OrderKey(attr="Beacon.parallax_seek_0")).first(limit=2),
            model,
            projection=_PROJECTION,
        ).root,
        model,
        POSTGRES,
    )
    cells = {
        "id": 1,
        "payload": StructuredDocument({"parallax_seek_0": 3}),
        "parallax_seek_1": 3,
        "parallax_seek_2": 1,
    }
    (delivered,) = deliver(model, compiled, [cells])
    assert delivered.members == {"id": 1, "parallax_seek_0": 3}
    row = result_row(compiled, cells)
    assert row_coordinates(compiled.result_contract, (row,)) == (ContinuationCoordinate((3, 1)),)


def test_a_corrupt_text_compared_carrier_still_reports_the_text_it_crossed_as() -> None:
    # The reported form of a coordinate bind is the form it was BOUND in, which
    # is what makes a delivery past storage the model contradicts reportable at
    # all: `joinedOn` compares as extracted text, so a stored spelling no `date`
    # decoding admits crosses and reports as those same characters. A compatibility
    # case corrupting a member the Continuation Order names authors its pages from
    # exactly this (`m-case-format` *Corrupting stored state*).
    plan = _planned(DOCUMENT_LAYOUT, "Traveler", OrderKey(attr=_TRAVELER_JOINED))
    node = plan.after(ContinuationCoordinate(("0000-13-99", 1)), limit=2)
    statement = _lowered(DOCUMENT_LAYOUT, node)
    assert statement.wire_binds()[2] == "0000-13-99"


def test_a_direct_column_carrier_outside_its_declared_type_has_no_reported_form() -> None:
    # The one shape the rule above does not cover, and the reason it does not
    # need to: a direct Column binds its carrier as a managed value, and canonical
    # Wire has no spelling for a value the declared type admits no member of.
    # Conforming DDL cannot store one — the Column's own type refuses it — so no
    # corpus case can author this, and the statement itself still lowers.
    plan = _planned(ORDERS, "Order", OrderKey(attr=_ORDER_NAME))
    node = plan.after(ContinuationCoordinate((object(), 1)), limit=2)
    statement = _lowered(ORDERS, node)
    with raises_code(UsageError, "wire-encoding-failed"):
        statement.wire_binds()


def test_each_continuing_branch_joins_its_own_shared_sources_beneath_the_root_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Both branches of a nullable leading term's continuing page select from their own
    # statement, so each joins the shared order itself, binds the predicate where
    # its own text puts it, and leaves the shared lock to the reattached base row.
    # They render the read's one physical and statement plans, each through its
    # own builder, into one result contract and one compiled read, which
    # retains no statement plan or builder.
    entity = entity_of(ORDERS, "OrderItem")
    query = object_query(
        entity.identity,
        Comparison(op="eq", subject=FieldSubject("OrderItem.order.name"), value="Ada"),
        order_by=(OrderKey(attr="parallax.compatibility.OrderItem.shippedOn"),),
    )
    node = continuation.plan(validate_object_query(entity, query, ORDERS), ORDERS).after(
        ContinuationCoordinate((dt.date(2024, 2, 15), 11)), limit=2
    )
    reuse = record_plan_reuse(monkeypatch)
    compiled = compile_entity_query(
        read_planning.plan(node, ORDERS, projection=_PROJECTION).root,
        ORDERS,
        POSTGRES,
        shared_lock=True,
    )
    statement = compiled.statement
    joined = "from order_item t0 left join orders t1 on t1.id = t0.order_id where t1.name = ? and "
    assert statement.sql.count(joined) == 2
    assert f"{joined}t0.shipped_on is null order by" in statement.sql
    assert statement.sql.endswith(
        ") u join order_item t0 on u.id = t0.id "
        "order by t0.shipped_on asc, t0.id asc limit ? for share of t0"
    )
    february = dt.date(2024, 2, 15)
    assert statement.binds == ("Ada", february, february, february, 11, 2, "Ada", 2, 2)

    (plan,) = reuse.plans
    assert isinstance(assert_planned_once(reuse), SingleTableReadPlan)
    ordinary, null_tail = reuse.roots
    assert ordinary.statement_plan is plan and null_tail.statement_plan is plan
    assert ordinary.scope_id == null_tail.scope_id == plan.root_scopes[None]
    assert ordinary.row.ctx is not null_tail.row.ctx
    source = SharedSourceRef(plan.root_scopes[None], 0)
    bindings = [root.row.ctx.source_binding(source) for root in reuse.roots]
    assert [binding.origin for binding in bindings] == [root.row for root in reuse.roots]
    assert bindings[0].target is not bindings[1].target
    assert all(binding.target.alias == "t1" for binding in bindings)
    assert reaches_compilation_state(ordinary.row)
    assert not reaches_compilation_state(compiled)


def test_both_continuing_branches_of_a_family_page_keep_the_tag_guard_after_the_grouped_seek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A concrete table-per-hierarchy page renders each branch through the one
    # single-table renderer: the caller's disjunction stays grouped, the seek
    # (or the NULL tail) follows it, and the framework tag guard binds last
    # before each branch's own cap; the outer union caps once more.
    entity = entity_of(PAYMENT, "CardPayment")
    query = object_query(
        entity.identity,
        Or(
            operands=(
                Comparison(op="eq", subject=FieldSubject("CardPayment.id"), value=3),
                Comparison(op="eq", subject=FieldSubject("CardPayment.id"), value=5),
            )
        ),
    )
    node = continuation.plan(validate_object_query(entity, query, PAYMENT), PAYMENT).after(
        ContinuationCoordinate((1,)), limit=2
    )
    reuse = record_plan_reuse(monkeypatch)
    statement = _lowered(PAYMENT, node)
    branch = (
        "select t0.id, t0.amount, t0.card_network, t0.id parallax_seek_0 from payment t0 where "
    )
    assert statement.sql == (
        "select u.id, u.amount, u.card_network, u.parallax_seek_0 from (("
        f"{branch}(t0.id = ? or t0.id = ?) and t0.id >= ? and (t0.id > ? or t0.id is null) "
        "and t0.kind = ? order by t0.id asc limit ?) union all ("
        f"{branch}(t0.id = ? or t0.id = ?) and t0.id is null and t0.kind = ? "
        "order by t0.id asc limit ?)) u order by u.parallax_seek_0 asc limit ?"
    )
    assert statement.binds == (3, 5, 1, 1, "card", 2, 3, 5, "card", 2, 2)
    shape = assert_planned_once(reuse)
    assert isinstance(shape, SingleTableReadPlan) and shape.tag_guard is not None
    ordinary, null_tail = reuse.roots
    assert ordinary.row.ctx is not null_tail.row.ctx


def test_both_continuing_branches_of_a_union_render_its_branch_roots_through_fresh_builders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A table-per-concrete-subtype page over a nullable direct leading term
    # renders each of its two seek branches as its own union, and every union
    # branch of either restarts its aliases at `t0`, joins the shared dealer
    # itself, and binds only its own branch root's sources; the two seek branches
    # finish one read.
    entity = entity_of(TRAVERSAL, "Vehicle")
    query = object_query(
        entity.identity,
        Comparison(op="eq", subject=FieldSubject("Vehicle.dealer.name"), value="Ada"),
        order_by=(OrderKey(attr="parallax.compatibility.Vehicle.dealerId"),),
    )
    node = continuation.plan(validate_object_query(entity, query, TRAVERSAL), TRAVERSAL).after(
        ContinuationCoordinate((3, 1)), limit=2
    )
    reuse = record_plan_reuse(monkeypatch)
    statement = _lowered(TRAVERSAL, node)
    for table in ("traversal_bike", "traversal_car"):
        branch = (
            f"from {table} t0 left join traversal_dealer t1 on t1.id = t0.dealer_id "
            "where t1.name = ?"
        )
        assert statement.sql.count(branch) == 2
    assert "u where u.dealer_id is null order by" in statement.sql
    assert statement.binds == ("Ada", "Ada", 3, 3, 3, 1, 2, "Ada", "Ada", 2, 2)

    (plan,) = reuse.plans
    assert isinstance(assert_planned_once(reuse), TpcsUnionReadPlan)
    branch_roots = tuple(plan.root_scopes.values())
    assert len(branch_roots) == 2
    assert all(root.statement_plan is plan for root in reuse.roots)
    assert [root.scope_id for root in reuse.roots] == [*branch_roots, *branch_roots]
    assert len({id(root.row.ctx) for root in reuse.roots}) == len(reuse.roots)
    for root in reuse.roots:
        builder = root.row.ctx
        assert builder.source_binding(SharedSourceRef(root.scope_id, 0)).origin is root.row


_MARIADB: Final = replace(
    POSTGRES, name="mariadb", binds_arrays=False, seek_null_tail_lock_placement="branches"
)
_ORDER_SHIPPED = "parallax.compatibility.OrderItem.shippedOn"
_ORDER_ORDERED_ON = "parallax.compatibility.Order.orderedOn"
_POSITION_VALUE = "parallax.compatibility.Position.value"


def _page_query(
    model: Metamodel, target: str, node: PredicateNode, *keys: OrderKey
) -> continuation.ContinuationPlan:
    entity = entity_of(model, target)
    query = object_query(entity.identity, node, order_by=keys)
    return continuation.plan(validate_object_query(entity, query, model), model)


def _template_pages() -> list[object]:
    def after(
        plan: continuation.ContinuationPlan, cold: tuple[object, ...], current: tuple[object, ...]
    ) -> tuple[ResolvedObjectQuery, ResolvedObjectQuery]:
        return (
            plan.after(ContinuationCoordinate(cold), limit=2),
            plan.after(ContinuationCoordinate(current), limit=5),
        )

    orders = _planned(ORDERS, "Order")
    nullable = _planned(
        ORDERS, "Order", OrderKey(attr=_ORDER_SKU), OrderKey(attr=_ORDER_ORDERED_ON, nulls="first")
    )
    positions = _planned(
        POSITIONS, "Position", OrderKey(attr=_POSITION_VALID_END), OrderKey(attr=_POSITION_VALUE)
    )
    february, march = dt.date(2024, 2, 15), dt.date(2024, 3, 1)
    return [
        pytest.param(
            orders.first(limit=2), orders.first(limit=5), ORDERS, None, id="first-page-cap"
        ),
        pytest.param(*after(orders, (1,), (9,)), ORDERS, None, id="direct-hoisted-range"),
        pytest.param(*after(orders, (1,), (9,)), ORDERS, True, id="locking-outer-join"),
        pytest.param(
            *after(_planned(ORDERS, "Order", OrderKey(attr=_ORDER_ACTIVE)), (True, 1), (False, 7)),
            ORDERS,
            False,
            id="null-tail-branches",
        ),
        pytest.param(
            *after(nullable, (None, february, 1), (None, march, 4)),
            ORDERS,
            False,
            id="null-then-finite",
        ),
        pytest.param(
            *after(nullable, ("A-100", None, 1), ("B-200", None, 3)),
            ORDERS,
            True,
            id="finite-then-null",
        ),
        pytest.param(
            *after(positions, (INFINITY, Decimal("1.50"), 1), (INFINITY, Decimal("2.5"), 2)),
            POSITIONS,
            False,
            id="infinity-then-finite",
        ),
        pytest.param(
            *after(positions, (INFINITY, Decimal("1.50"), 1), (INFINITY, Decimal("2.5"), 2)),
            POSITIONS,
            True,
            id="infinity-locking",
        ),
        pytest.param(
            *after(
                _planned(DOCUMENT_LAYOUT, "Traveler", OrderKey(attr=_TRAVELER_JOINED)),
                ("2024-01-05", 1),
                ("0000-13-99", 2),
            ),
            DOCUMENT_LAYOUT,
            False,
            id="text-compared-carrier",
        ),
        pytest.param(
            *after(_planned(PAYMENT, "CardPayment"), (1,), (6,)),
            PAYMENT,
            True,
            id="family-tag-guard",
        ),
        pytest.param(
            *after(
                _page_query(
                    TRAVERSAL,
                    "Vehicle",
                    Comparison(op="eq", subject=FieldSubject("Vehicle.dealer.name"), value="Ada"),
                    OrderKey(attr="parallax.compatibility.Vehicle.dealerId"),
                ),
                (3, 1),
                (8, 5),
            ),
            TRAVERSAL,
            False,
            id="union-branches",
        ),
        pytest.param(
            *after(
                _page_query(
                    ORDERS,
                    "OrderItem",
                    Comparison(op="eq", subject=FieldSubject("OrderItem.order.name"), value="Ada"),
                    OrderKey(attr=_ORDER_SHIPPED),
                ),
                (february, 11),
                (march, 12),
            ),
            ORDERS,
            True,
            id="shared-source-branches",
        ),
    ]


@pytest.mark.parametrize("dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"])
@pytest.mark.parametrize(("cold", "current", "model", "shared_lock"), _template_pages())
def test_a_page_template_renders_what_direct_compilation_of_the_current_page_binds(
    cold: ResolvedObjectQuery,
    current: ResolvedObjectQuery,
    model: Metamodel,
    shared_lock: bool,
    dialect: Dialect,
) -> None:
    # The template is compiled from another page of the same pattern, so every
    # finite carrier and cap it renders is the current page's, while NULL
    # branches, the open bound's framework bind, and every typed span and
    # override stay those direct compilation of the current page derives.
    template = compile_template(
        read_planning.plan(cold, model, projection=_PROJECTION).root,
        model,
        dialect,
        shared_lock=shared_lock,
    )
    direct = compile_entity_query(
        read_planning.plan(current, model, projection=_PROJECTION).root,
        model,
        dialect,
        shared_lock=shared_lock,
    )

    rendered = template.render(query=current)

    assert rendered.statement == direct.statement
    assert [type(bind) for bind in rendered.statement.binds] == [
        type(bind) for bind in direct.statement.binds
    ]
    assert all(
        rendered_bind is current_bind
        for rendered_bind, current_bind in zip(
            rendered.statement.binds, direct.statement.binds, strict=True
        )
        if not isinstance(current_bind, (int, str))
    )
    assert rendered.statement.wire_binds() == direct.statement.wire_binds()
    assert rendered.result_contract == direct.result_contract
    assert (
        template.render(query=cold).statement
        == compile_entity_query(
            read_planning.plan(cold, model, projection=_PROJECTION).root,
            model,
            dialect,
            shared_lock=shared_lock,
        ).statement
    )


def test_an_unpaged_template_renders_its_compiled_read_without_inputs() -> None:
    node = validate_object_query(
        entity_of(ORDERS, "Order"),
        object_query(entity_of(ORDERS, "Order").identity, TrueNode()),
        ORDERS,
    )
    template = compile_template(
        read_planning.plan(node, ORDERS, projection=_PROJECTION).root, ORDERS, POSTGRES
    )

    assert template.render() is template.compiled
    assert template.render(query=node) is template.compiled


def test_a_page_template_refuses_missing_current_inputs() -> None:
    plan = _planned(ORDERS, "Order")
    continued = plan.after(ContinuationCoordinate((1,)), limit=2)
    first = compile_template(
        read_planning.plan(plan.first(limit=2), ORDERS, projection=_PROJECTION).root,
        ORDERS,
        POSTGRES,
    )
    after = compile_template(
        read_planning.plan(continued, ORDERS, projection=_PROJECTION).root, ORDERS, POSTGRES
    )

    with raises_code(InternalError, SQL_GENERATION_FAILED, match="current page cap"):
        first.render()
    with raises_code(InternalError, SQL_GENERATION_FAILED, match="current seek"):
        after.render(query=plan.first(limit=2))
    with raises_code(InternalError, SQL_GENERATION_FAILED, match="until its template renders"):
        after.compiled.statement.wire_binds()
