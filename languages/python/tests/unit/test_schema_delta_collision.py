"""A derived Physical Index Name two definitions share (m-schema-delta), Docker-free.

A 128-bit fingerprint collision is a defensive backstop, not a control path: no
accepted model reaches it, and the fingerprint is stubbed here because that is
the only way to reach the branch at all. What the tests pin is the REPORT — that
a clash is refused rather than silently renamed, and that the refusal names every
group, every definition in it, and where each definition occurs.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest
from _corpus_model_support import formed
from _inheritance_family_support import entity_with_two_indices_over_one_column

from parallax.core.base import STRING
from parallax.core.dialect import POSTGRES, Dialect, PhysicalIndexName
from parallax.core.metamodel import AttributeIdentity, Column, EntityIdentity, IndexIdentity, Table
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor._records import Attribute, Entity, Index, Metamodel
from parallax.evolution.model_evolution import ABSENT, UnilateralEvolution, evolve
from parallax.evolution.schema_delta import (
    CollisionGroup,
    IndexPresence,
    PhysicalIndexNameCollisionError,
    schema_delta,
)
from parallax.evolution.schema_delta import _naming as naming
from parallax.evolution.schema_delta._naming import NamedIndex, collision_groups
from parallax.evolution.schema_delta._physical import IndexDefinition, PhysicalColumn

_ENTITY = EntityIdentity(namespace="parallax.test", name="Widget")
_OTHER = EntityIdentity(namespace="parallax.test", name="Gadget")


def _definition(
    entity: EntityIdentity, index: str, *, unique: bool = False, table: str | None = None
) -> IndexDefinition:
    return IndexDefinition(
        table=Table(name=table or entity.name.lower()),
        index=IndexIdentity(entity, index),
        components=(AttributeIdentity(entity, "code"),),
        columns=(PhysicalColumn(Column(name="code"), STRING, 8, nullable=True),),
        unique=unique,
    )


_SHARED = PhysicalIndexName("pxi_widget_code_00000000000000000000000000000000")


def _entry(
    definition: IndexDefinition,
    name: PhysicalIndexName = _SHARED,
    presence: IndexPresence = IndexPresence.LATER,
) -> NamedIndex:
    return NamedIndex(name=name, definition=definition, presence=presence)


def _groups(entries: Sequence[NamedIndex]) -> tuple[CollisionGroup, ...]:
    """``entries`` grouped with every Table they name carried into the later model."""
    return collision_groups(entries, {entry.definition.table for entry in entries})


def test_two_definitions_deriving_one_name_are_reported_as_a_group() -> None:
    widget = _definition(_ENTITY, "widget_code")
    gadget = _definition(_OTHER, "gadget_code", unique=True)
    (group,) = _groups([_entry(widget), _entry(gadget)])
    assert group.name == _SHARED
    # Canonical logical-identity order: Gadget precedes Widget.
    assert [definition.index.entity.name for definition in group.definitions] == [
        "Gadget",
        "Widget",
    ]
    reported = group.definitions[0]
    assert reported.table == Table(name="gadget")
    assert reported.index == IndexIdentity(_OTHER, "gadget_code")
    assert reported.components == (AttributeIdentity(_OTHER, "code"),)
    assert reported.unique is True


def test_a_name_only_one_definition_derives_is_no_group() -> None:
    widget = _definition(_ENTITY, "widget_code")
    gadget = _definition(_OTHER, "gadget_code")
    assert _groups([_entry(widget), _entry(gadget, PhysicalIndexName("pxi_gadget_code_1"))]) == ()


def test_each_definition_names_the_endpoints_it_occurs_in() -> None:
    # A clash may involve an Index the delta drops, one it creates, and one that
    # survives unchanged; the report says which, so a reader can tell an
    # already-deployed name apart from one about to be created.
    dropped = _definition(_ENTITY, "a_dropped")
    created = _definition(_ENTITY, "b_created")
    surviving = _definition(_ENTITY, "c_surviving")
    (group,) = _groups(
        [
            _entry(dropped, presence=IndexPresence.EARLIER),
            _entry(created, presence=IndexPresence.LATER),
            _entry(surviving, presence=IndexPresence.BOTH),
        ]
    )
    assert [definition.presence for definition in group.definitions] == [
        IndexPresence.EARLIER,
        IndexPresence.LATER,
        IndexPresence.BOTH,
    ]


def test_groups_are_reported_in_physical_index_name_order() -> None:
    first = PhysicalIndexName("pxi_aaa_0")
    second = PhysicalIndexName("pxi_bbb_0")
    groups = _groups(
        [
            _entry(_definition(_ENTITY, "one"), second),
            _entry(_definition(_OTHER, "two"), second),
            _entry(_definition(_ENTITY, "three"), first),
            _entry(_definition(_OTHER, "four"), first),
        ]
    )
    assert [group.name for group in groups] == [first, second]


def test_a_name_freed_before_it_is_taken_again_is_no_collision() -> None:
    # Statements run Table by Table, so an Index dropped from `a` is gone before
    # anything on `z` is created and the two definitions are never objects in the
    # database at once. Refusing here would refuse a delta that is executable.
    freed = _definition(_ENTITY, "freed", table="a")
    taken = _definition(_OTHER, "taken", table="z")
    assert (
        _groups(
            [
                _entry(freed, presence=IndexPresence.EARLIER),
                _entry(taken, presence=IndexPresence.LATER),
            ]
        )
        == ()
    )


def test_a_name_taken_before_it_is_freed_is_a_collision() -> None:
    # The same pair with the Tables exchanged: `a`'s create runs before `z`'s
    # drop, so both definitions hold the one name at that prefix. Coexistence is
    # the test, and the emitted order is what decides it.
    taken = _definition(_OTHER, "taken", table="a")
    freed = _definition(_ENTITY, "freed", table="z")
    (group,) = _groups(
        [
            _entry(freed, presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ]
    )
    assert [entry.presence for entry in group.definitions] == [
        IndexPresence.LATER,
        IndexPresence.EARLIER,
    ]


def test_one_Table_creates_before_it_drops_so_its_own_pair_collides() -> None:
    # Within a Table an altered Index is created before its earlier definition is
    # dropped, so a dropped and a created definition there always overlap. This
    # is the collision a plan could never report: keyed by the shared name, it
    # emits neither statement.
    freed = _definition(_ENTITY, "freed")
    taken = _definition(_ENTITY, "taken")
    (group,) = _groups(
        [
            _entry(freed, presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ]
    )
    assert len(group.definitions) == 2


def test_a_name_on_a_Table_the_delta_leaves_behind_is_never_freed() -> None:
    # No statement drops an Index from a Table the later endpoint does not hold,
    # so that definition is present throughout and collides with anything created
    # under its name.
    stranded = _definition(_ENTITY, "stranded", table="a")
    taken = _definition(_OTHER, "taken", table="z")
    (group,) = collision_groups(
        [
            _entry(stranded, presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ],
        {taken.table},
    )
    assert len(group.definitions) == 2


def test_a_generated_delta_refuses_a_collision_rather_than_renaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reaching the backstop needs the fingerprint to stop distinguishing, which
    # only a stub can do. What the generator must then NOT do is pick a different
    # name for one of them: a definition's name is its own.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    with pytest.raises(PhysicalIndexNameCollisionError) as raised:
        schema_delta(evolve(ABSENT, entity_with_two_indices_over_one_column()), POSTGRES)
    error = raised.value
    assert error.dialect_identity == "postgres"
    (group,) = error.groups
    assert [definition.index.name for definition in group.definitions] == [
        "widget_code_uq",
        "widget_code_uq_dup",
    ]
    assert all(definition.presence is IndexPresence.LATER for definition in group.definitions)


def test_a_collision_with_an_index_the_delta_never_touches_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The check spans the Indices that COEXIST, not the ones a statement names.
    # An Index both editions declare is never created or dropped, and it is still
    # an object in the database while the new one is created beside it, so a name
    # it already holds is a name the delta cannot take.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    with pytest.raises(PhysicalIndexNameCollisionError) as raised:
        schema_delta(_gaining_a_second_index(), POSTGRES)
    (group,) = raised.value.groups
    assert [(entry.index.name, entry.presence) for entry in group.definitions] == [
        ("widget_code_uq", IndexPresence.BOTH),
        ("widget_code_uq_dup", IndexPresence.LATER),
    ]


def test_a_delta_that_frees_a_name_before_taking_it_is_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End to end on the pair the census must NOT refuse: `a` loses the Index and
    # `z` gains one deriving the same name. The drop runs first, so the name is
    # free when the create runs, and the generator owes the statements.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    delta = schema_delta(_moving_an_index("a", "z"), _ONE_NAME)
    assert delta.statements == (
        "drop index pxi_index_00000000000000000000000000000000",
        "create index pxi_index_00000000000000000000000000000000 on z (code)",
    )


def test_a_delta_that_takes_a_name_before_freeing_it_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same two Entities with their Tables exchanged. Now the create runs
    # first and the name is still held, so the delta is not executable and is
    # refused instead of emitted.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    with pytest.raises(PhysicalIndexNameCollisionError) as raised:
        schema_delta(_moving_an_index("z", "a"), _ONE_NAME)
    (group,) = raised.value.groups
    assert [(entry.table.name, entry.presence) for entry in group.definitions] == [
        ("a", IndexPresence.LATER),
        ("z", IndexPresence.EARLIER),
    ]


_ONE_NAME: Dialect = dataclasses.replace(POSTGRES, max_identifier_bytes=37)
"""A Dialect whose limit leaves no readable prefix, so with the fingerprint
stubbed every definition derives the one name ``pxi_index_<zeros>``."""


def _one_fingerprint(definition: IndexDefinition) -> str:
    del definition
    return "0" * 32


def _moving_an_index(earlier_table: str, later_table: str) -> UnilateralEvolution:
    """One authored Index dropped from one Table and declared on another."""
    evolution = evolve(_indexed(earlier_table), _indexed(later_table))
    assert isinstance(evolution, UnilateralEvolution)
    return evolution


def _indexed(table: str) -> AcceptedMetamodel:
    """Two Entities on Tables ``a`` and ``z``, only ``table`` declaring an Index."""
    return formed(
        Metamodel(
            entities=tuple(
                Entity(
                    name=name,
                    table=name[:1].lower(),
                    attributes=(
                        Attribute(name="id", type="int64", column="id", primary_key=True),
                        Attribute(name="code", type="string", column="code", max_length=8),
                    ),
                    indices=(
                        (Index(name="code_ix", attributes=("code",)),)
                        if name[:1].lower() == table
                        else ()
                    ),
                )
                for name in ("Anvil", "Zither")
            )
        )
    )


def _gaining_a_second_index() -> UnilateralEvolution:
    """Declaring a second Index beside one both endpoints already hold."""
    evolution = evolve(_widget_with_one_index(), entity_with_two_indices_over_one_column())
    assert isinstance(evolution, UnilateralEvolution)
    return evolution


def _widget_with_one_index() -> AcceptedMetamodel:
    """``entity_with_two_indices_over_one_column`` before the second Index."""
    return formed(
        Metamodel(
            entities=(
                Entity(
                    name="Widget",
                    table="widget",
                    attributes=(
                        Attribute(name="id", type="int64", column="id", primary_key=True),
                        Attribute(name="code", type="string", column="code", max_length=8),
                    ),
                    indices=(Index(name="widget_code_uq", attributes=("code",), unique=True),),
                ),
            )
        )
    )
