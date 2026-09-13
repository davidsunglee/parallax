"""Aggregate observability at the shared Page and Root View delivery seam."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from parallax.conformance.story_models import ORDERS_MODEL
from parallax.core import deep_fetch
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.object_query import deserialize
from parallax.core.sql_gen._compile import compile_read
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle._materialization import (
    FlatPageRead,
    MaterializationObserver,
    Materializer,
)
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.materialize import Page, PageBuilder, RootView
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema
from tests.unit.snapshot._snapshot_page_support import identity_of, layout_of


class _RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    def prepared(self, levels: int) -> None:
        self.events.append(("prepared", levels))

    def statement_rendered(self, level: int) -> None:
        self.events.append(("statement_rendered", level))

    def statement_executed(self, level: int, rows: int) -> None:
        del level
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


def _context() -> LevelContext:
    model = model_of(ORDERS_MODEL)
    identity = identity_of(model, "Order")
    return LevelContext(layout_of(model, identity))


def _row(order_id: int) -> dict[str, object]:
    return {
        "id": order_id,
        "name": f"customer-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }


def _page(observer: MaterializationObserver, *order_ids: int) -> Page:
    builder = PageBuilder(ViewSchema.of(), observer)
    roots = tuple(
        convert_row(_row(order_id), _context(), builder, source=ROOT_LEVEL)
        for order_id in order_ids
    )
    return builder.finish(roots, Pin())


def _publish(page: Page) -> Callable[[RootView, int], Iterator[object]]:
    def publish(_root: RootView, position: int) -> Iterator[object]:
        yield position

    return publish


def test_read_page_and_roots_expose_only_aggregate_delivery_cadence() -> None:
    observer = _RecordingObserver()
    materializer = Materializer(observer)

    meta = model_of(ORDERS_MODEL)
    model = CatalogedModel(meta)
    query = preflight(
        deserialize({"target": "Order", "predicate": {"all": {}}}),
        model=meta,
        form="graph",
    )
    plan = deep_fetch.plan(query, meta, projection=deep_fetch.ReadProjectionRequest("all", True))
    compiled = compile_read(plan.root, meta, POSTGRES, result_form="instance")
    rows = tuple(tuple(_row(1)[key] for key in compiled.result_keys) for _ in range(2))

    page = materializer.read_page(FlatPageRead(model, compiled, lambda: rows, Pin())).page
    assert list(materializer.roots(page, _publish(page))) == [0, 1]
    assert observer.events == [
        ("prepared", 1),
        ("statement_rendered", ROOT_LEVEL),
        ("statement_executed", 2),
        ("states_decoded", 1),
        ("occurrences_reached", 1),
        ("root_published", 0),
        ("states_shared", 1),
        ("occurrences_reached", 1),
        ("root_published", 1),
    ]
    assert all(type(value) is int for _event, value in observer.events)


def test_root_publication_requires_one_pin_per_page_root() -> None:
    observer = _RecordingObserver()
    page = _page(observer, 1)
    with pytest.raises(ValueError, match="pin count must match"):
        list(Materializer(observer).roots(page, _publish(page), pins=()))


def test_eager_and_streamed_pages_report_the_same_publication_totals() -> None:
    eager = _RecordingObserver()
    eager_page = _page(eager, 1, 2)
    assert list(Materializer(eager).roots(eager_page, _publish(eager_page))) == [0, 1]

    streamed = _RecordingObserver()
    ordinal = 0
    for order_id in (1, 2):
        page = _page(streamed, order_id)
        assert list(Materializer(streamed).roots(page, _publish(page), ordinal_offset=ordinal)) == [
            0
        ]
        ordinal += page.root_count

    totals = {"occurrences_reached": 2, "states_decoded": 2}
    for event, expected in totals.items():
        assert sum(value for name, value in eager.events if name == event) == expected
        assert sum(value for name, value in streamed.events if name == event) == expected
    assert [value for name, value in eager.events if name == "root_published"] == [0, 1]
    assert [value for name, value in streamed.events if name == "root_published"] == [0, 1]
