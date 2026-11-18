from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final, Protocol, cast, overload

from parallax.core._execution._read_pipeline import ReadRepresentation
from parallax.core.internal.base import UsageError
from parallax.core.internal.entity import Entity, IncludePath
from parallax.core.internal.read_delivery import STREAM_STATE_INVALID, InvalidData
from parallax.core.internal.read_delivery._stream import StreamDelivery
from parallax.core.internal.temporal_read import Pin
from parallax.snapshot._handle._read import AT_PAUSED_ROOT, SnapshotPublication
from parallax.snapshot._publication._wire import WireEntity

__all__ = ["DEFAULT_BATCH_SIZE", "SnapshotStream", "StreamExecution"]

DEFAULT_BATCH_SIZE: Final = 1024


class StreamExecution(Protocol):
    """The read execution a Snapshot Stream obtains its one delivery from.

    It refuses re-entry, captures ``query`` through ``representation``, and
    judges the page size before the delivery exists; the delivery builds its
    publication through ``representation`` at entry.
    """

    def stream[Q](
        self,
        query: Q,
        batch_size: int,
        /,
        *,
        representation: ReadRepresentation[Q, SnapshotPublication],
    ) -> StreamDelivery[Any, Any, SnapshotPublication]: ...


class SnapshotStream[T]:
    """A single-pass stream of results; use it inside a `with` block.

    Entry adopts the model edition. Take exactly one iterator, either the default
    view (invalid stored data raises) or ``checked()`` (invalid roots are records).
    An ordinary standalone delivery failure carries a note naming that edition;
    a stream-state refusal carries none.

    Typed ``wire()`` projection is available only while paused at a delivered
    root. It uses that page's includes and does not advance the stream. Page size
    counts root positions and does not change their order or contents, except that
    a page-scope read shares nodes only within a page, so it can change which
    objects two roots share and what a shared Typed instance incidentally loaded.
    """

    __slots__ = ("_delivery", "_publication")

    def __init__[Q](
        self,
        execution: StreamExecution,
        query: Q,
        batch_size: int,
        *,
        representation: ReadRepresentation[Q, SnapshotPublication],
    ) -> None:
        self._publication: SnapshotPublication | None = None
        self._delivery = execution.stream(query, batch_size, representation=representation)

    def __enter__(self) -> SnapshotStream[T]:
        """Open the stream's scope: the delivery begins its read, builds this
        stream's publication, gates the query, plans its pages, and starts
        observing it. Nothing reaches the database."""
        self._publication = self._delivery.enter()
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
        at: IncludePath[Entity, Any] | None = None,
    ) -> WireEntity: ...

    @overload
    def wire[R: Entity, E: Entity](
        self: SnapshotStream[R],
        value: InvalidData[E],
        *,
        at: IncludePath[Entity, Any] | None = None,
    ) -> InvalidData[WireEntity]: ...

    def wire(
        self,
        value: object,
        *,
        at: IncludePath[Entity, Any] | None = None,
    ) -> WireEntity | InvalidData[WireEntity]:
        """Publish one eligible node under the current delivery Page's request shape."""
        publication = self._publication
        if publication is None:
            raise UsageError(STREAM_STATE_INVALID, AT_PAUSED_ROOT)
        return publication.project(value, at)

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
