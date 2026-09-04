"""Per-operation classification: why coordination is required, and whether the
operation is Overlap-Visible.

One rule function per operation kind, each a pure function of the operation and
the two endpoints, so a rule is stated and proven where it is decided rather
than inside a traversal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import EntityIdentity, Metamodel, TablePerHierarchy
from parallax.evolution.model_evolution._matching import Matching
from parallax.evolution.model_evolution._values import (
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinationReason,
    EntityRemoved,
    EvolutionOperation,
)

__all__ = ["Classification", "classify"]

_UNILATERAL: tuple[CoordinationReason, ...] = ()

# Removing a model-facing declaration invalidates a previously valid authored
# operation, which is the whole of why it needs coordination: the physical
# objects the earlier edition addressed may simply be left in place, so no
# destructive transformation is required of the database.
_REMOVAL: tuple[CoordinationReason, ...] = (CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED,)


@dataclass(frozen=True, slots=True)
class Classification:
    """One operation's verdict: its coordination reasons, and its overlap visibility.

    An empty reason set is unilateral. ``overlap_visible`` says the later edition
    may store a value an earlier edition cannot admit, which is narrower than
    behavioral change.
    """

    reasons: tuple[CoordinationReason, ...]
    overlap_visible: bool


def classify(
    matching: Matching, operations: Sequence[EvolutionOperation]
) -> tuple[Classification, ...]:
    """Classify each operation, positionally."""
    return tuple(_classify_one(matching, operation) for operation in operations)


def _classify_one(matching: Matching, operation: EvolutionOperation) -> Classification:
    match operation:
        case ConcreteSubtypeAdded():
            return Classification(
                reasons=_UNILATERAL,
                overlap_visible=_shares_a_table(matching.later, operation.entity),
            )
        case EntityRemoved() | ConcreteSubtypeRemoved():
            return Classification(reasons=_REMOVAL, overlap_visible=False)
        case _:
            return Classification(reasons=_UNILATERAL, overlap_visible=False)


def _shares_a_table(model: Metamodel, entity: EntityIdentity) -> bool:
    """Whether ``entity``'s family stores every concrete position in one Table.

    A table-per-hierarchy addition is Overlap-Visible because a later writer can
    place a new discriminator value in the shared Table that an earlier reader
    cannot admit; a table-per-concrete-subtype addition occupies a separate
    Table the earlier edition never reads.
    """
    view = inheritance_view(model).entity(entity)
    return view is not None and isinstance(view.strategy, TablePerHierarchy)
