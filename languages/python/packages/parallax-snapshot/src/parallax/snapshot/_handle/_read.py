from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, NoReturn, cast, overload

from parallax.core._execution._publication import SelectedReadModel
from parallax.core._execution._read_pipeline import ReadQuery
from parallax.core._execution._unit_work.evidence import ReadEvidence
from parallax.core.execution_lifecycle._events import ResultRepresentation
from parallax.core.internal import read_planning
from parallax.core.internal.base import (
    InternalError,
    NoResultFound,
    TooManyResultsFound,
    UsageError,
)
from parallax.core.internal.entity import Entity, EntityGraphConstruction, IncludePath
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.object_query import ObjectQueryNode, deserialize
from parallax.core.internal.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.internal.read_delivery import STREAM_STATE_INVALID, InvalidData
from parallax.core.internal.read_delivery._page import Page, invalid_result_refusal
from parallax.core.internal.read_delivery._page_reader import EagerPageResult, HistoryPageResult
from parallax.core.internal.temporal_read import Pin, TemporalShape
from parallax.snapshot._handle._errors import (
    SNAPSHOT_CLASS_BACKED_MODEL_REQUIRED,
    SNAPSHOT_MATERIALIZATION_FAILED,
)
from parallax.snapshot._handle._wire_projection import TypedWireProjection, TypedWireSource
from parallax.snapshot._inspection import SNAPSHOT_WIRE_ENVELOPE_INELIGIBLE, inspection_refusal
from parallax.snapshot._publication import _wire as wire_materialize
from parallax.snapshot._publication._graph_view import GraphView
from parallax.snapshot._publication._root_publication import publish_roots, publish_shared_roots
from parallax.snapshot._publication._typed import TypedRootPublisher
from parallax.snapshot._publication._wire import WireEntity
from parallax.snapshot._publication._wire_render import WireRootPublisher

__all__ = [
    "AT_PAUSED_ROOT",
    "TYPED",
    "TYPED_PAGE_SHARED",
    "WIRE",
    "WIRE_PAGE_SHARED",
    "CheckedSnapshot",
    "SharingScope",
    "Snapshot",
    "SnapshotPublication",
    "TypedPublication",
    "TypedRepresentation",
    "WirePublication",
    "WireQuery",
    "WireRepresentation",
    "check_sharing_scope",
    "wire_read_query",
]


type SharingScope = Literal["root", "page"]
"""How far a read may share published nodes: within one result root, or across
the roots of one Page."""


def check_sharing_scope(sharing_scope: SharingScope) -> None:
    """Refuse anything but a :data:`SharingScope` at the call that named it."""
    if cast("object", sharing_scope) not in ("root", "page"):
        raise ValueError(f"sharing_scope requires 'root' or 'page' (got {sharing_scope!r})")


def _sole[T](roots: tuple[T, ...], *, empty_is_absence: bool) -> T | None:
    """The one root ``roots`` holds, applying the arity rule both views share.

    Arity is settled before stored-data validity is even consulted, so a
    zero-root or multi-root refusal reads the same whichever view asked — the
    checked view narrows what a VALID single root is delivered as, never how many
    roots an accessor accepts.
    """
    count = len(roots)
    if count == 0:
        if empty_is_absence:
            return None
        raise NoResultFound("the snapshot matched no roots")
    if count > 1:
        expected = "0 or 1" if empty_is_absence else "exactly 1"
        raise TooManyResultsFound(f"the snapshot matched {count} roots, expected {expected}")
    return roots[0]


def _invalid_records[T](
    roots: tuple[T | InvalidData[T], ...],
) -> tuple[InvalidData[object], ...]:
    """Every invalid root in result order — empty for a wholly conforming read."""
    return tuple(
        cast("InvalidData[object]", root) for root in roots if isinstance(root, InvalidData)
    )


_WIRE_ALL = object()
_WIRE_AT_OMITTED = object()


class Snapshot[T]:
    """The result of a `find`: immutable result roots and the ways to read them.

    The Python reification of a core Snapshot Graph: ``db.find`` /
    ``tx.find``'s result. The complete surface: :meth:`result`,
    :meth:`result_or_none`, :meth:`results` (a FRESH ``list[T]`` per call),
    :meth:`checked`, :meth:`wire`,
    :attr:`pin` (the lowered as-of coordinates — only genuinely PINNED axes; a
    scanned axis is absent), :attr:`edition` (the Model Edition the read was
    served under), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, any lazy
    behavior, and every lifecycle accessor. A Typed result retains the request's
    canonical finite include shape, the graph construction that published it,
    and its model's prepared Wire facts so :meth:`wire` can publish the value in
    memory; it retains no execution
    scope, Page, Root View, connection, authority, or other lifecycle of the read.

    A root whose stored state contradicted the model is held as its
    :class:`~parallax.core.internal.read_delivery.InvalidData` record. The accessors
    here are the DEFAULT view: they check arity first and then refuse the read
    with :class:`~parallax.core.internal.read_delivery.InvalidDataError`, so a caller
    who never asks about stored-data validity can never silently receive a
    record in place of an Entity. :meth:`checked` is the same storage read in
    band instead. There is no ignore posture and no partition API: a finite
    union is partitioned with ordinary collection operations.
    """

    __slots__ = ("_edition", "_invalid", "_pin", "_roots", "_source")

    _roots: tuple[T | InvalidData[T], ...]
    _invalid: tuple[InvalidData[object], ...]
    _pin: Pin
    _edition: str
    _source: TypedWireSource | None

    def __init__(
        self,
        roots: tuple[T | InvalidData[T], ...],
        pin: Pin,
        edition: str,
        source: TypedWireSource | None = None,
    ) -> None:
        self._roots = roots
        self._invalid = _invalid_records(roots)
        self._pin = pin
        self._edition = edition
        self._source = source

    def result(self) -> T:
        """The single matched root; raises on zero, on more than one, and on
        invalid stored data — in that order."""
        root = _sole(self._roots, empty_is_absence=False)
        self._require_valid()
        return cast("T", root)

    def result_or_none(self) -> T | None:
        """The single matched root, or ``None`` on zero; raises on more than one
        and then on invalid stored data."""
        root = _sole(self._roots, empty_is_absence=True)
        self._require_valid()
        return cast("T | None", root)

    def results(self) -> list[T]:
        """Every matched root as an ordinary ``list[T]`` the caller owns (a
        fresh copy per call — this accessor is unaffected by node immutability).

        Eager access aggregates: every invalid root is reported together, in
        result order, rather than one refusal per call.
        """
        self._require_valid()
        return cast("list[T]", list(self._roots))

    def checked(self) -> CheckedSnapshot[T]:
        """This result's checked view — the same roots, delivered in band.

        A lightweight read-only view over the same storage: it performs no I/O,
        copies no root, and forwards :attr:`pin` and :attr:`edition` unchanged.
        """
        return CheckedSnapshot(self._roots, self._pin, self._edition)

    @overload
    def wire[R: Entity](self: Snapshot[R]) -> Snapshot[WireEntity]: ...

    @overload
    def wire[R: Entity](
        self: Snapshot[R],
        value: Entity,
        *,
        at: IncludePath[Entity, Any] | None = None,
    ) -> WireEntity: ...

    @overload
    def wire[R: Entity, E: Entity](
        self: Snapshot[R],
        value: InvalidData[E],
        *,
        at: IncludePath[Entity, Any] | None = None,
    ) -> InvalidData[WireEntity]: ...

    def wire(
        self,
        value: object = _WIRE_ALL,
        *,
        at: IncludePath[Entity, Any] | object | None = _WIRE_AT_OMITTED,
    ) -> Snapshot[WireEntity] | WireEntity | InvalidData[WireEntity]:
        """Publish this Typed result, or one eligible node, in canonical Wire form."""
        source = self._source
        if source is None:
            raise inspection_refusal(
                SNAPSHOT_WIRE_ENVELOPE_INELIGIBLE,
                "Snapshot.wire",
                "Wire projection is available only on a Typed Snapshot",
            )
        if value is _WIRE_ALL:
            if at is not _WIRE_AT_OMITTED:
                raise TypeError("whole-result Snapshot.wire() accepts no at= position")
            roots = cast("tuple[object, ...]", self._roots)
            pin = self._pin
            edition = self._edition
            del self
            projection = TypedWireProjection.for_call(source)
            try:
                return Snapshot(projection.project_roots(roots), pin, edition)
            finally:
                roots = ()
                projection.release()
        del self
        projection = TypedWireProjection.for_call(source)
        try:
            return projection.project(
                value,
                None if at is _WIRE_AT_OMITTED else cast("IncludePath[Entity, Any] | None", at),
            )
        finally:
            projection.release()

    @property
    def pin(self) -> Pin:
        """The query's OWN lowered as-of coordinates: only
        genuinely pinned axes — a scanned (``history`` / ``as_of_range``) axis
        is absent, per the core rule that a scan is not a pin."""
        return self._pin

    @property
    def edition(self) -> str:
        """The Model Edition the read that published this result adopted.

        Stamped when the result was built and retained for as long as the
        result is: reading it consults no Serving Model, so a publication
        landing after the read changes nothing here.
        """
        return self._edition

    def __repr__(self) -> str:
        return f"Snapshot(roots={len(self._roots)}, pin={self._pin!r})"

    def _require_valid(self) -> None:
        """Refuse once arity is settled, carrying exactly the roots in range.

        An accessor that already narrowed to one root has narrowed this tuple to
        that root's own record too, so the singular accessors report one and
        ``results()`` reports them all without either restating the rule. The
        refusal carries this result's own edition, because it is raised
        whenever the accessor is reached rather than while the read ran.
        """
        if self._invalid:
            raise invalid_result_refusal(self._invalid, edition=self._edition)


class CheckedSnapshot[T]:
    """A `Snapshot` whose roots are `T | InvalidData[T]`, so reads continue past bad rows.

    The whole eager checked surface: the same three arity accessors, the same
    :attr:`pin`, the same :attr:`edition`, and nothing else. It shares the
    result storage rather than owning a second copy of it, does no I/O, and
    refuses nothing a default accessor would have accepted — an invalid root
    simply arrives as its record instead of raising.
    """

    __slots__ = ("_edition", "_pin", "_roots")

    _roots: tuple[T | InvalidData[T], ...]
    _pin: Pin
    _edition: str

    def __init__(self, roots: tuple[T | InvalidData[T], ...], pin: Pin, edition: str) -> None:
        self._roots = roots
        self._pin = pin
        self._edition = edition

    def result(self) -> T | InvalidData[T]:
        """The single matched root, valid or classified; raises on zero or more
        than one."""
        return cast("T | InvalidData[T]", _sole(self._roots, empty_is_absence=False))

    def result_or_none(self) -> T | InvalidData[T] | None:
        """The single matched root, valid or classified, or ``None`` on zero;
        raises on more than one."""
        return _sole(self._roots, empty_is_absence=True)

    def results(self) -> list[T | InvalidData[T]]:
        """Every matched root, valid or classified, as a fresh ``list`` the
        caller owns and may partition with ordinary collection operations."""
        return list(self._roots)

    @property
    def pin(self) -> Pin:
        return self._pin

    @property
    def edition(self) -> str:
        return self._edition

    def __repr__(self) -> str:
        return f"CheckedSnapshot(roots={len(self._roots)}, pin={self._pin!r})"


AT_PAUSED_ROOT: Final = (
    "SnapshotStream.wire answers only while delivery is paused at a root of its current Page"
)


type SnapshotPublication = TypedPublication | WirePublication
"""The Snapshot lifecycle's Publication of one delivery, Typed or Wire.

:attr:`roots_of` is per Page rather than per result. Each Page's one Root View
is re-pointed at every root in turn, which keeps result scope a property of the
root being published rather than a mode the materializer is told about; a
page-scope publication may instead resolve a Page's roots together, and
otherwise ends in that same per-root pass. Every envelope it publishes is
stamped with the edition of the selection it was built over.
"""


class TypedPublication:
    """The Typed Publication of one delivery: frozen Entity instances, each node
    with a narrowed view retaining the selection's view keys to find it by.

    :meth:`project` answers only while :meth:`roots_of` is publishing a Page and
    the publication is unreleased. A caller runs only while that iterator is
    suspended at a root it yielded, and delivery releases the publication before
    any terminal failure reaches the caller, possibly with the iterator still
    suspended, so release withdraws availability itself rather than leaving it
    to the iterator's cleanup. The projection is allocated at the first
    :meth:`project`, so a delivery that never projects allocates none.
    """

    __slots__ = ("_construction", "_open_page", "_projection", "_selected", "_sharing_scope")

    def __init__(
        self,
        selected: SelectedReadModel,
        construction: EntityGraphConstruction,
        sharing_scope: SharingScope,
    ) -> None:
        self._selected = selected
        self._construction = construction
        self._sharing_scope: SharingScope = sharing_scope
        self._open_page: read_planning.IncludeTree | None = None
        self._projection: TypedWireProjection | None = None

    @property
    def representation(self) -> ResultRepresentation:
        return "typed"

    @property
    def edition(self) -> str:
        return self._selected.edition

    def roots_of(
        self,
        page: Page,
        includes: read_planning.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        origins: Mapping[int, ReadEvidence] = MappingProxyType({}),
        milestones: TemporalShape | None = None,
    ) -> Iterator[object]:
        self._open_page = includes
        projection = self._projection
        if projection is not None:
            projection.begin_page(includes)
        meta = self._selected.model.meta
        publisher = TypedRootPublisher(meta, self._construction, self._selected.narrowed_view_keys)

        def publish_root(root: GraphView, ordinal: int) -> tuple[object, ...]:
            # Stored state contradicting the model is no failure here: it was
            # classified before construction and publishes in band, so what
            # reaches this boundary is only a defect in building the Entity
            # graph a valid row describes.
            try:
                return publisher(root, ordinal)
            except Exception as exc:
                raise InternalError(
                    SNAPSHOT_MATERIALIZATION_FAILED,
                    "the read succeeded but its Entity graph could not be built",
                ) from exc

        try:
            yield from _publish_in_scope(
                page,
                publish_root,
                publisher.publish_shared_graph,
                meta,
                self._sharing_scope,
                atomic=atomic,
                ordinal_offset=ordinal_offset,
                origins=origins,
                milestones=milestones,
            )
        finally:
            self._open_page = None

    def project(
        self, value: object, at: IncludePath[Entity, Any] | None
    ) -> WireEntity | InvalidData[WireEntity]:
        """``value`` projected as Wire under the open Page's include shape."""
        includes = self._open_page
        if includes is None:
            raise UsageError(STREAM_STATE_INVALID, AT_PAUSED_ROOT)
        projection = self._projection
        if projection is None:
            projection = TypedWireProjection.for_delivery(
                self._construction, self._selected.wire, includes
            )
            self._projection = projection
        return projection.project(value, at)

    def release(self) -> None:
        self._open_page = None
        projection = self._projection
        self._projection = None
        if projection is not None:
            projection.release()

    def from_find(self, result: EagerPageResult[ReadEvidence], /) -> Snapshot[Any]:
        """``result``'s Page as a Snapshot at that read's own pin."""
        return _eager_snapshot(
            self,
            result.page,
            result.includes,
            result.page.pin,
            TypedWireSource(self._construction, self._selected.wire, result.includes),
            origins=result.origins,
        )

    def from_history(self, result: HistoryPageResult, /) -> Snapshot[Any]:
        """Every milestone's roots as ONE ordered result.

        Each milestone root is classified on its own, at its own milestone's
        edge, while a classified root's ordinal names its position in the flat
        published result. A milestone-set read carries no Include Path (`m-case-format`),
        so every root publishes root-only, and the outer pin
        is empty because a scan is not a pin.
        """
        return _eager_snapshot(
            self,
            result.page,
            result.includes,
            Pin(),
            TypedWireSource(self._construction, self._selected.wire, result.includes),
            milestones=result.milestones,
        )


class WirePublication:
    """The Wire Publication of one delivery: frozen declared-name value trees,
    rendered through the selection's prepared Wire facts.

    Its one delivery-scoped reuse state is the scalar encoder, created with the
    publication, rotated at each Page, and dropped at release, after which it
    publishes no further Page.
    """

    __slots__ = ("_encoder", "_selected", "_sharing_scope")

    def __init__(self, selected: SelectedReadModel, sharing_scope: SharingScope) -> None:
        self._selected = selected
        self._sharing_scope: SharingScope = sharing_scope
        self._encoder = wire_materialize.wire_scalar_cache()

    @property
    def representation(self) -> ResultRepresentation:
        return "wire"

    @property
    def edition(self) -> str:
        return self._selected.edition

    def roots_of(
        self,
        page: Page,
        includes: read_planning.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        origins: Mapping[int, ReadEvidence] = MappingProxyType({}),
        milestones: TemporalShape | None = None,
    ) -> Iterator[object]:
        encoder = self._encoder
        if encoder is None:
            raise RuntimeError("a released Wire publication cannot publish another Page")
        encoder.begin_page()
        meta = self._selected.model.meta
        publisher = WireRootPublisher(meta, self._selected.wire, includes, encoder)
        yield from _publish_in_scope(
            page,
            publisher,
            publisher.publish_shared_graph,
            meta,
            self._sharing_scope,
            atomic=atomic,
            ordinal_offset=ordinal_offset,
            origins=origins,
            milestones=milestones,
        )

    def project(self, value: object, at: IncludePath[Entity, Any] | None) -> NoReturn:
        """Refuse: a Wire envelope is no Typed value to project."""
        del value, at
        raise inspection_refusal(
            SNAPSHOT_WIRE_ENVELOPE_INELIGIBLE,
            "SnapshotStream.wire",
            "Wire projection is available only on a Typed Snapshot Stream",
        )

    def release(self) -> None:
        encoder = self._encoder
        self._encoder = None
        if encoder is not None:
            encoder.release()

    def from_find(self, result: EagerPageResult[ReadEvidence], /) -> Snapshot[Any]:
        """``result``'s Page as a Snapshot at that read's own pin."""
        return _eager_snapshot(
            self, result.page, result.includes, result.page.pin, None, origins=result.origins
        )

    def from_history(self, result: HistoryPageResult, /) -> Snapshot[Any]:
        """Every milestone's roots as ONE ordered result, at the empty pin."""
        return _eager_snapshot(
            self, result.page, result.includes, Pin(), None, milestones=result.milestones
        )


def _publish_in_scope[T](
    page: Page,
    publish_root: Callable[[GraphView, int], tuple[T, ...]],
    publish_shared_graph: Callable[[GraphView, Sequence[int]], tuple[T, ...]],
    meta: Metamodel,
    sharing_scope: SharingScope,
    *,
    atomic: bool,
    ordinal_offset: int,
    origins: Mapping[int, ReadEvidence],
    milestones: TemporalShape | None,
) -> Iterator[T]:
    if sharing_scope == "page":
        return publish_shared_roots(
            page,
            publish_root,
            publish_shared_graph,
            meta,
            atomic=atomic,
            ordinal_offset=ordinal_offset,
            milestones=milestones,
            read_evidence=origins,
        )
    return publish_roots(
        page,
        publish_root,
        meta,
        atomic=atomic,
        ordinal_offset=ordinal_offset,
        milestones=milestones,
        read_evidence=origins,
    )


def _eager_snapshot(
    publication: SnapshotPublication,
    page: Page,
    includes: read_planning.IncludeTree,
    pin: Pin,
    source: TypedWireSource | None,
    *,
    origins: Mapping[int, ReadEvidence] = MappingProxyType({}),
    milestones: TemporalShape | None = None,
) -> Snapshot[Any]:
    """``publication``'s one atomic publication of ``page``, released however it ends."""
    try:
        return Snapshot(
            tuple(
                publication.roots_of(
                    page, includes, atomic=True, origins=origins, milestones=milestones
                )
            ),
            pin,
            publication.edition,
            source,
        )
    finally:
        publication.release()


type WireQuery = ObjectQuery[Any, Any] | ObjectQueryNode | Mapping[str, object]
"""What a Wire read accepts: a canonical query mapping or node, or a Typed query.

What a Wire read accepts: the canonical Object Query mapping, the canonical
node itself, or — on a class-backed model — the Typed authoring value.
"""


def wire_read_query(query: WireQuery) -> ReadQuery:
    """``query`` as the unresolved input the shared read gate resolves.

    Accepting three spellings adds no query semantics: the mapping goes through
    `m-object-query`'s own deserializer and a node passes as itself, while the
    Typed value stays authored exactly as ``db.find`` hands it over, so it keeps
    the Typed operand policy rather than being encoded and decoded again.
    Nothing here validates the query — the shared read gate does, after the read
    adopts its selection and before any I/O — so all three spellings meet the
    same refusals.

    It is a stable converter a read is handed rather than a step the read
    performs first: a Wire read refuses re-entry before it looks at what it was
    handed, so a mapping no deserializer could accept is refused as re-entry
    when it arrives from inside a lifecycle context, exactly as an unusable Typed
    query is.
    """
    if isinstance(query, ObjectQueryNode):
        return query
    if isinstance(query, Mapping):
        return deserialize(query)
    return typed_read_query(query)


@dataclass(frozen=True, slots=True)
class TypedRepresentation:
    """A Typed read at one sharing scope."""

    sharing_scope: SharingScope

    @classmethod
    def at(cls, sharing_scope: SharingScope) -> TypedRepresentation:
        """The Typed representation at ``sharing_scope``, refusing any other value."""
        check_sharing_scope(sharing_scope)
        return TYPED if sharing_scope == "root" else TYPED_PAGE_SHARED

    def convert_query(self, query: ObjectQuery[Any, Any], /) -> ReadQuery:
        return typed_read_query(query)

    def publication_for(self, selected: SelectedReadModel, /) -> TypedPublication:
        """A Typed publication over ``selected``.

        It needs the graph construction, so this is where a selection that can
        materialize no Snapshot at all refuses a Typed read — before the query
        is judged, before a participating read's force-flush, and before any I/O.
        """
        construction = selected.construction
        if construction is None:
            raise UsageError(
                SNAPSHOT_CLASS_BACKED_MODEL_REQUIRED,
                "this read is served under a model that composed no Entity Class, so it "
                "cannot materialize a Snapshot",
            )
        return TypedPublication(selected, construction, self.sharing_scope)


@dataclass(frozen=True, slots=True)
class WireRepresentation:
    """A Wire read at one sharing scope.

    A Wire node is no Entity Class instance, so no materializer is required and
    no classless refusal applies.
    """

    sharing_scope: SharingScope

    @classmethod
    def at(cls, sharing_scope: SharingScope) -> WireRepresentation:
        """The Wire representation at ``sharing_scope``, refusing any other value."""
        check_sharing_scope(sharing_scope)
        return WIRE if sharing_scope == "root" else WIRE_PAGE_SHARED

    def convert_query(self, query: WireQuery, /) -> ReadQuery:
        return wire_read_query(query)

    def publication_for(self, selected: SelectedReadModel, /) -> WirePublication:
        return WirePublication(selected, self.sharing_scope)


TYPED: Final = TypedRepresentation("root")
TYPED_PAGE_SHARED: Final = TypedRepresentation("page")
WIRE: Final = WireRepresentation("root")
WIRE_PAGE_SHARED: Final = WireRepresentation("page")
