"""The neutral stream delivery's lifecycle callbacks, against a scripted scope.

A lifecycle composing :class:`StreamDelivery` learns each Page's include tree
before that Page publishes anything, and releases its projection state where the
delivery ends. Whether that happens for a Page that publishes nothing, and
whether a failing release callback still leaves the remaining roots, the
publication, and the read released, are properties of the delivery alone, so
they are graded here with no lifecycle, port, or SQL under it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast

import pytest

from parallax.core import deep_fetch
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    ActivityTarget,
    StreamActivity,
    StreamBatchActivity,
)
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.object_query import ObjectQueryNode, deserialize, validate_object_query
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery import InvalidData, InvalidDataError, StoredDataIssue
from parallax.core.read_delivery._page import Page, PageBuilder, ViewSchema
from parallax.core.read_delivery._page_reader import (
    EagerPageResult,
    HistoryPageResult,
    StreamPageResult,
)
from parallax.core.read_delivery._paging import At, PagingPlan
from parallax.core.read_delivery._publication import RootsOf
from parallax.core.read_delivery._stream import StreamDelivery
from parallax.core.temporal_read import Pin, TemporalShape
from parallax.core.write_plan import ObjectKey
from tests.unit._corpus_model_support import model as accepted_model
from tests.unit._corpus_model_support import target as entity_of

ORDERS: Metamodel = accepted_model("orders")
_INCLUDES = cast("deep_fetch.IncludeTree", object())


class _CallbackFailed(Exception):
    pass


class _Stream:
    """Records how the delivery ended its observed stream."""

    def __init__(self) -> None:
        self.endings: list[object] = []

    def __enter__(self) -> _Stream:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
        /,
    ) -> None:
        self.endings.append(("closed", exc))

    def batch(self) -> StreamBatchActivity:
        return INERT.batch()

    def exhausted(self) -> None:
        self.endings.append("exhausted")


class _Read:
    """A begun read that owns nothing and brackets nothing."""

    def __init__(self) -> None:
        self.released: list[BaseException | None] = []
        self.stream = _Stream()

    @property
    def selected(self) -> str:
        return "selection"

    @property
    def meta(self) -> Metamodel:
        return ORDERS

    @property
    def edition(self) -> str:
        return "edition"

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> StreamActivity:
        del target, interface, batch_size
        return self.stream

    def release(self, failure: BaseException | None, /) -> None:
        self.released.append(failure)

    def advance[T](self, body: Callable[[], T], /) -> T:
        return body()


class _Scope:
    """Answers one scripted Page per request, each holding ``roots`` roots."""

    def __init__(self, read: _Read, *pages: int) -> None:
        self._read = read
        self._pages = list(pages)

    def begin(self) -> _Read:
        return self._read

    def resolved(self, read: _Read, node: ObjectQueryNode, /) -> ResolvedObjectQuery:
        del read
        return validate_object_query(entity_of(ORDERS, "Order"), node, ORDERS)

    def page(
        self,
        read: _Read,
        paging: PagingPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
        *,
        scanned: bool,
    ) -> StreamPageResult[object]:
        del read, paging, at, batch, scanned
        roots = self._pages.pop(0)
        builder = PageBuilder(ViewSchema.of())
        return StreamPageResult(
            page=builder.finish((), Pin()),
            includes=_INCLUDES,
            sources={},
            delivered=roots,
            resume_from=None,
            exhausted=not self._pages,
            tie=None,
        )


class _Publication:
    """Publishes ``roots`` placeholder values per Page and records its release.

    A root position named in ``invalid`` publishes that classified root instead.
    """

    def __init__(self, pages: list[int], invalid: Mapping[int, object] | None = None) -> None:
        self._pages = pages
        self._invalid = dict(invalid or {})
        self.released = 0

    @property
    def interface(self) -> ReadInterface:
        return "typed"

    @property
    def edition(self) -> str:
        return "edition"

    @property
    def roots_of(self) -> RootsOf[object]:
        pages = self._pages
        invalid = self._invalid

        def roots_of(
            page: Page,
            includes: deep_fetch.IncludeTree,
            /,
            *,
            atomic: bool = False,
            ordinal_offset: int = 0,
            sources: Mapping[int, object] = {},
            milestones: TemporalShape | None = None,
        ) -> Iterator[object]:
            del page, includes, atomic, sources, milestones
            for ordinal in range(ordinal_offset, ordinal_offset + pages.pop(0)):
                yield invalid.get(ordinal, ordinal)

        return roots_of

    @property
    def release(self) -> Callable[[], None]:
        def release() -> None:
            self.released += 1

        return release

    def from_find(self, result: EagerPageResult[object], /) -> object:  # pragma: no cover
        raise NotImplementedError

    def from_history(self, result: HistoryPageResult, /) -> object:  # pragma: no cover
        raise NotImplementedError


def _node() -> ObjectQueryNode:
    return deserialize({"target": "Order", "predicate": {"all": {}}})


def _delivery(
    pages: list[int],
    *,
    on_page_start: Callable[[deep_fetch.IncludeTree], None],
    on_release: Callable[[], None],
    invalid: Mapping[int, object] | None = None,
) -> tuple[StreamDelivery[Any, _Publication], _Read, _Publication]:
    read = _Read()
    publication = _Publication(list(pages), invalid)
    delivery: StreamDelivery[Any, _Publication] = StreamDelivery(
        _node(),
        cast("Any", _Scope(read, *pages)),
        lambda _selected: publication,
        batch_size=2,
        on_page_start=on_page_start,
        on_release=on_release,
    )
    return delivery, read, publication


def test_every_page_starts_before_it_publishes_including_one_that_publishes_nothing() -> None:
    events: list[object] = []

    def on_page_start(includes: deep_fetch.IncludeTree) -> None:
        assert includes is _INCLUDES
        events.append("page")

    delivery, _read, publication = _delivery(
        [2, 0], on_page_start=on_page_start, on_release=lambda: events.append("release")
    )
    assert delivery.enter() is publication
    for root in delivery.view(checked=True):
        assert delivery.paused_includes is _INCLUDES
        events.append(root)
    assert delivery.paused_includes is None
    delivery.close()

    # Exhaustion releases the projection where it is discovered, and the scope
    # exit releases it again: the lifecycle's release is idempotent.
    assert events == ["page", 0, 1, "page", "release", "release"]
    assert publication.released == 1


def test_a_failing_release_callback_still_releases_the_rest_of_an_early_closed_delivery() -> None:
    def failing_release() -> None:
        raise _CallbackFailed

    delivery, read, publication = _delivery(
        [2, 1], on_page_start=lambda _includes: None, on_release=failing_release
    )
    delivery.enter()
    view = delivery.view(checked=False)
    assert next(view) == 0

    with pytest.raises(_CallbackFailed):
        delivery.close()

    assert publication.released == 1
    assert read.released == [None]
    assert delivery.state == "closed"


def test_a_failing_release_callback_still_releases_the_publication_at_exhaustion() -> None:
    def failing_release() -> None:
        raise _CallbackFailed

    delivery, read, publication = _delivery(
        [1], on_page_start=lambda _includes: None, on_release=failing_release
    )
    delivery.enter()
    view = delivery.view(checked=False)
    assert next(view) == 0

    with pytest.raises(_CallbackFailed):
        next(view)

    assert publication.released == 1
    assert read.stream.endings == ["exhausted"]


def test_a_failing_release_callback_still_retains_the_failure_the_delivery_announces() -> None:
    def failing_release() -> None:
        raise _CallbackFailed

    delivery, read, publication = _delivery(
        [3],
        on_page_start=lambda _includes: None,
        on_release=failing_release,
        invalid={1: _invalid_root(1)},
    )
    delivery.enter()
    view = delivery.view(checked=False)
    assert next(view) == 0

    with pytest.raises(_CallbackFailed) as settling:
        next(view)
    refusal = settling.value.__context__
    assert isinstance(refusal, InvalidDataError)

    with pytest.raises(_CallbackFailed):
        delivery.close()

    assert publication.released == 1
    assert read.stream.endings == [("closed", refusal)]


def _invalid_root(ordinal: int) -> InvalidData[object]:
    order = entity_of(ORDERS, "Order").identity
    key = ObjectKey(order, (("id", ordinal),))
    issue = StoredDataIssue(
        "stored-data-leaf-undecodable",
        order,
        AttributeIdentity(order, "sku"),
        key,
        path=(),
        stored_value="not-a-sku",
    )
    return InvalidData(
        issues=frozenset({issue}),
        data=None,
        object_key=key,
        version=None,
        edge=None,
        ordinal=ordinal,
    )


def test_an_unchecked_view_refuses_an_invalid_root_after_the_prefix_before_it() -> None:
    invalid = _invalid_root(1)
    delivery, _read, publication = _delivery(
        [3], on_page_start=lambda _includes: None, on_release=lambda: None, invalid={1: invalid}
    )
    delivery.enter()
    view = delivery.view(checked=False)
    assert next(view) == 0

    with pytest.raises(InvalidDataError) as refused:
        next(view)

    assert refused.value.invalid_data == (invalid,)
    assert refused.value.edition == publication.edition
    assert publication.released == 1


def test_a_checked_view_publishes_an_invalid_root_in_band() -> None:
    invalid = _invalid_root(1)
    delivery, _read, _publication = _delivery(
        [3], on_page_start=lambda _includes: None, on_release=lambda: None, invalid={1: invalid}
    )
    delivery.enter()
    assert list(delivery.view(checked=True)) == [0, invalid, 2]
    delivery.close()
