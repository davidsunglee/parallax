from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final, Literal, NamedTuple, Protocol, assert_never

from parallax.core.internal import concurrency, continuation, inheritance, read_planning
from parallax.core.internal.concurrency import ConcurrencyFacet, ConcurrencyPreference
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    TemporalDimension,
)
from parallax.core.internal.object_query._resolved import (
    ResolvedAsOfSelection,
    ResolvedHistorySelection,
    ResolvedLatestSelection,
    ResolvedObjectQuery,
    ResolvedRangeSelection,
    ResolvedTemporalSelection,
)
from parallax.core.internal.predicate._execution_values import ExecutionValueSources
from parallax.core.internal.predicate._resolved import (
    DeferredKeySet,
    RelatedObject,
    ResolvedAnd,
    ResolvedCollection,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedStringMatch,
    ScalarCollection,
    SubjectPosition,
)
from parallax.core.internal.read_delivery._fetch import correlation_table, slot_table
from parallax.core.internal.read_delivery._page import (
    ROOT_LEVEL,
    PageBuilder,
    SourceLevel,
    ViewSchema,
)
from parallax.core.internal.read_delivery._paging import PagingParameters
from parallax.core.internal.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.internal.read_planning._include_tree import build_include_tree
from parallax.core.internal.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_template,
)
from parallax.core.internal.sql_gen._inheritance import EMPTY_READ, EmptyRead
from parallax.core.internal.sql_gen._predicate import affix_needs_escape
from parallax.core.internal.sql_gen._seek import continuation_pattern
from parallax.core.internal.temporal_read import (
    Pin,
    TemporalShape,
    ranked_axes,
    resolved_query_pin,
    scans_resolved_axis,
    temporal_facet_of,
)

__all__ = [
    "DEFAULT_READ_PLAN_CACHE_CAPACITY",
    "EMPTY_READ",
    "UNCACHED_READ_PLANNER",
    "EmptyRead",
    "ReadKind",
    "ReadPlan",
    "ReadPlanCache",
    "ReadPlanner",
    "ReadPurpose",
    "check_read_plan_cache_capacity",
    "repeating_levels",
]

DEFAULT_READ_PLAN_CACHE_CAPACITY: Final = 128
"""The bounded plan reuse a root composed without an explicit capacity gets."""


def check_read_plan_cache_capacity(capacity: int) -> int:
    """Return a valid public cache capacity or raise before composition."""
    if type(capacity) is not int or capacity < 0:
        raise ValueError("read_plan_cache_capacity must be a nonnegative built-in int")
    return capacity


@dataclass(frozen=True, slots=True)
class _ReadPlanCacheStatistics:
    capacity: int
    size: int
    hits: int
    misses: int
    evictions: int


type ReadKind = Literal["single_instant", "milestone_set"]
type ReadPurpose = Literal["publication", "write_support"]

type _FetchWork = CompiledTemplate | EmptyRead | None


@dataclass(frozen=True, slots=True)
class _ReadPreparation:
    query_plan: read_planning.ObjectQueryPlan
    root: CompiledRead | EmptyRead
    root_rows: ReadRowConverter | None
    schema: ViewSchema | None
    repeating: frozenset[SourceLevel]
    correlations: tuple[tuple[AttributeIdentity, ...], ...]
    fetches: tuple[_FetchWork, ...]
    fetch_rows: tuple[ReadRowConverter | None, ...]


class _DeferredRead:
    __slots__ = ("_build", "_lock", "_prepared")

    def __init__(self, build: Callable[[], _ReadPreparation]) -> None:
        self._build: Callable[[], _ReadPreparation] | None = build
        self._lock = threading.Lock()
        self._prepared: _ReadPreparation | None = None

    def get(self) -> _ReadPreparation:
        with self._lock:
            if self._prepared is None:
                assert self._build is not None
                self._prepared = self._build()
                self._build = None
            return self._prepared


@dataclass(frozen=True, slots=True)
class ReadPlan:
    model: CatalogedModel
    kind: ReadKind
    purpose: ReadPurpose
    milestones: TemporalShape | None
    query: ResolvedObjectQuery | read_planning.PlannedEntityQuery
    pin: Pin
    _prepared: _ReadPreparation | _DeferredRead
    continuation: continuation.ContinuationPlan | None = None

    @property
    def collects_evidence(self) -> bool:
        return self.kind == "single_instant" and self.purpose == "publication"

    def _preparation(self) -> _ReadPreparation:
        prepared = self._prepared
        return prepared.get() if isinstance(prepared, _DeferredRead) else prepared

    @property
    def fetch_count(self) -> int:
        return len(self._preparation().query_plan.fetch_steps)

    def root_read(self) -> tuple[CompiledRead, ReadRowConverter] | EmptyRead:
        prepared = self._preparation()
        if isinstance(prepared.root, EmptyRead):
            return prepared.root
        assert prepared.root_rows is not None
        return prepared.root, prepared.root_rows

    def page_builder(self, observer: object | None) -> PageBuilder:
        prepared = self._preparation()
        schema = prepared.schema
        if schema is None:
            schema = ViewSchema.of(repeating_levels=prepared.repeating)
        return PageBuilder(schema, observer)

    def ready_fetches(self, completed: set[int]) -> tuple[int, ...]:
        return tuple(
            index
            for index, step in enumerate(self._preparation().query_plan.fetch_steps)
            if index not in completed
            and (isinstance(step.parent, read_planning.RootRef) or step.parent.index in completed)
        )

    def fetch_step(self, index: int) -> read_planning.FetchStep:
        return self._preparation().query_plan.fetch_steps[index]

    def prepared_fetch(
        self, index: int
    ) -> tuple[CompiledTemplate, ReadRowConverter] | EmptyRead | None:
        prepared = self._preparation()
        fetch = prepared.fetches[index]
        if fetch is None or isinstance(fetch, EmptyRead):
            return fetch
        rows = prepared.fetch_rows[index]
        assert rows is not None
        return fetch, rows

    def include_tree(self) -> read_planning.IncludeTree:
        return self._preparation().query_plan.includes


class ReadPlanner(Protocol):
    def plan(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: ResolvedObjectQuery,
        preference: ConcurrencyPreference | None,
        paging: PagingParameters | None = None,
        policy: ReadPlan | None = None,
    ) -> ReadPlan: ...

    def plan_acquisition(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: read_planning.PlannedEntityQuery,
        preference: ConcurrencyPreference | None,
        coverage_shared_lock: bool | None = None,
    ) -> ReadPlan: ...


@dataclass(frozen=True, slots=True)
class _CachedDelivery:
    prepared: _ReadPreparation
    root_template: CompiledTemplate | None
    model: CatalogedModel
    kind: ReadKind
    purpose: ReadPurpose
    milestones: TemporalShape | None

    def render(self, query: ResolvedObjectQuery | read_planning.PlannedEntityQuery) -> ReadPlan:
        if (
            self.kind == "milestone_set"
            and self.purpose == "publication"
            and isinstance(query, ResolvedObjectQuery)
            and query.paging is None
        ):
            query = replace(query, order_by=self.prepared.query_plan.root.order_by)
        template = self.root_template
        prepared = (
            self.prepared
            if template is None
            else replace(self.prepared, root=template.render(query=query))
        )
        pin = (
            resolved_query_pin(query.temporal)
            if isinstance(query, ResolvedObjectQuery) and self.kind == "single_instant"
            else Pin()
        )
        return ReadPlan(self.model, self.kind, self.purpose, self.milestones, query, pin, prepared)


def _milestones(model: CatalogedModel, entity: EntityIdentity) -> TemporalShape:
    shape = temporal_facet_of(model.meta).shape(entity)
    if shape is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.canonical}: no Temporal Facet shape")
    return shape


@dataclass(frozen=True, slots=True)
class _Identity:
    value: object

    def __hash__(self) -> int:
        return id(self.value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Identity) and self.value is other.value


class _QueryKey:
    """A resolved query's SQL-relevant structure, hashed once."""

    __slots__ = ("_hash", "value")

    def __init__(self, value: tuple[object, ...]) -> None:
        self.value = value
        self._hash = hash(value)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _QueryKey) and (
            self is other or (self._hash == other._hash and self.value == other.value)
        )


class _ReadPlanKey(NamedTuple):
    edition: str
    model: _Identity
    dialect: _Identity
    query: _QueryKey
    preference: ConcurrencyPreference | None
    delivery: object
    purpose: ReadPurpose = "publication"
    acquisition_lock: bool | None = None

    def same_family(self, other: _ReadPlanKey) -> bool:
        return (
            self.edition == other.edition
            and self.model == other.model
            and self.dialect == other.dialect
            and self.preference == other.preference
            and self.query == other.query
            and self.purpose == other.purpose
            and self.acquisition_lock == other.acquisition_lock
        )


@dataclass(slots=True)
class _Pending:
    ready: threading.Event
    prepared: _CachedDelivery | None = None
    error: BaseException | None = None


def _read_plan_key(
    *,
    edition: str,
    model: CatalogedModel,
    dialect: Dialect,
    query: ResolvedObjectQuery | read_planning.PlannedEntityQuery,
    preference: ConcurrencyPreference | None,
    purpose: ReadPurpose = "publication",
    coverage_shared_lock: bool | None = None,
) -> _ReadPlanKey:
    paging = query.paging
    delivery: tuple[object, ...]
    if paging is None:
        delivery = (query.limit, None)
    else:
        delivery = (
            None,
            "first"
            if paging.seek is None
            else ("after", continuation_pattern(paging.seek.coordinate)),
        )
    return _ReadPlanKey(
        edition,
        _Identity(model),
        _Identity(dialect),
        _QueryKey(
            _query_key(query)
            if isinstance(query, ResolvedObjectQuery)
            else (
                query.target,
                _predicate_key(query.predicate.predicate),
                query.narrow_to,
                tuple(member.identity for member in query.projection.value_objects),
                query.projection.observe_structured_document,
            )
        ),
        preference,
        delivery,
        purpose,
        coverage_shared_lock,
    )


def _query_key(query: ResolvedObjectQuery) -> tuple[object, ...]:
    """Everything about ``query`` its compiled plan depends on.

    The predicate's operands, a finite temporal selection's bounds, a page's
    cap, and its seek coordinate are execution values its templates render, so
    only their structure is part of the key. Members and positions are named by
    identity: the model the key also names fixes the metadata behind each.
    """
    return (
        query.root.identity,
        _predicate_key(query.predicate),
        tuple(_temporal_key(selection) for selection in query.temporal),
        tuple((term.member.identity, term.direction, term.nulls) for term in query.order_by),
        tuple(
            (
                path.source_position,
                tuple(
                    (segment.relationship, segment.position, segment.authored_narrow)
                    for segment in path.segments
                ),
            )
            for path in query.includes
        ),
        None if query.narrow_to is None else tuple(item.identity for item in query.narrow_to),
        query.limit if query.paging is None else None,
    )


def _operand_key(value: object) -> object:
    """``value``'s exact type, and a Decimal's exponent, but not the value:
    operands that share them render into one template."""
    if isinstance(value, Decimal):
        return Decimal, value.as_tuple().exponent
    return type(value)


def _predicate_key(predicate: ResolvedPredicate) -> object:  # noqa: C901 - exhaustive dispatcher
    match predicate:
        case ResolvedConstant(truth=truth):
            return ResolvedConstant, truth
        case ResolvedComparison(
            op=op, member=member, value=value, framework=framework, position=position
        ):
            return (
                ResolvedComparison,
                op,
                member.identity,
                _operand_key(value),
                framework,
                _position_key(position),
            )
        case ResolvedRange(member=member, lower=lower, upper=upper, position=position):
            return (
                ResolvedRange,
                member.identity,
                _operand_key(lower),
                _operand_key(upper),
                _position_key(position),
            )
        case ResolvedMembership(op=op, member=member, values=values, position=position):
            # Emptiness and the elements' distinct structures, not their number:
            # a nonempty list renders into its template whatever its length.
            operands = (
                values
                if isinstance(values, DeferredKeySet)
                else frozenset(_operand_key(value) for value in values)
            )
            return ResolvedMembership, op, member.identity, operands, _position_key(position)
        case ResolvedStringMatch(
            op=op,
            member=member,
            pattern=pattern,
            case_insensitive=case_insensitive,
            position=position,
        ):
            return (
                ResolvedStringMatch,
                op,
                member.identity,
                op not in ("like", "notLike") and affix_needs_escape(pattern),
                case_insensitive,
                _position_key(position),
            )
        case ResolvedNullCheck(op=op, member=member, position=position):
            return ResolvedNullCheck, op, member.identity, _position_key(position)
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            return type(predicate), tuple(_predicate_key(operand) for operand in operands)
        case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
            return type(predicate), _predicate_key(operand)
        case ResolvedNarrow(selection=selection, operand=operand, target=target):
            return (
                ResolvedNarrow,
                selection,
                None if operand is None else _predicate_key(operand),
                _position_key(target),
            )
        case ResolvedQuantifier(kind=kind, collection=collection, where=where, position=position):
            return (
                ResolvedQuantifier,
                kind,
                _collection_key(collection),
                None if where is None else _predicate_key(where),
                _position_key(position),
            )
        case ResolvedPresence(negated=negated, target=target, position=position, where=where):
            return (
                ResolvedPresence,
                negated,
                target.identity,
                _position_key(position),
                None if where is None else _predicate_key(where),
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(predicate)


def _position_key(position: SubjectPosition) -> object:
    """``position`` as the relationship hops that reach it from the current
    object; the current object and a bound scalar element are their own keys."""
    if isinstance(position, RelatedObject):
        return position.relationship.identity, _position_key(position.source)
    return type(position)


def _collection_key(collection: ResolvedCollection) -> object:
    if isinstance(collection, ScalarCollection):
        return ScalarCollection, collection.member.identity
    return type(collection), collection.identity


def _temporal_key(selection: ResolvedTemporalSelection) -> object:
    match selection:
        case ResolvedLatestSelection(axis=axis) | ResolvedHistorySelection(axis=axis):
            return type(selection), axis.dimension
        case ResolvedAsOfSelection(axis=axis, coordinate=coordinate):
            return ResolvedAsOfSelection, axis.dimension, _operand_key(coordinate)
        case ResolvedRangeSelection(axis=axis, start=start, end=end):
            return ResolvedRangeSelection, axis.dimension, _operand_key(start), _operand_key(end)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(selection)


def repeating_levels(
    model: CatalogedModel,
    resolvable: Sequence[Sequence[EntityIdentity]],
    referenced: Iterable[EntityIdentity],
) -> frozenset[SourceLevel]:
    """The source levels of a read that may record one row key more than once on
    its Page, from the Entities each level's statement can resolve a row to
    (none for a level that executes nothing) and the families ``referenced`` by
    a back-reference.

    A row key recurs across levels when a second level fetches the same family
    or a back-reference names it. Within-statement repetition comes from the
    compiled result contract.
    """
    facet = inheritance.inheritance_facet_of(model.meta)
    families_by_level: list[frozenset[EntityIdentity]] = []
    repeating: set[SourceLevel] = set()
    for entities in resolvable:
        views = tuple(_entity_view(facet, entity) for entity in entities)
        families_by_level.append(frozenset(view.root for view in views))
    shared = set(referenced)
    seen: set[EntityIdentity] = set()
    for families in families_by_level:
        shared.update(families & seen)
        seen.update(families)
    repeating.update(level for level, families in enumerate(families_by_level) if families & shared)
    return frozenset(repeating)


def _entity_view(
    facet: inheritance.InheritanceFacet, entity: EntityIdentity
) -> inheritance.InheritanceEntityView:
    view = facet.entity(entity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.canonical}: no inheritance view")
    return view


def _plan_uncached(
    *,
    model: CatalogedModel,
    dialect: Dialect,
    query: ResolvedObjectQuery | read_planning.PlannedEntityQuery,
    preference: ConcurrencyPreference | None,
    reusable: _ReadPreparation | None = None,
    templated: bool = False,
    kind: ReadKind | None = None,
    milestones: TemporalShape | None = None,
    purpose: ReadPurpose = "publication",
    coverage_shared_lock: bool | None = None,
) -> _CachedDelivery:
    """Plan ``query``; a ``templated`` plan's root is the unrendered read of a
    template every cached delivery renders."""
    if kind is None:
        assert isinstance(query, ResolvedObjectQuery)
        kind = "milestone_set" if scans_resolved_axis(query.temporal) else "single_instant"
        milestones = _milestones(model, query.root.identity) if kind == "milestone_set" else None
    if kind == "milestone_set" and isinstance(query, ResolvedObjectQuery) and query.paging is None:
        if query.includes:  # pragma: no cover - query validation rejects milestone includes
            raise ValueError("a milestone-set (history / asOfRange) read carries no fetch steps")
        query = continuation.ordered(
            query,
            model.meta,
            milestone_attributes=tuple(axis.start_attribute for axis in ranked_axes(milestones))
            if milestones is not None
            else (),
        )
    versioning = concurrency.concurrency_facet_of(model.meta)
    projection = read_planning.ReadProjectionRequest("all", True)
    if isinstance(query, read_planning.PlannedEntityQuery):
        root_query = (
            replace(
                query,
                execution_value_sources=ExecutionValueSources.authored(query.predicate.predicate),
            )
            if templated
            else query
        )
        planned = read_planning.ObjectQueryPlan(
            root_query,
            build_include_tree(
                queried=query.target, root=tuple(query.position.concrete_subtypes), positions=()
            ),
            (),
        )
        shared_lock = True if coverage_shared_lock is None else coverage_shared_lock
    else:
        planned = (
            read_planning.plan(
                query, model.meta, projection=projection, defer_execution_values=templated
            )
            if reusable is None
            else replace(
                reusable.query_plan,
                root=read_planning.plan_root(
                    query, model.meta, projection=projection, defer_execution_values=templated
                ),
            )
        )
        shared_lock = _takes_shared_lock(versioning, query.root.identity, preference)
    root_template: CompiledTemplate | None = None
    result_form = "row" if purpose == "write_support" else "instance"
    if templated:
        compiled_root = compile_template(
            planned.root, model.meta, dialect, result_form=result_form, shared_lock=shared_lock
        )
        if isinstance(compiled_root, EmptyRead):
            root = compiled_root
        else:
            root_template = compiled_root
            root = compiled_root.compiled
    else:
        root = compile_read(
            planned.root, model.meta, dialect, result_form=result_form, shared_lock=shared_lock
        )
    if reusable is None:
        fetches = _fetch_work(
            planned, model, dialect, versioning, preference, empty_root=isinstance(root, EmptyRead)
        )
        correlations = correlation_table(
            planned,
            model.meta,
            (index for index, work in enumerate(fetches) if not isinstance(work, EmptyRead)),
        )
        repeating = repeating_levels(
            model,
            (
                () if isinstance(root, EmptyRead) else root.result_contract.resolvable,
                *(
                    work.compiled.result_contract.resolvable
                    if isinstance(work, CompiledTemplate)
                    else ()
                    for work in fetches
                ),
            ),
            (
                step.family
                for step, work in zip(planned.fetch_steps, fetches, strict=True)
                if isinstance(step, read_planning.BackReferenceFetchStep) and work is None
            ),
        )
        repeating |= frozenset(
            index
            for index, compiled in enumerate(
                (
                    root,
                    *(
                        work.compiled if isinstance(work, CompiledTemplate) else work
                        for work in fetches
                    ),
                )
            )
            if isinstance(compiled, CompiledRead) and compiled.result_contract.may_repeat_row_keys
        )
        fetch_rows = tuple(
            bind(
                model,
                work.compiled.result_contract,
                work.compiled.projection,
                correlation_members=correlations[index + 1],
                singleton=index + 1 not in repeating,
            )
            if isinstance(work, CompiledTemplate)
            else None
            for index, work in enumerate(fetches)
        )
        schema = (
            ViewSchema.prepared(
                slot_table(planned),
                (model.layouts.entity(entity.identity) for entity in model.meta.entities),
                repeating_levels=repeating,
            )
            if kind == "single_instant" and purpose == "publication"
            else None
        )
    else:
        repeating = reusable.repeating
        fetches, correlations, fetch_rows, schema = (
            reusable.fetches,
            reusable.correlations,
            reusable.fetch_rows,
            reusable.schema,
        )
    prepared = _ReadPreparation(
        read_planning.release_execution_value_sources(planned),
        root,
        None
        if isinstance(root, EmptyRead)
        else bind(
            model,
            root.result_contract,
            root.projection,
            correlation_members=correlations[0],
            singleton=ROOT_LEVEL not in repeating,
            acquisition=purpose == "write_support",
        ),
        schema,
        repeating,
        correlations,
        fetches,
        fetch_rows,
    )
    return _CachedDelivery(prepared, root_template, model, kind, purpose, milestones)


def _takes_shared_lock(
    versioning: ConcurrencyFacet,
    entity: EntityIdentity,
    preference: ConcurrencyPreference | None,
) -> bool:
    """Whether a read of ``entity`` takes the shared row lock: the lock follows
    the Entity each level reads, and a read no writable unit of work owns has no
    preference and never locks."""
    return preference is not None and versioning.effective_strategy(entity, preference) == "locking"


def _fetch_work(
    planned: read_planning.ObjectQueryPlan,
    model: CatalogedModel,
    dialect: Dialect,
    versioning: ConcurrencyFacet,
    preference: ConcurrencyPreference | None,
    *,
    empty_root: bool,
) -> tuple[_FetchWork, ...]:
    """Each fetch step's retained work, in the dependency order steps are
    planned in: a level whose parent or own target position is empty has no
    occurrences to fetch."""
    work: list[_FetchWork] = []
    for step in planned.fetch_steps:
        parent_empty = (
            empty_root
            if isinstance(step.parent, read_planning.RootRef)
            else isinstance(work[step.parent.index], EmptyRead)
        )
        if parent_empty:
            work.append(EMPTY_READ)
        elif isinstance(step, read_planning.BackReferenceFetchStep):
            work.append(None if planned.includes.position(step.position).target else EMPTY_READ)
        else:
            work.append(
                compile_template(
                    step.query,
                    model.meta,
                    dialect,
                    result_form="instance",
                    shared_lock=_takes_shared_lock(versioning, step.query.target, preference),
                )
            )
    return tuple(work)


class ReadPlanCache:
    """A bounded true LRU with per-key single-flight read planning."""

    __slots__ = (
        "_capacity",
        "_entries",
        "_evictions",
        "_hits",
        "_lock",
        "_misses",
        "_pending",
    )

    def __init__(self, capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY) -> None:
        self._capacity = check_read_plan_cache_capacity(capacity)
        self._entries: OrderedDict[_ReadPlanKey, _CachedDelivery] = OrderedDict()
        self._pending: dict[_ReadPlanKey, _Pending] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def plan(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: ResolvedObjectQuery,
        preference: ConcurrencyPreference | None,
        paging: PagingParameters | None = None,
        policy: ReadPlan | None = None,
    ) -> ReadPlan:
        if paging is not None:
            kind: ReadKind = (
                "milestone_set" if scans_resolved_axis(query.temporal) else "single_instant"
            )
            milestones = (
                _milestones(model, query.root.identity) if kind == "milestone_set" else None
            )
            edge = (
                ()
                if milestones is None
                else tuple(axis.start_attribute for axis in ranked_axes(milestones))
            )
            pages = continuation.plan(query, model.meta, milestone_attributes=edge)
            page_query = pages.first(limit=paging.size)
            plan = ReadPlan(
                model,
                kind,
                "publication",
                milestones,
                page_query,
                resolved_query_pin(query.temporal) if kind == "single_instant" else Pin(),
                _DeferredRead(
                    lambda: self.plan(
                        edition=edition,
                        model=model,
                        dialect=dialect,
                        query=page_query,
                        preference=preference,
                        policy=plan,
                    )._preparation()  # pyright: ignore[reportPrivateUsage] - same-module preparation
                ),
                pages,
            )
            return plan
        return self._cached(
            edition=edition,
            model=model,
            dialect=dialect,
            query=query,
            preference=preference,
            kind=policy.kind if policy is not None else None,
            milestones=policy.milestones if policy is not None else None,
            purpose="publication",
            coverage_shared_lock=None,
        )

    def plan_acquisition(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: read_planning.PlannedEntityQuery,
        preference: ConcurrencyPreference | None,
        coverage_shared_lock: bool | None = None,
    ) -> ReadPlan:
        shape = _milestones(model, query.target)
        kind: ReadKind = (
            "milestone_set"
            if coverage_shared_lock is not None
            and any(axis.dimension is TemporalDimension.VALID_TIME for axis in ranked_axes(shape))
            else "single_instant"
        )
        return self._cached(
            edition=edition,
            model=model,
            dialect=dialect,
            query=query,
            preference=preference,
            kind=kind,
            milestones=shape if kind == "milestone_set" else None,
            purpose="write_support",
            coverage_shared_lock=coverage_shared_lock,
        )

    def _cached(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: ResolvedObjectQuery | read_planning.PlannedEntityQuery,
        preference: ConcurrencyPreference | None,
        kind: ReadKind | None,
        milestones: TemporalShape | None,
        purpose: ReadPurpose,
        coverage_shared_lock: bool | None,
    ) -> ReadPlan:
        if self._capacity == 0:
            return _plan_uncached(
                model=model,
                dialect=dialect,
                query=query,
                preference=preference,
                kind=kind,
                milestones=milestones,
                purpose=purpose,
                coverage_shared_lock=coverage_shared_lock,
            ).render(query)
        key = _read_plan_key(
            edition=edition,
            model=model,
            dialect=dialect,
            query=query,
            preference=preference,
            purpose=purpose,
            coverage_shared_lock=coverage_shared_lock,
        )
        reusable: _ReadPreparation | None = None
        pending: _Pending | None = None
        elected = False
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                self._hits += 1
            elif (pending := self._pending.get(key)) is None:
                pending = _Pending(threading.Event())
                self._pending[key] = pending
                self._misses += 1
                reusable = next(
                    (
                        value.prepared
                        for existing, value in reversed(self._entries.items())
                        if existing.same_family(key)
                    ),
                    None,
                )
                elected = True
        if cached is not None:
            return cached.render(query)
        assert pending is not None
        if not elected:
            return self._awaited(key, pending).render(query)

        try:
            cached = _plan_uncached(
                model=model,
                dialect=dialect,
                query=query,
                preference=preference,
                kind=kind,
                milestones=milestones,
                purpose=purpose,
                coverage_shared_lock=coverage_shared_lock,
                reusable=reusable,
                templated=True,
            )
        except BaseException as exc:
            with self._lock:
                self._pending.pop(key, None)
                pending.error = exc
                pending.ready.set()
            raise

        with self._lock:
            self._pending.pop(key, None)
            self._entries[key] = cached
            if len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
                self._evictions += 1
            pending.prepared = cached
            pending.ready.set()
        return cached.render(query)

    def _awaited(self, key: _ReadPlanKey, pending: _Pending) -> _CachedDelivery:
        pending.ready.wait()
        if pending.error is not None:
            raise pending.error
        cached = pending.prepared
        if cached is None:  # pragma: no cover - event publication invariant
            raise RuntimeError("a completed read plan published no result")
        with self._lock:
            self._hits += 1
            if key in self._entries:
                self._entries.move_to_end(key)
        return cached

    def _statistics(self) -> _ReadPlanCacheStatistics:
        with self._lock:
            return _ReadPlanCacheStatistics(
                self._capacity,
                len(self._entries),
                self._hits,
                self._misses,
                self._evictions,
            )


UNCACHED_READ_PLANNER: ReadPlanner = ReadPlanCache(0)
