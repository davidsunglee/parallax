"""Root classification and the in-band invalid-result surface (m-snapshot-read).

Three seams, in the order a read crosses them. `classify_roots` attributes the
issues a merge carries to the result roots whose requested include trees reach
them, and settles which allocation indices construction covers. The typed
materializer then publishes each root as itself or as its `InvalidData` record.
Finally a layout twin — one logical model authored twice, differing only in its
root-owned `layout` — proves the whole verdict is layout-independent: the same
stored state classifies identically whether it lives in its own columns or inside
one Structured Column.

Per-row detection lives in `test_snapshot_conversion.py`, propagation through the
merge in `test_snapshot_merge.py`, and the accessors that consume what publishes
here in `test_snapshot_find.py`.
"""

from __future__ import annotations

import datetime as dt
import pickle
from collections.abc import Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest
from _layout_twin_columns import COLUMNS_TWIN
from _layout_twin_columns import LayoutTwinItem as ColumnsItem
from _layout_twin_document import DOCUMENT_TWIN
from _layout_twin_document import LayoutTwinItem as DocumentItem
from _snapshot_graph_support import GraphFixture, invalid_record
from _transact_support import ACCOUNT

from _support import mirrored_models as mm
from _support.db_port import (
    Read,
    ScriptedPort,
)
from parallax.conformance import read_models
from parallax.conformance import vo_models as vo
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core import LATEST, DomainModel
from parallax.core.base import INFINITY, PresentDocument
from parallax.core.db_port import Row
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.snapshot import (
    MISSING_STORED_VALUE,
    InvalidData,
    InvalidDataError,
    ObjectKey,
    StoredDataIssue,
    connect,
)
from parallax.snapshot.materialize import (
    ClassifiedRoot,
    ConformingRoot,
    GraphClassification,
    RootClassification,
    classify_roots,
    merge_graph_input,
)
from parallax.snapshot.materialize._graph import graph_rows

_NAMESPACE = "parallax.compatibility"

_ORDER_ROW: dict[str, object] = {
    "id": 1,
    "name": "Ada",
    "sku": "A",
    "qty": 1,
    "price": Decimal("1"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 1),
}
_ITEM_ROW: dict[str, object] = {
    "id": 11,
    "order_id": 1,
    "sku": "x",
    "quantity": 1,
    "shipped_on": None,
}


def _classified(root: RootClassification) -> ClassifiedRoot:
    """The classified verdict ``root`` is, narrowed for the assertions on it."""
    assert isinstance(root, ClassifiedRoot), root
    return root


def _classify(fixture: GraphFixture, *roots: object, offset: int = 0) -> GraphClassification:
    graph = fixture.graph(*cast("Any", roots))
    return classify_roots(
        merge_graph_input(graph),
        model_of(ORDERS_MODEL),
        ordinal_offset=offset,
    )


# --------------------------------------------------------------------------- #
# Attribution: which roots one issue makes invalid.                            #
# --------------------------------------------------------------------------- #
def test_a_conforming_graph_is_answered_without_walking_or_wrapping() -> None:
    # The common case pays nothing: no issue anywhere means no reachability walk,
    # no excluded node, and no record to unwrap at publication.
    fixture = GraphFixture(ORDERS_MODEL, "parallax.compatibility.Order.items")
    order = fixture.node("Order", _ORDER_ROW)
    fixture.attach(
        order, "parallax.compatibility.Order.items", (fixture.node("OrderItem", _ITEM_ROW),)
    )

    classification = _classify(fixture, order)
    assert classification.conforming
    assert classification.excluded == frozenset()
    assert classification.roots == (ConformingRoot(0),)


def test_an_invalid_included_node_invalidates_every_root_that_reaches_it() -> None:
    # Reaching one affected object through several roots repeats its diagnosis in
    # each affected root's record, because classification is root-granular and no
    # root may deliver a pruned or partly published tree.
    fixture = GraphFixture(ORDERS_MODEL, "parallax.compatibility.Order.items")
    first = fixture.node("Order", _ORDER_ROW)
    second = fixture.node("Order", {**_ORDER_ROW, "id": 2})
    shared = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    fixture.attach(first, "parallax.compatibility.Order.items", (shared,))
    fixture.attach(second, "parallax.compatibility.Order.items", (shared,))

    diagnosis = StoredDataIssue(
        "stored-data-leaf-undecodable",
        EntityIdentity(_NAMESPACE, "OrderItem"),
        AttributeIdentity(EntityIdentity(_NAMESPACE, "OrderItem"), "shippedOn"),
        ObjectKey(EntityIdentity(_NAMESPACE, "OrderItem"), (("id", 11),)),
        path=(),
        stored_value="not-a-date",
    )
    affected = [_classified(root) for root in _classify(fixture, first, second).roots]
    assert [root.issues for root in affected] == [frozenset({diagnosis}), frozenset({diagnosis})]
    assert [root.ordinal for root in affected] == [0, 1]


def test_a_root_reaching_no_issue_stays_conforming_beside_an_invalid_sibling() -> None:
    fixture = GraphFixture(ORDERS_MODEL, "parallax.compatibility.Order.items")
    clean = fixture.node("Order", _ORDER_ROW)
    affected = fixture.node("Order", {**_ORDER_ROW, "id": 2})
    fixture.attach(clean, "parallax.compatibility.Order.items", ())
    fixture.attach(
        affected,
        "parallax.compatibility.Order.items",
        (fixture.node("OrderItem", {**_ITEM_ROW, "id": 12, "order_id": 2, "shipped_on": "nope"}),),
    )

    conforming, classified = _classify(fixture, clean, affected).roots
    assert isinstance(conforming, ConformingRoot)
    assert _classified(classified).ordinal == 1


def test_one_invalid_node_reached_twice_from_one_root_carries_one_diagnosis() -> None:
    # A broad view and its narrowed sibling reach the same node, and an object
    # diagnosed once is diagnosed once: the record is a set of facts, not a walk
    # log, so the second path adds nothing.
    fixture = GraphFixture(
        ORDERS_MODEL,
        "parallax.compatibility.Order.items",
        ("parallax.compatibility.Order.items", "items[OrderItem]"),
    )
    order = fixture.node("Order", _ORDER_ROW)
    item = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    fixture.attach(order, "parallax.compatibility.Order.items", (item,))
    fixture.attach(
        order, "parallax.compatibility.Order.items", (item,), narrowed="items[OrderItem]"
    )

    (classified,) = _classify(fixture, order).roots
    assert len(_classified(classified).issues) == 1


def test_the_ordinal_offset_positions_a_record_in_the_published_result() -> None:
    fixture = GraphFixture(ORDERS_MODEL)
    order = fixture.node("Order", {**_ORDER_ROW, "ordered_on": "not-a-date"})

    (classified,) = _classify(fixture, order, offset=4).roots
    assert _classified(classified).ordinal == 4


# --------------------------------------------------------------------------- #
# The construction scope narrows with the classification.                      #
# --------------------------------------------------------------------------- #
def test_a_non_hydrating_root_leaves_its_own_subtree_out_of_construction() -> None:
    fixture = GraphFixture(
        ORDERS_MODEL, "parallax.compatibility.OrderItem.order", "parallax.compatibility.Order.items"
    )
    order = fixture.node("Order", _ORDER_ROW)
    item = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    # A loaded-null view reaches nothing and so attributes nothing, which is the
    # arm distinct from an empty to-many and from an unloaded relationship.
    fixture.attach(item, "parallax.compatibility.OrderItem.order", None)
    fixture.attach(order, "parallax.compatibility.Order.items", (item,))

    classification = _classify(fixture, order)
    assert classification.excluded == frozenset({0, 1})
    assert _classified(classification.roots[0]).node is None


def test_a_node_a_conforming_root_also_reaches_stays_in_construction() -> None:
    # Exclusion follows publication, not blame: the shared item is constructible
    # and the conforming root needs it, so only the nodes no publishable root
    # reaches are left out.
    fixture = GraphFixture(ORDERS_MODEL, "parallax.compatibility.Order.items")
    clean = fixture.node("Order", _ORDER_ROW)
    affected = fixture.node("Order", {**_ORDER_ROW, "id": 2})
    shared = fixture.node("OrderItem", _ITEM_ROW)
    broken = fixture.node("OrderItem", {**_ITEM_ROW, "id": 12, "shipped_on": "not-a-date"})
    fixture.attach(clean, "parallax.compatibility.Order.items", (shared,))
    fixture.attach(affected, "parallax.compatibility.Order.items", (shared, broken))

    classification = _classify(fixture, clean, affected)
    assert classification.excluded == frozenset({2, 3})
    published, invalid = fixture.materialize(clean, affected)
    order = cast("Order", published)
    assert order.id == 1
    assert len(order.items) == 1
    assert invalid_record(invalid).data is None


# --------------------------------------------------------------------------- #
# Publication: what a classified root delivers.                                #
# --------------------------------------------------------------------------- #
def _customer(row: dict[str, object]) -> InvalidData[object]:
    document = PresentDocument(cast("Any", row["address"]))
    port = ScriptedPort(Read(rows=[{**row, "address": document}]))
    database = connect(port, vo.CUSTOMER_MODEL)
    return invalid_record(database.find(vo.Customer.where(vo.Customer.id == 1)).checked().result())


def test_a_hydratable_root_publishes_its_collapsed_value_beside_its_issues() -> None:
    # `street` is declared required and the stored document omits it, which the
    # normative absence collapse already answers with a null. Nothing is
    # invented, so the whole root hydrates and the violation still travels.
    published = _customer({"id": 1, "name": "Ada", "address": {"city": "Berlin"}})
    hydrated = cast("vo.Customer", published.data)
    assert hydrated.id == 1
    assert hydrated.address is not None
    assert hydrated.address.street is None
    assert hydrated.address.city == "Berlin"
    assert {(issue.code, issue.member) for issue in published.issues} == {
        (
            "stored-data-required-member-absent",
            ValueObjectAttributeIdentity(
                ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Customer"), ("address",)), "street"
            ),
        )
    }
    assert published.object_key == ObjectKey(EntityIdentity(_NAMESPACE, "Customer"), (("id", 1),))
    assert published.ordinal == 0
    assert published.version is None
    assert published.edge is None


def test_a_non_hydrating_root_publishes_no_data() -> None:
    # A stored leaf outside its declared type leaves no conforming value, so the
    # root carries its diagnosis and nothing else.
    published = _customer({"id": 1, "name": "Ada", "address": {"street": "1 Main", "city": 7}})
    assert published.data is None
    assert {issue.code for issue in published.issues} == {"stored-data-leaf-undecodable"}
    assert published.object_key == ObjectKey(EntityIdentity(_NAMESPACE, "Customer"), (("id", 1),))


def _balance(row: dict[str, object]) -> InvalidData[object]:
    port = ScriptedPort(Read(rows=[row]))
    database = connect(port, read_models.BALANCE_MODEL)
    query = read_models.Balance.where(read_models.Balance.id == 1).as_of(tx_time=LATEST)
    return invalid_record(database.find(query).checked().result())


def test_a_temporal_root_locates_itself_by_the_milestone_it_decoded() -> None:
    # The temporal locator is the milestone this state was read at, so a caller
    # holding the record can name the exact row the diagnosis is about. A
    # versioned root would carry `version` here instead; the two never coexist.
    opened = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    published = _balance(
        {"bal_id": 1, "acct_num": "A-1", "val": "not-a-decimal", "in_z": opened, "out_z": INFINITY}
    )
    assert published.data is None
    assert published.version is None
    assert published.edge is not None
    assert published.edge.tx_time == opened


def test_a_temporal_root_whose_milestone_did_not_decode_locates_no_edge() -> None:
    # The locator is a decoded fact or nothing: a milestone the row never carried
    # is not manufactured to fill the field.
    published = _balance(
        {"bal_id": 1, "acct_num": "A-1", "val": "not-a-decimal", "in_z": None, "out_z": INFINITY}
    )
    assert published.edge is None
    assert {issue.code for issue in published.issues} == {
        "stored-data-leaf-undecodable",
        "stored-data-attribute-null",
    }


def test_a_versioned_root_whose_version_did_not_decode_locates_no_version() -> None:
    row: dict[str, object] = {"id": 1, "owner": "Ada", "balance": Decimal("1.00"), "version": "x"}
    database = connect(ScriptedPort(Read(rows=[row])), ACCOUNT)
    published = invalid_record(
        database.find(mm.Account.where(mm.Account.id == 1)).checked().result()
    )
    assert published.version is None
    assert published.edge is None


def test_a_loaded_to_one_view_carries_attribution_to_its_parent() -> None:
    # A to-one arm is a lone allocation index rather than a tuple, and reaching an
    # invalid node through one invalidates its holder exactly as a to-many does.
    fixture = GraphFixture(
        ORDERS_MODEL, "parallax.compatibility.OrderItem.order", "parallax.compatibility.Order.items"
    )
    order = fixture.node("Order", _ORDER_ROW)
    item = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    fixture.attach(item, "parallax.compatibility.OrderItem.order", order)
    fixture.attach(order, "parallax.compatibility.Order.items", (item,))

    published = invalid_record(fixture.materialize(item)[0])
    assert published.data is None
    assert published.object_key == ObjectKey(EntityIdentity(_NAMESPACE, "OrderItem"), (("id", 11),))


# --------------------------------------------------------------------------- #
# The layout twin: one logical model, two descriptors, one verdict.            #
# --------------------------------------------------------------------------- #
def _published(
    model: DomainModel, query: object, rows: Sequence[Sequence[Row]]
) -> InvalidData[Any]:
    """One twin member's published record for a scripted two-level read."""
    database = connect(ScriptedPort(*(Read(rows=result) for result in rows)), model)
    record = database.find(cast("Any", query)).checked().result()
    assert isinstance(record, InvalidData), model
    return cast("InvalidData[Any]", record)


def _twin_records(
    profile: object, child_profile: object
) -> tuple[InvalidData[Any], InvalidData[Any]]:
    """The published record of one logical read, under each layout in turn.

    The two members author the same members, tables, and Entity names, so the
    only thing that differs is where the stored state physically lives: its own
    columns here, one Structured Column there.
    """
    return (
        _published(
            COLUMNS_TWIN,
            ColumnsItem.where(ColumnsItem.id == 1).include(ColumnsItem.children),
            (
                [{"id": 1, "profile": PresentDocument(cast("Any", profile))}],
                [
                    {
                        "id": 11,
                        "item_id": 1,
                        "profile": PresentDocument(cast("Any", child_profile)),
                    }
                ],
            ),
        ),
        _published(
            DOCUMENT_TWIN,
            DocumentItem.where(DocumentItem.id == 1).include(DocumentItem.children),
            (
                [{"id": 1, "payload": PresentDocument({"profile": cast("Any", profile)})}],
                [
                    {
                        "id": 11,
                        "item_id": 1,
                        "payload": PresentDocument({"profile": cast("Any", child_profile)}),
                    }
                ],
            ),
        ),
    )


def _profile_values(profile: Any) -> tuple[object, ...] | None:
    return None if profile is None else (profile.street, profile.city)


def _hydrated(data: object) -> tuple[object, ...] | None:
    """A hydrated twin root as declared member values and graph shape alone.

    The two members declare distinct classes, so their roots are never equal to
    each other however faithfully both hydrated. This is the projection of a root
    that carries exactly what Storage Layout may not change — every declared
    value, and the children the requested include tree reached.
    """
    if data is None:
        return None
    root = cast("Any", data)
    return (
        root.id,
        _profile_values(root.profile),
        tuple((child.id, child.item_id, _profile_values(child.profile)) for child in root.children),
    )


def _comparable(record: InvalidData[Any]) -> tuple[object, ...]:
    """Everything about a record that Storage Layout may not change."""
    return (
        record.issues,
        _hydrated(record.data),
        record.object_key,
        record.version,
        record.edge,
        record.ordinal,
    )


_TWIN_ITEM = EntityIdentity(_NAMESPACE, "LayoutTwinItem")
_TWIN_CHILD = EntityIdentity(_NAMESPACE, "LayoutTwinChild")
_ROOT_KEY = ObjectKey(_TWIN_ITEM, (("id", 1),))
_CHILD_KEY = ObjectKey(_TWIN_CHILD, (("id", 11),))


@pytest.mark.parametrize(
    ("profile", "child_profile", "expected"),
    [
        (
            {"city": "Berlin"},
            {"street": "1 Main", "city": None},
            StoredDataIssue(
                "stored-data-required-member-absent",
                _TWIN_ITEM,
                ValueObjectAttributeIdentity(
                    ValueObjectIdentity(_TWIN_ITEM, ("profile",)), "street"
                ),
                _ROOT_KEY,
                path=("profile", "street"),
                stored_value=MISSING_STORED_VALUE,
            ),
        ),
        (
            {"street": "1 Main", "city": None},
            {"city": "Berlin"},
            StoredDataIssue(
                "stored-data-required-member-absent",
                _TWIN_CHILD,
                ValueObjectAttributeIdentity(
                    ValueObjectIdentity(_TWIN_CHILD, ("profile",)), "street"
                ),
                _CHILD_KEY,
                path=("profile", "street"),
                stored_value=MISSING_STORED_VALUE,
            ),
        ),
        (
            {"street": "1 Main", "city": 7},
            {"street": "2 Main", "city": None},
            StoredDataIssue(
                "stored-data-leaf-undecodable",
                _TWIN_ITEM,
                ValueObjectAttributeIdentity(ValueObjectIdentity(_TWIN_ITEM, ("profile",)), "city"),
                _ROOT_KEY,
                path=("profile", "city"),
                stored_value=7,
            ),
        ),
        (
            {"street": "1 Main", "city": None},
            {"street": "2 Main", "city": 7},
            StoredDataIssue(
                "stored-data-leaf-undecodable",
                _TWIN_CHILD,
                ValueObjectAttributeIdentity(
                    ValueObjectIdentity(_TWIN_CHILD, ("profile",)), "city"
                ),
                _CHILD_KEY,
                path=("profile", "city"),
                stored_value=7,
            ),
        ),
    ],
    ids=["hydratable-root", "hydratable-child", "non-hydrating-root", "non-hydrating-child"],
)
def test_a_layout_twin_classifies_one_stored_state_identically(
    profile: object, child_profile: object, expected: StoredDataIssue
) -> None:
    # The invariant the twin exists for: the diagnosis, the object it names,
    # whether the root hydrated, and every declared value and child it hydrated
    # are the same whether that state lived in its own column or inside a
    # Structured Column. Only the physical SQL differs.
    hydrates = expected.code != "stored-data-leaf-undecodable"
    columns, document = _twin_records(profile, child_profile)
    assert _comparable(columns) == _comparable(document)
    assert columns.issues == frozenset({expected})
    # The record always locates the RESULT root, while its diagnosis locates the
    # object the violation was found on — the child, where the child carried it.
    assert columns.object_key == _ROOT_KEY
    assert (columns.data is not None) is hydrates


# --------------------------------------------------------------------------- #
# Evidence at the public seam: shared once, compared structurally, never shown. #
# --------------------------------------------------------------------------- #
def _issue(**overrides: Any) -> StoredDataIssue:
    """One diagnosis, spelled the way classification publishes one."""
    fields: dict[str, Any] = {
        "code": "stored-data-many-wrong-kind",
        "entity": EntityIdentity(_NAMESPACE, "Customer"),
        "member": ValueObjectIdentity(EntityIdentity(_NAMESPACE, "Customer"), ("address",)),
        "object_key": ObjectKey(EntityIdentity(_NAMESPACE, "Customer"), (("id", 1),)),
        "path": ("address", "phones"),
        "stored_value": MappingProxyType({"type": "home", "number": "555"}),
    }
    return StoredDataIssue(**(fields | overrides))


def test_classification_shares_the_one_frozen_evidence_rather_than_copying_it() -> None:
    # Conversion freezes a judged value where it judges it, and every seam above
    # carries that same object: attribution adds the root's Object Key and
    # nothing else. A further copy surviving anywhere along that chain would
    # double what a large rejected document costs and give two structurally
    # equal values no `is` can tell apart.
    fixture = GraphFixture(vo.CUSTOMER_MODEL)
    node = fixture.node("Customer", {"id": 1, "name": "Ada", "address": {"city": "Berlin"}})
    (converted,) = graph_rows(fixture.graph(node)).issues[node]
    record = invalid_record(fixture.materialize(node)[0])
    (published,) = record.issues
    assert published.stored_value is converted.stored_value
    refusal = InvalidDataError((record,))
    (reported,) = next(iter(refusal.invalid_data)).issues
    assert reported.stored_value is converted.stored_value


def test_one_occurrence_reached_twice_collapses_while_a_second_place_does_not() -> None:
    # What the frozenset is for, now that two more fields decide membership.
    # Reaching one occurrence again is the same diagnosis and collapses; the same
    # defect at another path, or a different value at this one, is a second fact
    # about the stored document and stays one.
    assert len({_issue(), _issue()}) == 1
    assert len({_issue(), _issue(path=("address", "geo"))}) == 2
    assert len({_issue(), _issue(stored_value=MappingProxyType({"type": "work"}))}) == 2


def test_structured_evidence_hashes_the_way_it_compares() -> None:
    # A read-only mapping compares by member rather than by member order and is
    # itself unhashable, so a hash inherited from the field tuple would either
    # refuse the issue outright or disagree with equality — and an issue whose
    # hash disagrees with its equality silently fails to collapse in a frozenset.
    reordered = _issue(stored_value=MappingProxyType({"number": "555", "type": "home"}))
    assert reordered == _issue()
    assert hash(reordered) == hash(_issue())
    assert len({_issue(), reordered}) == 1

    # An array of objects carries the same requirement one level down: the
    # sequence's own order is part of the value while each element's member
    # order is not, so the hash has to descend rather than stop at the array.
    listed = _issue(stored_value=(MappingProxyType({"type": "home", "number": "555"}),))
    listed_reordered = _issue(stored_value=(MappingProxyType({"number": "555", "type": "home"}),))
    assert listed == listed_reordered
    assert hash(listed) == hash(listed_reordered)
    assert len({listed, listed_reordered, _issue()}) == 2


def test_a_hashed_issue_pickles_the_way_an_unhashed_equal_one_does() -> None:
    # The cache behind that hash is process-local: text hashing is seeded per
    # interpreter, so what one process cached is not what an equal issue
    # computes in another. Publication hashes every issue into a frozenset, so
    # a cache that travelled would always travel — and would arrive
    # contradicting the equality it exists to agree with, leaving a restored
    # issue missing from a set built where it was read. Structured evidence is
    # a read-only mapping and pickles nowhere, so the shapes that cross this
    # boundary are the scalar, array, and marker ones.
    hashed = _issue(stored_value=("555", MISSING_STORED_VALUE))
    hash(hashed)
    assert pickle.dumps(hashed) == pickle.dumps(_issue(stored_value=("555", MISSING_STORED_VALUE)))

    restored = cast("StoredDataIssue", pickle.loads(pickle.dumps(hashed)))
    assert restored == hashed
    assert len({restored, hashed}) == 1


def test_evidence_is_reachable_only_by_asking_for_it() -> None:
    # A diagnostic value with no authority is also a value nothing prints: it
    # must not reach a log line, an exception message, or a debugger's rendering
    # of the record that carries it merely because something formatted the
    # diagnosis around it.
    record = _customer({"id": 1, "name": "Ada", "address": {"city": "Berlin"}})
    (issue,) = record.issues
    assert issue.stored_value is MISSING_STORED_VALUE
    assert "MISSING_STORED_VALUE" not in repr(issue)
    assert "stored_value" not in repr(issue)
    assert "MISSING_STORED_VALUE" not in repr(record)
    assert "MISSING_STORED_VALUE" not in str(InvalidDataError((record,)))
