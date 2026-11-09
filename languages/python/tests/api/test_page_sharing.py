"""Page-wide node sharing through the public verbs, over one seeded repeated graph.

Three Orders of one Customer, read through ``Order.customer.orders``, so every root
reaches the same four rows. Sharing is opportunistic, so these stories prove it ran
by counting unique published nodes, and use identity only for what must not happen.

Three Purchases of one Buyer add a Depot only the root position reaches, so a corrupt
Depot classifies its root alone, while every root still reaches that root's row.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import engine
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._mechanism.given_state import apply_given_apply
from parallax.conformance.class_models import MODELS
from parallax.conformance.guide_models import Address, Customer, Order
from parallax.conformance.read_models import DepositRate
from parallax.core import (
    LATEST,
    MANY_TO_ONE,
    ONE_TO_MANY,
    Attr,
    DomainModel,
    Entity,
    Int32,
    ObjectQuery,
    Rel,
    attr,
    rel,
)
from parallax.core.base import UsageError
from parallax.core.entity import UnloadedRelationshipError, model_of
from parallax.core.object_query import TX_TIME
from parallax.core.read_delivery import InvalidData, InvalidDataError
from parallax.snapshot import (
    ScopedDatabase,
    SharingScope,
    SnapshotStream,
    TxnContext,
    connect,
    edge_of,
    is_view_loaded,
    pin_of,
)
from tests._support.case_corpus import case as corpus_case
from tests._support.corpus import case_fixtures
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root


class Depot(Entity, table="sharing_depot"):
    id: Attr[int] = attr(primary_key=True)
    ship_to: Attr[Address]


class Buyer(Entity, table="sharing_buyer"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=100)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    purchases: Rel[tuple[Purchase, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "buyer_id"), order_by=("id",)
    )


class Purchase(Entity, table="sharing_purchase"):
    id: Attr[int] = attr(primary_key=True)
    buyer_id: Attr[int]
    depot_id: Attr[int]
    note: Attr[str] = attr(max_length=100)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    buyer: Rel[Buyer | None] = rel(reverse_of="purchases")
    depot: Rel[Depot] = rel(cardinality=MANY_TO_ONE, join=("depot_id", "id"))


_MODEL: Final = DomainModel(Customer, Order)
_INVALID_MODEL: Final = DomainModel(Depot, Buyer, Purchase)
_ORDER_IDS: Final = (10, 11, 12)
_ROOTS: Final = len(_ORDER_IDS)
_NODES_AT_PAGE_SCOPE: Final = _ROOTS + 1
_NODES_AT_ROOT_SCOPE: Final = _ROOTS * (_ROOTS + 1)
_DOCUMENTS_AT_PAGE_SCOPE: Final = 2 * _ROOTS + 1
_DOCUMENTS_AT_ROOT_SCOPE: Final = _ROOTS * (_ROOTS + 2)
_SPLITTING_THE_ROOTS: Final = 2
_TWO_PAGES_OF_PURCHASES: Final = (7, 8, 9, *_ORDER_IDS)
_INVALID_ORDINAL_ON_THE_LATER_PAGE: Final = 4
_NODES_ON_THE_LATER_PAGE_AT_PAGE_SCOPE: Final = 9
_NODES_ON_THE_LATER_PAGE_AT_ROOT_SCOPE: Final = 16
_NODES_ACROSS_TWO_PAGES: Final = 2 * _NODES_AT_PAGE_SCOPE
_DOCUMENTS_ACROSS_TWO_PAGES: Final = _ROOTS + 2 * _NODES_AT_PAGE_SCOPE
_REPLACED_ON: Final = dt.date(2024, 5, 1)
_ORDER_KEYS: Final = {"id", "customerId", "placedOn", "total", "version"}
_CUSTOMER_KEYS: Final = {"id", "name", "email"}
_REPEATED: Final[ObjectQuery[Any, Any]] = (
    Order.where(Order.all).include(Order.customer.orders).order_by(Order.id.asc())
)
_INVALID: Final = _ORDER_IDS[1]
_PURCHASE_KEYS: Final = {"id", "buyerId", "depotId", "note", "version"}
_NODES_BESIDE_AN_INVALID_ROOT_AT_PAGE_SCOPE: Final = 6
_NODES_BESIDE_AN_INVALID_ROOT_AT_ROOT_SCOPE: Final = 10
_DOCUMENTS_BESIDE_AN_INVALID_ROOT_AT_PAGE_SCOPE: Final = 8
_DOCUMENTS_BESIDE_AN_INVALID_ROOT_AT_ROOT_SCOPE: Final = 12
_BESIDE_AN_INVALID_ROOT: Final[ObjectQuery[Any, Any]] = (
    Purchase.where(Purchase.all)
    .include(Purchase.depot, Purchase.buyer.purchases)
    .order_by(Purchase.id.asc())
)


def _db(profile_run: Any, *, lifecycle_provider: Any = None) -> ScopedDatabase:
    profile_run.reset(
        model_of(_MODEL),
        {
            "Customer": [{"id": 1, "name": "Ada", "email": None}],
            "Order": [
                {
                    "id": order_id,
                    "customerId": 1,
                    "placedOn": "2024-04-01",
                    "total": "5.00",
                    "version": 1,
                }
                for order_id in _ORDER_IDS
            ],
        },
    )
    return own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=lifecycle_provider)
    ).using_database_login()


def _db_with_a_corrupt_depot(
    profile_run: Any,
    *,
    depot_of: Callable[[int], int],
    corrupt: int,
    purchases: tuple[int, ...] = _ORDER_IDS,
) -> ScopedDatabase:
    """``purchases`` of one Buyer, each at ``depot_of`` its id, with the required
    ``street`` of Depot ``corrupt`` absent. That stays hydratable, so an invalid root
    still publishes the nodes a write door must refuse."""
    profile_run.reset(
        model_of(_INVALID_MODEL),
        {
            "Buyer": [{"id": 1, "name": "Ada", "version": 1}],
            "Depot": [
                {
                    "id": depot,
                    "shipTo": {"street": "1 Quay", "city": "Oslo", "postcode": "0150"},
                }
                for depot in {depot_of(purchase) for purchase in purchases}
            ],
            "Purchase": [
                {
                    "id": purchase,
                    "buyerId": 1,
                    "depotId": depot_of(purchase),
                    "note": "held",
                    "version": 1,
                }
                for purchase in purchases
            ],
        },
    )
    control = profile_run.control()
    try:
        control.execute_write(
            f"update sharing_depot set ship_to = ship_to - 'street' where id = {corrupt}", ()
        )
    finally:
        control.close()
    return own_root(connect(profile_run.port, _INVALID_MODEL)).using_database_login()


def _db_with_an_invalid_root(profile_run: Any) -> ScopedDatabase:
    return _db_with_a_corrupt_depot(
        profile_run, depot_of=lambda purchase: purchase, corrupt=_INVALID
    )


def _db_with_every_root_invalid(profile_run: Any) -> ScopedDatabase:
    return _db_with_a_corrupt_depot(profile_run, depot_of=lambda _purchase: 1, corrupt=1)


def _direct_wire(reader: Any, **scope: SharingScope) -> list[Any]:
    return reader.wire.find(_BESIDE_AN_INVALID_ROOT, **scope).checked().results()


def _projected_wire(reader: Any, **scope: SharingScope) -> list[Any]:
    return reader.find(_BESIDE_AN_INVALID_ROOT, **scope).wire().checked().results()


_WIRE_READS: Final = pytest.mark.parametrize("read", [_direct_wire, _projected_wire])


def _purchase_nodes(roots: list[Any]) -> int:
    return len(
        {
            id(node)
            for root in roots
            for node in (root, root.depot, root.buyer, *root.buyer.purchases)
        }
    )


def _purchase_documents(roots: list[Any]) -> int:
    return len(
        {
            id(document)
            for root in roots
            for document in (root, root["depot"], root["buyer"], *root["buyer"]["purchases"])
        }
    )


def _purchase_document(root: Any, purchase_id: int) -> Any:
    return next(leaf for leaf in root["buyer"]["purchases"] if leaf["id"] == purchase_id)


def _valid(roots: list[Any]) -> list[Any]:
    return [root for root in roots if not isinstance(root, InvalidData)]


def _hydrated(roots: list[Any]) -> list[Any]:
    return [root.data for root in roots]


def _nodes(roots: list[Any]) -> int:
    return len(
        {id(node) for root in roots for node in (root, root.customer, *root.customer.orders)}
    )


def _documents(roots: list[Any]) -> int:
    return len(
        {
            id(document)
            for root in roots
            for document in (root, root["customer"], *root["customer"]["orders"])
        }
    )


def _by_id(nodes: tuple[Any, ...], node_id: int) -> Any:
    return next(node for node in nodes if node.id == node_id)


def _assert_each_position_holds_its_keys(roots: list[Any]) -> None:
    for root in roots:
        assert set(root) == {*_ORDER_KEYS, "customer"}
        assert set(root["customer"]) == {*_CUSTOMER_KEYS, "orders"}
        for leaf in root["customer"]["orders"]:
            assert set(leaf) == _ORDER_KEYS


def test_a_page_publishes_one_node_per_logical_row(profile_run: Any) -> None:
    db = _db(profile_run)
    at_root = db.find(_REPEATED).results()
    at_page = db.find(_REPEATED, sharing_scope="page").results()
    again = db.find(_REPEATED, sharing_scope="page").results()

    assert _nodes(at_root) == _NODES_AT_ROOT_SCOPE
    assert _nodes(at_page) == _NODES_AT_PAGE_SCOPE
    assert [root.id for root in at_page] == list(_ORDER_IDS)
    assert at_root[0].customer is not at_root[1].customer
    assert at_page[0] is not again[0]
    assert at_page[0].customer is not again[0].customer
    for root in (*at_root, *at_page):
        assert _by_id(root.customer.orders, root.id) is root


def test_a_back_reference_shares_with_the_forward_hop_on_its_slot(profile_run: Any) -> None:
    db = _db(profile_run)
    query = Order.where(Order.all).include(Order.customer.orders.customer)

    assert _nodes(db.find(query, sharing_scope="page").results()) == _NODES_AT_PAGE_SCOPE


def test_a_shared_node_gains_what_another_position_loaded_and_closes_a_cycle(
    profile_run: Any,
) -> None:
    db = _db(profile_run)
    at_root = db.find(_REPEATED).results()
    at_page = db.find(_REPEATED, sharing_scope="page").results()

    with pytest.raises(UnloadedRelationshipError):
        _ = _by_id(at_root[0].customer.orders, _ORDER_IDS[1]).customer
    leaf = _by_id(at_page[0].customer.orders, _ORDER_IDS[1])
    assert leaf.customer is at_page[0].customer
    assert _by_id(leaf.customer.orders, leaf.id) is leaf


def test_a_typed_to_wire_projection_keeps_each_positions_keys(profile_run: Any) -> None:
    db = _db(profile_run)
    direct = db.wire.find(_REPEATED).results()
    projected = cast("list[Any]", db.find(_REPEATED, sharing_scope="page").wire().results())

    _assert_each_position_holds_its_keys(projected)
    assert projected == direct


def test_a_direct_wire_page_publishes_one_document_per_node_and_render_token(
    profile_run: Any,
) -> None:
    db = _db(profile_run)
    at_root = cast("list[Any]", db.wire.find(_REPEATED).results())
    at_page = cast("list[Any]", db.wire.find(_REPEATED, sharing_scope="page").results())
    again = cast("list[Any]", db.wire.find(_REPEATED, sharing_scope="page").results())

    assert _documents(at_root) == _DOCUMENTS_AT_ROOT_SCOPE
    assert _documents(at_page) == _DOCUMENTS_AT_PAGE_SCOPE
    assert [root["id"] for root in at_page] == list(_ORDER_IDS)
    assert at_root[0]["customer"] is not at_root[1]["customer"]
    assert at_page[0] is not again[0]
    assert at_page[0]["customer"] is not again[0]["customer"]
    _assert_each_position_holds_its_keys(at_page)
    assert at_page == at_root


def test_a_back_reference_renders_finitely_on_a_shared_document(profile_run: Any) -> None:
    db = _db(profile_run)
    query = Order.where(Order.all).include(Order.customer.orders.customer).order_by(Order.id.asc())

    def back_references(roots: list[Any]) -> list[Any]:
        return [leaf["customer"] for root in roots for leaf in root["customer"]["orders"]]

    at_root = cast("list[Any]", db.wire.find(query).results())
    at_page = cast("list[Any]", db.wire.find(query, sharing_scope="page").results())

    assert len({id(document) for document in back_references(at_root)}) == _ROOTS
    assert len({id(document) for document in back_references(at_page)}) == 1
    for document in back_references(at_page):
        assert set(document) == _CUSTOMER_KEYS
    assert at_page == at_root
    assert json.loads(json.dumps(at_page)) == json.loads(json.dumps(at_root))


def test_a_milestone_reads_roots_stand_at_their_own_pins(profile_run: Any) -> None:
    case = corpus_case("m-inheritance-100")
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    apply_given_apply(case, profile_run.port)
    db = own_root(connect(profile_run.port, MODELS[Path(case.model).stem])).using_database_login()
    query = DepositRate.where(DepositRate.all).history(TX_TIME).as_of(valid_time=LATEST)

    at_root = db.find(query).results()
    at_page = db.find(query, sharing_scope="page").results()

    assert len(at_page) == 2
    assert at_page[0] is not at_page[1]
    assert pin_of(at_page[0]) != pin_of(at_page[1])
    assert [pin_of(root) for root in at_page] == [pin_of(root) for root in at_root]
    assert [edge_of(root) for root in at_page] == [edge_of(root) for root in at_root]


def test_an_unknown_scope_is_refused_before_any_database_call(profile_run: Any) -> None:
    observation = LifecycleObservation()
    db = _db(profile_run, lifecycle_provider=observation.provider)
    unknown = cast("SharingScope", "everything")

    def refused_inside(reader: Any) -> None:
        before = observation.database_calls
        with pytest.raises(ValueError, match="sharing_scope"):
            reader.find(_REPEATED, sharing_scope=unknown)
        with pytest.raises(ValueError, match="sharing_scope"):
            reader.wire.find(_REPEATED, sharing_scope=unknown)
        with pytest.raises(ValueError, match="sharing_scope"):
            reader.stream(_REPEATED, sharing_scope=unknown)
        with pytest.raises(ValueError, match="sharing_scope"):
            reader.wire.stream(_REPEATED, sharing_scope=unknown)
        assert observation.database_calls == before

    refused_inside(db)
    db.transact(refused_inside)
    db.read_only(refused_inside)


def test_a_shared_node_carries_the_write_evidence_its_read_admits(profile_run: Any) -> None:
    db = _db(profile_run)

    def amend_through_two_roots(tx: TxnContext) -> None:
        roots = tx.find(_REPEATED, sharing_scope="page").results()
        tx.amend(roots[0].edit(total=Decimal("6.00")))
        alias = _by_id(roots[1].customer.orders, roots[0].id)
        tx.amend(alias.edit(placed_on=_REPLACED_ON))

    db.transact(amend_through_two_roots)
    stored = db.find(Order.where(Order.id == _ORDER_IDS[0])).result()
    assert (stored.total, stored.placed_on, stored.version) == (
        Decimal("6.00"),
        _REPLACED_ON,
        2,
    )


def test_a_shared_document_carries_the_write_evidence_its_read_admits(profile_run: Any) -> None:
    db = _db(profile_run)

    def amend_through_two_roots(tx: TxnContext) -> None:
        roots = cast("list[Any]", tx.wire.find(_REPEATED, sharing_scope="page").results())
        tx.wire.amend(roots[0], {"total": "6.00"})
        alias = next(
            leaf for leaf in roots[1]["customer"]["orders"] if leaf["id"] == roots[0]["id"]
        )
        tx.wire.amend(alias, {"placedOn": _REPLACED_ON.isoformat()})

    db.transact(amend_through_two_roots)
    stored = db.find(Order.where(Order.id == _ORDER_IDS[0])).result()
    assert (stored.total, stored.placed_on, stored.version) == (
        Decimal("6.00"),
        _REPLACED_ON,
        2,
    )


def test_a_shared_document_from_another_attempt_is_refused_at_the_write_door(
    profile_run: Any,
) -> None:
    db = _db(profile_run)
    published = cast(
        "list[Any]",
        db.transact(lambda tx: tx.wire.find(_REPEATED, sharing_scope="page").results()),
    )

    with raises_code(UsageError, "write-evidence-unavailable"):
        db.transact(lambda tx: tx.wire.amend(published[0], {"total": "6.00"}))


def test_a_shared_node_from_another_attempt_is_refused_at_the_write_door(profile_run: Any) -> None:
    db = _db(profile_run)
    published = db.transact(lambda tx: tx.find(_REPEATED, sharing_scope="page").results())

    with raises_code(UsageError, "write-evidence-unavailable"):
        db.transact(lambda tx: tx.amend(published[0].edit(total=Decimal("6.00"))))


def test_valid_roots_share_beside_an_invalid_one(profile_run: Any) -> None:
    db = _db_with_an_invalid_root(profile_run)
    at_root = db.find(_BESIDE_AN_INVALID_ROOT).checked().results()
    at_page = db.find(_BESIDE_AN_INVALID_ROOT, sharing_scope="page").checked().results()

    first, invalid, last = cast("list[Any]", at_page)
    assert [first.id, invalid.data.id, last.id] == list(_ORDER_IDS)
    assert invalid.ordinal == 1
    assert invalid.issues == cast("Any", at_root[1]).issues
    assert _purchase_nodes(_valid(at_page)) == _NODES_BESIDE_AN_INVALID_ROOT_AT_PAGE_SCOPE
    assert _purchase_nodes(_valid(at_root)) == _NODES_BESIDE_AN_INVALID_ROOT_AT_ROOT_SCOPE

    neighbour = _by_id(first.buyer.purchases, _INVALID)
    assert invalid.data is not neighbour
    assert invalid.data.buyer is not first.buyer
    assert invalid.data.depot.id == _INVALID
    with pytest.raises(UnloadedRelationshipError):
        _ = neighbour.depot


@_WIRE_READS
def test_valid_documents_share_beside_an_invalid_one(profile_run: Any, read: Any) -> None:
    db = _db_with_an_invalid_root(profile_run)
    at_root = read(db)
    at_page = read(db, sharing_scope="page")

    first, invalid, last = at_page
    assert [first["id"], invalid.data["id"], last["id"]] == list(_ORDER_IDS)
    assert invalid.ordinal == 1
    assert invalid.issues == at_root[1].issues
    assert _purchase_documents(_valid(at_page)) == _DOCUMENTS_BESIDE_AN_INVALID_ROOT_AT_PAGE_SCOPE
    assert _purchase_documents(_valid(at_root)) == _DOCUMENTS_BESIDE_AN_INVALID_ROOT_AT_ROOT_SCOPE

    neighbour = _purchase_document(first, _INVALID)
    assert invalid.data is not neighbour
    assert invalid.data["buyer"] is not first["buyer"]
    assert set(neighbour) == _PURCHASE_KEYS
    assert _valid(at_page) == _valid(at_root)
    assert invalid.data == at_root[1].data


def test_an_invalid_nodes_write_is_refused_and_its_neighbours_admitted(profile_run: Any) -> None:
    db = _db_with_an_invalid_root(profile_run)

    def amend_the_row_through_both(tx: TxnContext) -> None:
        first, invalid, _last = cast(
            "list[Any]", tx.find(_BESIDE_AN_INVALID_ROOT, sharing_scope="page").checked().results()
        )
        for edited in (invalid.data.edit(note="moved"), invalid.data.buyer.edit(name="Grace")):
            with raises_code(UsageError, "write-value-not-stored"):
                tx.amend(edited)
        tx.amend(_by_id(first.buyer.purchases, _INVALID).edit(note="moved"))
        tx.amend(first.buyer.edit(name="Grace"))

    db.transact(amend_the_row_through_both)
    purchase = db.find(Purchase.where(Purchase.id == _INVALID)).result()
    buyer = db.find(Buyer.where(Buyer.id == 1)).result()
    assert (purchase.note, purchase.version, buyer.name) == ("moved", 2, "Grace")


@_WIRE_READS
def test_an_invalid_documents_write_is_refused_and_its_neighbours_admitted(
    profile_run: Any, read: Any
) -> None:
    db = _db_with_an_invalid_root(profile_run)

    def amend_the_row_through_both(tx: TxnContext) -> None:
        first, invalid, _last = read(tx, sharing_scope="page")
        for document, edit in (
            (invalid.data, {"note": "moved"}),
            (invalid.data["buyer"], {"name": "Grace"}),
        ):
            with raises_code(UsageError, "write-instruction-invalid"):
                tx.wire.amend(document, edit)
        tx.wire.amend(_purchase_document(first, _INVALID), {"note": "moved"})
        tx.wire.amend(first["buyer"], {"name": "Grace"})

    db.transact(amend_the_row_through_both)
    purchase = db.find(Purchase.where(Purchase.id == _INVALID)).result()
    buyer = db.find(Buyer.where(Buyer.id == 1)).result()
    assert (purchase.note, purchase.version, buyer.name) == ("moved", 2, "Grace")


def test_a_corrupt_row_every_root_reaches_publishes_no_more_nodes_than_root_scope(
    profile_run: Any,
) -> None:
    db = _db_with_every_root_invalid(profile_run)
    at_root = db.find(_BESIDE_AN_INVALID_ROOT).checked().results()
    at_page = db.find(_BESIDE_AN_INVALID_ROOT, sharing_scope="page").checked().results()

    assert _purchase_nodes(_hydrated(at_page)) == _purchase_nodes(_hydrated(at_root))


@_WIRE_READS
def test_a_corrupt_row_every_root_reaches_publishes_no_more_documents_than_root_scope(
    profile_run: Any, read: Any
) -> None:
    db = _db_with_every_root_invalid(profile_run)

    at_root = _hydrated(read(db))
    at_page = _hydrated(read(db, sharing_scope="page"))

    assert _purchase_documents(at_page) == _purchase_documents(at_root)
    assert at_page == at_root


def _delivered(stream: SnapshotStream[Any]) -> list[Any]:
    with stream as roots:
        return list(roots)


def _projected(stream: SnapshotStream[Any]) -> list[Any]:
    with stream as roots:
        return [stream.wire(root) for root in roots]


def _checked(stream: SnapshotStream[Any]) -> list[Any]:
    with stream:
        return list(stream.checked())


def _checked_and_projected(stream: SnapshotStream[Any]) -> list[Any]:
    with stream:
        return [stream.wire(root) for root in stream.checked()]


def _delivered_before_a_refusal(stream: SnapshotStream[Any]) -> tuple[list[Any], Any]:
    delivered: list[Any] = []
    with stream as roots, pytest.raises(InvalidDataError) as refused:
        delivered.extend(roots)
    return delivered, refused.value


def _direct_wire_stream(reader: Any, query: Any, **options: Any) -> SnapshotStream[Any]:
    return reader.wire.stream(query, **options)


def _typed_stream(reader: Any, query: Any, **options: Any) -> SnapshotStream[Any]:
    return reader.stream(query, **options)


_WIRE_STREAMS: Final = pytest.mark.parametrize(
    ("open_stream", "drain"),
    [(_direct_wire_stream, _delivered), (_typed_stream, _projected)],
    ids=["direct", "projected"],
)
_CHECKED_WIRE_STREAMS: Final = pytest.mark.parametrize(
    ("open_stream", "drain"),
    [(_direct_wire_stream, _checked), (_typed_stream, _checked_and_projected)],
    ids=["direct", "projected"],
)


def test_a_stream_shares_within_each_page_and_never_across_one(profile_run: Any) -> None:
    db = _db(profile_run)
    whole = _delivered(db.stream(_REPEATED, sharing_scope="page"))
    paged = _delivered(db.stream(_REPEATED, batch_size=_SPLITTING_THE_ROOTS, sharing_scope="page"))
    at_root = _delivered(db.stream(_REPEATED, batch_size=_SPLITTING_THE_ROOTS))

    assert _nodes(whole) == _NODES_AT_PAGE_SCOPE
    assert _nodes(paged) == _NODES_ACROSS_TWO_PAGES
    assert _nodes(at_root) == _NODES_AT_ROOT_SCOPE
    assert [root.id for root in paged] == list(_ORDER_IDS)
    last_on_the_page, past_the_boundary = paged[1:]
    assert last_on_the_page.customer is not past_the_boundary.customer
    assert _by_id(last_on_the_page.customer.orders, past_the_boundary.id) is not past_the_boundary


@_WIRE_STREAMS
def test_a_wire_stream_shares_within_each_page_and_never_across_one(
    profile_run: Any, open_stream: Any, drain: Any
) -> None:
    db = _db(profile_run)
    whole = drain(open_stream(db, _REPEATED, sharing_scope="page"))
    paged = drain(open_stream(db, _REPEATED, batch_size=_SPLITTING_THE_ROOTS, sharing_scope="page"))
    at_root = drain(open_stream(db, _REPEATED, batch_size=_SPLITTING_THE_ROOTS))

    assert _documents(whole) == _DOCUMENTS_AT_PAGE_SCOPE
    assert _documents(paged) == _DOCUMENTS_ACROSS_TWO_PAGES
    assert _documents(at_root) == _DOCUMENTS_AT_ROOT_SCOPE
    assert [root["id"] for root in paged] == list(_ORDER_IDS)
    last_on_the_page, past_the_boundary = paged[1:]
    assert last_on_the_page["customer"] is not past_the_boundary["customer"]
    _assert_each_position_holds_its_keys(paged)
    assert paged == at_root


def _standalone(db: ScopedDatabase, read: Callable[[Any], list[Any]]) -> list[Any]:
    return read(db)


def _read_only(db: ScopedDatabase, read: Callable[[Any], list[Any]]) -> list[Any]:
    return db.read_only(read)


def _read_write(db: ScopedDatabase, read: Callable[[Any], list[Any]]) -> list[Any]:
    return db.transact(read)


@pytest.mark.parametrize("run", [_standalone, _read_only, _read_write])
def test_a_stream_shares_wherever_it_runs(profile_run: Any, run: Any) -> None:
    db = _db(profile_run)

    def typed(reader: Any) -> list[Any]:
        return _delivered(reader.stream(_REPEATED, sharing_scope="page"))

    def wire(reader: Any) -> list[Any]:
        return _delivered(reader.wire.stream(_REPEATED, sharing_scope="page"))

    assert _nodes(run(db, typed)) == _NODES_AT_PAGE_SCOPE
    assert _documents(run(db, wire)) == _DOCUMENTS_AT_PAGE_SCOPE


def test_a_delivered_root_already_carries_all_it_will_ever_carry(profile_run: Any) -> None:
    db = _db(profile_run)

    with db.stream(_REPEATED, batch_size=_SPLITTING_THE_ROOTS, sharing_scope="page") as stream:
        roots = iter(stream)
        first = next(roots)
        on_this_page = _by_id(first.customer.orders, _ORDER_IDS[1])
        on_the_next_page = _by_id(first.customer.orders, _ORDER_IDS[2])

        assert on_this_page.customer is first.customer
        assert not is_view_loaded(on_the_next_page, Order.customer)
        assert [root.id for root in roots] == list(_ORDER_IDS[1:])

    assert not is_view_loaded(on_the_next_page, Order.customer)


def test_a_stream_keeps_its_prefix_at_an_invalid_root_and_a_checked_stream_passes_it(
    profile_run: Any,
) -> None:
    db = _db_with_an_invalid_root(profile_run)

    delivered, refused = _delivered_before_a_refusal(
        db.stream(_BESIDE_AN_INVALID_ROOT, sharing_scope="page")
    )
    at_root, refused_at_root = _delivered_before_a_refusal(db.stream(_BESIDE_AN_INVALID_ROOT))
    assert [root.id for root in delivered] == [root.id for root in at_root] == list(_ORDER_IDS[:1])
    assert [record.ordinal for record in refused.invalid_data] == [1]
    assert refused.invalid_data[0].issues == refused_at_root.invalid_data[0].issues

    first, invalid, last = _checked(db.stream(_BESIDE_AN_INVALID_ROOT, sharing_scope="page"))
    assert [first.id, invalid.data.id, last.id] == list(_ORDER_IDS)
    assert invalid.ordinal == 1
    assert _purchase_nodes([first, last]) == _NODES_BESIDE_AN_INVALID_ROOT_AT_PAGE_SCOPE
    assert invalid.data is not _by_id(first.buyer.purchases, _INVALID)
    assert invalid.data.buyer is not first.buyer


@_CHECKED_WIRE_STREAMS
def test_a_checked_wire_stream_passes_an_invalid_root_and_its_neighbours_share(
    profile_run: Any, open_stream: Any, drain: Any
) -> None:
    db = _db_with_an_invalid_root(profile_run)

    first, invalid, last = drain(open_stream(db, _BESIDE_AN_INVALID_ROOT, sharing_scope="page"))
    at_root = drain(open_stream(db, _BESIDE_AN_INVALID_ROOT))

    assert [first["id"], invalid.data["id"], last["id"]] == list(_ORDER_IDS)
    assert invalid.ordinal == 1
    assert invalid.issues == at_root[1].issues
    assert _purchase_documents([first, last]) == _DOCUMENTS_BESIDE_AN_INVALID_ROOT_AT_PAGE_SCOPE
    assert invalid.data is not _purchase_document(first, _INVALID)
    assert invalid.data["buyer"] is not first["buyer"]
    assert invalid.data == at_root[1].data
    assert [first, last] == _valid(at_root)


def test_a_default_wire_stream_keeps_its_prefix_at_an_invalid_root(profile_run: Any) -> None:
    db = _db_with_an_invalid_root(profile_run)

    delivered, refused = _delivered_before_a_refusal(
        db.wire.stream(_BESIDE_AN_INVALID_ROOT, sharing_scope="page")
    )
    at_root, _ = _delivered_before_a_refusal(db.wire.stream(_BESIDE_AN_INVALID_ROOT))

    assert delivered == at_root
    assert [root["id"] for root in delivered] == list(_ORDER_IDS[:1])
    assert [record.ordinal for record in refused.invalid_data] == [1]


def test_an_invalid_root_on_a_later_page_keeps_its_place_in_the_result(profile_run: Any) -> None:
    db = _db_with_a_corrupt_depot(
        profile_run,
        depot_of=lambda purchase: purchase,
        corrupt=_INVALID,
        purchases=_TWO_PAGES_OF_PURCHASES,
    )

    def delivered(**scope: SharingScope) -> list[Any]:
        return _checked(db.stream(_BESIDE_AN_INVALID_ROOT, batch_size=_ROOTS, **scope))

    at_page = delivered(sharing_scope="page")
    at_root = delivered()

    invalid = at_page[_INVALID_ORDINAL_ON_THE_LATER_PAGE]
    assert invalid.data.id == _INVALID
    assert invalid.ordinal == _INVALID_ORDINAL_ON_THE_LATER_PAGE
    assert invalid.issues == at_root[_INVALID_ORDINAL_ON_THE_LATER_PAGE].issues
    valid_on_the_later_page = _valid(at_page[_ROOTS:])
    assert _purchase_nodes(valid_on_the_later_page) == _NODES_ON_THE_LATER_PAGE_AT_PAGE_SCOPE
    assert _purchase_nodes(_valid(at_root[_ROOTS:])) == _NODES_ON_THE_LATER_PAGE_AT_ROOT_SCOPE


def test_a_write_inside_a_stream_loop_is_admitted_on_a_shared_node(profile_run: Any) -> None:
    db = _db(profile_run)

    def amend_as_delivered(tx: TxnContext) -> None:
        delivered: list[Any] = []
        with tx.stream(_REPEATED, sharing_scope="page") as roots:
            for root in roots:
                tx.amend(root.edit(total=Decimal("6.00")))
                delivered.append(root)
        assert _nodes(delivered) == _NODES_AT_PAGE_SCOPE

    db.transact(amend_as_delivered)
    stored = db.find(_REPEATED).results()
    assert [(root.total, root.version) for root in stored] == [(Decimal("6.00"), 2)] * _ROOTS


@pytest.mark.parametrize(
    "open_stream", [_direct_wire_stream, _typed_stream], ids=["direct", "projected"]
)
def test_a_write_inside_a_stream_loop_is_admitted_on_a_shared_document(
    profile_run: Any, open_stream: Any
) -> None:
    db = _db(profile_run)

    def amend_as_delivered(tx: TxnContext) -> None:
        delivered: list[Any] = []
        with open_stream(tx, _REPEATED, sharing_scope="page") as stream:
            for root in stream:
                document = root if open_stream is _direct_wire_stream else stream.wire(root)
                tx.wire.amend(document, {"total": "6.00"})
                delivered.append(document)
        assert _documents(delivered) == _DOCUMENTS_AT_PAGE_SCOPE

    db.transact(amend_as_delivered)
    stored = db.find(_REPEATED).results()
    assert [(root.total, root.version) for root in stored] == [(Decimal("6.00"), 2)] * _ROOTS
