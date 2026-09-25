from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from dataclasses import replace
from typing import Any, Final, Literal, Protocol, cast, overload

from parallax.core import continuation, deep_fetch
from parallax.core.base import ManagedValue, NeutralType
from parallax.core.entity import Entity, RelationshipPath
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    ActivityTarget,
    SnapshotStreamActivity,
    StreamBatchActivity,
)
from parallax.core.metamodel import AttributeIdentity
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._validated import ContinuationCoordinate
from parallax.core.temporal_read import (
    Pin,
    TemporalShape,
    scans_validated_axis,
    validated_query_pin,
)
from parallax.snapshot.handle._family import temporal_shape
from parallax.snapshot.handle._materialization import DeliveryPage, DeliveryPlan
from parallax.snapshot.handle._paging import At, PagePlan
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._publication import SelectedReadModel
from parallax.snapshot.handle._read import (
    ResultPublication,
    projection_concrete,
    wire_position,
)
from parallax.snapshot.materialize import InvalidData, InvalidDataError, WireEntity
from parallax.snapshot.materialize import _wire as wire_materialize
from parallax.snapshot.materialize._invalid import EXCEPTION_MACHINERY
from parallax.snapshot.materialize._wire import EntityReader, WireWalk
from parallax.snapshot.materialize._wire_memo import WeakIdentityMemo

__all__ = [
    "SnapshotStream",
    "SnapshotStreamContinuationError",
    "SnapshotStreamStateError",
    "StreamRead",
    "check_batch_size",
]


class _PageWireEncoder(Protocol):
    def begin_page(self) -> None: ...

    def __call__(self, neutral_type: NeutralType, value: ManagedValue) -> object: ...

    def release(self) -> None: ...


class StreamRead(Protocol):
    """The read a delivery was begun as: one selection, and the bracket every
    advance of the delivery runs under.

    A stream begins its read at entry and retains it through every page, so the
    selection it was opened under, whose activity the stream is, and how a
    failure escaping the delivery reaches the caller are one answer given once.
    A standalone delivery is a Root Execution of its own that adopted its
    selection at entry, leases one connection per page, and names that edition on
    an ordinary failure escaping an advance; a participating one is a child of the current
    Transaction Attempt, serves the transaction's fixed selection, runs on the
    attempt's connection, and lets a failure propagate to the invocation that
    contextualizes it once.

    ``release`` settles any lane-owned resource at the delivery boundary. Both
    current lanes answer no-op: standalone leases end inside each page and a
    participating stream owns no connection of its own.
    """

    @property
    def selected(self) -> SelectedReadModel: ...

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> SnapshotStreamActivity: ...

    def release(self, failure: BaseException | None, /) -> None: ...

    def advance[T](self, body: Callable[[], T], /) -> T: ...


class StreamScope[R: StreamRead](Protocol):
    """What a delivery asks its read composition for, as one object.

    A stream retains the ONE read composition that constructed it, so beginning
    its read, choosing how its roots are published, and reading each page are
    answered by the object that also serves the eager reads beside it. Which
    bracket a page runs inside belongs to the read the scope began and never to
    the loop above: a standalone page reads straight through, while a
    participating one runs inside its unit of work's force-flush, so buffered
    writes reach the database before the page that must see them.

    A page is handed its own Stream Batch UNENTERED, because where that scope
    opens is part of the same answer: a participating page enters it after the
    flush, which is what leaves the dependency batch an ordered sibling of the
    page rather than a scope around it (`m-execution-lifecycle`).

    The read travels with the page rather than being held below, because the
    stream is the holder of the ONE read it was begun as and no page of a
    delivery may be read under a second selection.
    """

    def begin(self) -> R: ...

    def publication(
        self, selected: SelectedReadModel, interface: ReadInterface, /
    ) -> ResultPublication: ...

    def page(
        self,
        read: R,
        page_plan: DeliveryPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
    ) -> DeliveryPage: ...


type _State = Literal["created", "open", "draining", "exhausted", "failed", "closed"]

_CREATED: Final[_State] = "created"
_OPEN: Final[_State] = "open"
_DRAINING: Final[_State] = "draining"
_EXHAUSTED: Final[_State] = "exhausted"
_FAILED: Final[_State] = "failed"
_CLOSED: Final[_State] = "closed"

_ENTER_ONCE: Final = (
    "a Snapshot Stream is entered exactly once, and only before anything has drained it"
)
_SINGLE_PASS: Final = (
    "a Snapshot Stream is single-pass: it delivers its roots to the first view taken "
    "inside its scope, and to no second view and no second pass"
)
_IN_SCOPE: Final = "a Snapshot Stream answers only inside its own scope"
_CURRENT_PROJECTION_PAGE: Final = (
    "SnapshotStream.wire answers only while delivery is paused at a root of its current Page"
)

_END: Final = object()
"""What one advance answers when the delivery ran out, so exhaustion crosses the
read's bracket as a value: ``StopIteration`` is an ordinary exception, and a
bracket that contextualizes ordinary failures would otherwise wrap it."""


def check_batch_size(batch_size: int) -> None:
    """Refuse anything but a positive built-in ``int`` page size.

    ``limit``'s rule, applied to the other count a read can carry: ``type(x) is
    not int`` is an IDENTITY check, so nothing is coerced and ``True`` is not
    the page size 1. The refusal happens at the call that named the size, before
    any plan, any page, and any I/O.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError(f"batch_size requires a positive built-in int (got {batch_size!r})")


class SnapshotStreamStateError(RuntimeError):
    """A Snapshot Stream was asked for something its own rules refuse.

    Every case is a rule about the stream rather than about the data: entering
    one twice, taking a second view or a second pass, or reaching one outside
    its scope. The message names the rule; nothing about the stream's internals
    is reported.
    """


class SnapshotStreamContinuationError(RuntimeError):
    """A delivery reached two roots the database placed at ONE coordinate.

    Deliberately not a :class:`SnapshotStreamStateError`: nothing about the
    stream was misused, and nothing the caller can do differently avoids it. The
    Continuation Order is total over storage the model describes, so what this
    reports is storage that has lost a constraint the order rests on — and a
    delivery that continued past it would have to skip a root, duplicate one, or
    loop, none of which a delivery may do.

    Every root before the tie is published first, so this arrives after the
    maximal strictly ordered prefix and :attr:`ordinal` is the position of the
    first root that could not be delivered. :attr:`terms` is the order that
    turned out not to be total, and :attr:`coordinate` is an inert copy of where
    that root stood — readable and comparable, with no public constructor
    turning it back into pagination authority, and kept out of the message, the
    default repr, lifecycle events, and default logging. A one-root lookahead
    proves that at LEAST two roots tie, so no count of them is reported.

    Frozen by hand for :class:`~parallax.snapshot.materialize.InvalidDataError`'s
    own reason: a frozen dataclass would also refuse :meth:`add_note`, and
    ``__slots__`` restricts nothing on a :class:`BaseException`.
    """

    code: Final[str] = "snapshot-stream-continuation-order-not-total"

    _terms: tuple[AttributeIdentity, ...]
    _coordinate: tuple[object, ...]
    _ordinal: int

    def __init__(
        self,
        *,
        terms: tuple[AttributeIdentity, ...],
        coordinate: tuple[object, ...],
        ordinal: int,
    ) -> None:
        order = ", ".join(f"{identity.entity.canonical}.{identity.name}" for identity in terms)
        super().__init__(
            f"the delivery cannot continue past result {ordinal}: two adjacent roots stand "
            f"at one Continuation Order coordinate, so ({order}) is not total over the "
            f"stored data"
        )
        object.__setattr__(self, "_terms", terms)
        object.__setattr__(self, "_coordinate", coordinate)
        object.__setattr__(self, "_ordinal", ordinal)

    def __setattr__(self, name: str, value: object) -> None:
        if name not in EXCEPTION_MACHINERY:
            raise AttributeError(
                f"SnapshotStreamContinuationError is frozen; cannot assign {name!r}"
            )
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name not in EXCEPTION_MACHINERY:
            raise AttributeError(
                f"SnapshotStreamContinuationError is frozen; cannot delete {name!r}"
            )
        super().__delattr__(name)

    @property
    def terms(self) -> tuple[AttributeIdentity, ...]:
        return self._terms

    @property
    def coordinate(self) -> tuple[object, ...]:
        """An inert copy of the coordinate both tied roots stood at, positionally
        aligned with :attr:`terms`."""
        return self._coordinate

    @property
    def ordinal(self) -> int:
        """The zero-based position, in the delivery, of the first root that could
        not be delivered."""
        return self._ordinal


class _StreamWireProjection:
    __slots__ = ("_encoder", "_includes", "_model", "_reader", "_walk")

    def __init__(self, model: CatalogedModel, includes: deep_fetch.IncludeTree) -> None:
        self._model = model
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
                reader = EntityReader(self._model, operation="SnapshotStream.wire")
            concrete = projection_concrete(reader, node, operation="SnapshotStream.wire")
        position = wire_position(
            self._includes,
            self._model,
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

    __slots__ = (
        "_activity",
        "_batch_size",
        "_failure",
        "_interface",
        "_milestones",
        "_node",
        "_page_plan",
        "_pages",
        "_pin",
        "_projection_includes",
        "_projection_model",
        "_projection_state",
        "_publication",
        "_read",
        "_scope",
        "_state",
    )

    def __init__(
        self,
        node: ObjectQueryNode,
        interface: ReadInterface,
        scope: StreamScope[Any],
        *,
        batch_size: int,
    ) -> None:
        self._node = node
        self._interface: ReadInterface = interface
        self._scope: StreamScope[Any] = scope
        self._batch_size = batch_size
        self._state: _State = _CREATED
        self._read: StreamRead | None = None
        self._publication: ResultPublication | None = None
        self._projection_model: CatalogedModel | None = None
        self._projection_includes: deep_fetch.IncludeTree | None = None
        self._projection_state: _StreamWireProjection | None = None
        self._page_plan: DeliveryPlan | None = None
        self._pages: Generator[object] | None = None
        self._pin: Pin = Pin()
        self._milestones: TemporalShape | None = None
        self._activity: SnapshotStreamActivity = INERT
        self._failure: BaseException | None = None

    def __enter__(self) -> SnapshotStream[T]:
        """Open the stream's scope: begin its read, gate the query, plan its
        pages, and start observing it.

        Everything deterministic happens here and nothing reaches the database:
        the read is begun, which is where a standalone stream adopts the
        selection every page will be served under; then the publication, which
        is where a selection that can materialize no Snapshot at all refuses a
        Typed delivery; then the same read gate an eager find crosses, the page
        plan, and the pin the delivery will answer for itself — the query's own
        lowered as-of coordinates where it reads one instant, and the empty pin
        where it scans an axis. Each is a refusal a caller can earn and keeps
        its own type, so all of them precede the stream's own activity — a
        refused stream opens no Root Execution and calls no Provider — and
        constructing a stream without entering it adopts nothing, observes
        nothing, and reads nothing.
        """
        self._require(_ENTER_ONCE, _CREATED)
        read = self._scope.begin()
        publication = self._scope.publication(read.selected, self._interface)
        self._publication = publication
        try:
            meta = read.selected.model.meta
            validated = preflight(self._node, model=meta, form="graph")
            self._page_plan = DeliveryPlan(
                PagePlan(continuation.plan(validated, meta), self._batch_size, self._node.limit)
            )
            if scans_validated_axis(validated.temporal):
                self._milestones = temporal_shape(meta, validated.root)
                self._pin = Pin()
            else:
                self._pin = validated_query_pin(validated.temporal)
            self._read = read
            self._activity = read.open_stream(
                self._node.target, publication.interface, self._batch_size
            ).__enter__()
        except BaseException:
            self._release_publication()
            raise
        self._projection_model = publication.projection_model
        self._state = _OPEN
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
        /,
    ) -> None:
        """Close the scope, and end the observation the way the delivery ended.

        What ended the stream is the delivery's own verdict rather than whatever
        exception happens to be leaving the block: Parallax's work failing IS the
        stream failing, whether the caller re-raised it or caught it, and a
        caller's own exception is a caller stopping early however it arrived. A
        delivery that exhausted has already finished, so neither rewrites it.
        """
        self._state = _CLOSED
        failure = self._failure
        self._failure = None
        self._release_projection()
        self._release_pages()
        self._release_publication()
        # Settle lane-owned resources before the observed stream finishes. Page
        # leases have already ended, and participating streams own none.
        read = self._read
        if read is not None:
            read.release(failure)
        self._activity.__exit__(
            type(failure) if failure is not None else None,
            failure,
            failure.__traceback__ if failure is not None else None,
        )

    def __iter__(self) -> Iterator[T]:
        """The default view: each root as it is published, refusing invalid data.

        Taking it locks the delivery to this view and this pass.
        """
        self._require(_SINGLE_PASS, _OPEN)
        self._state = _DRAINING
        return cast("Iterator[T]", self._drain(checked=False))

    def checked(self) -> Iterator[T | InvalidData[T]]:
        """The checked view: the same delivery, with a root whose stored state
        contradicted the model arriving as its record in band.

        Taking it locks the delivery exactly as iterating does, and the two
        exclude each other: a stream delivers through one view, once.
        """
        self._require(_SINGLE_PASS, _OPEN)
        self._state = _DRAINING
        return cast("Iterator[T | InvalidData[T]]", self._drain(checked=True))

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
        model = self._projection_model
        if model is None:
            if self._state != _CREATED:
                from parallax.snapshot._inspection import SnapshotInspectionError

                raise SnapshotInspectionError(
                    code="snapshot-wire-envelope-ineligible",
                    message="Wire projection is available only on a Typed Snapshot Stream",
                    operation="SnapshotStream.wire",
                )
            raise SnapshotStreamStateError(_CURRENT_PROJECTION_PAGE)
        includes = self._projection_includes
        if includes is None:
            raise SnapshotStreamStateError(_CURRENT_PROJECTION_PAGE)
        projection = self._projection_state
        if projection is None:
            projection = _StreamWireProjection(model, includes)
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
        self._require(_IN_SCOPE, _OPEN, _DRAINING)
        return self._pin

    @property
    def edition(self) -> str:
        """The Model Edition this delivery was begun under, answered where
        :attr:`pin` is: inside the scope, and never before entry.

        Fixed when the scope was entered and retained through every page, so a
        publication landing mid-delivery changes neither what a later page is
        read under nor what this reports. A stream that has not entered has no
        Adopted Edition, which is what the state refusal before entry says."""
        self._require(_IN_SCOPE, _OPEN, _DRAINING)
        return self._begun().selected.edition

    def __repr__(self) -> str:
        return f"SnapshotStream(target={self._node.target.canonical!r}, state={self._state!r})"

    def _require(self, rule: str, /, *allowed: _State) -> None:
        if self._state not in allowed:
            raise SnapshotStreamStateError(rule)

    def _begun(self) -> StreamRead:
        read = self._read
        # Reachable from an entered scope alone.
        if read is None:  # pragma: no cover - see above
            raise SnapshotStreamStateError(_IN_SCOPE)
        return read

    def _advance(self, pages: Generator[object], /) -> object:
        """One advance of a view: the scope check, the next root, the state it settles.

        Every advance is an entry point and checks the state again, because
        taking a view answers an iterator a caller may hold past the scope that
        answered it. A stream reached after its scope closed reads nothing,
        yields nothing, and settles nothing — the state it was left in stands,
        and it stands for every later advance too.

        The step itself runs under the begun read's bracket, which is what
        names the edition on an ordinary failure escaping a standalone
        delivery; the state check stands before it, so a refusal about the
        stream keeps its own type. The delivery settles with the failure the
        step raised, before the bracket sees it, so the verdict the stream
        announces is the underlying one.

        A delivery that already settled keeps answering ``StopIteration`` inside
        its scope, so exhaustion is the end of an iteration rather than a second
        refusal, and the terminal state a settled delivery carries is never
        written over by a later advance.
        """
        self._require(_IN_SCOPE, _DRAINING, _EXHAUSTED, _FAILED)
        root = self._begun().advance(lambda: self._step(pages))
        if root is _END:
            raise StopIteration
        return root

    def _step(self, pages: Generator[object], /) -> object:
        try:
            return next(pages)
        except StopIteration:
            self._settle(_EXHAUSTED)
            return _END
        except BaseException as failure:
            self._settle(_FAILED, failure)
            raise

    def _settle(self, terminal: _State, failure: BaseException | None = None, /) -> None:
        """Record how the delivery ended, once.

        Exhaustion finishes the observed stream HERE, where it was discovered,
        rather than at the scope exit that follows it: the outcome is true at
        this point, and settling it here is what leaves a later caller error with
        nothing to rewrite. A failure is remembered instead, because the scope's
        own exit is where a stream announces one — and remembering it is what
        keeps the verdict correct for a caller that caught the failure and left
        the block normally. The reference is dropped at that exit, so a failed
        delivery holds one exception for the remainder of its scope and no
        longer.
        """
        if self._state != _DRAINING:
            return
        self._state = terminal
        read = self._read
        if read is not None:
            read.release(failure)
        self._release_projection()
        self._release_pages()
        self._release_publication()
        if terminal == _EXHAUSTED:
            self._activity.exhausted()
        else:
            self._failure = failure

    def _release_publication(self) -> None:
        publication = self._publication
        self._publication = None
        if publication is not None:
            publication.release()

    def _release_pages(self) -> None:
        pages = self._pages
        self._pages = None
        if pages is not None:
            pages.close()

    def _release_projection(self) -> None:
        self._projection_includes = None
        projection = self._projection_state
        self._projection_state = None
        if projection is not None:
            projection.release()

    def _begin_projection_page(self, includes: deep_fetch.IncludeTree) -> None:
        self._projection_includes = None
        if self._projection_state is not None:
            self._projection_state.begin_page(includes)

    def _projection_roots(
        self, roots: Iterator[object], includes: deep_fetch.IncludeTree
    ) -> Iterator[object]:
        self._begin_projection_page(includes)
        for root in roots:
            self._projection_includes = includes
            yield root
            self._projection_includes = None

    def _drain(self, *, checked: bool) -> Iterator[object]:
        pages = self._roots(checked=checked)
        self._pages = pages
        return _Delivery(self._advance, pages)

    def _roots(self, *, checked: bool) -> Generator[object]:
        """One root at a time, page after page, holding only the position.

        A page decides how many roots to ask for and whether any follow it; this
        loop says where the delivery stands and publishes what comes back. The
        next page resumes from the coordinate the page itself reports, so the
        rule that a delivery advances by the LAST KEPT root lives on the page
        rather than in a subscript here.

        The order of the last steps IS the precedence: every root the page kept
        is published first, a throwing view's refusal of invalid stored data
        interrupts that publication from inside the loop, and a page that could
        not be continued past refuses only once the loop has run to completion.

        Each page is prepared inside a Stream Batch of its own and published
        outside it, so what a stream costs an observer is two events per page
        plus two for itself — proportional to the pages it read rather than to
        the roots it delivered.
        """
        page_plan = self._page_plan
        publication = self._publication
        read = self._read
        # Draining is reachable from an entered scope alone.
        if page_plan is None or publication is None or read is None:  # pragma: no cover - see above
            raise SnapshotStreamStateError(_IN_SCOPE)
        coordinate: ContinuationCoordinate | None = None
        emitted = 0
        while True:
            page = self._scope.page(
                read, page_plan, At(coordinate, emitted), self._activity.batch()
            )
            roots = publication.roots_of(
                page.page,
                page.includes,
                ordinal_offset=emitted,
                sources=page.sources,
                milestones=self._milestones,
            )
            if self._projection_model is not None:
                roots = self._projection_roots(roots, page.includes)
            for root in roots:
                if not checked and isinstance(root, InvalidData):
                    raise InvalidDataError(
                        (cast("InvalidData[object]", root),), edition=publication.edition
                    )
                yield root
            delivered = page.delivered
            resume_from = page.resume_from
            tie = page.tie
            exhausted = page.exhausted
            del page
            emitted += delivered
            if resume_from is not None:
                coordinate = resume_from
            if tie is not None:
                raise SnapshotStreamContinuationError(
                    terms=tie.terms,
                    coordinate=tie.coordinate,
                    ordinal=tie.ordinal,
                )
            if exhausted:
                return


class _Delivery(Iterator[object]):
    """A view over one stream: an iterator guarding a paging generator.

    Deliberately not the generator itself. An error raised out of a generator
    frame CLOSES it, so a generator that refuses an out-of-scope advance could
    refuse only once — every later advance of the same retained view would end
    the caller's loop quietly instead. Guarding a separate object is what makes
    each advance an entry point of its own for as long as the view is held.
    """

    __slots__ = ("_advance", "_pages")

    def __init__(
        self, advance: Callable[[Generator[object]], object], pages: Generator[object]
    ) -> None:
        self._advance = advance
        self._pages = pages

    def __next__(self) -> object:
        return self._advance(self._pages)
