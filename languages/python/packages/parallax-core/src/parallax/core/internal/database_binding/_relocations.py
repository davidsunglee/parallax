from __future__ import annotations

from dataclasses import dataclass

from parallax.core.internal.database_binding._physical import PhysicalSequence, PhysicalTable
from parallax.core.internal.database_binding._resolved import ResolvedBinding
from parallax.core.internal.metamodel import EntityIdentity

__all__ = ["Relocation", "SequenceRelocated", "TableRelocated", "relocations_between"]


@dataclass(frozen=True, slots=True)
class TableRelocated:
    """A mapping owner both selections hold resolves to a different physical table."""

    mapping_owner: EntityIdentity
    earlier: PhysicalTable
    later: PhysicalTable


@dataclass(frozen=True, slots=True)
class SequenceRelocated:
    """A logical allocator both selections declare resolves to a different physical sequence."""

    allocator: str
    earlier: PhysicalSequence
    later: PhysicalSequence


type Relocation = TableRelocated | SequenceRelocated
"""One surviving physical object that moved between two resolved bindings."""


def relocations_between(earlier: ResolvedBinding, later: ResolvedBinding) -> tuple[Relocation, ...]:
    """Every surviving table, then every surviving sequence, whose physical object moved.

    Tables follow canonical owner order and sequences allocator-key order. An
    owner or allocator only one side holds was added or removed, not moved.
    """
    tables = tuple(
        TableRelocated(table.mapping_owner, held.physical, table.physical)
        for table in later.tables
        if (held := earlier._tables.get(table.mapping_owner)) is not None  # pyright: ignore[reportPrivateUsage] - the owning module's own index
        and held.physical != table.physical
    )
    sequences = tuple(
        SequenceRelocated(allocator, held_sequence, physical)
        for allocator, physical in later.sequences.items()
        if (held_sequence := earlier.sequences.get(allocator)) is not None
        and held_sequence != physical
    )
    return (*tables, *sequences)
