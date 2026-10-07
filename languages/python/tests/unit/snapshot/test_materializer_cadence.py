"""Aggregate observability at the shared Page and Root View delivery seam."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from parallax.conformance.story_models import ORDERS_MODEL
from parallax.core import deep_fetch
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.execution._concurrency import CONCURRENCY
from parallax.core.execution._preflight import preflight
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import deserialize
from parallax.core.read_delivery import _row_lane
from parallax.core.read_delivery._page import (
    INERT_OBSERVER,
    ROOT_LEVEL,
    EntityState,
    MaterializationObserver,
    Page,
    PageBuilder,
    PageRows,
    ViewSchema,
    page_cadence,
)
from parallax.core.read_delivery._page_reader import FlatPageRequest, PageReader
from parallax.core.read_delivery._row_converter import bind
from parallax.core.read_delivery._row_lane import (
    _published_rows,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.sql_gen._compile import CompiledRead, compile_read
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import RootView
from parallax.snapshot.materialize._publication import publish_roots
from tests.unit._prepared_read_support import bound_read
from tests.unit.snapshot._snapshot_page_support import RecordingObserver


def test_the_inert_observer_accepts_a_witness_comparison_total() -> None:
    INERT_OBSERVER.witnesses_compared(1)


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
    prepared = bound_read(model_of(ORDERS_MODEL), "Order")
    roots = tuple(
        prepared.convert_row(_row(order_id), builder, source=ROOT_LEVEL)[0]
        for order_id in order_ids
    )
    return builder.finish(roots, Pin())


def _publish(page: Page) -> Callable[[RootView, int], Iterator[object]]:
    def publish(_root: RootView, position: int) -> Iterator[object]:
        yield position

    return publish


def _order_read() -> tuple[Metamodel, CatalogedModel, CompiledRead]:
    meta = model_of(ORDERS_MODEL)
    query = preflight(
        deserialize({"target": "Order", "predicate": {"all": {}}}),
        model=meta,
        form="graph",
    )
    plan = deep_fetch.plan(query, meta, projection=deep_fetch.ReadProjectionRequest("all", True))
    return (
        meta,
        CatalogedModel(meta),
        compile_read(plan.root, meta, POSTGRES, result_form="instance"),
    )


def test_read_page_and_roots_expose_only_aggregate_delivery_cadence() -> None:
    observer = RecordingObserver()
    materializer = PageReader(observer)
    meta, model, compiled = _order_read()
    rows = tuple(tuple(_row(1)[key] for key in compiled.result_keys) for _ in range(2))

    stage = materializer.read_page(FlatPageRequest(model, compiled, lambda: rows, Pin()))

    assert page_cadence(stage.page) is observer
    assert (
        len(_published_rows(stage, meta, CONCURRENCY, bind(model, compiled).row_publisher())) == 2
    )
    assert observer.events == [
        ("prepared", 1),
        ("statement_rendered", ROOT_LEVEL),
        ("statement_executed", 2),
        ("states_decoded", 1),
        ("occurrences_reached", 1),
        ("states_shared", 1),
        ("occurrences_reached", 1),
        ("root_published", 0),
        ("root_published", 1),
    ]
    assert all(type(value) is int for _event, value in observer.events)


def test_eager_row_publication_withholds_events_when_a_later_root_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = RecordingObserver()
    meta, model, compiled = _order_read()
    rows = tuple(tuple(_row(order_id)[key] for key in compiled.result_keys) for order_id in (1, 2))
    stage = PageReader(observer).read_page(FlatPageRequest(model, compiled, lambda: rows, Pin()))

    judged: list[int] = []
    state_for = vars(_row_lane)["state_for"]

    def fail_on_second_root(rows: PageRows, projection: int) -> EntityState:
        judged.append(projection)
        if len(judged) == 2:
            raise RuntimeError("later row failed")
        return state_for(rows, projection)

    monkeypatch.setattr(_row_lane, "state_for", fail_on_second_root)
    with pytest.raises(RuntimeError, match="later row failed"):
        _published_rows(stage, meta, CONCURRENCY, bind(model, compiled).row_publisher())

    assert [event for event in observer.events if event[0] == "root_published"] == []


def test_a_flat_page_read_without_an_observer_records_none_and_publishes_inertly() -> None:
    _meta, model, compiled = _order_read()
    rows = (tuple(_row(1)[key] for key in compiled.result_keys),)

    stage = PageReader().read_page(FlatPageRequest(model, compiled, lambda: rows, Pin()))

    assert stage.page.observer is None
    assert page_cadence(stage.page) is INERT_OBSERVER


def test_root_publication_requires_one_pin_per_page_root() -> None:
    observer = RecordingObserver()
    page = _page(observer, 1)
    with pytest.raises(ValueError, match="pin count must match"):
        list(publish_roots(page, _publish(page), pins=()))


def test_eager_and_streamed_pages_report_the_same_publication_totals() -> None:
    eager = RecordingObserver()
    eager_page = _page(eager, 1, 2)
    assert list(publish_roots(eager_page, _publish(eager_page))) == [0, 1]

    streamed = RecordingObserver()
    ordinal = 0
    for order_id in (1, 2):
        page = _page(streamed, order_id)
        assert list(publish_roots(page, _publish(page), ordinal_offset=ordinal)) == [0]
        ordinal += page.root_count

    totals = {"occurrences_reached": 2, "states_decoded": 2}
    for event, expected in totals.items():
        assert sum(value for name, value in eager.events if name == event) == expected
        assert sum(value for name, value in streamed.events if name == event) == expected
    assert [value for name, value in eager.events if name == "root_published"] == [0, 1]
    assert [value for name, value in streamed.events if name == "root_published"] == [0, 1]


def test_atomic_publication_withholds_every_root_and_event_when_a_later_root_fails() -> None:
    # An eager result is one publication boundary. Even though root zero can be
    # prepared, root one's failure prevents either value or either publication
    # event from crossing that boundary.
    observer = RecordingObserver()
    page = _page(observer, 1, 2)

    def publish(_root: RootView, position: int) -> Iterator[object]:
        if position == 1:
            raise RuntimeError("later root failed")
        yield position

    received: list[object] = []
    with pytest.raises(RuntimeError, match="later root failed"):
        received.extend(publish_roots(page, publish, atomic=True, model=model_of(ORDERS_MODEL)))

    assert received == []
    assert [event for event in observer.events if event[0] == "root_published"] == []


def test_an_atomic_publication_needs_the_model_that_decides_state_deferral() -> None:
    observer = RecordingObserver()
    page = _page(observer, 1)
    with pytest.raises(ValueError, match="state deferral against its model"):
        list(publish_roots(page, _publish(page), atomic=True))
    assert observer.events == []


def test_incremental_publication_keeps_the_prefix_before_a_later_root_fails() -> None:
    # A streamed Page uses the same root seam without eager atomicity. Root zero
    # therefore crosses the boundary, and its event is emitted, before root one
    # fails; the already-delivered prefix remains observable.
    observer = RecordingObserver()
    page = _page(observer, 1, 2)
    received: list[object] = []

    def publish(_root: RootView, position: int) -> Iterator[object]:
        if position == 1:
            raise RuntimeError("later root failed")
        yield position

    roots = publish_roots(page, publish)
    received.append(next(roots))
    assert received == [0]
    with pytest.raises(RuntimeError, match="later root failed"):
        next(roots)

    assert [event for event in observer.events if event[0] == "root_published"] == [
        ("root_published", 0)
    ]
