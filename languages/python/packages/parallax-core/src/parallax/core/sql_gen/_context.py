"""One statement's shared lowering state (m-sql), and the error every module raises.

The sink of the private `sql_gen` direction: `_context` imports no sibling, and
every other private module may import it. That is what forces :class:`SqlGenError`
to live here — it is the one name the whole package raises, so any other home
would make some module import sideways.

:class:`Ctx` is the state a single compiled statement threads through lowering:
the metamodel and dialect it renders against, its ordered bind list, and its
alias counter. Constructing a `Ctx` declares a new statement scope (a plain
read, a table-per-hierarchy read, each table-per-concrete-subtype `union all`
branch); :meth:`Ctx.child` is the one seam that shares the bind list and alias
counter BY IDENTITY, which is what keeps a correlated subquery's aliases and
binds continuing the enclosing statement's single sequence.

Named without a leading underscore because the MODULE carries the privacy: this
package's supported seam is the six names `__init__` re-exports, and nothing
here reaches it. Importers alias to the module-private spelling
(`import Ctx as _Ctx`), the codebase's established cross-module idiom.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parallax.core import inheritance
from parallax.core.descriptor import Attribute, Entity, Metamodel
from parallax.core.dialect import Dialect


def _new_binds() -> list[object]:
    return []


class SqlGenError(ValueError):
    """An operation cannot be lowered to SQL (unsupported node or unbound reference)."""


def _new_alias_seq() -> list[int]:
    # The next alias INDEX after this context's own `t0` — a one-element mutable
    # cell so every `Ctx` created via `.child()` (a correlated-EXISTS interior,
    # nested however deep) shares and advances the SAME counter, continuing the
    # single `t0, t1, …` sequence (m-sql rule 1). A fresh top-level statement
    # (a plain read, a TPH read, or each TPCS `union all` branch — which restarts
    # its own alias scheme at `t0`) gets its own counter via this default factory.
    return [1]


@dataclass(frozen=True, slots=True)
class Ctx:
    """Lowering context: the resolved target entity, its dialect, and its alias."""

    meta: Metamodel
    dialect: Dialect
    entity: Entity
    alias: str = "t0"
    binds: list[object] = field(default_factory=_new_binds)
    alias_seq: list[int] = field(default_factory=_new_alias_seq)
    # A write-appropriate column formatter (m-batch-write readless predicate
    # lowering, `m-batch-write.md` "Predicate-selected readless forms"): a
    # write's rendered predicate is UNALIASED (`where balance < ?`), contrasting
    # the resolving read's aliased `t0.balance < ?` form. ``False`` (the read
    # compiler's own default) for every ordinary read context.
    unaliased: bool = False

    def own_column(self, column: str) -> str:
        """Render one of THIS context's own columns, honoring :attr:`unaliased`.

        The single consultant of :attr:`unaliased` — every reference to a column
        of the active target must route through here so a write's bare-column
        form can never be bypassed. :meth:`column_of` is the attribute-resolving
        front door; a value object's backing DOCUMENT column is not an
        ``Attribute`` and so has no `attr_ref` to resolve, but it is just as much
        this target's own column and takes the same rendering decision.

        Not every column reference is "this context's own": an unnested array
        element's ``t1.value`` is always alias-qualified, because the subquery
        that produced it declares that alias itself regardless of whether the
        enclosing statement is a read or a write. Those callers reach for
        :meth:`Dialect.qualified` directly, and correctly so.
        """
        if self.unaliased:
            return self.dialect.quote(column)
        return self.dialect.qualified(self.alias, column)

    def column_of(self, attr_ref: str) -> str:
        return self.own_column(self.entity_attribute(attr_ref).column)

    def next_alias(self) -> str:
        """The next alias in this statement's single continuing sequence."""
        index = self.alias_seq[0]
        self.alias_seq[0] = index + 1
        return f"t{index}"

    def child(self, entity: Entity, alias: str) -> Ctx:
        """A nested context for a correlated hop's interior: the SAME bind list
        and alias counter (so a nested hop's binds/aliases continue this
        statement's single sequence), a different active entity/alias."""
        return Ctx(
            meta=self.meta,
            dialect=self.dialect,
            entity=entity,
            alias=alias,
            binds=self.binds,
            alias_seq=self.alias_seq,
        )

    def entity_attribute(self, attr_ref: str) -> Attribute:
        _, _, name = attr_ref.partition(".")
        for attribute in self._searchable_attributes():
            if attribute.name == name:
                return attribute
        raise SqlGenError(f"{attr_ref!r} names no attribute on {self.entity.name}")

    def _searchable_attributes(self) -> tuple[Attribute, ...]:
        """The attributes an `attr_ref`'s class-name-qualified name may resolve to.

        A plain entity resolves only against its own declared attributes
        (unchanged). An inheritance participant resolves against its **whole
        family** (`parallax.core.inheritance.family_attributes`): the read's own
        predicate may reference a root-inherited attribute through a concrete
        target's own class name, and a `narrow` branch predicate references that
        branch's own attribute by its own class name — narrow-position validity
        for the reference is enforced upstream (`m-op-algebra`'s model-aware
        validator), so this need only widen the search, never re-validate scope.
        """
        if self.entity.inheritance is None:
            return self.entity.attributes
        return inheritance.family_attributes(self.meta, self.entity)

    def bind(self, value: object) -> None:
        self.binds.append(value)
