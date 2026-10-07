from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, cast, overload

from parallax.core import deep_fetch
from parallax.core.entity import Entity, EntityGraphConstruction, RelationshipPath
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.object_query._nodes import IncludePath
from parallax.core.object_query.validate import validate_include_path
from parallax.core.predicate import root_position
from parallax.core.read_delivery import InvalidData, InvalidDataError
from parallax.core.read_delivery._page import Page, page_edges
from parallax.core.read_delivery._page_reader import EagerPageResult, HistoryPageResult
from parallax.core.read_delivery._publication import RootsOf
from parallax.core.temporal_read import Edge, Pin, TemporalShape
from parallax.core.unit_work import ReadOrigin

if TYPE_CHECKING:
    from parallax.snapshot.materialize._wire import EntityReader

from parallax.core.execution._concurrency import CONCURRENCY
from parallax.core.execution._publication import SelectedReadModel
from parallax.snapshot._inspection import SnapshotInspectionError
from parallax.snapshot.handle._errors import SnapshotConnectionError, SnapshotMaterializationError
from parallax.snapshot.materialize import RootView, wire_roots
from parallax.snapshot.materialize._publication import publish_roots
from parallax.snapshot.materialize._typed import typed_root
from parallax.snapshot.materialize._wire import WireEntity

__all__ = [
    "CheckedSnapshot",
    "NoResultFound",
    "Snapshot",
    "SnapshotPublication",
    "TooManyResultsFound",
    "projection_concrete",
    "typed_publication",
    "typed_publication_for",
    "wire_position",
    "wire_publication",
    "wire_publication_for",
]


class NoResultFound(RuntimeError):
    """``Snapshot.result()`` matched zero roots."""


class TooManyResultsFound(RuntimeError):
    """``Snapshot.result()`` / ``.result_or_none()`` matched more than one root
    ."""


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
    """The Python reification of a core Snapshot Graph: ``db.find`` /
    ``tx.find``'s result. The complete surface: :meth:`result`,
    :meth:`result_or_none`, :meth:`results` (a FRESH ``list[T]`` per call),
    :meth:`checked`, :meth:`wire`,
    :attr:`pin` (the lowered as-of coordinates — only genuinely PINNED axes; a
    scanned axis is absent), :attr:`edition` (the Model Edition the read was
    served under), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, any lazy
    behavior, and every lifecycle accessor. A Typed result retains the request's
    canonical finite include shape and the graph construction that published it
    so :meth:`wire` can publish the value in memory; it retains no execution
    scope, Page, Root View, connection, authority, or other lifecycle of the read.

    A root whose stored state contradicted the model is held as its
    :class:`~parallax.core.read_delivery.InvalidData` record. The accessors
    here are the DEFAULT view: they check arity first and then refuse the read
    with :class:`~parallax.core.read_delivery.InvalidDataError`, so a caller
    who never asks about stored-data validity can never silently receive a
    record in place of an Entity. :meth:`checked` is the same storage read in
    band instead. There is no ignore posture and no partition API: a finite
    union is partitioned with ordinary collection operations.
    """

    __slots__ = ("_construction", "_edition", "_includes", "_invalid", "_pin", "_roots")

    _roots: tuple[T | InvalidData[T], ...]
    _invalid: tuple[InvalidData[object], ...]
    _pin: Pin
    _edition: str
    _includes: deep_fetch.IncludeTree | None
    _construction: EntityGraphConstruction | None

    def __init__(
        self,
        roots: tuple[T | InvalidData[T], ...],
        pin: Pin,
        edition: str,
        includes: deep_fetch.IncludeTree | None = None,
        construction: EntityGraphConstruction | None = None,
    ) -> None:
        self._roots = roots
        self._invalid = _invalid_records(roots)
        self._pin = pin
        self._edition = edition
        self._includes = includes
        self._construction = construction

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
        at: RelationshipPath[Entity, Any] | None = None,
    ) -> WireEntity: ...

    @overload
    def wire[R: Entity, E: Entity](
        self: Snapshot[R],
        value: InvalidData[E],
        *,
        at: RelationshipPath[Entity, Any] | None = None,
    ) -> InvalidData[WireEntity]: ...

    def wire(
        self,
        value: object = _WIRE_ALL,
        *,
        at: RelationshipPath[Entity, Any] | object | None = _WIRE_AT_OMITTED,
    ) -> Snapshot[WireEntity] | WireEntity | InvalidData[WireEntity]:
        """Publish this Typed result, or one eligible node, in canonical Wire form."""
        projection = self._construction
        includes = self._includes
        if projection is None or includes is None:
            raise SnapshotInspectionError(
                code="snapshot-wire-envelope-ineligible",
                message="Wire projection is available only on a Typed Snapshot",
                operation="Snapshot.wire",
            )
        if value is _WIRE_ALL:
            if at is not _WIRE_AT_OMITTED:
                raise TypeError("whole-result Snapshot.wire() accepts no at= position")
            values = self._roots
            pin = self._pin
            edition = self._edition
            del self
            try:
                projected = _project_eager_values(values, includes, projection, includes.root)
                return Snapshot(projected, pin, edition)
            finally:
                values = ()
        del self
        reader = _require_projection_inputs((value,), projection)
        position = wire_position(
            includes,
            reader.model,
            None if at is _WIRE_AT_OMITTED else cast("RelationshipPath[Entity, Any] | None", at),
        )
        return _project_eager_values((value,), includes, projection, position, reader=reader)[0]

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
            raise InvalidDataError(self._invalid, edition=self._edition)


def _require_projection_inputs(
    values: tuple[object, ...],
    projection: EntityGraphConstruction,
    *,
    operation: str = "Snapshot.wire",
) -> EntityReader:
    """Validate explicit inputs before resolving a separately supplied position."""
    from parallax.snapshot.materialize._wire import EntityReader

    reader = EntityReader(projection, operation=operation)
    for value in values:
        record = cast("InvalidData[object]", value) if isinstance(value, InvalidData) else None
        node: object | None = record.data if record is not None else cast("object", value)
        if node is None:
            continue
        projection_concrete(reader, node, operation=operation)
    return reader


def projection_concrete(
    reader: EntityReader, node: object, *, operation: str = "Snapshot.wire"
) -> EntityIdentity:
    """Require lifecycle identity and retained layout to describe one concrete."""
    from parallax.snapshot.materialize._wire import projection_entity

    concrete = projection_entity(node, operation=operation)
    layout = reader.layout(node)
    if layout.concrete != concrete:  # pragma: no cover - correspondence includes identity
        raise SnapshotInspectionError(
            code="snapshot-wire-input-incompatible",
            message=(
                f"{type(node).__name__} lifecycle identity {concrete.canonical} does not "
                f"match retained layout {layout.concrete.canonical}"
            ),
            operation=operation,
            entity=concrete,
        )
    return concrete


def wire_position(
    includes: deep_fetch.IncludeTree,
    model: CatalogedModel,
    path: RelationshipPath[Entity, Any] | None,
    *,
    operation: str = "Snapshot.wire",
) -> deep_fetch.PositionId:
    if path is None:
        return includes.root
    root = model.meta.entity(includes.queried)
    if root is None:  # pragma: no cover - the tree came from this exact model
        raise SnapshotInspectionError(
            code="snapshot-wire-at-unrequested",
            message=f"the retained model declares no query root {includes.queried.canonical}",
            operation=operation,
        )
    authored = IncludePath(
        segments=path.segments,
        applies_to=None
        if path.source is None or path.source == includes.queried.canonical
        else (path.source,),
    )
    try:
        resolved = validate_include_path(authored, model.meta, root_position(model.meta, root))
        position = includes.requested_position(resolved)
    except Exception as error:
        raise SnapshotInspectionError(
            code="snapshot-wire-at-unrequested",
            message=f"the requested projection position is not part of this read: {error}",
            operation=operation,
        ) from error
    if position is None:
        raise SnapshotInspectionError(
            code="snapshot-wire-at-unrequested",
            message="the requested projection position is not an exact prefix of this read",
            operation=operation,
        )
    return position


def _project_eager_values(
    values: tuple[object, ...],
    includes: deep_fetch.IncludeTree,
    projection: EntityGraphConstruction,
    position: deep_fetch.PositionId,
    *,
    reader: EntityReader | None = None,
) -> tuple[WireEntity | InvalidData[WireEntity], ...]:
    from parallax.snapshot.materialize._wire import (
        EntityReader,
        WireWalk,
        shared_wire_encoder,
    )
    from parallax.snapshot.materialize._wire_memo import StrongIdentityMemo

    walk: WireWalk[object] | None = None
    encoder: _DeliveryWireEncoder | None = None
    projected: list[WireEntity | InvalidData[WireEntity]] = []
    value: object | None = None
    record: InvalidData[object] | None = None
    node: object | None = None
    rendered: WireEntity | None = None
    try:
        for index in range(len(values)):
            value = values[index]
            record = cast("InvalidData[object]", value) if isinstance(value, InvalidData) else None
            node = record.data if record is not None else cast("object", value)
            if node is None:
                projected.append(cast("InvalidData[WireEntity]", record))
                continue
            if reader is None:
                reader = EntityReader(projection)
            concrete = projection_concrete(reader, node)
            if not includes.admits(position, concrete):
                raise SnapshotInspectionError(
                    code="snapshot-wire-at-concrete-mismatch",
                    message=(
                        f"{concrete.canonical} is not admitted at requested position {position}"
                    ),
                    operation="Snapshot.wire",
                    entity=concrete,
                )
            if walk is None:
                encoder = shared_wire_encoder()
                encoder.begin_page()
                walk = WireWalk(
                    reader,
                    includes,
                    encoder,
                    memo=StrongIdentityMemo(),
                )
            rendered = walk.position(node, position)
            projected.append(
                rendered
                if record is None
                else cast("InvalidData[WireEntity]", replace(record, data=rendered))
            )
        return tuple(projected)
    finally:
        if walk is not None:
            walk.clear()
        if reader is not None:
            reader.clear()
        projected.clear()
        values = ()
        value = None
        record = None
        node = None
        rendered = None
        if encoder is not None:
            encoder.release()


class CheckedSnapshot[T]:
    """A :class:`Snapshot`'s roots as ``T | InvalidData[T]``.

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


def edge_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (the Python binding: each
    milestone-set root is edge-pinned at its own milestone's from-instant).

    An axis the Entity does not declare answers absent on both sides, so the
    rendering needs no per-entity axis list of its own.
    """
    return Pin(tx_time=edge.tx_time_or_none, valid_time=edge.valid_time_or_none)


class _DeliveryWireEncoder(Protocol):
    def __call__(self, neutral_type: Any, value: Any, /) -> object: ...

    def begin_page(self) -> None: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SnapshotPublication:
    """Which materializer a read publishes through, as the ONE conversion every
    read reaches it by: the Snapshot lifecycle's Publication.

    Read execution and delivery are the same whichever materializer runs — the
    shared gate, the milestone-set dispatch, the Page read, the activity, and
    inside a transaction the lock derivation and the observation record.
    Passing the publication in is what lets that orchestration exist once
    instead of once per result form, so the equivalence the Typed and Wire
    interfaces promise is structural rather than maintained by inspection.

    :attr:`roots_of` is deliberately per-Page rather than per-result. The
    publication itself is delivery-scoped: an eager read uses it once and a
    stream reuses it across every bounded Page, then :attr:`release` drops any
    representation-specific reuse state. An eager
    find and a milestone-set find each publish one Page, while a streamed read
    publishes one bounded Page at a time. Every root receives a transient Root
    View, which keeps result scope a property of the root being published rather
    than a mode the materializer is told
    about. :meth:`from_find` and :meth:`from_history` are the two eager
    compositions over it, so neither is an independent conversion that could
    drift from the streamed one.

    ``interface`` is the same choice named for the Read activity that
    orchestration opens: which materializer publishes IS which read interface
    ran, so the two are one value rather than two that could disagree.
    ``edition`` is the Model Edition of the selection the publication was
    built over, and every envelope it publishes is stamped with it — the one
    place the stamp is applied, so no result form can be published without
    one.
    """

    interface: ReadInterface
    roots_of: RootsOf[ReadOrigin]
    edition: str
    release: Callable[[], None]
    construction: EntityGraphConstruction | None = None

    def from_find(self, result: EagerPageResult[ReadOrigin]) -> Snapshot[Any]:
        """``result``'s Page as a Snapshot at that read's own pin."""
        try:
            return Snapshot(
                tuple(
                    self.roots_of(
                        result.page,
                        result.includes,
                        atomic=True,
                        sources=result.sources,
                    )
                ),
                result.page.pin,
                self.edition,
                result.includes if self.construction is not None else None,
                self.construction,
            )
        finally:
            self.release()

    def from_history(self, result: HistoryPageResult) -> Snapshot[Any]:
        """Every milestone's roots as ONE ordered result.

        Each milestone root is classified through its own Root View while a
        classified root's ordinal names its position in the flat published
        result. A milestone-set read carries no Include Path (`m-case-format`),
        so every root publishes root-only, and the outer pin
        is empty because a scan is not a pin.
        """
        try:
            return Snapshot(
                tuple(
                    self.roots_of(
                        result.page,
                        result.includes,
                        atomic=True,
                        milestones=result.milestones,
                    )
                ),
                Pin(),
                self.edition,
                result.includes if self.construction is not None else None,
                self.construction,
            )
        finally:
            self.release()


def _release_nothing() -> None:
    pass


def typed_publication_for(selected: SelectedReadModel, /) -> SnapshotPublication:
    """The Typed publication of a read served under ``selected``.

    A Typed publication needs the graph construction, so this is where a
    selection that can materialize no Snapshot at all refuses a Typed read —
    before the query is judged, before a participating read's force-flush, and
    before any I/O. The publication carries the selection's edition, so every
    envelope it publishes is stamped with what the read was served under.
    """
    construction = selected.construction
    if construction is None:
        raise SnapshotConnectionError(
            "this read is served under a model that composed no Entity Class, so it "
            "cannot materialize a Snapshot (snapshot-class-backed-model-required)"
        )
    return typed_publication(selected.model, construction, selected.edition)


def wire_publication_for(selected: SelectedReadModel, /) -> SnapshotPublication:
    """The Wire publication of a read served under ``selected``.

    A Wire node is no Entity Class instance, so no materializer is required and
    no classless refusal applies.
    """
    return wire_publication(selected.model, selected.edition)


def typed_publication(
    model: CatalogedModel, construction: EntityGraphConstruction, edition: str
) -> SnapshotPublication:
    """Publish through the typed materializer: frozen Entity instances."""

    def roots_of(
        page: Page,
        includes: deep_fetch.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        sources: Mapping[int, ReadOrigin] = MappingProxyType({}),
        milestones: TemporalShape | None = None,
    ) -> Iterator[object]:
        del includes

        pins = tuple(
            None if edge is None else edge_pin(edge) for edge in page_edges(page, milestones)
        )

        def publish(root: RootView, position: int) -> Iterator[object]:
            yield from _materialize_result_page(
                root,
                model.meta,
                construction,
                ordinal_offset=ordinal_offset + position,
                sources=sources,
            )

        yield from publish_roots(
            page,
            publish,
            atomic=atomic,
            model=model.meta,
            ordinal_offset=ordinal_offset,
            pins=pins,
            prepare=lambda root: root.prime(sources),
        )

    return SnapshotPublication("typed", roots_of, edition, _release_nothing, construction)


def wire_publication(model: CatalogedModel, edition: str) -> SnapshotPublication:
    """Publish through the wire materializer: frozen declared-name value trees.

    ``model`` is the selection's cataloged model. Each node's family variant
    is read off the layout that catalog fixed, so the publication's one
    delivery-scoped reuse state is the scalar encoder.
    """

    from parallax.snapshot.materialize._wire import shared_wire_encoder

    encode: _DeliveryWireEncoder | None = shared_wire_encoder()
    released = False

    def release() -> None:
        nonlocal encode, released
        if released:
            return
        released = True
        if encode is not None:
            encode.release()
            encode = None

    def roots_of(
        page: Page,
        includes: deep_fetch.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        sources: Mapping[int, ReadOrigin] = MappingProxyType({}),
        milestones: TemporalShape | None = None,
    ) -> Iterator[object]:
        pins = tuple(
            None if edge is None else edge_pin(edge) for edge in page_edges(page, milestones)
        )

        nonlocal encode
        current = encode
        if released or current is None:
            raise RuntimeError("a released Wire publication cannot publish another Page")
        current.begin_page()

        def publish(root: RootView, position: int) -> Iterator[object]:
            yield from wire_roots(
                root,
                model.meta,
                CONCURRENCY,
                includes,
                ordinal_offset=ordinal_offset + position,
                sources=sources,
                encode=current,
            )

        yield from publish_roots(
            page,
            publish,
            atomic=atomic,
            model=model.meta,
            ordinal_offset=ordinal_offset,
            pins=pins,
            prepare=lambda root: root.prime(sources),
        )

    return SnapshotPublication("wire", roots_of, edition, release)


def _materialize_result_page(
    root: RootView,
    meta: Metamodel,
    construction: EntityGraphConstruction,
    *,
    ordinal_offset: int = 0,
    sources: Mapping[int, ReadOrigin] = MappingProxyType({}),
) -> tuple[Any, ...]:
    """Translate a graph-construction or lifecycle failure exactly once.

    Stored state that contradicts the model is no failure here: it was
    classified before construction and publishes in band, so what reaches this
    wrapper is only a defect in building the Entity graph a valid row describes.
    """
    try:
        return typed_root(
            root, meta, CONCURRENCY, construction, ordinal_offset=ordinal_offset, sources=sources
        )
    except Exception as exc:
        raise SnapshotMaterializationError(
            "the read succeeded but its Entity graph could not be built "
            "(snapshot-materialization-failed)",
            cause=exc,
        ) from exc
