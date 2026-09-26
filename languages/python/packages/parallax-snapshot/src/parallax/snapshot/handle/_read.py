from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, cast, overload

from parallax.core import continuation, deep_fetch, inheritance, opt_lock, read_lock
from parallax.core import predicate as predicate_algebra
from parallax.core.db_port import (
    DatabaseConnection,
    Row,
)
from parallax.core.dialect import LockMode
from parallax.core.entity import Entity, EntityGraphConstruction, RelationshipPath
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    DatabaseCallScope,
    ReadActivity,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
)
from parallax.core.object_query._nodes import IncludePath
from parallax.core.object_query._validated import (
    ValidatedObjectQuery,
)
from parallax.core.object_query.validate import validate_include_path
from parallax.core.predicate import root_position
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import (
    Edge,
    Pin,
    TemporalShape,
    validated_query_pin,
)
from parallax.core.unit_work import Concurrency

if TYPE_CHECKING:
    from parallax.snapshot.materialize._wire import EntityReader

from parallax.snapshot._inspection import SnapshotInspectionError
from parallax.snapshot._read_result import (
    FindResult,
    HistoryFindResult,
    PublishedRow,
    RowsResult,
)
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._errors import SnapshotMaterializationError
from parallax.snapshot.handle._family import temporal_shape
from parallax.snapshot.handle._materialization import (
    INERT as MATERIALIZATION_INERT,
)
from parallax.snapshot.handle._materialization import (
    EagerPageRead,
    FlatPageRead,
    MaterializationObserver,
    Materializer,
    RowPublication,
    page_cadence,
)
from parallax.snapshot.handle._read_plan import UNCACHED_READ_PLANNER, ReadPlanner
from parallax.snapshot.handle._retention import (
    ObservationLedger,
    ObservedRows,
    ReadSources,
)
from parallax.snapshot.materialize import (
    ClassifiedRoot,
    InvalidData,
    InvalidDataError,
    Page,
    PageBuilder,
    RootView,
    classify_roots,
    page_edges,
    require_publishable,
    wire_roots,
)
from parallax.snapshot.materialize._page import ABSENT
from parallax.snapshot.materialize._prepared import PreparedRead, RowPublisher
from parallax.snapshot.materialize._typed import typed_root
from parallax.snapshot.materialize._views import (
    ROOT_LEVEL,
    ChildSlot,
    SourceLevel,
)
from parallax.snapshot.materialize._wire import WireEntity

__all__ = [
    "CheckedSnapshot",
    "NoResultFound",
    "PublishedRow",
    "ResultPublication",
    "RowsResult",
    "Snapshot",
    "TooManyResultsFound",
    "attach_back_reference",
    "attach_children",
    "attach_empty",
    "convert_rows",
    "correlation_member",
    "correlation_table",
    "entity_read_lock",
    "execute_read",
    "find",
    "find_history",
    "find_rows",
    "gather_keys",
    "guarded_parents",
    "parent_refs",
    "projection_concrete",
    "publishable_rows",
    "slot_table",
    "typed_publication",
    "wire_position",
    "wire_publication",
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
    canonical finite include shape and accepted model so :meth:`wire` can publish
    the value in memory; it retains no execution scope, Page, Root View,
    connection, authority, or other lifecycle of the read.

    A root whose stored state contradicted the model is held as its
    :class:`~parallax.snapshot.materialize.InvalidData` record. The accessors
    here are the DEFAULT view: they check arity first and then refuse the read
    with :class:`~parallax.snapshot.materialize.InvalidDataError`, so a caller
    who never asks about stored-data validity can never silently receive a
    record in place of an Entity. :meth:`checked` is the same storage read in
    band instead. There is no ignore posture and no partition API: a finite
    union is partitioned with ordinary collection operations.
    """

    __slots__ = ("_edition", "_includes", "_invalid", "_pin", "_projection_model", "_roots")

    _roots: tuple[T | InvalidData[T], ...]
    _invalid: tuple[InvalidData[object], ...]
    _pin: Pin
    _edition: str
    _includes: deep_fetch.IncludeTree | None
    _projection_model: CatalogedModel | EntityGraphConstruction | None

    def __init__(
        self,
        roots: tuple[T | InvalidData[T], ...],
        pin: Pin,
        edition: str,
        includes: deep_fetch.IncludeTree | None = None,
        projection_model: CatalogedModel | EntityGraphConstruction | None = None,
    ) -> None:
        self._roots = roots
        self._invalid = _invalid_records(roots)
        self._pin = pin
        self._edition = edition
        self._includes = includes
        self._projection_model = projection_model

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
        projection = self._projection_model
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
    projection: CatalogedModel | EntityGraphConstruction,
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
    projection: CatalogedModel | EntityGraphConstruction,
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


def entity_read_lock(
    meta: Metamodel, entity: EntityIdentity, preference: Concurrency | None
) -> LockMode | None:
    """The read-lock mode a participating read of ``entity`` carries, composed
    from the two policies this scope legally names at once.

    The lock follows the ENTITY, not the query: `m-opt-lock` derives that
    Entity's Effective Concurrency Strategy from the unit of work's one
    Concurrency Preference and the Entity's own Optimistic Lock Facet, and
    `m-read-lock` maps the derived strategy to the `m-dialect` lock parameter.
    So one transaction's deep fetch locks its unversioned levels while leaving
    its versioned and temporal ones lock-free, and the same level locks or not
    depending on the model rather than on the call.

    ``preference`` is ``None`` for a read no unit of work owns — a standalone
    :meth:`~parallax.snapshot.handle.ScopedDatabase.find` — which has no participation
    to derive a strategy from and therefore never locks.
    """
    if preference is None:
        return None
    return read_lock.mode_for(
        opt_lock.effective_strategy(preference, opt_lock.view(meta).key(entity))
    )


def find(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    preference: Concurrency | None = None,
    ledger: ObservationLedger | None = None,
    calls: DatabaseCallScope = INERT,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
    edition: str = "",
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> FindResult:
    """The whole-result read: every root ``query`` matches, with its included values.

    `Materializer.read_page` executes the root statement, converts its positional
    rows, and reads each planned level into one Page through one orchestration
    path.

    ``query`` is the read's canonical Object Query: one carrying Include Paths,
    or any other query planned with zero levels (root-only instance-form
    materialization — a plain snapshot read, or the source find behind a
    scenario `mutate` action).

    ``model`` is the connected model as one value: the accepted Metamodel every
    level's own Entity resolves against, and the exact-model layout catalog
    every level's conversion reads its applicable member set from. The two
    travel together rather than as two arguments, so no read can be handed
    layouts derived from a model other than the one it resolves against, and one
    connection reads share one catalog whatever they address. The Page
    builder holds neither: a row arrives already associated with its layout, so the builder
    names no model to disagree with the one its rows were converted under.

    ``preference`` is the owning unit of work's Concurrency Preference, and
    EVERY level derives its own read lock from it against that level's own
    target Entity (:func:`entity_read_lock`): a versioned root reads lock-free
    while an unversioned included Entity in the same transaction takes the
    shared lock. Omitting it is how a non-transactional read locks nothing at
    all.

    ``ledger`` is the participating unit of work this read's evidence is indexed
    into and stamped with. Omitting it is what makes a read STANDALONE: its
    values still carry the evidence they observed — a value's write evidence
    belongs to the value — and simply name no participation, so an
    effective-Optimistic write may import that evidence while an
    effective-Locking one cannot.

    ``calls`` is the scope this executor brackets its Database Calls against,
    handed down by whichever composition root owns the operation: the Read a
    standalone read's own root opened, or the Read a participating read's
    transaction attempt opened. It is the narrower Database Call scope rather
    than a Read because opening calls is the whole of what this executor asks of
    it. Passing the shared inert activity — which omitting the argument does —
    runs the same code and emits nothing, and is what the default path, a
    declined root, and one page of a streamed read do.
    """
    return Materializer(observer).read_page(
        EagerPageRead(query, model, port, preference, ledger, calls, planner, edition)
    )


def publishable_rows(
    model: CatalogedModel,
    compiled: CompiledRead,
    read: Callable[[], Sequence[Row]],
    *,
    pin: Pin,
) -> RowPublication:
    """Materialize and validate one predicate-write batch.

    A predicate write has no in-band channel for a stored-data verdict, so it
    applies the publication gate before deriving observations or writes. History
    and row reads publish invalid roots in band through their own Root View
    publication.
    """
    materializer = Materializer()
    staged = materializer.read_page(FlatPageRead(model, compiled, read, pin))

    def require(root: RootView, _position: int) -> Iterator[object]:
        require_publishable(root)
        return iter(())

    tuple(materializer.roots(staged.page, require))
    return staged


def find_rows(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    edition: str,
    preference: Concurrency | None = None,
    read: ReadActivity = INERT,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> RowsResult:
    """The row-form read: one statement and one Page of transformed roots.

    The transformed row is the returned representation, so the values lane builds
    no typed object graph. It does build a Page, which is what classification
    runs over: a row whose own stored state contradicted the model publishes its
    :class:`~parallax.snapshot.materialize.InvalidData` record in place of itself,
    carrying the row when the collapse produced one and nothing when no value
    could be produced without inventing it. What it shares with :func:`find` is
    everything that decides behavior: the same canonical root query
    (`deep_fetch.plan` injects the as-of predicate and canonicalizes navigation
    for both lanes), the same
    private :func:`~parallax.core.sql_gen._compile.compile_read` with the lane selected by
    ``result_form``, and the same Database Call bracket. ``edition`` is the
    Model Edition ``model`` was selected under, which the result retains.

    A row-form read materializes no relationships, and the shared read gate
    (:func:`~parallax.snapshot.handle._preflight.preflight`) refuses a
    request that asks this lane for one — before any I/O, and before a
    participating read's force-flush — so the plan reaching here carries no
    level to drop.
    """
    meta = model.meta
    plan = planner.plan(
        edition=edition,
        model=model,
        dialect=port.dialect,
        query=query,
        result_form="row",
        preference=preference,
    )
    compiled, prepared = plan.root_read()

    stage = Materializer(observer).read_page(
        FlatPageRead(
            model,
            compiled,
            lambda: execute_read(port, compiled, read),
            validated_query_pin(query.temporal),
            prepared,
        )
    )
    return RowsResult(rows=_published_rows(stage, meta, prepared.row_publisher()), edition=edition)


def _published_rows(
    stage: RowPublication, meta: Metamodel, publisher: RowPublisher
) -> tuple[PublishedRow, ...]:
    """One published element per staged row, in result order."""

    def publish(root: RootView, position: int) -> Iterator[PublishedRow]:
        (verdict,) = classify_roots(root, meta, CONCURRENCY, ordinal_offset=position).roots
        node = root.roots[0]
        detached = (
            None
            if node is None
            else MappingProxyType(
                publisher.publish(
                    root.layout(node).concrete, root.member_values(node), stage.variants[position]
                )
            )
        )
        if isinstance(verdict, ClassifiedRoot):
            yield cast(
                "InvalidData[Mapping[str, object]]",
                verdict.published(detached),
            )
            return
        if detached is None:  # pragma: no cover - a valid verdict names one node
            raise ValueError("row publication requires one materialized root state")
        yield detached

    return tuple(
        Materializer(page_cadence(stage.page)).roots(stage.page, publish, atomic=True, model=meta)
    )


def find_history(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    read: ReadActivity = INERT,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
    edition: str = "",
    preference: Concurrency | None = None,
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> HistoryFindResult:
    """The flat milestone-set Snapshot read.

    ``history`` and ``asOfRange`` return the full matching milestone sequence in
    one statement and one Page. Continuation order is authored before SQL
    compilation, so the flat roots already rank by logical key and canonical axis
    starts. Each Root View is classified independently; a valid root retains its
    edge as the publication pin, while an invalid edge remains in band with no
    pin. A milestone-set query carries no includes, so the Page schema is
    root-only.
    """
    meta = model.meta
    metadata = query.root
    ordered = continuation.ordered(query, meta)
    plan = planner.plan(
        edition=edition,
        model=model,
        dialect=port.dialect,
        query=ordered,
        result_form="instance",
        preference=preference,
    )
    if plan.fetch_count:  # pragma: no cover - validated milestone queries cannot include
        # m-case-format: a v1 milestone-set read carries no includes.
        raise ValueError("a milestone-set (history / asOfRange) read carries no fetch steps")
    # Temporality is family-wide (`m-inheritance`), so every milestone edge the
    # result derives (`page_edges`) reads the family's shared Temporal Shape
    # rather than the queried target's own, possibly locally empty, axes.
    shape = temporal_shape(meta, metadata)
    compiled, prepared = plan.root_read()

    stage = Materializer(observer).read_page(
        FlatPageRead(model, compiled, lambda: execute_read(port, compiled, read), Pin(), prepared)
    )

    return HistoryFindResult(page=stage.page, milestones=shape, includes=plan.include_tree())


def convert_rows(
    builder: PageBuilder,
    source: SourceLevel,
    prepared: PreparedRead,
    rows: Iterable[Row],
    observations: ObservedRows,
    correlation_members: tuple[AttributeIdentity, ...] = (),
) -> tuple[int, ...]:
    """Convert ``rows`` into ``builder``, observing each one while it is still live.

    ``prepared`` is the read those provider rows convert and are observed under:
    the layout, projected
    documents, and attribute contracts a row needs were derived when that read
    was bound, so nothing here re-derives what the statement projected.

    ``source`` is where in the plan these rows land, which is what sizes each
    projection's view row: the levels attaching BELOW this one are what its rows
    can receive.

    The observation records the SAME row's raw document and pairs it with the
    occurrence conversion produced. Once a Root View judges that occurrence,
    evidence reads the Page-owned Entity State through its physical-key mapping
    view; no second member row is decoded or reconstructed.

    Each row is observed under its OWN resolved concrete Entity — the level the
    conversion resolved for it — rather than under the level-wide position the
    query addressed. The root and every level run through here, so that one rule
    reaches an abstract-target root's concrete, a polymorphic level's concrete,
    and an included child alike.

    A NON-HYDRATING projection is observed by nothing: no conforming value exists
    for it, so it publishes no writable source and can carry no claim. A
    hydratable one is observed like any other — the collapse produced legal
    member values, and the row behind it is the ordinary stored row a later write
    settles against.
    """
    refs: list[int] = []
    for row in rows:
        ref, resolved, document, _variant = prepared.convert_driver(
            row, builder, source=source, correlation_members=correlation_members
        )
        refs.append(ref)
        observations.observe_occurrence(ref, resolved, document)
    return tuple(refs)


def correlation_table(
    plan: deep_fetch.ObjectQueryPlan, meta: Metamodel
) -> tuple[tuple[AttributeIdentity, ...], ...]:
    """Correlation members decoded during the identity pass for each source level."""
    table: list[list[AttributeIdentity]] = [[] for _ in range(len(plan.fetch_steps) + 1)]
    for index, step in enumerate(plan.fetch_steps):
        parent_source = (
            ROOT_LEVEL if isinstance(step.parent, deep_fetch.RootRef) else step.parent.index + 1
        )
        table[parent_source].append(correlation_member(meta, step.owner.identity))
        if isinstance(step, deep_fetch.QueryFetchStep):
            table[index + 1].append(correlation_member(meta, step.related.identity))
    return tuple(tuple(dict.fromkeys(members)) for members in table)


def slot_table(plan: deep_fetch.ObjectQueryPlan) -> tuple[tuple[ChildSlot, ...], ...]:
    """Which view slots each source level's parents can receive, indexed by
    source position: the root is 0 and fetch step ``i`` is ``i + 1``.

    A level contributes one slot to whichever source level its own PARENT rows
    came from, carrying that level's path-root guard as the concretes it admits.
    The table is dense over every source level the plan can produce a projection
    at — a level attaching nothing still owns an empty entry, and a
    back-reference level, which converts no row of its own, is simply never
    named as a parent.

    This is where the plan vocabulary stops: what crosses into ``materialize`` is
    slots, so nothing there interprets a fetch plan.
    """
    table: list[list[ChildSlot]] = [[] for _ in range(len(plan.fetch_steps) + 1)]
    for step in plan.fetch_steps:
        position = plan.includes.position(step.position)
        assert position.view is not None
        parent = (
            ROOT_LEVEL if isinstance(step.parent, deep_fetch.RootRef) else step.parent.index + 1
        )
        parent_position = plan.includes.position(position.parent or plan.includes.root)
        table[parent].append(
            ChildSlot(
                position.view,
                None if position.source == parent_position.target else frozenset(position.source),
            )
        )
    return tuple(tuple(slots) for slots in table)


def attach_children(
    builder: PageBuilder,
    meta: Metamodel,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.QueryFetchStep,
    parents: tuple[int, ...],
    children: tuple[int, ...],
) -> None:
    """Fan one level's converted children back to their parents in memory,
    preserving fetched order within each to-many bucket."""
    position = tree.position(step.position)
    assert position.view is not None
    related = correlation_member(meta, step.related.identity)
    owner = correlation_member(meta, step.owner.identity)
    buckets: dict[object, list[int]] = {}
    for child in children:
        buckets.setdefault(builder.member_value(child, related), []).append(child)
    for parent in parents:
        matched = buckets.get(builder.member_value(parent, owner), [])
        builder.write_view(
            parent,
            position.view,
            tuple(matched) if position.to_many else (matched[0] if matched else None),
        )


def attach_empty(
    builder: PageBuilder,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.QueryFetchStep,
    parents: tuple[int, ...],
) -> None:
    """Attach the empty/null relationship result to every admitted parent.

    m-deep-fetch: an empty gathered parent-key set issues no child query at all,
    and every parent still gets a LOADED view — empty or null — rather than an
    unset one.
    """
    position = tree.position(step.position)
    assert position.view is not None
    empty: tuple[int, ...] | None = () if position.to_many else None
    for parent in parents:
        builder.write_view(parent, position.view, empty)


def attach_back_reference(
    builder: PageBuilder,
    meta: Metamodel,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.BackReferenceFetchStep,
    parents: tuple[int, ...],
) -> None:
    """Resolve an ancestor-revisit level against the scope's own identity map.

    A back-reference issues no SQL: m-case-format's "Back-reference cycles"
    guarantees the ancestor is already converted, so the parent's own correlation
    member names a projection this builder has already registered.

    An absent correlation member and a stored null both resolve nothing, and both
    leave the loaded-empty or loaded-null result behind: a parent that names no
    ancestor reaches none whichever of the two its row holds.
    """
    position = tree.position(step.position)
    assert position.view is not None
    owner = correlation_member(meta, step.owner.identity)
    for parent in parents:
        key = builder.member_value(parent, owner)
        if key is None or key is ABSENT:
            builder.write_view(parent, position.view, () if position.to_many else None)
            continue
        referenced = builder.resolve(step.family, key)
        if referenced is None:  # pragma: no cover - guards a malformed plan
            raise ValueError(
                f"back-reference {position.view.relationship.name!r}: no already-converted "
                f"{step.family.canonical} node for key {key!r} (m-case-format "
                "'Back-reference cycles' guarantees the ancestor is already known)"
            )
        builder.write_view(
            parent,
            position.view,
            (referenced,) if position.to_many else referenced,
        )


def correlation_member(meta: Metamodel, attribute: AttributeIdentity) -> AttributeIdentity:
    """The Identity a converted node carries for the member ``attribute`` names.

    A relationship join addresses a correlation Attribute at the POSITION it
    reaches it through, which for an inheritance participant may be a descendant
    of the position that declares it (`Person.pets` joins `Pet.ownerId` for an
    Attribute `Animal` declares). A converted node keys every family-effective
    member by its own DECLARING identity, so the two spellings must be reconciled
    once here rather than by loosening how a node is keyed.

    Resolution runs over the addressed position's own ancestry chain rather than
    the family-wide projection superset, which is what keeps the member addressed
    where the join names it: disjoint sibling branches may reuse a member name
    (`m-inheritance` "Members do not shadow across ancestry"), so the superset can
    hold two same-named Attributes and only the chain distinguishes them.
    """
    position = inheritance.view(meta).entity(attribute.entity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return attribute
    declared = position.applicable_attribute(attribute.name)
    if declared is None:  # pragma: no cover - a resolved join names a declared member
        return attribute
    return declared.identity


def execute_read(
    port: DatabaseConnection, compiled: CompiledRead, calls: DatabaseCallScope
) -> list[Row]:
    """Run one compiled read's statement inside its own Database Call bracket.

    A FAILED call finishes too, and the failure then propagates untouched: a
    call that reached the port and came back is work the lifecycle owes an
    account of, whatever it came back with. The bracket owns that, so this
    function announces only the rows it alone holds. Every read this
    package issues — a find level, and the resolving read a materializing
    predicate write runs — goes through here, so the duration and failed-call
    semantics of a `read` call have exactly one definition.

    Takes the whole ``CompiledRead`` rather than a statement plus its document
    ordinals: the statement, the ordinals it must be executed with, and the
    target Entity the activity reports all come from one compile or from none.
    """
    statement = compiled.statement
    document_reads = compiled.document_reads
    with calls.database_call(statement, "read", compiled.target) as call:
        driver_sql = port.dialect.to_driver_sql(statement.sql)
        binds = list(statement.binds)
        rows = (
            port.execute(driver_sql, binds, document_reads)
            if document_reads
            else port.execute(driver_sql, binds)
        )
        call.read_completed(rows)
    return rows


def parent_refs(
    parent: deep_fetch.ParentRef,
    root_refs: tuple[int, ...],
    level_refs: Sequence[tuple[int, ...]],
) -> tuple[int, ...]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_refs
    return level_refs[parent.index]


def guarded_parents(
    builder: PageBuilder,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.FetchStep,
    parents: tuple[int, ...],
) -> tuple[int, ...]:
    """The parent nodes a path-root guard admits into ``level``
    (m-deep-fetch "Path-root guards").

    A guard is a SOURCE filter, not a view: it selects which already-converted
    parents this level gathers keys from and attaches to, so an excluded parent
    never sees the level's view at all — the closed-world distinction
    between "no such related row" and "this object never participated". Selection
    is by each parent's OWN resolved concrete Entity, which is exactly what a
    guard's resolved source set enumerates. An unguarded level returns the
    sequence unchanged.
    """
    position = tree.position(step.position)
    assert position.parent is not None
    if position.source == tree.position(position.parent).target:
        return parents
    admitted = frozenset(position.source)
    return tuple(parent for parent in parents if builder.concrete_of(parent) in admitted)


def gather_keys(
    builder: PageBuilder, parents: tuple[int, ...], member: AttributeIdentity
) -> list[predicate_algebra.Scalar]:
    """The values of ``member`` across ``parents`` that name something.

    A member this level's parents did not carry and one stored null are distinct
    answers now and both drop out here: neither names a child row, so gathering
    either would widen the child query by a key nothing joins on.

    A gathered key is always a declared PRIMARY-KEY (or unique FK) attribute's
    own value — one of `m-predicate`'s neutral scalar types — even though a
    projection's values are typed as plain ``object``; the cast reflects that
    runtime invariant, not a widening of the membership node's own typed-literal
    contract.
    """
    keys: list[predicate_algebra.Scalar] = []
    seen: set[predicate_algebra.Scalar] = set()
    for value in (builder.member_value(parent, member) for parent in parents):
        if value is None or value is ABSENT:
            continue
        key = cast("predicate_algebra.Scalar", value)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def edge_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (the Python binding: each
    milestone-set root is edge-pinned at its own milestone's from-instant).

    An axis the Entity does not declare answers absent on both sides, so the
    rendering needs no per-entity axis list of its own.
    """
    return Pin(tx_time=edge.tx_time_or_none, valid_time=edge.valid_time_or_none)


class RootsOf(Protocol):
    """One materializer's publication of the roots one sealed Page carries.

    The whole conversion, in one call: form each Root View, classify its root, and
    publish the ones that hydrate. ``includes`` is the requested Include Path
    tree, which the Wire unwind bounds its walk by and the typed construction
    does not consult. ``ordinal_offset`` is where this Page's roots start in
    the ordered result being published, which is nonzero wherever one result
    spans several Pages. ``sources`` is the Read Origin the executor retained
    per PROJECTION, which each published node carries so a later keyed write
    reads its evidence off the value it was handed.
    """

    def __call__(
        self,
        page: Page,
        includes: deep_fetch.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
        milestones: TemporalShape | None = None,
    ) -> Iterator[object]: ...


class _DeliveryWireEncoder(Protocol):
    def __call__(self, neutral_type: Any, value: Any, /) -> object: ...

    def begin_page(self) -> None: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ResultPublication:
    """Which materializer a read publishes through, as the ONE conversion every
    orchestration reaches it by.

    A handle's read orchestration is the same whichever materializer runs — the
    shared gate, the milestone-set dispatch, the executor entry, the activity the
    handle hands down, and inside a transaction the lock derivation and the
    observation record. Passing the publication in is what lets that
    orchestration exist once per handle instead of once per result form, so the
    equivalence the Typed and Wire interfaces promise is structural rather than
    maintained by inspection.

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
    roots_of: RootsOf
    edition: str
    release: Callable[[], None]
    construction: EntityGraphConstruction | None = None

    def from_find(self, result: FindResult) -> Snapshot[Any]:
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

    def from_history(self, result: HistoryFindResult) -> Snapshot[Any]:
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


def typed_publication(
    model: CatalogedModel, construction: EntityGraphConstruction, edition: str
) -> ResultPublication:
    """Publish through the typed materializer: frozen Entity instances."""

    def roots_of(
        page: Page,
        includes: deep_fetch.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
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

        yield from Materializer(page_cadence(page)).roots(
            page,
            publish,
            atomic=atomic,
            model=model.meta,
            ordinal_offset=ordinal_offset,
            pins=pins,
            prepare=lambda root: root.prime(sources),
        )

    return ResultPublication("typed", roots_of, edition, _release_nothing, construction)


def wire_publication(model: CatalogedModel, edition: str) -> ResultPublication:
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
        sources: ReadSources = MappingProxyType({}),
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

        yield from Materializer(page_cadence(page)).roots(
            page,
            publish,
            atomic=atomic,
            model=model.meta,
            ordinal_offset=ordinal_offset,
            pins=pins,
            prepare=lambda root: root.prime(sources),
        )

    return ResultPublication("wire", roots_of, edition, release)


def _materialize_result_page(
    root: RootView,
    meta: Metamodel,
    construction: EntityGraphConstruction,
    *,
    ordinal_offset: int = 0,
    sources: ReadSources = MappingProxyType({}),
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
