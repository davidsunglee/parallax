from __future__ import annotations

from dataclasses import dataclass, field

from parallax.core.internal.dialect import SequenceDdl
from parallax.core.internal.metamodel import EntityIdentity, KeySequence
from parallax.core.internal.storage_layout import (
    DocumentRootConstraint,
    TableLayout,
    TemporalHistoryConstraints,
)

__all__ = [
    "PhysicalSequence",
    "PhysicalTable",
    "ResolvedDocumentRootConstraint",
    "ResolvedSequence",
    "ResolvedTable",
    "ResolvedTemporalConstraints",
    "sequence_ddl",
    "sequence_physical",
]


@dataclass(frozen=True, slots=True)
class PhysicalTable:
    """One physical table: its location's qualifier components, then its local name.

    Components compare exactly, without case folding or dotted-name parsing.
    """

    qualifier: tuple[str, ...]
    name: str


@dataclass(frozen=True, slots=True)
class PhysicalSequence:
    """One physical sequence: its location's qualifier components, then its local name."""

    qualifier: tuple[str, ...]
    name: str


@dataclass(frozen=True, slots=True)
class ResolvedTemporalConstraints:
    """A temporal table's logical constraint definition and the names it takes there.

    ``definition`` is the Storage Layout's own definition, referenced rather
    than copied. Every name derives from the resolved physical local table name.
    ``valid_check_name`` is absent exactly when the table has no Valid-Time axis.
    """

    definition: TemporalHistoryConstraints
    primary_key_name: str
    transaction_check_name: str
    valid_check_name: str | None
    exclusion_name: str


@dataclass(frozen=True, slots=True)
class ResolvedDocumentRootConstraint:
    """A Document table's root-object constraint and the name it takes there.

    ``definition`` is the Storage Layout's own definition, referenced rather
    than copied; ``check_name`` derives from the resolved physical local name.
    """

    definition: DocumentRootConstraint
    check_name: str


@dataclass(frozen=True, slots=True)
class ResolvedTable:
    """One mapping owner's table under one binding.

    ``sql`` is the dialect's rendering of ``physical``, made once at resolution
    and read by every statement naming the table. ``layout`` and the resolved
    constraints are functions of the owner, the model, and ``physical``, so
    they stay out of comparison.
    """

    mapping_owner: EntityIdentity
    physical: PhysicalTable
    sql: str
    layout: TableLayout = field(compare=False, repr=False)
    temporal_constraints: ResolvedTemporalConstraints | None = field(compare=False, repr=False)
    document_root_constraint: ResolvedDocumentRootConstraint | None = field(
        compare=False, repr=False
    )


@dataclass(frozen=True, slots=True)
class ResolvedSequence:
    """One native allocator under one binding: the sequence counterpart of
    :class:`ResolvedTable`, and the one view allocation, DDL, and publication
    comparison read.

    ``sql`` is the dialect's rendering of ``physical`` and ``data_type`` its
    rendering of the key type, both made once at resolution. ``key_sequence``
    is the model's declaration, which every consumer of the allocator states
    identically. ``key_range`` is the key type's value space intersected with
    the sequences the dialect represents. ``consuming_tables`` are the
    binding's resolved tables whose rows take keys from it, in canonical owner
    order; they are a function of the model and binding, so they stay out of
    comparison.
    """

    allocator: str
    physical: PhysicalSequence
    sql: str
    key_sequence: KeySequence
    data_type: str
    key_range: tuple[int, int]
    consuming_tables: tuple[ResolvedTable, ...] = field(compare=False, repr=False)

    @property
    def allocation_settings(self) -> tuple[int, int, tuple[int, int]]:
        """What a reservation held under this sequence depends on: the batch
        size, the stride, and the key range. The initial value only places a
        newly created sequence, so it is no part of them."""
        key_sequence = self.key_sequence
        return (key_sequence.batch_size, key_sequence.increment_size, self.key_range)


def sequence_ddl(sequence: ResolvedSequence) -> SequenceDdl:
    """The live definition ``sequence`` is created with and every reservation
    is checked against: one physical step per reserved block, bounded by the
    key range, starting at the declared initial value."""
    key_sequence = sequence.key_sequence
    low, high = sequence.key_range
    return SequenceDdl(
        data_type=sequence.data_type,
        increment=key_sequence.batch_size * key_sequence.increment_size,
        minimum=low,
        maximum=high,
        start=key_sequence.initial_value,
    )


def sequence_physical(sequence: PhysicalSequence | ResolvedSequence) -> PhysicalSequence:
    """The physical sequence a resolved allocator entry places, whichever
    strategy declared it."""
    return sequence if isinstance(sequence, PhysicalSequence) else sequence.physical
