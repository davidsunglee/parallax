"""The execution-owned view schema: interning, guard splitting, and translation.

Three claims. **Interning** is what keeps the schema's cost a function of the
plan rather than of the graph: two concretes no guard splits are answered one
layout object, and a guard is the only thing that gives them different ones.
**The union** is what a merged logical node's row is laid out by — every source
layout its concrete has, in the member layout's own canonical order, fixed before
the node's first projection is walked. **The translation** is how a projection's
own row reaches that union, once, where the merged row is built.

The schema is stated over the animal corpus model throughout, because it is the
one that carries a polymorphic family a guard can actually split.
"""

from __future__ import annotations

import pytest
from _corpus_model_support import model as corpus_model

from parallax.core.entity._layout import EntityLayout, LayoutCatalog
from parallax.core.metamodel import EntityIdentity, Metamodel, RelationshipIdentity
from parallax.snapshot.materialize._views import (
    ROOT_LEVEL,
    ChildSlot,
    RelationshipViewKey,
    ViewSchema,
)

_NAMESPACE = "parallax.compatibility"

_ANIMAL = corpus_model("animal")


def _identity(name: str) -> EntityIdentity:
    return EntityIdentity(_NAMESPACE, name)


def _layout(name: str, model: Metamodel = _ANIMAL) -> EntityLayout:
    return LayoutCatalog(model).entity(_identity(name))


def _key(entity: str, name: str, narrowed: str | None = None) -> RelationshipViewKey:
    return RelationshipViewKey(RelationshipIdentity(_identity(entity), name), narrowed)


_OWNER = _key("Animal", "owner")
_OWNER_NARROWED = _key("Animal", "owner", "owner[Person]")
_ANIMALS = _key("Person", "animals")
_PETS = _key("Person", "pets")


# --------------------------------------------------------------------------- #
# Interning and guard splitting.                                              #
# --------------------------------------------------------------------------- #
def test_two_concretes_no_guard_splits_share_one_source_layout() -> None:
    # The concrete axis is degenerate on an unguarded level, so every concrete of
    # a polymorphic family is laid out by the one object — which is what keeps
    # the schema's retained size a function of the plan and not of the family.
    schema = ViewSchema.of(_OWNER)
    dog = schema.source(ROOT_LEVEL, _layout("Dog"))
    assert schema.source(ROOT_LEVEL, _layout("Cat")) is dog
    assert schema.source(ROOT_LEVEL, _layout("WildBoar")) is dog
    assert dog.slots == (_OWNER,)


def test_a_guard_splits_two_concretes_into_layouts_of_different_widths() -> None:
    # A path-root guard selects parents by their own resolved concrete, so the
    # excluded one holds no slot at all rather than an empty one: unloaded is
    # what "this object never participated" spells.
    schema = ViewSchema(
        ((ChildSlot(_OWNER), ChildSlot(_OWNER_NARROWED, frozenset({_identity("Dog")}))),)
    )
    dog = schema.source(ROOT_LEVEL, _layout("Dog"))
    cat = schema.source(ROOT_LEVEL, _layout("Cat"))
    assert dog is not cat
    assert dog.slots == (_OWNER, _OWNER_NARROWED)
    assert cat.slots == (_OWNER,)
    assert schema.source(ROOT_LEVEL, _layout("WildBoar")) is cat


def test_two_levels_attaching_one_view_key_share_that_key_s_slot() -> None:
    # A guarded path and its broad sibling are distinct hops filling the same
    # view. One view is one slot, so the later hop overwrites rather than
    # occupying a second position no reader could tell from the first.
    schema = ViewSchema(((ChildSlot(_OWNER), ChildSlot(_OWNER, frozenset({_identity("Dog")}))),))
    assert schema.source(ROOT_LEVEL, _layout("Dog")).slots == (_OWNER,)


def test_a_source_layout_is_answered_identically_on_a_second_reach() -> None:
    schema = ViewSchema.of(_OWNER)
    layout = _layout("Dog")
    assert schema.source(ROOT_LEVEL, layout) is schema.source(ROOT_LEVEL, layout)


def test_a_concrete_no_slot_admits_carries_an_empty_row() -> None:
    # Building on demand degrades gracefully: a concrete nothing enumerated is
    # laid out for rather than failed on, and what it is laid out is nothing.
    schema = ViewSchema(((ChildSlot(_OWNER, frozenset({_identity("Dog")})),),))
    assert schema.source(ROOT_LEVEL, _layout("Cat")).slots == ()
    assert schema.merged(_layout("Cat")).slots == ()


def test_a_schema_lays_out_no_row_for_a_source_level_its_plan_never_had() -> None:
    with pytest.raises(ValueError, match="1 source levels"):
        ViewSchema.of(_OWNER).source(1, _layout("Dog"))


# --------------------------------------------------------------------------- #
# The merged union and the translation into it.                               #
# --------------------------------------------------------------------------- #
def test_a_merged_layout_is_the_union_of_a_concretes_source_layouts() -> None:
    # A node projected at one level still carries the slots its concrete can
    # receive at every other, because the width is fixed before the first
    # projection of that node is walked and a second level widens nothing.
    schema = ViewSchema(((ChildSlot(_PETS),), (ChildSlot(_ANIMALS),)))
    merged = schema.merged(_layout("Person"))
    assert merged.slots == (_ANIMALS, _PETS)
    assert dict(merged.index_of) == {_ANIMALS: 0, _PETS: 1}


def test_the_union_is_in_the_member_layouts_canonical_order_not_the_plans() -> None:
    # `animals` is declared before `pets`, so the union states them in that order
    # whichever level reached which — the same rule the merge walks slots by.
    forward = ViewSchema(((ChildSlot(_ANIMALS),), (ChildSlot(_PETS),)))
    backward = ViewSchema(((ChildSlot(_PETS),), (ChildSlot(_ANIMALS),)))
    assert forward.merged(_layout("Person")).slots == backward.merged(_layout("Person")).slots


def test_to_merged_carries_every_source_slot_to_the_position_its_key_holds() -> None:
    schema = ViewSchema(((ChildSlot(_PETS),), (ChildSlot(_ANIMALS),)))
    layout = _layout("Person")
    merged = schema.merged(layout)
    for level, translation in enumerate(merged.to_merged):
        source = schema.source(level, layout)
        assert translation == tuple(merged.index_of[view] for view in source.slots)
        assert tuple(merged.slots[slot] for slot in translation) == source.slots
    assert merged.to_merged == ((1,), (0,))


def test_a_guarded_concretes_translation_omits_the_slot_it_never_receives() -> None:
    schema = ViewSchema(
        ((ChildSlot(_OWNER), ChildSlot(_OWNER_NARROWED, frozenset({_identity("Dog")}))),)
    )
    assert schema.merged(_layout("Dog")).to_merged == ((0, 1),)
    assert schema.merged(_layout("Cat")).to_merged == ((0,),)


def test_a_merged_layout_is_answered_identically_on_a_second_reach() -> None:
    # Every node of one concrete shares the one layout, which is what makes a
    # merge's per-node view layout a reference rather than a derivation.
    schema = ViewSchema.of(_OWNER)
    assert schema.merged(_layout("Dog")) is schema.merged(_layout("Dog"))
