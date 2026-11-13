from __future__ import annotations

from dataclasses import dataclass, field

from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.storage_layout import TableLayout, TemporalHistoryConstraints

__all__ = [
    "PhysicalSequence",
    "PhysicalTable",
    "ResolvedTable",
    "ResolvedTemporalConstraints",
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
class ResolvedTable:
    """One mapping owner's table under one binding.

    ``sql`` is the dialect's rendering of ``physical``, made once at resolution
    and read by every statement naming the table. ``layout`` and
    ``temporal_constraints`` are functions of the owner, the model, and
    ``physical``, so they stay out of comparison.
    """

    mapping_owner: EntityIdentity
    physical: PhysicalTable
    sql: str
    layout: TableLayout = field(compare=False, repr=False)
    temporal_constraints: ResolvedTemporalConstraints | None = field(compare=False, repr=False)
