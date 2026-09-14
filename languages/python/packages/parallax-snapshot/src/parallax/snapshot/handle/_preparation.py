"""Bounded cross-delivery preparation at the Snapshot read seam.

The interface is deliberately one operation: given the immutable facts of a
read, return its immutable preparation. Planning, effective lock derivation,
compilation, binding, schema preparation, normalized keys, edition isolation,
and eviction are implementation details. Callers retain this module, never a
connection or an execution, and use the returned value only while assembling a
Page.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Literal, cast

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
from parallax.core.unit_work import Concurrency
from parallax.snapshot.materialize import UnwindTree
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._views import ViewSchema

__all__ = [
    "PREPARATION_CACHE_CAPACITY",
    "PreparationCache",
    "PreparationCacheStats",
    "PreparedDelivery",
    "PreparedLevel",
]

type ResultForm = Literal["row", "instance"]

PREPARATION_CACHE_CAPACITY = 4


@dataclass(frozen=True, slots=True)
class PreparationCacheStats:
    capacity: int
    size: int
    hits: int
    misses: int
    evictions: int
    invalidations: int


@dataclass(frozen=True, slots=True)
class PreparedLevel:
    template: CompiledTemplate
    rows: PreparedRead


@dataclass(frozen=True, slots=True)
class PreparedDelivery:
    plan: deep_fetch.ObjectQueryPlan
    root: CompiledRead
    root_rows: PreparedRead
    schema: ViewSchema
    correlations: tuple[tuple[AttributeIdentity, ...], ...]
    includes: UnwindTree
    children: tuple[PreparedLevel | None, ...]

    def with_root(
        self,
        plan: deep_fetch.ObjectQueryPlan,
        compiled: CompiledRead,
        prepared: PreparedRead,
    ) -> PreparedDelivery:
        return replace(self, plan=plan, root=compiled, root_rows=prepared)


@dataclass(frozen=True, slots=True)
class _CachedDelivery:
    family_key: object
    delivery: PreparedDelivery
    coordinate_positions: tuple[tuple[int, int], ...] = ()
    limit_positions: tuple[int, ...] = ()

    def render(self, query: ValidatedObjectQuery) -> PreparedDelivery:
        if not self.coordinate_positions:
            return self.delivery
        paging = query.paging
        if paging is None or paging.seek is None:  # pragma: no cover - constructor invariant
            raise ValueError("a continuing preparation requires a seek coordinate")
        binds = list(self.delivery.root.statement.binds)
        for bind_index, carrier_index in self.coordinate_positions:
            binds[bind_index] = paging.seek.coordinate.carriers[carrier_index]
        for bind_index in self.limit_positions:
            binds[bind_index] = query.limit
        compiled = replace(
            self.delivery.root,
            statement=replace(self.delivery.root.statement, binds=tuple(binds)),
        )
        return self.delivery.with_root(self.delivery.plan, compiled, self.delivery.root_rows)


def _frozen_query_value(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        entries = (
            (_frozen_query_value(key), _frozen_query_value(item)) for key, item in mapping.items()
        )
        return tuple(sorted(entries, key=lambda entry: repr(entry[0])))
    if isinstance(value, tuple | list):
        return tuple(_frozen_query_value(item) for item in cast("Sequence[object]", value))
    if isinstance(value, set | frozenset):
        values = cast("set[object] | frozenset[object]", value)
        return tuple(sorted((_frozen_query_value(item) for item in values), key=repr))
    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value),
            tuple(
                (item.name, _frozen_query_value(getattr(value, item.name)))
                for item in fields(value)
            ),
        )
    return value


def _query_key(query: ValidatedObjectQuery) -> object:
    paging = query.paging
    page = (
        None
        if paging is None
        else ("first" if paging.seek is None else ("after", null_pattern(paging.seek.coordinate)))
    )
    return _frozen_query_value((query.authored, query.limit, page))


def _template_query(
    query: ValidatedObjectQuery,
) -> tuple[ValidatedObjectQuery, tuple[object | None, ...], object | None]:
    paging = query.paging
    if paging is None or paging.seek is None:
        return query, (), None
    markers = tuple(
        None if carrier is None else object() for carrier in paging.seek.coordinate.carriers
    )
    limit_marker = object()
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


class PreparationCache:
    """A lock-protected, edition-isolated true LRU of prepared deliveries."""

    __slots__ = (
        "_capacity",
        "_entries",
        "_evictions",
        "_hits",
        "_invalidations",
        "_lock",
        "_misses",
        "_scope",
    )

    def __init__(self, capacity: int = PREPARATION_CACHE_CAPACITY) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("a preparation cache capacity is a positive built-in int")
        self._capacity = capacity
        self._entries: OrderedDict[
            tuple[object, ResultForm, tuple[LockMode | None, ...]], _CachedDelivery
        ] = OrderedDict()
        self._scope: tuple[str, int, str] | None = None
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0

    def prepare(
        self,
        *,
        edition: str,
        model: CatalogedModel,
        dialect: Dialect,
        query: ValidatedObjectQuery,
        result_form: ResultForm,
        preference: Concurrency | None,
    ) -> PreparedDelivery:
        from parallax.snapshot.handle import _read

        scope = (edition, id(model), dialect.name)
        query_key = _query_key(query)
        family_key = _frozen_query_value(query.authored)
        base_key = (query_key, result_form)
        with self._lock:
            if self._scope != scope:
                if self._scope is not None:
                    self._invalidations += 1
                self._entries.clear()
                self._scope = scope
            planned = next(
                (
                    cached.delivery.plan
                    for (held_query, held_form, _held_concurrency), cached in self._entries.items()
                    if (held_query, held_form) == base_key
                ),
                None,
            )
            markers: tuple[object | None, ...] = ()
            limit_marker: object | None = None
            if planned is None:
                compiled_query, markers, limit_marker = _template_query(query)
                planned = deep_fetch.plan(
                    compiled_query,
                    model.meta,
                    projection=deep_fetch.ReadProjectionRequest("all", True),
                )
            locks = cast(
                "tuple[LockMode | None, ...]",
                (
                    _read.entity_read_lock(model.meta, query.root.identity, preference),
                    *(
                        None
                        if level.is_back_reference
                        else _read.entity_read_lock(
                            model.meta, level.query_template().target, preference
                        )
                        for level in planned.levels
                    ),
                ),
            )
            key = (query_key, result_form, locks)
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                self._hits += 1
                return cached.render(query)
            self._misses += 1
            reusable = next(
                (
                    value.delivery
                    for (held_query, held_form, held_locks), value in self._entries.items()
                    if held_query != query_key
                    and held_form == result_form
                    and held_locks == locks
                    and value.family_key == family_key
                ),
                None,
            )
            if query.paging is not None and query.paging.seek is not None and not markers:
                compiled_query, markers, limit_marker = _template_query(query)
                planned = deep_fetch.plan(
                    compiled_query,
                    model.meta,
                    projection=deep_fetch.ReadProjectionRequest("all", True),
                )
            correlations = (
                reusable.correlations
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
            children = (
                reusable.children
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
            prepared = PreparedDelivery(
                planned,
                root,
                bind(model, root, correlation_members=correlations[0]),
                reusable.schema
                if reusable is not None
                else ViewSchema.prepared(
                    _read.slot_table(planned),
                    (model.layouts.entity(entity.identity) for entity in model.meta.entities),
                ),
                correlations,
                reusable.includes if reusable is not None else _read.include_tree(planned.levels),
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
            cached_delivery = _CachedDelivery(family_key, prepared, positions, limit_positions)
            self._entries[key] = cached_delivery
            if len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
                self._evictions += 1
            return cached_delivery.render(query)

    @property
    def stats(self) -> PreparationCacheStats:
        with self._lock:
            return PreparationCacheStats(
                self._capacity,
                len(self._entries),
                self._hits,
                self._misses,
                self._evictions,
                self._invalidations,
            )


def _prepared_level(
    model: CatalogedModel,
    template: CompiledTemplate,
    correlations: tuple[AttributeIdentity, ...],
) -> PreparedLevel:
    return PreparedLevel(
        template,
        bind(model, template.compiled, correlation_members=correlations),
    )
