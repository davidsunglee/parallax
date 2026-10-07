from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any, Final, Protocol, cast, overload

from parallax.core import deep_fetch
from parallax.core.base import ManagedValue, NeutralType
from parallax.core.entity import Entity, EntityGraphConstruction, RelationshipPath
from parallax.core.execution._publication import SelectedReadModel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.read_delivery import InvalidData, StreamStateError
from parallax.core.read_delivery._stream import StreamDelivery
from parallax.core.temporal_read import Pin
from parallax.snapshot._handle._read import (
    SnapshotPublication,
    projection_concrete,
    wire_position,
)
from parallax.snapshot._publication import _wire as wire_materialize
from parallax.snapshot._publication._wire import EntityReader, WireEntity, WireWalk
from parallax.snapshot._publication._wire_memo import WeakIdentityMemo

__all__ = ["SnapshotStream", "StreamExecution"]


class _PageWireEncoder(Protocol):
    def begin_page(self) -> None: ...

    def __call__(self, neutral_type: NeutralType, value: ManagedValue) -> object: ...

    def release(self) -> None: ...


class StreamExecution(Protocol):
    """The read execution a Snapshot Stream obtains its one delivery from.

    It refuses re-entry, lowers ``query`` with ``convert_query``, and judges the
    page size before the delivery exists; the delivery builds its publication
    with ``build_publication`` at entry and reports each Page and its release to
    the two callbacks.
    """

    def stream[Q](
        self,
        query: Q,
        batch_size: int,
        /,
        *,
        convert_query: Callable[[Q], ObjectQueryNode],
        build_publication: Callable[[SelectedReadModel], SnapshotPublication],
        on_page_start: Callable[[deep_fetch.IncludeTree], None],
        on_release: Callable[[], None],
    ) -> StreamDelivery[Any, SnapshotPublication]: ...


_CURRENT_PROJECTION_PAGE: Final = (
    "SnapshotStream.wire answers only while delivery is paused at a root of its current Page"
)


class _StreamWireProjection:
    __slots__ = ("_construction", "_encoder", "_includes", "_reader", "_walk")

    def __init__(
        self, construction: EntityGraphConstruction, includes: deep_fetch.IncludeTree
    ) -> None:
        self._construction = construction
        self._includes = includes
        self._reader: EntityReader | None = None
        self._walk: WireWalk[object] | None = None
        self._encoder: _PageWireEncoder | None = None

    def begin_page(self, includes: deep_fetch.IncludeTree) -> None:
        self._clear_entities()
        self._includes = includes
        if self._encoder is not None:
            self._encoder.begin_page()

    def project(
        self,
        value: object,
        at: RelationshipPath[Entity, Any] | None,
    ) -> WireEntity | InvalidData[WireEntity]:
        record: InvalidData[object] | None = (
            cast("InvalidData[object]", value) if isinstance(value, InvalidData) else None
        )
        node: object | None = record.data if record is not None else cast("object", value)
        concrete = None
        reader = self._reader
        if node is not None:
            if reader is None:
                reader = EntityReader(self._construction, operation="SnapshotStream.wire")
            concrete = projection_concrete(reader, node, operation="SnapshotStream.wire")
        position = wire_position(
            self._includes,
            self._construction.cataloged,
            at,
            operation="SnapshotStream.wire",
        )
        if node is None:
            return cast("InvalidData[WireEntity]", record)
        assert concrete is not None
        if not self._includes.admits(position, concrete):
            from parallax.snapshot._inspection import SnapshotInspectionError

            raise SnapshotInspectionError(
                code="snapshot-wire-at-concrete-mismatch",
                message=f"{concrete.canonical} is not admitted at requested position {position}",
                operation="SnapshotStream.wire",
                entity=concrete,
            )
        if self._reader is None:
            assert reader is not None
            self._reader = reader
        if self._walk is None:
            if self._encoder is None:
                self._encoder = wire_materialize.shared_wire_encoder()
                self._encoder.begin_page()
            reader = self._reader
            assert reader is not None
            self._walk = WireWalk(
                reader,
                self._includes,
                self._encoder,
                memo=WeakIdentityMemo[object](),
            )
        rendered = cast("WireEntity", self._walk.position(node, position))
        return (
            rendered
            if record is None
            else cast("InvalidData[WireEntity]", replace(record, data=rendered))
        )

    def release(self) -> None:
        self._clear_entities()
        if self._encoder is not None:
            self._encoder.release()
            self._encoder = None

    def _clear_entities(self) -> None:
        if self._walk is not None:
            self._walk.clear()
            self._walk = None
        if self._reader is not None:
            self._reader.clear()
            self._reader = None


class SnapshotStream[T]:
    """Scope-bound, single-pass delivery; enter before accessing any property.

    Entry adopts the model edition. Take exactly one iterator, either the default
    view (invalid stored data raises) or ``checked()`` (invalid roots are records).
    Ordinary standalone delivery failures are contextualized under that edition;
    stream-state refusals retain their own type.

    Typed ``wire()`` projection is available only while paused at a delivered
    root. It uses that page's includes and does not advance the stream. Page size
    counts root positions and does not change their order or contents.
    """

    __slots__ = ("_delivery", "_projection_construction", "_projection_state")

    def __init__[Q](
        self,
        execution: StreamExecution,
        query: Q,
        batch_size: int,
        *,
        convert_query: Callable[[Q], ObjectQueryNode],
        build_publication: Callable[[SelectedReadModel], SnapshotPublication],
    ) -> None:
        self._projection_construction: EntityGraphConstruction | None = None
        self._projection_state: _StreamWireProjection | None = None
        self._delivery = execution.stream(
            query,
            batch_size,
            convert_query=convert_query,
            build_publication=build_publication,
            on_page_start=self._begin_projection_page,
            on_release=self._release_projection,
        )

    def __enter__(self) -> SnapshotStream[T]:
        """Open the stream's scope: the delivery begins its read, builds this
        stream's publication, gates the query, plans its pages, and starts
        observing it. Nothing reaches the database."""
        publication = self._delivery.enter()
        self._projection_construction = publication.construction
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
        /,
    ) -> None:
        """Close the scope; the delivery ends its observation the way it ended."""
        self._delivery.close()

    def __iter__(self) -> Iterator[T]:
        """The default view: each root as it is published, refusing invalid data.

        Taking it locks the delivery to this view and this pass.
        """
        return cast("Iterator[T]", self._delivery.view(checked=False))

    def checked(self) -> Iterator[T | InvalidData[T]]:
        """The checked view: the same delivery, with a root whose stored state
        contradicted the model arriving as its record in band.

        Taking it locks the delivery exactly as iterating does, and the two
        exclude each other: a stream delivers through one view, once.
        """
        return cast("Iterator[T | InvalidData[T]]", self._delivery.view(checked=True))

    @overload
    def wire[R: Entity](
        self: SnapshotStream[R],
        value: Entity,
        *,
        at: RelationshipPath[Entity, Any] | None = None,
    ) -> WireEntity: ...

    @overload
    def wire[R: Entity, E: Entity](
        self: SnapshotStream[R],
        value: InvalidData[E],
        *,
        at: RelationshipPath[Entity, Any] | None = None,
    ) -> InvalidData[WireEntity]: ...

    def wire(
        self,
        value: object,
        *,
        at: RelationshipPath[Entity, Any] | None = None,
    ) -> WireEntity | InvalidData[WireEntity]:
        """Publish one eligible node under the current delivery Page's request shape."""
        construction = self._projection_construction
        if construction is None:
            if self._delivery.entered:
                from parallax.snapshot._inspection import SnapshotInspectionError

                raise SnapshotInspectionError(
                    code="snapshot-wire-envelope-ineligible",
                    message="Wire projection is available only on a Typed Snapshot Stream",
                    operation="SnapshotStream.wire",
                )
            raise StreamStateError(_CURRENT_PROJECTION_PAGE)
        includes = self._delivery.paused_includes
        if includes is None:
            raise StreamStateError(_CURRENT_PROJECTION_PAGE)
        projection = self._projection_state
        if projection is None:
            projection = _StreamWireProjection(construction, includes)
            self._projection_state = projection
        return projection.project(value, at)

    @property
    def pin(self) -> Pin:
        """Where the delivery as a whole stands, available before the first page:
        a stream settles this from the query rather than from a result, so no
        page can revise what the caller was already told.

        For a read at one instant that is the query's OWN lowered as-of
        coordinates, which every Page carries identically. For a
        milestone-set read it is the EMPTY pin, exactly as the whole result of
        the same query answers: a scan is not a pin, and each root of one stands
        at its own milestone edge rather than at any coordinate the delivery
        holds."""
        return self._delivery.pin

    @property
    def edition(self) -> str:
        """The Model Edition this delivery was begun under, answered where
        :attr:`pin` is: inside the scope, and never before entry.

        Fixed when the scope was entered and retained through every page, so a
        publication landing mid-delivery changes neither what a later page is
        read under nor what this reports. A stream that has not entered has no
        Adopted Edition, which is what the state refusal before entry says."""
        return self._delivery.edition

    def __repr__(self) -> str:
        return f"SnapshotStream(target={self._delivery.target!r}, state={self._delivery.state!r})"

    def _begin_projection_page(self, includes: deep_fetch.IncludeTree) -> None:
        if self._projection_state is not None:
            self._projection_state.begin_page(includes)

    def _release_projection(self) -> None:
        projection = self._projection_state
        self._projection_state = None
        if projection is not None:
            projection.release()
