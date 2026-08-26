"""``ValueObject.edit(**changes)`` and the copy doors it seals (spec §3).

The Entity half of the one edit contract is pinned in ``test_edit.py``; what this
suite proves is what the Value Object half answers differently. Three things do:
no Change Record is stamped, because a Value Object has no identity and is never
independently written; presence is carried forward member by member, because the
document a write stores spells only the members the value populates; and half the
closed edit-code set is unreachable, because no Value Object member carries the
designations those codes report.

The stakes are the reason the verb exists. Assigning an occurrence replaces its
subtree whole, so a member a restated value forgets is a member the write
deletes, and an unvalidated copy is structurally invalid data one write away from
being stored.

What this suite holds is the in-memory seam — the populated set, the document a
value serializes to, the instance state a copy carries — and every refusal. The
idiomatic usage story, where the derived value is graded as the document the
database then holds, runs against real Postgres in
``tests/api/test_value_object_edit_run.py``.
"""

from __future__ import annotations

import copy as copy_module
import threading
from functools import cached_property
from typing import Any, cast

import pytest
from _compact_support import layout_slots
from pydantic import PrivateAttr

from _support import value_object_models as vm
from parallax.core import Attr, Rel, ValueObject, attr
from parallax.core.entity import EDIT_CODES, EditError, EntityDefinitionError
from parallax.core.entity._entity import CHANGE_RECORD_SLOT
from parallax.core.entity._instance_state import AUXILIARY_STATE_SLOT, COMPACT_STATE_SLOT
from parallax.core.metamodel import MODEL_ROOT

_UNREACHABLE_FROM_A_VALUE_OBJECT = frozenset(
    {
        "edit-relationship-member",
        "edit-primary-key",
        "edit-read-only",
        "edit-framework-owned",
    }
)
"""The four codes no Value Object edit can raise, named here rather than read off
the implementation so narrowing one of them fails this suite instead of agreeing
with itself. Each reports something ``m-value-object`` does not have: a
relationship to refuse, or one of the three assignment designations."""


def _address(city: str = "Oslo") -> vm.Address:
    """One Address populating three of its four members: ``geo`` is nullable and
    is deliberately left unset, which is the presence state an edit must carry."""
    return vm.Address(street="Storgata 1", city=city, phones=(vm.Phone(type="home", number="1"),))


# --------------------------------------------------------------------------- #
# The copy: everything unnamed is carried forward, presence included.          #
# --------------------------------------------------------------------------- #
def test_an_unset_optional_member_stays_absent_from_the_document() -> None:
    # The round-trip property replacement depends on: an edit fabricates no
    # explicit null for a member storage never held, so writing back what a read
    # published stores what was read.
    edited = _address().edit(city="Bergen")
    assert "geo" not in edited.model_fields_set
    assert edited.__parallax_document__() == {
        "street": "Storgata 1",
        "city": "Bergen",
        "phones": [{"type": "home", "number": "1"}],
    }


def test_naming_a_nullable_member_none_stores_an_explicit_null() -> None:
    # The other side of the same distinction: absence is what was never authored,
    # and a null is what a caller authored.
    edited = _address().edit(geo=None)
    assert "geo" in edited.model_fields_set
    assert edited.__parallax_document__()["geo"] is None


def test_an_edit_replaces_a_nested_occurrence_whole() -> None:
    geo = vm.Geo(country="NO", point=vm.Point(lat=59.9, lon=10.7))
    edited = _address().edit(geo=geo)
    assert edited.geo == geo
    assert edited.__parallax_document__()["geo"] == {
        "country": "NO",
        "point": {"lat": 59.9, "lon": 10.7},
    }


def test_an_edit_replaces_a_many_occurrence_whole() -> None:
    edited = _address().edit(phones=(vm.Phone(type="work", number="2"),))
    assert edited.__parallax_document__()["phones"] == [{"type": "work", "number": "2"}]


def test_an_edit_with_no_changes_is_legal_and_carries_the_same_state() -> None:
    original = _address()
    plain = original.edit()
    assert plain is not original
    assert plain == original
    assert plain.model_fields_set == original.model_fields_set


def test_an_edit_stamps_no_change_record() -> None:
    # A Change Record answers "what did this object's caller touch", which is a
    # question about an identity a Value Object does not have. The slot the Entity
    # surface owns is therefore never written here — and the codec that reads it
    # never reaches a Value Object, which reaches storage only inside its owner.
    edited = _address().edit(city="Bergen")
    assert CHANGE_RECORD_SLOT not in edited.__dict__
    assert CHANGE_RECORD_SLOT not in _address().edit().__dict__


class _Tagged(ValueObject):
    """One derived cache on a Value Object, spelled the way the language spells
    one: the memoized answer is computed from a declared member, so an edit that
    replaces that member contradicts it."""

    label: Attr[str]

    @cached_property
    def shouted(self) -> str:
        return self.label.upper()


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=["authored", "change-free"])
def test_an_edit_never_carries_a_derived_cache(changes: dict[str, object]) -> None:
    tagged = _Tagged(label="a")
    assert tagged.shouted == "A"
    assert "shouted" not in tagged.edit(**changes).__dict__


class _Marked(ValueObject):
    """One private attribute on a Value Object, which Pydantic keeps in a slot of
    the object layout rather than in the instance dictionary an edit rebuilds, and
    one slot the class lays out itself, which no base of it has ever heard of."""

    __slots__ = ("token",)

    label: Attr[str]

    _mark = PrivateAttr(default=3)


_REBUILT_SLOTS = frozenset(
    {"__dict__", "__pydantic_fields_set__", COMPACT_STATE_SLOT, AUXILIARY_STATE_SLOT}
)
"""The four slots an edit fills from semantic state rather than carrying, as the
Entity half states them."""

_COPIED_CONTAINER_SLOTS = frozenset({"__pydantic_extra__", "__pydantic_private__"})
"""The carried slots the copy gets its own outer mapping of, as the Entity half
states them."""


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=["authored", "change-free"])
def test_an_edit_carries_every_slot_of_the_layout_it_does_not_rebuild(
    changes: dict[str, object],
) -> None:
    # Completeness graded over the layout THIS CLASS actually has, walked across
    # its whole MRO, exactly as the Entity half grades it: every other carry test
    # reads a name out of the instance dictionary, and neither `PrivateAttr` state
    # nor a slot the declaring class lays out for itself is stored under one. How
    # each travels is graded too — the framework's own mappings are the copy's
    # own, everything else is the very object the source held.
    marked = _Marked(label="a")
    cast("Any", marked)._mark = 9
    object.__setattr__(marked, "token", ["t"])
    carried = {
        name: slot for name, slot in layout_slots(_Marked).items() if name not in _REBUILT_SLOTS
    }
    assert {"token", "__pydantic_private__"} <= set(carried)
    copied = marked.edit(**changes)
    for name, slot in carried.items():
        held = slot.__get__(marked)
        assert slot.__get__(copied) == held
        if name in _COPIED_CONTAINER_SLOTS and held is not None:
            assert slot.__get__(copied) is not held
        else:
            assert slot.__get__(copied) is held
    assert cast("Any", copied)._mark == 9


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=["authored", "change-free"])
def test_an_edit_carries_an_authored_slot_s_payload_itself(changes: dict[str, object]) -> None:
    # Unchanged means the object itself on this surface too, so an edit neither
    # loses the source's view of a mutation made through the copy nor refuses a
    # payload no copy protocol can reproduce.
    marked = _Marked(label="a")
    guard = threading.Lock()
    object.__setattr__(marked, "token", guard)
    assert cast("Any", marked.edit(**changes)).token is guard


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=["authored", "change-free"])
def test_an_edit_leaves_a_slot_the_source_never_held_unheld(changes: dict[str, object]) -> None:
    # A layout travels with the absences in it, on this surface too.
    copied = _Marked(label="a").edit(**changes)
    with pytest.raises(AttributeError, match="token"):
        cast("Any", copied).token  # noqa: B018 - the access itself is the assertion


@pytest.mark.parametrize("changes", [{"city": "Bergen"}, {}], ids=["authored", "change-free"])
def test_an_edit_carries_a_slot_no_declaration_names(changes: dict[str, object]) -> None:
    # The carry is by COMPLEMENT on this surface too, which is what lets a kind of
    # instance state neither frontend knows travel through an edit.
    value = _address()
    marker = object()
    object.__setattr__(value, "__parallax_unnamed__", marker)
    assert value.edit(**changes).__dict__["__parallax_unnamed__"] is marker


# --------------------------------------------------------------------------- #
# Refusals: the shared rules, minus the four no Value Object member can break. #
# --------------------------------------------------------------------------- #
def test_an_unknown_member_name_is_rejected() -> None:
    with pytest.raises(EditError, match="unknown member name"):
        _address().edit(postcode="0150")


def test_a_nested_path_is_rejected_rather_than_reported_as_unknown() -> None:
    # The member is perfectly well known; what the authored name asks for is a
    # sparse write below an occurrence's boundary, which no door offers.
    with pytest.raises(EditError, match="never a nested path") as caught:
        _address().edit(**{"geo.country": "NO"})
    assert caught.value.codes == {"edit-nested-path"}
    assert caught.value.violations[0].member_name == "geo.country"


def test_an_ill_typed_leaf_raises_at_edit_time_not_at_the_database() -> None:
    with pytest.raises(EditError, match="does not match the declared type"):
        _address().edit(city=42)


def test_a_malformed_occurrence_document_raises_at_edit_time() -> None:
    with pytest.raises(EditError, match="required attribute is absent"):
        _address().edit(geo=vm.Geo.model_construct(elevation=1.0))


def test_every_violation_is_reported_once_and_ordered_independently_of_keyword_order() -> None:
    # Aggregated, not first-failure, exactly as the Entity surface reports. Every
    # violation shares one location here, so the code and the member name are what
    # order the report — which is why those two terms exist.
    def refuse(**changes: object) -> EditError:
        with pytest.raises(EditError) as caught:
            _address().edit(**changes)
        return caught.value

    error = refuse(**{"city": 42, "postcode": "0150", "geo.country": "NO"})
    assert [(v.code, v.member_name) for v in error.violations] == [
        ("edit-nested-path", "geo.country"),
        ("edit-unknown-member", "postcode"),
        ("edit-value-mismatch", "city"),
    ]
    assert refuse(**{"geo.country": "NO", "city": 42, "postcode": "0150"}).violations == (
        error.violations
    )


def test_every_violation_locates_at_the_model_root() -> None:
    # A Value Object Class is a reusable shape rather than a position in a model —
    # the same class composes into occurrences of many Entities — so there is no
    # occurrence for a refusal to name and the location says so.
    with pytest.raises(EditError) as caught:
        _address().edit(city=42, postcode="0150")
    assert {violation.location for violation in caught.value.violations} == {MODEL_ROOT}


def test_a_refused_edit_builds_nothing_and_retains_no_cause() -> None:
    with pytest.raises(EditError) as caught:
        _address().edit(city=42)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_a_value_that_passes_judgement_still_faces_the_constructor() -> None:
    # The judgement checks the declared Neutral Type and Pydantic checks the
    # Python annotation, so a Value Object member assigned a raw mapping — a
    # document the judgement accepts — is still refused where §2 refuses it.
    with pytest.raises(TypeError, match="never a raw mapping"):
        _address().edit(geo={"country": "NO"})


def test_every_edit_code_a_value_object_can_earn_has_a_reachable_refusal() -> None:
    # Closed from below on this surface as well: each code left after the four
    # structurally unreachable ones is what some authored mistake actually raises.
    refusals = (
        lambda: _address().model_copy(),
        lambda: _address().edit(postcode="0150"),
        lambda: _address().edit(**{"geo.country": "NO"}),
        lambda: _address().edit(city=42),
    )
    observed: set[str] = set()
    for refusal in refusals:
        with pytest.raises(EditError) as caught:
            refusal()
        observed |= caught.value.codes
    assert observed == EDIT_CODES - _UNREACHABLE_FROM_A_VALUE_OBJECT


def test_the_unreachable_codes_are_refused_where_the_designation_would_be_declared() -> None:
    # Unreachable by construction rather than by omission: a Value Object member
    # cannot declare a key, a read-only mark, or a relationship in the first
    # place, and framework ownership is derived from an Entity's version Attribute
    # and As-Of Axes, which a Value Object has neither of.
    with pytest.raises(EntityDefinitionError) as designated:

        class _Keyed(ValueObject):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            id: Attr[int] = attr(primary_key=True, read_only=True)

    assert designated.value.code == "entity-option-context-invalid"
    with pytest.raises(EntityDefinitionError) as related:

        class _Related(ValueObject):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            owner: Rel[vm.Customer]

    assert related.value.code == "entity-annotation-invalid"


# --------------------------------------------------------------------------- #
# `edit` is the only door: every inherited copy path creates nothing.          #
# --------------------------------------------------------------------------- #
def test_every_inherited_copy_path_is_refused() -> None:
    # One reachable path would defeat the purpose. `model_copy(update=...)` writes
    # its values in without validating them, so it can build a Value Object no
    # declaration admits — and a structurally invalid occurrence serializes into
    # the stored document exactly as a valid one does.
    value = _address()
    doors = (
        lambda: value.model_copy(),
        lambda: value.model_copy(update={"city": 42}),
        lambda: value.model_copy(deep=True),
        lambda: value.copy(),
        lambda: copy_module.copy(value),
        lambda: copy_module.deepcopy(value),
    )
    for door in doors:
        with pytest.raises(EditError) as caught:
            door()
        assert caught.value.codes == {"edit-use-edit"}
        violation = caught.value.violations[0]
        assert violation.member_name is None
        assert violation.location == MODEL_ROOT
        assert "edit(**changes)" in violation.message


def test_a_refused_copy_door_retains_no_cause_while_another_error_is_handled() -> None:
    # A copy door examines nothing, so whatever the caller happened to be handling
    # is not why it refused.
    value = _address()
    doors = (
        lambda: value.model_copy(),
        lambda: value.copy(),
        lambda: copy_module.copy(value),
        lambda: copy_module.deepcopy(value),
    )
    for door in doors:
        try:
            raise RuntimeError("an unrelated failure being handled")
        except RuntimeError:
            with pytest.raises(EditError) as caught:
                door()
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__


def test_a_value_object_class_may_not_declare_the_copy_verb() -> None:
    # The reservation that arrived with the verb: a declared `edit` installs its
    # descriptor over it and leaves the class with no way to derive a copy at all.
    with pytest.raises(EntityDefinitionError) as caught:

        class _Audited(ValueObject):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            edit: Attr[str]  # pyright: ignore[reportIncompatibleMethodOverride] - shadowing the copy verb is the rejection under test

    assert caught.value.code == "entity-reserved-member-name"
