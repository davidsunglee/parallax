"""Per-operation classification: why coordination is required, and whether the
operation is Overlap-Visible.

One rule function per operation kind, each a pure function of the operation and
the two endpoints, so a rule is stated and proven where it is decided rather
than inside a traversal. Every rule compares the EFFECTIVE facts a family fixes
rather than the raw declarations a field delta reports, so an authored form that
normalizes to the accepted value it already had classifies as no change at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AttributePrimaryKey,
    PersistenceMode,
    PrimaryKey,
    TablePerHierarchy,
)
from parallax.evolution.model_evolution._matching import EntityFacts, Matching
from parallax.evolution.model_evolution._values import (
    COORDINATION_REASON_ORDER,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinationReason,
    EntityAltered,
    EntityRemoved,
    EvolutionOperation,
    InheritanceChanged,
    MaximumLengthChanged,
    NullabilityChanged,
    OptimisticLockingChanged,
    PersistenceChanged,
    PrimaryKeyChanged,
    ReadOnlyChanged,
    StorageChanged,
    StorageContainerChanged,
    StorageLayoutChanged,
    TypeChanged,
)

__all__ = ["Classification", "classify"]

_AUTHORING = CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED
_MIGRATION = CoordinationReason.DATABASE_MIGRATION_REQUIRED

_UNILATERAL: tuple[CoordinationReason, ...] = ()

# Removing a model-facing declaration invalidates a previously valid authored
# operation, which is the whole of why it needs coordination: the physical
# objects the earlier edition addressed may simply be left in place, so no
# destructive transformation is required of the database.
_REMOVAL: tuple[CoordinationReason, ...] = (_AUTHORING,)


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
                overlap_visible=_shares_a_table(matching.entities.added[operation.entity].family),
            )
        case EntityRemoved() | ConcreteSubtypeRemoved() | AttributeRemoved():
            return Classification(reasons=_REMOVAL, overlap_visible=False)
        case EntityAltered():
            return _entity_alteration(matching.entities.surviving[operation.entity], operation)
        case AttributeAdded():
            return _attribute_addition(matching, operation)
        case AttributeAltered():
            return _attribute_alteration(operation)
        case _:
            return Classification(reasons=_UNILATERAL, overlap_visible=False)


def _shares_a_table(family: InheritanceEntityView) -> bool:
    """Whether ``family`` stores every concrete position in one Table.

    A table-per-hierarchy addition is Overlap-Visible because a later writer can
    place a new discriminator value in the shared Table that an earlier reader
    cannot admit; a table-per-concrete-subtype addition occupies a separate
    Table the earlier edition never reads.
    """
    return isinstance(family.strategy, TablePerHierarchy)


def _attribute_addition(matching: Matching, operation: AttributeAdded) -> Classification:
    """A member added to an Entity that already stores rows.

    Adding a nullable member is unilateral. A required one needs coordination
    until a default and backfill contract makes existing rows satisfy the later
    model; a wholly new Entity may carry required members, because its own
    addition suppresses them and creates a complete empty Table.
    """
    if matching.attributes.added[operation.attribute].nullable:
        return Classification(reasons=_UNILATERAL, overlap_visible=False)
    return Classification(reasons=(_MIGRATION,), overlap_visible=False)


def _entity_alteration(
    surviving: tuple[EntityFacts, EntityFacts], operation: EntityAltered
) -> Classification:
    earlier, later = surviving
    reasons: set[CoordinationReason] = set()
    for delta in operation.deltas:
        match delta:
            case StorageContainerChanged() | StorageLayoutChanged():
                # The two editions cannot address both physical locations
                # through one compiled operation surface.
                reasons.add(_MIGRATION)
            case PersistenceChanged():
                reasons |= _persistence_reasons(earlier.family, later.family)
            case InheritanceChanged():
                reasons |= _inheritance_reasons(earlier.family, later.family)
    return Classification(reasons=_in_fixed_order(reasons), overlap_visible=False)


def _persistence_reasons(
    earlier: InheritanceEntityView, later: InheritanceEntityView
) -> set[CoordinationReason]:
    """Persistence Mode is directional over the whole family: withdrawing writes
    removes valid persistence operations, and granting them adds only new ones."""
    if earlier.persistence is PersistenceMode.READ_WRITE and later.persistence is (
        PersistenceMode.READ_ONLY
    ):
        return {_AUTHORING}
    return set()


def _inheritance_reasons(
    earlier: InheritanceEntityView, later: InheritanceEntityView
) -> set[CoordinationReason]:
    """An inheritance change classified by its effective consequences.

    Interposing an abstract subtype keeps every earlier narrowing valid and every
    earlier physical fact intact, so it is unilateral. Moving a position out of an
    earlier branch invalidates a narrowing through that branch, and a strategy,
    tag, or container change needs the rows themselves transformed.
    """
    reasons: set[CoordinationReason] = set()
    if not _selection_preserved(earlier, later):
        reasons.add(_AUTHORING)
    if not _physically_compatible(earlier, later):
        reasons.add(_MIGRATION)
    return reasons


def _selection_preserved(earlier: InheritanceEntityView, later: InheritanceEntityView) -> bool:
    """Whether every earlier narrowing through this position stays valid.

    The ancestry answers which narrowings reach it, the concrete-subtype set
    answers which rows a narrowing to it denotes, and the applicable members
    answer what such a narrowing may address.
    """
    return (
        set(earlier.ancestry) <= set(later.ancestry)
        and set(earlier.concrete_subtypes) <= set(later.concrete_subtypes)
        and {member.identity for member in earlier.applicable_attributes}
        <= {member.identity for member in later.applicable_attributes}
    )


def _physically_compatible(earlier: InheritanceEntityView, later: InheritanceEntityView) -> bool:
    """Whether the position's rows stay where they are, tagged as they were."""
    return (
        earlier.container == later.container
        and earlier.strategy == later.strategy
        and earlier.tag_column == later.tag_column
        and earlier.tag_value == later.tag_value
    )


def _attribute_alteration(operation: AttributeAltered) -> Classification:
    reasons: set[CoordinationReason] = set()
    overlap_visible = False
    for delta in operation.deltas:
        match delta:
            case TypeChanged():
                # A changed Neutral Type changes accepted operands, write
                # inputs, and decoded results, and no safe widening between type
                # families is inferred from the two accepted types.
                reasons |= {_AUTHORING, _MIGRATION}
            case StorageChanged():
                reasons.add(_MIGRATION)
            case PrimaryKeyChanged(earlier_key, later_key):
                reasons |= _primary_key_reasons(earlier_key, later_key)
            case NullabilityChanged(_, nullable):
                if nullable:
                    overlap_visible = True
                else:
                    reasons.add(_MIGRATION)
            case MaximumLengthChanged(earlier_length, later_length):
                if _bound_relaxed(earlier_length, later_length):
                    overlap_visible = True
                else:
                    reasons.add(_MIGRATION)
            case ReadOnlyChanged(_, read_only):
                if read_only:
                    reasons.add(_AUTHORING)
            case OptimisticLockingChanged(_, optimistic_locking):
                if optimistic_locking:
                    # A caller-authored Attribute becomes framework-owned, so a
                    # previously valid write no longer supplies it.
                    reasons.add(_AUTHORING)
    return Classification(reasons=_in_fixed_order(reasons), overlap_visible=overlap_visible)


def _primary_key_reasons(
    earlier: AttributePrimaryKey, later: AttributePrimaryKey
) -> set[CoordinationReason]:
    """Membership moves the physical key as well as the lookup and insert shape;
    a generation change alone moves only what the caller supplies."""
    if isinstance(earlier, PrimaryKey) != isinstance(later, PrimaryKey):
        return {_AUTHORING, _MIGRATION}
    return {_AUTHORING}


def _bound_relaxed(earlier: int | None, later: int | None) -> bool:
    """Whether the later String bound admits every value the earlier one did."""
    if later is None:
        return True
    if earlier is None:
        return False
    return later > earlier


def _in_fixed_order(reasons: set[CoordinationReason]) -> tuple[CoordinationReason, ...]:
    return tuple(reason for reason in COORDINATION_REASON_ORDER if reason in reasons)
