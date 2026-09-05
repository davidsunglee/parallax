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
    ExactEntityReference,
    Metamodel,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    Table,
    TablePerHierarchy,
    TemporalDimension,
)
from parallax.evolution.model_evolution import (
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisRemoved,
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
    # required one has no default and backfill contract to satisfy them with.
    assert _verdict(_holding(), _holding(_member(nullable=True))) == _Verdict(_UNILATERAL, False)
    assert _verdict(_holding(), _holding(_member())) == _Verdict((_MIGRATION,), False)


def test_a_member_removal_needs_the_authoring_surface_whatever_it_declared() -> None:
    # The Column may simply be left in place, so removal never reaches the
    # database — and a nullable member is no more removable than a required one.
    assert _verdict(_holding(_member(nullable=True)), _holding()) == _Verdict((_AUTHORING,), False)


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


def _hierarchy(*, interposed: bool) -> Metamodel:
    """A table-per-hierarchy family whose concrete leaf extends the root
    directly, or extends an abstract position interposed under it."""
    root = Declaration(
        identity=_ROOT,
        container=Table("instrument"),
        attributes=(key(_ROOT),),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    branch = Declaration(
        identity=_BRANCH,
        attributes=(dataclasses.replace(attribute(_BRANCH, "memo", type=STRING), nullable=True),),
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
    # existing rows must carry. Removing one leaves those physical facts where
    # they are, so it needs the authoring surface alone.
    without = _beside_widget(_reading(axis=None))
    with_axis = _beside_widget(_reading(axis=("openedAt", "closedAt")))
    added = evolve(without, with_axis)
    assert _verdict_on(added, _axis_operation(added)) == _Verdict(_BOTH, False)
    removed = evolve(with_axis, without)
    assert _verdict_on(removed, _axis_operation(removed)) == _Verdict((_AUTHORING,), False)


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


def _axis_operation(evolution: Evolution) -> EvolutionOperation:
    (operation,) = [
        candidate
        for candidate in evolution.operations
        if isinstance(candidate, AsOfAxisAdded | AsOfAxisAltered | AsOfAxisRemoved)
    ]
    return operation
