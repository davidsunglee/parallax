"""One statement's shared lowering state (m-sql), and the error every module raises.

The sink of the private `sql_gen` direction: `_context` imports no sibling, and
every other private module may import it. That is what forces :class:`SqlGenError`
to live here — it is the one name the whole package raises, so any other home
would make some module import sideways.

:class:`Ctx` is the whole of that state, and it is deliberately small: the
metamodel, its Inheritance Facet and Storage Layout Facet, and the dialect a
statement renders against, its ordered bind list, and its alias counter. It
holds **no resolution policy** —
no active entity, no alias, no
aliased-versus-unaliased rendering decision, no attribute search. Those are the
`_predicate` resolution scope's, which is also what makes a `Ctx` a plain mutable
accumulator: with nothing per-scope left on it, exactly ONE exists per statement
(a plain read, a table-per-hierarchy read, each table-per-concrete-subtype `union
all` branch), nested scopes just keep pointing at it, and the frozen-dataclass
costume plus its one-element `alias_seq` cell — a workaround for incrementing an
int on a frozen field — both retire. Precedent for the `slots`-only mutable
builder: `parallax.snapshot.materialize.GraphBuilder`.

:class:`ColumnScope` and :class:`PlanScope` are the NARROWED views of a
resolution scope handed to the plan-only modules (`_inheritance`, `_navigation`),
which sit BELOW the module that defines the concrete scope and so cannot name it.
Neither exposes `bind` or `binds`, which is how "a plan never binds" is a type
rule rather than a convention (see the comment above them). They are signatures
only: every decision they describe is implemented one layer up.

Named without a leading underscore because the MODULE carries the privacy: this
package's supported seam is the six names `__init__` re-exports, and nothing
here reaches it. Importers alias to the module-private spelling
(`import Ctx as _Ctx`), the codebase's established cross-module idiom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from parallax.core.base import ManagedValue, NeutralType
from parallax.core.dialect import Dialect
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.storage_layout import StorageLayoutFacet, TableLayout
from parallax.core.wire import WireValue, decode_canonical_wire, encode_wire

type _BindForm = Literal["MANAGED", "COMPARISON_TEXT"]


@dataclass(frozen=True, slots=True)
class _TypedBindSpan:
    start: int
    stop: int
    neutral_type: NeutralType
    form: _BindForm


@dataclass(frozen=True, slots=True)
class _RepeatedTypedBindSpan:
    start: int
    width: int
    stride: int
    repetitions: int
    neutral_type: NeutralType
    form: _BindForm


@dataclass(frozen=True, slots=True)
class _WireBindOverride:
    index: int
    value: WireValue


@dataclass(frozen=True, slots=True)
class LoweredStatement:
    """Canonical SQL, driver binds, and compact canonical-Wire bind metadata."""

    sql: str
    binds: tuple[object, ...] = ()
    typed_bind_spans: tuple[_TypedBindSpan | _RepeatedTypedBindSpan, ...] = field(
        default=(), repr=False
    )
    wire_bind_overrides: tuple[_WireBindOverride, ...] = field(default=(), repr=False)

    def wire_binds(self) -> tuple[WireValue, ...]:
        projected = list(cast("tuple[WireValue, ...]", self.binds))
        for span in self.typed_bind_spans:
            indexes = (
                range(span.start, span.stop)
                if isinstance(span, _TypedBindSpan)
                else (
                    span.start + repetition * span.stride + offset
                    for repetition in range(span.repetitions)
                    for offset in range(span.width)
                )
            )
            for index in indexes:
                value = self.binds[index]
                if span.form == "MANAGED":
                    projected[index] = encode_wire(span.neutral_type, cast("ManagedValue", value))
                else:
                    managed = decode_canonical_wire(span.neutral_type, cast("WireValue", value))
                    projected[index] = encode_wire(span.neutral_type, managed)
        for override in self.wire_bind_overrides:
            projected[override.index] = override.value
        return tuple(projected)


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


# --------------------------------------------------------------------------- #
# Planner capabilities.                                                        #
#                                                                              #
# A PLAN-only module (`_inheritance`, `_navigation`) must never push a bind:    #
# a framework guard bound while a plan is being built lands AHEAD of the user   #
# binds the caller has not lowered yet, and the emitted SQL text — which still  #
# puts the guard last — silently disagrees with the bind tuple. That is the     #
# defect, and `compile_sweep` cannot see it: the SQL is byte-identical          #
# whenever only one bind is in flight.                                         #
#                                                                              #
# So the rule is enforced by what a planner can HOLD rather than by what its    #
# author remembers. A planner is handed one of the protocols below instead of   #
# the concrete resolution scope; neither exposes `bind`, `binds`, nor the `ctx` #
# that owns them, so `scope.bind(...)` and `scope.ctx.bind(...)` are both type  #
# errors. `_predicate.EntityScope` satisfies both                                #
# structurally, so the narrowing costs the caller nothing — it just passes its  #
# own scope.                                                                   #
# --------------------------------------------------------------------------- #
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

    def next_alias(self) -> str: ...

    def child(self, entity: EntityMetadata, alias: str) -> PlanScope: ...


class StatementBuilder:
    """One statement's shared lowering state: ordered binds and the alias counter.

    Constructing a ``Ctx`` declares a new statement scope — a plain read, a
    table-per-hierarchy read, or each table-per-concrete-subtype `union all`
    branch (which is exactly why each such branch restarts its own aliases at
    `t0` and keeps its binds separable). Nothing copies a ``Ctx``: every nested
    resolution scope holds this same object, so a correlated subquery's aliases
    and binds continue the enclosing statement's single sequence by identity
    rather than by an argument someone has to remember to thread.

    ``facet`` is the model's Inheritance Facet and ``storage`` its Storage
    Layout Facet, the two facets `m-sql` reads: each is retrieved once per
    compiled statement and travels with the model it was compiled from, so no
    lowering step re-derives a family answer or a physical table shape.
    """

    __slots__ = (
        "_next_alias_index",
        "_repeated_typed_spans",
        "_typed_binds",
        "_wire_overrides",
        "binds",
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
        self.binds: list[object] = []
        self._typed_binds: dict[int, tuple[NeutralType, _BindForm]] = {}
        self._repeated_typed_spans: list[_RepeatedTypedBindSpan] = []
        self._wire_overrides: dict[int, WireValue] = {}
        self.requires_variant_partition = False
        # The next alias INDEX after this statement's own `t0`, which is never
        # allocated here — it is the base scope's default alias (m-sql rule 1).
        self._next_alias_index = 1

    def next_alias(self) -> str:
        """The next alias in this statement's single continuing sequence."""
        index = self._next_alias_index
        self._next_alias_index = index + 1
        return f"t{index}"

    def bind(self, value: object) -> None:
        self.binds.append(value)

    def bind_typed(
        self, value: object, neutral_type: NeutralType, form: _BindForm = "MANAGED"
    ) -> None:
        index = len(self.binds)
        self.binds.append(value)
        self._typed_binds[index] = (neutral_type, form)

    def bind_override(self, value: object, wire_value: WireValue) -> None:
        index = len(self.binds)
        self.binds.append(value)
        self._wire_overrides[index] = wire_value

    def repeat_typed_pattern(self, *, start: int, width: int, repetitions: int) -> None:
        """Compact a repeated fixed-width bind pattern into per-run descriptors."""
        if repetitions < 2:
            return
        stop = start + width
        first_row = {
            index: metadata
            for index, metadata in self._typed_binds.items()
            if start <= index < stop
        }
        for repetition in range(1, repetitions):
            row_start = start + repetition * width
            pattern = {
                index - row_start: metadata
                for index, metadata in self._typed_binds.items()
                if row_start <= index < row_start + width
            }
            expected = {index - start: metadata for index, metadata in first_row.items()}
            if pattern != expected:
                return
        runs: list[tuple[int, int, NeutralType, _BindForm]] = []
        for index, (neutral_type, form) in sorted(first_row.items()):
            if (
                runs
                and runs[-1][1] == index
                and runs[-1][2] == neutral_type
                and runs[-1][3] == form
            ):
                run_start, _run_stop, run_type, run_form = runs[-1]
                runs[-1] = (run_start, index + 1, run_type, run_form)
            else:
                runs.append((index, index + 1, neutral_type, form))
        for run_start, run_stop, neutral_type, form in runs:
            run_width = run_stop - run_start
            self._repeated_typed_spans.append(
                _RepeatedTypedBindSpan(
                    run_start,
                    run_width,
                    width,
                    repetitions,
                    neutral_type,
                    form,
                )
            )
            for repetition in range(repetitions):
                for offset in range(run_width):
                    self._typed_binds.pop(run_start + repetition * width + offset, None)

    def extend(self, statement: LoweredStatement) -> None:
        """Append a compiled fragment without discarding its bind provenance."""
        offset = len(self.binds)
        self.binds.extend(statement.binds)
        for span in statement.typed_bind_spans:
            if isinstance(span, _RepeatedTypedBindSpan):
                self._repeated_typed_spans.append(
                    _RepeatedTypedBindSpan(
                        offset + span.start,
                        span.width,
                        span.stride,
                        span.repetitions,
                        span.neutral_type,
                        span.form,
                    )
                )
                continue
            indexes = range(span.start, span.stop)
            for index in indexes:
                self._typed_binds[offset + index] = (span.neutral_type, span.form)
        for override in statement.wire_bind_overrides:
            self._wire_overrides[offset + override.index] = override.value

    def statement(self, sql: str) -> LoweredStatement:
        return LoweredStatement(
            sql,
            tuple(self.binds),
            tuple(
                sorted(
                    (*self._typed_spans(), *self._repeated_typed_spans),
                    key=lambda span: span.start,
                )
            ),
            tuple(
                _WireBindOverride(index, value)
                for index, value in sorted(self._wire_overrides.items())
            ),
        )

    def _typed_spans(self) -> tuple[_TypedBindSpan, ...]:
        spans: list[_TypedBindSpan] = []
        for index, (neutral_type, form) in sorted(self._typed_binds.items()):
            if (
                spans
                and spans[-1].stop == index
                and spans[-1].neutral_type == neutral_type
                and spans[-1].form == form
            ):
                previous = spans[-1]
                spans[-1] = _TypedBindSpan(previous.start, index + 1, neutral_type, form)
            else:
                spans.append(_TypedBindSpan(index, index + 1, neutral_type, form))
        return tuple(spans)
