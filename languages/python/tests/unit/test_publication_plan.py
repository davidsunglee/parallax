"""The publication plan, and the refusals that keep a published row well formed.

The parity corpus grades what a published value serializes to. This grades what a
publication plan IS: the two index spaces a class fixes at creation, the order a
positional row is aligned to, the ordinal each descriptor is handed, and the four
refusals the one attachment door makes. It also pins the class-creation ORDERING
the plan depends on — descriptors installed once the class exists, never seeded
into the namespace Pydantic collects field defaults from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from _compact_support import published
from pydantic import BaseModel

from parallax.core.entity import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    UNLOADED,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Entity,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity._instance_state import (
    COMPACT_STATE_SLOT,
    allocate,
    install,
    plan_of,
    publish,
    serialization_schema,
)
from parallax.core.entity._members import Attr as AttrDescriptor
from parallax.core.metamodel import TablePerHierarchy

if TYPE_CHECKING:
    from pydantic_core import core_schema as cs

_NS = "plan"


class Geo(ValueObject):
    lat: Attr[float]


class Animal(
    Entity,
    table="animal",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    spot: Attr[Geo | None]
    name: Attr[str]
    owner_id: Attr[int | None]
    friends: Rel[tuple[Animal, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))
    owner: Rel[Animal | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))


class Cat(Animal, inheritance=ConcreteSubtype(tag_value="cat")):
    perch: Attr[Geo | None]
    indoor: Attr[bool | None]


def test_the_member_order_is_attributes_root_first_then_occurrences() -> None:
    # The order a positional construction row is aligned to, which is the order an
    # accepted Metamodel fixes for the same concrete: every contributor's
    # attributes root-first, then every contributor's occurrences the same way.
    # A class body may interleave the two, and this one does.
    assert plan_of(Animal).py_names == ("id", "name", "owner_id", "spot")
    assert plan_of(Cat).py_names == ("id", "name", "owner_id", "indoor", "spot", "perch")


def test_the_field_order_is_pydantic_s_own_and_is_not_the_member_order() -> None:
    # Repr, iteration, and serialization are stated over Pydantic's field order,
    # which follows the class body rather than the model's member categories. The
    # plan carries both because a class that declares an occurrence before an
    # attribute makes them differ.
    assert plan_of(Animal).fields == ("id", "spot", "name", "owner_id")
    assert plan_of(Cat).fields == ("id", "spot", "name", "owner_id", "perch", "indoor")


def test_a_bit_is_one_less_than_its_tuple_index_and_relationships_carry_none() -> None:
    plan = plan_of(Cat)
    assert dict(plan.indexes) == {py_name: bit + 1 for py_name, bit in plan.bits.items()}
    assert dict(plan.relationships) == {"friends": 7, "owner": 8}
    assert plan.template == (0, None, None, None, None, None, None, UNLOADED, UNLOADED)


def test_an_attribute_keeps_its_position_in_a_descendant_and_an_occurrence_does_not() -> None:
    # Ancestry contributes attributes root-first, so a root-declared attribute
    # indexes identically at every depth; an occurrence and a relationship both
    # sit after the exact class's own attribute count, which is a property of the
    # concrete rather than of the family. That is why a descendant installs its
    # own descriptor for every member it inherits.
    assert plan_of(Animal).indexes["id"] == plan_of(Cat).indexes["id"]
    assert plan_of(Animal).indexes["spot"] == 4
    assert plan_of(Cat).indexes["spot"] == 5
    assert plan_of(Animal).relationships["owner"] == 6
    assert plan_of(Cat).relationships["owner"] == 8


@pytest.mark.parametrize("py_name", ["id", "name", "owner_id", "spot", "friends", "owner"])
def test_every_inherited_member_has_a_descriptor_of_the_descendant_s_own(py_name: str) -> None:
    inherited = vars(Cat)[py_name]
    assert inherited is not vars(Animal)[py_name]
    plan = plan_of(Cat)
    expected = plan.indexes.get(py_name, plan.relationships.get(py_name))
    assert inherited._index == expected


def test_an_inherited_member_reads_the_declaring_entity_in_the_expression_it_seeds() -> None:
    # The descendant's descriptor is derived from the declaring class's own, so
    # the reference it hands out is unchanged: an inherited member spelled through
    # a subtype still emits the ancestor's identity on the wire.
    for py_name in ("name", "owner"):
        descendant = vars(Cat)[py_name]
        declaring = vars(Animal)[py_name]
        assert descendant._ref == declaring._ref


def test_a_descriptor_reachable_while_a_class_is_built_becomes_its_field_default() -> None:
    # The hazard the installation order exists to avoid, demonstrated rather than
    # described. Pydantic reads a field's default off the class under construction
    # with `getattr`, so a descriptor answering under a member's name at that
    # moment IS that member's default from then on.
    class _Seed:
        def __get__(self, obj: object | None, owner: type | None = None) -> str:
            return "a query seed"

    seeded = type("Seeded", (BaseModel,), {"__annotations__": {"name": str}, "name": _Seed()})
    assert cast("Any", seeded).__pydantic_fields__["name"].default == "a query seed"


@pytest.mark.parametrize("owner", [Animal, Cat])
def test_no_member_of_a_built_class_collected_a_descriptor_as_its_default(owner: type) -> None:
    # The other half: the engine installs every descriptor once the class exists,
    # so what each member collected is a value rather than what class access to it
    # answers. An inherited member is the case that broke — its descriptor is the
    # base's and answers for the name Pydantic reads.
    for py_name, field in cast("Any", owner).__pydantic_fields__.items():
        assert isinstance(vars(owner)[py_name], AttrDescriptor)
        assert field.is_required() or field.get_default(call_default_factory=True) is None


def test_the_plan_is_stamped_per_exact_class_and_never_shared() -> None:
    assert vars(Cat)["__parallax_plan__"] is not vars(Animal)["__parallax_plan__"]
    assert plan_of(Cat) is vars(Cat)["__parallax_plan__"]


def test_class_metadata_does_not_grow_with_published_instance_count() -> None:
    before = len(vars(Cat))
    values = [published(Cat, id=index, name="c") for index in range(50)]
    assert len(vars(Cat)) == before
    assert plan_of(Cat) is vars(Cat)["__parallax_plan__"]
    assert all(value.id == index for index, value in enumerate(values))


# --------------------------------------------------------------------------- #
# The one attachment door, and what it refuses
# --------------------------------------------------------------------------- #


def test_publication_carries_every_required_member_or_is_refused() -> None:
    with pytest.raises(ValueError, match="required id, name"):
        published(Cat, spot=None)


def test_a_member_no_class_declares_is_refused() -> None:
    with pytest.raises(ValueError, match="declares no member 'nope'"):
        published(Cat, id=1, name="c", nope=2)


def test_a_relationship_no_class_declares_is_refused() -> None:
    with pytest.raises(ValueError, match="declares no relationship 'nope'"):
        published(Cat, {"nope": None}, id=1, name="c")


def test_a_published_value_is_attached_exactly_once() -> None:
    value = published(Cat, id=1, name="c")
    with pytest.raises(ValueError, match="already published"):
        publish(value, {"id": 2, "name": "d"})
    assert value.id == 1


def test_a_refused_publication_leaves_the_shell_unattached() -> None:
    shell = allocate(Cat)
    with pytest.raises(ValueError, match="required"):
        publish(shell, {"id": 1})
    assert not hasattr(shell, COMPACT_STATE_SLOT)


def test_a_plan_whose_members_are_not_the_class_s_fields_is_refused() -> None:
    with pytest.raises(ValueError, match="different sets"):
        install(Cat, members=("id",), occurrences={}, relationships=())


def test_the_seam_leaves_a_schema_that_is_not_a_model_schema_alone() -> None:
    # The hook is the framework root's, so what reaches it is always the schema of
    # a model being built; leaving anything else untouched is what keeps that a
    # statement rather than an assumption.
    other = cast("cs.CoreSchema", {"type": "int"})
    assert serialization_schema(Cat, other) is other


# --------------------------------------------------------------------------- #
# Presence, equality, and the state a published value does not keep
# --------------------------------------------------------------------------- #


def test_two_values_differing_only_in_private_state_are_unequal() -> None:
    from pydantic import PrivateAttr

    class Kept(Entity, table="kept", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)

        _mark = PrivateAttr(default=0)

    first = published(Kept, id=1)
    second = published(Kept, id=1)
    assert first == second
    object.__setattr__(second, "__pydantic_private__", {"_mark": 9})
    assert first != second


def test_a_published_value_keeps_no_name_keyed_presence_state() -> None:
    value = published(Cat, id=1, name="c")
    row = object.__getattribute__(value, COMPACT_STATE_SLOT)
    assert isinstance(row, tuple)
    assert row[0] == 0b000011
    assert object.__getattribute__(value, "__pydantic_fields_set__") == set()
    assert object.__getattribute__(value, "__pydantic_extra__") is None
    assert not any(isinstance(held, dict | set) for held in cast("tuple[Any, ...]", row))


def test_a_published_relationship_reads_its_tail_position() -> None:
    friend = published(Cat, id=2, name="f")
    value = published(Cat, {"friends": (friend,), "owner": None}, id=1, name="c")
    assert value.friends == (friend,)
    assert value.owner is None
