"""The publication plan, and the refusals that keep a published row well formed.

The parity corpus grades what a published value serializes to. This grades what
the shared positional row routine fills and refuses, the state a published value
keeps and does not keep, and where a published subtype reads what it inherits.
"""

from __future__ import annotations

import gc
from typing import Any, cast

import pytest

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
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._instance_state import (
    allocate,
    install,
    is_present,
    plan_of,
)
from parallax.core.entity._model import DomainModel
from parallax.core.entity._pydantic_storage import instance_presence
from parallax.core.metamodel import TablePerHierarchy
from tests.unit._indexed_graph_support import published_nodes
from tests.unit.core.entity._compact_support import carries_instance_storage, published, raw_row

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


# --------------------------------------------------------------------------- #
# The positional row, and what it refuses
# --------------------------------------------------------------------------- #


def test_a_required_member_publication_carried_no_value_for_reads_its_position() -> None:
    # Publication refuses no row for what it does not carry. A required member has
    # no declared default, so its position holds `None` — not a value the member
    # admits, and not one publication invented either: a read is entitled to carry
    # nothing there, and the presence bit beside it is what keeps that
    # distinguishable from a carried null.
    value = published(Cat, spot=None)
    assert (value.id, value.name) == (None, None)
    assert value.model_fields_set == {"spot"}


# `Cat`: id, name, owner_id, indoor, then the occurrences spot and perch; then
# the relationships friends and owner.
_PETS = DomainModel(Animal, Cat)


def test_each_position_lands_at_its_own_index_and_only_occurrences_are_built() -> None:
    # Absent keeps the template default with its bit clear; a carried null is a
    # value with its bit set; an unloaded relationship keeps the sentinel.
    value = published_nodes(
        _PETS, (Cat.identity, (1, None, ABSENT, True, (1.5,), ABSENT), ((), UNLOADED))
    )[0]
    row = raw_row(cast("Any", value))
    assert row is not None
    spot = row[5]
    assert type(spot) is Geo
    assert spot.lat == 1.5
    assert row == (0b011011, 1, None, None, True, spot, None, (), UNLOADED)
    assert cast("Any", value).model_fields_set == {"id", "name", "indoor", "spot"}


def test_a_plan_whose_members_are_not_the_class_s_fields_is_refused() -> None:
    with pytest.raises(ValueError, match="different sets"):
        install(Cat, members=("id",), occurrences={}, relationships=())


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
    # Not even a shared empty set: what a published value answers for
    # `__pydantic_fields_set__` is synthesized from the bitmap, so the slot
    # Pydantic's own storage keeps one in is never written at all. Storage is
    # asked for by identity, because a dictionary held in a slot of the layout's
    # own is not storage; the set scan stays layout-blind because that presence
    # slot is the only place in the layout a set ever reaches.
    value = published(Cat, id=1, name="c")
    row = raw_row(value)
    assert isinstance(row, tuple)
    assert row[0] == 0b000011
    assert value.model_fields_set == {"id", "name"}
    with pytest.raises(AttributeError):
        instance_presence(value)
    assert object.__getattribute__(value, "__pydantic_extra__") is None
    assert not any(isinstance(held, dict | set) for held in row)
    assert not carries_instance_storage(value)
    assert not [held for held in gc.get_referents(value) if isinstance(held, set)]


def test_a_shell_awaiting_publication_holds_neither_state_nor_presence() -> None:
    # The slot is unset rather than cleared until publication attaches the row,
    # and that is what a shell answers with: empty storage, and no
    # populated-member set at all — the two facts a refused publication leaves
    # behind.
    shell = allocate(Cat)
    assert shell.__dict__ == {}
    with pytest.raises(AttributeError):
        _ = shell.__pydantic_fields_set__


def test_presence_is_read_per_member_from_whichever_backing_holds_it() -> None:
    # The only presence question internal code has, and the one that allocates
    # nothing: both backings answer it from what they already hold, so a row or
    # document walk never synthesizes a set to ask it.
    bits = plan_of(Cat).bits
    for value in (published(Cat, id=1, name="c"), Cat(id=1, name="c")):
        assert is_present(value, bits["id"])
        assert is_present(value, bits["name"])
        assert not is_present(value, bits["indoor"])


def test_a_value_object_declaring_no_member_publishes_and_dumps_as_empty() -> None:
    # The degenerate width, which the permutation a plan carries has to spell
    # rather than build: `operator.itemgetter` refuses to be constructed with no
    # index at all.
    class Nothing(ValueObject):
        pass

    value = published(Nothing)
    assert value.model_dump() == Nothing().model_dump() == {}
    assert plan_of(Nothing).fields == ()


def test_a_published_relationship_reads_its_tail_position() -> None:
    friend = published(Cat, id=2, name="f")
    value = published(Cat, {"friends": (friend,), "owner": None}, id=1, name="c")
    assert value.friends == (friend,)
    assert value.owner is None


def test_a_published_subtype_reads_an_inherited_occurrence_at_its_own_position() -> None:
    # An occurrence sits after the exact class's own attributes, so `Cat` reads
    # the `spot` it inherits at a position `Animal` never laid out.
    spot = Geo(lat=1.5)
    value = published(Cat, id=1, name="c", indoor=True, spot=spot)
    assert value.spot == spot
    assert value.indoor is True
