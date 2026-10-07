from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from typing import Any, Final, Literal, Protocol, cast

from parallax.core import continuation, deep_fetch
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    ActivityTarget,
    StreamActivity,
    StreamBatchActivity,
)
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._validated import ContinuationCoordinate, ValidatedObjectQuery
from parallax.core.read_delivery._delivery import temporal_shape
from parallax.core.read_delivery._page import EXCEPTION_MACHINERY, InvalidData, InvalidDataError
from parallax.core.read_delivery._page_reader import StreamPageResult
from parallax.core.read_delivery._paging import At, PagingPlan
from parallax.core.read_delivery._publication import Publication
from parallax.core.temporal_read import (
    Pin,
    TemporalShape,
    scans_validated_axis,
    validated_query_pin,
)

__all__ = [
    "StreamContinuationError",
    "StreamDelivery",
    "StreamRead",
    "StreamScope",
    "StreamStateError",
    "check_batch_size",
]


class StreamRead[Selection](Protocol):
    """The read a delivery was begun as: one selection, and the bracket every
    advance of the delivery runs under.

    A stream begins its read at entry and retains it through every page, so the
    selection it was opened under, whose activity the stream is, and how a
    failure escaping the delivery reaches the caller are one answer given once.
    ``selected`` is opaque here: delivery hands it to the publication builder it
    was constructed with and reads nothing off it. ``meta`` and ``edition`` are
    the model and Model Edition that selection serves.

    ``release`` settles any resource the read owns at the delivery boundary.
    """

    @property
    def selected(self) -> Selection: ...

    @property
    def meta(self) -> Metamodel: ...

    @property
    def edition(self) -> str: ...

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> StreamActivity: ...

    def release(self, failure: BaseException | None, /) -> None: ...

    def advance[T](self, body: Callable[[], T], /) -> T: ...


class StreamScope[R, Origin](Protocol):
    """What a delivery asks the execution that constructed it for.

    The scope begins the delivery's one read, validates the query under that
    read's model, and reads each page inside that read's own bracket: a
    standalone page leases its own connection, while a participating one runs
    inside its unit of work's read gate, so buffered writes reach the database
    before the page that must see them. A page is handed its own Stream Batch
    UNENTERED, because where that scope opens is part of the same answer.
    ``scanned`` marks a delivery that scans an As-Of Axis, whose Pages carry no
    origins.
    """

    def begin(self) -> R: ...

    def validated(self, read: R, node: ObjectQueryNode, /) -> ValidatedObjectQuery: ...

    def page(
        self,
        read: R,
        paging: PagingPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
        *,
        scanned: bool,
    ) -> StreamPageResult[Origin]: ...


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


class StreamStateError(RuntimeError):
    """A stream was asked for something its own rules refuse.

    Every case is a rule about the stream rather than about the data: entering
    one twice, taking a second view or a second pass, or reaching one outside
    its scope. The message names the rule; nothing about the stream's internals
    is reported.
    """


class StreamContinuationError(RuntimeError):
    """A delivery reached two roots the database placed at ONE coordinate.

    Deliberately not a :class:`StreamStateError`: nothing about the stream was
    misused, and nothing the caller can do differently avoids it. The
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

    Frozen by hand for :class:`InvalidDataError`'s own reason: a frozen
    dataclass would also refuse :meth:`add_note`, and ``__slots__`` restricts
    nothing on a :class:`BaseException`.
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
            raise AttributeError(f"StreamContinuationError is frozen; cannot assign {name!r}")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name not in EXCEPTION_MACHINERY:
            raise AttributeError(f"StreamContinuationError is frozen; cannot delete {name!r}")
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


class StreamDelivery[R: StreamRead[Any], P: Publication[Any, Any]]:
    """One scope-bound, single-pass streamed delivery.

    It owns the delivery's whole state machine: entry, the one selected view,
    advancement page after page, continuation, the bounded current Page, the
    pause at a yielded root, failure retention, and terminal cleanup. A
    lifecycle composes it rather than inheriting it, and supplies two callbacks
    once: ``on_page_start`` receives each Page's include tree before its first
    root is published, including a Page that yields nothing or fails during
    publication, and ``on_release`` runs where the delivery releases its
    lifecycle projection state, before the remaining roots and the publication
    are released. A delivery that settles and then closes releases twice, so
    ``on_release`` is idempotent; a failure it raises still leaves the roots and
    the publication released and the delivery's verdict recorded.
    """

    __slots__ = (
        "_activity",
        "_batch_size",
        "_build_publication",
        "_failure",
        "_milestones",
        "_node",
        "_on_page_start",
        "_on_release",
        "_pages",
        "_paging",
        "_paused_includes",
        "_pin",
        "_publication",
        "_read",
        "_scope",
        "_state",
    )

    def __init__(
        self,
        node: ObjectQueryNode,
        scope: StreamScope[R, Any],
        build_publication: Callable[[Any], P],
        *,
        batch_size: int,
        on_page_start: Callable[[deep_fetch.IncludeTree], None],
        on_release: Callable[[], None],
    ) -> None:
        self._node = node
        self._scope = scope
        self._build_publication = build_publication
        self._batch_size = batch_size
        self._on_page_start = on_page_start
        self._on_release = on_release
        self._state: _State = _CREATED
        self._read: R | None = None
        self._publication: P | None = None
        self._paging: PagingPlan | None = None
        self._pages: Generator[object] | None = None
        self._pin: Pin = Pin()
        self._milestones: TemporalShape | None = None
        self._activity: StreamActivity = INERT
        self._failure: BaseException | None = None
        self._paused_includes: deep_fetch.IncludeTree | None = None

    def enter(self) -> P:
        """Open the delivery's scope: begin its read, build its publication,
        gate the query, plan its pages, and start observing it.

        Everything deterministic happens here and nothing reaches the database:
        the read is begun, which is where a standalone stream adopts the
        selection every page will be served under; then the publication, which
        is where a selection that cannot publish this representation refuses;
        then the read gate, the page plan, and the pin the delivery will answer
        for itself — the query's own lowered as-of coordinates where it reads
        one instant, and the empty pin where it scans an axis. Each is a refusal
        a caller can earn and keeps its own type, so all of them precede the
        stream's own activity — a refused stream opens no Root Execution and
        calls no Provider.
        """
        self._require(_ENTER_ONCE, _CREATED)
        read = self._scope.begin()
        publication = self._build_publication(read.selected)
        self._publication = publication
        try:
            meta = read.meta
            validated = self._scope.validated(read, self._node)
            self._paging = PagingPlan(
                continuation.plan(validated, meta), self._batch_size, self._node.limit
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
        self._state = _OPEN
        return publication

    def close(self) -> None:
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
        try:
            self._release_delivery()
        finally:
            # Settle read-owned resources before the observed stream finishes.
            # Page leases have already ended, and participating streams own none.
            read = self._read
            if read is not None:
                read.release(failure)
            self._activity.__exit__(
                type(failure) if failure is not None else None,
                failure,
                failure.__traceback__ if failure is not None else None,
            )

    def view(self, *, checked: bool) -> Iterator[object]:
        """The delivery's one view, taken once: each root as it is published.

        The default view refuses a root whose stored state contradicted the
        model; the checked view delivers its record in band.
        """
        self._require(_SINGLE_PASS, _OPEN)
        self._state = _DRAINING
        pages = self._roots(checked=checked)
        self._pages = pages
        return _Delivery(self._advance, pages)

    @property
    def entered(self) -> bool:
        """Whether entry succeeded, at any point in the delivery's life."""
        return self._state != _CREATED

    @property
    def state(self) -> str:
        return self._state

    @property
    def target(self) -> str:
        return self._node.target.canonical

    @property
    def paused_includes(self) -> deep_fetch.IncludeTree | None:
        """The current Page's include tree while the delivery is paused at a
        root it yielded, and ``None`` at every other moment."""
        return self._paused_includes

    @property
    def pin(self) -> Pin:
        """Where the delivery as a whole stands, available before the first page:
        settled from the query rather than from a result, so no page can revise
        what the caller was already told.

        For a read at one instant that is the query's OWN lowered as-of
        coordinates, which every Page carries identically. For a milestone-set
        read it is the EMPTY pin: a scan is not a pin, and each root of one
        stands at its own milestone edge."""
        self._require(_IN_SCOPE, _OPEN, _DRAINING)
        return self._pin

    @property
    def edition(self) -> str:
        """The Model Edition this delivery was begun under, answered where
        :attr:`pin` is: inside the scope, and never before entry."""
        self._require(_IN_SCOPE, _OPEN, _DRAINING)
        return self._begun().edition

    def _require(self, rule: str, /, *allowed: _State) -> None:
        if self._state not in allowed:
            raise StreamStateError(rule)

    def _begun(self) -> R:
        read = self._read
        # Reachable from an entered scope alone.
        if read is None:  # pragma: no cover - see above
            raise StreamStateError(_IN_SCOPE)
        return read

    def _advance(self, pages: Generator[object], /) -> object:
        """One advance of the view: the scope check, the next root, the state it settles.

        Every advance is an entry point and checks the state again, because
        taking a view answers an iterator a caller may hold past the scope that
        answered it. A stream reached after its scope closed reads nothing,
        yields nothing, and settles nothing.

        The step itself runs under the begun read's bracket, which is what
        names the edition on an ordinary failure escaping a standalone
        delivery; the state check stands before it, so a refusal about the
        stream keeps its own type. The delivery settles with the failure the
        step raised, before the bracket sees it, so the verdict the stream
        announces is the underlying one.

        A delivery that already settled keeps answering ``StopIteration`` inside
        its scope, so exhaustion is the end of an iteration rather than a second
        refusal.
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
        rather than at the scope exit that follows it. A failure is remembered
        instead, because the scope's own exit is where a stream announces one —
        which keeps the verdict correct for a caller that caught the failure and
        left the block normally. The reference is dropped at that exit.
        """
        if self._state != _DRAINING:
            return
        self._state = terminal
        if terminal == _FAILED:
            self._failure = failure
        try:
            read = self._read
            if read is not None:
                read.release(failure)
            self._release_delivery()
        finally:
            if terminal == _EXHAUSTED:
                self._activity.exhausted()

    def _release_delivery(self) -> None:
        """Release the lifecycle's projection state, then the remaining roots,
        then the publication, each even when an earlier one fails."""
        self._paused_includes = None
        try:
            self._on_release()
        finally:
            try:
                self._release_pages()
            finally:
                self._release_publication()

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

    def _roots(self, *, checked: bool) -> Generator[object]:
        """One root at a time, page after page, holding only the position.

        A page decides how many roots to ask for and whether any follow it; this
        loop says where the delivery stands and publishes what comes back. The
        next page resumes from the coordinate the page itself reports.

        The order of the last steps IS the precedence: every root the page kept
        is published first, a throwing view's refusal of invalid stored data
        interrupts that publication from inside the loop, and a page that could
        not be continued past refuses only once the loop has run to completion.

        Each page is read inside a Stream Batch of its own and published outside
        it, so what a stream costs an observer is two events per page plus two
        for itself.
        """
        paging = self._paging
        publication = self._publication
        read = self._read
        # Draining is reachable from an entered scope alone.
        if paging is None or publication is None or read is None:  # pragma: no cover - see above
            raise StreamStateError(_IN_SCOPE)
        coordinate: ContinuationCoordinate | None = None
        emitted = 0
        while True:
            page = self._scope.page(
                read,
                paging,
                At(coordinate, emitted),
                self._activity.batch(),
                scanned=self._milestones is not None,
            )
            includes = page.includes
            self._on_page_start(includes)
            roots = publication.roots_of(
                page.page,
                includes,
                ordinal_offset=emitted,
                sources=page.sources,
                milestones=self._milestones,
            )
            for root in roots:
                if not checked and isinstance(root, InvalidData):
                    raise InvalidDataError(
                        (cast("InvalidData[object]", root),), edition=publication.edition
                    )
                self._paused_includes = includes
                yield root
                self._paused_includes = None
            delivered = page.delivered
            resume_from = page.resume_from
            tie = page.tie
            exhausted = page.exhausted
            del page
            emitted += delivered
            if resume_from is not None:
                coordinate = resume_from
            if tie is not None:
                raise StreamContinuationError(
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
