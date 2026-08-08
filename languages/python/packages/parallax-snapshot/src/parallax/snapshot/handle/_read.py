"""``parallax.snapshot.handle._read`` — the production find executor and the
Snapshot result surface (m-deep-fetch / m-snapshot-read).

The module DAG's snapshot-handle scope already reaches `materialize` + `m-sql`
+ `m-db-port`, so the deliberate DAG-forbidden edges (`m-deep-fetch`/
`m-snapshot-read` may not import `m-sql`; `m-sql` may not import `m-navigate`/
`m-temporal-read`) are composed HERE, exactly like `_write_lowering` composes
the write-side `m-unit-work` x `m-sql` edge — one executor, production-owned:
`db.find` and `tx.find` both call the SAME :func:`find` / :func:`find_history`
and build the SAME
:class:`~parallax.snapshot.materialize.SnapshotGraphInput`, so the per-level
loop exists exactly once on the developer-facing path.

Each level's rows are materialized and converted one at a time: a converted node
names its correlation members, so the next level gathers its keys off the
converted parent rather than off a retained row. The port answers one statement
with its whole `list[Row]` (`m-db-port`), so that raw result set is the level's
own lifetime; what this module never does is build a second collection over it —
a materialized row is reachable only until its conversion, and no level
accumulates them. Nothing below this module holds a row, and no row survives into
the graph input, the Snapshot, or the observation record.

The executor's own results (:class:`ExecutedStatement`, :class:`Execution`,
:class:`FindResult`, :class:`HistoryFindResult`) stay
co-located with it, together with the developer-facing :class:`Snapshot`
surface they convert into and the pin helpers that carry a query's or a
milestone's as-of coordinates across that conversion. Those helpers stay here
rather than moving to the write side: `_write_inputs` imports this module, so
the reverse edge would close a cycle.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from parallax.core import deep_fetch, inheritance, op_algebra
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity import EntityGraphConstruction
from parallax.core.metamodel import AsOfAxisMetadata as AcceptedAsOfAxis
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    entity_by_name,
)
from parallax.core.sql_gen import CompiledRead, MaterializedReadRow, Statement, compile_read
from parallax.core.temporal_read import Edge, Pin, milestone_edge, statement_pin
from parallax.snapshot.handle._errors import SnapshotMaterializationError
from parallax.snapshot.handle._materializer import materialize_graph
from parallax.snapshot.materialize import (
    LevelContext,
    MergeScope,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeRef,
    attribute_value,
    convert_row,
    observable_columns,
)

__all__ = [
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "NoResultFound",
    "ObservationCollector",
    "Snapshot",
    "TooManyResultsFound",
    "find",
    "find_history",
]


@dataclass(frozen=True, slots=True)
class ExecutedStatement:
    """One statement this executor actually ran (or would run — the caller's own
    compile-eligibility posture is not this module's concern). ``duration`` is
    the WALL-CLOCK seconds the port's own ``execute`` call took — informational
    only (spec §3: never graded, never used for control flow)."""

    sql: str
    binds: tuple[object, ...]
    duration: float = 0.0


@dataclass(frozen=True, slots=True)
class Execution:
    """The ordered record of every statement one `find` / `find_history` call
    executed — the production analogue of the conformance adapter's `emissions`
    + `roundTrips`, built once here and consumed by both."""

    statements: tuple[ExecutedStatement, ...]

    @property
    def round_trips(self) -> int:
        return len(self.statements)


class NoResultFound(RuntimeError):
    """``Snapshot.result()`` matched zero roots (spec §2/§3)."""


class TooManyResultsFound(RuntimeError):
    """``Snapshot.result()`` / ``.result_or_none()`` matched more than one root
    (spec §2/§3)."""


class Snapshot[T]:
    """The Python reification of a core Snapshot Graph (spec §3): ``db.find`` /
    ``tx.find``'s result. The complete surface: :meth:`result`,
    :meth:`result_or_none`, :meth:`results` (a FRESH ``list[T]`` per call),
    :attr:`pin` (the lowered as-of coordinates — only genuinely PINNED axes; a
    scanned axis is absent), :attr:`execution` (per-statement ``sql`` /
    ``binds``, informational ``duration``, and ``round_trips``), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, and any lazy
    behavior — every accessor is a pure in-memory read over roots already
    materialized in full by ``db.find`` / ``tx.find``.
    """

    __slots__ = ("_execution", "_pin", "_roots")

    _roots: tuple[T, ...]
    _pin: Pin
    _execution: Execution

    def __init__(self, roots: tuple[T, ...], pin: Pin, execution: Execution) -> None:
        self._roots = roots
        self._pin = pin
        self._execution = execution

    def result(self) -> T:
        """The single matched root; raises on zero or more than one."""
        count = len(self._roots)
        if count == 0:
            raise NoResultFound("the snapshot matched no roots")
        if count > 1:
            raise TooManyResultsFound(f"the snapshot matched {count} roots, expected exactly 1")
        return self._roots[0]

    def result_or_none(self) -> T | None:
        """The single matched root, or ``None`` on zero; raises on more than one."""
        count = len(self._roots)
        if count == 0:
            return None
        if count > 1:
            raise TooManyResultsFound(f"the snapshot matched {count} roots, expected 0 or 1")
        return self._roots[0]

    def results(self) -> list[T]:
        """Every matched root as an ordinary ``list[T]`` the caller owns (a
        fresh copy per call — this accessor is unaffected by node immutability)."""
        return list(self._roots)

    @property
    def pin(self) -> Pin:
        """The query's OWN lowered as-of coordinates (spec §3): only
        genuinely pinned axes — a scanned (``history`` / ``as_of_range``) axis
        is absent, per the core rule that a scan is not a pin."""
        return self._pin

    @property
    def execution(self) -> Execution:
        """This find's execution record (per-statement ``sql`` / ``binds``,
        informational ``duration``, and ``round_trips``)."""
        return self._execution

    def __repr__(self) -> str:
        return (
            f"Snapshot(roots={len(self._roots)}, pin={self._pin!r}, "
            f"round_trips={self._execution.round_trips})"
        )


class ObservationCollector(Protocol):
    """Where :func:`find` hands each materialized row's observable state.

    Supplying one *is* the decision to observe: ``Transaction.find`` passes a
    collector and ``Database.find`` passes ``None``, so a non-transactional read
    — which has no unit of work to observe into — allocates no observation state
    at all rather than building a record and discarding it.

    The driver only ever hands rows over; it never reads a collector back. What
    it hands over is PHYSICAL-column keyed, so the collector snapshots the values
    a later write may need and retains no row and no node of its own.
    """

    def observe_row(
        self, entity: EntityIdentity, columns: Mapping[str, object], document: object | None
    ) -> None:
        """Take one materialized row's observable state.

        ``entity`` is the exact Entity that row's own compiled read resolved it
        to — a per-row fact under table-per-hierarchy, never the position the
        query targeted and never family-normalized — which is what a subsequent
        keyed write on that row resolves to as well. ``columns`` is every value
        the row materialized, keyed by physical column. ``document`` is the raw
        Structured Column the row arrived with under Relational Document
        Layout — provenance the member fan-out drops, so a Temporal Observation
        can retain it without a second read (`m-unit-work`) — and ``None`` under
        `Columns` layout.
        """
        ...


@dataclass(frozen=True, slots=True)
class FindResult:
    """A single-graph find's Snapshot Graph Input plus its execution record."""

    graph: SnapshotGraphInput
    execution: Execution


@dataclass(frozen=True, slots=True)
class HistoryFindResult:
    """A milestone-set find's ordered per-milestone graph inputs plus its
    (single-statement) execution record.

    Each entry is a root-only graph pinned at its own milestone's from-instant
    (m-snapshot-read "The whole-graph pin"); a v1 milestone-set graph carries no
    includes (m-case-format).
    """

    graphs: tuple[SnapshotGraphInput, ...]
    execution: Execution


def _new_roots() -> list[SnapshotNodeRef]:
    return []


@dataclass(slots=True)
class _Milestone:
    """One milestone-set partition under construction: its own merge scope, the
    chronological rank of the row that opened it, and its converted roots."""

    scope: MergeScope
    rank: tuple[object, ...]
    roots: list[SnapshotNodeRef] = field(default_factory=_new_roots)


def find(
    op: op_algebra.Operation,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    port: DbPort,
    *,
    lock: LockMode | None = None,
    observations: ObservationCollector | None = None,
) -> FindResult:
    """The one per-level deep-fetch / snapshot-materialization loop (m-deep-fetch
    "one query per non-empty relationship level"; m-snapshot-read "round trips").

    ``op`` is the read's raw operation: a `DeepFetch` node, or any other read
    operation planned with zero levels (root-only instance-form materialization
    — a plain snapshot read, or the source find behind a scenario `mutate`
    action). Canonicalizes the root query (`m-temporal-read` + `m-navigate`,
    composed here), compiles and executes it, then for each
    planned level: restricts the parent nodes to the ones a path-root guard admits
    (`FetchLevel.source_position`, m-deep-fetch — an excluded parent contributes no
    key and receives no attachment, so its view stays unset); gathers the distinct
    non-null parent keys; an empty gathered
    set attaches the empty/null relationship result and issues no child SQL; a
    back-reference level issues no SQL either (resolved through the merge scope's
    own graph-local identity map); otherwise compiles and executes ONE child query
    (carrying the level's declared relationship ordering), applies
    `familyVariant` materialization (`m-sql`) to its rows, and converts them.
    Every level is the same three steps — compile, execute, convert — with
    `familyVariant` materialization and each row's resolved concrete Entity coming
    from that level's OWN `~parallax.core.sql_gen.CompiledRead`, never re-derived
    here from the operation a second time.

    Keys are gathered and fanned back by MEMBER identity
    (`FetchLevel.owner` / `related`), which is what lets each
    level's rows be converted one at a time: no column-to-member
    inversion happens here, and no row outlives its own level.

    Returns the whole Snapshot Graph Input — every projection, the root
    references in result order, and the query's own lowered pin — plus the full
    ordered execution record.

    ``observations``, when supplied, takes every materialized row (root and each
    attached level) as the level materializes it, so a caller with a unit of work
    behind it can record what a later write needs. Omitting it is how a
    non-transactional read builds no observation state at all.
    """
    # ``meta`` is the accepted model the connected ``Database`` already holds, so
    # every level's own Entity resolves against it directly.
    root_entity = _metadata(meta, target)
    plan_ = deep_fetch.plan(root_entity, op, meta)
    statements: list[ExecutedStatement] = []
    scope = MergeScope(meta)

    root_compiled = compile_read(
        plan_.root_operation, meta, dialect, root_entity, result_form="instance", lock=lock
    )
    root_refs = _convert_level(scope, port, dialect, root_compiled, statements, observations)

    level_refs: list[tuple[SnapshotNodeRef, ...]] = []
    for level in plan_.levels:
        parents = _guarded_parents(scope, level, _parent_refs(level.parent, root_refs, level_refs))
        if level.is_back_reference:
            _attach_back_reference(scope, meta, level, parents)
            level_refs.append(())
            continue
        keys = _distinct_keys(scope, parents, _correlation_member(meta, level.owner.identity))
        if not keys:
            _attach_empty(scope, level, parents)
            level_refs.append(())
            continue
        child_target, child_op = level.child_operation(keys)
        child_entity = _metadata(meta, child_target)
        child_compiled = compile_read(
            child_op,
            meta,
            dialect,
            child_entity,
            result_form="instance",
            lock=lock,
        )
        # A child level takes its narrow from `FetchLevel.narrow_to` (consumed
        # inside `child_operation`), never from the compiled read — only the ROOT
        # has no planner-supplied narrow to fall back on.
        child_refs = _convert_level(scope, port, dialect, child_compiled, statements, observations)
        _attach_children(scope, meta, level, parents, child_refs)
        level_refs.append(child_refs)

    pin = deep_fetch_statement_pin(op, declaring_metadata(meta, root_entity.identity))
    return FindResult(graph=scope.build(root_refs, pin), execution=Execution(tuple(statements)))


def find_history(
    op: op_algebra.Operation, meta: Metamodel, dialect: Dialect, target: str, port: DbPort
) -> HistoryFindResult:
    """The milestone-set snapshot read (m-snapshot-read "The whole-graph pin";
    m-case-format "Milestone-set graphs"): `history` / `asOfRange` return the
    full matching milestone SET in one statement, partitioned here by each
    row's own edge (`~parallax.core.temporal_read.milestone_edge`) into one
    root-only graph per milestone, each with its OWN merge scope — graph-local
    identity never promises reuse across milestones.

    Each row is converted into its own milestone's scope as it materializes, so
    the partition holds converted nodes rather than a second copy of the result
    set; ordering is by the edge that OPENED each milestone,
    which is why the chronological rank is taken off the row while it is still
    live. The graphs come out in chronological edge order (Valid Time first,
    matching the corpus's own authored `then.graphs` order) rather than in the
    database's unspecified natural row order, and rows within one milestone keep
    that natural order.
    """
    metadata = _metadata(meta, target)
    plan_ = deep_fetch.plan(metadata, op, meta)
    if plan_.levels:
        # m-case-format: a v1 milestone-set read carries no includes.
        raise ValueError("a milestone-set (history / asOfRange) read carries no deep-fetch levels")
    # `declaring_metadata` resolves the entity whose as-of axes are this target's
    # FAMILY's actual temporal declaration (the root, for a participant —
    # temporality is family-wide, `m-inheritance`); every
    # `~parallax.core.temporal_read` per-entity primitive below (`milestone_edge`,
    # `_edge_sort_key`) MUST resolve through it rather than the queried target's
    # own (possibly locally-empty) axes.
    entity = declaring_metadata(meta, metadata.identity)
    compiled = compile_read(plan_.root_operation, meta, dialect, metadata, result_form="instance")
    statements: list[ExecutedStatement] = []
    milestones: dict[Edge, _Milestone] = {}
    for row in _execute_compiled(port, dialect, compiled, statements):
        edge = milestone_edge(entity, row.values)
        milestone = milestones.get(edge)
        if milestone is None:
            milestone = _Milestone(MergeScope(meta), _edge_sort_key(entity, row.values))
            milestones[edge] = milestone
        milestone.roots.append(
            convert_row(
                row.values,
                LevelContext(row.resolved_entity, compiled.documents),
                milestone.scope,
            )
        )
    graphs = tuple(
        milestone.scope.build(tuple(milestone.roots), _edge_pin(edge))
        for edge, milestone in sorted(milestones.items(), key=lambda entry: entry[1].rank)
    )
    return HistoryFindResult(graphs=graphs, execution=Execution(tuple(statements)))


def _convert_level(
    scope: MergeScope,
    port: DbPort,
    dialect: Dialect,
    compiled: CompiledRead,
    statements: list[ExecutedStatement],
    observations: ObservationCollector | None,
) -> tuple[SnapshotNodeRef, ...]:
    """Execute one level and convert each of its rows as that row materializes.

    The observation, when one is being collected, is taken from the SAME row the
    conversion reads, while that row is still live. It is deliberately physical:
    a Predecessor Row is column-keyed by contract, so the write side is served by
    its own explicitly physical extraction rather than by a converted node
    carrying columns it has no other use for.

    Each row is observed under its OWN resolved concrete Entity — the identity
    the conversion already builds its `LevelContext` from — rather than under
    the level-wide position the query addressed. The root and every level run
    through here, so that one rule reaches an abstract-target root's concrete,
    a polymorphic level's concrete, and an included child alike.
    """
    refs: list[SnapshotNodeRef] = []
    for row in _execute_compiled(port, dialect, compiled, statements):
        context = LevelContext(row.resolved_entity, compiled.documents)
        refs.append(convert_row(row.values, context, scope))
        if observations is not None:
            observations.observe_row(
                row.resolved_entity, observable_columns(row.values, context), row.document
            )
    return tuple(refs)


def _view_key(level: deep_fetch.FetchLevel) -> RelationshipViewKey:
    """The view ``level`` attaches under: its declared direction, plus the derived
    narrowed-view key when the level's attach key is not simply that direction's
    own name."""
    narrowed = None if level.attach_key == level.relationship.name else level.attach_key
    return RelationshipViewKey(level.relationship, narrowed)


def _attach_children(
    scope: MergeScope,
    meta: Metamodel,
    level: deep_fetch.FetchLevel,
    parents: tuple[SnapshotNodeRef, ...],
    children: tuple[SnapshotNodeRef, ...],
) -> None:
    """Fan one level's converted children back to their parents in memory,
    preserving fetched order within each to-many bucket."""
    assert level.related is not None
    related = _correlation_member(meta, level.related.identity)
    owner = _correlation_member(meta, level.owner.identity)
    buckets: dict[object, list[SnapshotNodeRef]] = {}
    for child in children:
        key = attribute_value(scope.node(child), related)
        buckets.setdefault(key, []).append(child)
    view = _view_key(level)
    for parent in parents:
        matched = buckets.get(attribute_value(scope.node(parent), owner), [])
        scope.attach(
            parent,
            view,
            tuple(matched) if level.to_many else (matched[0] if matched else None),
        )


def _attach_empty(
    scope: MergeScope, level: deep_fetch.FetchLevel, parents: tuple[SnapshotNodeRef, ...]
) -> None:
    """Attach the empty/null relationship result to every admitted parent.

    m-deep-fetch: an empty gathered parent-key set issues no child query at all,
    and every parent still gets a LOADED view — empty or null — rather than an
    unset one.
    """
    view = _view_key(level)
    empty: tuple[SnapshotNodeRef, ...] | None = () if level.to_many else None
    for parent in parents:
        scope.attach(parent, view, empty)


def _attach_back_reference(
    scope: MergeScope,
    meta: Metamodel,
    level: deep_fetch.FetchLevel,
    parents: tuple[SnapshotNodeRef, ...],
) -> None:
    """Resolve an ancestor-revisit level against the scope's own identity map.

    A back-reference issues no SQL: m-case-format's "Back-reference cycles"
    guarantees the ancestor is already converted, so the parent's own correlation
    member names a node this scope has already registered.
    """
    assert level.back_reference_family is not None
    view = _view_key(level)
    owner = _correlation_member(meta, level.owner.identity)
    for parent in parents:
        key = attribute_value(scope.node(parent), owner)
        if key is None:
            scope.attach(parent, view, () if level.to_many else None)
            continue
        referenced = scope.resolve(level.back_reference_family, (key,))
        if referenced is None:  # pragma: no cover - guards a malformed plan
            raise ValueError(
                f"back-reference {level.attach_key!r}: no already-converted "
                f"{level.back_reference_family.canonical} node for key {key!r} (m-case-format "
                "'Back-reference cycles' guarantees the ancestor is already known)"
            )
        scope.attach(parent, view, (referenced,) if level.to_many else referenced)


def _correlation_member(meta: Metamodel, attribute: AttributeIdentity) -> AttributeIdentity:
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


def _execute_compiled(
    port: DbPort, dialect: Dialect, compiled: CompiledRead, statements: list[ExecutedStatement]
) -> Iterator[MaterializedReadRow]:
    """Execute one compiled read, materializing its rows through its OWN transform.

    Takes the whole `~parallax.core.sql_gen.CompiledRead` rather than a statement
    plus a transform, so the two can only ever come from the same compile. That
    matters because `find` holds the root's and a child level's compiled reads in
    scope at the same time: crossing them is otherwise an ordinary-looking edit
    that raises deep inside the tag transform in one direction and, in the other,
    silently leaves the raw tag column standing where `familyVariant` should be.
    Keeping the pair bundled here is the caller-side half of `CompiledRead`'s own
    self-containment — it makes `find`'s "compile, execute, convert"
    structural rather than a convention every level has to remember.

    The statement runs and is recorded on the way in; the port's own whole-result
    `list[Row]` is what a row-returning execute answers by contract, and only the
    per-row materialization is lazy — so each MATERIALIZED row is reachable for
    exactly as long as its consumer takes to convert it, and the level never
    holds a second copy of its result set.
    """
    return map(compiled.materialize_row, _execute(port, dialect, compiled.statement, statements))


def _execute(
    port: DbPort, dialect: Dialect, statement: Statement, statements: list[ExecutedStatement]
) -> list[Row]:
    started = time.perf_counter()
    rows = port.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))
    statements.append(
        ExecutedStatement(statement.sql, statement.binds, time.perf_counter() - started)
    )
    return rows


def _parent_refs(
    parent: deep_fetch.ParentRef,
    root_refs: tuple[SnapshotNodeRef, ...],
    level_refs: Sequence[tuple[SnapshotNodeRef, ...]],
) -> tuple[SnapshotNodeRef, ...]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_refs
    return level_refs[parent.index]


def _guarded_parents(
    scope: MergeScope, level: deep_fetch.FetchLevel, parents: tuple[SnapshotNodeRef, ...]
) -> tuple[SnapshotNodeRef, ...]:
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
    if level.source_position is None:
        return parents
    admitted = frozenset(level.source_position)
    return tuple(parent for parent in parents if scope.node(parent).concrete_entity in admitted)


def _distinct_keys(
    scope: MergeScope, parents: tuple[SnapshotNodeRef, ...], member: AttributeIdentity
) -> list[op_algebra.Scalar]:
    """The distinct NON-NULL values of ``member`` across ``parents``, in first-
    encountered order (m-deep-fetch: the gathered set is unordered for grading
    purposes — an implementation MUST NOT sort at runtime to match a fixture —
    so encounter order is as good as any, and deterministic run to run).

    A gathered key is always a declared PRIMARY-KEY (or unique FK) attribute's
    own value — one of `m-op-algebra`'s neutral scalar types — even though a
    converted node's values are typed as plain ``object``; the cast reflects that
    runtime invariant, not a widening of the membership node's own typed-literal
    contract.
    """
    gathered = (attribute_value(scope.node(parent), member) for parent in parents)
    values = dict.fromkeys(value for value in gathered if value is not None)
    return cast("list[op_algebra.Scalar]", list(values))


def _metadata(meta: Metamodel, name: str) -> EntityMetadata:
    """``name``'s accepted Metadata within ``meta``, raising when it names no
    single declared Entity.

    A bare spelling two namespaces share names no single Entity and is the
    normative `reference-ambiguous-entity-name` refusal, carried by
    ``op_algebra``'s own :class:`~parallax.core.op_algebra.OperationRejectedError`
    so one rule and one class answer it whether preflight or this executor
    resolves the reference. Every other miss is unreachable: the root target was
    resolved by identity at preflight, and each level's own target is the
    canonical spelling its resolved position minted.
    """
    metadata = entity_by_name(meta, name)
    if metadata is not None:
        return metadata
    shared = sorted(
        candidate.identity.canonical
        for candidate in meta.entities
        if candidate.identity.name == name
    )
    if len(shared) > 1:
        raise op_algebra.OperationRejectedError(
            "reference-ambiguous-entity-name",
            f"{name!r}: the bare Entity spelling is shared by {shared}, so it names no single "
            "Entity in this model and the read resolves nowhere (m-op-algebra reference "
            "resolution)",
        )
    raise KeyError(name)  # pragma: no cover - preflight resolved this target by identity


def declaring_metadata(model: Metamodel, target: EntityIdentity) -> EntityMetadata:
    """The accepted Metadata of the position that DECLARES ``target``'s family
    facts — its family root, which for a standalone Entity is itself.

    Temporality and the physical primary key are family-wide and root-owned
    (`m-inheritance` "Inherited members"), so every per-entity milestone
    primitive below resolves through this rather than through the queried
    target's own (possibly locally empty) declaration.

    Keyed by Entity Identity rather than by an already-resolved Metadata, because
    a read's preflight answers an identity: the resolution is exact and the
    caller keeps no metadata it would otherwise have to thread.
    """
    position = inheritance.view(model).entity(target)
    root = model.entity(target if position is None else position.root)
    if root is None:  # pragma: no cover - preflight resolved this identity in this model
        raise ValueError(f"{target.canonical}: the model declares no family root")
    return root


def _start_column(entity: EntityMetadata, axis: AcceptedAsOfAxis) -> str:
    declared = entity.attribute(axis.start_attribute.name)
    if declared is None:  # pragma: no cover - an accepted axis names a declared Attribute
        raise ValueError(f"{entity.identity.canonical}: {axis.start_attribute.name} is undeclared")
    return declared.storage.name


def _edge_sort_key(entity: EntityMetadata, row: Row) -> tuple[object, ...]:
    """Valid Time first, then Transaction Time (m-sql's bind-order convention),
    each dimension's start-column value — used only to chronologically order a
    milestone-set read's per-milestone graphs, never to select or filter rows. A
    Temporal Dimension's member value IS that canonical rank, so the row that
    opens a milestone carries the rank of every row that joins it."""
    ordered = sorted(entity.declared_as_of_axes, key=lambda axis: axis.dimension.value)
    return tuple(row[_start_column(entity, axis)] for axis in ordered)


def _edge_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (spec §3: each
    milestone-set root is edge-pinned at its own milestone's from-instant).

    An axis the Entity does not declare answers absent on both sides, so the
    rendering needs no per-entity axis list of its own.
    """
    return Pin(tx_time=edge.tx_time_or_none, valid_time=edge.valid_time_or_none)


def deep_fetch_statement_pin(op: op_algebra.Operation, entity: EntityMetadata) -> Pin:
    """``snapshot.pin`` for ``op`` (spec §3): identical to
    ``~parallax.core.temporal_read.statement_pin``, except that an outer
    ``DeepFetch`` directive (``.include(...)`` composed after ``.as_of(...)``)
    is peeled first. ``m-temporal-read`` never imports ``m-deep-fetch`` (the
    DAG forbids the reverse dependency direction), so `statement_pin`'s own
    directive-peeling (`Limit`/`OrderBy`/`Distinct` only) cannot see a
    `DeepFetch` wrapper — this composition is the
    handle's own job. A milestone-set read (`.history()`/`.as_of_range()`)
    never reaches here carrying an outer `DeepFetch`: that combination builds as
    an ordinary valid Find Query and the read preflight refuses it by name
    (spec §3 ``snapshot-history-includes``) before any pin is derived, so this
    peel is unconditionally safe.
    """
    pin_op = op.operand if isinstance(op, op_algebra.DeepFetch) else op
    return statement_pin(pin_op, entity)


def snapshot_from_find_result(
    result: FindResult, meta: Metamodel, construction: EntityGraphConstruction
) -> Snapshot[Any]:
    roots = _materialized(lambda: materialize_graph(result.graph, meta, construction))
    return Snapshot(roots, result.graph.pin, result.execution)


def snapshot_from_history_result(
    result: HistoryFindResult, meta: Metamodel, construction: EntityGraphConstruction
) -> Snapshot[Any]:
    roots: list[Any] = []
    for graph in result.graphs:
        roots.extend(_materialized(lambda: materialize_graph(graph, meta, construction)))  # noqa: B023
    return Snapshot(tuple(roots), Pin(), result.execution)


def _materialized(build: Callable[[], tuple[object, ...]]) -> tuple[Any, ...]:
    """One graph's roots, or the single translation of a materialization failure.

    This is the ONE boundary where graph construction, lifecycle build, and
    state-factory failures become
    :class:`~parallax.snapshot.handle._errors.SnapshotMaterializationError`, so a
    caller sees exactly one wrapping with the original cause chained. Everything
    that failed BEFORE a graph was being built — the query, the connection, the
    transaction, the adapter, SQL generation, row conversion — has already
    raised with its own classification and never reaches here.
    """
    try:
        return build()
    except Exception as exc:
        raise SnapshotMaterializationError(
            "the read succeeded but its Entity graph could not be built "
            "(snapshot-materialization-failed)",
            cause=exc,
        ) from exc
