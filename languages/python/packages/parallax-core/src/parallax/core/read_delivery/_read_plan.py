from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final, Literal, NamedTuple, Protocol, assert_never, cast

from parallax.core import deep_fetch
from parallax.core.base import ManagedValue
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity
from parallax.core.object_query._resolved import (
    ContinuationCoordinate,
    Paging,
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
from parallax.core.sql_gen._seek import null_pattern
from parallax.core.temporal_read import scans_resolved_axis
from parallax.core.unit_work import Concurrency

__all__ = [
    "DEFAULT_READ_PLAN_CACHE_CAPACITY",
    "UNCACHED_READ_PLANNER",
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
class _PreparedFetch:
    template: CompiledTemplate
    rows: ReadRowConverter


@dataclass(frozen=True, slots=True)
class ReadPlan:
    """An immutable read plan consumed through behavioral accessors."""

    _query_plan: deep_fetch.ObjectQueryPlan
    _root: CompiledRead
    _root_rows: ReadRowConverter
    _schema: ViewSchema
    _correlations: tuple[tuple[AttributeIdentity, ...], ...]
    _fetches: tuple[_PreparedFetch | None, ...]

    @property
    def fetch_count(self) -> int:
        return len(self._query_plan.fetch_steps)

    def root_read(self) -> tuple[CompiledRead, ReadRowConverter]:
        return self._root, self._root_rows

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

    def fetch_read(
        self, index: int, keys: list[ManagedValue]
    ) -> tuple[CompiledRead, ReadRowConverter]:
        fetch = self._fetches[index]
        if fetch is None:
            raise ValueError("an executable fetch step requires a prepared template")
        return fetch.template.render(keys), fetch.rows

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
    plan: ReadPlan
    coordinate_positions: tuple[tuple[int, int], ...] = ()
    limit_positions: tuple[int, ...] = ()

    def render(self, query: ResolvedObjectQuery) -> ReadPlan:
        if not self.coordinate_positions and not self.limit_positions:
            return self.plan
        paging = query.paging
        if self.coordinate_positions and (
            paging is None or paging.seek is None
        ):  # pragma: no cover - constructor invariant
            raise ValueError("a continuing read plan requires a seek coordinate")
        compiled, _ = self.plan.root_read()
        binds = list(compiled.statement.binds)
        for bind_index, carrier_index in self.coordinate_positions:
            assert paging is not None and paging.seek is not None
            binds[bind_index] = paging.seek.coordinate.carriers[carrier_index]
        for bind_index in self.limit_positions:
            binds[bind_index] = query.limit
        compiled = replace(
            compiled,
            statement=replace(compiled.statement, binds=tuple(binds)),
        )
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
            "first" if paging.seek is None else ("after", null_pattern(paging.seek.coordinate)),
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

    A plan captures its ordinary binds, so the predicate's and the temporal
    selections' managed operands are part of the key; a page's cap and seek
    coordinate are substituted at render time and are not. Members and
    positions are named by identity: the model the key also names fixes the
    metadata behind each.
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
    """``value`` as plan key material that two binds share only if they are the
    same bind: equal values of different exact types, and Decimals spelling
    one number at different exponents, stay apart."""
    if isinstance(value, Decimal):
        return Decimal, value.as_tuple()
    return type(value), value


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
                _operand_key(pattern),
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
        case ResolvedPresence(negated=negated, target=target, position=position):
            return (
                ResolvedPresence,
                negated,
                target.identity,
                _position_key(position),
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


def _template_query(
    query: ResolvedObjectQuery,
) -> tuple[ResolvedObjectQuery, tuple[object | None, ...], object | None]:
    paging = query.paging
    if paging is None:
        return query, (), None
    limit_marker = object()
    if paging.seek is None:
        return replace(query, limit=cast("int", limit_marker)), (), limit_marker
    markers = tuple(
        None if carrier is None else object() for carrier in paging.seek.coordinate.carriers
    )
    seek = replace(
        paging.seek,
        coordinate=ContinuationCoordinate(markers),
    )
    return (
        replace(
            query,
            paging=Paging(seek),
            limit=cast("int", limit_marker),
        ),
        markers,
        limit_marker,
    )


def _plan_uncached(
    *,
    model: CatalogedModel,
    dialect: Dialect,
    query: ResolvedObjectQuery,
    result_form: ResultForm,
    preference: Concurrency | None,
    reusable: ReadPlan | None = None,
) -> _CachedDelivery:
    compiled_query, markers, limit_marker = _template_query(query)
    planned = deep_fetch.plan(
        compiled_query,
        model.meta,
        projection=deep_fetch.ReadProjectionRequest(
            "none" if result_form == "row" else "all",
            result_form == "instance",
        ),
    )
    locks = cast(
        "tuple[LockMode | None, ...]",
        (
            entity_read_lock(model.meta, query.root.identity, preference),
            *(
                None
                if isinstance(step, deep_fetch.BackReferenceFetchStep)
                else entity_read_lock(model.meta, step.query_template().target, preference)
                for step in planned.fetch_steps
            ),
        ),
    )
    correlations = (
        reusable._correlations  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
        if reusable is not None
        else correlation_table(planned, model.meta)
    )
    root = compile_read(
        planned.root,
        model.meta,
        dialect,
        result_form=result_form,
        lock=locks[0],
    )
    fetches: tuple[_PreparedFetch | None, ...] = (
        reusable._fetches  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
        if reusable is not None
        else tuple(
            None
            if isinstance(step, deep_fetch.BackReferenceFetchStep)
            else _prepared_level(
                model,
                compile_template(
                    step.query_template(),
                    model.meta,
                    dialect,
                    result_form=result_form,
                    lock=locks[index + 1],
                ),
                correlations[index + 1],
            )
            for index, step in enumerate(planned.fetch_steps)
        )
    )
    prepared = ReadPlan(
        planned,
        root,
        bind(model, root, correlation_members=correlations[0]),
        reusable._schema  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
        if reusable is not None
        else (
            ViewSchema.prepared(
                slot_table(planned),
                (model.layouts.entity(entity.identity) for entity in model.meta.entities),
            )
            if result_form == "instance" and not scans_resolved_axis(query.temporal)
            else ViewSchema.of()
        ),
        correlations,
        fetches,
    )
    positions = tuple(
        (bind_index, carrier_index)
        for bind_index, bind_value in enumerate(root.statement.binds)
        for carrier_index, marker in enumerate(markers)
        if marker is not None and bind_value is marker
    )
    expected = {index for index, marker in enumerate(markers) if marker is not None}
    if {carrier for _bind, carrier in positions} != expected:
        raise ValueError("compiled continuation lost a non-null coordinate bind")
    limit_positions = (
        ()
        if limit_marker is None
        else tuple(
            bind_index
            for bind_index, bind_value in enumerate(root.statement.binds)
            if bind_value is limit_marker
        )
    )
    if limit_marker is not None and not limit_positions:
        raise ValueError("compiled continuation lost its page limit bind")
    return _CachedDelivery(prepared, positions, limit_positions)


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
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                self._hits += 1
                return cached.render(query)
            pending = self._pending.get(key)
            if pending is None:
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
                build = True
            else:
                build = False

        if not build:
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
            return cached.render(query)

        try:
            cached = _plan_uncached(
                model=model,
                dialect=dialect,
                query=query,
                result_form=result_form,
                preference=preference,
                reusable=reusable,
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


def _prepared_level(
    model: CatalogedModel,
    template: CompiledTemplate,
    correlations: tuple[AttributeIdentity, ...],
) -> _PreparedFetch:
    return _PreparedFetch(
        template,
        bind(model, template.compiled, correlation_members=correlations),
    )
