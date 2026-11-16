from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from parallax.core.internal.database_binding._authored import DatabaseBinding
from parallax.core.internal.database_binding._physical import (
    PhysicalSequence,
    ResolvedSequence,
    ResolvedTable,
)
from parallax.core.internal.database_binding._resolution import resolve
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.metamodel import EntityIdentity, Metamodel

__all__ = ["ResolvedBinding"]


@dataclass(frozen=True, slots=True)
class ResolvedBinding:
    """One model placed by one binding: every table and sequence it needs, resolved.

    Constructing one resolves, validates, and renders every physical object, or
    raises :class:`~parallax.core.internal.database_binding.BindingError`, so a
    resolved binding exists only for the model it was resolved from. Equality
    compares ``meta`` and ``binding``; every resolved product is a function of
    the two.
    """

    meta: Metamodel
    binding: DatabaseBinding
    _tables: Mapping[EntityIdentity, ResolvedTable] = field(init=False, compare=False, repr=False)
    _sequences: Mapping[str, PhysicalSequence | ResolvedSequence] = field(
        init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        tables, sequences = resolve(self.meta, self.binding)
        object.__setattr__(self, "_tables", tables)
        object.__setattr__(self, "_sequences", sequences)

    @property
    def dialect(self) -> Dialect:
        """The backend every resolved object lives in."""
        return self.binding.dialect

    @property
    def tables(self) -> tuple[ResolvedTable, ...]:
        """Every mapping owner's resolved table, in canonical owner order."""
        return tuple(self._tables.values())

    @property
    def sequences(self) -> Mapping[str, PhysicalSequence | ResolvedSequence]:
        """Every logical allocator's sequence, by allocator key in codepoint order.

        A native allocator resolves to its :class:`ResolvedSequence`; an
        allocator a registry ``Sequence`` declares keeps its bare placement.
        """
        return self._sequences

    def table(self, mapping_owner: EntityIdentity) -> ResolvedTable:
        """``mapping_owner``'s resolved table; a non-owner is a :class:`LookupError`."""
        try:
            return self._tables[mapping_owner]
        except KeyError:
            raise LookupError(f"{mapping_owner.canonical} owns no table") from None

    def sequence(self, allocator: str) -> PhysicalSequence | ResolvedSequence:
        """``allocator``'s sequence; an undeclared key is a :class:`LookupError`."""
        try:
            return self._sequences[allocator]
        except KeyError:
            raise LookupError(f"{allocator!r} is no logical allocator of the model") from None
