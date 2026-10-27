from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final, Literal, NamedTuple, Protocol, assert_never

from parallax.core import deep_fetch, inheritance
from parallax.core._execution._unit_work.uow import Concurrency
from parallax.core.dialect import Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity
from parallax.core.object_query._resolved import (
    ResolvedAsOfSelection,
    ResolvedHistorySelection,
    ResolvedLatestSelection,
    ResolvedObjectQuery,
    ResolvedRangeSelection,
    ResolvedTemporalSelection,
)
from parallax.core.predicate._resolved import (
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
from parallax.core.read_delivery._fetch import correlation_table, entity_read_lock, slot_table
from parallax.core.read_delivery._page import PageBuilder, ViewSchema
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_template,
)
from parallax.core.sql_gen._predicate import affix_needs_escape
from parallax.core.sql_gen._seek import continuation_pattern
from parallax.core.temporal_read import scans_resolved_axis

__all__ = [
    "DEFAULT_READ_PLAN_CACHE_CAPACITY",
    "EMPTY_READ",
    "UNCACHED_READ_PLANNER",
    "EmptyRead",
    "ReadPlan",
    "ReadPlanCache",
    "ReadPlanner",
    "check_read_plan_cache_capacity",
]

type ResultForm = Literal["row", "instance"]

DEFAULT_READ_PLAN_CACHE_CAPACITY: Final = 16
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


@dataclass(frozen=True, slots=True)
class EmptyRead:
    """A read position no stored row can occupy: its effective concrete set is
    empty, so it has no statement to execute and no rows to convert."""


EMPTY_READ: Final = EmptyRead()

type _FetchWork = CompiledTemplate | EmptyRead | None


@dataclass(frozen=True, slots=True)
class ReadPlan:
    """An immutable read plan consumed through behavioral accessors."""

    _query_plan: deep_fetch.ObjectQueryPlan
    _root: CompiledRead | EmptyRead
    _root_rows: ReadRowConverter | None
    _schema: ViewSchema
    _correlations: tuple[tuple[AttributeIdentity, ...], ...]
    _fetches: tuple[_FetchWork, ...]
    _fetch_rows: tuple[ReadRowConverter | None, ...]

    @property
    def fetch_count(self) -> int:
        return len(self._query_plan.fetch_steps)

    def root_read(self) -> tuple[CompiledRead, ReadRowConverter] | EmptyRead:
        root = self._root
        if isinstance(root, EmptyRead):
            return root
        assert self._root_rows is not None
        return root, self._root_rows

    def page_builder(self, observer: object | None) -> PageBuilder:
        return PageBuilder(self._schema, observer)

    def ready_fetches(self, completed: set[int]) -> tuple[int, ...]:
        return tuple(
            index
            for index, step in enumerate(self._query_plan.fetch_steps)
            if index not in completed
            and (isinstance(step.parent, deep_fetch.RootRef) or step.parent.index in completed)
        )

    def fetch_step(self, index: int) -> deep_fetch.FetchStep:
        return self._query_plan.fetch_steps[index]

    def prepared_fetch(
        self, index: int
    ) -> tuple[CompiledTemplate, ReadRowConverter] | EmptyRead | None:
        """Fetch step ``index``'s executable template and converter, or
        :class:`EmptyRead` for a level at or beneath an empty position, or
        ``None`` for a reachable back-reference, which attaches from rows
        already converted."""
        fetch = self._fetches[index]
        if fetch is None or isinstance(fetch, EmptyRead):
            return fetch
        rows = self._fetch_rows[index]
        assert rows is not None
        return fetch, rows

    def include_tree(self) -> deep_fetch.IncludeTree:
        return self._query_plan.includes

    def with_root(
        self,
        compiled: CompiledRead,
    ) -> ReadPlan:
        return replace(self, _root=compiled)


class ReadPlanner(Protocol):
    """The one read-planning operation every delivery crosses."""

    def plan(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: ResolvedObjectQuery,
        result_form: ResultForm,
        preference: Concurrency | None,
    ) -> ReadPlan: ...


@dataclass(frozen=True, slots=True)
class _CachedDelivery:
    """A plan whose root is ``root_template``'s unrendered read, when it has one."""

    plan: ReadPlan
    root_template: CompiledTemplate | None

    def render(self, query: ResolvedObjectQuery) -> ReadPlan:
        template = self.root_template
        if template is None:
            return self.plan
        compiled = template.render(query=query)
        if compiled is template.compiled:
            return self.plan
        return self.plan.with_root(compiled)


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
    result_form: ResultForm
    concurrency: Concurrency | None
    delivery: object

    def same_family(self, other: _ReadPlanKey) -> bool:
        return (
            self.edition == other.edition
            and self.model == other.model
            and self.dialect == other.dialect
            and self.result_form == other.result_form
            and self.concurrency == other.concurrency
            and self.query == other.query
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
    query: ResolvedObjectQuery,
    result_form: ResultForm,
    preference: Concurrency | None,
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
        _QueryKey(_query_key(query)),
        result_form,
        preference,
        delivery,
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
            operands = (
                values
                if isinstance(values, DeferredKeySet)
                else tuple(_operand_key(value) for value in values)
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


def _plan_uncached(
    *,
    model: CatalogedModel,
    dialect: Dialect,
    query: ResolvedObjectQuery,
    result_form: ResultForm,
    preference: Concurrency | None,
    reusable: ReadPlan | None = None,
    templated: bool = False,
) -> _CachedDelivery:
    """Plan ``query``; a ``templated`` plan's root is the unrendered read of a
    template every cached delivery renders."""
    empty_root = _empty_root(model, query)
    projection = deep_fetch.ReadProjectionRequest(
        "none" if result_form == "row" else "all",
        result_form == "instance",
    )
    planned = (
        deep_fetch.plan(query, model.meta, projection=projection, defer_execution_values=templated)
        if reusable is None
        else replace(
            reusable._query_plan,  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
            root=deep_fetch.plan_root(
                query, model.meta, projection=projection, defer_execution_values=templated
            ),
        )
    )
    root_template: CompiledTemplate | None = None
    root: CompiledRead | EmptyRead
    if empty_root:
        root = EMPTY_READ
    else:
        lock = entity_read_lock(model.meta, query.root.identity, preference)
        if templated:
            root_template = compile_template(
                planned.root, model.meta, dialect, result_form=result_form, lock=lock
            )
            root = root_template.compiled
        else:
            root = compile_read(
                planned.root, model.meta, dialect, result_form=result_form, lock=lock
            )
    if reusable is None:
        fetches = _fetch_work(
            planned, model, dialect, result_form, preference, empty_root=empty_root
        )
        correlations = correlation_table(
            planned,
            model.meta,
            (index for index, work in enumerate(fetches) if not isinstance(work, EmptyRead)),
        )
        fetch_rows = tuple(
            bind(
                model,
                work.compiled.result_contract,
                work.compiled.projection,
                correlation_members=correlations[index + 1],
            )
            if isinstance(work, CompiledTemplate)
            else None
            for index, work in enumerate(fetches)
        )
        schema = (
            ViewSchema.prepared(
                slot_table(planned),
                (model.layouts.entity(entity.identity) for entity in model.meta.entities),
            )
            if result_form == "instance" and not scans_resolved_axis(query.temporal)
            else ViewSchema.of()
        )
    else:
        fetches, correlations, fetch_rows, schema = (
            reusable._fetches,  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
            reusable._correlations,  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
            reusable._fetch_rows,  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
            reusable._schema,  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
        )
    prepared = ReadPlan(
        deep_fetch.release_execution_value_sources(planned),
        root,
        None
        if isinstance(root, EmptyRead)
        else bind(
            model,
            root.result_contract,
            root.projection,
            correlation_members=correlations[0],
        ),
        schema,
        correlations,
        fetches,
        fetch_rows,
    )
    return _CachedDelivery(prepared, root_template)


def _empty_root(model: CatalogedModel, query: ResolvedObjectQuery) -> bool:
    """Whether ``query``'s result position has no concrete inhabitant.

    Validation refuses an authored narrowing to the empty set, so only an
    unnarrowed dormant abstract target qualifies; a standalone Entity's view is
    its own concrete.
    """
    if query.narrow_to is not None:
        return False
    view = inheritance.view(model.meta).entity(query.root.identity)
    return view is not None and not view.concrete_subtypes


def _fetch_work(
    planned: deep_fetch.ObjectQueryPlan,
    model: CatalogedModel,
    dialect: Dialect,
    result_form: ResultForm,
    preference: Concurrency | None,
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
            if isinstance(step.parent, deep_fetch.RootRef)
            else isinstance(work[step.parent.index], EmptyRead)
        )
        if parent_empty or not planned.includes.position(step.position).target:
            work.append(EMPTY_READ)
        elif isinstance(step, deep_fetch.BackReferenceFetchStep):
            work.append(None)
        else:
            work.append(
                compile_template(
                    step.query,
                    model.meta,
                    dialect,
                    result_form=result_form,
                    lock=entity_read_lock(model.meta, step.query.target, preference),
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
        result_form: ResultForm,
        preference: Concurrency | None,
    ) -> ReadPlan:
        if self._capacity == 0:
            return _plan_uncached(
                model=model,
                dialect=dialect,
                query=query,
                result_form=result_form,
                preference=preference,
            ).render(query)
        key = _read_plan_key(
            edition=edition,
            model=model,
            dialect=dialect,
            query=query,
            result_form=result_form,
            preference=preference,
        )
        reusable: ReadPlan | None = None
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
                        value.plan
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
                result_form=result_form,
                preference=preference,
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
