from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from itertools import chain
from typing import Literal, Protocol, cast

from parallax.core.base import (
    INFINITY_LITERAL,
    JSON,
    TIMESTAMP,
    ManagedValue,
    NeutralType,
    TemporalBound,
    detach_json_container,
    matches_neutral_type,
)
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import Dialect
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.predicate._validated import DeferredKeySet
from parallax.core.storage_layout import StorageLayoutFacet, TableLayout
from parallax.core.wire import (
    WireDecodingError,
    WireEncodingError,
    WireValue,
    decode_wire,
    encode_wire,
)

type _ScalarBindForm = Literal["MANAGED", "COMPARISON_TEXT"]
type _BindForm = _ScalarBindForm | Literal["MANAGED_ARRAY"]
type _TypedBindSlot = tuple[NeutralType, _ScalarBindForm]


class _NoWireBindOverride:
    pass


_NO_WIRE_BIND_OVERRIDE = _NoWireBindOverride()


@dataclass(frozen=True, slots=True)
class _TypedBindSpan:
    start: int
    stop: int
    neutral_type: NeutralType
    form: _BindForm

    def indexes(self) -> range:
        return range(self.start, self.stop)

    def shifted(self, offset: int) -> _TypedBindSpan:
        return _TypedBindSpan(self.start + offset, self.stop + offset, self.neutral_type, self.form)

    def resized(self, growth: int) -> _TypedBindSpan:
        return _TypedBindSpan(self.start, self.stop + growth, self.neutral_type, self.form)


@dataclass(frozen=True, slots=True)
class _RepeatedTypedBindSpan:
    start: int
    width: int
    stride: int
    repetitions: int
    neutral_type: NeutralType
    form: _BindForm

    def indexes(self) -> Iterator[int]:
        return (
            self.start + repetition * self.stride + offset
            for repetition in range(self.repetitions)
            for offset in range(self.width)
        )

    def shifted(self, offset: int) -> _RepeatedTypedBindSpan:
        return _RepeatedTypedBindSpan(
            self.start + offset,
            self.width,
            self.stride,
            self.repetitions,
            self.neutral_type,
            self.form,
        )


type _BindSpan = _TypedBindSpan | _RepeatedTypedBindSpan


@dataclass(frozen=True, slots=True)
class _WireBindOverride:
    index: int
    value: WireValue


@dataclass(frozen=True, slots=True)
class LoweredStatement:
    """Canonical SQL, driver binds, and compact canonical-Wire bind metadata."""

    sql: str
    binds: tuple[object, ...] = ()
    _typed_bind_spans: tuple[_BindSpan, ...] = field(default=(), repr=False)
    _wire_bind_overrides: tuple[_WireBindOverride, ...] = field(default=(), repr=False)
    _compiler_proven: bool = field(default=False, repr=False, compare=False)

    @property
    def typed_bind_spans(self) -> tuple[_BindSpan, ...]:
        return self._typed_bind_spans

    @property
    def wire_bind_overrides(self) -> tuple[_WireBindOverride, ...]:
        return self._wire_bind_overrides

    @property
    def is_compiler_proven(self) -> bool:
        return self._compiler_proven

    def wire_binds(self) -> tuple[WireValue, ...]:
        unprojected = object()
        projected: list[WireValue | object] = [unprojected] * len(self.binds)
        for span in self._typed_bind_spans:
            for index in span.indexes():
                projected[index] = _typed_wire_bind(self.binds[index], span.neutral_type, span.form)
        for override in self._wire_bind_overrides:
            projected[override.index] = override.value
        for index, value in enumerate(projected):
            if value is unprojected:
                projected[index] = _wire_bind(self.binds[index])
        return cast("tuple[WireValue, ...]", tuple(projected))

    def replace_bind(self, index: int, values: Sequence[object]) -> LoweredStatement:
        """Replace one bind with ``values``, which the typed span covering it then covers."""
        binds = (*self.binds[:index], *values, *self.binds[index + 1 :])
        growth = len(values) - 1
        if not growth:
            return LoweredStatement(
                self.sql,
                binds,
                self._typed_bind_spans,
                self._wire_bind_overrides,
                self._compiler_proven,
            )

        def moved(span: _BindSpan) -> _BindSpan:
            if span.start > index:
                return span.shifted(growth)
            if isinstance(span, _TypedBindSpan) and index < span.stop:
                return span.resized(growth)
            return span

        return LoweredStatement(
            self.sql,
            binds,
            tuple(moved(span) for span in self._typed_bind_spans),
            tuple(
                _WireBindOverride(override.index + growth, override.value)
                if override.index > index
                else override
                for override in self._wire_bind_overrides
            ),
            self._compiler_proven,
        )

    def defer_keys(self, *, postgres_array: bool) -> DeferredKeyTemplate:
        """Prepare all physical occurrences of one marker, compared by identity."""
        indexes = tuple(
            index for index, value in enumerate(self.binds) if isinstance(value, DeferredKeySet)
        )
        if not indexes or any(self.binds[index] is not self.binds[indexes[0]] for index in indexes):
            raise SqlGenError("a child read template must carry exactly one deferred key set")
        boundaries = (0, *(index + 1 for index in indexes))
        runs = tuple(
            self.binds[start:stop]
            for start, stop in zip(boundaries, (*indexes, len(self.binds)), strict=True)
        )
        spans = tuple(
            (
                span,
                bisect_left(indexes, span.start),
                bisect_left(
                    indexes,
                    span.stop
                    if isinstance(span, _TypedBindSpan)
                    else span.start + (span.repetitions - 1) * span.stride + span.width,
                ),
            )
            for span in self._typed_bind_spans
        )
        if any(
            isinstance(span, _RepeatedTypedBindSpan) and before != after
            for span, before, after in spans
        ):
            raise SqlGenError("a deferred key set cannot occupy repeated row-bind metadata")
        overrides = tuple(
            (override, bisect_left(indexes, override.index))
            for override in self._wire_bind_overrides
        )
        return DeferredKeyTemplate(
            self,
            postgres_array,
            runs,
            spans,
            overrides,
            () if postgres_array else tuple(self.sql.split("__parallax_deferred_keys__")),
        )


@dataclass(frozen=True, slots=True)
class DeferredKeyTemplate:
    """Statement-owned access prepared once, without retaining execution keys."""

    statement: LoweredStatement
    postgres_array: bool
    _runs: tuple[tuple[object, ...], ...]
    _spans: tuple[tuple[_BindSpan, int, int], ...]
    _overrides: tuple[tuple[_WireBindOverride, int], ...]
    _sql_parts: tuple[str, ...]

    def render(self, keys: list[ManagedValue]) -> LoweredStatement:
        if not keys:
            raise SqlGenError("a child read template requires at least one gathered key")
        statement = self.statement
        values = (keys,) if self.postgres_array else keys
        binds = tuple(
            chain(
                chain.from_iterable(chain(run, values) for run in self._runs[:-1]),
                self._runs[-1],
            )
        )
        growth = len(values) - 1
        if not growth:
            spans = statement.typed_bind_spans
            overrides = statement.wire_bind_overrides
        else:
            spans = tuple(
                _TypedBindSpan(
                    span.start + before * growth,
                    span.stop + after * growth,
                    span.neutral_type,
                    span.form,
                )
                if isinstance(span, _TypedBindSpan)
                else span.shifted(before * growth)
                for span, before, after in self._spans
            )
            overrides = tuple(
                replace(override, index=override.index + before * growth)
                for override, before in self._overrides
            )
        sql = (
            statement.sql
            if self.postgres_array
            else ", ".join("?" for _ in keys).join(self._sql_parts)
        )
        return LoweredStatement(sql, binds, spans, overrides, statement.is_compiler_proven)


def _typed_wire_bind(value: object, neutral_type: NeutralType, form: _BindForm) -> WireValue:
    if isinstance(value, DeferredKeySet):
        raise SqlGenError("a deferred key set has no Wire projection until its keys are rendered")
    if form == "MANAGED":
        return encode_wire(neutral_type, cast("ManagedValue", value))
    if form == "MANAGED_ARRAY":
        return [encode_wire(neutral_type, element) for element in cast("list[ManagedValue]", value)]
    return cast("str", value)


def _wire_bind(value: object) -> WireValue:
    if isinstance(value, JsonDocument):
        value = detach_json_container(value.value)
    if value is None:
        return None
    try:
        managed = decode_wire(JSON, cast("WireValue", value))
        return encode_wire(JSON, managed)
    except (WireDecodingError, WireEncodingError) as error:
        raise SqlGenError(
            f"bind carrier {type(value).__name__} is not an ordinary Wire value: {error}"
        ) from error


class SqlGenError(ValueError):
    """A query cannot be lowered to SQL (unsupported node or unbound reference)."""


def table_layout(
    storage: StorageLayoutFacet, facet: InheritanceFacet, entity: EntityIdentity
) -> TableLayout:
    """The canonical layout of the one Table a read of ``entity``'s rows selects.

    Total at every call site: a table-per-hierarchy position reads the root's
    shared Table and a concrete subtype reads its own, so only a
    table-per-concrete-subtype abstract position owns none — and such a position
    fans out to its concretes, each carrying its own layout, before a layout is
    ever asked for.
    """
    view = facet.entity(entity)
    container = None if view is None else view.container
    if container is None:  # pragma: no cover - an abstract position never reads one table
        raise SqlGenError(f"{entity.canonical}: this inheritance position has no Table Layout")
    layout = storage.table(container)
    if layout is None:  # pragma: no cover - every accepted Table compiles exactly one layout
        raise SqlGenError(f"{container.name}: the model compiles no layout for this table")
    return layout


# the concrete resolution scope; neither exposes `bind`, `binds`, nor the `ctx` #


class ColumnScope(Protocol):
    """Renders one of the active target's own columns.

    The whole capability a guard FRAGMENT needs: which alias (if any) qualifies
    this statement's own columns. No resolution, no allocation, no binding.
    """

    def own_column(self, column: str) -> str: ...


class PlanScope(ColumnScope, Protocol):
    """What a plan-only module may do: resolve against the model, render its own
    and its children's columns, and ALLOCATE an alias — nothing else.

    Alias allocation is deliberately included: a hop plan must take its child
    alias at the point the hop opens, before anything descends into the hop's
    interior, which is what keeps the `t0, t1, …` sequence depth-first in source
    order (m-sql rule 1). Allocation is order-visible but not order-FRAGILE — an
    alias is consumed by the very fragment that took it.

    Binding is the opposite, and is deliberately absent: `bind` / `binds` appear
    nowhere here, so a planner cannot push a bind even by accident. Guard binds
    travel out of a plan as VALUES and are pushed by the caller, after it has
    lowered its own interior predicate.

    :meth:`child` returns another ``PlanScope`` rather than the concrete scope,
    so descending never widens the capability back out.
    """

    @property
    def meta(self) -> Metamodel: ...

    @property
    def facet(self) -> InheritanceFacet: ...

    @property
    def storage(self) -> StorageLayoutFacet: ...

    @property
    def entity(self) -> EntityMetadata: ...

    def column_of(self, attr_ref: str) -> str: ...

    def column_for(self, attribute: AttributeMetadata) -> str: ...

    def next_alias(self) -> str: ...

    def child(self, entity: EntityMetadata, alias: str) -> PlanScope: ...


class StatementBuilder:
    """One statement's aliases and role-classified bind sequence."""

    __slots__ = (
        "_binds",
        "_classified",
        "_next_alias_index",
        "_typed_spans",
        "_wire_overrides",
        "dialect",
        "facet",
        "meta",
        "requires_variant_partition",
        "storage",
    )

    def __init__(
        self,
        meta: Metamodel,
        facet: InheritanceFacet,
        storage: StorageLayoutFacet,
        dialect: Dialect,
    ) -> None:
        self.meta = meta
        self.facet = facet
        self.storage = storage
        self.dialect = dialect
        self._binds: list[object] = []
        self._typed_spans: list[_BindSpan] = []
        self._wire_overrides: dict[int, WireValue] = {}
        self._classified = 0
        self.requires_variant_partition = False
        self._next_alias_index = 1

    def next_alias(self) -> str:
        index = self._next_alias_index
        self._next_alias_index = index + 1
        return f"t{index}"

    def bind_structural(self, value: object) -> None:
        self._append(value)

    def bind_structural_all(self, values: Sequence[object]) -> None:
        for value in values:
            self.bind_structural(value)

    def bind_document(self, value: JsonDocument) -> None:
        self._append(value)

    def bind_managed(self, value: object, neutral_type: NeutralType) -> None:
        self._bind_typed(value, neutral_type, "MANAGED")

    def bind_comparison_text(self, value: object, neutral_type: NeutralType) -> None:
        self._bind_typed(value, neutral_type, "COMPARISON_TEXT")

    def bind_managed_array(self, value: object, neutral_type: NeutralType) -> None:
        self._bind_typed(value, neutral_type, "MANAGED_ARRAY")

    def bind_framework(
        self,
        value: object,
        *,
        wire_value: WireValue | _NoWireBindOverride = _NO_WIRE_BIND_OVERRIDE,
    ) -> None:
        index = len(self._binds)
        self._append(value)
        if not isinstance(wire_value, _NoWireBindOverride):
            self._wire_overrides[index] = wire_value

    def bind_framework_all(self, values: Sequence[object]) -> None:
        for value in values:
            self.bind_framework(value)

    def bind_typed_rows(
        self,
        rows: Sequence[Sequence[object]],
        pattern: Sequence[_TypedBindSlot | None],
    ) -> None:
        """Append rows and compact their actual non-null type/form runs."""
        if not rows:
            return
        width = len(pattern)
        if any(len(row) != width for row in rows):
            raise SqlGenError("a repeated bind pattern has inconsistent row widths")
        if len(rows) == 1:
            for value, slot in zip(rows[0], pattern, strict=True):
                self._bind_row_value(value, slot)
            return
        start = len(self._binds)
        for row in rows:
            for value in row:
                self._append(value)
                if isinstance(value, TemporalBound):
                    self._wire_overrides[len(self._binds) - 1] = INFINITY_LITERAL
        signatures = tuple(
            tuple(
                self._typed_row_slot(value, slot) for value, slot in zip(row, pattern, strict=True)
            )
            for row in rows
        )
        self._append_row_spans(start, width, signatures)

    def _append_row_spans(
        self,
        start: int,
        width: int,
        signatures: tuple[tuple[_TypedBindSlot | None, ...], ...],
    ) -> None:
        """Record the typed spans of rows bound contiguously from ``start``.

        Consecutive rows with one signature form a group, and each run of equal
        non-null slots in that signature becomes one span: a repeated span across
        a group of several rows, or a plain span for a group of one.
        """
        group_start = 0
        for group_stop in range(1, len(signatures) + 1):
            if group_stop < len(signatures) and signatures[group_stop] == signatures[group_start]:
                continue
            signature = signatures[group_start]
            run_start: int | None = None
            run_slot: _TypedBindSlot | None = None
            for offset, slot in enumerate((*signature, None)):
                if slot == run_slot:
                    continue
                if run_slot is not None and run_start is not None:
                    run_type, run_form = run_slot
                    repetitions = group_stop - group_start
                    span_start = start + group_start * width + run_start
                    if repetitions == 1:
                        self._append_typed_span(
                            _TypedBindSpan(
                                span_start,
                                span_start + offset - run_start,
                                run_type,
                                run_form,
                            )
                        )
                    else:
                        self._typed_spans.append(
                            _RepeatedTypedBindSpan(
                                span_start,
                                offset - run_start,
                                width,
                                repetitions,
                                run_type,
                                run_form,
                            )
                        )
                run_start = offset if slot is not None else None
                run_slot = slot
            group_start = group_stop

    def append_fragment(self, statement: LoweredStatement) -> None:
        """Append a compiler-proven fragment without discarding bind provenance."""
        if not statement.is_compiler_proven:
            raise SqlGenError("only a finished compiler fragment may be appended")
        offset = len(self._binds)
        self._binds.extend(statement.binds)
        self._classified += len(statement.binds)
        for span in statement.typed_bind_spans:
            self._append_typed_span(span.shifted(offset))
        for override in statement.wire_bind_overrides:
            self._wire_overrides[offset + override.index] = override.value

    def finish(self, sql: str) -> LoweredStatement:
        """Validate bind metadata and seal a compiler-proven statement."""
        if self._classified != len(self._binds):
            raise SqlGenError("every compiler bind must be supplied through one role-specific API")
        occupied: set[int] = set()
        spans = tuple(sorted(self._typed_spans, key=lambda span: span.start))
        for span in spans:
            if isinstance(span, _TypedBindSpan):
                valid_shape = span.start >= 0 and span.stop > span.start
            else:
                valid_shape = (
                    span.start >= 0
                    and span.width > 0
                    and span.stride >= span.width
                    and span.repetitions > 0
                )
            if not valid_shape:
                raise SqlGenError("typed bind metadata has invalid dimensions or stride")
            for index in span.indexes():
                if not 0 <= index < len(self._binds) or index in occupied:
                    raise SqlGenError("typed bind metadata is out of range or overlaps")
                occupied.add(index)
        overrides = tuple(
            _WireBindOverride(index, value) for index, value in sorted(self._wire_overrides.items())
        )
        if any(not 0 <= override.index < len(self._binds) for override in overrides):
            raise SqlGenError("Wire bind override metadata is out of range")
        return LoweredStatement(sql, tuple(self._binds), spans, overrides, True)

    def _append(self, value: object) -> None:
        self._binds.append(value)
        self._classified += 1

    def _bind_row_value(self, value: object, slot: _TypedBindSlot | None) -> None:
        typed_slot = self._typed_row_slot(value, slot)
        if typed_slot is not None:
            neutral_type, form = typed_slot
            self._bind_typed(value, neutral_type, form)
        elif isinstance(value, TemporalBound):
            self.bind_framework(value, wire_value=INFINITY_LITERAL)
        elif isinstance(value, JsonDocument):
            self.bind_document(value)
        else:
            self.bind_structural(value)

    def _typed_row_slot(self, value: object, slot: _TypedBindSlot | None) -> _TypedBindSlot | None:
        if slot is None or value is None:
            return None
        neutral_type, form = slot
        if isinstance(value, TemporalBound) or (
            neutral_type == TIMESTAMP and value == INFINITY_LITERAL
        ):
            return None
        valid = (
            matches_neutral_type(value, neutral_type)
            if form == "MANAGED"
            else isinstance(value, str)
        )
        if not valid:
            raise SqlGenError(
                f"repeated bind carrier {type(value).__name__} does not match "
                f"{form} slot {neutral_type!r}"
            )
        return slot

    def _bind_typed(self, value: object, neutral_type: NeutralType, form: _BindForm) -> None:
        index = len(self._binds)
        self._append(value)
        self._append_typed_span(_TypedBindSpan(index, index + 1, neutral_type, form))

    def _append_typed_span(self, span: _BindSpan) -> None:
        if (
            isinstance(span, _TypedBindSpan)
            and self._typed_spans
            and isinstance(self._typed_spans[-1], _TypedBindSpan)
            and self._typed_spans[-1].stop == span.start
            and self._typed_spans[-1].neutral_type == span.neutral_type
            and self._typed_spans[-1].form == span.form
        ):
            previous = self._typed_spans[-1]
            self._typed_spans[-1] = _TypedBindSpan(
                previous.start, span.stop, span.neutral_type, span.form
            )
        else:
            self._typed_spans.append(span)
