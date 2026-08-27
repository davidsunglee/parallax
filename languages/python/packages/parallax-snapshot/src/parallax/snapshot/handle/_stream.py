"""``parallax.snapshot.handle._stream`` — the Snapshot Stream (`m-snapshot-read`).

A streamed read is the eager read surrounded rather than replaced. Above the
executor sits a page loop that asks
:mod:`~parallax.core.continuation` for one bounded root query at a time; below
it sits publication, which walks the page's own sealed graph ONE root at a time.
The executor between them is the same :func:`~parallax.snapshot.handle._read.find`
an eager read runs, planning, issuing its `1 + L` statements, and sealing one
graph exactly as it always has — so a page's child levels are the same
``IN (gathered keys)`` lookups, and only the root statement differs.

What that buys is the bound this surface exists for: the working set is one
page's sealed graph plus the current root's merge and published graph, and it
does not grow with the total number of roots. Advancing releases the previous
root; finishing a page releases the page graph after its last root.

Root scope is a property of the GRAPH rather than a mode anything is told about.
:func:`~parallax.snapshot.materialize._graph.root_scoped` narrows a page graph to
one root and the ordinary merge, classification, and materializers run over the
result unchanged — which is why identity is root-local here without a second
publication path, and why the same seam publishes an eager read.

The delivery type guards a private paging generator rather than being one. A
bare generator handed to a caller could not refuse a second pass — re-iterating
one yields nothing at all — so every entry point checks the one state field
first, in the discipline the unit of work's own scope flag already uses.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator, Mapping
from contextlib import closing
from typing import Final, Literal, cast

from parallax.core import continuation
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, entity_by_name
from parallax.core.object_query import ObjectQueryNode
from parallax.core.temporal_read import Pin, query_pin
from parallax.snapshot._read_result import FindResult
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import ResultPublication, declaring_metadata
from parallax.snapshot.materialize import InvalidData, InvalidDataError
from parallax.snapshot.materialize._graph import root_members, root_scoped

__all__ = ["PageRead", "SnapshotStream", "SnapshotStreamStateError", "check_batch_size"]

type PageRead = Callable[[ObjectQueryNode], FindResult]
"""How one page reaches the database: the executor entry its owner composed.

A standalone stream's page is a plain find; a participating one's runs inside
its unit of work's force-flush, so buffered writes reach the database before the
page that must see them. Which it is belongs to the handle that opened the
stream, never to the loop above it.
"""

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
_KEYLESS_ROOT: Final = (
    "a stream cannot continue past a root whose primary key did not decode "
    "(snapshot-stream-keyless-root)"
)


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
    one twice, taking a second view or a second pass, reaching one outside its
    scope, or continuing past a root that can supply no cursor. The message
    names the rule; nothing about the stream's internals is reported.
    """


class SnapshotStream[T]:
    """``db.stream`` / ``db.wire.stream``'s result: a scope-bound, single-pass
    delivery of roots in the Continuation Order.

    Deliberately NOT a :class:`~parallax.snapshot.handle._read.Snapshot`. There
    is no whole-result accessor, no arity accessor, and no way to re-read what
    already went past — a caller holding one holds a position in a delivery
    rather than a value. Everything outside the scope raises, including
    :attr:`pin`, so "the stream answers inside its scope" is one rule rather
    than one rule with an exception.

    Iterating is the default view and raises
    :class:`~parallax.snapshot.materialize.InvalidDataError` at a root whose
    stored state contradicted the model; :meth:`checked` is the same delivery
    with that root arriving as its record instead. A view is taken once: the
    second — of either kind — is refused rather than silently delivering
    nothing.

    ``batch_size`` counts ROOT positions and is a performance dial alone. It
    changes neither the order roots arrive in, nor which roots arrive, nor what
    each carries — including the one root shape that ends a delivery early, a
    root whose own primary key did not decode, which ends it from whatever
    position it lands in.
    """

    __slots__ = (
        "_batch_size",
        "_model",
        "_node",
        "_page_read",
        "_pin",
        "_plan",
        "_publication",
        "_state",
    )

    def __init__(
        self,
        node: ObjectQueryNode,
        model: CatalogedModel,
        publication: ResultPublication,
        page_read: PageRead,
        *,
        batch_size: int,
    ) -> None:
        self._node = node
        self._model = model
        self._publication = publication
        self._page_read = page_read
        self._batch_size = batch_size
        self._state: _State = _CREATED
        self._plan: continuation.ContinuationPlan | None = None
        self._pin: Pin = Pin()

    def __enter__(self) -> SnapshotStream[T]:
        """Open the stream's scope: gate the query and plan its pages.

        Everything deterministic happens here and nothing reaches the database:
        the same read gate an eager find crosses, then the page plan and the
        query's own lowered as-of coordinates. Constructing a stream and never
        entering it therefore emits nothing and reads nothing.
        """
        self._require(_ENTER_ONCE, _CREATED)
        preflight(self._node, model=self._model.meta, form="graph")
        entity = self._entity()
        self._plan = continuation.plan(entity, self._node, self._model.meta)
        self._pin = query_pin(self._node, declaring_metadata(self._model.meta, entity.identity))
        self._state = _OPEN
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
        /,
    ) -> None:
        self._state = _CLOSED

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

    @property
    def pin(self) -> Pin:
        """The query's OWN lowered as-of coordinates, available before the first
        page: a stream computes them from the query rather than from a result,
        and every page's sealed graph carries the identical pin, so no page can
        revise what the caller was already told."""
        self._require(_IN_SCOPE, _OPEN, _DRAINING)
        return self._pin

    def __repr__(self) -> str:
        return f"SnapshotStream(target={self._node.target.canonical!r}, state={self._state!r})"

    def _require(self, rule: str, /, *allowed: _State) -> None:
        if self._state not in allowed:
            raise SnapshotStreamStateError(rule)

    def _entity(self) -> EntityMetadata:
        entity = entity_by_name(self._model.meta, self._node.target.canonical)
        if entity is None:  # pragma: no cover - the gate above resolved this target
            raise SnapshotStreamStateError(f"{self._node.target.canonical}: no such Entity")
        return entity

    def _drain(self, *, checked: bool) -> Iterator[object]:
        """The paging generator, with the terminal state it settles.

        Every advance is an entry point and checks the state again, because
        taking a view returns a generator that a caller may hold past the scope
        that answered it. A stream reached after its scope closed reads nothing,
        yields nothing, and settles nothing — the state it was left in stands.

        A caller abandoning the loop closes this generator, which is a caller
        decision rather than a stream outcome, so the state it leaves is the
        draining one its scope exit then closes.
        """
        with closing(self._roots(checked=checked)) as roots:
            while True:
                self._require(_IN_SCOPE, _DRAINING)
                try:
                    root = next(roots)
                except StopIteration:
                    break
                except BaseException:
                    self._state = _FAILED
                    raise
                yield root
        self._state = _EXHAUSTED

    def _roots(self, *, checked: bool) -> Generator[object]:
        """One root at a time, page after page, holding only the cursor.

        A short page proves exhaustion — fewer roots than asked for means no
        more exist. A full final page does not, so it costs one more root
        statement returning nothing, unless a declared ``limit`` has already
        been delivered in full.
        """
        plan = self._plan
        if plan is None:  # pragma: no cover - draining is reachable from an entered scope alone
            raise SnapshotStreamStateError(_IN_SCOPE)
        limit = self._node.limit
        cursor: Mapping[AttributeIdentity, object] | None = None
        emitted = 0
        while True:
            size = self._batch_size if limit is None else min(self._batch_size, limit - emitted)
            node = plan.first(limit=size) if cursor is None else plan.after(cursor, limit=size)
            page = self._page_read(node)
            delivered = 0
            for position, members in enumerate(root_members(page.graph)):
                root = self._published(page, position, ordinal=emitted + position)
                delivered += 1
                if not checked and isinstance(root, InvalidData):
                    raise InvalidDataError((cast("InvalidData[object]", root),))
                yield root
                if members is None:
                    raise SnapshotStreamStateError(_KEYLESS_ROOT)
                cursor = members
            emitted += delivered
            if delivered < size or (limit is not None and emitted >= limit):
                return

    def _published(self, page: FindResult, position: int, *, ordinal: int) -> object:
        """The one root at ``position`` of ``page``, published on its own.

        The page graph is shared INPUT rather than a publication unit: scoping it
        to one root is what keeps a relationship from reading as loaded on this
        root only because a neighbour in the same page reached it.
        """
        roots = self._publication.roots_of(
            root_scoped(page.graph, position),
            page.includes,
            ordinal_offset=ordinal,
            sources=page.sources,
        )
        return roots[0]
