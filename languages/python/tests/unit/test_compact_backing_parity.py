"""One behavior, graded twice: over ordinary backing and over a compact row.

Every reader of a value's physical state asks the instance-state Module rather
than Pydantic's instance dictionary, and the point of asking there is that the
answers do not depend on which backing the value carries. So each case here
builds the SAME value both ways and asserts one outcome: an edit, the Change
Record an edit chain composes, the three Row Codec operations, and a Value
Object's canonical document.

The two arms are twins by construction. ``model_construct(**members)`` populates
exactly the named members and fills every other declared field with its declared
default, which is what ``publish`` does with a bitmap and a template row — so the
arms differ in representation and in nothing else. Neither arm validates, which
is also what publication does not do. That premise has one bound, graded at the
end: a required member carried no value has no declared default to be filled
with, so the ordinary arm leaves it unset and reading it raises, while the
published arm reads the ``None`` its position holds. Neither invents a value, and
neither refuses one.

The models are chosen for reach rather than realism, because a corpus grading an
equivalence is only as wide as the shapes it can express: containment two deep
under both a One and a Many occurrence, a member a concrete inherits rather than
declares, a required member beside optional ones, a member populated as null
beside one never populated, and — on a Value Object and an Entity alike — the two
kinds of state that live outside the members, a ``PrivateAttr`` and a
``cached_property``.

Lifecycle state is graded on both arms: it rides a slot of the ``Entity`` root's
own layout, so a published node carries it exactly as an ordinary value does.
"""

from __future__ import annotations

import pickle
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

import pytest
from _compact_support import carries_instance_storage, published, raw_row, real_storage
from pydantic import PrivateAttr

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity import row_codec_of, to_document
from parallax.core.entity._entity import (
    CHANGE_RECORD_SLOT,
    ChangeRecord,
    attach_lifecycle_state,
    lifecycle_state,
)
from parallax.core.entity._instance_state import is_published
from parallax.core.entity._pydantic_storage import attach_instance_state

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from parallax.core.entity import EntityRowCodec

_NS = "parallax.parity"


class Fix(ValueObject):
    """The corpus's deepest leaf, so an occurrence stands under an occurrence."""

    epoch: Attr[int | None]


class Point(ValueObject):
    lat: Attr[float | None]
    lon: Attr[float | None]
    fix: Attr[Fix | None]


class Site(ValueObject):
    """A Value Object carrying both containment shapes, and both kinds of state
    that live outside the members: a private attribute, and a derived value a
    ``cached_property`` writes where the backing keeps it."""

    city: Attr[str]
    zip_code: Attr[str | None]
    point: Attr[Point | None]
    tags: Attr[tuple[Point, ...]]

    _revision = PrivateAttr(default=0)

    @cached_property
    def shouted(self) -> str:
        return self.city.upper()


class Depot(Entity, table="depot", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    capacity: Attr[int | None]
    site: Attr[Site | None]
    crates: Rel[tuple[Crate, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "depot_id"))

    _revision = PrivateAttr(default=0)

    @cached_property
    def shouted(self) -> str:
        return self.label.upper()


class Crate(Entity, table="crate", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    depot_id: Attr[int | None]
    depot: Rel[Depot | None] = rel(cardinality=MANY_TO_ONE, join=("depot_id", "id"))


class Vehicle(
    Entity,
    table="vehicle",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """A family root, so the corpus reaches a member a value inherits rather than
    declares: both backings address one by the position its own concrete's
    ancestry-first layout gives it."""

    id: Attr[int] = attr(primary_key=True)
    plate: Attr[str]
    site: Attr[Site | None]


class Truck(Vehicle, namespace=_NS, inheritance=ConcreteSubtype(tag_value="truck")):
    payload: Attr[int | None]


PARITY_MODEL = DomainModel(Depot, Crate, Vehicle, Truck)

type Builder = Callable[..., Any]


def _ordinary[M](
    cls: type[M], relationships: Mapping[str, object] | None = None, /, **members: object
) -> M:
    """``cls`` backed by an instance dictionary, populated exactly as ``members``.

    The validation-free constructor, because publication validates nothing
    either: what makes this a twin of the published arm is that both populate the
    named members, leave every other declared field at its declared default, and
    report exactly the named members as populated. A loaded relationship goes into
    the storage under its own name, which is where ordinary backing keeps one and
    where every reader of one looks: a value's relationships are attached with the
    rest of its state, so no descriptor takes one a member at a time.
    """
    value = cast("Any", cls).model_construct(**members)
    for py_name, related in (relationships or {}).items():
        attach_instance_state(value, py_name, related)
    return cast("M", value)


BACKINGS: tuple[tuple[str, Builder], ...] = (("ordinary", _ordinary), ("published", published))


@pytest.fixture(params=BACKINGS, ids=[name for name, _build in BACKINGS])
def build(request: pytest.FixtureRequest) -> Builder:
    """One arm's builder: the same call spelling produces either backing."""
    return cast("Builder", request.param[1])


def _codec() -> EntityRowCodec:
    return row_codec_of(PARITY_MODEL)


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


def test_the_two_arms_address_an_inherited_member_the_same_way() -> None:
    # A concrete's row is its family's, ancestry first, so `plate` occupies a
    # position `Truck` never declared and `payload` one it did. Neither arm reads
    # a member off the class that declared it, so both answer, populate, and omit
    # the inherited member exactly as they do the declared one.
    members: dict[str, object] = {"id": 1, "plate": "AB-12"}
    ordinary, compact = _ordinary(Truck, **members), published(Truck, **members)
    assert ordinary == compact
    assert ordinary.model_fields_set == compact.model_fields_set == set(members)
    assert ordinary.payload is compact.payload is None
    assert _codec().full_row(ordinary) == _codec().full_row(compact) == {"id": 1, "plate": "AB-12"}


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
    # An edit reads what the source holds where the source holds it. Reaching for
    # the source's instance dictionary instead would create one, permanently, on a
    # path that only meant to copy — and the value's private attributes and its
    # read `cached_property` are dictionaries of the layout's own, which is why
    # this asks whether STORAGE exists rather than whether any dictionary does.
    value = published(Depot, id=1, label="north")
    assert value.shouted == "NORTH"
    value.edit(label="south")
    value.edit()
    assert not carries_instance_storage(value)
    # Read last, because reading it is what creates it.
    assert real_storage(value) == {}


def test_an_edit_of_either_backing_carries_an_inherited_member_forward(build: Builder) -> None:
    edited = build(Truck, id=1, plate="AB-12").edit(payload=9)
    assert edited.plate == "AB-12"
    assert edited.payload == 9
    assert real_storage(edited)[CHANGE_RECORD_SLOT] == {"payload": None}


def test_an_edit_of_either_backing_carries_private_state_and_derives_again(
    build: Builder,
) -> None:
    # The state that lives outside the members, which the two backings keep in
    # different places: a private attribute rides a slot of its own on both, and
    # a read `cached_property` writes into the instance dictionary of an ordinary
    # value and the auxiliary slot of a published one. An edit carries the first
    # and derives the second again, from either backing.
    value: Any = build(Site, city="Springfield")
    value._revision = 4
    assert value.shouted == "SPRINGFIELD"
    edited: Any = value.edit(city="Shelbyville")
    assert edited._revision == 4
    assert edited.shouted == "SHELBYVILLE"


def test_an_unedited_value_of_either_backing_carries_no_record(build: Builder) -> None:
    value = build(Depot, id=1, label="north")
    assert CHANGE_RECORD_SLOT not in real_storage(value)


# --------------------------------------------------------------------------- #
# Row derivation
# --------------------------------------------------------------------------- #


def test_a_full_row_emits_every_populated_member_of_either_backing(build: Builder) -> None:
    assert _codec().full_row(build(Depot, id=1, label="north", capacity=12)) == {
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
    assert _codec().full_row(value) == {"id": 1, "label": "north"}


def test_a_full_row_spells_a_member_populated_as_null(build: Builder) -> None:
    assert _codec().full_row(build(Depot, id=1, label="north", capacity=None)) == {
        "id": 1,
        "label": "north",
        "capacity": None,
    }


def test_a_full_row_renders_an_occurrence_as_its_document(build: Builder) -> None:
    assert _codec().full_row(build(Depot, id=1, label="north", site=_site()))["site"] == {
        "city": "Springfield",
        "point": {"lat": 1.0},
        "tags": [],
    }


def test_an_identity_row_reads_the_primary_key_of_either_backing(build: Builder) -> None:
    assert _codec().identity_row(build(Depot, id=1, label="north")) == {"id": 1}


def test_an_edited_row_is_the_identity_plus_the_effective_changes(build: Builder) -> None:
    edited = build(Depot, id=1, label="north", capacity=12).edit(label="south")
    assert _codec().edited_row(edited) == {"id": 1, "label": "south"}


def test_an_edited_row_answers_none_for_a_value_no_edit_touched(build: Builder) -> None:
    assert _codec().edited_row(build(Depot, id=1, label="north")) is None


def test_an_edited_row_answers_none_for_a_chain_that_nets_to_zero(build: Builder) -> None:
    value = build(Depot, id=1, label="north")
    assert _codec().edited_row(value.edit(label="south").edit(label="north")) is None
    assert _codec().restored_members(value.edit(label="south").edit(label="north")) == {"label"}


def test_a_row_derived_from_a_published_value_creates_no_storage_for_it() -> None:
    # The published arm's own obligation, which the ordinary arm cannot have:
    # every operation above reaches for what the value holds by name, and asking
    # a published value's storage for it would create the dictionary publication
    # exists without — permanently, on a read.
    value = published(Depot, id=1, label="north", capacity=12)
    assert value.shouted == "NORTH"
    codec = _codec()
    codec.full_row(value)
    codec.identity_row(value)
    codec.edited_row(value)
    codec.restored_members(value)
    assert not carries_instance_storage(value)
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
    # Containment past one level, in both shapes: an occurrence inside a One
    # occurrence, and an occurrence inside an element of a Many. Presence is
    # resolved at every depth against the value standing there, so the arms agree
    # about a leaf populated at depth two and one left absent there.
    document = to_document(
        build(
            Site,
            city="Springfield",
            point=build(Point, lat=1.0, lon=2.0, fix=build(Fix, epoch=7)),
            tags=(build(Point, lat=3.0, fix=build(Fix)), build(Point, lat=4.0)),
        )
    )
    assert document == {
        "city": "Springfield",
        "point": {"lat": 1.0, "lon": 2.0, "fix": {"epoch": 7}},
        "tags": [{"lat": 3.0, "fix": {}}, {"lat": 4.0}],
    }


def test_a_document_derived_from_a_published_value_creates_no_storage_for_it() -> None:
    value = published(Site, city="Springfield", point=published(Point, lat=1.0))
    assert value.shouted == "SPRINGFIELD"
    to_document(value)
    assert not carries_instance_storage(value)
    assert not carries_instance_storage(cast("Any", value).point)
    # Read last, because reading it is what creates it.
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
# Where the two arms are not twins
# --------------------------------------------------------------------------- #


def test_a_required_member_no_value_was_carried_for_reads_as_its_position_holds() -> None:
    # The one place the two arms are not twins, and neither invents a value.
    # `model_construct` leaves a required member it was handed nothing for unset,
    # so reading it raises; a row has a position for that member whatever
    # happens, so a published value reads `None` there — which is not a value the
    # member admits, and is why the presence bit beside it is what tells a
    # carried null from a position no read filled.
    #
    # Publication refuses neither. A required position a read did not carry is a
    # recorded finding on the projection (spec §5) rather than a row this seam may
    # reject, and refusing one here would refuse a document collapse the read
    # specification defines.
    with pytest.raises(AttributeError, match="city"):
        _ = _ordinary(Site, zip_code=None).city
    absent = published(Site, zip_code=None)
    assert absent.city is None
    assert absent.model_fields_set == {"zip_code"}


def test_an_edit_carries_lifecycle_state_forward_on_either_backing() -> None:
    # Lifecycle state rides a slot of the Entity root's own layout rather than the
    # instance dictionary, so a published node carries it exactly as an ordinary
    # one does and an edit carries it across from either.
    for value in (_ordinary(Depot, id=1, label="north"), published(Depot, id=1, label="north")):
        attach_lifecycle_state(cast("Any", value), "pinned")
        assert lifecycle_state(cast("Any", value).edit(label="south")) == "pinned"
    assert lifecycle_state(published(Depot, id=1, label="north")) is None
