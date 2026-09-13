"""``parallax.snapshot.handle._read`` — the production find executor and the
Snapshot result surface (m-deep-fetch / m-snapshot-read).

The module DAG's snapshot-handle scope already reaches `materialize` + `m-sql`
+ `m-db-port`, so the edges the DAG declares nowhere (`m-deep-fetch` may not
import `m-sql`; `m-sql` may not import `m-navigate`/`m-temporal-read`) are
composed HERE, exactly like `_write_lowering` composes
the write-side `m-unit-work` x `m-sql` edge — one executor, production-owned:
`db.find` and `tx.find` both call the SAME :func:`find` / :func:`find_history`
and build the SAME
:class:`~parallax.snapshot.materialize.Page`, so the per-level
loop exists exactly once on the developer-facing path.

Included Page levels materialize and convert rows one at a time: a converted
node names its correlation members, so the next level gathers keys from the
converted parent rather than a retained row. A graph-form read's own ROOTS instead
stage as one tuple across :func:`read_roots` / :func:`build_page`, the one joint
a whole-result read has. Flat-row, history, and predicate-write lanes
instead stage one tuple of SQL-materialized rows into one Page, before any
consumer-specific derivation, so each lane classifies or refuses that one staging
Page rather than judging rows as it walks them. The port's raw
`list[Row]` remains one statement's own lifetime, and neither raw nor
SQL-materialized rows survive into a sealed Page, a Snapshot, or a lifecycle
event.

The executor's own results (:class:`FindResult`, :class:`HistoryFindResult`) are
`m-snapshot-read`'s own carriers — the sealed Page and the private Source Hints
a materializer needs, and nothing about the execution that produced them — so
they are defined in
:mod:`~parallax.snapshot._read_result` and re-exported here beside the
executor that builds them, together with the developer-facing :class:`Snapshot`
surface they convert into and the pin helpers that carry a query's or a
milestone's as-of coordinates across that conversion.

A graph-form read also retains the write evidence its Page-owned states observed, onto the
values it publishes: this module drives
:mod:`parallax.snapshot.handle._retention` while each row is still live, and
hands the resulting Source Hints to whichever materializer runs. The dependency
goes this way and only this way — the retention module names nothing here.

One executor, two materializers. The two :class:`ResultPublication` values are
PEERS over the same
:class:`~parallax.snapshot.materialize.RootView`: which one runs is chosen
after execution has already finished and neither calls the other. Each publishes
one Page at a time, so an eager find, a milestone-set find, and a
streamed read differ in WHICH Pages they hand over rather than in how a Page
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

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, cast

from parallax.core import continuation, deep_fetch, inheritance, opt_lock, read_lock
from parallax.core import predicate as predicate_algebra
from parallax.core.db_port import (
    DatabaseConnection,
    PipelineStatement,
    Row,
)
from parallax.core.dialect import LockMode
from parallax.core.entity import EntityGraphConstruction
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    DatabaseCallActivity,
    DatabaseCallScope,
    ReadActivity,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.object_query._validated import (
    ValidatedObjectQuery,
    ValidatedTemporalSelection,
)
from parallax.core.sql_gen._compile import (
    CompiledRead,
    MaterializedReadRow,
    compile_read,
    compile_template,
)
from parallax.core.temporal_read import (
    Edge,
    Pin,
    scans_validated_axis,
    validated_query_pin,
)
from parallax.core.unit_work import Concurrency, EntityStateRow
from parallax.snapshot._read_result import (
    FindResult,
    HistoryFindResult,
    PublishedRow,
    RowsResult,
)
from parallax.snapshot.handle._errors import SnapshotMaterializationError
from parallax.snapshot.handle._materialization import (
    INERT as MATERIALIZATION_INERT,
)
from parallax.snapshot.handle._materialization import (
    MaterializationObserver,
    Materializer,
)
from parallax.snapshot.handle._retention import (
    ObservationLedger,
    ObservedRows,
    ReadSources,
    deferred_evidence,
)
from parallax.snapshot.materialize import (
    EMPTY_UNWIND,
    ClassifiedRoot,
    InvalidData,
    InvalidDataError,
    Page,
    PageBuilder,
    RelationshipViewKey,
    RootView,
    UnwindTree,
    classify_roots,
    hydrates,
    page_edges,
    page_rows,
    require_publishable,
    unwind_tree,
    wire_roots,
)
from parallax.snapshot.materialize._page import ABSENT
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._typed import typed_root
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
    "RowPublication",
    "RowsResult",
    "Snapshot",
    "TooManyResultsFound",
    "entity_read_lock",
    "find",
    "find_history",
    "find_rows",
    "publishable_rows",
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
    scanned axis is absent), :attr:`edition` (the Model Edition the read was
    served under), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, any lazy
    behavior, and every lifecycle accessor — whatever the read published, it
    published while it ran, and the result retains nothing of it but the
    edition it was read under.

    A root whose stored state contradicted the model is held as its
    :class:`~parallax.snapshot.materialize.InvalidData` record. The accessors
    here are the DEFAULT view: they check arity first and then refuse the read
    with :class:`~parallax.snapshot.materialize.InvalidDataError`, so a caller
    who never asks about stored-data validity can never silently receive a
    record in place of an Entity. :meth:`checked` is the same storage read in
    band instead. There is no ignore posture and no partition API: a finite
    union is partitioned with ordinary collection operations.
    """

    __slots__ = ("_edition", "_invalid", "_pin", "_roots")

    _roots: tuple[T | InvalidData[T], ...]
    _invalid: tuple[InvalidData[object], ...]
    _pin: Pin
    _edition: str

    def __init__(self, roots: tuple[T | InvalidData[T], ...], pin: Pin, edition: str) -> None:
        self._roots = roots
        self._invalid = _invalid_records(roots)
        self._pin = pin
        self._edition = edition

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

    @property
    def pin(self) -> Pin:
        """The query's OWN lowered as-of coordinates (spec §3): only
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


class CheckedSnapshot[T]:
    """A :class:`Snapshot`'s roots as ``T | InvalidData[T]`` (spec §4).

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
        """The source Snapshot's own pin, forwarded unchanged."""
        return self._pin

    @property
    def edition(self) -> str:
        """The source Snapshot's own edition, forwarded unchanged."""
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
    :meth:`~parallax.snapshot.handle.Database.find` — which has no participation
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
) -> FindResult:
    """The whole-result read: every root ``query`` matches, and the graph below them.

    Defined as the composition of its two halves — :func:`read_roots` runs the
    root statement, :func:`build_graph` converts what came back and deep-fetches
    each planned level — so that reading the roots and building the graph they
    stand at the top of are separable without a second executor.

    ``query`` is the read's canonical Object Query: one carrying Include Paths,
    or any other query planned with zero levels (root-only instance-form
    materialization — a plain snapshot read, or the source find behind a
    scenario `mutate` action).

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
    return Materializer(observer).read_page(
        lambda cadence: build_page(
            read_roots(
                query,
                model,
                port,
                preference=preference,
                calls=calls,
                observer=cadence,
            ),
            model,
            port,
            preference=preference,
            ledger=ledger,
            calls=calls,
        )
    )


@dataclass(frozen=True, slots=True)
class RootRead:
    """One root statement already executed and materialized, together with what
    the graph built from its rows must be built under.

    The whole-result form of the pairing one statement's execution makes: the
    ``plan`` whose levels descend below these roots, the ``prepared`` read they
    materialized through and convert under, and the ``temporal`` selection their
    pin and their retained evidence are settled from all reach conversion as the
    one read that produced the rows, so no half of a find can be run against
    another half's query.
    """

    plan: deep_fetch.ObjectQueryPlan
    prepared: PreparedRead[MaterializedReadRow]
    rows: tuple[MaterializedReadRow, ...]
    temporal: tuple[ValidatedTemporalSelection, ...]
    observer: MaterializationObserver = MATERIALIZATION_INERT


def read_roots(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    preference: Concurrency | None = None,
    calls: DatabaseCallScope = INERT,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
) -> RootRead:
    """Plan ``query``, issue its ROOT statement, and materialize the rows it returned.

    Canonicalizes the root query (`m-temporal-read` + `m-navigate`, composed
    here), compiles it, binds it, and runs it. Nothing here converts, judges, or
    attaches anything, and no level's SQL is issued: what comes back is one
    statement's rows and the prepared read they belong to.

    The rows come back whole rather than as the lazy materialization a level
    converts out of: an iterator crossing this seam would have to be consumed by
    conversion, which is the one pass the seam exists to separate.
    """
    meta = model.meta
    plan_ = deep_fetch.plan(query, meta, projection=deep_fetch.ReadProjectionRequest("all", True))
    compiled = compile_read(
        plan_.root,
        meta,
        port.dialect,
        result_form="instance",
        lock=entity_read_lock(meta, query.root.identity, preference),
    )
    prepared = bind(model, compiled)
    observer.prepared(len(plan_.levels) + 1)
    observer.statement_rendered(ROOT_LEVEL)
    driver_rows = execute_read(port, compiled, calls)
    observer.statement_executed(ROOT_LEVEL, len(driver_rows))
    return RootRead(
        plan=plan_,
        prepared=prepared,
        rows=tuple(map(prepared.materialize, driver_rows)),
        temporal=query.temporal,
        observer=observer,
    )


def build_page(
    root_read: RootRead,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    preference: Concurrency | None = None,
    ledger: ObservationLedger | None = None,
    calls: DatabaseCallScope = INERT,
) -> FindResult:
    """The one per-level deep-fetch / snapshot-materialization loop (m-deep-fetch
    "one query per non-empty relationship level"; m-snapshot-read "round trips").

    Converts ``root_read``'s rows, then for each planned level: restricts the
    parent nodes to the ones a path-root guard admits
    (`FetchLevel.source_position`, m-deep-fetch — an excluded parent contributes no
    key and receives no attachment, so its view stays unset); gathers the distinct
    non-null parent keys; an empty gathered
    set attaches the empty/null relationship result and issues no child SQL; a
    back-reference level issues no SQL either (resolved through the Page's own
    identity map); otherwise compiles and executes ONE child query
    (carrying the level's declared relationship ordering), applies
    `familyVariant` materialization (`m-sql`) to its rows, and converts them.
    Every level is the same three steps — compile, execute, convert — with
    `familyVariant` materialization and each row's resolved concrete Entity coming
    from that level's OWN `~parallax.core.sql_gen._compile.CompiledRead`, never re-derived
    here from the query a second time. The root level's own three steps are
    :func:`read_roots`'s, which is why its compiled read arrives here rather than
    being compiled a second time.

    Keys are gathered and fanned back by MEMBER identity
    (`FetchLevel.owner` / `related`), which is what lets each
    level's rows be converted one at a time: no column-to-member
    inversion happens here, and no row outlives its own level.

    Returns the whole sealed Page — every occurrence, the root
    indexes in result order, and the query's own lowered pin — plus the
    Source Hint each observed projection's value will carry.

    ``model``, ``preference``, ``ledger``, and ``calls`` are :func:`find`'s own,
    and every level below the root derives its read lock, its retained evidence,
    and its Database Call bracket from them exactly as the root did.
    """
    meta = model.meta
    plan_ = root_read.plan
    builder = PageBuilder(ViewSchema(_slot_table(plan_)), root_read.observer)
    observations = ObservedRows()

    root_refs = _convert_rows(builder, ROOT_LEVEL, root_read.prepared, root_read.rows, observations)

    level_refs: list[tuple[int, ...]] = [()] * len(plan_.levels)
    completed: set[int] = set()
    while len(completed) < len(plan_.levels):
        ready = [
            index
            for index, level in enumerate(plan_.levels)
            if index not in completed
            and (isinstance(level.parent, deep_fetch.RootRef) or level.parent.index in completed)
        ]
        pending: list[tuple[int, deep_fetch.FetchLevel, tuple[int, ...], CompiledRead]] = []
        for index in ready:
            level = plan_.levels[index]
            parents = _guarded_parents(
                builder, level, _parent_refs(level.parent, root_refs, level_refs)
            )
            if level.is_back_reference:
                _attach_back_reference(builder, meta, level, parents)
                completed.add(index)
                continue
            keys = _gather_keys(builder, parents, _correlation_member(meta, level.owner.identity))
            if not keys:
                _attach_empty(builder, level, parents)
                completed.add(index)
                continue
            child_query = level.query_template()
            template = compile_template(
                child_query,
                meta,
                port.dialect,
                result_form="instance",
                lock=entity_read_lock(meta, child_query.target, preference),
            )
            root_read.observer.statement_rendered(index + 1)
            pending.append((index, level, parents, template.render(keys)))

        if len(pending) == 1:
            for index, level, parents, compiled in pending:
                child_refs = _convert_level(
                    builder,
                    index + 1,
                    model,
                    port,
                    compiled,
                    calls,
                    observations,
                    root_read.observer,
                )
                _attach_children(builder, meta, level, parents, child_refs)
                level_refs[index] = child_refs
                completed.add(index)
        elif pending:
            with ExitStack() as stack:
                call_contexts: list[DatabaseCallActivity] = []
                for _index, _level, _parents, compiled in pending:
                    context = calls.database_call(compiled.statement, "read", compiled.target)
                    call_contexts.append(context.__enter__())
                    stack.push(context.__exit__)
                batches = port.execute_pipeline(
                    tuple(
                        PipelineStatement(
                            port.dialect.to_driver_sql(compiled.statement.sql),
                            compiled.statement.binds,
                            compiled.document_reads,
                        )
                        for _index, _level, _parents, compiled in pending
                    )
                )
                for call, rows in zip(call_contexts, batches, strict=True):
                    call.read_completed(rows)
            for (index, level, parents, compiled), rows in zip(pending, batches, strict=True):
                root_read.observer.statement_executed(index + 1, len(rows))
                child_refs = _convert_level_rows(
                    builder, index + 1, model, compiled, rows, observations
                )
                _attach_children(builder, meta, level, parents, child_refs)
                level_refs[index] = child_refs
                completed.add(index)

    pin = validated_query_pin(root_read.temporal)
    page = builder.finish(root_refs, pin)
    return FindResult(
        page=page,
        includes=_include_tree(plan_.levels),
        sources=_retained(
            meta,
            root_read.temporal,
            observations,
            page=page,
            ledger=ledger,
            pin=pin,
        ),
    )


def _retained(
    meta: Metamodel,
    temporal: tuple[ValidatedTemporalSelection, ...],
    observations: ObservedRows,
    *,
    page: Page,
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
    if scans_validated_axis(temporal):
        return MappingProxyType({})
    rows = page_rows(page)
    state_rows: dict[object, EntityStateRow] = {}

    def admitted(node: int) -> EntityStateRow | None:
        key = rows.keys[node]
        state = None if key is None else rows.judged_states.get(key)
        if key is None or state is None or not hydrates(state.findings):
            return None
        held = state_rows.get(key)
        if held is None:
            held = EntityStateRow.over_state(rows.layouts[node], state, absent=ABSENT)
            state_rows[key] = held
        return held

    return deferred_evidence(
        meta,
        observations,
        admitted,
        lambda node: rows.layouts[node].concrete,
        ledger=ledger,
        pin=pin,
    )


@dataclass(frozen=True, slots=True)
class RowPublication:
    """One flat batch and the Page-owned Entity States that judged it.

    Staging carries what contradicted the model rather than deciding about it, so
    a batch reaching a lane through :func:`judge_rows` has passed no publication
    gate and one reaching it through :func:`publishable_rows` has.

    ``rows`` retains statement metadata such as history coordinates. ``page`` and
    ``roots`` retain the converted occurrences, while ``root`` exposes their
    judged Entity States to history, row publication, and predicate-write
    staging without another payload decode or reconstructed member dictionary.
    """

    rows: tuple[MaterializedReadRow, ...]
    page: Page
    roots: tuple[int, ...]
    root: RootView


def publishable_rows(
    model: CatalogedModel,
    compiled: CompiledRead,
    rows: Sequence[Row],
    *,
    pin: Pin,
) -> RowPublication:
    """Materialize and validate one flat row batch before lane-specific use.

    The refusing peer of :func:`judge_rows`, for lanes with nowhere to
    publish a verdict: a milestone-set read must decode a temporal edge before it
    can partition its rows at all, and a predicate write has no in-band channel
    for one. Both apply the publication gate to the Page before deriving
    milestones, observations, or writes.
    """
    staged = Materializer().read_page(
        lambda observer: judge_rows(model, compiled, rows, pin=pin, observer=observer)
    )
    require_publishable(staged.root)
    return staged


def judge_rows(
    model: CatalogedModel,
    compiled: CompiledRead,
    rows: Sequence[Row],
    *,
    pin: Pin,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
) -> RowPublication:
    """Materialize one flat row batch into a Page before lane-specific use.

    The prepared read carries the compiled transform's findings, family-tag
    verdict, and classified-member provenance into conversion, so the Page
    carries whatever contradicted the model and each lane decides what to
    do with it.
    """
    prepared = bind(model, compiled)
    materialized = tuple(map(prepared.materialize, rows))
    schema = ViewSchema.of()
    builder = PageBuilder(schema, observer)
    roots = tuple(prepared.convert(row, builder, source=ROOT_LEVEL) for row in materialized)
    page = builder.finish(roots, pin)
    return RowPublication(materialized, page, roots, RootView(page))


def find_rows(
    query: ValidatedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    edition: str,
    preference: Concurrency | None = None,
    read: ReadActivity = INERT,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
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
    root_entity = query.root
    plan_ = deep_fetch.plan(query, meta, projection=deep_fetch.ReadProjectionRequest("none", False))
    compiled = compile_read(
        plan_.root,
        meta,
        port.dialect,
        result_form="row",
        lock=entity_read_lock(meta, root_entity.identity, preference),
    )

    def read_page(cadence: MaterializationObserver) -> RowPublication:
        cadence.prepared(1)
        cadence.statement_rendered(ROOT_LEVEL)
        driver_rows = execute_read(port, compiled, read)
        cadence.statement_executed(ROOT_LEVEL, len(driver_rows))
        return judge_rows(
            model, compiled, driver_rows, pin=validated_query_pin(query.temporal), observer=cadence
        )

    stage = Materializer(observer).read_page(read_page)
    for item in stage.rows:
        if item.family_variant is not None:
            item.values["familyVariant"] = item.family_variant
    return RowsResult(rows=_published_rows(stage, meta), edition=edition)


def _published_rows(stage: RowPublication, meta: Metamodel) -> tuple[PublishedRow, ...]:
    """One published element per staged row, in result order.

    The Page gives each row the root position of its own ordinal, so a
    verdict and the row it judged are paired by position rather than by a second
    identity this lane would have to derive.
    """
    published: list[PublishedRow] = []
    for item, verdict in zip(stage.rows, classify_roots(stage.root, meta).roots, strict=True):
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
    port: DatabaseConnection,
    *,
    read: ReadActivity = INERT,
    observer: MaterializationObserver = MATERIALIZATION_INERT,
) -> HistoryFindResult:
    """The milestone-set snapshot read (m-snapshot-read "The whole-graph pin";
    m-case-format "Milestone-set graphs").

    ``history`` and ``asOfRange`` return the full matching milestone set in one
    statement and one Page. Continuation order is authored onto the canonical
    graph-form read before SQL compilation, so the Page's flat root sequence is
    already logical key followed by canonical axis starts. Each root's edge is
    retained as its publication pin; Page identity remains shared while every
    published result root receives a root-local object graph.

    The flat Page first passes the same publication gate as a predicate-write
    resolving read. A milestone-set query carries no includes, so the one Page
    schema is root-only.
    """
    meta = model.meta
    metadata = query.root
    ordered = continuation.ordered(query, meta)
    plan_ = deep_fetch.plan(ordered, meta, projection=deep_fetch.ReadProjectionRequest("all", True))
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

    def read_page(cadence: MaterializationObserver) -> RowPublication:
        cadence.prepared(1)
        cadence.statement_rendered(ROOT_LEVEL)
        driver_rows = execute_read(port, compiled, read)
        cadence.statement_executed(ROOT_LEVEL, len(driver_rows))
        return judge_rows(model, compiled, driver_rows, pin=Pin(), observer=cadence)

    stage = Materializer(observer).read_page(read_page)

    return HistoryFindResult(page=stage.page, milestones=entity)


def _convert_level(
    builder: PageBuilder,
    source: SourceLevel,
    model: CatalogedModel,
    port: DatabaseConnection,
    compiled: CompiledRead,
    calls: DatabaseCallScope,
    observations: ObservedRows,
    observer: MaterializationObserver,
) -> tuple[int, ...]:
    """Bind one level's compiled read, execute it, and convert each of its rows
    as that row materializes.

    The read is prepared and executed in the same breath, which is what keeps a
    `find` — holding the root's compiled read and this level's at once — from
    materializing one statement's rows through the other's transform: crossing
    them raises deep inside a tag stage in one direction and, in the other,
    silently leaves the raw tag column standing where `familyVariant` should be.

    A level converts straight out of the lazy materialization rather than out of
    a retained tuple the way a root read does, so it holds one materialized row
    at a time: the port's own whole-result `list[Row]` is what a row-returning
    execute answers by contract, and only the per-row materialization is lazy.
    """
    rows = execute_read(port, compiled, calls)
    observer.statement_executed(source, len(rows))
    return _convert_level_rows(builder, source, model, compiled, rows, observations)


def _convert_level_rows(
    builder: PageBuilder,
    source: SourceLevel,
    model: CatalogedModel,
    compiled: CompiledRead,
    rows: Sequence[Row],
    observations: ObservedRows,
) -> tuple[int, ...]:
    prepared = bind(model, compiled)
    return _convert_rows(builder, source, prepared, map(prepared.materialize, rows), observations)


def _convert_rows(
    builder: PageBuilder,
    source: SourceLevel,
    prepared: PreparedRead[MaterializedReadRow],
    rows: Iterable[MaterializedReadRow],
    observations: ObservedRows,
) -> tuple[int, ...]:
    """Convert ``rows`` into ``builder``, observing each one while it is still live.

    ``prepared`` is the read those rows materialized through, which is also what
    each of them converts and is observed under: the layout, projected
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
        ref = prepared.convert(row, builder, source=source)
        refs.append(ref)
        observations.observe_occurrence(
            ref,
            row.resolved_entity,
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
    builder: PageBuilder,
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
    builder: PageBuilder, level: deep_fetch.FetchLevel, parents: tuple[int, ...]
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
    builder: PageBuilder,
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


def _parent_refs(
    parent: deep_fetch.ParentRef,
    root_refs: tuple[int, ...],
    level_refs: Sequence[tuple[int, ...]],
) -> tuple[int, ...]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_refs
    return level_refs[parent.index]


def _guarded_parents(
    builder: PageBuilder, level: deep_fetch.FetchLevel, parents: tuple[int, ...]
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


def _gather_keys(
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


def edge_pin(edge: Edge) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (spec §3: each
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
    spans several graphs. ``sources`` is the Source Hint the executor retained
    per PROJECTION, which each published node carries so a later keyed write
    reads its evidence off the value it was handed.
    """

    def __call__(
        self,
        page: Page,
        includes: UnwindTree = EMPTY_UNWIND,
        /,
        *,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
        milestones: EntityMetadata | None = None,
    ) -> Iterator[object]: ...


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

    :attr:`roots_of` is deliberately per-Page rather than per-result. An eager
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

    def from_find(self, result: FindResult) -> Snapshot[Any]:
        """``result``'s Page as a Snapshot at that read's own pin."""
        return Snapshot(
            tuple(self.roots_of(result.page, result.includes, sources=result.sources)),
            result.page.pin,
            self.edition,
        )

    def from_history(self, result: HistoryFindResult) -> Snapshot[Any]:
        """Every milestone's roots as ONE ordered result.

        Each milestone root is classified through its own Root View while a
        classified root's ordinal names its position in the flat published
        result. A milestone-set read carries no Include Path (`m-case-format`),
        so every root publishes root-only, and the outer pin
        is empty because a scan is not a pin.
        """
        return Snapshot(
            tuple(self.roots_of(result.page, milestones=result.milestones)), Pin(), self.edition
        )


def typed_publication(
    meta: Metamodel, construction: EntityGraphConstruction, edition: str
) -> ResultPublication:
    """Publish through the typed materializer: frozen Entity instances."""

    def roots_of(
        page: Page,
        includes: UnwindTree = EMPTY_UNWIND,
        /,
        *,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
        milestones: EntityMetadata | None = None,
    ) -> Iterator[object]:
        del includes

        def publish() -> Iterator[object]:
            for position, edge in enumerate(page_edges(page, milestones)):
                root = RootView(page, position, pin=None if edge is None else edge_pin(edge))
                published = tuple(
                    _materialize_result_page(
                        root,
                        meta,
                        construction,
                        ordinal_offset=ordinal_offset + position,
                        sources=sources,
                    )
                )
                del root
                yield from published

        cadence = cast(
            "MaterializationObserver",
            page.observer if page.observer is not None else MATERIALIZATION_INERT,
        )
        yield from Materializer(cadence).roots(page, publish, ordinal_offset=ordinal_offset)

    return ResultPublication("typed", roots_of, edition)


def wire_publication(meta: Metamodel, edition: str) -> ResultPublication:
    """Publish through the wire materializer: frozen declared-name value trees."""

    def roots_of(
        page: Page,
        includes: UnwindTree = EMPTY_UNWIND,
        /,
        *,
        ordinal_offset: int = 0,
        sources: ReadSources = MappingProxyType({}),
        milestones: EntityMetadata | None = None,
    ) -> Iterator[object]:
        def publish() -> Iterator[object]:
            for position, edge in enumerate(page_edges(page, milestones)):
                root = RootView(page, position, pin=None if edge is None else edge_pin(edge))
                published = tuple(
                    wire_roots(
                        root,
                        meta,
                        includes,
                        ordinal_offset=ordinal_offset + position,
                        sources=root.by_allocation(sources),
                    )
                )
                del root
                yield from published

        cadence = cast(
            "MaterializationObserver",
            page.observer if page.observer is not None else MATERIALIZATION_INERT,
        )
        yield from Materializer(cadence).roots(page, publish, ordinal_offset=ordinal_offset)

    return ResultPublication("wire", roots_of, edition)


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
        return typed_root(root, meta, construction, ordinal_offset=ordinal_offset, sources=sources)
    except Exception as exc:
        raise SnapshotMaterializationError(
            "the read succeeded but its Entity graph could not be built "
            "(snapshot-materialization-failed)",
            cause=exc,
        ) from exc
