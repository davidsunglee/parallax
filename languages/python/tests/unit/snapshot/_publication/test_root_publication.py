"""One publication pass over a Page: realized reach, lazy origins, per-root
resets, and the failure boundary, in both representations and at both delivery
boundaries.

Page reach can include an overwritten arm or a claimant's losing slot. Such an
arm is judged and compared, so a projection conflict in it still refuses, but
it publishes nowhere, so a finding in it neither classifies nor refuses a root
whose carried views never reach it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, Final, Literal, cast

import pytest

from parallax.core._execution._concurrency import CONCURRENCY
from parallax.core.base import NeutralType, PresentDocument
from parallax.core.deep_fetch import IncludeTree
from parallax.core.entity import UNLOADED
from parallax.core.read_delivery import InvalidData
from parallax.core.read_delivery._page import Page, page_rows, shared_entity_state
from parallax.core.wire._codec import encode_managed_wire
from parallax.snapshot import (
    SnapshotConsistencyError,
    SnapshotMaterializationError,
    is_view_loaded,
)
from parallax.snapshot._inspection import RootConformance, snapshot_state_of
from parallax.snapshot._publication import _root, _typed, _wire
from parallax.snapshot._publication._root import RootView
from parallax.snapshot._publication._root_publication import publish_roots
from parallax.snapshot._publication._typed import TypedRootPublisher
from parallax.snapshot._publication._wire import (
    WireRootPublisher,
    read_evidence_of,
    stored_entity_of,
)
from tests._support.model_capabilities import graph_construction_for
from tests.unit._root_publication_support import each_root, observed
from tests.unit.snapshot._encoded_page_models import ENCODED_ACCOUNT, ENCODED_ORDERS, EncodedOrder
from tests.unit.snapshot._snapshot_page_support import PageFixture, identity_of, invalid_record

_NS: Final = "parallax.compatibility"
_ITEMS: Final = f"{_NS}.EncodedOrder.items"
_BY_CODE: Final = f"{_NS}.EncodedOrder.itemsByCode"
_ITEM_ORDER: Final = f"{_NS}.EncodedOrderItem.order"
_NARROWED: Final = "items[EncodedOrderItem]"
_UNDECODABLE: Final = "not-hex"
_WRONG_KIND: Final = PresentDocument("not-a-document")

type _Form = Literal["typed", "wire"]

_DELIVERY = pytest.mark.parametrize("atomic", [False, True], ids=["streamed", "atomic"])
_FORM = pytest.mark.parametrize("form", ["typed", "wire"])


def _order(
    fixture: PageFixture, order_id: int = 1, *, badge: str | None = None, address: object = None
) -> int:
    return fixture.node(
        "EncodedOrder",
        {"id": order_id, "name": f"order-{order_id}", "badge_hex": badge, "address": address},
    )


def _item(fixture: PageFixture, item_id: int, *, order_id: int = 1, code: str = "0c") -> int:
    return fixture.node("EncodedOrderItem", {"id": item_id, "order_id": order_id, "code_hex": code})


def _order_tree(fixture: PageFixture) -> IncludeTree:
    """Order with its items and by-code items, each item with its order."""
    return fixture.include_tree(
        "EncodedOrder",
        (0, _ITEMS, "EncodedOrderItem"),
        (1, _ITEM_ORDER, "EncodedOrder"),
        (0, _BY_CODE, "EncodedOrderItem"),
        (3, _ITEM_ORDER, "EncodedOrder"),
    )


def _published(
    fixture: PageFixture,
    form: _Form,
    *roots: int,
    atomic: bool,
    origins: Mapping[int, object] | None = None,
) -> tuple[object, ...]:
    held: Mapping[int, object] = {} if origins is None else origins
    if form == "typed":
        return fixture.materialize(*roots, atomic=atomic, origins=held)
    return fixture.materialize_wire(
        *roots, includes=_order_tree(fixture), atomic=atomic, origins=held
    )


def _field(form: _Form, value: object, name: str, typed_name: str | None = None) -> Any:
    if form == "typed":
        return getattr(value, typed_name or name)
    return cast("Mapping[str, object]", value)[name]


def _conforming(form: _Form, value: object) -> bool:
    if form == "typed":
        state = snapshot_state_of(value)
        assert state is not None
        return state.root_conformance is RootConformance.CONFORMING
    return stored_entity_of(cast("Any", value)) is not None


def _evidence(form: _Form, value: object) -> object:
    if form == "typed":
        state = snapshot_state_of(value)
        assert state is not None
        return state.read_evidence
    return read_evidence_of(cast("Any", value))


# --------------------------------------------------------------------------- #
# Realized reach: an arm the carried views discard publishes nowhere.          #
# --------------------------------------------------------------------------- #
def _overwritten_arm(*, invalid: Literal["discarded", "current"]) -> tuple[PageFixture, int]:
    """An order whose items view was written twice, the invalid item arm first
    when it is ``discarded`` and last when it is ``current``."""
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    order = _order(fixture)
    valid = _item(fixture, 11)
    broken = _item(fixture, 12, code=_UNDECODABLE)
    arms = (broken, valid) if invalid == "discarded" else (valid, broken)
    for arm in arms:
        fixture.attach(order, _ITEMS, (arm,))
    return fixture, order


@_DELIVERY
@_FORM
def test_a_discarded_invalid_arm_does_not_classify_the_valid_current_arm(
    form: _Form, atomic: bool
) -> None:
    fixture, order = _overwritten_arm(invalid="discarded")

    (published,) = _published(fixture, form, order, atomic=atomic)

    assert not isinstance(published, InvalidData)
    assert [_field(form, item, "id") for item in _field(form, published, "items")] == [11]
    assert _conforming(form, published)
    assert all(_conforming(form, item) for item in _field(form, published, "items"))


@_DELIVERY
@_FORM
def test_a_current_invalid_arm_still_classifies_its_root(form: _Form, atomic: bool) -> None:
    fixture, order = _overwritten_arm(invalid="current")

    (published,) = _published(fixture, form, order, atomic=atomic)

    record = invalid_record(published)
    assert record.data is None
    (issue,) = record.issues
    assert issue.code == "stored-data-leaf-undecodable"
    assert issue.entity == identity_of(fixture.model, "EncodedOrderItem")
    assert issue.stored_value == _UNDECODABLE


@_DELIVERY
@_FORM
def test_a_projection_conflict_in_a_discarded_arm_still_refuses(form: _Form, atomic: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    order = _order(fixture)
    discarded = _item(fixture, 11, code="0d")
    current = _item(fixture, 11)
    fixture.attach(order, _ITEMS, (discarded,))
    fixture.attach(order, _ITEMS, (current,))

    with pytest.raises(SnapshotConsistencyError) as conflict:
        _published(fixture, form, order, atomic=atomic)

    assert conflict.value.code == "snapshot-fetched-row-conflict"
    assert type(conflict.value) is SnapshotConsistencyError


def _continuing_past_a_discarded_arm() -> tuple[PageFixture, int, int]:
    """An order reaching item 11 through ``items`` and item 12 through
    ``itemsByCode``, each item's order cycling back to it. Item 11's order view
    was first written to an invalid order the later write discards, so Page
    reach visits that order before item 12."""
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS, _BY_CODE, _ITEM_ORDER)
    order = _order(fixture)
    first = _item(fixture, 11)
    second = _item(fixture, 12)
    discarded = _order(fixture, 2, badge=_UNDECODABLE)
    fixture.attach(order, _ITEMS, (first,))
    fixture.attach(order, _BY_CODE, (second,))
    fixture.attach(first, _ITEM_ORDER, discarded)
    fixture.attach(first, _ITEM_ORDER, order)
    fixture.attach(second, _ITEM_ORDER, order)
    return fixture, order, discarded


@_DELIVERY
@_FORM
def test_continuation_views_survive_compacting_a_discarded_arm(form: _Form, atomic: bool) -> None:
    fixture, order, _discarded = _continuing_past_a_discarded_arm()

    (published,) = _published(fixture, form, order, atomic=atomic)

    assert _conforming(form, published)
    (first,) = _field(form, published, "items")
    (second,) = _field(form, published, "itemsByCode", "items_by_code")
    assert (_field(form, first, "id"), _field(form, second, "id")) == (11, 12)
    if form == "typed":
        assert first.order is published
        assert second.order is published
    else:
        assert _field(form, first, "order")["id"] == 1
        assert _field(form, second, "order")["id"] == 1


def test_compaction_renumbers_every_carried_reference_and_keeps_full_reach() -> None:
    fixture, order, discarded = _continuing_past_a_discarded_arm()

    (root,) = fixture.observed_roots(order)

    assert root.names == ["EncodedOrder", "EncodedOrderItem", "EncodedOrderItem"]
    assert not root.has_issues
    items = root.view_layouts[0].index_of[fixture.view_key(_ITEMS)]
    by_code = root.view_layouts[0].index_of[fixture.view_key(_BY_CODE)]
    item_order = root.view_layouts[1].index_of[fixture.view_key(_ITEM_ORDER)]
    assert (root.view(0, items), root.view(0, by_code)) == ((1,), (2,))
    assert root.view(1, item_order) == root.view(2, item_order) == 0
    assert discarded in root.reached
    assert len(root.reached) == 4


@_DELIVERY
@_FORM
def test_a_back_reference_survives_compacting_a_discarded_arm(form: _Form, atomic: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS, references={_ITEM_ORDER: ("EncodedOrder",)})
    order = _order(fixture)
    discarded = _item(fixture, 12, code=_UNDECODABLE)
    current = _item(fixture, 11)
    fixture.attach(order, _ITEMS, (discarded,))
    fixture.attach(order, _ITEMS, (current,))
    for item in (discarded, current):
        fixture.attach_reference(item, _ITEM_ORDER, "EncodedOrder", "EncodedOrderItem.orderId")

    (published,) = _published(fixture, form, order, atomic=atomic)

    assert _conforming(form, published)
    (item,) = _field(form, published, "items")
    assert _field(form, item, "id") == 11
    if form == "typed":
        assert item.order is published
    else:
        assert _field(form, item, "order")["id"] == 1


@_DELIVERY
@_FORM
def test_a_claimants_losing_slot_does_not_classify_the_merged_node(
    form: _Form, atomic: bool
) -> None:
    # Two equal projections of item 11 merge into one node, which carries the
    # first claimant's order view; the second claimant's invalid order is reached
    # and judged but published nowhere.
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS, _BY_CODE, _ITEM_ORDER)
    order = _order(fixture)
    first = _item(fixture, 11)
    second = _item(fixture, 11)
    losing = _order(fixture, 2, badge=_UNDECODABLE)
    fixture.attach(order, _ITEMS, (first,))
    fixture.attach(order, _BY_CODE, (second,))
    fixture.attach(first, _ITEM_ORDER, order)
    fixture.attach(second, _ITEM_ORDER, losing)

    (published,) = _published(fixture, form, order, atomic=atomic)

    assert _conforming(form, published)
    (item,) = _field(form, published, "items")
    (aliased,) = _field(form, published, "itemsByCode", "items_by_code")
    if form == "typed":
        assert item is aliased
        assert item.order is published
    else:
        assert item == aliased
        assert _field(form, item, "order")["id"] == 1


# --------------------------------------------------------------------------- #
# Origins: acquired after judgment, for conforming roots, before release.      #
# --------------------------------------------------------------------------- #
class _RecordedOrigins(Mapping[int, object]):
    """A lazy origin map that records each projection it is asked for and
    refuses one asked before its state is judged or after its rows released."""

    def __init__(self, *, failing: bool = False) -> None:
        self.page: Page | None = None
        self.lookups: list[int] = []
        self._failing = failing

    def __getitem__(self, projection: int) -> object:
        if self._failing:
            raise RuntimeError("origin resolution failed")
        rows = page_rows(self.page)
        assert rows.keys[projection] is not None, f"projection {projection} was released"
        assert shared_entity_state(rows, projection) is not None, (
            f"projection {projection} is unjudged"
        )
        self.lookups.append(projection)
        return ("evidence", projection)

    def __iter__(self) -> Iterator[int]:
        return iter(())

    def __len__(self) -> int:
        return 0


def _origins_for(fixture: PageFixture, *roots: int, failing: bool = False) -> _RecordedOrigins:
    origins = _RecordedOrigins(failing=failing)
    origins.page = fixture.page(*roots)
    return origins


@pytest.mark.parametrize("valid_first", [True, False], ids=["valid-first", "invalid-first"])
@_DELIVERY
@_FORM
def test_only_a_conforming_root_acquires_origins_for_a_state_it_shares(
    form: _Form, atomic: bool, valid_first: bool
) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    valid = _order(fixture)
    invalid = _order(fixture, 2, address=_WRONG_KIND)
    shared = _item(fixture, 11)
    fixture.attach(valid, _ITEMS, (shared,))
    fixture.attach(invalid, _ITEMS, (shared,))
    roots = (valid, invalid) if valid_first else (invalid, valid)
    origins = _origins_for(fixture, *roots)

    published = _published(fixture, form, *roots, atomic=atomic, origins=origins)

    conforming, record = published if valid_first else reversed(published)
    record = invalid_record(record)
    assert sorted(origins.lookups) == [valid, shared]
    assert _evidence(form, conforming) == ("evidence", valid)
    (item,) = _field(form, conforming, "items")
    assert _evidence(form, item) == ("evidence", shared)
    assert record.data is not None
    (hydrated,) = _field(form, record.data, "items")
    assert _evidence(form, record.data) is None
    assert _evidence(form, hydrated) is None
    assert hydrated is not item


@_DELIVERY
@_FORM
def test_a_discarded_issue_bearing_arm_acquires_no_origin(form: _Form, atomic: bool) -> None:
    fixture, order, discarded = _continuing_past_a_discarded_arm()
    origins = _origins_for(fixture, order)

    (published,) = _published(fixture, form, order, atomic=atomic, origins=origins)

    assert discarded not in origins.lookups
    assert len(origins.lookups) == 3
    assert _evidence(form, published) == ("evidence", order)


@_FORM
def test_a_deferring_atomic_page_acquires_origins_after_judging_and_before_release(
    form: _Form,
) -> None:
    # Versioned roots defer their states and release each projection at its
    # last use, so a lookup made before judging or after release would refuse.
    fixture = PageFixture(ENCODED_ACCOUNT)
    accounts = tuple(
        fixture.node("EncodedAccount", {"id": key, "token_hex": "0a", "version": 1})
        for key in (1, 2, 1)
    )
    origins = _origins_for(fixture, *accounts)

    if form == "typed":
        published = fixture.materialize(*accounts, atomic=True, origins=origins)
    else:
        published = fixture.materialize_wire(*accounts, atomic=True, origins=origins)

    assert origins.lookups == list(accounts)
    assert [_evidence(form, root) for root in published] == [
        ("evidence", account) for account in accounts
    ]


@_DELIVERY
@_FORM
def test_an_origin_resolution_failure_propagates_unwrapped(form: _Form, atomic: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS)
    order = _order(fixture)
    origins = _origins_for(fixture, order, failing=True)

    with pytest.raises(RuntimeError, match="origin resolution failed") as failure:
        _published(fixture, form, order, atomic=atomic, origins=origins)

    assert type(failure.value) is RuntimeError


# --------------------------------------------------------------------------- #
# Alternating roots: every per-root fact is reset, and no value is shared.     #
# --------------------------------------------------------------------------- #
def _alternating() -> tuple[PageFixture, tuple[int, ...]]:
    """Roots differing in size, concrete, findings, and arms: an order whose
    items and by-code items reach one diamond of items with a narrowed view
    and a cycle; an order whose own badge never decodes; an item root with a
    null order; an order with empty items and unloaded by-code items; and an
    order whose address is the wrong kind, which still hydrates."""
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS, _BY_CODE, (_ITEMS, _NARROWED), _ITEM_ORDER)
    diamond = _order(fixture)
    first = _item(fixture, 11)
    second = _item(fixture, 12)
    fixture.attach(diamond, _ITEMS, (first, second))
    fixture.attach(diamond, _BY_CODE, (second, first))
    fixture.attach(diamond, _ITEMS, (first,), narrowed=_NARROWED)
    fixture.attach(first, _ITEM_ORDER, diamond)
    fixture.attach(second, _ITEM_ORDER, diamond)
    broken = _order(fixture, 2, badge=_UNDECODABLE)
    fixture.attach(broken, _ITEMS, (_item(fixture, 21, order_id=2),))
    orphan = _item(fixture, 31, order_id=9)
    fixture.attach(orphan, _ITEM_ORDER, None)
    empty = _order(fixture, 4)
    fixture.attach(empty, _ITEMS, ())
    hydrating = _order(fixture, 5, address=_WRONG_KIND)
    fixture.attach(hydrating, _ITEMS, (_item(fixture, 51, order_id=5),))
    return fixture, (diamond, broken, orphan, empty, hydrating)


def _typed_shape(value: object) -> object:
    if isinstance(value, InvalidData):
        record = cast("InvalidData[Any]", value)
        data = None if record.data is None else _typed_shape(record.data)
        return ("invalid", record.ordinal, data)
    entity = cast("Any", value)
    if type(value).__name__ == "EncodedOrderItem":
        order = entity.order
        return ("item", entity.id, None if order is None else order.id)
    return (
        "order",
        entity.id,
        tuple(item.id for item in entity.items),
        tuple(item.id for item in entity.items_by_code)
        if is_view_loaded(entity, EncodedOrder.items_by_code)
        else "unloaded",
    )


def _typed_objects(value: object) -> list[object]:
    if isinstance(value, InvalidData):
        data = cast("InvalidData[Any]", value).data
        return [] if data is None else _typed_objects(data)
    entity = cast("Any", value)
    if type(value).__name__ == "EncodedOrderItem":
        return [entity] if entity.order is None else [entity, entity.order]
    return [entity, *entity.items]


@pytest.mark.parametrize("reverse", [False, True], ids=["valid-first", "invalid-first"])
@_DELIVERY
def test_alternating_typed_roots_reset_every_per_root_fact(atomic: bool, reverse: bool) -> None:
    fixture, roots = _alternating()
    ordered = tuple(reversed(roots)) if reverse else roots

    published = fixture.materialize(*ordered, atomic=atomic)

    def expected(root: int, ordinal: int) -> object:
        return {
            roots[0]: ("order", 1, (11, 12), (12, 11)),
            roots[1]: ("invalid", ordinal, None),
            roots[2]: ("item", 31, None),
            roots[3]: ("order", 4, (), "unloaded"),
            roots[4]: ("invalid", ordinal, ("order", 5, (51,), "unloaded")),
        }[root]

    assert [_typed_shape(value) for value in published] == [
        expected(root, ordinal) for ordinal, root in enumerate(ordered)
    ]
    diamond = cast("Any", published[ordered.index(roots[0])])
    assert diamond.items[0] is diamond.items_by_code[1]
    assert diamond.items[0].order is diamond
    narrowed = snapshot_state_of(diamond)
    assert narrowed is not None
    assert narrowed.views[_NARROWED] == (diamond.items[0],)
    _assert_disjoint([{id(node) for node in _typed_objects(value)} for value in published])


@pytest.mark.parametrize("reverse", [False, True], ids=["valid-first", "invalid-first"])
@_DELIVERY
def test_alternating_wire_roots_reset_every_per_root_fact(atomic: bool, reverse: bool) -> None:
    fixture, roots = _alternating()
    ordered = tuple(reversed(roots)) if reverse else roots
    includes = fixture.include_tree(
        "EncodedOrder",
        (0, _ITEMS, "EncodedOrderItem"),
        (1, _ITEM_ORDER, "EncodedOrder"),
        (0, _BY_CODE, "EncodedOrderItem"),
        (0, _ITEMS, "EncodedOrderItem", _NARROWED),
        also=("EncodedOrderItem",),
    )

    published = fixture.materialize_wire(*ordered, includes=includes, atomic=atomic)

    diamond = cast("Mapping[str, Any]", published[ordered.index(roots[0])])
    assert [item["id"] for item in diamond["items"]] == [11, 12]
    assert [item["id"] for item in diamond["itemsByCode"]] == [12, 11]
    assert [item["id"] for item in diamond[_NARROWED]] == [11]
    assert diamond["items"][0]["order"]["id"] == 1
    assert invalid_record(published[ordered.index(roots[1])]).data is None
    orphan = cast("Mapping[str, Any]", published[ordered.index(roots[2])])
    assert orphan["id"] == 31
    empty = cast("Mapping[str, Any]", published[ordered.index(roots[3])])
    assert empty["items"] == []
    assert "itemsByCode" not in empty
    hydrated = cast("Mapping[str, Any]", invalid_record(published[ordered.index(roots[4])]).data)
    assert [item["id"] for item in hydrated["items"]] == [51]
    assert stored_entity_of(cast("Any", hydrated)) is None
    assert all(
        stored_entity_of(cast("Any", published[ordered.index(root)])) is not None
        for root in (roots[0], roots[2], roots[3])
    )
    _assert_disjoint(
        [
            {id(node) for node in _wire_nodes(cast("Mapping[str, Any]", value))}
            for value in (
                cast("InvalidData[Any]", root).data if isinstance(root, InvalidData) else root
                for root in published
            )
            if value is not None
        ]
    )


def _assert_disjoint(roots: list[set[int]]) -> None:
    """No object one published root reaches is reached by another."""
    every = {node for nodes in roots for node in nodes}
    assert sum(len(nodes) for nodes in roots) == len(every)


def _wire_nodes(node: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield node
    for key in ("items", "itemsByCode", _NARROWED):
        for child in node.get(key, ()):
            yield from _wire_nodes(child)
    order = node.get("order")
    if order is not None:
        yield from _wire_nodes(order)


class _Boom(Exception):
    pass


def test_the_wire_walk_forgets_a_root_whose_rendering_failed() -> None:
    # Item 12's code refuses to encode after item 11 rendered, so a memo kept
    # across roots would answer the next root's item from the failed root.
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    failed = _order(fixture)
    fixture.attach(failed, _ITEMS, (_item(fixture, 11), _item(fixture, 12, code="0d")))
    later = _order(fixture, 2)
    fixture.attach(later, _ITEMS, (_item(fixture, 21, order_id=2),))
    page = fixture.page(failed, later)

    def encode(neutral_type: NeutralType, value: object) -> object:
        if value == b"\x0d":
            raise _Boom
        return encode_managed_wire(neutral_type, cast("Any", value))

    includes = fixture.include_tree("EncodedOrder", (0, _ITEMS, "EncodedOrderItem"))
    publisher = WireRootPublisher(fixture.model, CONCURRENCY, includes, encode)

    def publish_root(root: RootView, ordinal: int) -> tuple[object, ...]:
        try:
            return publisher(root, ordinal)
        except _Boom:
            return ("failed",)

    first, second = publish_roots(page, publish_root, fixture.model)

    assert first == "failed"
    assert [item["id"] for item in cast("Any", second)["items"]] == [21]


# --------------------------------------------------------------------------- #
# The Typed boundary wraps publisher-side failures only.                      #
# --------------------------------------------------------------------------- #
def _two_orders() -> tuple[PageFixture, tuple[int, int]]:
    fixture = PageFixture(ENCODED_ORDERS)
    return fixture, (_order(fixture), _order(fixture, 2))


def _failing_second_call[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    calls = 0

    def failing(*args: P.args, **kwargs: P.kwargs) -> R:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("the second root failed")
        return function(*args, **kwargs)

    return failing


def _publish_until_failure(
    fixture: PageFixture, roots: tuple[int, ...], form: _Form, *, atomic: bool
) -> tuple[list[object], BaseException]:
    received: list[object] = []
    if form == "typed":
        stream = fixture.materialize_stream(*roots, atomic=atomic)
    else:
        stream = fixture.materialize_wire_stream(*roots, atomic=atomic)
    with pytest.raises(Exception) as failure:
        received.extend(stream)
    return received, failure.value


@pytest.mark.parametrize("seam", ["classification", "construction"])
@_DELIVERY
def test_a_typed_publisher_failure_is_wrapped_once_with_its_cause(
    monkeypatch: pytest.MonkeyPatch, seam: str, atomic: bool
) -> None:
    fixture, roots = _two_orders()
    if seam == "classification":
        monkeypatch.setattr(
            _typed, "classify_root", _failing_second_call(vars(_typed)["classify_root"])
        )
    else:
        monkeypatch.setattr(
            TypedRootPublisher,
            "_lifecycle_states",
            _failing_second_call(vars(TypedRootPublisher)["_lifecycle_states"]),
        )

    received, failure = _publish_until_failure(fixture, roots, "typed", atomic=atomic)

    assert type(failure) is SnapshotMaterializationError
    assert type(failure.cause) is RuntimeError
    assert failure.__cause__ is failure.cause
    assert [cast("Any", value).id for value in received] == ([] if atomic else [1])


@pytest.mark.parametrize(
    ("seam", "form"),
    [("decoding", "typed"), ("decoding", "wire"), ("classification", "wire")],
)
@_DELIVERY
def test_a_pass_side_or_wire_failure_propagates_unwrapped(
    monkeypatch: pytest.MonkeyPatch, seam: str, form: _Form, atomic: bool
) -> None:
    fixture, roots = _two_orders()
    if seam == "decoding":
        monkeypatch.setattr(
            _root, "entity_state", _failing_second_call(vars(_root)["entity_state"])
        )
    else:
        monkeypatch.setattr(
            _wire, "classify_root", _failing_second_call(vars(_wire)["classify_root"])
        )

    received, failure = _publish_until_failure(fixture, roots, form, atomic=atomic)

    assert type(failure) is RuntimeError
    assert len(received) == (0 if atomic else 1)


@pytest.mark.parametrize("hydrates", [True, False], ids=["hydrating", "non-hydrating"])
def test_a_typed_publisher_clears_its_root_bookkeeping_however_a_root_ends(
    hydrates: bool,
) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    order = _order(fixture, address=_WRONG_KIND if hydrates else None, badge=None)
    fixture.attach(order, _ITEMS, (_item(fixture, 11, code="0c" if hydrates else _UNDECODABLE),))
    publisher = TypedRootPublisher(
        fixture.model, graph_construction_for(ENCODED_ORDERS), CONCURRENCY
    )
    held: list[RootView | None] = []

    def publish_root(root: RootView, ordinal: int) -> tuple[object, ...]:
        published = publisher(root, ordinal)
        held.append(publisher._root)  # pyright: ignore[reportPrivateUsage]
        return published

    (published,) = publish_roots(fixture.page(order), publish_root, fixture.model)

    assert (invalid_record(published).data is not None) is hydrates
    assert held == [None]


def test_a_typed_publisher_clears_its_root_bookkeeping_when_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    order = _order(fixture)
    fixture.attach(order, _ITEMS, (_item(fixture, 11),))
    publisher = TypedRootPublisher(
        fixture.model, graph_construction_for(ENCODED_ORDERS), CONCURRENCY
    )

    def failing_state(*_args: object) -> object:
        raise _Boom

    monkeypatch.setattr(TypedRootPublisher, "_lifecycle_states", failing_state)
    with pytest.raises(_Boom):
        list(publish_roots(fixture.page(order), publisher, fixture.model))

    assert publisher._root is None  # pyright: ignore[reportPrivateUsage]


# --------------------------------------------------------------------------- #
# A Root View is borrowed: only what a callback copies outlives the call.      #
# --------------------------------------------------------------------------- #
def test_a_root_view_answers_broad_relationship_values_as_node_indices() -> None:
    # The graph Typed publication hands Entity Graph Construction: a loaded
    # to-many is the tuple of this root's nodes in carried order, and a direction
    # no fetched row loaded is the unloaded sentinel.
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    order = _order(fixture)
    fixture.attach(order, _ITEMS, (_item(fixture, 11), _item(fixture, 12)))

    answered = each_root(
        fixture.page(order),
        fixture.model,
        lambda root, _ordinal: [root.relationship_values(node) for node in range(len(root))],
    )

    assert answered == [[((1, 2), UNLOADED), (UNLOADED,), (UNLOADED,)]]


def test_a_retained_root_view_answers_for_the_last_root_while_copies_survive() -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    first = _order(fixture)
    fixture.attach(first, _ITEMS, (_item(fixture, 11), _item(fixture, 12)))
    second = _item(fixture, 31, order_id=9)
    page = fixture.page(first, second)

    retained: list[RootView] = []

    def inspect(root: RootView, ordinal: int) -> object:
        retained.append(root)
        return observed(root, ordinal)

    copies = each_root(page, fixture.model, inspect)

    assert retained[0] is retained[1]
    assert [len(retained[0])] * 2 == [1, 1]
    assert [copy.names for copy in cast("list[Any]", copies)] == [
        ["EncodedOrder", "EncodedOrderItem", "EncodedOrderItem"],
        ["EncodedOrderItem"],
    ]


@_FORM
def test_a_zero_root_atomic_page_still_releases_its_storage(form: _Form) -> None:
    fixture = PageFixture(ENCODED_ORDERS)
    _order(fixture)
    page = fixture.page()

    if form == "typed":
        assert fixture.materialize(atomic=True) == ()
    else:
        assert fixture.materialize_wire(atomic=True) == ()

    rows = page_rows(page)
    assert (list(rows.layouts), list(rows.member_rows)) == ([], [])
