"""A derived Physical Index Name two definitions share (m-schema-delta), Docker-free.

A 128-bit fingerprint collision is a defensive backstop, not a control path: no
accepted model reaches it, and the fingerprint is stubbed here because that is
the only way to reach the branch at all. What the tests pin is the REPORT — that
a clash is refused rather than silently renamed, and that the refusal names every
group, every definition in it, and where each definition occurs.
"""

from __future__ import annotations

import pytest
from _inheritance_family_support import entity_with_two_indices_over_one_column

from parallax.core.base import STRING
from parallax.core.dialect import POSTGRES, PhysicalIndexName
from parallax.core.metamodel import AttributeIdentity, Column, EntityIdentity, IndexIdentity, Table
from parallax.evolution.model_evolution import ABSENT, evolve
from parallax.evolution.schema_delta import (
    IndexPresence,
    PhysicalIndexNameCollisionError,
    schema_delta,
)
from parallax.evolution.schema_delta import _naming as naming
from parallax.evolution.schema_delta._naming import collision_groups
from parallax.evolution.schema_delta._physical import IndexDefinition, PhysicalColumn

_ENTITY = EntityIdentity(namespace="parallax.test", name="Widget")
_OTHER = EntityIdentity(namespace="parallax.test", name="Gadget")


def _definition(entity: EntityIdentity, index: str, *, unique: bool = False) -> IndexDefinition:
    return IndexDefinition(
        table=Table(name=entity.name.lower()),
        index=IndexIdentity(entity, index),
        components=(AttributeIdentity(entity, "code"),),
        columns=(PhysicalColumn(Column(name="code"), STRING, 8, nullable=True),),
        unique=unique,
    )


_SHARED = PhysicalIndexName("pxi_widget_code_00000000000000000000000000000000")


def test_two_definitions_deriving_one_name_are_reported_as_a_group() -> None:
    widget = _definition(_ENTITY, "widget_code")
    gadget = _definition(_OTHER, "gadget_code", unique=True)
    (group,) = collision_groups({widget: _SHARED, gadget: _SHARED}, [], [widget, gadget])
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
    assert (
        collision_groups(
            {widget: _SHARED, gadget: PhysicalIndexName("pxi_gadget_code_1")}, [], [widget, gadget]
        )
        == ()
    )


def test_each_definition_names_the_endpoints_it_occurs_in() -> None:
    # A clash may involve an Index the delta drops, one it creates, and one that
    # survives unchanged; the report says which, so a reader can tell an
    # already-deployed name apart from one about to be created.
    dropped = _definition(_ENTITY, "a_dropped")
    created = _definition(_ENTITY, "b_created")
    surviving = _definition(_ENTITY, "c_surviving")
    (group,) = collision_groups(
        {dropped: _SHARED, created: _SHARED, surviving: _SHARED},
        [dropped, surviving],
        [created, surviving],
    )
    assert [definition.presence for definition in group.definitions] == [
        IndexPresence.EARLIER,
        IndexPresence.LATER,
        IndexPresence.BOTH,
    ]


def test_groups_are_reported_in_physical_index_name_order() -> None:
    first = PhysicalIndexName("pxi_aaa_0")
    second = PhysicalIndexName("pxi_bbb_0")
    definitions = {
        _definition(_ENTITY, "one"): second,
        _definition(_OTHER, "two"): second,
        _definition(_ENTITY, "three"): first,
        _definition(_OTHER, "four"): first,
    }
    groups = collision_groups(definitions, [], list(definitions))
    assert [group.name for group in groups] == [first, second]


def test_a_generated_delta_refuses_a_collision_rather_than_renaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reaching the backstop needs the fingerprint to stop distinguishing, which
    # only a stub can do. What the generator must then NOT do is pick a different
    # name for one of them: a definition's name is its own.
    def _one_fingerprint(definition: IndexDefinition) -> str:
        del definition
        return "0" * 32

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
