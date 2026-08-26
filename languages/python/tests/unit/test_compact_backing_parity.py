"""One behavior, graded twice: over ordinary backing and over a compact row.

Every reader of a value's physical state now asks the instance-state Module
rather than Pydantic's instance dictionary, and the point of that move is that
the answers do not depend on which backing the value carries. So each case here
builds the SAME value both ways and asserts one outcome: an edit, the Change
Record an edit chain composes, the three Row Codec operations, and a Value
Object's canonical document.

The two arms are twins by construction. ``model_construct(**members)`` populates
exactly the named members and fills every other declared field with its declared
default, which is what ``publish`` does with a bitmap and a template row — so the
arms differ in representation and in nothing else. Neither arm validates, which
is also what publication does not do.

Lifecycle state has no compact arm in this phase and is graded on the ordinary
one alone: it still rides in the instance dictionary a published value does not
have, and the slot that will carry it arrives with the publication flip.
"""

from __future__ import annotations

import gc
import pickle
from typing import TYPE_CHECKING, Any, cast

import pytest
from _compact_support import published, raw_row, real_storage

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    Attr,
    DomainModel,
    Entity,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity import row_codec_of, to_document
from parallax.core.entity._declaration import LIFECYCLE_STATE_SLOT
from parallax.core.entity._entity import CHANGE_RECORD_SLOT, ChangeRecord
from parallax.core.entity._instance_state import is_published
from parallax.core.entity._pydantic_storage import attach_instance_state

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from parallax.core.entity import EntityRowCodec

_NS = "parallax.parity"


class Point(ValueObject):
    lat: Attr[float | None]
    lon: Attr[float | None]


class Site(ValueObject):
    city: Attr[str]
    zip_code: Attr[str | None]
    point: Attr[Point | None]
    tags: Attr[tuple[Point, ...]]


class Depot(Entity, table="depot", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    capacity: Attr[int | None]
    site: Attr[Site | None]
    crates: Rel[tuple[Crate, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "depot_id"))


class Crate(Entity, table="crate", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    depot_id: Attr[int | None]
    depot: Rel[Depot | None] = rel(cardinality=MANY_TO_ONE, join=("depot_id", "id"))


DEPOTS = DomainModel(Depot, Crate)

type Builder = Callable[..., Any]


def _ordinary[M](
    cls: type[M], relationships: Mapping[str, object] | None = None, /, **members: object
) -> M:
    """``cls`` backed by an instance dictionary, populated exactly as ``members``.

    The validation-free constructor, because publication validates nothing
    either: what makes this a twin of the published arm is that both populate the
    named members, leave every other declared field at its declared default, and
    report exactly the named members as populated.
    """
    value = cast("Any", cls).model_construct(**members)
    for py_name, related in (relationships or {}).items():
        object.__setattr__(value, py_name, related)
    return cast("M", value)


BACKINGS: tuple[tuple[str, Builder], ...] = (("ordinary", _ordinary), ("published", published))


@pytest.fixture(params=BACKINGS, ids=[name for name, _build in BACKINGS])
def build(request: pytest.FixtureRequest) -> Builder:
    """One arm's builder: the same call spelling produces either backing."""
    return cast("Builder", request.param[1])


def _depots() -> EntityRowCodec:
    return row_codec_of(DEPOTS)


def _site() -> Site:
    return Site.model_construct(city="Springfield", point=Point.model_construct(lat=1.0))


# --------------------------------------------------------------------------- #
# The arms are twins before anything is asked of them
# --------------------------------------------------------------------------- #


def test_the_two_arms_agree_about_what_the_value_holds_and_what_it_populated() -> None:
    members: dict[str, object] = {"id": 1, "label": "north", "site": _site()}
    ordinary, compact = _ordinary(Depot, **members), published(Depot, **members)
    assert is_published(compact)
    assert not is_published(ordinary)
    assert ordinary == compact
    assert ordinary.model_fields_set == compact.model_fields_set == set(members)
    assert ordinary.capacity is compact.capacity is None
    assert dict(ordinary) == dict(compact)


# --------------------------------------------------------------------------- #
# Edit
# --------------------------------------------------------------------------- #


def test_an_edit_of_either_backing_yields_an_ordinary_value(build: Builder) -> None:
    edited = build(Depot, id=1, label="north").edit(label="south")
    assert not is_published(edited)
    assert raw_row(edited) is None
    assert real_storage(edited) == {
        "id": 1,
        "label": "south",
        "capacity": None,
        "site": None,
        CHANGE_RECORD_SLOT: {"label": "north"},
    }


def test_an_edit_replaces_what_it_names_and_carries_the_rest(build: Builder) -> None:
    site = _site()
    edited = build(Depot, id=1, label="north", site=site).edit(label="south")
    assert edited.id == 1
    assert edited.label == "south"
    assert edited.site == site
    assert edited.capacity is None


def test_an_edit_that_authors_nothing_reproduces_the_value(build: Builder) -> None:
    value = build(Depot, id=1, label="north", capacity=12)
    assert value.edit() == value
    assert value.edit().model_fields_set == {"id", "label", "capacity"}


def test_an_edit_carries_a_loaded_relationship_forward(build: Builder) -> None:
    depot = build(Depot, id=1, label="north")
    crate = build(Crate, {"depot": depot}, id=7, depot_id=1)
    assert crate.edit(depot_id=2).depot == depot


def test_an_edit_carries_an_unloaded_relationship_forward_unloaded(build: Builder) -> None:
    crate = build(Crate, id=7, depot_id=1)
    with pytest.raises(AttributeError, match="depot"):
        _ = crate.edit(depot_id=2).depot


def test_an_edit_chain_records_the_earliest_original_of_each_touched_member(
    build: Builder,
) -> None:
    value = build(Depot, id=1, label="north", capacity=12)
    chained = value.edit(label="south").edit(label="east", capacity=13)
    assert real_storage(chained)[CHANGE_RECORD_SLOT] == {"label": "north", "capacity": 12}
    assert isinstance(real_storage(chained)[CHANGE_RECORD_SLOT], ChangeRecord)


def test_an_edit_that_authors_nothing_carries_the_record_it_was_handed(build: Builder) -> None:
    chained = build(Depot, id=1, label="north").edit(label="south").edit()
    assert real_storage(chained)[CHANGE_RECORD_SLOT] == {"label": "north"}


def test_an_edit_of_a_published_value_creates_no_storage_for_it() -> None:
    # `Depot` declares neither a `cached_property` nor a `PrivateAttr`, so the
    # whole of what its published values hold is the row — and an edit reaches it
    # there. Reaching for the source's instance dictionary instead would create
    # one, permanently, on a path that only meant to copy.
    value = published(Depot, id=1, label="north")
    value.edit(label="south")
    value.edit()
    assert not [held for held in gc.get_referents(value) if isinstance(held, dict)]
    # Read last, because reading it is what creates it.
    assert real_storage(value) == {}


def test_an_unedited_value_of_either_backing_carries_no_record(build: Builder) -> None:
    value = build(Depot, id=1, label="north")
    assert CHANGE_RECORD_SLOT not in real_storage(value)


# --------------------------------------------------------------------------- #
# Row derivation
# --------------------------------------------------------------------------- #


def test_a_full_row_emits_every_populated_member_of_either_backing(build: Builder) -> None:
    assert _depots().full_row(build(Depot, id=1, label="north", capacity=12)) == {
        "id": 1,
        "label": "north",
        "capacity": 12,
    }


def test_a_full_row_omits_a_member_the_value_never_populated(build: Builder) -> None:
    # The distinction compact presence exists to preserve: `capacity` reads as
    # `None` under both backings, and neither row spells it, so the narrower
    # insert is emitted and the column keeps its stored default.
    value = build(Depot, id=1, label="north")
    assert value.capacity is None
    assert _depots().full_row(value) == {"id": 1, "label": "north"}


def test_a_full_row_spells_a_member_populated_as_null(build: Builder) -> None:
    assert _depots().full_row(build(Depot, id=1, label="north", capacity=None)) == {
        "id": 1,
        "label": "north",
        "capacity": None,
    }


def test_a_full_row_renders_an_occurrence_as_its_document(build: Builder) -> None:
    assert _depots().full_row(build(Depot, id=1, label="north", site=_site()))["site"] == {
        "city": "Springfield",
        "point": {"lat": 1.0},
        "tags": [],
    }


def test_an_identity_row_reads_the_primary_key_of_either_backing(build: Builder) -> None:
    assert _depots().identity_row(build(Depot, id=1, label="north")) == {"id": 1}


def test_an_edited_row_is_the_identity_plus_the_effective_changes(build: Builder) -> None:
    edited = build(Depot, id=1, label="north", capacity=12).edit(label="south")
    assert _depots().edited_row(edited) == {"id": 1, "label": "south"}


def test_an_edited_row_answers_none_for_a_value_no_edit_touched(build: Builder) -> None:
    assert _depots().edited_row(build(Depot, id=1, label="north")) is None


def test_an_edited_row_answers_none_for_a_chain_that_nets_to_zero(build: Builder) -> None:
    value = build(Depot, id=1, label="north")
    assert _depots().edited_row(value.edit(label="south").edit(label="north")) is None
    assert _depots().restored_members(value.edit(label="south").edit(label="north")) == {"label"}


def test_a_row_derived_from_a_published_value_creates_no_storage_for_it() -> None:
    # The published arm's own obligation, which the ordinary arm cannot have:
    # every operation above reaches for what the value holds by name, and asking
    # a published value's storage for it would create the dictionary publication
    # exists without — permanently, on a read.
    value = published(Depot, id=1, label="north", capacity=12)
    codec = _depots()
    codec.full_row(value)
    codec.identity_row(value)
    codec.edited_row(value)
    codec.restored_members(value)
    assert not [held for held in gc.get_referents(value) if isinstance(held, dict)]
    # Read last, because reading it is what creates it.
    assert real_storage(value) == {}


# --------------------------------------------------------------------------- #
# Document presence
# --------------------------------------------------------------------------- #


def test_a_document_omits_a_member_the_value_never_populated(build: Builder) -> None:
    # `tags` is the one exception under either backing: a Many occurrence is
    # never nullable and its empty default IS a value, so it is contributed
    # whether or not the value populated it.
    assert to_document(build(Site, city="Springfield")) == {"city": "Springfield", "tags": []}


def test_a_document_spells_a_member_populated_as_null(build: Builder) -> None:
    assert to_document(build(Site, city="Springfield", zip_code=None)) == {
        "city": "Springfield",
        "zipCode": None,
        "tags": [],
    }


def test_a_document_renders_nested_occurrences_of_either_backing(build: Builder) -> None:
    document = to_document(
        build(
            Site,
            city="Springfield",
            point=build(Point, lat=1.0, lon=2.0),
            tags=(build(Point, lat=3.0),),
        )
    )
    assert document == {
        "city": "Springfield",
        "point": {"lat": 1.0, "lon": 2.0},
        "tags": [{"lat": 3.0}],
    }


def test_a_document_derived_from_a_published_value_creates_no_storage_for_it() -> None:
    value = published(Site, city="Springfield", point=published(Point, lat=1.0))
    to_document(value)
    assert not [held for held in gc.get_referents(value) if isinstance(held, dict)]
    assert real_storage(value) == {}


# --------------------------------------------------------------------------- #
# Value Object edit and pickle
# --------------------------------------------------------------------------- #


def test_a_value_object_edit_of_either_backing_yields_an_ordinary_value(build: Builder) -> None:
    edited = build(Site, city="Springfield").edit(city="Shelbyville")
    assert not is_published(edited)
    assert raw_row(edited) is None


def test_a_value_object_edit_carries_presence_forward_exactly(build: Builder) -> None:
    edited = build(Site, city="Springfield").edit(zip_code="49007")
    assert edited.model_fields_set == {"city", "zip_code"}
    assert to_document(edited) == {"city": "Springfield", "zipCode": "49007", "tags": []}


def test_a_value_object_edit_that_authors_nothing_carries_presence_forward_too(
    build: Builder,
) -> None:
    edited = build(Site, city="Springfield").edit()
    assert edited.model_fields_set == {"city"}
    assert to_document(edited) == {"city": "Springfield", "tags": []}


def test_a_value_object_of_either_backing_pickles_to_an_ordinary_one(build: Builder) -> None:
    # Compact backing is publication backing rather than a persistent format, so
    # a published value crosses as its declared values and its presence and
    # arrives ordinary — carrying the same members, and the same distinction
    # between an unpopulated member and one populated as null.
    value = build(Site, city="Springfield", zip_code=None)
    restored = pickle.loads(pickle.dumps(value))
    assert restored == value
    assert restored.model_fields_set == {"city", "zip_code"}
    assert raw_row(restored) is None
    assert to_document(restored) == to_document(value)


# --------------------------------------------------------------------------- #
# What has no compact arm yet
# --------------------------------------------------------------------------- #


def test_an_edit_carries_lifecycle_state_forward_on_the_backing_that_can_hold_it() -> None:
    # Lifecycle state still rides in the instance dictionary, which a published
    # value does not have, so this is the one edit behavior with an ordinary arm
    # alone until publication attaches it to a slot of its own.
    value = _ordinary(Depot, id=1, label="north")
    attach_instance_state(value, LIFECYCLE_STATE_SLOT, "pinned")
    assert real_storage(value.edit(label="south"))[LIFECYCLE_STATE_SLOT] == "pinned"
    assert getattr(published(Depot, id=1, label="north"), LIFECYCLE_STATE_SLOT, None) is None
