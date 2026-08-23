"""The Wire read interface: ``db.wire.find`` / ``tx.wire.find`` and what they publish.

Drives the real seam end to end — the production executor against a canned
`m-db-port`, then the wire materializer — so what these assert is what a Wire
read answers. The typed materializer runs over the same merge in the graph
suites, which is what makes "peers over one merge" checkable rather than
asserted.

Three claims bound what is asserted here: keys are declared member names and
leaves are canonical Wire Values (`m-wire`); a back-reference unwinds finitely
along the requested Include Paths rather than truncating to a primary-key stub;
and every returned mapping and list refuses, at every depth, mutation reaching
it through the instance, while staying an ordinary built-in subclass.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import pickle
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest
from _metamodel_support import Declaration, key, source
from _snapshot_graph_support import documents_of, identity_of, layout_of
from _transact_support import NoIoPort

from _support.db_port import body_outcome
from _support.document_reads import fold_mapping_rows
from _support.sql import compile_read
from parallax.conformance import class_models, models
from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INFINITY, STRING, PresentDocument
from parallax.core.db_port import DbPort, DocumentReadOrdinals, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AbstractRoot,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    Table,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import object_query_node
from parallax.core.predicate import All
from parallax.core.temporal_read import Pin
from parallax.snapshot import InvalidData, WireEntity, connect, handle
from parallax.snapshot.handle._wire import WireDatabaseView, wire_query_node
from parallax.snapshot.materialize import (
    merge_graph_input,
    source_hint_of,
    wire_roots,
)
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

# Descriptor-backed Domain Models, because a connection takes the Domain Model
# itself; the accepted Metamodel underneath one is what the materialize-level
# seams below are stated over.
_MODELS = models.load_domain_models()
ORDERS = _MODELS["orders"]
CUSTOMER = _MODELS["customer"]
CUSTOMER_META = model_of(CUSTOMER)


class QueuePort:
    """A fake `m-db-port` returning one canned response per ``execute()`` call,
    in call order — enough to drive the executor's own per-level loop without a
    real database."""

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)
        self.executed: list[tuple[str, list[object]]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return fold_mapping_rows(self._responses.pop(0), document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
        return body_outcome(cast("DbPort", self), body)


def _order_row(order_id: int = 1) -> Row:
    return {
        "id": order_id,
        "name": "Ada",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def _wire_database(port: QueuePort) -> handle.Database:
    return handle.Database(port, ORDERS, dialect=POSTGRES)


def _entity(published: object) -> WireEntity:
    assert isinstance(published, WireEntity), published
    return published


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping), value
    return cast("Mapping[str, object]", value)


def _sequence(value: object) -> Sequence[object]:
    assert isinstance(value, list), value
    return cast("Sequence[object]", value)


# --------------------------------------------------------------------------- #
# Declared names and canonical values.                                         #
# --------------------------------------------------------------------------- #


def test_wire_keys_are_declared_member_names_and_leaves_are_canonical() -> None:
    port = QueuePort([[_order_row()]])
    query = deserialize_query(
        {"target": "Order", "predicate": {"eq": {"attr": "Order.id", "value": 1}}}
    )
    root = _entity(_wire_database(port).wire.find(query).result())
    # `ordered_on` is the physical column; `orderedOn` is the declared member.
    assert set(root) == {"id", "name", "sku", "qty", "price", "active", "orderedOn"}
    assert root["price"] == "10.50"
    assert root["orderedOn"] == "2024-01-05"
    assert root["active"] is True


def test_a_document_occurrence_publishes_the_members_the_document_held() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "address": {
                        "street": "1 Park Ave",
                        "city": "Oslo",
                        "geo": {"country": "NO", "elevation": 10.5},
                        "phones": [{"type": "home", "number": "555-1234"}],
                    },
                }
            ]
        ]
    )
    query = deserialize_query(
        {"target": "Customer", "predicate": {"eq": {"attr": "Customer.id", "value": 1}}}
    )
    root = _entity(handle.Database(port, CUSTOMER, dialect=POSTGRES).wire.find(query).result())
    address = _mapping(root["address"])
    geo = _mapping(address["geo"])
    # `geo.point` is a declared `one` the stored document never carried, so it is
    # absent from the published node rather than invented as a null.
    assert set(geo) == {"country", "elevation"}
    assert _sequence(address["phones"])[0] == {"type": "home", "number": "555-1234"}


def test_two_stored_occurrences_short_and_null_publish_differently() -> None:
    # The distinction publication now carries: a document that omits `geo` and one
    # that stores it as JSON null are two stored states, so they publish two
    # nodes. Both hydrate a Typed `geo` of `None`, which is why the Wire node was
    # the only place the difference could be lost.
    def published(document: object) -> Mapping[str, object]:
        port = QueuePort([[{"id": 1, "name": "Ada", "address": document}]])
        query = deserialize_query(
            {"target": "Customer", "predicate": {"eq": {"attr": "Customer.id", "value": 1}}}
        )
        root = _entity(handle.Database(port, CUSTOMER, dialect=POSTGRES).wire.find(query).result())
        return _mapping(root["address"])

    assert published({"street": "1 Park Ave", "city": "Oslo"}) == {
        "street": "1 Park Ave",
        "city": "Oslo",
        "phones": [],
    }
    assert published({"street": "1 Park Ave", "city": "Oslo", "geo": None}) == {
        "street": "1 Park Ave",
        "city": "Oslo",
        "geo": None,
        "phones": [],
    }


def test_only_an_entity_node_can_carry_a_source_hint() -> None:
    # A nested Value Object mapping is structurally identical to an Entity node
    # and answers `isinstance(value, WireEntity)` with false — and it has no slot
    # to put a hint in, which is what makes "only an Entity node carries one"
    # structural rather than a rule the materializer has to keep.
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "address": {
                        "street": "1 Park Ave",
                        "city": "Oslo",
                        "geo": {"country": "NO", "elevation": 10.5},
                        "phones": [{"type": "home", "number": "555-1234"}],
                    },
                }
            ]
        ]
    )
    query = deserialize_query(
        {"target": "Customer", "predicate": {"eq": {"attr": "Customer.id", "value": 1}}}
    )
    root = _entity(handle.Database(port, CUSTOMER, dialect=POSTGRES).wire.find(query).result())
    address = _mapping(root["address"])
    assert not isinstance(address, WireEntity)
    assert source_hint_of(cast("Any", address)) is None
    assert source_hint_of(root) is not None


def test_an_absent_document_occurrence_reads_null_and_an_absent_many_reads_empty() -> None:
    port = QueuePort([[{"id": 4, "name": "Mary", "address": None}]])
    query = deserialize_query(
        {"target": "Customer", "predicate": {"eq": {"attr": "Customer.id", "value": 4}}}
    )
    root = _entity(handle.Database(port, CUSTOMER, dialect=POSTGRES).wire.find(query).result())
    assert root["address"] is None

    # A `many` has no absent state, so a document omitting `phones` stored that
    # member's one zero value under a spelling that carries no key, and publishing
    # `[]` for it renders what was stored rather than inventing a value — the
    # verdict a leaf and a `one` do not share, because for them an omitted key and
    # a stored null are two states.
    port = QueuePort([[{"id": 3, "name": "Grace", "address": {"street": "9 Beacon St"}}]])
    query = deserialize_query(
        {"target": "Customer", "predicate": {"eq": {"attr": "Customer.id", "value": 3}}}
    )
    root = _entity(handle.Database(port, CUSTOMER, dialect=POSTGRES).wire.find(query).result())
    assert _mapping(root["address"])["phones"] == []


def test_an_absent_many_publishes_empty_through_the_unclassified_decode_too() -> None:
    # The same document reaching conversion with no member preclassified, which is
    # the arm `convert_row` takes for a caller that supplies no classified set. Its
    # occurrence reduction has to answer exactly as the row transform's does, or
    # one stored state publishes two nodes depending on which door it came in by.
    identity = identity_of(CUSTOMER_META, "Customer")
    builder = GraphBuilder(ViewSchema.of())
    ref = convert_row(
        {"id": 3, "name": "Grace", "address": {"street": "9 Beacon St"}},
        LevelContext(layout_of(CUSTOMER_META, identity), documents_of(CUSTOMER_META, identity)),
        builder,
        source=ROOT_LEVEL,
    )
    (published,) = wire_roots(merge_graph_input(builder.seal((ref,), Pin())), CUSTOMER_META)
    assert _mapping(_entity(published)["address"]) == {"street": "9 Beacon St", "phones": []}


def test_the_absent_sentinel_reaches_no_published_position_at_any_depth() -> None:
    # A row that carried neither a scalar nor a nested member holds this
    # runtime's own absence marker at each of those positions. Publication skips
    # such a position rather than rendering it, so what a caller reads is a
    # member the value does not have — the marker itself is unreachable, at every
    # depth a document can nest to.
    identity = identity_of(CUSTOMER_META, "Customer")
    builder = GraphBuilder(ViewSchema.of())
    ref = convert_row(
        {"id": 3, "address": {"street": "9 Beacon St", "geo": {"country": "NO"}}},
        LevelContext(layout_of(CUSTOMER_META, identity), documents_of(CUSTOMER_META, identity)),
        builder,
        source=ROOT_LEVEL,
    )
    (published,) = wire_roots(merge_graph_input(builder.seal((ref,), Pin())), CUSTOMER_META)
    node = _entity(published)
    assert "name" not in node
    assert "city" not in _mapping(node["address"])
    assert "elevation" not in _mapping(_mapping(node["address"])["geo"])
    assert _absent_free(node) == 0


def _absent_free(value: object) -> int:
    """The number of published positions holding the absence marker, at any depth."""
    if isinstance(value, Mapping):
        return sum(_absent_free(item) for item in cast("Mapping[str, object]", value).values())
    if isinstance(value, list):
        return sum(_absent_free(item) for item in cast("list[object]", value))
    return 1 if value is ABSENT else 0


# --------------------------------------------------------------------------- #
# The include tree, not the identity graph, bounds the walk.                   #
# --------------------------------------------------------------------------- #


def test_an_unrequested_relationship_is_absent_rather_than_null() -> None:
    port = QueuePort([[_order_row()]])
    query = deserialize_query(
        {"target": "Order", "predicate": {"eq": {"attr": "Order.id", "value": 1}}}
    )
    root = _entity(_wire_database(port).wire.find(query).result())
    assert "items" not in root


def test_a_requested_relationship_unwinds_in_result_order() -> None:
    port = QueuePort(
        [
            [_order_row()],
            [
                {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": None},
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
        ]
    )
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )
    root = _entity(_wire_database(port).wire.find(query).result())
    items = _sequence(root["items"])
    assert [_mapping(item)["id"] for item in items] == [12, 11]
    # The child's own foreign key is a declared member and keeps its declared name.
    assert _mapping(items[0])["orderId"] == 1


def test_a_back_reference_unwinds_finitely_instead_of_stubbing() -> None:
    port = QueuePort(
        [
            [_order_row()],
            [
                {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": None},
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
        ]
    )
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [
                {"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]},
            ],
        }
    )
    snapshot = _wire_database(port).wire.find(query)
    root = _entity(snapshot.result())
    items = _sequence(root["items"])
    back = _mapping(_mapping(items[0])["order"])
    # The whole Order renders — not a primary-key stub — and the walk stops
    # because the include tree has no child under `items.order`, not because a
    # cycle detector fired.
    assert back["name"] == "Ada"
    assert "items" not in back
    # Two positions reaching one merged node under one subtree share one object.
    assert _mapping(items[1])["order"] is back
    # The root is a different position: its subtree still carries `items`.
    assert back is not root
    assert len(port.executed) == 2


# --------------------------------------------------------------------------- #
# Frozen values.                                                               #
# --------------------------------------------------------------------------- #


def _frozen_root() -> WireEntity:
    port = QueuePort(
        [
            [_order_row()],
            [{"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None}],
        ]
    )
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )
    return _entity(_wire_database(port).wire.find(query).result())


def test_a_wire_mapping_is_a_dict_that_refuses_mutation_through_the_instance() -> None:
    root = _frozen_root()
    assert isinstance(root, dict)
    assert type(root) is not dict
    mutable = cast("Any", root)
    for mutate in (
        lambda: mutable.__setitem__("id", 2),
        lambda: mutable.__delitem__("id"),
        mutable.clear,
        lambda: mutable.pop("id"),
        mutable.popitem,
        lambda: mutable.setdefault("id", 2),
        lambda: mutable.update({"id": 2}),
        lambda: mutable.__ior__({"id": 2}),
    ):
        with pytest.raises(TypeError, match="refuses mutation"):
            mutate()
    assert root["id"] == 1


def test_a_wire_sequence_is_a_list_that_refuses_mutation_through_the_instance() -> None:
    items = _sequence(_frozen_root()["items"])
    assert isinstance(items, list)
    assert type(items) is not list
    mutable = cast("Any", items)
    for mutate in (
        lambda: mutable.__setitem__(0, {}),
        lambda: mutable.__delitem__(0),
        lambda: mutable.append({}),
        lambda: mutable.extend([{}]),
        lambda: mutable.insert(0, {}),
        lambda: mutable.remove(items[0]),
        mutable.pop,
        mutable.clear,
        mutable.sort,
        mutable.reverse,
        lambda: mutable.__iadd__([{}]),
        lambda: mutable.__imul__(2),
    ):
        with pytest.raises(TypeError, match="refuses mutation"):
            mutate()
    assert len(items) == 1


def test_a_wire_value_compares_structurally_and_is_unhashable() -> None:
    root = _frozen_root()
    assert root == dict(root)
    assert _sequence(root["items"]) == list(_sequence(root["items"]))
    with pytest.raises(TypeError):
        hash(root)
    with pytest.raises(TypeError):
        hash(_sequence(root["items"]))


def test_a_wire_value_serializes_as_json_directly() -> None:
    root = _frozen_root()
    assert json.loads(json.dumps(root))["orderedOn"] == "2024-01-05"


def test_plain_conversion_yields_an_ordinary_mapping() -> None:
    root = _frozen_root()
    plain = dict(root)
    assert type(plain) is dict
    plain["id"] = 2
    assert root["id"] == 1


def test_copying_a_wire_value_answers_the_same_object() -> None:
    root = _frozen_root()
    items = _sequence(root["items"])
    assert cast("Any", root).copy() is root
    assert copy.copy(root) is root
    assert copy.deepcopy(root) is root
    assert cast("Any", items).copy() is items
    assert copy.copy(items) is items
    assert copy.deepcopy(items) is items


def test_pickling_a_wire_value_yields_ordinary_domain_data() -> None:
    root = _frozen_root()
    restored = pickle.loads(pickle.dumps(root))
    assert type(restored) is dict
    assert restored["id"] == 1
    items = pickle.loads(pickle.dumps(_sequence(root["items"])))
    assert type(items) is list


def test_the_wire_entity_interface_is_not_constructible() -> None:
    with pytest.raises(TypeError):
        cast("Any", WireEntity)()


def test_a_published_value_refuses_the_repopulating_initializer() -> None:
    # `__init__` mutates too — `dict.__init__` / `list.__init__` repopulate an
    # existing container in place — so a caller reaching for the one mutator
    # that is not named like one is refused with the rest, at every depth.
    root = _frozen_root()
    items = _sequence(root["items"])
    for mutate in (
        lambda: cast("Any", root).__init__({"id": 2}),
        lambda: cast("Any", items).__init__([{"id": 2}]),
        lambda: cast("Any", items[0]).__init__({"id": 2}),
    ):
        with pytest.raises(TypeError, match="refuses mutation"):
            mutate()
    assert root["id"] == 1
    assert len(items) == 1
    assert _mapping(items[0])["id"] == 11


def test_a_published_value_is_the_type_its_construction_could_not_have_faked() -> None:
    # The refusing `__init__` is what makes construction private: `type(value)(…)`
    # — the one spelling a caller holding a published value can reach the class
    # through — cannot produce a second one.
    root = _frozen_root()
    with pytest.raises(TypeError, match="refuses mutation"):
        cast("Any", type(root))({"id": 2})


# --------------------------------------------------------------------------- #
# Query spellings, capability, and classification.                             #
# --------------------------------------------------------------------------- #


def test_every_accepted_query_spelling_lowers_to_one_canonical_node() -> None:
    document = {"target": "Order", "predicate": {"eq": {"attr": "Order.id", "value": 1}}}
    node = deserialize_query(document)
    assert wire_query_node(node) is node
    assert wire_query_node(document) == node

    typed = Gadget.where(Gadget.id == 1)
    assert wire_query_node(typed) == object_query_node(typed)


class Gadget(Entity, table="gadget", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]


GADGETS = DomainModel(Gadget)


def test_a_wire_view_reports_itself_without_leaking_its_owner() -> None:
    database = _wire_database(QueuePort([]))
    assert repr(database.wire) == "WireDatabaseView()"
    assert isinstance(database.wire, WireDatabaseView)


def test_a_wire_read_participates_in_the_transaction_that_owns_it() -> None:
    port = QueuePort([[_order_row()]])
    database = _wire_database(port)
    result = database.transact(
        lambda tx: _entity(
            tx.wire.find(
                {"target": "Order", "predicate": {"eq": {"attr": "Order.id", "value": 1}}}
            ).result()
        )
    )
    assert result["id"] == 1
    # Order is unversioned, so the default preference resolves it to the Locking
    # fallback and the participating read renders that Entity's shared-lock suffix.
    assert " for share of " in port.executed[0][0]


# Both Domain Model provenances a connection admits, over one corpus model: the
# classes an application composes and the descriptor document a class-free caller
# hands the public door. Capability follows the model, so every result shape a
# Wire read can publish is proven through BOTH.
_CUSTOMER_MODELS: Mapping[str, DomainModel] = {
    "class-backed": class_models.MODELS["customer"],
    "descriptor-backed": CUSTOMER,
}

_VALID_CUSTOMER: Row = {
    "id": 1,
    "name": "Ada",
    "address": {"street": "Storgata 1", "city": "Oslo", "phones": []},
}


def _customer_wire(model: DomainModel, row: Row) -> object:
    """One connected Customer read, published in band."""
    port = QueuePort([[row]])
    query = deserialize_query({"target": "Customer", "predicate": {"all": {}}})
    return connect(port, model, dialect=POSTGRES).wire.find(query).checked().result()


@pytest.mark.parametrize("provenance", list(_CUSTOMER_MODELS))
def test_either_model_provenance_publishes_one_conforming_wire_root(provenance: str) -> None:
    published = _entity(_customer_wire(_CUSTOMER_MODELS[provenance], _VALID_CUSTOMER))
    assert published["name"] == "Ada"
    address = _mapping(published["address"])
    assert address["street"] == "Storgata 1"
    # The document held no `geo`, so the published occurrence carries no such key
    # at any depth — the same absence the hydrated Typed value keeps.
    assert "geo" not in address


@pytest.mark.parametrize("provenance", list(_CUSTOMER_MODELS))
def test_either_model_provenance_publishes_a_hydratable_record(provenance: str) -> None:
    published = _customer_wire(
        _CUSTOMER_MODELS[provenance], {"id": 1, "name": "Ada", "address": {"city": "Oslo"}}
    )
    assert isinstance(published, InvalidData)
    record = cast("InvalidData[object]", published)
    assert {issue.code for issue in record.issues} == {"stored-data-required-member-absent"}
    # The collapse a hydratable root is published under answers what the required
    # member READS as; it puts no key back. A required LEAF the document omits
    # therefore stays absent from the published node — one of the positions where
    # `m-snapshot-read` *What a materialized value carries* separates held from
    # carried.
    assert "street" not in _mapping(cast("Mapping[str, object]", record.data)["address"])


@pytest.mark.parametrize("provenance", list(_CUSTOMER_MODELS))
def test_either_model_provenance_publishes_a_non_hydrating_record(provenance: str) -> None:
    published = _customer_wire(
        _CUSTOMER_MODELS[provenance], {"id": None, "name": "Ada", "address": None}
    )
    assert isinstance(published, InvalidData)
    record = cast("InvalidData[object]", published)
    assert {issue.code for issue in record.issues} == {"stored-data-primary-key-null"}
    assert record.data is None


def test_the_constructor_door_classifies_the_same_way_connect_does() -> None:
    # The first-party constructor the conformance adapter uses reaches the same
    # materializer `connect` does, so its verdicts are the same ones.
    port = QueuePort([[{"id": 1, "name": "Ada", "address": {"city": "Oslo"}}]])
    query = deserialize_query(
        {"target": "Customer", "predicate": {"eq": {"attr": "Customer.id", "value": 1}}}
    )
    published = (
        handle.Database(port, CUSTOMER, dialect=POSTGRES).wire.find(query).checked().result()
    )
    assert isinstance(published, InvalidData)
    record = cast("InvalidData[object]", published)
    assert {issue.code for issue in record.issues} == {"stored-data-required-member-absent"}


def test_a_classless_connection_serves_wire_and_refuses_typed_before_any_io() -> None:
    with pytest.raises(handle.SnapshotConnectionError):
        handle.Database(NoIoPort(), ORDERS, dialect=POSTGRES).find(
            cast("Any", Gadget.where(Gadget.id == 1))
        )
    # The capability the same connection DOES hold is an executed read, not a
    # reachable namespace: the Wire lane needs no Entity Class, so it runs.
    served = handle.Database(QueuePort([[_order_row()]]), ORDERS, dialect=POSTGRES)
    assert isinstance(served.wire, WireDatabaseView)
    published = served.wire.find(
        {"target": "Order", "predicate": {"eq": {"attr": "Order.id", "value": 1}}}
    ).result()
    assert _entity(published)["name"] == "Ada"


# --------------------------------------------------------------------------- #
# Inheritance, guarded paths, temporal ends, and milestone sets.               #
# --------------------------------------------------------------------------- #


ANIMAL = _MODELS["animal"]
INVOICE = _MODELS["invoice"]
_UTC = dt.UTC


def test_an_inheritance_participant_publishes_its_family_variant() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "kind": "dog",
                    "name": "Rex",
                    "owner_id": None,
                    "license_id": "L",
                    "bark_volume": 3,
                }
            ]
        ]
    )
    query = deserialize_query({"target": "Animal", "predicate": {"all": {}}})
    root = _entity(handle.Database(port, ANIMAL, dialect=POSTGRES).wire.find(query).result())
    assert root["familyVariant"] == "Dog"
    assert root["barkVolume"] == 3


def test_a_loaded_null_to_one_view_publishes_null_and_a_guarded_parent_publishes_nothing() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "kind": "dog",
                    "name": "Rex",
                    "owner_id": None,
                    "license_id": "L",
                    "bark_volume": 3,
                },
                {
                    "id": 2,
                    "kind": "cat",
                    "name": "Mia",
                    "owner_id": None,
                    "license_id": "L",
                    "indoor": True,
                },
            ]
        ]
    )
    query = deserialize_query(
        {
            "target": "Animal",
            "predicate": {"all": {}},
            "includes": [
                {
                    "segments": [{"rel": "Animal.owner"}],
                    "appliesTo": ["parallax.compatibility.Dog"],
                }
            ],
        }
    )
    roots = handle.Database(port, ANIMAL, dialect=POSTGRES).wire.find(query).results()
    dog, cat = (_entity(root) for root in roots)
    # The guard admits only the Dog, so the Cat never sees the view at all — an
    # absent key, which is what unloaded means — while the admitted Dog's own
    # null correlation key publishes a loaded-null view.
    assert dog["owner"] is None
    assert "owner" not in cat


def test_a_temporal_end_publishes_the_canonical_infinity_literal() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                }
            ]
        ]
    )
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    )
    root = _entity(handle.Database(port, INVOICE, dialect=POSTGRES).wire.find(query).result())
    assert root["txStart"] == "2024-04-01T00:00:00.000000Z"
    assert root["txEnd"] == "infinity"


def _history_port() -> QueuePort:
    return QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                },
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
            ]
        ]
    )


_HISTORY_QUERY: Mapping[str, object] = {
    "target": "InvoiceLine",
    "predicate": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
    "temporal": {"transaction-time": {"history": {}}},
}


def test_a_milestone_set_wire_read_publishes_every_milestone_in_one_ordered_result() -> None:
    port = _history_port()
    roots = handle.Database(port, INVOICE, dialect=POSTGRES).wire.find(_HISTORY_QUERY).results()
    assert [_entity(root)["amount"] for root in roots] == ["50.00", "75.00"]


def test_a_participating_milestone_set_wire_read_runs_inside_the_transaction() -> None:
    port = _history_port()
    database = handle.Database(port, INVOICE, dialect=POSTGRES)
    result = database.transact(lambda tx: tx.wire.find(_HISTORY_QUERY).results())
    assert [_entity(root)["amount"] for root in result] == ["50.00", "75.00"]


# --------------------------------------------------------------------------- #
# Declared names keep the published field set collision-free.                  #
# --------------------------------------------------------------------------- #
_VARIANT_ROOT = EntityIdentity("catalog", "AssetRecord")
_SHARED_VARIANT = EntityIdentity("archive", "SharedVariant")

# One Entity family whose Value Object storage column is spelled exactly like the
# synthetic family-variant key. A projection that published members by COLUMN
# would put the stored document where the variant spelling belongs; declared
# names cannot collide with it, and the wire node proves both survive.
_VARIANT_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_VARIANT_ROOT,
            container=Table("asset_record"),
            attributes=(key(_VARIANT_ROOT),),
            value_objects=(
                ValueObjectOccurrenceDeclaration(
                    name="mailingAddress",
                    storage=Column("familyVariant"),
                    shape=ValueObjectShapeDeclaration(
                        key=ValueObjectShapeKey(),
                        attributes=(ValueObjectAttributeDeclaration("label", STRING),),
                    ),
                ),
            ),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_SHARED_VARIANT,
            value_objects=(
                ValueObjectOccurrenceDeclaration(
                    name="archiveProfile",
                    storage=Column("archive_profile"),
                    shape=ValueObjectShapeDeclaration(
                        key=ValueObjectShapeKey(),
                        attributes=(ValueObjectAttributeDeclaration("label", STRING),),
                    ),
                ),
            ),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "archive-shared"),
        ),
    )
)


def test_a_value_object_column_spelled_like_the_variant_key_still_publishes_both() -> None:
    compiled = compile_read(All(), _VARIANT_MODEL, POSTGRES, _root_of(_VARIANT_MODEL))
    materialized = compiled.materialize_row(
        {
            "id": 1,
            "kind": "archive-shared",
            "familyVariant": PresentDocument({"label": "mail"}),
            "archive_profile": PresentDocument({"label": "archive"}),
        }
    )
    builder = GraphBuilder(ViewSchema.of())
    ref = convert_row(
        materialized.values,
        LevelContext(
            layout_of(_VARIANT_MODEL, materialized.resolved_entity),
            compiled.documents,
        ),
        builder,
        source=ROOT_LEVEL,
    )
    (root,) = wire_roots(merge_graph_input(builder.seal((ref,), Pin())), _VARIANT_MODEL)
    assert root == {
        "id": 1,
        "familyVariant": "SharedVariant",
        "mailingAddress": {"label": "mail"},
        "archiveProfile": {"label": "archive"},
    }


def _root_of(model: Any) -> Any:
    entity = model.entity(_VARIANT_ROOT)
    assert entity is not None
    return entity
