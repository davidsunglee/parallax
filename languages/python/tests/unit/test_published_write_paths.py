"""Every write into a published value, and how each one ends.

A published value's declared state is one immutable row, presented under the two
names Pydantic reads instance state by. Reads are the easy half. A WRITE has
nowhere obvious to land: the mapping a caller reaches through ``__dict__`` is
built for that read and discarded with it, so a write into it would evaporate
and the next read would answer from the row as though nothing had happened.

Silently inert is the one outcome this seam may not have. So every write path
into a published value ends as either a deliberate demotion — the value becomes
an ordinary Pydantic-backed one holding the same members — or a loud refusal, and
this module is the enumeration. One test per path, named for the path, so a new
one arriving with a Pydantic release is a gap that reads as a gap.

The one path no in-process design closes is ``object.__setattr__``, which resolves
no ``__setattr__`` and reaches the storage itself; the framework's obligation
there is to make no such write of its own, which is what the last section grades.
"""

from __future__ import annotations

import copy
import gc
import pickle
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

import pytest
from _compact_support import published, raw_row, real_storage
from pydantic import BaseModel, ConfigDict, PrivateAttr, TypeAdapter, ValidationError

from parallax.core.entity import (
    MANY_TO_ONE,
    UNLOADED,
    Attr,
    Entity,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity._errors import EditError, EntityDefinitionError
from parallax.core.entity._instance_state import auxiliary

if TYPE_CHECKING:
    from collections.abc import Callable

_NS = "writepaths"


class Crate(Entity, table="crate", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str | None]
    peer_id: Attr[int | None]
    peer: Rel[Crate | None] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))

    _mark = PrivateAttr(default=3)

    @cached_property
    def warmed(self) -> int:
        return self.id * 10


class Bare(Entity, table="bare", namespace=_NS):
    """The same shape carrying no author-owned state, so what a published value of
    it references is exactly what publication attached."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str | None]
    peer_id: Attr[int | None]
    peer: Rel[Bare | None] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))


class Place(ValueObject):
    city: Attr[str]
    zip_code: Attr[str | None]


class Marker(ValueObject):
    """A Value Object declaring no member, so what a published one presents is
    author-owned state alone."""

    @cached_property
    def stamp(self) -> str:
        return "on"


def _crate() -> Crate:
    return published(Crate, id=1, label="x")


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_assigning_a_member_is_refused_because_every_declared_class_is_frozen() -> None:
    with pytest.raises(ValidationError, match="frozen"):
        cast("Any", _crate()).label = "y"


def test_deleting_a_member_is_refused_for_the_same_reason() -> None:
    with pytest.raises(ValidationError, match="frozen"):
        del cast("Any", _crate()).label


def test_assignment_validation_cannot_be_turned_on_by_a_class_body() -> None:
    # `validate_assignment=True` would make Pydantic write a validated member
    # back into the mapping it read, which for a published value is a temporary.
    # It is unreachable rather than handled: the engine owns the configuration,
    # and both spellings of asking for one are refused at class creation.
    with pytest.raises(EntityDefinitionError, match="entity-reserved-member-name"):

        class Configured(Entity, table="configured", namespace=_NS):  # pyright: ignore[reportUnusedClass] - the declaration is refused, so nothing uses it
            id: Attr[int] = attr(primary_key=True)

            model_config = ConfigDict(validate_assignment=True)

    with pytest.raises(EntityDefinitionError, match="entity-header-unknown-option"):

        class Headered(  # pyright: ignore[reportUnusedClass] - likewise
            Entity,
            table="headered",
            namespace=_NS,
            validate_assignment=True,
        ):
            id: Attr[int] = attr(primary_key=True)


def test_the_engine_leaves_assignment_validation_and_revalidation_at_their_defaults() -> None:
    # The other half of the reservation above: what the engine installs is frozen
    # and nothing else, so neither option is on for any declared class.
    for cls in (Crate, Place):
        config = cast("Any", cls).model_config
        assert config.get("frozen") is True
        assert "validate_assignment" not in config
        assert "revalidate_instances" not in config


def test_assigning_a_relationship_on_a_published_value_is_refused() -> None:
    # A relationship reads its own position in the row, and the row is attached
    # once. A write reaching the presentation instead would be lost, so the
    # descriptor refuses rather than absorbing it.
    value = _crate()
    with pytest.raises(AttributeError, match="attached once"):
        object.__setattr__(value, "peer", None)
    assert raw_row(value) == (0b011, 1, "x", None, UNLOADED)


def test_writing_a_relationship_position_through_that_mapping_is_refused_too() -> None:
    # The row holds a relationship position that the presentation does not carry,
    # so a write of one is a key the mapping has never heard of and a position
    # the row already owns. Taking it as author-owned state would leave the tail
    # answering unloaded while everything reading the value's named state saw the
    # shadow — the split the refusal below exists to prevent.
    value = _crate()
    peer = published(Crate, id=2, label="z")
    state = cast("dict[str, Any]", value.__dict__)
    with pytest.raises(TypeError, match="attached once"):
        state["peer"] = peer
    with pytest.raises(TypeError, match="attached once"):
        state.setdefault("peer", peer)
    with pytest.raises(TypeError, match="attached once"):
        del state["peer"]
    assert raw_row(value) == (0b011, 1, "x", None, UNLOADED)
    assert auxiliary(value) == {}


def test_a_class_declaring_no_author_owned_state_refuses_the_write_it_cannot_keep() -> None:
    # A presentation is seeded from the auxiliary slot only where the class
    # declares state that could be there, so on a class declaring none the slot
    # is read by nothing: a write into it would be answered by the next
    # presentation as though it had never happened. Refusing is what keeps the
    # class fact a contract rather than a prediction.
    value = published(Bare, id=1, label="x", peer_id=None)
    state = cast("dict[str, Any]", value.__dict__)
    with pytest.raises(TypeError, match="declares no"):
        state["memo"] = 7
    with pytest.raises(TypeError, match="declares no"):
        state.setdefault("memo", 7)
    with pytest.raises(TypeError, match="declares no"):
        state.update(memo=7)
    with pytest.raises(TypeError, match="declares no"):
        state |= {"memo": 7}
    assert cast("dict[str, Any]", value.__dict__) == {"id": 1, "label": "x", "peer_id": None}
    assert auxiliary(value) == {}


_COPY_DOORS: tuple[Callable[[Any], object], ...] = (
    copy.copy,
    copy.deepcopy,
    lambda value: value.model_copy(),
    lambda value: value.model_copy(update={"label": "y"}),
    lambda value: value.copy(),
    lambda value: copy.replace(value, label="y"),
)


@pytest.mark.parametrize("door", _COPY_DOORS)
def test_every_inherited_copy_door_is_refused_on_a_published_value(
    door: Callable[[Any], object],
) -> None:
    # Each would have written into a copy's mapping, and each was already refused
    # for its own reason; this is the statement that publication reopens none.
    with pytest.raises(EditError, match="edit-use-edit"):
        door(_crate())


# --------------------------------------------------------------------------- #
# Deliberate demotions
# --------------------------------------------------------------------------- #


def test_a_published_value_object_pickles_as_an_ordinary_one_holding_the_same_state() -> None:
    # Pydantic's own pickle support reads instance state and writes it back
    # wholesale, so a published value crosses as declared values and presence and
    # arrives ordinary. That is the contract rather than a limitation: compact
    # backing is publication backing, not a persistent format.
    value = published(Place, city="Springfield")
    restored = pickle.loads(pickle.dumps(value))
    assert restored == value
    assert restored.model_fields_set == value.model_fields_set == {"city"}
    assert raw_row(restored) is None
    assert real_storage(restored) == {"city": "Springfield", "zip_code": None}


def test_a_lifecycle_free_published_entity_pickles_the_same_way() -> None:
    value = published(Crate, id=1, label="x")
    restored = pickle.loads(pickle.dumps(value))
    assert restored == value
    assert restored.model_fields_set == {"id", "label"}
    assert raw_row(restored) is None
    assert restored._mark == 3


def test_every_other_mutation_of_that_mapping_reaches_the_same_slot() -> None:
    # `functools.cached_property` assigns an item, but a third-party descriptor
    # memoizing through the mapping it was handed can reach for any of `dict`'s
    # mutators. Each is answered rather than inherited, because an inherited one
    # writes the temporary at C speed and vanishes with it — the property would
    # recompute forever, with no signal that it had.
    value = _crate()
    state = cast("dict[str, Any]", value.__dict__)
    state.setdefault("first", 1)
    state.update({"second": 2})
    state |= {"third": 3}
    assert auxiliary(value) == {"first": 1, "second": 2, "third": 3}
    assert state.setdefault("first", 99) == 1
    assert state.pop("second") == 2
    assert state.pop("second", "gone") == "gone"
    assert auxiliary(value) == {"first": 1, "third": 3}
    assert cast("dict[str, Any]", value.__dict__)["third"] == 3
    assert raw_row(value) == (0b011, 1, "x", None, UNLOADED)
    assert real_storage(value) == {}


def test_re_initializing_that_mapping_is_the_update_dict_makes_of_it() -> None:
    # `dict.__init__` on a mapping that already holds items updates it in place
    # rather than replacing it, which makes it a mutator like the ones above and
    # one an inherited implementation would run against the temporary. A caller
    # reaching it is rare; leaving it the one silent write would still leave one.
    value = _crate()
    state = cast("dict[str, Any]", value.__dict__)
    state.__init__({"first": 1}, second=2)
    assert auxiliary(value) == {"first": 1, "second": 2}
    assert cast("dict[str, Any]", value.__dict__)["first"] == 1
    with pytest.raises(TypeError, match="attached once"):
        state.__init__(label="y")
    assert raw_row(value) == (0b011, 1, "x", None, UNLOADED)


def test_an_answered_mutator_keeps_the_arity_dict_gives_it() -> None:
    # `dict.pop` takes at most one default and rejects a second as a caller
    # error. An answered mutator that accepted one would make the presentation
    # honour a call the mapping it presents refuses, which is a different mapping
    # rather than a stricter one.
    state = cast("Any", _crate().__dict__)
    with pytest.raises(TypeError, match="at most 2 arguments"):
        state.pop("missing", 1, 2)
    with pytest.raises(TypeError, match="at most 2 arguments"):
        cast("Any", {}).pop("missing", 1, 2)


_KEYWORD_REFUSALS: tuple[Callable[[Any], object], ...] = (
    lambda state: state.__ior__(state={"memo": 1}),
    lambda state: state.popitem(self=1),
    lambda state: state.clear(self=1),
)


def test_an_answered_mutator_binds_no_keyword_to_a_parameter_of_its_own() -> None:
    # Every parameter of `dict`'s own methods is positional-only, because they are
    # C functions — so a keyword reaching one is data or an error and is never a
    # parameter name. An answered mutator spelling a parameter keyword-bindable
    # refuses a call `dict` honours by colliding with the data key of the same
    # spelling, which is a different mapping rather than a stricter one.
    value = _crate()
    state = cast("Any", value.__dict__)
    state.__init__(self=7, state=8)
    assert auxiliary(value) == {"self": 7, "state": 8}
    plain: Any = {}
    plain.__init__(self=7, state=8)
    assert plain == {"self": 7, "state": 8}
    for refuse in _KEYWORD_REFUSALS:
        with pytest.raises(TypeError):
            refuse(cast("Any", _crate().__dict__))
        with pytest.raises(TypeError):
            refuse(cast("Any", {"memo": 1}))


_ROW_MUTATIONS: tuple[Callable[[dict[str, Any]], object], ...] = (
    lambda state: state.__setitem__("label", "y"),
    lambda state: state.update(label="y"),
    lambda state: state.__ior__({"label": "y"}),
    lambda state: state.__delitem__("label"),
    lambda state: state.pop("label"),
    lambda state: state.pop("label", None),
    lambda state: state.popitem(),
    lambda state: state.clear(),
)


def test_a_presentation_of_author_owned_state_alone_drops_it_the_ordinary_way() -> None:
    # A class declaring no member presents its author-owned state and nothing
    # else, so the removals that must refuse anywhere a row is presented have
    # nothing to refuse here and answer as `dict` does — including on the mapping
    # they leave empty.
    value = published(Marker)
    state = cast("dict[str, Any]", value.__dict__)
    state.clear()
    state.update(first=1, second=2)
    assert state.popitem() == ("second", 2)
    assert auxiliary(value) == {"first": 1}
    state.clear()
    assert auxiliary(value) == {}
    assert cast("dict[str, Any]", value.__dict__) == {}
    with pytest.raises(KeyError):
        del state["first"]
    with pytest.raises(KeyError):
        state.popitem()
    assert real_storage(value) == {}


@pytest.mark.parametrize("mutation", _ROW_MUTATIONS)
def test_mutating_a_declared_member_through_that_mapping_is_refused(
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    # The other end of the same rule: a member the row holds cannot be rewritten
    # or dropped through the mapping presenting it. Absorbing the write would
    # split the value — the descriptor keeps answering from the row while a dump
    # reads the shadow — which is the outcome the seam may not have.
    value = published(Bare, id=1, label="x", peer_id=None)
    with pytest.raises(TypeError, match="attached once"):
        mutation(cast("dict[str, Any]", value.__dict__))
    assert raw_row(value) == (0b111, 1, "x", None, UNLOADED)
    assert value.model_dump() == {"id": 1, "label": "x", "peer_id": None}


def test_writing_into_a_published_value_s_own_mapping_reaches_its_auxiliary_slot() -> None:
    # The one write that must neither refuse nor demote, because
    # `functools.cached_property` makes it and author-owned dynamic state is
    # explicitly kept at its ordinary cost. It lands in a slot of its own, so the
    # row is untouched and the value's real storage is still not there.
    value = _crate()
    cast("dict[str, Any]", value.__dict__)["warmed"] = 99
    assert auxiliary(value) == {"warmed": 99}
    assert value.warmed == 99
    assert raw_row(value) == (0b011, 1, "x", None, UNLOADED)
    assert value.model_dump() == {"id": 1, "label": "x", "peer_id": None}
    assert real_storage(value) == {}


def test_assigning_instance_state_wholesale_demotes_the_value_it_is_assigned_to() -> None:
    # Every path Pydantic writes a model's state by — validation,
    # `model_construct`, `__setstate__` — assigns this name, and each is
    # producing an ordinary value out of semantic state. The row is cleared with
    # the same write, so no value is left split between a row nothing wrote and
    # storage nothing reads.
    value = _crate()
    object.__setattr__(value, "__dict__", {"id": 9, "label": "z", "peer_id": None})
    object.__setattr__(value, "__pydantic_fields_set__", {"id"})
    assert raw_row(value) is None
    assert value.id == 9
    assert value.model_dump() == {"id": 9, "label": "z", "peer_id": None}
    assert value.model_fields_set == {"id"}
    assert value.model_dump(exclude_unset=True) == {"id": 9}


def test_a_demoted_value_reports_a_member_its_new_storage_omits() -> None:
    # Demotion replaces the row with storage, and storage a caller assembled can
    # be missing a member the row always had a position for. Ordinary attribute
    # dispatch reaches the member descriptor exactly then, and what it reports is
    # the member's absence rather than the representation's.
    value = _crate()
    object.__setattr__(value, "__dict__", {"id": 9})
    assert value.id == 9
    with pytest.raises(AttributeError, match="has no attribute 'label'"):
        _ = value.label
    assert not hasattr(value, "label")


def test_the_same_holds_for_a_value_object_member() -> None:
    value = published(Place, city="Springfield")
    object.__setattr__(value, "__dict__", {"city": "Shelbyville"})
    assert value.city == "Shelbyville"
    with pytest.raises(AttributeError, match="has no attribute 'zip_code'"):
        _ = value.zip_code


# --------------------------------------------------------------------------- #
# Neither, because nothing is written
# --------------------------------------------------------------------------- #


def test_validating_an_already_published_value_returns_that_same_value() -> None:
    # Pydantic's no-revalidation behaviour, which the engine's fixed
    # configuration makes the only one available: a published value validated
    # again IS the published value, so there is no de-publication to be silent
    # about.
    value = _crate()
    assert Crate.model_validate(value) is value
    assert TypeAdapter(Crate).validate_python(value) is value

    class Outer(BaseModel):
        model_config = ConfigDict(revalidate_instances="always")
        crate: Crate

    assert Outer(crate=value).crate is value
    assert Outer.model_validate({"crate": value}).crate is value
    assert raw_row(value) is not None


# --------------------------------------------------------------------------- #
# The residual, and the framework's own obligation under it
# --------------------------------------------------------------------------- #


def _dict_referents(value: object) -> list[Any]:
    """Every mapping ``value`` itself holds, without asking it for one.

    Asking is what creates one, so an assertion that reads ``__dict__`` cannot
    tell a storage that was never created from one created empty by the read.
    """
    return [held for held in gc.get_referents(value) if isinstance(held, dict)]


def test_no_framework_read_of_a_published_value_writes_its_storage() -> None:
    # `object.__setattr__` resolves no `__setattr__` and reaches a value's
    # storage directly, so no framework can intercept it — the same door the
    # pickle refusal is already stated against. What the framework owes is that
    # none of its own paths take it, which is what this grades: every read a
    # published value answers leaves its storage uncreated.
    value = published(Bare, {"peer": None}, id=1, label="x", peer_id=None)
    matrix: tuple[dict[str, Any], ...] = ({}, {"exclude_unset": True}, {"round_trip": True})
    for kwargs in matrix:
        value.model_dump(**kwargs)
        value.model_dump_json(**kwargs)
    repr(value)
    hash(value)
    dict(value)
    _ = value.model_fields_set
    _ = value.peer
    _ = value.label
    assert value == published(Bare, id=1, label="x", peer_id=None)
    assert not _dict_referents(value)
    # Read last, because reading it is what creates it.
    assert real_storage(value) == {}


def test_nor_does_a_framework_read_that_wants_the_whole_of_a_value_s_named_state() -> None:
    # Edit, pickle, and the Row Codec's provenance read each want everything a
    # value holds under a name rather than one member, and ordinary backing keeps
    # all of that in the instance dictionary. Reaching for the dictionary on a
    # published value would answer "nothing" AND create one — losing the row's
    # members into a copy built from an empty mapping, permanently, on a read.
    value = published(Bare, {"peer": None}, id=1, label="x", peer_id=None)
    edited = value.edit(label="y")
    assert edited.model_dump() == {"id": 1, "label": "y", "peer_id": None}
    assert edited.peer is None
    assert value.model_dump() == {"id": 1, "label": "x", "peer_id": None}
    assert pickle.loads(pickle.dumps(value)) == value
    assert not _dict_referents(value)
    assert real_storage(value) == {}


def test_that_named_state_carries_author_owned_state_the_way_ordinary_backing_does() -> None:
    # An edit preserves everything it neither replaces nor invalidates (§3), and
    # a published value keeps author-owned state in a slot of its own rather than
    # beside its declared members. A reader that stopped at the row would drop
    # exactly what the same edit of an ordinary value carries forward. The
    # `cached_property` result is the one thing both drop, because the class
    # declares that slot derived from state the edit may have replaced.
    value = _crate()
    cast("dict[str, Any]", value.__dict__)["third_party_cache"] = 7
    assert value.warmed == 10
    edited = value.edit(label="y")
    assert real_storage(edited)["third_party_cache"] == 7
    assert "warmed" not in real_storage(edited)

    ordinary = Crate.model_construct(id=1, label="x", peer_id=None)
    cast("dict[str, Any]", ordinary.__dict__)["third_party_cache"] = 7
    assert ordinary.warmed == 10
    assert real_storage(ordinary.edit(label="y")) == real_storage(edited)


def test_that_a_published_value_edits_out_of_the_same_object_layout_too() -> None:
    # `named_state` answers what a value holds under a NAME, and Pydantic keeps a
    # `PrivateAttr` in a slot of its own instead — so the row a published value
    # publishes cannot be the whole of what its edit carries either. `allocate`
    # gives a shell that slot at the declared defaults, and the edit has to carry
    # what the value holds there rather than restore those defaults.
    value = _crate()
    cast("Any", value)._mark = 9
    edited = value.edit(label="y")
    assert cast("Any", edited)._mark == 9
    assert cast("Any", value.edit())._mark == 9
    # The private slot is a mapping the object layout gives every value of a class
    # declaring one, and it is the only mapping this one holds.
    assert _dict_referents(value) == [{"_mark": 9}]
    assert real_storage(value) == {}


def test_a_published_value_object_edits_out_of_its_row_the_same_way() -> None:
    value = published(Place, city="Springfield", zip_code="49007")
    edited = value.edit(city="Shelbyville")
    assert edited.model_dump() == {"city": "Shelbyville", "zip_code": "49007"}
    assert not _dict_referents(value)
    assert real_storage(value) == {}


def test_an_edit_that_authors_nothing_carries_the_whole_row_forward() -> None:
    # The branch that never reaches the constructor, and so has nothing to catch
    # a partition that came back empty: it restates whatever it was handed.
    value = published(Bare, {"peer": None}, id=1, label="x", peer_id=None)
    assert value.edit() == value
    assert value.edit().model_fields_set == {"id", "label", "peer_id"}
    assert not _dict_referents(value)
    assert real_storage(value) == {}


def test_reaching_a_published_value_s_storage_directly_is_the_stated_residual() -> None:
    # Recorded rather than pretended away. A caller that goes around the frozen
    # refusal writes ordinary storage, which shadows the member descriptor on an
    # attribute read while serialization keeps answering from the row. Nothing
    # in-process prevents it; what the test above states is that the framework
    # never does it.
    value = _crate()
    object.__setattr__(value, "label", "forged")
    assert value.label == "forged"
    assert value.model_dump()["label"] == "x"
