"""Read planning and its bounded cross-delivery reuse policy.

The deep interface is :class:`ReadPlanner`: every read supplies the immutable
facts that can affect planning and receives an opaque :class:`ReadPlan` whose
behavior is sufficient to assemble a Page. The default implementation keeps a
bounded true-LRU of exact-query plans. Capacity zero takes the same construction
path without retaining a plan between calls.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Literal, Protocol, cast

from parallax.core import deep_fetch
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity
from parallax.core.object_query._validated import (
    ContinuationCoordinate,
    Paging,
    ValidatedObjectQuery,
)
from parallax.core.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_template,
)
from parallax.core.sql_gen._seek import null_pattern
from parallax.core.temporal_read import scans_validated_axis
from parallax.core.unit_work import Concurrency
from parallax.snapshot.materialize import PageBuilder, UnwindTree
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._views import ViewSchema

__all__ = ["ReadPlan", "ReadPlanner"]

type ResultForm = Literal["row", "instance"]
type _ReadPlanKey = tuple[
    str,
    _Identity,
    _Identity,
    object,
    ResultForm,
    Concurrency | None,
]
type _FamilyKey = tuple[str, _Identity, _Identity, object, ResultForm, Concurrency | None]

_DEFAULT_CAPACITY = 16


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
class _ReadPlanLevel:
    template: CompiledTemplate
    rows: PreparedRead


@dataclass(frozen=True, slots=True)
class ReadPlan:
    """An immutable read plan consumed through behavioral accessors."""

    _query_plan: deep_fetch.ObjectQueryPlan
    _root: CompiledRead
    _root_rows: PreparedRead
    _schema: ViewSchema
    _correlations: tuple[tuple[AttributeIdentity, ...], ...]
    _includes: UnwindTree
    _children: tuple[_ReadPlanLevel | None, ...]

    @property
    def level_count(self) -> int:
        return len(self._query_plan.levels)

    def root_read(self) -> tuple[CompiledRead, PreparedRead]:
        return self._root, self._root_rows

    def page_builder(self, observer: object | None) -> PageBuilder:
        return PageBuilder(self._schema, observer)

    def ready_levels(self, completed: set[int]) -> tuple[int, ...]:
        return tuple(
            index
            for index, level in enumerate(self._query_plan.levels)
            if index not in completed
            and (isinstance(level.parent, deep_fetch.RootRef) or level.parent.index in completed)
        )

    def level(self, index: int) -> deep_fetch.FetchLevel:
        return self._query_plan.levels[index]

    def correlation_members(self, source: int) -> tuple[AttributeIdentity, ...]:
        return self._correlations[source]

    def child_read(self, index: int, keys: Sequence[object]) -> tuple[CompiledRead, PreparedRead]:
        child = self._children[index]
        if child is None:
            raise ValueError("an executable child level requires a prepared template")
        return child.template.render(keys), child.rows

    def include_tree(self) -> UnwindTree:
        return self._includes

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
        query: ValidatedObjectQuery,
        result_form: ResultForm,
        preference: Concurrency | None,
    ) -> ReadPlan: ...


@dataclass(frozen=True, slots=True)
class _CachedDelivery:
    family_key: _FamilyKey
    plan: ReadPlan
    coordinate_positions: tuple[tuple[int, int], ...] = ()
    limit_positions: tuple[int, ...] = ()

    def render(self, query: ValidatedObjectQuery) -> ReadPlan:
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


@dataclass(slots=True)
class _Pending:
    ready: threading.Event
    prepared: _CachedDelivery | None = None
    error: BaseException | None = None


def _frozen_query_value(value: object) -> object:
    value_type = type(value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return (
            value_type,
            frozenset(
                (_frozen_query_value(key), _frozen_query_value(item))
                for key, item in mapping.items()
            ),
        )
    if isinstance(value, tuple | list):
        return (
            value_type,
            tuple(_frozen_query_value(item) for item in cast("Sequence[object]", value)),
        )
    if isinstance(value, set | frozenset):
        values = cast("set[object] | frozenset[object]", value)
        return value_type, frozenset(_frozen_query_value(item) for item in values)
    if is_dataclass(value) and not isinstance(value, type):
        return (
            value_type,
            tuple(
                (item.name, _frozen_query_value(getattr(value, item.name)))
                for item in fields(value)
            ),
        )
    return value_type, value


def _query_key(query: ValidatedObjectQuery) -> object:
    paging = query.paging
    page = (
        None
        if paging is None
        else ("first" if paging.seek is None else ("after", null_pattern(paging.seek.coordinate)))
    )
    return _frozen_query_value(
        (
            query.authored if paging is None else replace(query.authored, limit=None),
            query.limit if paging is None else None,
            page,
        )
    )


def _read_plan_key(
    *,
    edition: str,
    model: CatalogedModel,
    dialect: Dialect,
    query: ValidatedObjectQuery,
    result_form: ResultForm,
    preference: Concurrency | None,
) -> _ReadPlanKey:
    return (
        edition,
        _Identity(model),
        _Identity(dialect),
        _query_key(query),
        result_form,
        preference,
    )


def _family_key(
    *,
    edition: str,
    model: CatalogedModel,
    dialect: Dialect,
    query: ValidatedObjectQuery,
    result_form: ResultForm,
    preference: Concurrency | None,
) -> _FamilyKey:
    return (
        edition,
        _Identity(model),
        _Identity(dialect),
        _frozen_query_value(
            query.authored if query.paging is None else replace(query.authored, limit=None)
        ),
        result_form,
        preference,
    )


def _template_query(
    query: ValidatedObjectQuery,
) -> tuple[ValidatedObjectQuery, tuple[object | None, ...], object | None]:
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
    edition: str,
    model: CatalogedModel,
    dialect: Dialect,
    query: ValidatedObjectQuery,
    result_form: ResultForm,
    preference: Concurrency | None,
    reusable: ReadPlan | None = None,
) -> _CachedDelivery:
    from parallax.snapshot.handle import _read

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
            _read.entity_read_lock(model.meta, query.root.identity, preference),
            *(
                None
                if level.is_back_reference
                else _read.entity_read_lock(model.meta, level.query_template().target, preference)
                for level in planned.levels
            ),
        ),
    )
    correlations = (
        reusable._correlations  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
        if reusable is not None
        else _read.correlation_table(planned, model.meta)
    )
    root = compile_read(
        planned.root,
        model.meta,
        dialect,
        result_form=result_form,
        lock=locks[0],
    )
    children: tuple[_ReadPlanLevel | None, ...] = (
        reusable._children  # pyright: ignore[reportPrivateUsage] - same-module plan reuse
        if reusable is not None
        else tuple(
            None
            if level.is_back_reference
            else _prepared_level(
                model,
                compile_template(
                    level.query_template(),
                    model.meta,
                    dialect,
                    result_form=result_form,
                    lock=locks[index + 1],
                ),
                correlations[index + 1],
            )
            for index, level in enumerate(planned.levels)
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
                _read.slot_table(planned),
                (model.layouts.entity(entity.identity) for entity in model.meta.entities),
            )
            if result_form == "instance" and not scans_validated_axis(query.temporal)
            else ViewSchema.of()
        ),
        correlations,
        reusable.include_tree() if reusable is not None else _read.include_tree(planned.levels),
        children,
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
    return _CachedDelivery(
        _family_key(
            edition=edition,
            model=model,
            dialect=dialect,
            query=query,
            result_form=result_form,
            preference=preference,
        ),
        prepared,
        positions,
        limit_positions,
    )


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

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
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
        query: ValidatedObjectQuery,
        result_form: ResultForm,
        preference: Concurrency | None,
    ) -> ReadPlan:
        if self._capacity == 0:
            return _plan_uncached(
                edition=edition,
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
        family_key = _family_key(
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
                        for value in reversed(self._entries.values())
                        if value.family_key == family_key
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
                edition=edition,
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
) -> _ReadPlanLevel:
    return _ReadPlanLevel(
        template,
        bind(model, template.compiled, correlation_members=correlations),
    )
