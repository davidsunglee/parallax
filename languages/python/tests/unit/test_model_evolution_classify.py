"""One classification rule at a time, read off the evolution it produces.

Each rule is directional, and the compatibility corpus witnesses one direction of
each per case. What is cheaper to state here is the rule itself: both directions
of one boundary side by side, the values at its edges, and the combinations a
corpus model pair would need a whole scenario of its own to reach — several field
deltas on one operation, and an entity fact whose accepted declaration and
effective value disagree.

Every verdict is read off the public result: an operation's reasons are the
Coordination Requirement naming it, and its overlap visibility is its membership
in the Unilateral Evolution's own payload. Nothing here reaches the rule
functions directly.
"""

from __future__ import annotations

import dataclasses

import pytest
from _metamodel_support import Declaration, attribute, identity, key, source

from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INT32, STRING, TIMESTAMP
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    ConcreteSubtype,
    Document,
    EntityIdentity,
    ExactEntityReference,
    Metamodel,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.evolution.model_evolution import (
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisRemoved,
    ConcreteSubtypeAdded,
    CoordinationReason,
    EntityAdded,
    EntityAltered,
    Evolution,
    EvolutionOperation,
    UnilateralEvolution,
    evolve,
)

_AUTHORING = CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED
_MIGRATION = CoordinationReason.DATABASE_MIGRATION_REQUIRED
_BOTH = (_AUTHORING, _MIGRATION)
_UNILATERAL: tuple[CoordinationReason, ...] = ()

_WIDGET = identity("Widget")
_ROOT = identity("Instrument")
_BRANCH = identity("Note")
_LEAF = identity("Bond")

_LABEL = attribute(_WIDGET, "label", type=STRING)


@dataclasses.dataclass(frozen=True, slots=True)
class _Verdict:
    """One operation's classification, as the evolution reports it."""

    reasons: tuple[CoordinationReason, ...]
    overlap_visible: bool


def _member(**facts: object) -> AttributeMetadata:
    """``Widget.label`` with the declared facts under test replaced."""
    return dataclasses.replace(_LABEL, **facts)


def _holding(*members: AttributeMetadata) -> Metamodel:
    """A one-Entity model whose non-key members are ``members``."""
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET, container=Table("widget"), attributes=(key(_WIDGET), *members)
            )
        )
    )


def _verdict(earlier: Metamodel, later: Metamodel) -> _Verdict:
    """The verdict on the one operation the two endpoints differ by."""
    evolution = evolve(earlier, later)
    (operation,) = evolution.operations
    return _verdict_on(evolution, operation)


def _verdict_on(evolution: Evolution, operation: EvolutionOperation) -> _Verdict:
    if isinstance(evolution, UnilateralEvolution):
        return _Verdict((), operation in evolution.overlap_visible_operations)
    named = [
        requirement
        for requirement in evolution.coordination_requirements
        if requirement.operation == operation
    ]
    return _Verdict(named[0].reasons if named else (), overlap_visible=False)


def test_a_member_addition_is_directional_in_what_existing_rows_already_hold() -> None:
    # Nothing has to be migrated for a member existing rows need no value for; a
    # required one has no default and backfill contract to satisfy them with, and
    # every previously valid insert omits the input it now demands.
    assert _verdict(_holding(), _holding(_member(nullable=True))) == _Verdict(_UNILATERAL, False)
    assert _verdict(_holding(), _holding(_member())) == _Verdict(_BOTH, False)


def test_a_required_addition_the_framework_owns_asks_nothing_of_the_caller() -> None:
    # The caller never supplied this value, so no earlier write shape changes;
    # the rows that already exist still have none, so the database does.
    owned = dataclasses.replace(
        attribute(_WIDGET, "version"), optimistic_locking=True, framework_owned=True
    )
    assert _verdict(_holding(), _holding(owned)) == _Verdict((_MIGRATION,), False)


def test_a_flag_moving_on_a_read_only_entity_withdraws_no_input_either() -> None:
    # The same rule from the other side: an Entity that accepted no caller write
    # holds no input for a read-only or optimistic-locking flag to withdraw,
    # however the Attribute's own capability moves.
    assert _verdict(_sealed(_member()), _sealed(_member(read_only=True))) == _Verdict(
        _UNILATERAL, False
    )


def test_a_required_addition_reaches_the_caller_only_where_an_insert_did() -> None:
    # `AuthoringSurfaceChangeRequired` names a PREVIOUSLY valid shape that must
    # change, so an Entity already effectively `ReadOnly` has no insert for the
    # member to invalidate; the rows it holds still have no value for it, so the
    # database is the whole of the reason. An Entity that BECOMES read-only had
    # one, and the addition is classified on its own terms.
    assert _verdict(_sealed(), _sealed(_member())) == _Verdict((_MIGRATION,), False)
    becoming = evolve(_holding(), _sealed(_member()))
    (added,) = [
        operation for operation in becoming.operations if not isinstance(operation, EntityAltered)
    ]
    assert _verdict_on(becoming, added) == _Verdict(_BOTH, False)


def _sealed(*members: AttributeMetadata) -> Metamodel:
    """``_holding``'s model with the Entity effectively ``ReadOnly``."""
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET,
                container=Table("widget"),
                persistence=PersistenceMode.READ_ONLY,
                attributes=(key(_WIDGET), *members),
            )
        )
    )


def test_a_member_removal_is_directional_in_what_the_shape_it_leaves_demands() -> None:
    # The shape survives the member here, so what the database has to do about
    # the removal is what that shape still demands: a nullable member leaves a
    # Column the later edition simply stops writing, while a required one leaves
    # one that rejects every write no longer supplying it.
    assert _verdict(_holding(_member(nullable=True)), _holding()) == _Verdict((_AUTHORING,), False)
    assert _verdict(_holding(_member()), _holding()) == _Verdict(_BOTH, False)


def test_a_neutral_type_change_needs_both_and_infers_no_safe_widening() -> None:
    assert _verdict(_holding(_member(type=INT32)), _holding(_member(type=STRING))) == _Verdict(
        _BOTH, False
    )


def test_a_storage_location_change_needs_the_database_alone() -> None:
    # The member keeps its identity and its whole caller contract; only the two
    # editions' physical addressing disagrees.
    assert _verdict(_holding(_member()), _holding(_member(storage=Column("headline")))) == _Verdict(
        (_MIGRATION,), False
    )


def _keyed(on: str, *, generation: PkGeneration = APPLICATION_ASSIGNED) -> Metamodel:
    """A two-member Entity whose primary key is the member named ``on``.

    An Entity holds exactly one primary key, so moving it is the only way to
    witness membership joining and leaving in one accepted pair.
    """
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET,
                container=Table("widget"),
                attributes=(
                    attribute(
                        _WIDGET,
                        "id",
                        primary_key=PrimaryKey(generation) if on == "id" else NOT_PRIMARY_KEY,
                    ),
                    attribute(
                        _WIDGET,
                        "code",
                        type=STRING,
                        primary_key=PrimaryKey(generation) if on == "code" else NOT_PRIMARY_KEY,
                    ),
                ),
            )
        )
    )


def test_key_membership_reaches_the_database_and_generation_alone_does_not() -> None:
    # Membership moves the physical key as well as the lookup and insert shape,
    # in both the joining and the leaving direction; generation moves only what
    # the caller supplies, so it stops at the authoring surface.
    moved = evolve(_keyed("id"), _keyed("code"))
    assert [_verdict_on(moved, operation) for operation in moved.operations] == [
        _Verdict(_BOTH, False),
        _Verdict(_BOTH, False),
    ]
    assert _verdict(_keyed("id"), _keyed("id", generation=MAX)) == _Verdict((_AUTHORING,), False)


def test_nullability_is_directional_and_expansion_is_overlap_visible() -> None:
    required, nullable = _member(), _member(nullable=True)
    assert _verdict(_holding(required), _holding(nullable)) == _Verdict(_UNILATERAL, True)
    assert _verdict(_holding(nullable), _holding(required)) == _Verdict((_MIGRATION,), False)


@pytest.mark.parametrize(
    ("earlier", "later", "expected"),
    [
        (32, 128, _Verdict(_UNILATERAL, True)),
        (32, None, _Verdict(_UNILATERAL, True)),
        (128, 32, _Verdict((_MIGRATION,), False)),
        (None, 32, _Verdict((_MIGRATION,), False)),
    ],
)
def test_a_string_bound_is_directional_at_both_of_its_edges(
    earlier: int | None, later: int | None, expected: _Verdict
) -> None:
    # A removed bound admits everything a larger one does, and introducing one
    # where none existed contracts the domain exactly as shrinking one does.
    assert (
        _verdict(_holding(_member(max_length=earlier)), _holding(_member(max_length=later)))
        == expected
    )


def test_the_write_surface_is_directional_in_what_the_caller_may_still_supply() -> None:
    editable, read_only = _member(), _member(read_only=True)
    assert _verdict(_holding(editable), _holding(read_only)) == _Verdict((_AUTHORING,), False)
    assert _verdict(_holding(read_only), _holding(editable)) == _Verdict(_UNILATERAL, False)


def _identified(*, read_only: bool) -> Metamodel:
    """A `Widget` whose application-assigned key carries the read-only flag."""
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET,
                container=Table("widget"),
                attributes=(
                    dataclasses.replace(key(_WIDGET), read_only=read_only),
                    _LABEL,
                ),
            )
        )
    )


def test_a_flag_moving_over_input_the_caller_never_had_withdraws_nothing() -> None:
    # An application-assigned key admits insert input and no update whatever its
    # read-only flag says, so declaring the flag changes the declaration without
    # touching the contract — and the raw delta is no verdict on its own.
    assert _verdict(_identified(read_only=False), _identified(read_only=True)) == _Verdict(
        _UNILATERAL, False
    )


def test_member_ownership_is_directional_in_who_supplies_the_value() -> None:
    version = attribute(_WIDGET, "version")
    owned = dataclasses.replace(version, optimistic_locking=True, framework_owned=True)
    assert _verdict(_holding(version), _holding(owned)) == _Verdict((_AUTHORING,), False)
    assert _verdict(_holding(owned), _holding(version)) == _Verdict(_UNILATERAL, False)


def test_an_alteration_reports_the_reasons_of_every_delta_it_carries() -> None:
    # An alteration is one operation however many fields moved, so its reasons
    # are every delta's together, in the fixed order, rather than one verdict
    # per field.
    assert _verdict(
        _holding(_member(max_length=128)),
        _holding(_member(type=INT32, max_length=None, read_only=True)),
    ) == _Verdict(_BOTH, False)


_WIDGET_TABLE = Table("widget")


def _entity(
    *,
    container: Table = _WIDGET_TABLE,
    persistence: PersistenceMode | None = None,
    layout: Document | None = None,
) -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET,
                container=container,
                persistence=persistence,
                layout=layout,
                attributes=(key(_WIDGET), _LABEL),
            )
        )
    )


def test_a_container_change_needs_the_database_alone() -> None:
    assert _verdict(_entity(), _entity(container=Table("widget_archive"))) == _Verdict(
        (_MIGRATION,), False
    )


def test_a_layout_change_needs_the_database_alone() -> None:
    assert _verdict(_entity(), _entity(layout=Document(Column("doc")))) == _Verdict(
        (_MIGRATION,), False
    )


def test_persistence_is_directional_in_its_effective_mode_not_its_declaration() -> None:
    # Declaring nothing and declaring the default are the same effective mode, so
    # the delta the differ reports is not by itself a verdict.
    absent = _entity()
    declared = _entity(persistence=PersistenceMode.READ_WRITE)
    read_only = _entity(persistence=PersistenceMode.READ_ONLY)
    assert _verdict(absent, declared) == _Verdict(_UNILATERAL, False)
    assert _verdict(declared, read_only) == _Verdict((_AUTHORING,), False)
    assert _verdict(read_only, declared) == _Verdict(_UNILATERAL, False)


def _hierarchy(*, interposed: bool, declares: AttributeMetadata | None = None) -> Metamodel:
    """A table-per-hierarchy family whose concrete leaf extends the root
    directly, or extends an abstract position interposed under it.

    The interposed position declares ``declares``, defaulting to a nullable
    member.
    """
    root = Declaration(
        identity=_ROOT,
        container=Table("instrument"),
        attributes=(key(_ROOT),),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    memo = dataclasses.replace(attribute(_BRANCH, "memo", type=STRING), nullable=True)
    branch = Declaration(
        identity=_BRANCH,
        attributes=(declares or memo,),
        inheritance=AbstractSubtype(ExactEntityReference(_ROOT)),
    )
    leaf = Declaration(
        identity=_LEAF,
        attributes=(attribute(_LEAF, "coupon"),),
        inheritance=ConcreteSubtype(ExactEntityReference(_BRANCH if interposed else _ROOT), "BOND"),
    )
    return form_metamodel(source(root, leaf) if not interposed else source(root, branch, leaf))


def _altered(evolution: Evolution) -> EvolutionOperation:
    (operation,) = [
        candidate for candidate in evolution.operations if isinstance(candidate, EntityAltered)
    ]
    return operation


_TERMS = ValueObjectOccurrenceDeclaration(
    name="terms",
    storage=Column("terms"),
    shape=ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("tenor", type=STRING, nullable=True),),
    ),
)


def _interposing(
    *,
    attributes: tuple[AttributeMetadata, ...] = (),
    value_objects: tuple[ValueObjectOccurrenceDeclaration, ...] = (),
) -> Evolution:
    """Interposing an abstract position that declares the given members."""
    root = Declaration(
        identity=_ROOT,
        container=Table("instrument"),
        attributes=(key(_ROOT),),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    branch = Declaration(
        identity=_BRANCH,
        attributes=attributes,
        value_objects=value_objects,
        inheritance=AbstractSubtype(ExactEntityReference(_ROOT)),
    )
    leaf = Declaration(
        identity=_LEAF,
        attributes=(attribute(_LEAF, "coupon"),),
        inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "BOND"),
    )
    return evolve(
        form_metamodel(source(root, leaf)),
        form_metamodel(
            source(
                root,
                branch,
                dataclasses.replace(
                    leaf, inheritance=ConcreteSubtype(ExactEntityReference(_BRANCH), "BOND")
                ),
            )
        ),
    )


def test_an_interposed_position_hands_its_required_members_down() -> None:
    # The arriving parent's own addition suppresses operations for its members,
    # so the descendant's inheritance alteration is where they are answered for:
    # rows already stored carry no value for a required inherited member, and no
    # previously valid insert supplies one — for an Attribute and a Value Object
    # occurrence alike.
    attributes = _interposing(attributes=(attribute(_BRANCH, "issuer", type=STRING),))
    assert _verdict_on(attributes, _altered(attributes)) == _Verdict(_BOTH, False)
    occurrences = _interposing(value_objects=(_TERMS,))
    assert _verdict_on(occurrences, _altered(occurrences)) == _Verdict(_BOTH, False)


def test_an_inheritance_change_is_classified_by_its_effective_consequences() -> None:
    # Interposing an abstract position keeps every earlier narrowing resolvable
    # and every physical fact intact. Flattening one back out is the same raw
    # parent change in the other direction and is NOT the inverse verdict: a
    # narrowing through the position that left stops resolving, while the leaf's
    # Table, tag Column, and tag value are exactly where they were — so the
    # authoring surface reaches coordination on its own.
    direct, interposed = _hierarchy(interposed=False), _hierarchy(interposed=True)
    interposing = evolve(direct, interposed)
    assert _verdict_on(interposing, _altered(interposing)) == _Verdict(_UNILATERAL, False)
    flattening = evolve(interposed, direct)
    assert _verdict_on(flattening, _altered(flattening)) == _Verdict((_AUTHORING,), False)


def test_a_departing_position_takes_its_required_members_off_rows_that_stay() -> None:
    # An abstract position stores nothing of its own, so its removal leaves the
    # members it handed down in the descendant's Table: a required one still
    # rejects every later write that omits the value nothing now describes. The
    # nullable case above stops at the authoring surface.
    interposed = _hierarchy(interposed=True, declares=attribute(_BRANCH, "issuer", type=STRING))
    flattening = evolve(interposed, _hierarchy(interposed=False))
    assert _verdict_on(flattening, _altered(flattening)) == _Verdict(_BOTH, False)


_SIBLING = identity("Bill")
_OTHER_ROOT = identity("Security")
_OTHER_LEAF = identity("Share")


def _branch_family(
    *declares: AttributeMetadata,
    under: EntityIdentity | None,
    holds: tuple[ValueObjectOccurrenceDeclaration, ...],
    leaf_under: EntityIdentity,
    concrete: bool = False,
) -> Metamodel:
    """A legal table-per-hierarchy family: root ``Instrument``, a member-less
    abstract ``Bill``, a ``Note`` declaring ``declares`` and ``holds`` beneath
    ``under``, and the family's one concrete subtype ``Bond`` beneath
    ``leaf_under``. ``Note`` is abstract unless ``concrete`` gives it a tag value
    of its own."""
    root = Declaration(
        identity=_ROOT,
        container=Table("instrument"),
        attributes=(key(_ROOT),),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    sibling = Declaration(
        identity=_SIBLING, inheritance=AbstractSubtype(ExactEntityReference(_ROOT))
    )
    parent = ExactEntityReference(under or _ROOT)
    branch = Declaration(
        identity=_BRANCH,
        attributes=declares,
        value_objects=holds,
        inheritance=ConcreteSubtype(parent, "NOTE") if concrete else AbstractSubtype(parent),
    )
    leaf = Declaration(
        identity=_LEAF,
        attributes=(attribute(_LEAF, "coupon"),),
        inheritance=ConcreteSubtype(ExactEntityReference(leaf_under), "BOND"),
    )
    return form_metamodel(source(root, sibling, branch, leaf))


def _rowless_branch(
    *declares: AttributeMetadata,
    under: EntityIdentity | None = None,
    holds: tuple[ValueObjectOccurrenceDeclaration, ...] = (),
    concrete: bool = False,
) -> Metamodel:
    """The family with ``Bond`` hanging off the root, so ``Note`` resolves to an
    EMPTY effective concrete set while the family stays legal. ``under`` places
    ``Note`` beneath the member-less abstract ``Bill`` instead of the root, and
    ``concrete`` turns ``Note`` itself into the shape it denotes."""
    return _branch_family(*declares, under=under, holds=holds, leaf_under=_ROOT, concrete=concrete)


def _rowful_branch(
    *declares: AttributeMetadata, holds: tuple[ValueObjectOccurrenceDeclaration, ...] = ()
) -> Metamodel:
    """The same family with ``Bond`` hanging off ``Note``, which therefore
    denotes ``Bond``'s stored shape."""
    return _branch_family(*declares, under=None, holds=holds, leaf_under=_BRANCH)


def test_a_position_composing_no_concrete_subtype_has_no_row_to_answer_for() -> None:
    # Only concrete subtypes own rows. A required member arriving on a position
    # that composes none has no stored row to backfill and no insert to
    # invalidate, so it asks for nothing; cutting it back out leaves no
    # surviving shape demanding a value, and stops at the authoring surface a
    # read of the position still occupies.
    issuer = attribute(_BRANCH, "issuer", type=STRING)
    bare, declaring = _rowless_branch(), _rowless_branch(issuer)
    assert _verdict(bare, declaring) == _Verdict(_UNILATERAL, False)
    assert _verdict(declaring, bare) == _Verdict((_AUTHORING,), False)


def test_a_flag_moving_where_no_write_names_a_target_withdraws_no_input() -> None:
    # A ReadWrite family is not a write surface on its own: a write names a
    # concrete target, and this position resolves to none.
    editable = attribute(_BRANCH, "issuer", type=STRING)
    assert _verdict(
        _rowless_branch(editable), _rowless_branch(dataclasses.replace(editable, read_only=True))
    ) == _Verdict(_UNILATERAL, False)


def test_a_rowless_position_holds_no_value_a_domain_change_can_reach() -> None:
    # Contracting a member's admitted domain is a claim about values already
    # stored and about the shape a later write must be accepted in; expanding it
    # is a claim about what a later writer may store an earlier reader cannot
    # admit. Neither claim has a subject here, for a scalar Attribute, a Value
    # Object occurrence, and a Value Object leaf alike.
    required = attribute(_BRANCH, "issuer", type=STRING)
    optional = dataclasses.replace(required, nullable=True)
    assert _verdict(_rowless_branch(required), _rowless_branch(optional)) == _Verdict(
        _UNILATERAL, False
    )
    assert _verdict(_rowless_branch(optional), _rowless_branch(required)) == _Verdict(
        _UNILATERAL, False
    )
    absent = dataclasses.replace(_TERMS, nullable=True)
    assert _verdict(_rowless_branch(holds=(_TERMS,)), _rowless_branch(holds=(absent,))) == _Verdict(
        _UNILATERAL, False
    )
    leaf = ValueObjectAttributeDeclaration("tenor", type=STRING)
    filled = dataclasses.replace(
        _TERMS, shape=dataclasses.replace(_TERMS.shape, attributes=(leaf,))
    )
    assert _verdict(_rowless_branch(holds=(_TERMS,)), _rowless_branch(holds=(filled,))) == _Verdict(
        _UNILATERAL, False
    )


def test_a_rowless_position_leaves_a_branch_no_narrowing_ever_came_through() -> None:
    # A Subtype Selection resolving to the empty set is rejected, so nothing
    # narrowed through `Bill` to reach `Note`. Flattening `Note` back out from
    # under a member-less `Bill` therefore invalidates no authored shape, where
    # the same flattening of a position owning rows invalidates the narrowing.
    beneath, flattened = _rowless_branch(under=_SIBLING), _rowless_branch()
    flattening = evolve(beneath, flattened)
    assert _verdict_on(flattening, _altered(flattening)) == _Verdict(_UNILATERAL, False)


def _across_roots(
    *, moved: bool, leaf_under: EntityIdentity | None = None, concrete: bool = False
) -> Metamodel:
    """Two live table-per-hierarchy families with distinct Tables and tag
    Columns, with ``Note`` under one root or the other and the concrete ``Bond``
    beneath ``leaf_under``, defaulting to the first root. ``Note`` is abstract
    unless ``concrete`` gives it a tag value of its own."""
    return form_metamodel(
        source(
            Declaration(
                identity=_ROOT,
                container=Table("instrument"),
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=_LEAF,
                attributes=(attribute(_LEAF, "coupon"),),
                inheritance=ConcreteSubtype(ExactEntityReference(leaf_under or _ROOT), "BOND"),
            ),
            Declaration(
                identity=_OTHER_ROOT,
                container=Table("security"),
                attributes=(key(_OTHER_ROOT, "ref"),),
                inheritance=AbstractRoot(TablePerHierarchy("sort")),
            ),
            Declaration(
                identity=_OTHER_LEAF,
                attributes=(attribute(_OTHER_LEAF, "units"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_OTHER_ROOT), "SHARE"),
            ),
            Declaration(
                identity=_BRANCH,
                inheritance=(
                    ConcreteSubtype(_moved_parent(moved), "NOTE")
                    if concrete
                    else AbstractSubtype(_moved_parent(moved))
                ),
            ),
        )
    )


def _moved_parent(moved: bool) -> ExactEntityReference:
    return ExactEntityReference(_OTHER_ROOT if moved else _ROOT)


def test_a_rowless_position_moving_between_families_carries_no_data_across() -> None:
    # The move changes the position's Table, strategy tag Column, and applicable
    # members at once. It owns no row for the Table change to transform, so the
    # database is not asked for anything — but a read of the position addressed
    # the family key it leaves behind, which is an authoring surface change.
    moving = evolve(_across_roots(moved=False), _across_roots(moved=True))
    assert _verdict_on(moving, _altered(moving)) == _Verdict((_AUTHORING,), False)


def test_a_position_arriving_in_a_family_as_a_shape_leaves_its_own_behind() -> None:
    # Turning `Note` concrete under the root it did not have places its
    # discriminator value in a Table this position never sat in, so the shape
    # arrives in that family exactly as an added subtype does. Every root
    # declares the one primary key of its family, so the root this position
    # leaves always takes back a member a read of it addressed: a cross-family
    # arrival requires the authoring surface whatever its new role is, which is
    # why its overlap visibility is never published however its own verdict
    # reads. This assertion is the guard on that — a unilateral verdict here
    # would mean the rule had become publicly reachable and needs a case.
    joining = evolve(_across_roots(moved=False), _across_roots(moved=True, concrete=True))
    assert _verdict_on(joining, _altered(joining)) == _Verdict((_AUTHORING,), False)


def _altered_on(evolution: Evolution, entity: EntityIdentity) -> EvolutionOperation:
    (operation,) = [
        candidate
        for candidate in evolution.operations
        if isinstance(candidate, EntityAltered) and candidate.entity == entity
    ]
    return operation


def test_a_member_leaving_a_position_its_shape_also_leaves_demands_no_backfill() -> None:
    # The stored shape a removal speaks about is the one the position keeps: with
    # `Bond` reparented out from under `Note` in the same edition, no `Note`
    # denotes a row that still demands `issuer`, so the removal stops at the
    # authoring surface a read of the position occupies. `Bond` is where the loss
    # of a required member off rows that stay IS reported, and it carries both.
    issuer = attribute(_BRANCH, "issuer", type=STRING)
    departing = evolve(_rowful_branch(issuer), _rowless_branch())
    (removed,) = [
        operation for operation in departing.operations if not isinstance(operation, EntityAltered)
    ]
    assert _verdict_on(departing, removed) == _Verdict((_AUTHORING,), False)
    assert _verdict_on(departing, _altered_on(departing, _LEAF)) == _Verdict(_BOTH, False)


def test_a_member_arriving_where_the_shape_departs_has_no_row_to_backfill() -> None:
    # The addition's mirror: the rows `Note` denoted leave it in the same edition
    # the required `issuer` arrives, so there is neither a row to backfill nor an
    # insert the later model still demands the value of.
    issuer = attribute(_BRANCH, "issuer", type=STRING)
    arriving = evolve(_rowful_branch(), _rowless_branch(issuer))
    (added,) = [
        operation for operation in arriving.operations if not isinstance(operation, EntityAltered)
    ]
    assert _verdict_on(arriving, added) == _Verdict(_UNILATERAL, False)


def test_a_domain_change_reaches_only_the_shape_the_position_keeps() -> None:
    # Contracting the domain claims something about values already stored under
    # the position and about a write the later edition must still accept;
    # expanding it claims something about a value a later writer may store where
    # an earlier reader reads. Neither claim survives the shape leaving.
    optional = dataclasses.replace(attribute(_BRANCH, "issuer", type=STRING), nullable=True)
    required = dataclasses.replace(optional, nullable=False)
    for earlier, later in ((optional, required), (required, optional)):
        changing = evolve(_rowful_branch(earlier), _rowless_branch(later))
        (altered,) = [
            operation
            for operation in changing.operations
            if not isinstance(operation, EntityAltered)
        ]
        assert _verdict_on(changing, altered) == _Verdict(_UNILATERAL, False)


def test_an_expansion_with_no_later_writer_is_visible_to_nobody() -> None:
    # Overlap visibility is a claim about a LATER writer placing a value an
    # earlier reader cannot admit, so a family the later edition holds read-only
    # names none, however many rows it denotes.
    assert _verdict(_sealed(_member()), _sealed(_member(nullable=True))) == _Verdict(
        _UNILATERAL, False
    )


def test_a_position_the_rows_leave_carries_no_data_to_the_family_it_joins() -> None:
    # The rowful case of the move above: `Note` denotes `Bond` before the move
    # and nothing after it, because `Bond` stays behind under the old root. No
    # `Note`-denoted row crosses to the other Table, so the changed Table,
    # strategy tag Column, and family key are an authoring surface change alone.
    moving = evolve(_across_roots(moved=False, leaf_under=_BRANCH), _across_roots(moved=True))
    assert _verdict_on(moving, _altered_on(moving, _BRANCH)) == _Verdict((_AUTHORING,), False)


_READING = identity("Reading")

_WIDGET_ONLY = Declaration(
    identity=_WIDGET, container=Table("widget"), attributes=(key(_WIDGET), _LABEL)
)


def _timestamped(name: str) -> AttributeMetadata:
    return attribute(_READING, name, type=TIMESTAMP)


def _reading(
    *, axis: tuple[str, str] | None, endpoints: tuple[str, ...] = ("openedAt", "closedAt")
) -> Declaration:
    """A `Reading` Entity declaring ``endpoints`` as Timestamps, carrying a
    Transaction-Time axis over ``axis`` when one is named.

    None of the candidate endpoint names is a conventional temporal one: a
    declared axis reserves those for its own endpoints, so an Entity that could
    move its axis between two pairs may bear neither.
    """
    return Declaration(
        identity=_READING,
        container=Table("reading"),
        attributes=(key(_READING), *(_timestamped(name) for name in endpoints)),
        as_of_axes=(
            ()
            if axis is None
            else (
                AsOfAxisMetadata(
                    TemporalDimension.TRANSACTION_TIME,
                    AttributeIdentity(_READING, axis[0]),
                    AttributeIdentity(_READING, axis[1]),
                ),
            )
        ),
    )


def _beside_widget(*declarations: Declaration) -> Metamodel:
    return form_metamodel(source(_WIDGET_ONLY, *declarations))


def test_an_axis_on_an_existing_entity_needs_the_surface_and_the_database() -> None:
    # The axis changes the temporal operation surface and the framework ownership
    # of its endpoints, and it moves the derived physical key and the bounds
    # existing rows must carry. Removal is not the mirror of a member removal
    # that leaves a Column behind: the key the Entity keeps is NARROWER than the
    # one its stored history was written under, so that history collides beneath
    # the later identity and the direction is symmetric after all.
    without = _beside_widget(_reading(axis=None))
    with_axis = _beside_widget(_reading(axis=("openedAt", "closedAt")))
    added = evolve(without, with_axis)
    assert _verdict_on(added, _axis_operation(added)) == _Verdict(_BOTH, False)
    removed = evolve(with_axis, without)
    assert _verdict_on(removed, _axis_operation(removed)) == _Verdict(_BOTH, False)


def test_an_axis_alteration_needs_the_surface_and_the_database() -> None:
    # Endpoint Attributes reach a descriptor framework-fixed, so a surviving axis
    # naming different ones is reachable only through the `m-metamodel` seam.
    pair = ("openedAt", "closedAt", "seenAt", "goneAt")
    moved = evolve(
        _beside_widget(_reading(axis=("openedAt", "closedAt"), endpoints=pair)),
        _beside_widget(_reading(axis=("seenAt", "goneAt"), endpoints=pair)),
    )
    assert _verdict_on(moved, _axis_operation(moved)) == _Verdict(_BOTH, False)


def test_an_axis_on_a_wholly_new_entity_is_carried_by_its_parent_addition() -> None:
    # A new Entity creates a complete empty Table, so its axis needs neither a
    # surface change nor a migration and is not described on its own at all.
    arriving = evolve(_beside_widget(), _beside_widget(_reading(axis=("openedAt", "closedAt"))))
    assert [type(operation) for operation in arriving.operations] == [EntityAdded]
    assert isinstance(arriving, UnilateralEvolution)


def _arriving_family() -> Metamodel:
    """A table-per-hierarchy family beside the standalone `Widget`."""
    return _beside_widget(
        Declaration(
            identity=_ROOT,
            container=Table("instrument"),
            attributes=(key(_ROOT),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_LEAF,
            attributes=(attribute(_LEAF, "coupon"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "BOND"),
        ),
    )


def test_a_family_arriving_whole_is_visible_to_no_earlier_reader() -> None:
    # Overlap visibility is a claim about an EARLIER edition: a later writer
    # placing a discriminator value in a shared Table an earlier reader cannot
    # admit. A family the earlier model holds no position of has neither that
    # Table nor a selection through it, so its concrete subtype's addition is
    # visible to nobody however the family stores its positions.
    evolution = evolve(_beside_widget(), _arriving_family())
    (added,) = [
        operation
        for operation in evolution.operations
        if isinstance(operation, ConcreteSubtypeAdded)
    ]
    assert _verdict_on(evolution, added) == _Verdict(_UNILATERAL, False)


def _tagged_family(*, persistence: PersistenceMode, leaves: tuple[str, ...]) -> Metamodel:
    """A table-per-hierarchy family under *persistence*, holding one concrete
    subtype per name in *leaves*."""
    return _beside_widget(
        Declaration(
            identity=_ROOT,
            container=Table("instrument"),
            attributes=(key(_ROOT),),
            persistence=persistence,
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        *(
            Declaration(
                identity=identity(leaf),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), leaf.upper()),
            )
            for leaf in leaves
        ),
    )


@pytest.mark.parametrize(
    ("persistence", "overlap_visible"),
    ((PersistenceMode.READ_WRITE, True), (PersistenceMode.READ_ONLY, False)),
)
def test_a_subtype_joining_a_read_only_family_has_no_writer_to_be_seen_by(
    persistence: PersistenceMode, overlap_visible: bool
) -> None:
    # The risk is a LATER WRITER placing a discriminator value in the shared
    # Table that an earlier reader cannot admit. A family the later edition holds
    # read-only admits no such writer, so the same addition under the same
    # strategy is visible only where writes are.
    evolution = evolve(
        _tagged_family(persistence=persistence, leaves=("Bond",)),
        _tagged_family(persistence=persistence, leaves=("Bond", "Swap")),
    )
    (added,) = [
        operation
        for operation in evolution.operations
        if isinstance(operation, ConcreteSubtypeAdded)
    ]
    assert _verdict_on(evolution, added) == _Verdict(_UNILATERAL, overlap_visible)


def _axis_operation(evolution: Evolution) -> EvolutionOperation:
    (operation,) = [
        candidate
        for candidate in evolution.operations
        if isinstance(candidate, AsOfAxisAdded | AsOfAxisAltered | AsOfAxisRemoved)
    ]
    return operation
