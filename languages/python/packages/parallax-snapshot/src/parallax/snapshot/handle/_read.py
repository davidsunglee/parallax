"""``parallax.snapshot.handle._read`` — the production find executor and the
Snapshot result surface (m-deep-fetch / m-snapshot-read).

The module DAG's snapshot-handle scope already reaches `materialize` + `m-sql`
+ `m-db-port`, so the edges the DAG declares nowhere (`m-deep-fetch` may not
import `m-sql`; `m-sql` may not import `m-navigate`/`m-temporal-read`) are
composed HERE, exactly like `_write_lowering` composes
the write-side `m-unit-work` x `m-sql` edge — one executor, production-owned:
`db.find` and `tx.find` both call the SAME :func:`find` / :func:`find_history`
and build the SAME
:class:`~parallax.snapshot.materialize.SnapshotGraph`, so the per-level
loop exists exactly once on the developer-facing path.

Graph levels materialize and convert rows one at a time: a converted node names
its correlation members, so the next level gathers keys from the converted
parent rather than a retained row. Flat-row, history, and predicate-write lanes
instead stage one tuple of SQL-materialized rows and merge them once, before any
consumer-specific derivation, so each lane classifies or refuses that one staging
graph rather than judging rows as it walks them. The port's raw
`list[Row]` remains one statement's own lifetime, and neither raw nor
SQL-materialized rows survive into a sealed graph, a Snapshot, or a lifecycle
event.

The executor's own results (:class:`FindResult`, :class:`HistoryFindResult`) are
`m-snapshot-read`'s own carriers — the sealed graph and the private Source Hints
a materializer needs, and nothing about the execution that produced them — so
they are defined in
:mod:`~parallax.snapshot._read_result` and re-exported here beside the
executor that builds them, together with the developer-facing :class:`Snapshot`
surface they convert into and the pin helpers that carry a query's or a
milestone's as-of coordinates across that conversion.

A graph-form read also retains the write evidence its rows observed, onto the
values it publishes: this module drives :mod:`parallax.snapshot.handle.
_write_inputs`'s retention while each row is still live, and hands the resulting
Source Hints to whichever materializer runs. The dependency goes this way and
only this way — the write-input module names nothing here.

One executor, two materializers. The two :class:`ResultPublication` values are
PEERS over the same
:class:`~parallax.snapshot.materialize.GraphMerge`: which one runs is chosen
after execution has already finished and neither calls the other. Each publishes
one sealed graph at a time, so an eager find, a milestone-set find, and a
streamed read differ in WHICH graphs they hand over rather than in how a graph
becomes a result.
:func:`find_rows` is the values lane's own degenerate case — the transformed row
IS the representation, so it publishes rows directly and shares with :func:`find`
exactly the canonicalization, compilation, and Database Call bracket that decide
behavior.

All three classify stored state that contradicts the model rather than refusing
it: a Snapshot element is ``T | InvalidData[T]``, a row-form element is
``Mapping | InvalidData[Mapping]``, the default accessors here refuse an invalid
result after their own arity check, and :meth:`Snapshot.checked` reads the same
storage in band. Milestone-set staging and predicate-write staging still refuse
the whole read at the shared publication gate: a milestone read must decode a
temporal edge before it can partition, and a write has no in-band channel to
publish a verdict through.

What a find EXECUTES is `m-execution-lifecycle`'s vocabulary, not this module's:
each read runs inside the activity its composition root handed down, and each
call is bracketed into a Database Call child of it. A standalone read is handed
the Read its own root opened; a participating read is handed the Read its
transaction's attempt opened; an unobserved one is handed the shared inert
activity, and the same bracket then emits nothing. Nothing is retained — a
result carries no record of the calls that produced it — so an executor takes the
activity it brackets against and answers the result alone. :func:`execute_read`
is where the call bracket actually happens, and it is deliberately the package's
ONE of them: the materializing predicate write's resolving read
(`_predicate_writes`) is a read that reaches the database too, so it brackets
through this same function rather than through a second copy of the timing and
failed-call rules.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, cast

from parallax.core import deep_fetch, inheritance, opt_lock, read_lock
from parallax.core import predicate as predicate_algebra
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import LockMode
from parallax.core.entity import EntityGraphConstruction
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope, ReadActivity
from parallax.core.metamodel import AsOfAxisMetadata as AcceptedAsOfAxis
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.object_query import ObjectQueryNode, ValidatedObjectQuery
from parallax.core.sql_gen._compile import CompiledRead, MaterializedReadRow, compile_read
from parallax.core.temporal_read import Edge, Pin, milestone_edge, query_pin, scans_an_axis
from parallax.core.unit_work import Concurrency
from parallax.snapshot._read_result import (
    FindResult,
    HistoryFindResult,
    PublishedRow,
    RowsResult,
)
from parallax.snapshot.handle._errors import SnapshotMaterializationError
from parallax.snapshot.handle._materializer import materialize_graph
from parallax.snapshot.handle._write_inputs import (
    ObservationLedger,
    ReadObservations,
    ReadSources,
    retain_evidence,
)
from parallax.snapshot.materialize import (
    EMPTY_UNWIND,
    ClassifiedRoot,
    GraphMerge,
    InvalidData,
    InvalidDataError,
    RelationshipViewKey,
    SnapshotGraph,
    UnwindTree,
    classify_roots,
    hydrates,
    merge_graph_input,
    observable_columns,
    require_publishable,
    unwind_tree,
    wire_roots,
)
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder
from parallax.snapshot.materialize._views import (
    ROOT_LEVEL,
    ChildSlot,
    SourceLevel,
    ViewSchema,
)

__all__ = [
    "CheckedSnapshot",
    "FindResult",
    "HistoryFindResult",
    "NoResultFound",
    "PublishedRow",
    "ResultPublication",
    "RowsResult",
    "Snapshot",
    "StagedRows",
    "TooManyResultsFound",
    "entity_read_lock",
    "find",
    "find_history",
    "find_rows",
    "stage_publishable_rows",
    "typed_publication",
    "wire_publication",
]


class NoResultFound(RuntimeError):
    """``Snapshot.result()`` matched zero roots (spec §2/§3)."""


class TooManyResultsFound(RuntimeError):
    """``Snapshot.result()`` / ``.result_or_none()`` matched more than one root
    (spec §2/§3)."""


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


class Snapshot[T]:
    """The Python reification of a core Snapshot Graph (spec §3): ``db.find`` /
    ``tx.find``'s result. The complete surface: :meth:`result`,
    :meth:`result_or_none`, :meth:`results` (a FRESH ``list[T]`` per call),
    :meth:`checked`,
    :attr:`pin` (the lowered as-of coordinates — only genuinely PINNED axes; a
    scanned axis is absent), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, any lazy
    behavior, and every lifecycle accessor — whatever the read published, it
    published while it ran, and the result retains nothing of it.

    A root whose stored state contradicted the model is held as its
    :class:`~parallax.snapshot.materialize.InvalidData` record. The accessors
    here are the DEFAULT view: they check arity first and then refuse the read
    with :class:`~parallax.snapshot.materialize.InvalidDataError`, so a caller
    who never asks about stored-data validity can never silently receive a
    record in place of an Entity. :meth:`checked` is the same storage read in
    band instead. There is no ignore posture and no partition API: a finite
    union is partitioned with ordinary collection operations.
    """

    __slots__ = ("_invalid", "_pin", "_roots")

    _roots: tuple[T | InvalidData[T], ...]
    _invalid: tuple[InvalidData[object], ...]
    _pin: Pin

    def __init__(self, roots: tuple[T | InvalidData[T], ...], pin: Pin) -> None:
        self._roots = roots
        self._invalid = _invalid_records(roots)
        self._pin = pin

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
        copies no root, and forwards :attr:`pin` unchanged.
        """
        return CheckedSnapshot(self._roots, self._pin)

    @property
    def pin(self) -> Pin:
        """The query's OWN lowered as-of coordinates (spec §3): only
        genuinely pinned axes — a scanned (``history`` / ``as_of_range``) axis
        is absent, per the core rule that a scan is not a pin."""
        return self._pin

    def __repr__(self) -> str:
        return f"Snapshot(roots={len(self._roots)}, pin={self._pin!r})"

    def _require_valid(self) -> None:
        """Refuse once arity is settled, carrying exactly the roots in range.

        An accessor that already narrowed to one root has narrowed this tuple to
        that root's own record too, so the singular accessors report one and
        ``results()`` reports them all without either restating the rule.
        """
        if self._invalid:
            raise InvalidDataError(self._invalid)


class CheckedSnapshot[T]:
    """A :class:`Snapshot`'s roots as ``T | InvalidData[T]`` (spec §4).

    The whole eager checked surface: the same three arity accessors, the same
    :attr:`pin`, and nothing else. It shares the result
    storage rather than owning a second copy of it, does no I/O, and refuses
    nothing a default accessor would have accepted — an invalid root simply
    arrives as its record instead of raising.
    """

    __slots__ = ("_pin", "_roots")

    _roots: tuple[T | InvalidData[T], ...]
    _pin: Pin

    def __init__(self, roots: tuple[T | InvalidData[T], ...], pin: Pin) -> None:
        self._roots = roots
        self._pin = pin

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
        """The source Snapshot's own pin, forwarded unchanged."""
        return self._pin

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
    :meth:`~parallax.snapshot.handle.Database.find` — which has no participation
    to derive a strategy from and therefore never locks.
    """
    if preference is None:
        return None
    return read_lock.mode_for(
        opt_lock.effective_strategy(preference, opt_lock.view(meta).key(entity))
    )


def _new_roots() -> list[int]:
    return []


@dataclass(slots=True)
class _Milestone:
    """One milestone-set partition under construction: its own graph builder, the
    chronological rank of the row that opened it, and its imported roots."""

    builder: GraphBuilder
    rank: tuple[object, ...]
    roots: list[int] = field(default_factory=_new_roots)


def find(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DbPort,
    *,
    preference: Concurrency | None = None,
    ledger: ObservationLedger | None = None,
    calls: DatabaseCallScope = INERT,
) -> FindResult:
    """The one per-level deep-fetch / snapshot-materialization loop (m-deep-fetch
    "one query per non-empty relationship level"; m-snapshot-read "round trips").

    ``query`` is the read's canonical Object Query: one carrying Include Paths,
    or any other query planned with zero levels (root-only instance-form
    materialization — a plain snapshot read, or the source find behind a
    scenario `mutate` action). Canonicalizes the root query (`m-temporal-read` +
    `m-navigate`, composed here), compiles and executes it, then for each
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
    from that level's OWN `~parallax.core.sql_gen._compile.CompiledRead`, never re-derived
    here from the query a second time.

    Keys are gathered and fanned back by MEMBER identity
    (`FetchLevel.owner` / `related`), which is what lets each
    level's rows be converted one at a time: no column-to-member
    inversion happens here, and no row outlives its own level.

    Returns the whole sealed Snapshot graph — every projection, the root
    indexes in result order, and the query's own lowered pin — plus the
    Source Hint each observed projection's value will carry.

    ``model`` is the connected model as one value: the accepted Metamodel every
    level's own Entity resolves against, and the exact-model layout catalog
    every level's conversion reads its applicable member set from. The two
    travel together rather than as two arguments, so no read can be handed
    layouts derived from a model other than the one it resolves against, and one
    connection's reads share one catalog whatever they address. The graph
    builder holds neither: a row arrives at it already laid out, so a builder
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
    meta = model.meta
    authored = query.authored
    root_entity = query.root
    plan_ = deep_fetch.plan(query, meta)
    builder = GraphBuilder(ViewSchema(_slot_table(plan_)))
    observations = ReadObservations()

    root_compiled = compile_read(
        plan_.root,
        meta,
        port.dialect,
        result_form="instance",
        lock=entity_read_lock(meta, root_entity.identity, preference),
    )
    root_refs = _convert_level(builder, ROOT_LEVEL, model, port, root_compiled, calls, observations)

    level_refs: list[tuple[int, ...]] = []
    for index, level in enumerate(plan_.levels):
        parents = _guarded_parents(
            builder, level, _parent_refs(level.parent, root_refs, level_refs)
        )
        if level.is_back_reference:
            _attach_back_reference(builder, meta, level, parents)
            level_refs.append(())
            continue
        keys = _distinct_keys(builder, parents, _correlation_member(meta, level.owner.identity))
        if not keys:
            _attach_empty(builder, level, parents)
            level_refs.append(())
            continue
        child_query = level.query_for(keys)
        child_compiled = compile_read(
            child_query,
            meta,
            port.dialect,
            result_form="instance",
            lock=entity_read_lock(meta, child_query.target, preference),
        )
        child_refs = _convert_level(
            builder, index + 1, model, port, child_compiled, calls, observations
        )
        _attach_children(builder, meta, level, parents, child_refs)
        level_refs.append(child_refs)

    pin = query_pin(authored, declaring_metadata(meta, root_entity.identity))
    return FindResult(
        graph=builder.seal(root_refs, pin),
        includes=_include_tree(plan_.levels),
        sources=_retained(meta, authored, observations, ledger=ledger, pin=pin),
    )


def _retained(
    meta: Metamodel,
    query: ObjectQueryNode,
    observations: ReadObservations,
    *,
    ledger: ObservationLedger | None,
    pin: Pin,
) -> ReadSources:
    """What ``query``'s rows retain for the write side.

    Nothing at all for a MILESTONE-SET read, which is what
    :func:`find_history` retains for the same query: a scan stands at no single
    coordinate, so the pin every hint would carry names none of the milestones
    the rows are — and each of those rows is at a finite Transaction-Time edge
    and read-only through every keyed verb anyway. Retaining the query's own
    coordinate instead would make a streamed milestone writable where the whole
    result of the same query is not, which is a difference the delivery is not
    allowed to make.
    """
    if scans_an_axis(query):
        return MappingProxyType({})
    return retain_evidence(meta, observations, ledger=ledger, pin=pin)


@dataclass(frozen=True, slots=True)
class StagedRows:
    """One flat batch after SQL row materialization, before any lane has judged it.

    Staging carries what contradicted the model rather than deciding about it, so
    a batch reaching a lane through :func:`stage_rows` has passed no publication
    gate and one reaching it through :func:`stage_publishable_rows` has.

    ``rows`` and their aligned ``contexts`` remain available for the lane-specific
    work that follows. ``graph`` and ``roots`` retain the converted projections
    for the history lane, which repartitions clean rows by milestone without
    converting them a second time. ``merge`` is the merge over that same staging
    graph, which the lane either classifies or refuses; each row occupies the
    root position of the same ordinal, so a verdict lands on the row it judged.
    ``schema`` is the view schema this batch was laid out against — a flat batch
    plans no levels, so it carries no slot — and it travels with the batch so a
    lane building further graphs out of these rows shares the one schema of its
    execution rather than deriving a second.
    """

    rows: tuple[MaterializedReadRow, ...]
    contexts: tuple[LevelContext, ...]
    graph: SnapshotGraph
    roots: tuple[int, ...]
    merge: GraphMerge
    schema: ViewSchema


def stage_publishable_rows(
    model: CatalogedModel,
    compiled: CompiledRead,
    rows: Sequence[Mapping[str, object]],
    *,
    pin: Pin,
) -> StagedRows:
    """Materialize and validate one flat row batch before lane-specific use.

    The refusing peer of :func:`stage_rows`, for the two lanes with nowhere to
    publish a verdict: a milestone-set read must decode a temporal edge before it
    can partition its rows at all, and a predicate write has no in-band channel
    for one. Both apply the publication gate to the staging graph before deriving
    milestones, observations, or writes.
    """
    staged = stage_rows(model, compiled, rows, pin=pin)
    require_publishable(staged.merge)
    return staged


def stage_rows(
    model: CatalogedModel,
    compiled: CompiledRead,
    rows: Sequence[Mapping[str, object]],
    *,
    pin: Pin,
) -> StagedRows:
    """Materialize and merge one flat row batch before lane-specific use.

    Every caller forwards the compiled transform's findings, family-tag verdict,
    and classified-member provenance through :func:`convert_row`, so the staging
    graph carries whatever contradicted the model and each lane decides what to
    do with it.
    """
    layouts = model.layouts
    materialized = tuple(compiled.materialize_row(row) for row in rows)
    contexts = tuple(
        LevelContext(
            layouts.entity(row.resolved_entity),
            compiled.projected_documents,
            compiled.attribute_reads(row.resolved_entity),
        )
        for row in materialized
    )
    schema = ViewSchema.of()
    builder = GraphBuilder(schema)
    roots = tuple(
        convert_row(
            row.values,
            context,
            builder,
            source=ROOT_LEVEL,
            findings=row.findings,
            family_tag_unknown=row.family_tag_unknown,
            classified_members=row.classified_members,
        )
        for row, context in zip(materialized, contexts, strict=True)
    )
    graph = builder.seal(roots, pin)
    return StagedRows(materialized, contexts, graph, roots, merge_graph_input(graph), schema)


def find_rows(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DbPort,
    *,
    preference: Concurrency | None = None,
    read: ReadActivity = INERT,
) -> RowsResult:
    """The row-form read: one statement, its rows transformed, no graph.

    The transformed row is the returned representation, so the values lane builds
    no result graph. It does build a staging graph, which is what classification
    runs over: a row whose own stored state contradicted the model publishes its
    :class:`~parallax.snapshot.materialize.InvalidData` record in place of itself,
    carrying the row when the collapse produced one and nothing when no value
    could be produced without inventing it. What it shares with :func:`find` is
    everything that decides behavior: the same canonical root query
    (`deep_fetch.plan` injects the as-of predicate and canonicalizes navigation
    for both lanes), the same
    private :func:`~parallax.core.sql_gen._compile.compile_read` with the lane selected by
    ``result_form``, and the same Database Call bracket.

    A row-form read materializes no relationships, and the shared read gate
    (:func:`~parallax.snapshot.handle._preflight.preflight`) refuses a
    request that asks this lane for one — before any I/O, and before a
    participating read's force-flush — so the plan reaching here carries no
    level to drop.
    """
    meta = model.meta
    authored = query.authored
    root_entity = query.root
    plan_ = deep_fetch.plan(query, meta)
    compiled = compile_read(
        plan_.root,
        meta,
        port.dialect,
        result_form="row",
        lock=entity_read_lock(meta, root_entity.identity, preference),
    )
    rows = execute_read(
        port,
        compiled,
        read,
    )
    stage = stage_rows(
        model,
        compiled,
        rows,
        pin=query_pin(authored, declaring_metadata(meta, root_entity.identity)),
    )
    for item in stage.rows:
        if item.family_variant is not None:
            item.values["familyVariant"] = item.family_variant
    return RowsResult(rows=_published_rows(stage, meta))


def _published_rows(stage: StagedRows, meta: Metamodel) -> tuple[PublishedRow, ...]:
    """One published element per staged row, in result order.

    The staging graph gives each row the root position of its own ordinal, so a
    verdict and the row it judged are paired by position rather than by a second
    identity this lane would have to derive.
    """
    published: list[PublishedRow] = []
    for item, verdict in zip(stage.rows, classify_roots(stage.merge, meta).roots, strict=True):
        detached = MappingProxyType(dict(item.values))
        if isinstance(verdict, ClassifiedRoot):
            published.append(
                cast(
                    "InvalidData[Mapping[str, object]]",
                    verdict.published(None if verdict.node is None else detached),
                )
            )
            continue
        published.append(detached)
    return tuple(published)


def find_history(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DbPort,
    *,
    read: ReadActivity = INERT,
) -> HistoryFindResult:
    """The milestone-set snapshot read (m-snapshot-read "The whole-graph pin";
    m-case-format "Milestone-set graphs"): `history` / `asOfRange` return the
    full matching milestone SET in one statement, partitioned here by each
    row's own edge (`~parallax.core.temporal_read.milestone_edge`) into one
    root-only graph per milestone, each with its OWN merge scope — graph-local
    identity never promises reuse across milestones.

    The flat batch first passes the same staged publication gate a predicate
    write's resolving read does — the row-form lane classifies in band instead.
    Clean projections are then imported out of the SEALED staging graph into
    milestone-local builders, keeping each row's layout, member row, and issues
    by reference rather than decoding any of them a second time. The
    graphs come out in chronological edge order (Valid Time
    first, matching the corpus's own authored `then.graphs` order) rather than in
    the database's unspecified natural row order, and rows within one milestone
    keep that natural order.

    Every milestone graph is laid out against the staging batch's OWN view
    schema, so one milestone-set read has exactly one — a milestone-set query
    carries no includes, and a schema is a fact about the plan rather than about
    a partition of its rows.
    """
    meta = model.meta
    metadata = query.root
    plan_ = deep_fetch.plan(query, meta)
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
    compiled = compile_read(plan_.root, meta, port.dialect, result_form="instance")
    stage = stage_publishable_rows(
        model,
        compiled,
        execute_read(port, compiled, read),
        pin=Pin(),
    )

    milestones: dict[Edge, _Milestone] = {}
    for row, staged_ref in zip(stage.rows, stage.roots, strict=True):
        edge = milestone_edge(entity, row.values)
        milestone = milestones.get(edge)
        if milestone is None:
            milestone = _Milestone(GraphBuilder(stage.schema), _edge_sort_key(entity, row.values))
            milestones[edge] = milestone
        milestone.roots.append(
            milestone.builder.import_projection(ROOT_LEVEL, stage.graph, staged_ref)
        )
    graphs = tuple(
        milestone.builder.seal(tuple(milestone.roots), edge_pin(edge))
        for edge, milestone in sorted(milestones.items(), key=lambda entry: entry[1].rank)
    )
    return HistoryFindResult(graphs=graphs)


def _convert_level(
    builder: GraphBuilder,
    source: SourceLevel,
    model: CatalogedModel,
    port: DbPort,
    compiled: CompiledRead,
    calls: DatabaseCallScope,
    observations: ReadObservations,
) -> tuple[int, ...]:
    """Execute one level and convert each of its rows as that row materializes.

    ``source`` is where in the plan these rows land, which is what sizes each
    projection's view row: the levels attaching BELOW this one are what its rows
    can receive.

    The observation is taken from the SAME row the conversion reads, while that
    row is still live, and paired with the projection that row converted into —
    the pairing that lets the value built from that projection carry the evidence
    later. It is deliberately physical: a Predecessor Row is column-keyed by
    contract, so the write side is served by its own explicitly physical
    extraction rather than by a converted node carrying columns it has no other
    use for.

    Each row is observed under its OWN resolved concrete Entity — the identity
    the conversion already builds its `LevelContext` from — rather than under
    the level-wide position the query addressed. The root and every level run
    through here, so that one rule reaches an abstract-target root's concrete,
    a polymorphic level's concrete, and an included child alike.

    A NON-HYDRATING projection is observed by nothing: no conforming value exists
    for it, so it publishes no writable source and can carry no claim. A
    hydratable one is observed like any other — the collapse produced legal
    member values, and the row behind it is the ordinary stored row a later write
    settles against.
    """
    refs: list[int] = []
    for row in _execute_compiled(port, compiled, calls):
        context = LevelContext(
            model.layouts.entity(row.resolved_entity),
            compiled.projected_documents,
            compiled.attribute_reads(row.resolved_entity),
        )
        ref = convert_row(
            row.values,
            context,
            builder,
            source=source,
            findings=row.findings,
            family_tag_unknown=row.family_tag_unknown,
            classified_members=row.classified_members,
        )
        refs.append(ref)
        if not hydrates(builder.issues_of(ref)):
            continue
        observations.observe_row(
            ref,
            row.resolved_entity,
            observable_columns(row.values, context, classified_members=row.classified_members),
            row.document,
        )
    return tuple(refs)


def _include_tree(levels: Sequence[deep_fetch.FetchLevel]) -> UnwindTree:
    """The planned levels as the include tree a wire unwind descends.

    A level's own parent reference is what the tree is built from, so the tree
    and the fan-out below attach through one derivation of the view key rather
    than two spellings of it.
    """
    if not levels:
        return EMPTY_UNWIND
    return unwind_tree(
        [
            (
                _view_key(level),
                None if isinstance(level.parent, deep_fetch.RootRef) else level.parent.index,
            )
            for level in levels
        ]
    )


def _view_key(level: deep_fetch.FetchLevel) -> RelationshipViewKey:
    """The view ``level`` attaches under: its declared direction, plus the derived
    narrowed-view key when the level's attach key is not simply that direction's
    own name."""
    narrowed = None if level.attach_key == level.relationship.name else level.attach_key
    return RelationshipViewKey(level.relationship, narrowed)


def _slot_table(plan: deep_fetch.ObjectQueryPlan) -> tuple[tuple[ChildSlot, ...], ...]:
    """Which view slots each source level's parents can receive, indexed by
    source level: the root is 0 and plan level ``i`` is ``i + 1``.

    A level contributes one slot to whichever source level its own PARENT rows
    came from, carrying that level's path-root guard as the concretes it admits.
    The table is dense over every source level the plan can produce a projection
    at — a level attaching nothing still owns an empty entry, and a
    back-reference level, which converts no row of its own, is simply never
    named as a parent.

    This is where the plan vocabulary stops: what crosses into ``materialize`` is
    slots, so nothing there interprets a fetch plan.
    """
    table: list[list[ChildSlot]] = [[] for _ in range(len(plan.levels) + 1)]
    for level in plan.levels:
        parent = (
            ROOT_LEVEL if isinstance(level.parent, deep_fetch.RootRef) else level.parent.index + 1
        )
        table[parent].append(
            ChildSlot(
                _view_key(level),
                None if level.source_position is None else frozenset(level.source_position),
            )
        )
    return tuple(tuple(slots) for slots in table)


def _attach_children(
    builder: GraphBuilder,
    meta: Metamodel,
    level: deep_fetch.FetchLevel,
    parents: tuple[int, ...],
    children: tuple[int, ...],
) -> None:
    """Fan one level's converted children back to their parents in memory,
    preserving fetched order within each to-many bucket."""
    assert level.related is not None
    related = _correlation_member(meta, level.related.identity)
    owner = _correlation_member(meta, level.owner.identity)
    buckets: dict[object, list[int]] = {}
    for child in children:
        buckets.setdefault(builder.member_value(child, related), []).append(child)
    view = _view_key(level)
    for parent in parents:
        matched = buckets.get(builder.member_value(parent, owner), [])
        builder.write_view(
            parent,
            view,
            tuple(matched) if level.to_many else (matched[0] if matched else None),
        )


def _attach_empty(
    builder: GraphBuilder, level: deep_fetch.FetchLevel, parents: tuple[int, ...]
) -> None:
    """Attach the empty/null relationship result to every admitted parent.

    m-deep-fetch: an empty gathered parent-key set issues no child query at all,
    and every parent still gets a LOADED view — empty or null — rather than an
    unset one.
    """
    view = _view_key(level)
    empty: tuple[int, ...] | None = () if level.to_many else None
    for parent in parents:
        builder.write_view(parent, view, empty)


def _attach_back_reference(
    builder: GraphBuilder,
    meta: Metamodel,
    level: deep_fetch.FetchLevel,
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
    assert level.back_reference_family is not None
    view = _view_key(level)
    owner = _correlation_member(meta, level.owner.identity)
    for parent in parents:
        key = builder.member_value(parent, owner)
        if key is None or key is ABSENT:
            builder.write_view(parent, view, () if level.to_many else None)
            continue
        referenced = builder.resolve(level.back_reference_family, key)
        if referenced is None:  # pragma: no cover - guards a malformed plan
            raise ValueError(
                f"back-reference {level.attach_key!r}: no already-converted "
                f"{level.back_reference_family.canonical} node for key {key!r} (m-case-format "
                "'Back-reference cycles' guarantees the ancestor is already known)"
            )
        builder.write_view(parent, view, (referenced,) if level.to_many else referenced)


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
    port: DbPort, compiled: CompiledRead, calls: DatabaseCallScope
) -> Iterator[MaterializedReadRow]:
    """Execute one compiled read, materializing its rows through its OWN transform.

    Takes the whole `~parallax.core.sql_gen._compile.CompiledRead` rather than a statement
    plus a transform, so the two can only ever come from the same compile. That
    matters because `find` holds the root's and a child level's compiled reads in
    scope at the same time: crossing them is otherwise an ordinary-looking edit
    that raises deep inside the tag transform in one direction and, in the other,
    silently leaves the raw tag column standing where `familyVariant` should be.
    Keeping the pair bundled here is the caller-side half of `CompiledRead`'s own
    self-containment — it makes `find`'s "compile, execute, convert"
    structural rather than a convention every level has to remember.

    The statement runs inside its own Database Call bracket on the way in; the
    port's own whole-result `list[Row]` is what a row-returning execute answers
    by contract, and only the per-row materialization is lazy — so each
    MATERIALIZED row is reachable for exactly as long as its consumer takes to
    convert it, and the level never holds a second copy of its result set.
    """
    return map(compiled.materialize_row, execute_read(port, compiled, calls))


def execute_read(port: DbPort, compiled: CompiledRead, calls: DatabaseCallScope) -> list[Row]:
    """Run one compiled read's statement inside its own Database Call bracket.

    A FAILED call finishes too, and the failure then propagates untouched: a
    call that reached the port and came back is work the lifecycle owes an
    account of, whatever it came back with. The bracket owns that, so this
    function announces only the rows it alone holds. Every read this
    package issues — a find level, and the resolving read a materializing
    predicate write runs — goes through here, so the duration and failed-call
    semantics of a `read` call have exactly one definition.

    Takes the whole ``CompiledRead`` rather than a statement plus its document
    ordinals, for the same reason :func:`_execute_compiled` does: the statement,
    the ordinals it must be executed with, and the target Entity the activity
    reports all come from one compile or from none.
    """
    statement = compiled.statement
    document_reads = compiled.document_reads
    with calls.database_call(statement, "READ", compiled.target) as call:
        driver_sql = port.dialect.to_driver_sql(statement.sql)
        binds = list(statement.binds)
        rows = (
            port.execute(driver_sql, binds, document_reads)
            if document_reads
            else port.execute(driver_sql, binds)
        )
        call.read_completed(rows)
    return rows


def _parent_refs(
    parent: deep_fetch.ParentRef,
    root_refs: tuple[int, ...],
    level_refs: Sequence[tuple[int, ...]],
) -> tuple[int, ...]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_refs
    return level_refs[parent.index]


def _guarded_parents(
    builder: GraphBuilder, level: deep_fetch.FetchLevel, parents: tuple[int, ...]
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
    if level.source_position is None:
        return parents
    admitted = frozenset(level.source_position)
    return tuple(parent for parent in parents if builder.concrete_of(parent) in admitted)


def _distinct_keys(
    builder: GraphBuilder, parents: tuple[int, ...], member: AttributeIdentity
) -> list[predicate_algebra.Scalar]:
    """The distinct values of ``member`` across ``parents`` that name something,
    in first-encountered order (m-deep-fetch: the gathered set is unordered for
    grading purposes — an implementation MUST NOT sort at runtime to match a
    fixture — so encounter order is as good as any, and deterministic run to
    run).

    A member this level's parents did not carry and one stored null are distinct
    answers now and both drop out here: neither names a child row, so gathering
    either would widen the child query by a key nothing joins on.

    A gathered key is always a declared PRIMARY-KEY (or unique FK) attribute's
    own value — one of `m-predicate`'s neutral scalar types — even though a
    projection's values are typed as plain ``object``; the cast reflects that
    runtime invariant, not a widening of the membership node's own typed-literal
    contract.
    """
    gathered = (builder.member_value(parent, member) for parent in parents)
    values = dict.fromkeys(value for value in gathered if value is not None and value is not ABSENT)
    return cast("list[predicate_algebra.Scalar]", list(values))


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


def edge_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (spec §3: each
    milestone-set root is edge-pinned at its own milestone's from-instant).

    An axis the Entity does not declare answers absent on both sides, so the
    rendering needs no per-entity axis list of its own.
    """
    return Pin(tx_time=edge.tx_time_or_none, valid_time=edge.valid_time_or_none)


class RootsOf(Protocol):
    """One materializer's publication of the roots ONE sealed graph carries.

    The whole conversion, in one call: merge the graph, classify its roots, and
    publish the ones that hydrate. ``includes`` is the requested Include Path
    tree, which the Wire unwind bounds its walk by and the typed construction
    does not consult. ``ordinal_offset`` is where this graph's roots start in
    the ordered result being published, which is nonzero wherever one result
    spans several graphs. ``sources`` is the Source Hint the executor retained
    per PROJECTION, which each published node carries so a later keyed write
    reads its evidence off the value it was handed.
    """

    def __call__(
        self,
        graph: SnapshotGraph,
        includes: UnwindTree = EMPTY_UNWIND,
        /,
        *,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
    ) -> tuple[object, ...]: ...


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

    :attr:`roots_of` is deliberately per-GRAPH rather than per-result. An eager
    find publishes one graph, a milestone-set find concatenates one per
    milestone, and a streamed read publishes one root-scoped graph at a time —
    three orchestrations over one conversion, which is what keeps result scope a
    property of the graph a materializer is handed rather than a mode it is told
    about. :meth:`from_find` and :meth:`from_history` are the two eager
    compositions over it, so neither is an independent conversion that could
    drift from the streamed one.

    ``interface`` is the same choice named for the Read activity that
    orchestration opens: which materializer publishes IS which read interface
    ran, so the two are one value rather than two that could disagree.
    """

    interface: ReadInterface
    roots_of: RootsOf

    def from_find(self, result: FindResult) -> Snapshot[Any]:
        """``result``'s one graph as a Snapshot at that read's own pin."""
        return Snapshot(
            self.roots_of(result.graph, result.includes, sources=result.sources),
            result.graph.pin,
        )

    def from_history(self, result: HistoryFindResult) -> Snapshot[Any]:
        """Every milestone's roots as ONE ordered result.

        Each milestone graph is classified on its own — graph-local identity
        never promises reuse across milestones — while a classified root's
        ordinal names its position in the published result rather than in the
        graph it came from, so the offset advances by what each graph
        contributed. A milestone-set read carries no Include Path
        (`m-case-format`), so every graph publishes root-only, and the outer pin
        is empty because a scan is not a pin.
        """
        roots: list[object] = []
        for graph in result.graphs:
            roots.extend(self.roots_of(graph, ordinal_offset=len(roots)))
        return Snapshot(tuple(roots), Pin())


def typed_publication(meta: Metamodel, construction: EntityGraphConstruction) -> ResultPublication:
    """Publish through the typed materializer: frozen Entity instances."""

    def roots_of(
        graph: SnapshotGraph,
        includes: UnwindTree = EMPTY_UNWIND,
        /,
        *,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
    ) -> tuple[object, ...]:
        del includes  # the typed construction walks the merge, never the include tree
        return _materialize_result_graph(
            graph, meta, construction, ordinal_offset=ordinal_offset, sources=sources
        )

    return ResultPublication("TYPED", roots_of)


def wire_publication(meta: Metamodel) -> ResultPublication:
    """Publish through the wire materializer: frozen declared-name value trees."""

    def roots_of(
        graph: SnapshotGraph,
        includes: UnwindTree = EMPTY_UNWIND,
        /,
        *,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
    ) -> tuple[object, ...]:
        merge = merge_graph_input(graph)
        return wire_roots(
            merge,
            meta,
            includes,
            ordinal_offset=ordinal_offset,
            sources=merge.by_allocation(sources),
        )

    return ResultPublication("WIRE", roots_of)


def _materialize_result_graph(
    graph: SnapshotGraph,
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
        return materialize_graph(
            graph, meta, construction, ordinal_offset=ordinal_offset, sources=sources
        )
    except Exception as exc:
        raise SnapshotMaterializationError(
            "the read succeeded but its Entity graph could not be built "
            "(snapshot-materialization-failed)",
            cause=exc,
        ) from exc
