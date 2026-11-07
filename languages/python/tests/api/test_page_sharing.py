"""Page-wide node sharing through the public verbs, over one seeded repeated graph.

Three Orders of one Customer, read through ``Order.customer.orders``, so every root
reaches the same four rows. Sharing is opportunistic, so these stories prove it ran
by counting unique published nodes, and use identity only for what must not happen.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import engine
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._mechanism.given_state import apply_given_apply
from parallax.conformance.class_models import MODELS
from parallax.conformance.guide_models import Customer, Order
from parallax.conformance.read_models import DepositRate
from parallax.core import LATEST, DomainModel, ObjectQuery
from parallax.core.entity import UnloadedRelationshipError, model_of
from parallax.core.object_query import TX_TIME
from parallax.core.unit_work import WriteEvidenceError
from parallax.snapshot import ScopedDatabase, SharingScope, TxnContext, connect, edge_of, pin_of
from tests._support.adoption import raises_contextualized
from tests._support.case_corpus import case as corpus_case
from tests._support.corpus import case_fixtures
from tests._support.root_ownership import own_root

_MODEL: Final = DomainModel(Customer, Order)
_ORDER_IDS: Final = (10, 11, 12)
_ROOTS: Final = len(_ORDER_IDS)
_NODES_AT_PAGE_SCOPE: Final = _ROOTS + 1
_NODES_AT_ROOT_SCOPE: Final = _ROOTS * (_ROOTS + 1)
_DOCUMENTS_AT_PAGE_SCOPE: Final = 2 * _ROOTS + 1
_DOCUMENTS_AT_ROOT_SCOPE: Final = _ROOTS * (_ROOTS + 2)
_REPLACED_ON: Final = dt.date(2024, 5, 1)
_ORDER_KEYS: Final = {"id", "customerId", "placedOn", "total", "version"}
_CUSTOMER_KEYS: Final = {"id", "name", "email"}
_REPEATED: Final[ObjectQuery[Any, Any]] = (
    Order.where(Order.all).include(Order.customer.orders).order_by(Order.id.asc())
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


def _order(orders: tuple[Any, ...], order_id: int) -> Any:
    return next(order for order in orders if order.id == order_id)


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
        assert _order(root.customer.orders, root.id) is root


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
        _ = _order(at_root[0].customer.orders, _ORDER_IDS[1]).customer
    leaf = _order(at_page[0].customer.orders, _ORDER_IDS[1])
    assert leaf.customer is at_page[0].customer
    assert _order(leaf.customer.orders, leaf.id) is leaf


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
        assert observation.database_calls == before

    refused_inside(db)
    db.transact(refused_inside)
    db.read_only(refused_inside)


def test_a_shared_node_carries_the_write_evidence_its_read_admits(profile_run: Any) -> None:
    db = _db(profile_run)

    def amend_through_two_roots(tx: TxnContext) -> None:
        roots = tx.find(_REPEATED, sharing_scope="page").results()
        tx.amend(roots[0].edit(total=Decimal("6.00")))
        alias = _order(roots[1].customer.orders, roots[0].id)
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

    with raises_contextualized(WriteEvidenceError) as refused:
        db.transact(lambda tx: tx.wire.amend(published[0], {"total": "6.00"}))

    assert refused.value.code == "write-evidence-unavailable"


def test_a_shared_node_from_another_attempt_is_refused_at_the_write_door(profile_run: Any) -> None:
    db = _db(profile_run)
    published = db.transact(lambda tx: tx.find(_REPEATED, sharing_scope="page").results())

    with raises_contextualized(WriteEvidenceError) as refused:
        db.transact(lambda tx: tx.amend(published[0].edit(total=Decimal("6.00"))))

    assert refused.value.code == "write-evidence-unavailable"
