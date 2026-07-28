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
builder: `parallax.snapshot.materialize.Node`.

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

from typing import Protocol

from parallax.core.dialect import Dialect
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.storage_layout import StorageLayoutFacet, TableLayout


class SqlGenError(ValueError):
    """An operation cannot be lowered to SQL (unsupported node or unbound reference)."""


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
# errors rather than review findings. `_predicate.EntityScope` satisfies both   #
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


class Ctx:
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

    __slots__ = ("_next_alias_index", "binds", "dialect", "facet", "meta", "storage")

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
