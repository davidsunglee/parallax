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
    AttributeIdentity,
    AttributeMetadata,
    AttributePrimaryKey,
    Cardinality,
    EntityIdentity,
    PersistenceMode,
    PrimaryKey,
    TablePerHierarchy,
    ValueObjectIdentity,
)
from parallax.evolution.model_evolution._matching import EntityFacts, Matching, RelationshipFacts
from parallax.evolution.model_evolution._values import (
    CALLER_INPUT_ORDER,
    COORDINATION_REASON_ORDER,
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisRemoved,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    AttributeWriteCapability,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinationReason,
    EntityAltered,
    EntityRemoved,
    EvolutionOperation,
    InheritanceChanged,
    MaximumLengthChanged,
    MultiplicityChanged,
    NullabilityChanged,
    OptimisticLockingChanged,
    PersistenceChanged,
    PrimaryKeyChanged,
    ReadOnlyChanged,
    RelationshipAltered,
    RelationshipRemoved,
    StorageChanged,
    StorageContainerChanged,
    StorageLayoutChanged,
    TypeChanged,
    ValueObjectAttributeAdded,
    ValueObjectAttributeAltered,
    ValueObjectAttributeRemoved,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceRemoved,
    attribute_write_capability,
)

__all__ = ["Classification", "classify"]

_AUTHORING = CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED
_MIGRATION = CoordinationReason.DATABASE_MIGRATION_REQUIRED

_UNILATERAL: tuple[CoordinationReason, ...] = ()
_BOTH: tuple[CoordinationReason, ...] = (_AUTHORING, _MIGRATION)

# Removing a model-facing declaration invalidates a previously valid authored
# operation, which is always one reason it needs coordination. It is the whole
# of the reason only where the removal takes its stored shape with it: the
# physical objects the earlier edition addressed are then addressed by nobody
# and may simply be left in place.
_REMOVAL: tuple[CoordinationReason, ...] = (_AUTHORING,)


@dataclass(frozen=True, slots=True)
class _Position:
    """One Entity's family-effective views at the two endpoints.

    Only concrete subtypes own rows, so the stored shape a boundary speaks about
    at a position is the one BOTH editions denote there. A shape arriving under
    the position is answered for where it arrives — a new one by its own
    addition, which creates it complete, and a surviving one reparented in at its
    own inheritance alteration — and one leaving is answered for at the
    alteration that moves it, so neither is this position's to report. A boundary
    phrased instead over a previously valid authored operation alone reads the
    earlier endpoint by itself.
    """

    earlier: InheritanceEntityView
    later: InheritanceEntityView

    @property
    def keeps_a_stored_shape(self) -> bool:
        """Whether a shape stored under this position is still stored under it."""
        return bool(set(self.earlier.concrete_subtypes) & set(self.later.concrete_subtypes))

    @property
    def becomes_a_stored_shape(self) -> bool:
        """Whether the position starts owning rows of its own that it did not own.

        An abstract position owns none, so a role change to a concrete subtype
        adds the position itself to the shapes the family stores.
        """
        was_a_shape = self.earlier.entity in self.earlier.concrete_subtypes
        return not was_a_shape and self.later.entity in self.later.concrete_subtypes

    @property
    def wrote_before(self) -> bool:
        """Whether a caller write valid in the earlier edition still names a shape here.

        ``AuthoringSurfaceChangeRequired`` names a PREVIOUSLY valid shape that
        must change, so an Entity whose family was already effectively
        ``ReadOnly`` has none for a member arriving on it, or for a write flag
        moving over it, to invalidate. An Entity that becomes read-only had one,
        which is why the withdrawal is directional rather than symmetric here. A
        ``ReadWrite`` family is not enough on its own: a write names a concrete
        target, so a change over a position that keeps none reshapes no insert
        the later edition still demands.
        """
        return self.earlier.persistence is PersistenceMode.READ_WRITE and self.keeps_a_stored_shape

    @property
    def writes_after(self) -> bool:
        """Whether a later writer can place a value in a shape an earlier reader holds."""
        return self.later.persistence is PersistenceMode.READ_WRITE and self.keeps_a_stored_shape


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
                overlap_visible=_overlaps_an_earlier_reader(
                    matching, matching.entities.added[operation.entity].family
                ),
            )
        case EntityRemoved() | ConcreteSubtypeRemoved() | RelationshipRemoved():
            # The stored shape goes with the declaration — a Relationship
            # direction stores no value of its own — so nothing the later
            # edition writes meets what the earlier one left behind. An abstract
            # position stores nothing of its own either; the members it handed
            # down survive in each descendant, whose inheritance alteration is
            # where losing them is classified.
            return Classification(reasons=_REMOVAL, overlap_visible=False)
        case AttributeRemoved():
            return _member_removal(
                nullable=matching.attributes.removed[operation.attribute].nullable,
                position=_position(matching, operation.attribute.entity),
            )
        case ValueObjectOccurrenceRemoved():
            return _member_removal(
                nullable=matching.value_objects.removed[operation.value_object].nullable,
                position=_position(matching, operation.value_object.entity),
            )
        case ValueObjectAttributeRemoved():
            return _member_removal(
                nullable=matching.value_object_attributes.removed[
                    operation.value_object_attribute
                ].nullable,
                position=_position(matching, operation.value_object_attribute.value_object.entity),
            )
        case EntityAltered():
            return _entity_alteration(
                matching, matching.entities.surviving[operation.entity], operation
            )
        case AttributeAdded():
            return _attribute_addition(
                matching.attributes.added[operation.attribute],
                _position(matching, operation.attribute.entity),
            )
        case AttributeAltered():
            return _attribute_alteration(
                matching.attributes.surviving[operation.attribute],
                operation,
                _position(matching, operation.attribute.entity),
            )
        case ValueObjectOccurrenceAdded():
            return _member_addition(
                nullable=matching.value_objects.added[operation.value_object].nullable,
                position=_position(matching, operation.value_object.entity),
            )
        case ValueObjectOccurrenceAltered():
            return _occurrence_alteration(
                operation, _position(matching, operation.value_object.entity)
            )
        case ValueObjectAttributeAdded():
            return _member_addition(
                nullable=matching.value_object_attributes.added[
                    operation.value_object_attribute
                ].nullable,
                position=_position(matching, operation.value_object_attribute.value_object.entity),
            )
        case ValueObjectAttributeAltered():
            return _value_object_attribute_alteration(
                operation,
                _position(matching, operation.value_object_attribute.value_object.entity),
            )
        case RelationshipAltered():
            return _relationship_alteration(
                matching.relationships.surviving[operation.relationship]
            )
        case AsOfAxisAdded() | AsOfAxisAltered() | AsOfAxisRemoved():
            # An axis on an Entity that already stores rows changes the temporal
            # operation surface and the framework ownership of its endpoints, and
            # it moves the derived physical key and the bounds existing rows must
            # carry. Removing one is not the mirror of removing a member: the
            # key it leaves is NARROWER than the one the surviving rows were
            # written under, so that history collides beneath the later logical
            # identity. An axis on a wholly new Entity is suppressed by that
            # Entity's own unilateral addition and never reaches here.
            return Classification(reasons=_BOTH, overlap_visible=False)
        case _:
            return Classification(reasons=_UNILATERAL, overlap_visible=False)


def _tags_a_shared_table(family: InheritanceEntityView) -> bool:
    """Whether a later writer can place a new discriminator value an earlier
    reader cannot admit.

    Only table-per-hierarchy shares one Table across a family's shapes, so a
    table-per-concrete-subtype shape occupies a Table the earlier edition never
    reads; and a family the later edition holds read-only has no writer to place
    the value with at all.
    """
    return (
        isinstance(family.strategy, TablePerHierarchy)
        and family.persistence is PersistenceMode.READ_WRITE
    )


def _overlaps_an_earlier_reader(matching: Matching, family: InheritanceEntityView) -> bool:
    """Whether a shape arriving in ``family`` is Overlap-Visible.

    Visibility is a claim about an EARLIER READER, so it asks whether the earlier
    edition already held a position of the family the shape lands in — every such
    position carries the shared Table and a selection through it. A family that
    arrives whole is visible to nobody, and the arriving shape is not that reader
    itself: a surviving position moving here addressed another family's Table
    before it moved.
    """
    return _tags_a_shared_table(family) and any(
        position in matching.entities.surviving
        for position in family.ancestry
        if position != family.entity
    )


def _newly_stored_shape_overlaps(matching: Matching, position: _Position) -> bool:
    """Whether a position that starts storing rows of its own is Overlap-Visible.

    A surviving position turning concrete hands a later writer the same new
    discriminator value an added concrete subtype hands it, so it is judged in
    the family it lands in on exactly those terms — the family whose root it
    keeps, which the earlier edition already held, or another family, which is
    visible to whichever earlier readers it already had. The root a moving
    position leaves takes back every member it gave it, so such a move always
    requires the authoring surface and its visibility is never published; the
    clause is stated on the general terms anyway, because the verdict is the
    rule, not what the assembled evolution goes on to report.
    """
    return position.becomes_a_stored_shape and _overlaps_an_earlier_reader(matching, position.later)


def _attribute_addition(added: AttributeMetadata, position: _Position) -> Classification:
    """An Attribute added to an Entity that survives its arrival.

    A framework-owned Attribute is one no caller ever supplied, so its arrival
    withdraws no previously valid write shape however it is declared.
    """
    return _member_addition(
        nullable=added.nullable,
        position=position,
        caller_authored=attribute_write_capability(added)
        is not AttributeWriteCapability.FRAMEWORK_OWNED,
    )


def _member_removal(*, nullable: bool, position: _Position) -> Classification:
    """A member cut out of an Entity or Value Object that survives it.

    The removal invalidates a previously valid authored operation whatever the
    member declared. A **required** one cut out of a shape that survives under
    the position reaches the database too: that shape still demands a value the
    later model no longer describes, so the object enforcing it must be relaxed
    or removed before a later write is accepted. A nullable member leaves a
    stored form the later edition simply stops writing, and so does one whose
    position keeps no stored shape to demand it. The verdict reads the accepted
    required-ness rather than the physical object enforcing it, which is what
    keeps the rule the same for a member holding a direct Column and one inside
    a Structured Column — the mirror of the addition rule below.
    """
    if nullable or not position.keeps_a_stored_shape:
        return Classification(reasons=_REMOVAL, overlap_visible=False)
    return Classification(reasons=_BOTH, overlap_visible=False)


def _member_addition(
    *, nullable: bool, position: _Position, caller_authored: bool = True
) -> Classification:
    """A member added to an Entity or Value Object that survives its arrival.

    Adding a nullable member is unilateral. A required one needs the database
    where a shape stored under the position survives there: its rows have no
    value for the member until a default and backfill contract supplies one, for
    a scalar Attribute and a Value Object member alike, whether it occupies a
    direct Column or an existing Structured Column. It needs the authoring
    surface too where a previously valid insert carried the value — the member
    is caller-authored and the containing Entity admitted caller writes in the
    earlier edition — because that insert now omits a required input. A wholly
    new Entity may carry required members, because its own addition suppresses
    them and creates a complete empty Table, and so may a position keeping no
    stored shape, which has neither a row to backfill nor an insert to
    invalidate.
    """
    if nullable or not position.keeps_a_stored_shape:
        return Classification(reasons=_UNILATERAL, overlap_visible=False)
    if caller_authored and position.wrote_before:
        return Classification(reasons=_BOTH, overlap_visible=False)
    return Classification(reasons=(_MIGRATION,), overlap_visible=False)


def _position(matching: Matching, entity: EntityIdentity) -> _Position:
    """The containing Entity's family-effective views at the two endpoints.

    Every member operation reaching classification belongs to an Entity that
    survives: a member of an Entity present at one endpoint alone is suppressed
    by that Entity's own addition or removal.
    """
    earlier, later = matching.entities.surviving[entity]
    return _Position(earlier.family, later.family)


def _domain_contraction(position: _Position) -> set[CoordinationReason]:
    """The reasons narrowing a member's admitted value domain carries.

    A contraction is a claim about values already stored and about the shape a
    later write must still be accepted in, so a position keeping no stored shape
    carries no reason for it.
    """
    return {_MIGRATION} if position.keeps_a_stored_shape else set()


def _entity_alteration(
    matching: Matching, surviving: tuple[EntityFacts, EntityFacts], operation: EntityAltered
) -> Classification:
    earlier, later = surviving
    position = _Position(earlier.family, later.family)
    reasons: set[CoordinationReason] = set()
    overlap_visible = False
    for delta in operation.deltas:
        match delta:
            case StorageContainerChanged() | StorageLayoutChanged():
                # The two editions cannot address both physical locations
                # through one compiled operation surface.
                reasons.add(_MIGRATION)
            case PersistenceChanged():
                reasons |= _persistence_reasons(earlier.family, later.family)
            case InheritanceChanged():
                reasons |= _inheritance_reasons(position)
                overlap_visible = _newly_stored_shape_overlaps(matching, position)
    return Classification(reasons=_in_fixed_order(reasons), overlap_visible=overlap_visible)


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


def _inheritance_reasons(position: _Position) -> set[CoordinationReason]:
    """An inheritance change classified by its effective consequences.

    Interposing an abstract subtype keeps every earlier narrowing valid and every
    earlier physical fact intact, so it is unilateral — but only while the
    members the position newly inherits are additions the shapes it keeps could
    have taken on their own, and the members a departing ancestor withdraws are
    removals from a shape that survives. Moving a position out of an earlier
    branch invalidates a narrowing through that branch, and a strategy, tag, or
    container change needs the rows themselves transformed. What survives on a
    position keeping no stored shape is the member comparison, which a read
    targeting it still addresses.
    """
    reasons: set[CoordinationReason] = set()
    if not _selection_preserved(position):
        reasons.add(_AUTHORING)
    if not _physically_compatible(position):
        reasons.add(_MIGRATION)
    return reasons | _inherited_addition_reasons(position) | _inherited_removal_reasons(position)


def _selection_preserved(position: _Position) -> bool:
    """Whether every earlier authored reference to this position stays valid.

    The ancestry answers which narrowings reach it, the concrete-subtype set
    answers which rows a narrowing to it denotes, and the applicable members
    answer what a read of it may address. The member comparison is asked of
    every position, a rowless one included: a read may target it and address the
    members its ancestry makes applicable, and answer with nothing.
    """
    return (
        _reachable_by_the_same_narrowings(position)
        and set(position.earlier.concrete_subtypes) <= set(position.later.concrete_subtypes)
        and _applicable_members(position.earlier) <= _applicable_members(position.later)
    )


def _reachable_by_the_same_narrowings(position: _Position) -> bool:
    """Whether every branch an earlier narrowing came through still reaches here.

    This is the one inheritance clause phrased over a previously valid authored
    operation alone, so it reads the earlier endpoint by itself: a Subtype
    Selection resolves to the position's effective concrete set and is rejected
    where that set is empty, so no narrowing ever reached a position denoting
    nothing then and the branch it hung from carried no authored shape.
    """
    return not position.earlier.concrete_subtypes or set(position.earlier.ancestry) <= set(
        position.later.ancestry
    )


def _applicable_members(
    view: InheritanceEntityView,
) -> set[AttributeIdentity | ValueObjectIdentity]:
    """Every member a narrowing to this position may address."""
    return {member.identity for member in view.applicable_attributes} | {
        occurrence.identity for occurrence in view.applicable_value_objects
    }


def _inherited_addition_reasons(position: _Position) -> set[CoordinationReason]:
    """The reasons the members an arriving ancestor hands this position carry.

    A position joining the ancestry brings every member it declares to whatever
    shape is stored here. An ancestor arriving new suppresses its members' own
    operations, and one that already existed declares them where this shape was
    not stored, so either way this alteration is the only place their consequence
    for these rows is reported. Each is classified exactly as a member declared
    here would be.
    """
    arriving = set(position.later.ancestry) - set(position.earlier.ancestry)
    if not arriving:
        return set()
    inherited = (
        *(
            _attribute_addition(attribute, position)
            for attribute in position.later.applicable_attributes
            if attribute.identity.entity in arriving
        ),
        *(
            _member_addition(nullable=occurrence.nullable, position=position)
            for occurrence in position.later.applicable_value_objects
            if occurrence.identity.entity in arriving
        ),
    )
    return {reason for addition in inherited for reason in addition.reasons}


def _inherited_removal_reasons(position: _Position) -> set[CoordinationReason]:
    """The reasons the members a departing ancestor withdraws from this position carry.

    A position leaving the ancestry takes its declared members off whatever shape
    stays stored here. The ancestor's own removal takes no stored shape with it —
    an abstract position stores nothing of its own and its members live in each
    descendant's Table — so this alteration is where their consequence is
    reported. Each is classified exactly as a member cut out of this position
    would be, which is what makes a required one reach the database where a
    stored shape survives: those rows still carry a value the later model no
    longer describes and the object enforcing it still rejects a later write that
    omits it.
    """
    departing = set(position.earlier.ancestry) - set(position.later.ancestry)
    if not departing:
        return set()
    surviving = _applicable_members(position.later)
    withdrawn = (
        *(
            _member_removal(nullable=attribute.nullable, position=position)
            for attribute in position.earlier.applicable_attributes
            if attribute.identity.entity in departing and attribute.identity not in surviving
        ),
        *(
            _member_removal(nullable=occurrence.nullable, position=position)
            for occurrence in position.earlier.applicable_value_objects
            if occurrence.identity.entity in departing and occurrence.identity not in surviving
        ),
    )
    return {reason for removal in withdrawn for reason in removal.reasons}


def _physically_compatible(position: _Position) -> bool:
    """Whether the position's rows stay where they are, tagged as they were.

    Only a shape stored under the position in both editions has data to carry
    across, so a Table, strategy, or tag change moves nothing where the position
    keeps none.
    """
    if not position.keeps_a_stored_shape:
        return True
    return (
        position.earlier.container == position.later.container
        and position.earlier.strategy == position.later.strategy
        and position.earlier.tag_column == position.later.tag_column
        and position.earlier.tag_value == position.later.tag_value
    )


def _attribute_alteration(
    surviving: tuple[AttributeMetadata, AttributeMetadata],
    operation: AttributeAltered,
    position: _Position,
) -> Classification:
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
                    overlap_visible = position.writes_after
                else:
                    reasons |= _domain_contraction(position)
            case MaximumLengthChanged(earlier_length, later_length):
                if _bound_relaxed(earlier_length, later_length):
                    overlap_visible = position.writes_after
                else:
                    reasons |= _domain_contraction(position)
            case ReadOnlyChanged() | OptimisticLockingChanged():
                # Neither flag is the contract: what invalidates a previously
                # valid write is caller input the later edition no longer
                # accepts, which a flag moving over an Attribute the caller
                # never supplied — a generated key, an axis endpoint — does not,
                # and neither does one moving over an Entity that accepted no
                # caller write to carry the input in the first place.
                if _withdraws_caller_input(*surviving) and position.wrote_before:
                    reasons.add(_AUTHORING)
    return Classification(reasons=_in_fixed_order(reasons), overlap_visible=overlap_visible)


def _occurrence_alteration(
    operation: ValueObjectOccurrenceAltered, position: _Position
) -> Classification:
    reasons: set[CoordinationReason] = set()
    overlap_visible = False
    for delta in operation.deltas:
        match delta:
            case StorageChanged():
                reasons.add(_MIGRATION)
            case MultiplicityChanged():
                # An authored path changes between one object and a collection,
                # whatever the position stores, and each stored document the
                # position keeps carries the shape it left behind.
                reasons |= {_AUTHORING} | _domain_contraction(position)
            case NullabilityChanged(_, nullable):
                if nullable:
                    overlap_visible = position.writes_after
                else:
                    reasons |= _domain_contraction(position)
    return Classification(reasons=_in_fixed_order(reasons), overlap_visible=overlap_visible)


def _value_object_attribute_alteration(
    operation: ValueObjectAttributeAltered, position: _Position
) -> Classification:
    """A scalar leaf owns no Column, key, bound, or locking fact, so its two
    deltas classify exactly as the same two do on a scalar Attribute."""
    reasons: set[CoordinationReason] = set()
    overlap_visible = False
    for delta in operation.deltas:
        match delta:
            case TypeChanged():
                reasons |= {_AUTHORING, _MIGRATION}
            case NullabilityChanged(_, nullable):
                if nullable:
                    overlap_visible = position.writes_after
                else:
                    reasons |= _domain_contraction(position)
    return Classification(reasons=_in_fixed_order(reasons), overlap_visible=overlap_visible)


def _relationship_alteration(
    surviving: tuple[RelationshipFacts, RelationshipFacts],
) -> Classification:
    """A surviving Relationship, judged on the direction it navigates.

    Join, dependency, ordering, and source-side cardinality may all change behind
    a preserved surface; what a previously valid authored navigation cannot
    survive is reaching a different Entity or answering with a collection where
    it answered with one object. The comparison reads the symmetric facet, so a
    change a defining peer makes is seen from the reverse side too, and a
    declaration that merely changes form while naming the same direction is no
    change to the surface at all.
    """
    earlier, later = surviving
    if _navigates_the_same_way(earlier, later):
        return Classification(reasons=_UNILATERAL, overlap_visible=False)
    return Classification(reasons=(_AUTHORING,), overlap_visible=False)


def _navigates_the_same_way(earlier: RelationshipFacts, later: RelationshipFacts) -> bool:
    return (
        earlier.direction.join.target.entity == later.direction.join.target.entity
        and _answers_many(earlier) == _answers_many(later)
    )


def _answers_many(facts: RelationshipFacts) -> bool:
    """Whether navigating this direction answers with a collection."""
    return facts.direction.cardinality is Cardinality.ONE_TO_MANY


def _primary_key_reasons(
    earlier: AttributePrimaryKey, later: AttributePrimaryKey
) -> set[CoordinationReason]:
    """Membership moves the physical key as well as the lookup and insert shape;
    a generation change alone moves only what the caller supplies."""
    if isinstance(earlier, PrimaryKey) != isinstance(later, PrimaryKey):
        return {_AUTHORING, _MIGRATION}
    return {_AUTHORING}


def _withdraws_caller_input(earlier: AttributeMetadata, later: AttributeMetadata) -> bool:
    """Whether the later edition accepts less caller input than the earlier one."""
    return CALLER_INPUT_ORDER.index(attribute_write_capability(later)) < CALLER_INPUT_ORDER.index(
        attribute_write_capability(earlier)
    )


def _bound_relaxed(earlier: int | None, later: int | None) -> bool:
    """Whether the later String bound admits every value the earlier one did."""
    if later is None:
        return True
    if earlier is None:
        return False
    return later > earlier


def _in_fixed_order(reasons: set[CoordinationReason]) -> tuple[CoordinationReason, ...]:
    return tuple(reason for reason in COORDINATION_REASON_ORDER if reason in reasons)
