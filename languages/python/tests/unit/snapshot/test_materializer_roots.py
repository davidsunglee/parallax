"""Page-wide Entity State and root-local Snapshot publication."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest

from parallax.conformance.story_models import ORDERS_MODEL
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.temporal_read import Pin
from parallax.snapshot import SnapshotConsistencyError
from parallax.snapshot.materialize import PageBuilder, RootView, _convert
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._page import InvalidRootInput, page_rows
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema
from tests.unit.snapshot._snapshot_graph_support import GraphFixture, identity_of, layout_of


def _order(order_id: object, name: str = "Ada") -> dict[str, object]:
    return {
        "id": order_id,
        "name": name,
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }


def _context() -> LevelContext:
    meta = model_of(ORDERS_MODEL)
    identity = identity_of(meta, "Order")
    return LevelContext(layout_of(meta, identity))


def _page(
    occurrences: tuple[tuple[int, dict[str, object]], ...],
) -> tuple[object, tuple[int, ...]]:
    source_count = max((source for source, _row in occurrences), default=0) + 1
    builder = PageBuilder(ViewSchema(tuple(() for _ in range(source_count))))
    roots = tuple(
        convert_row(row, _context(), builder, source=source) for source, row in occurrences
    )
    return builder.finish(roots, Pin()), roots


def test_equal_witnesses_decode_once_and_share_one_page_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    decode = _convert._decode_row  # pyright: ignore[reportPrivateUsage]

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return decode(*args, **kwargs)

    monkeypatch.setattr(_convert, "_decode_row", counting)
    page, _roots = _page(((ROOT_LEVEL, _order(1)), (ROOT_LEVEL, _order(1))))
    assert calls == 0

    first = RootView(cast("Any", page), 0)
    second = RootView(cast("Any", page), 1)

    assert calls == 1
    assert len(cast("Any", page).judged_states) == 1
    assert first.member_values(0) is second.member_values(0)


def test_unequal_witnesses_raise_one_order_independent_projection_conflict() -> None:
    def conflict(rows: tuple[tuple[int, dict[str, object]], ...]) -> SnapshotConsistencyError:
        page, _roots = _page(rows)
        with pytest.raises(SnapshotConsistencyError) as raised:
            RootView(cast("Any", page), 0)
        return raised.value

    forward = conflict(((0, _order(1, "Ada")), (1, _order(1, "Grace"))))
    reverse = conflict(((1, _order(1, "Grace")), (0, _order(1, "Ada"))))

    expected_member = AttributeIdentity(EntityIdentity("parallax.compatibility", "Order"), "name")
    assert forward.code == reverse.code == "snapshot-projection-conflict"
    assert forward.object_key == reverse.object_key
    assert forward.coordinates == reverse.coordinates == ()
    assert forward.members == reverse.members == (expected_member,)
    assert forward.occurrences == reverse.occurrences == ((0, 0), (1, 0))
    assert "Ada" not in str(forward) and "Grace" not in str(forward)


def test_keyless_occurrences_remain_distinct_invalid_root_positions() -> None:
    page, _roots = _page(((0, _order(None)), (0, _order(None))))
    roots = page_rows(cast("Any", page)).roots
    assert all(isinstance(root, InvalidRootInput) for root in roots)
    assert [cast("InvalidRootInput", root).ordinal for root in roots] == [0, 1]


def test_a_root_view_reaches_only_its_roots_nodes_and_unions_its_views() -> None:
    fixture = GraphFixture(ORDERS_MODEL, "Order.items", "Order.itemsByShipDate")
    first = fixture.node("Order", _order(1))
    second = fixture.node("Order", _order(2, "Grace"))
    item = fixture.node(
        "OrderItem",
        {"id": 10, "order_id": 1, "sku": "A-100", "quantity": 1, "shipped_on": None},
    )
    fixture.attach(first, "Order.items", (item,))
    fixture.attach(first, "Order.itemsByShipDate", (item,))
    fixture.attach(second, "Order.items", ())
    fixture.attach(second, "Order.itemsByShipDate", ())
    page = fixture.graph(first, second)

    first_view = RootView(page, 0)
    second_view = RootView(page, 1)

    assert [identity.name for identity in first_view.order] == ["Order", "OrderItem"]
    assert [identity.name for identity in second_view.order] == ["Order"]
    assert first_view.view(0, 0) == first_view.view(0, 1) == (1,)


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    def prepared(self, levels: int) -> None:
        self.events.append(("prepared", levels))

    def statement_rendered(self, level: int) -> None:
        self.events.append(("statement_rendered", level))

    def statement_executed(self, level: int, rows: int) -> None:
        self.events.append(("statement_executed", rows))

    def occurrences_reached(self, count: int) -> None:
        self.events.append(("occurrences_reached", count))

    def witnesses_compared(self, count: int) -> None:
        self.events.append(("witnesses_compared", count))

    def states_decoded(self) -> None:
        self.events.append(("states_decoded", 1))

    def states_shared(self) -> None:
        self.events.append(("states_shared", 1))

    def root_published(self, ordinal: int) -> None:
        self.events.append(("root_published", ordinal))


def publish_roots(page: Any, observer: RecordingObserver) -> Iterator[object]:
    from parallax.snapshot.handle._materialization import Materializer

    def publish() -> Iterator[object]:
        for position in range(page.root_count):
            RootView(page, position)
            yield position

    yield from Materializer(observer).roots(page, publish)


def test_root_zero_publishes_before_root_one_state_is_decoded() -> None:
    observer = RecordingObserver()
    builder = PageBuilder(ViewSchema.of(), observer)
    first = convert_row(_order(1), _context(), builder, source=ROOT_LEVEL)
    second = convert_row(_order(2), _context(), builder, source=ROOT_LEVEL)
    page = builder.finish((first, second), Pin())

    assert list(publish_roots(page, observer)) == [0, 1]
    relevant = [
        name for name, _value in observer.events if name in {"states_decoded", "root_published"}
    ]
    assert relevant == ["states_decoded", "root_published", "states_decoded", "root_published"]
