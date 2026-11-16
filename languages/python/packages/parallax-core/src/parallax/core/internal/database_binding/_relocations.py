from __future__ import annotations

from dataclasses import dataclass

from parallax.core.internal.database_binding._physical import (
    PhysicalSequence,
    PhysicalTable,
    ResolvedSequence,
    sequence_physical,
)
from parallax.core.internal.database_binding._resolved import ResolvedBinding
from parallax.core.internal.metamodel import EntityIdentity

__all__ = [
    "AllocatorSettingsChanged",
    "BreakingChange",
    "SequenceRelocated",
    "TableRelocated",
    "breaking_changes_between",
]


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


@dataclass(frozen=True, slots=True)
class AllocatorSettingsChanged:
    """A native allocator both selections declare changes its allocation settings.

    Its batch size, its increment size, or its key range differs."""

    allocator: str
    earlier: ResolvedSequence
    later: ResolvedSequence


type BreakingChange = TableRelocated | SequenceRelocated | AllocatorSettingsChanged
"""One change to a surviving physical object that invalidates what a root
holds against it."""


def breaking_changes_between(
    earlier: ResolvedBinding, later: ResolvedBinding
) -> tuple[BreakingChange, ...]:
    """Every surviving table that moved, then every surviving allocator whose
    sequence moved or whose allocation settings changed.

    Tables follow canonical owner order and allocators allocator-key order, a
    relocation before a settings change of the same allocator. An owner or
    allocator only one side holds was added or removed, and an allocator one
    side generates natively and the other through a registry changed strategy;
    neither invalidates anything a root holds, so neither is reported.
    """
    tables = tuple(
        TableRelocated(table.mapping_owner, held.physical, table.physical)
        for table in later.tables
        if (held := earlier._tables.get(table.mapping_owner)) is not None  # pyright: ignore[reportPrivateUsage] - the owning module's own index
        and held.physical != table.physical
    )
    sequences: list[BreakingChange] = []
    for allocator, current in later.sequences.items():
        held_sequence = earlier.sequences.get(allocator)
        if held_sequence is None:
            continue
        before, after = sequence_physical(held_sequence), sequence_physical(current)
        if before != after:
            sequences.append(SequenceRelocated(allocator, before, after))
        if (
            isinstance(held_sequence, ResolvedSequence)
            and isinstance(current, ResolvedSequence)
            and held_sequence.allocation_settings != current.allocation_settings
        ):
            sequences.append(AllocatorSettingsChanged(allocator, held_sequence, current))
    return (*tables, *sequences)
